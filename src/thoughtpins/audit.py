"""Audit log helpers for user-visible security and data lifecycle events."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from thoughtpins.db import AuditLog
from thoughtpins.privacy import fingerprint_identifier

MAX_AUDIT_METADATA_STRING = 200
MAX_AUDIT_METADATA_ITEMS = 20

_DROP_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "content",
    "cookie",
    "credential",
    "id_token",
    "message",
    "password",
    "prompt",
    "raw_text",
    "refresh_token",
    "secret",
    "set_cookie",
    "text",
    "token",
}
_DROP_KEY_PARTS = (
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)
_FINGERPRINT_KEYS = {"client_ip", "ip", "ip_address", "remote_addr"}


def record_audit_event(
    session: Session,
    *,
    user_id: str | None,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a compact audit event without leaking journal content."""
    if user_id and session.bind and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": user_id},
        )

    try:
        session.add(
            AuditLog(
                user_id=user_id,
                action=action[:64],
                metadata_json=_safe_metadata(metadata or {}),
            )
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(
            "Audit event write failed action={} user_id_hash={}: {}",
            action,
            fingerprint_identifier(user_id),
            e,
        )


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        safe_key, safe_value = _sanitize_metadata_item(key, value)
        if safe_key is None:
            continue
        safe[safe_key] = safe_value
    return safe


def _sanitize_metadata_item(key: str, value: Any) -> tuple[str | None, Any]:
    normalized = _normalize_key(key)
    if _should_drop_key(normalized):
        return None, None
    if normalized in _FINGERPRINT_KEYS:
        return f"{normalized}_hash", fingerprint_identifier(value)
    return key, _sanitize_metadata_value(value)


def _sanitize_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:MAX_AUDIT_METADATA_ITEMS]:
            safe_key, safe_value = _sanitize_metadata_item(str(raw_key), raw_value)
            if safe_key is not None:
                safe[safe_key] = safe_value
        return safe
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata_value(item) for item in list(value)[:MAX_AUDIT_METADATA_ITEMS]]
    if isinstance(value, str):
        return value[:MAX_AUDIT_METADATA_STRING]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_AUDIT_METADATA_STRING]


def _should_drop_key(normalized_key: str) -> bool:
    if normalized_key in _DROP_KEYS:
        return True
    if normalized_key.endswith("_hash"):
        return True
    if normalized_key.endswith("_token"):
        return True
    return any(part in normalized_key for part in _DROP_KEY_PARTS)


def _normalize_key(key: str) -> str:
    return key.lower().replace("-", "_")
