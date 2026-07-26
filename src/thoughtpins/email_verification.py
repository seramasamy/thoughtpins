"""Email verification token helpers.

This module creates and verifies tokens. Delivery is intentionally left to the
deployment layer until an email provider is configured.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from thoughtpins.auth import hash_refresh_token
from thoughtpins.config import config
from thoughtpins.db import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _prefs(user: User) -> dict[str, Any]:
    return dict(user.preferences_json or {})


def create_email_verification_token(user: User) -> str:
    token = "tpv_" + secrets.token_urlsafe(32)
    prefs = _prefs(user)
    prefs["email_verification"] = {
        "verified": False,
        "token_hash": hash_refresh_token(token),
        "expires_at_utc": (_utcnow() + timedelta(hours=config.EMAIL_VERIFICATION_TOKEN_TTL_HOURS)).isoformat(),
    }
    user.preferences_json = prefs
    return token


def is_email_verified(user: User) -> bool:
    if not config.REQUIRE_EMAIL_VERIFICATION:
        return True
    prefs = _prefs(user)
    verification = prefs.get("email_verification") or {}
    return bool(verification.get("verified"))


def verify_email_token(user: User, token: str) -> bool:
    prefs = _prefs(user)
    verification = dict(prefs.get("email_verification") or {})
    if not verification:
        return False
    expires_raw = verification.get("expires_at_utc")
    if not isinstance(expires_raw, str):
        return False
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except ValueError:
        return False
    if expires_at < _utcnow():
        return False
    if verification.get("token_hash") != hash_refresh_token(token):
        return False
    verification["verified"] = True
    verification.pop("token_hash", None)
    prefs["email_verification"] = verification
    user.preferences_json = prefs
    return True
