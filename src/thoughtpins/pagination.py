"""Signed keyset cursors for stable API pagination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime

from thoughtpins.config import config


@dataclass(frozen=True)
class CursorPosition:
    occurred_at: datetime
    row_id: str


def encode_cursor(*, sort: str, direction: str, occurred_at: datetime, row_id: str) -> str:
    payload = {
        "v": 1,
        "s": sort,
        "d": _direction(direction),
        "t": occurred_at.isoformat(timespec="microseconds"),
        "i": row_id,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(_signing_key(), raw, hashlib.sha256).digest()[:16]
    return _b64(raw + signature)


def decode_cursor(value: str, *, sort: str, direction: str) -> CursorPosition:
    try:
        packed = _unb64(value)
        if len(packed) <= 16:
            raise ValueError
        raw, supplied = packed[:-16], packed[-16:]
        expected = hmac.new(_signing_key(), raw, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(supplied, expected):
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("v") != 1 or payload.get("s") != sort or payload.get("d") != _direction(direction):
            raise ValueError
        row_id = str(payload["i"])
        if not row_id or len(row_id) > 128:
            raise ValueError
        occurred_at = datetime.fromisoformat(str(payload["t"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired pagination cursor") from exc
    return CursorPosition(occurred_at=occurred_at, row_id=row_id)


def _signing_key() -> bytes:
    value = config.JWT_SECRET or config.DATA_ENCRYPTION_KEY or config.API_KEY
    if not value:
        value = "thoughtpins-development-cursor-key"
    return value.encode("utf-8")


def _direction(value: str) -> str:
    normalized = value.lower()
    if normalized not in {"asc", "desc"}:
        raise ValueError("Cursor direction must be asc or desc")
    return normalized


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    if not value or len(value) > 1024:
        raise ValueError("Invalid pagination cursor")
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
