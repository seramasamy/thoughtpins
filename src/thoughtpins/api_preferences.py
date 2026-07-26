"""Account preference schemas and policy-aware preference resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import User


class PreferencesResponse(BaseModel):
    notifications_enabled: bool = False
    reminder_hour_local: int | None = Field(default=None, ge=0, le=23)
    timezone: str | None = Field(default=None, max_length=64)
    private_entries_in_ask: bool = False
    weekly_digest_enabled: bool = False
    product_updates_enabled: bool = False
    importance_prompts_enabled: bool = False
    preferred_name: str | None = Field(default=None, max_length=128)
    response_style: str = Field(default="friendly", pattern="^(friendly|clear|mirror)$")
    legal_acceptances: dict[str, dict[str, str]] = Field(default_factory=dict)
    updated_at_utc: str | None = None


class PreferencesUpdateRequest(BaseModel):
    notifications_enabled: bool | None = None
    reminder_hour_local: int | None = Field(default=None, ge=0, le=23)
    timezone: str | None = Field(default=None, max_length=64)
    private_entries_in_ask: bool | None = None
    weekly_digest_enabled: bool | None = None
    product_updates_enabled: bool | None = None
    importance_prompts_enabled: bool | None = None
    preferred_name: str | None = Field(default=None, max_length=128)
    response_style: str | None = Field(default=None, pattern="^(friendly|clear|mirror)$")

    @field_validator("timezone", "preferred_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def preferences_response(user: User) -> PreferencesResponse:
    prefs = default_preferences(user)
    stored = dict(user.preferences_json or {})
    app_prefs = dict(stored.get("app_preferences") or {})
    prefs.update({key: value for key, value in app_prefs.items() if key in prefs})
    if prefs.get("response_style") not in {"friendly", "clear", "mirror"}:
        prefs["response_style"] = "friendly"
    prefs["legal_acceptances"] = dict(stored.get("legal_acceptances") or {})
    return PreferencesResponse(**prefs)


def upsert_app_preferences(user: User, updates: dict[str, Any]) -> None:
    prefs = dict(user.preferences_json or {})
    app_prefs = dict(prefs.get("app_preferences") or {})
    app_prefs.update(updates)
    app_prefs["updated_at_utc"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    prefs["app_preferences"] = app_prefs
    user.preferences_json = prefs


def resolve_private_context_preference(
    session: Session,
    *,
    user_id: str,
    requested: bool | None,
) -> bool:
    """Resolve per-request recall against the owned account and server policy."""
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    enabled = preferences_response(user).private_entries_in_ask if requested is None else requested
    if enabled and not config.PRIVATE_ALLOW_LLM:
        raise HTTPException(status_code=403, detail="Private-entry LLM context is disabled by server policy")
    return bool(enabled)


def default_preferences(user: User) -> dict[str, Any]:
    return {
        "notifications_enabled": False,
        "reminder_hour_local": None,
        "timezone": config.LOCAL_TIMEZONE,
        "private_entries_in_ask": False,
        "weekly_digest_enabled": False,
        "product_updates_enabled": False,
        "importance_prompts_enabled": False,
        "preferred_name": user.display_name,
        "response_style": "friendly",
        "legal_acceptances": {},
        "updated_at_utc": None,
    }
