"""HTTP buffering and persistence for authenticated idempotent mutations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from thoughtpins.config import config
from thoughtpins.idempotency import abandon_request, claim_request, complete_request, request_hash
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
    fingerprint = request_hash(
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        content_type=request.headers.get("Content-Type", ""),
        body=body,
    )
    session = get_session()
    try:
        claim = claim_request(
            session,
            user_id=user_id,
            scope=f"{request.method.upper()}:{request.url.path}",
            key=raw_key,
            fingerprint=fingerprint,
        )
    finally:
        session.close()

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
        _abandon(user_id=user_id, record_id=claim.record_id)
        raise

    response_body = b"".join([chunk async for chunk in response.body_iterator])
    content_type = response.headers.get("Content-Type", "")
    replayable = (
        200 <= response.status_code < 400
        and content_type.lower().startswith("application/json")
        and len(response_body) <= config.IDEMPOTENCY_MAX_RESPONSE_BYTES
    )
    if claim.record_id:
        persistence_session = get_session()
        try:
            if replayable:
                complete_request(
                    persistence_session,
                    user_id=user_id,
                    record_id=claim.record_id,
                    response_status=response.status_code,
                    response_body=response_body,
                )
            else:
                abandon_request(persistence_session, user_id=user_id, record_id=claim.record_id)
        finally:
            persistence_session.close()

    headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )


def _abandon(*, user_id: str, record_id: str | None) -> None:
    if not record_id:
        return
    session = get_session()
    try:
        abandon_request(session, user_id=user_id, record_id=record_id)
    finally:
        session.close()
