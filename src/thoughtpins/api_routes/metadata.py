"""Metadata, health, and metrics API routes."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from thoughtpins.config import config
from thoughtpins.runtime_health import build_deep_health_checks, build_readiness_checks, deep_health_status

ERROR_CODE_DOCS: dict[str, str] = {
    "bad_request": "The request shape is valid JSON but violates an endpoint rule.",
    "unauthorized": "Authentication credentials are missing, expired, or invalid.",
    "forbidden": "The caller is authenticated but not allowed to perform the action.",
    "not_found": "The requested resource does not exist for the authenticated user.",
    "conflict": "The request conflicts with existing data, such as duplicate registration.",
    "payload_too_large": "The request body exceeds MAX_REQUEST_BODY_BYTES.",
    "rate_limit_exceeded": "The caller exceeded the configured rate limit tier.",
    "usage_budget_exceeded": "The account or deployment reached its configured AI spend budget for the month.",
    "validation_error": "FastAPI/Pydantic rejected the request parameters or body.",
    "internal_error": "An unexpected server error occurred.",
    "maintenance_mode": "The deployment is temporarily in maintenance mode; retry after the supplied Retry-After value.",
}


class ClientConfigResponse(BaseModel):
    app_name: str
    api_version: str
    environment: str
    auth_required: bool
    registration_locked: bool

    oauth_google_enabled: bool
    oauth_apple_enabled: bool
    # Public by design: an OAuth client ID appears in the page source of every
    # site using these providers. Served here so rotating it does not require a
    # frontend rebuild.
    oauth_google_client_id: str | None = None
    oauth_apple_client_id: str | None = None
    magic_link_enabled: bool = False
    # Private launch. Told to the client before sign-in so the sign-up screen can
    # say what happens next instead of surprising people after they register.
    invite_required: bool = False
    invite_request_email: str = ""
    voice_archive_enabled: bool
    ai_processing: str
    memory_context_mode: str
    privacy_policy_url: str | None = None
    terms_url: str | None = None
    support_url: str | None = None
    account_deletion_url: str | None = None
    ai_disclosure_url: str | None = None
    legal_document_version: str
    minimum_supported_clients: dict[str, str]
    recommended_clients: dict[str, str]
    store_urls: dict[str, str | None]
    maintenance_mode: bool
    maintenance_message: str | None = None
    maintenance_retry_after_seconds: int | None = None
    maintenance_allow_reads: bool = True


def create_metadata_router(
    *,
    start_time: float,
    request_counts: dict[tuple[str, str, int], int],
    request_durations: list[float],
    current_user_dependency: Callable,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    @router.head("/health")
    @router.get("/v1/health", include_in_schema=False)
    @router.head("/v1/health", include_in_schema=False)
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - start_time, 1),
            "version": config.API_VERSION,
            "environment": config.ENVIRONMENT,
            "auth_required": config.REQUIRE_API_AUTH,
            "maintenance_mode": config.MAINTENANCE_MODE,
        }

    @router.get("/ready", include_in_schema=False)
    @router.head("/ready", include_in_schema=False)
    @router.get("/v1/health/ready", include_in_schema=False)
    @router.head("/v1/health/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        try:
            checks = await asyncio.wait_for(run_in_threadpool(build_readiness_checks), timeout=5.0)
        except TimeoutError:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "checks": {"runtime": "timeout"}},
            )
        ready = deep_health_status(checks) == "ok"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "checks": {name: str(check.get("status") or "unknown") for name, check in checks.items()},
            },
        )

    @router.get("/v1/errors", tags=["metadata"])
    async def error_catalog() -> dict[str, Any]:
        return {
            "envelope": {
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "request_id": "the X-Request-ID response header value",
                    "details": [],
                }
            },
            "codes": ERROR_CODE_DOCS,
        }

    @router.get("/v1/client-config", response_model=ClientConfigResponse, tags=["metadata"])
    async def client_config() -> ClientConfigResponse:
        return ClientConfigResponse(
            app_name=config.APP_NAME,
            api_version=config.API_VERSION,
            environment=config.ENVIRONMENT,
            auth_required=config.REQUIRE_API_AUTH,
            registration_locked=config.SYSTEM_LOCKED,
            oauth_google_enabled=bool(config.GOOGLE_OAUTH_CLIENT_IDS),
            oauth_apple_enabled=bool(config.APPLE_OAUTH_CLIENT_IDS),
            oauth_google_client_id=(config.GOOGLE_OAUTH_CLIENT_IDS[0] if config.GOOGLE_OAUTH_CLIENT_IDS else None),
            oauth_apple_client_id=(config.APPLE_OAUTH_CLIENT_IDS[0] if config.APPLE_OAUTH_CLIENT_IDS else None),
            magic_link_enabled=bool(config.MAGIC_LINK_ENABLED),
            invite_required=bool(config.INVITE_ONLY),
            invite_request_email=config.INVITE_REQUEST_EMAIL,
            voice_archive_enabled=config.VOICE_ARCHIVE_ENABLED,
            ai_processing="configured",
            memory_context_mode=config.MEMORY_CONTEXT_MODE,
            privacy_policy_url=config.PRIVACY_POLICY_URL or "/privacy",
            terms_url=config.TERMS_URL or "/terms",
            support_url=config.SUPPORT_URL or "/support",
            account_deletion_url=config.ACCOUNT_DELETION_URL or "/account/delete",
            ai_disclosure_url=config.AI_DISCLOSURE_URL or "/ai-disclosure",
            legal_document_version=config.LEGAL_DOCUMENT_VERSION,
            minimum_supported_clients={
                "ios": config.MIN_IOS_VERSION,
                "android": config.MIN_ANDROID_VERSION,
                "web": config.MIN_WEB_VERSION,
            },
            recommended_clients={
                "ios": config.RECOMMENDED_IOS_VERSION,
                "android": config.RECOMMENDED_ANDROID_VERSION,
                "web": config.RECOMMENDED_WEB_VERSION,
            },
            store_urls={
                "ios": config.IOS_STORE_URL or None,
                "android": config.ANDROID_STORE_URL or None,
                "web": config.WEB_APP_URL or None,
            },
            maintenance_mode=config.MAINTENANCE_MODE,
            maintenance_message=config.MAINTENANCE_MESSAGE if config.MAINTENANCE_MODE else None,
            maintenance_retry_after_seconds=config.MAINTENANCE_RETRY_AFTER_SECONDS if config.MAINTENANCE_MODE else None,
            maintenance_allow_reads=config.MAINTENANCE_ALLOW_READS,
        )

    @router.get("/v1/metrics", response_class=PlainTextResponse)
    async def metrics(user_id: str = Depends(current_user_dependency)) -> str:
        del user_id
        total = sum(request_counts.values())
        durations = sorted(request_durations)
        p95 = durations[int(len(durations) * 0.95) - 1] if durations else 0.0
        lines = [
            "# HELP thoughtpins_requests_total Total HTTP requests by method, path, and status.",
            "# TYPE thoughtpins_requests_total counter",
        ]
        for (method, path, status_code), count in sorted(request_counts.items()):
            safe_path = path.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(
                f'thoughtpins_requests_total{{method="{method}",path="{safe_path}",status="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP thoughtpins_request_duration_seconds_p95 Rolling in-process p95 request duration.",
                "# TYPE thoughtpins_request_duration_seconds_p95 gauge",
                f"thoughtpins_request_duration_seconds_p95 {p95:.6f}",
                "# HELP thoughtpins_uptime_seconds Process uptime in seconds.",
                "# TYPE thoughtpins_uptime_seconds gauge",
                f"thoughtpins_uptime_seconds {time.time() - start_time:.1f}",
                "# HELP thoughtpins_requests_in_memory_total Total requests seen by this process.",
                "# TYPE thoughtpins_requests_in_memory_total counter",
                f"thoughtpins_requests_in_memory_total {total}",
            ]
        )
        return "\n".join(lines) + "\n"

    @router.get("/v1/health/deep")
    async def deep_health(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        checks = build_deep_health_checks(user_id)
        return {
            "status": deep_health_status(checks),
            "uptime_seconds": round(time.time() - start_time, 1),
            "version": config.API_VERSION,
            "checks": checks,
        }

    return router
