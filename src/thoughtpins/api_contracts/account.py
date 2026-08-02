"""Account, safety, and device-management HTTP contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AccountDeleteRequest(BaseModel):
    confirm: str = Field(..., description="Must equal DELETE")


class InviteRedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)


class InviteRequestSubmission(BaseModel):
    note: str | None = Field(default=None, max_length=600)


class InviteRequestResponse(BaseModel):
    """What the person asking sees back.

    Deliberately says nothing about queue position or how many others are
    waiting: that is operator information, and guessing at it would only invite
    people to resubmit.
    """

    status: str = "received"
    note: str | None = None
    requested_at_utc: str | None = None


class InviteStatusResponse(BaseModel):
    """Whether this account may use the product yet, and how to ask if not."""

    invite_required: bool = False
    invite_redeemed: bool = False
    admitted: bool = True
    contact_email: str = ""
    attempts_remaining: int = 0


class SignInMethodsResponse(BaseModel):
    """What this account can currently sign in with, and how to add a password.

    `password_change_requires` is the server's decision, not a hint: an account
    that already has a password proves itself with that password, and one that
    has never had a password proves control of its inbox with a fresh emailed
    code instead. Without that second path, anyone holding a borrowed session on
    a link-only account could quietly give themselves a permanent credential.
    """

    email: str | None = None
    phone: str | None = None
    password_set: bool = False
    email_verified: bool = False
    oauth_providers: list[str] = Field(default_factory=list)
    magic_link_available: bool = False
    password_change_requires: str = Field(..., pattern="^(current_password|email_code|unavailable)$")


class PasswordSetRequest(BaseModel):
    new_password: str = Field(..., min_length=12, max_length=256)
    current_password: str | None = Field(default=None, max_length=256)
    code: str | None = Field(
        default=None,
        max_length=16,
        description="Six-digit code from a fresh sign-in email. Required when the account has no password yet.",
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password must not start or end with whitespace")
        if len(value) < 12:
            raise ValueError("Password must be at least 12 characters")
        return value


class PasswordSetResponse(BaseModel):
    status: str = "ok"
    password_set: bool = True
    other_sessions_revoked: int = 0


class LegalAcceptanceRequest(BaseModel):
    document: str = Field(..., pattern="^(privacy|terms|ai_disclosure)$")
    version: str = Field(..., min_length=1, max_length=32)


SAFETY_REPORT_CATEGORIES = {
    "unsafe_ai_output",
    "harmful_or_illegal_content",
    "copyright_concern",
    "privacy_concern",
    "harassment_or_abuse",
    "self_harm_or_crisis",
    "security_concern",
    "other",
}
SAFETY_REPORT_TARGET_TYPES = {
    "general",
    "chat_message",
    "document_source",
    "raw_entry",
    "memory_card",
    "account",
}


class SafetyReportRequest(BaseModel):
    category: str = Field(..., max_length=64)
    summary: str = Field(..., min_length=8, max_length=1000)
    target_type: str | None = Field(default=None, max_length=64)
    target_id: str | None = Field(default=None, max_length=64)
    source: str = Field(default="web", pattern="^(web|ios|android|telegram|api)$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SAFETY_REPORT_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(SAFETY_REPORT_CATEGORIES))}")
        return normalized

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("summary must be at least 8 characters")
        return normalized

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in SAFETY_REPORT_TARGET_TYPES:
            raise ValueError(f"target_type must be one of: {', '.join(sorted(SAFETY_REPORT_TARGET_TYPES))}")
        return normalized

    @field_validator("target_id")
    @classmethod
    def strip_target_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SafetyReportResponse(BaseModel):
    id: str
    status: str
    category: str
    created_at_utc: str | None = None
    support_channel: str = "support@thoughtpins.com"


class DeviceRegistrationRequest(BaseModel):
    installation_id: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    platform: str = Field(..., pattern="^(ios|android|web)$")
    device_name: str | None = Field(default=None, max_length=128)
    app_version: str | None = Field(default=None, max_length=32)
    build_number: str | None = Field(default=None, max_length=32)
    os_version: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    push_provider: str | None = Field(default=None, pattern="^(apns|fcm|webpush)$")
    push_token: str | None = Field(default=None, min_length=16, max_length=4096)
    notifications_enabled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "installation_id",
        "device_name",
        "app_version",
        "build_number",
        "os_version",
        "locale",
        "timezone",
        "push_provider",
        "push_token",
    )
    @classmethod
    def strip_optional_device_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class DeviceResponse(BaseModel):
    id: str
    installation_id: str
    platform: str
    device_name: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    os_version: str | None = None
    locale: str | None = None
    timezone: str | None = None
    push_provider: str | None = None
    push_token_present: bool = False
    notifications_enabled: bool = False
    created_at_utc: str | None = None
    last_seen_at_utc: str | None = None
    revoked_at_utc: str | None = None


class DevicesPageResponse(BaseModel):
    items: list[DeviceResponse]
    total: int


class SessionResponse(BaseModel):
    id: str
    current: bool = False
    created_at_utc: str | None = None
    expires_at_utc: str | None = None
    revoked_at_utc: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None


class SessionsPageResponse(BaseModel):
    items: list[SessionResponse]
    total: int
