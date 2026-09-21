"""HTTP buffering and persistence for authenticated idempotent mutations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from thoughtpins.config import config
from thoughtpins.idempotency import IdempotencyClaim, abandon_request, claim_request, complete_request, request_hash
from thoughtpins.store import get_session


async def call_with_idempotency(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    user_id: str,
) -> Response:
    raw_key = request.headers.get("Idempotency-Key", "").strip()
    if not raw_key or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return await call_next(request)

    body = await request.body()
    claim = await run_in_threadpool(
        _claim,
        user_id=user_id,
        key=raw_key,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        content_type=request.headers.get("Content-Type", ""),
        body=body,
    )

    if claim.is_replay:
        return Response(
            content=claim.replay_body,
            status_code=claim.replay_status or 200,
            media_type="application/json",
            headers={"X-Idempotent-Replay": "true"},
        )

    try:
        response = await call_next(request)
    except Exception:
        await run_in_threadpool(_abandon, user_id=user_id, record_id=claim.record_id)
        raise

    # BaseHTTPMiddleware returns a streaming wrapper, while an ordinary ASGI
    # adapter can return a concrete Response. Both are valid call_next results.
    if hasattr(response, "body_iterator"):
        response_body = b"".join([chunk async for chunk in response.body_iterator])
    else:
        response_body = bytes(response.body)
    content_type = response.headers.get("Content-Type", "")
    replayable = (
        200 <= response.status_code < 400
        and content_type.lower().startswith("application/json")
        and len(response_body) <= config.IDEMPOTENCY_MAX_RESPONSE_BYTES
    )
    if claim.record_id:
        await run_in_threadpool(
            _persist,
            user_id=user_id,
            record_id=claim.record_id,
            replayable=replayable,
            response_status=response.status_code,
            response_body=response_body,
        )

    headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )


def _claim(
    *, user_id: str, key: str, method: str, path: str, query: str, content_type: str, body: bytes
) -> IdempotencyClaim:
    # Hash before opening the session, in the same worker as the claim. This
    # avoids a separate scheduling hop without holding a connection during hashing.
    fingerprint = request_hash(method=method, path=path, query=query, content_type=content_type, body=body)
    session = get_session()
    try:
        return claim_request(
            session, user_id=user_id, scope=f"{method.upper()}:{path}", key=key, fingerprint=fingerprint
        )
    finally:
        session.close()


def _persist(*, user_id: str, record_id: str, replayable: bool, response_status: int, response_body: bytes) -> None:
    session = get_session()
    try:
        if replayable:
            complete_request(
                session,
                user_id=user_id,
                record_id=record_id,
                response_status=response_status,
                response_body=response_body,
            )
        else:
            abandon_request(session, user_id=user_id, record_id=record_id)
    finally:
        session.close()


def _abandon(*, user_id: str, record_id: str | None) -> None:
    if not record_id:
        return
    session = get_session()
    try:
        abandon_request(session, user_id=user_id, record_id=record_id)
    finally:
        session.close()
