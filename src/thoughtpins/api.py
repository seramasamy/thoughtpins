"""FastAPI service for Thought Pins' journal brain."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from thoughtpins.api_contracts import COMMON_ERROR_RESPONSES
from thoughtpins.api_gateway import (
    _client_ip,
    _content_length_too_large,
    _extract_api_key,
    _is_invite_blocked,
    _is_maintenance_allowed,
    _is_public_path,
    _rate_limit_for_path,
    _resolve_request_user,
    _safe_request_id,
    _security_headers,
)
from thoughtpins.api_idempotency_http import call_with_idempotency
from thoughtpins.api_openapi import install_openapi_contract
from thoughtpins.api_routes.account import create_account_router
from thoughtpins.api_routes.admin import create_admin_router
from thoughtpins.api_routes.auth import create_auth_router
from thoughtpins.api_routes.chat import create_chat_router
from thoughtpins.api_routes.entries import create_entries_router
from thoughtpins.api_routes.exports import create_exports_router
from thoughtpins.api_routes.library import create_library_router
from thoughtpins.api_routes.memory import create_memory_router
from thoughtpins.api_routes.metadata import create_metadata_router
from thoughtpins.api_routes.public import create_public_router
from thoughtpins.api_routes.voice import create_voice_router
from thoughtpins.apple_oauth import exchange_apple_authorization_code, revoke_apple_refresh_token
from thoughtpins.chat.engine import execute_chat_message
from thoughtpins.chat.memory_answer import answer_with_llm
from thoughtpins.config import config
from thoughtpins.idempotency import IdempotencyConflict, InvalidIdempotencyKey
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.jobs import enqueue_ingestion_job, recover_pending_jobs
from thoughtpins.library import flush_document_indexing
from thoughtpins.memory.context_package import build_memory_context_package
from thoughtpins.oauth import verify_oauth_id_token
from thoughtpins.rate_limit import RateLimitBackendUnavailable, check_rate_limit
from thoughtpins.startup_recovery import recover_orphaned_entries as _recover_orphaned_entries
from thoughtpins.store import get_session, init_db
from thoughtpins.tenancy import tenant_context
from thoughtpins.usage import UsageBudgetExceeded

_start_time = time.time()
_REQUEST_COUNTS: dict[tuple[str, str, int], int] = {}
_REQUEST_DURATIONS: list[float] = []


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _error_payload(code: str, message: str, request_id: str = "", details: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details is not None:
        payload["error"]["details"] = _json_safe(details)
    return payload


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _http_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        402: "usage_budget_exceeded",
        409: "conflict",
        413: "payload_too_large",
        429: "rate_limit_exceeded",
    }.get(status_code, "internal_error" if status_code >= 500 else "bad_request")


def _record_metric(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    key = (method, path, status_code)
    _REQUEST_COUNTS[key] = _REQUEST_COUNTS.get(key, 0) + 1
    _REQUEST_DURATIONS.append(duration_seconds)
    if len(_REQUEST_DURATIONS) > 1000:
        del _REQUEST_DURATIONS[:-1000]


def _error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    *,
    retry_after: int | None = None,
    details: Any | None = None,
) -> JSONResponse:
    headers = {"X-Request-ID": request_id}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content=_error_payload(code, message, request_id, details),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if config.RUN_STARTUP_RECOVERY:
        _recover_orphaned_entries()
    if config.PROCESS_ENTRIES_ASYNC:
        recover_pending_jobs()
    logger.info("Thought Pins API started")
    try:
        yield
    finally:
        if not flush_document_indexing(timeout_seconds=config.DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS):
            logger.warning("Document vector indexing queue did not drain before shutdown")
        try:
            from thoughtpins.memory.vector_store import close_vector_store

            close_vector_store()
        except Exception as exc:
            logger.debug("Vector store close skipped during shutdown: {}", exc)


app = FastAPI(
    title="Thought Pins API",
    description=(
        "AI journal companion backend: ingestion, query, reports, and memory graph. "
        "Errors use a consistent envelope documented at /v1/errors."
    ),
    version=config.API_VERSION,
    lifespan=lifespan,
    responses=COMMON_ERROR_RESPONSES,
)

if config.CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key", "X-Request-ID"],
        expose_headers=["Retry-After", "X-Idempotent-Replay", "X-Request-ID"],
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = _request_id(request)
    headers = dict(exc.headers or {})
    headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content=_error_payload(_http_error_code(exc.status_code), str(exc.detail), request_id),
    )


@app.exception_handler(UsageBudgetExceeded)
async def usage_budget_exception_handler(request: Request, exc: UsageBudgetExceeded) -> JSONResponse:
    """Surface a spend cap as 402 rather than a generic 500.

    Interactive chat degrades gracefully before reaching here; this covers the
    synchronous ingestion/extraction routes, where blocking is the correct and
    cheapest behaviour.
    """
    request_id = _request_id(request)
    return JSONResponse(
        status_code=402,
        headers={"X-Request-ID": request_id},
        content=_error_payload("usage_budget_exceeded", str(exc), request_id, {"scope": exc.scope}),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _request_id(request)
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": request_id},
        content=_error_payload("validation_error", "Request validation failed", request_id, exc.errors()),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception("Unhandled API error request_id={}", request_id)
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request_id},
        content=_error_payload("internal_error", "Internal server error", request_id),
    )


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    request_id = _safe_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    started = time.perf_counter()

    async def finish(response):
        response.headers["X-Request-ID"] = request_id
        for key, value in _security_headers().items():
            if key not in response.headers:
                response.headers[key] = value
        _record_metric(
            request.method,
            request.url.path,
            response.status_code,
            time.perf_counter() - started,
        )
        return response

    try:
        if _content_length_too_large(request):
            return await finish(
                _error_response(
                    413,
                    "payload_too_large",
                    "Request body is too large",
                    request_id,
                )
            )

        if config.MAINTENANCE_MODE and not _is_maintenance_allowed(request):
            return await finish(
                _error_response(
                    503,
                    "maintenance_mode",
                    config.MAINTENANCE_MESSAGE,
                    request_id,
                    retry_after=config.MAINTENANCE_RETRY_AFTER_SECONDS,
                    details={"retry_after_seconds": config.MAINTENANCE_RETRY_AFTER_SECONDS},
                )
            )

        if request.method == "OPTIONS" or _is_public_path(request.url.path):
            if request.url.path.startswith("/v1/auth/"):
                key = f"public:{_client_ip(request) or 'unknown'}:{request.url.path}"
                allowed, retry_after = check_rate_limit(key, limit=_rate_limit_for_path(request.url.path))
                if not allowed:
                    return await finish(
                        _error_response(
                            429,
                            "rate_limit_exceeded",
                            "Rate limit exceeded",
                            request_id,
                            retry_after=retry_after,
                        )
                    )
            return await finish(await call_next(request))

        key = _extract_api_key(request)
        session = get_session()
        try:
            user = _resolve_request_user(request, session, key)

            if not user:
                return await finish(
                    _error_response(
                        401,
                        "unauthorized",
                        "Missing or invalid API credentials",
                        request_id,
                    )
                )

            request.state.user_id = user.id
            request.state.user_is_admin = bool(user.is_admin)

            # Private launch. Enforced here rather than per route so a new
            # endpoint is closed until it is deliberately exempted.
            if _is_invite_blocked(user, request.url.path):
                return await finish(
                    _error_response(
                        403,
                        "invite_required",
                        "Thought Pins is in private testing. Enter an invite code to start.",
                        request_id,
                        details={"contact_email": config.INVITE_REQUEST_EMAIL},
                    )
                )

            rate_key = f"user:{user.id}:{request.url.path}"
            allowed, retry_after = check_rate_limit(rate_key, limit=_rate_limit_for_path(request.url.path))
            if not allowed:
                return await finish(
                    _error_response(
                        429,
                        "rate_limit_exceeded",
                        "Rate limit exceeded",
                        request_id,
                        retry_after=retry_after,
                    )
                )
        finally:
            session.close()

        with tenant_context(user.id):
            try:
                response = await call_with_idempotency(request, call_next, user_id=user.id)
            except InvalidIdempotencyKey as exc:
                response = _error_response(400, "invalid_idempotency_key", str(exc), request_id)
            except IdempotencyConflict as exc:
                response = _error_response(
                    409,
                    "idempotency_conflict",
                    str(exc),
                    request_id,
                    retry_after=2,
                )
            return await finish(response)
    except RateLimitBackendUnavailable:
        logger.error("Distributed rate limiting unavailable request_id={}", request_id)
        return await finish(
            _error_response(
                503,
                "rate_limit_backend_unavailable",
                "Traffic controls are temporarily unavailable. Please try again.",
                request_id,
                retry_after=5,
            )
        )
    except Exception:
        _record_metric(request.method, request.url.path, 500, time.perf_counter() - started)
        raise


def current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def current_auth_session_id(request: Request) -> str | None:
    return getattr(request.state, "auth_session_id", None)


app.include_router(
    create_metadata_router(
        start_time=_start_time,
        request_counts=_REQUEST_COUNTS,
        request_durations=_REQUEST_DURATIONS,
        current_user_dependency=current_user_id,
    )
)
app.include_router(create_public_router())
app.include_router(
    create_auth_router(
        verify_oauth_fn=lambda provider, token: verify_oauth_id_token(provider, token),
        exchange_apple_code_fn=lambda code, **kwargs: exchange_apple_authorization_code(code, **kwargs),
    )
)
app.include_router(
    create_entries_router(
        current_user_dependency=current_user_id,
        process_message_fn=lambda session, text, **kwargs: process_message(session, text, **kwargs),
        enqueue_job_fn=lambda job_id, user_id=None: enqueue_ingestion_job(job_id, user_id=user_id),
    )
)
app.include_router(
    create_chat_router(
        current_user_dependency=current_user_id,
        answer_with_llm_fn=lambda query, session, **kwargs: answer_with_llm(query, session, **kwargs),
        build_memory_context_fn=lambda query, session, **kwargs: build_memory_context_package(query, session, **kwargs),
        execute_chat_message_fn=lambda session, text, **kwargs: execute_chat_message(session, text, **kwargs),
    )
)
app.include_router(create_admin_router(current_user_dependency=current_user_id))
app.include_router(create_library_router(current_user_dependency=current_user_id))
app.include_router(create_memory_router(current_user_dependency=current_user_id, start_time=_start_time))
app.include_router(create_exports_router(current_user_dependency=current_user_id))
app.include_router(create_voice_router(current_user_dependency=current_user_id))
app.include_router(
    create_account_router(
        current_user_dependency=current_user_id,
        current_session_dependency=current_auth_session_id,
        revoke_apple_token_fn=lambda token, **kwargs: revoke_apple_refresh_token(token, **kwargs),
    )
)


install_openapi_contract(app, is_public_path=_is_public_path)
