"""Durable idempotency records for retried client mutations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import encrypt_for_storage, maybe_decrypt_text
from thoughtpins.db import ApiIdempotencyRecord

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")


class InvalidIdempotencyKey(ValueError):
    """Raised when a client key is unsafe or ambiguous."""


class IdempotencyConflict(RuntimeError):
    """Raised when a key is reused for a different or active request."""


@dataclass(frozen=True)
class IdempotencyClaim:
    record_id: str | None
    replay_status: int | None = None
    replay_body: bytes | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_status is not None and self.replay_body is not None


def normalize_key(value: str) -> str:
    key = value.strip()
    if not _KEY_PATTERN.fullmatch(key):
        raise InvalidIdempotencyKey(
            "Idempotency-Key must be 8-128 characters using letters, numbers, dot, colon, underscore, or hyphen"
        )
    return key


def request_hash(*, method: str, path: str, query: str, content_type: str, body: bytes) -> str:
    digest = hashlib.sha256()
    for component in (method.upper(), path, query, content_type.lower()):
        digest.update(component.encode("utf-8"))
        digest.update(b"\x00")
    digest.update(body)
    return digest.hexdigest()


def claim_request(
    session: Session,
    *,
    user_id: str,
    scope: str,
    key: str,
    fingerprint: str,
) -> IdempotencyClaim:
    """Claim a key or return its completed response for an exact replay."""
    now = _utcnow()
    normalized = normalize_key(key)
    existing = _find(session, user_id=user_id, scope=scope, key=normalized)
    if existing and existing.expires_at_utc <= now:
        session.delete(existing)
        session.commit()
        existing = None
    if existing:
        return _resolve_existing(session, existing, fingerprint=fingerprint, now=now)

    record = ApiIdempotencyRecord(
        user_id=user_id,
        scope=scope,
        idempotency_key=normalized,
        request_hash=fingerprint,
        status="in_progress",
        expires_at_utc=now + timedelta(hours=max(1, config.IDEMPOTENCY_TTL_HOURS)),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _find(session, user_id=user_id, scope=scope, key=normalized)
        if not existing:
            raise
        return _resolve_existing(session, existing, fingerprint=fingerprint, now=now)
    session.refresh(record)
    return IdempotencyClaim(record_id=record.id)


def complete_request(
    session: Session,
    *,
    user_id: str,
    record_id: str,
    response_status: int,
    response_body: bytes,
) -> None:
    record = _record(session, user_id=user_id, record_id=record_id)
    if not record:
        return
    text = response_body.decode("utf-8")
    record.response_body = encrypt_for_storage(text) or text
    record.response_status = response_status
    record.status = "completed"
    record.completed_at_utc = _utcnow()
    session.commit()


def abandon_request(session: Session, *, user_id: str, record_id: str) -> None:
    """Release a reservation after a transient or non-replayable response."""
    record = _record(session, user_id=user_id, record_id=record_id)
    if record:
        session.delete(record)
        session.commit()


def _resolve_existing(
    session: Session,
    record: ApiIdempotencyRecord,
    *,
    fingerprint: str,
    now: datetime,
) -> IdempotencyClaim:
    if record.request_hash != fingerprint:
        raise IdempotencyConflict("Idempotency-Key was already used for a different request")
    if record.status == "completed" and record.response_status is not None and record.response_body is not None:
        body = maybe_decrypt_text(record.response_body)
        return IdempotencyClaim(record_id=None, replay_status=record.response_status, replay_body=body.encode("utf-8"))
    stale_before = now - timedelta(seconds=max(30, config.IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS))
    if record.status == "in_progress" and record.created_at_utc and record.created_at_utc > stale_before:
        raise IdempotencyConflict("An identical request is still being processed")
    record.status = "in_progress"
    record.response_status = None
    record.response_body = None
    record.completed_at_utc = None
    record.created_at_utc = now
    session.commit()
    return IdempotencyClaim(record_id=record.id)


def _find(session: Session, *, user_id: str, scope: str, key: str) -> ApiIdempotencyRecord | None:
    return (
        session.query(ApiIdempotencyRecord)
        .filter(
            ApiIdempotencyRecord.user_id == user_id,
            ApiIdempotencyRecord.scope == scope,
            ApiIdempotencyRecord.idempotency_key == key,
        )
        .first()
    )


def _record(session: Session, *, user_id: str, record_id: str) -> ApiIdempotencyRecord | None:
    return (
        session.query(ApiIdempotencyRecord)
        .filter(ApiIdempotencyRecord.id == record_id, ApiIdempotencyRecord.user_id == user_id)
        .first()
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
