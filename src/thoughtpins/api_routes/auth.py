"""Authentication and registration API routes."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from thoughtpins.apple_oauth import AppleOAuthError, exchange_apple_authorization_code
from thoughtpins.audit import record_audit_event
from thoughtpins.auth import (
    hash_password,
    issue_token_pair,
    refresh_token_pair,
    revoke_refresh_token,
    verify_password,
)
from thoughtpins.config import config
from thoughtpins.db import User
from thoughtpins.email_verification import (
    create_email_verification_token,
    is_email_verified,
    mark_email_verified,
    verify_email_token,
)
from thoughtpins.email_delivery import EmailDeliveryError
from thoughtpins.magic_link import (
    MagicLinkInvalid,
    MagicLinkRateLimited,
    consume_magic_code,
    consume_magic_link,
    issue_magic_link,
)
from thoughtpins.oauth import verify_oauth_id_token
from thoughtpins.privacy import fingerprint_identifier
from thoughtpins.oauth_accounts import (
    OAuthAccountError,
    OAuthIdentityConflict,
    OAuthRegistrationDisabled,
    resolve_oauth_user,
    store_refresh_credential,
)
from thoughtpins.store import get_session
from thoughtpins.users import (
    get_user_by_email,
    get_user_by_phone,
)
from thoughtpins.users import (
    register_user as create_user,
)


class RegisterRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    phone: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=128)
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"email": "user@example.com", "password": "correct horse battery staple"},
                {"phone": "+15555550123", "password": "correct horse battery staple"},
            ]
        }
    }

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return _normalize_email_address(value)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return _normalize_phone_number(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.strip() != value:
            raise ValueError("Password must not start or end with whitespace")
        if len(value) < 12:
            raise ValueError("Password must be at least 12 characters")
        return value

    @field_validator("display_name", "telegram_chat_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RegisterResponse(BaseModel):
    status: str
    user_id: str
    api_key: str | None = None
    email_verification_required: bool = False
    verification_token: str | None = Field(default=None, description="Returned only in non-production local testing")


class LoginRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    identifier: str | None = Field(
        default=None,
        max_length=255,
        description="Email or phone number. Kept separate from email/phone for simple clients.",
    )
    password: str = Field(..., min_length=1, max_length=256)
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"email": "user@example.com", "password": "correct horse battery staple"},
                {"identifier": "+15555550123", "password": "correct horse battery staple"},
            ]
        }
    }

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return _normalize_email_address(value)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return _normalize_phone_number(value)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if "@" in value:
            return _normalize_email_address(value)
        return _normalize_phone_number(value)

    def lookup(self) -> tuple[str, str] | None:
        if self.email:
            return "email", self.email
        if self.phone:
            return "phone", self.phone
        if self.identifier:
            return ("email", self.identifier) if "@" in self.identifier else ("phone", self.identifier)
        return None


class OAuthRequest(BaseModel):
    provider: str = Field(..., pattern="^(google|apple)$")
    id_token: str = Field(..., min_length=20, max_length=8192)
    authorization_code: str | None = Field(default=None, min_length=4, max_length=4096)
    redirect_uri: str | None = Field(default=None, max_length=2048)
    nonce: str | None = Field(default=None, min_length=16, max_length=256)
    display_name: str | None = Field(default=None, max_length=128)
    model_config = {
        "json_schema_extra": {
            "examples": [{"provider": "google", "id_token": "<oidc-id-token>", "display_name": "User"}]
        }
    }


class EmailVerifyRequest(BaseModel):
    email: str = Field(..., max_length=255)
    token: str = Field(..., min_length=16, max_length=256)
    model_config = {"json_schema_extra": {"examples": [{"email": "user@example.com", "token": "tpv_example"}]}}


class MagicLinkRequest(BaseModel):
    email: str = Field(..., max_length=255)
    model_config = {"json_schema_extra": {"examples": [{"email": "user@example.com"}]}}

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _normalize_email_address(value)
        if not normalized:
            raise ValueError("Invalid email address")
        return normalized


class MagicLinkConsumeRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)
    model_config = {"json_schema_extra": {"examples": [{"token": "tpm_example"}]}}


class MagicCodeConsumeRequest(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=4, max_length=16)
    model_config = {"json_schema_extra": {"examples": [{"email": "user@example.com", "code": "123456"}]}}

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _normalize_email_address(value)
        if not normalized:
            raise ValueError("Invalid email address")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "access_token": "<jwt-access-token>",
                    "refresh_token": "<opaque-refresh-token>",
                    "token_type": "bearer",
                    "expires_in": 3600,
                }
            ]
        }
    }


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, max_length=512)


def create_auth_router(
    *,
    verify_oauth_fn: Callable[[str, str], Any] | None = None,
    exchange_apple_code_fn: Callable[..., Any] | None = None,
) -> APIRouter:
    router = APIRouter()
    oauth_verifier = verify_oauth_fn or verify_oauth_id_token
    apple_code_exchange = exchange_apple_code_fn or exchange_apple_authorization_code

    @router.post("/v1/auth/login", response_model=TokenResponse)
    async def login(req: LoginRequest, request: Request) -> TokenResponse:
        lookup = req.lookup()
        if not lookup:
            raise HTTPException(status_code=422, detail="Provide email, phone, or identifier")
        lookup_kind, lookup_value = lookup
        session = get_session()
        try:
            if lookup_kind == "email":
                user = get_user_by_email(lookup_value, session=session)
            else:
                user = get_user_by_phone(lookup_value, session=session)
            if not user or not verify_password(req.password, user.password_hash):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            if user.email and not is_email_verified(user):
                raise HTTPException(status_code=403, detail="Email verification required")
            user.last_login_utc = _utcnow()
            tokens = issue_token_pair(
                session,
                user,
                user_agent=request.headers.get("User-Agent"),
                ip_address=_client_ip(request),
            )
            record_audit_event(
                session,
                user_id=user.id,
                action="auth.login",
                metadata={"method": "password", "identifier": lookup_kind, "ip": _client_ip(request)},
            )
            return TokenResponse(**tokens)
        finally:
            session.close()

    @router.post("/v1/auth/oauth", response_model=TokenResponse)
    async def oauth_login(req: OAuthRequest, request: Request) -> TokenResponse:
        session = get_session()
        try:
            try:
                identity = oauth_verifier(req.provider, req.id_token)
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e)) from e

            apple_grant = None
            apple_client_id = None
            if identity.provider == "google" and req.nonce:
                _validate_oauth_nonce(identity.nonce, req.nonce, provider="Google")
            if identity.provider == "apple":
                apple_client_id = identity.audience or _single_apple_client_id()
                if not apple_client_id:
                    raise HTTPException(status_code=401, detail="Apple OAuth audience is unavailable")
                redirect_uri = _validated_apple_redirect_uri(req.redirect_uri)
                if config.is_production() and not req.authorization_code:
                    raise HTTPException(status_code=422, detail="Apple authorization code is required")
                if config.is_production() and not req.nonce:
                    raise HTTPException(status_code=422, detail="Apple sign-in nonce is required")
                _validate_oauth_nonce(identity.nonce, req.nonce, provider="Apple")
                if req.authorization_code:
                    try:
                        apple_grant = apple_code_exchange(
                            req.authorization_code,
                            client_id=apple_client_id,
                            redirect_uri=redirect_uri,
                        )
                    except AppleOAuthError as exc:
                        raise HTTPException(status_code=503, detail=str(exc)) from exc
                    try:
                        code_identity = oauth_verifier("apple", apple_grant.id_token)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=401, detail="Apple authorization code identity is invalid"
                        ) from exc
                    if code_identity.subject != identity.subject or code_identity.audience != identity.audience:
                        raise HTTPException(status_code=401, detail="Apple authorization code identity does not match")
                    _validate_oauth_nonce(code_identity.nonce, req.nonce, provider="Apple")

            try:
                user, credential = resolve_oauth_user(
                    session,
                    identity,
                    display_name=req.display_name,
                    allow_registration=not config.SYSTEM_LOCKED or config.ALLOW_OAUTH_REGISTRATION,
                )
                if apple_grant and apple_client_id:
                    store_refresh_credential(
                        credential,
                        refresh_token=apple_grant.refresh_token,
                        client_id=apple_client_id,
                    )
            except OAuthRegistrationDisabled as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except OAuthIdentityConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OAuthAccountError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            prefs = dict(user.preferences_json or {})
            # Remove identity data written by pre-1.0 development builds.
            prefs.pop("oauth_profiles", None)
            if identity.email_verified:
                prefs["email_verification"] = {"verified": True, "provider": identity.provider}
            user.preferences_json = prefs
            user.auth_method = "oauth"
            user.last_login_utc = _utcnow()
            tokens = issue_token_pair(
                session,
                user,
                user_agent=request.headers.get("User-Agent"),
                ip_address=_client_ip(request),
            )
            record_audit_event(
                session,
                user_id=user.id,
                action="auth.oauth_login",
                metadata={"provider": identity.provider, "ip": _client_ip(request)},
            )
            return TokenResponse(**tokens)
        finally:
            session.close()

    @router.post("/v1/auth/email/verify")
    async def verify_email(req: EmailVerifyRequest) -> dict[str, str]:
        session = get_session()
        try:
            user = get_user_by_email(req.email, session=session)
            if not user or not verify_email_token(user, req.token):
                raise HTTPException(status_code=400, detail="Invalid or expired verification token")
            session.commit()
            record_audit_event(session, user_id=user.id, action="auth.email_verified")
            return {"status": "verified"}
        finally:
            session.close()

    @router.post("/v1/auth/magic-link/request")
    async def request_magic_link(req: MagicLinkRequest, request: Request) -> dict[str, str]:
        if not config.MAGIC_LINK_ENABLED:
            raise HTTPException(status_code=404, detail="Passwordless sign-in is not enabled")

        # Always answer identically. A different response for known vs unknown
        # addresses would turn this endpoint into an account-existence oracle.
        accepted = {"status": "sent"}
        session = get_session()
        try:
            user = get_user_by_email(req.email, session=session)
            if user is None and not (config.MAGIC_LINK_ALLOW_REGISTRATION and not config.SYSTEM_LOCKED):
                logger.info("Magic link requested for unknown address {}", fingerprint_identifier(req.email))
                return accepted
            try:
                issue_magic_link(
                    session,
                    req.email,
                    request_ip_hash=fingerprint_identifier(_client_ip(request)),
                )
            except MagicLinkRateLimited:
                # Also answered identically: revealing the limit would leak that
                # the address is being targeted.
                logger.info("Magic link rate limited for {}", fingerprint_identifier(req.email))
                return accepted
            except EmailDeliveryError as exc:
                # Never surface delivery outcome. Providers reject some
                # recipients and not others, so a distinct status here would
                # reintroduce exactly the enumeration oracle this endpoint
                # avoids. Failures are alerted through logging/Sentry instead.
                logger.error(
                    "Magic link delivery failed for {}: {}",
                    fingerprint_identifier(req.email),
                    exc,
                )
                return accepted
            return accepted
        finally:
            session.close()

    def _sign_in_by_email(session, email: str, request: Request, *, method: str) -> TokenResponse:
        """Shared tail of both passwordless paths: resolve or create, then issue."""
        user = get_user_by_email(email, session=session)
        created = False
        if user is None:
            if config.SYSTEM_LOCKED or not config.MAGIC_LINK_ALLOW_REGISTRATION:
                raise HTTPException(status_code=403, detail="Registration is disabled")
            try:
                create_user(email=email, password_hash=None)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            user = get_user_by_email(email, session=session)
            created = True
            if user is None:
                raise HTTPException(status_code=500, detail="Could not create the account")

        # Receiving the link or code proves control of the inbox, which is what
        # email verification asks for; record it so verification-gated logins are
        # not blocked afterwards.
        mark_email_verified(user)
        user.last_login_utc = _utcnow()
        tokens = issue_token_pair(
            session,
            user,
            user_agent=request.headers.get("User-Agent"),
            ip_address=_client_ip(request),
        )
        record_audit_event(
            session,
            user_id=user.id,
            action="auth.magic_link",
            metadata={"method": method, "created": created, "ip": _client_ip(request)},
        )
        return TokenResponse(**tokens)

    @router.post("/v1/auth/magic-link/consume", response_model=TokenResponse)
    async def consume_magic_link_route(req: MagicLinkConsumeRequest, request: Request) -> TokenResponse:
        if not config.MAGIC_LINK_ENABLED:
            raise HTTPException(status_code=404, detail="Passwordless sign-in is not enabled")
        session = get_session()
        try:
            try:
                email = consume_magic_link(session, req.token)
            except MagicLinkInvalid as exc:
                raise HTTPException(status_code=400, detail="Invalid or expired sign-in link") from exc
            return _sign_in_by_email(session, email, request, method="magic_link")
        finally:
            session.close()

    @router.post("/v1/auth/magic-code/consume", response_model=TokenResponse)
    async def consume_magic_code_route(req: MagicCodeConsumeRequest, request: Request) -> TokenResponse:
        if not config.MAGIC_LINK_ENABLED:
            raise HTTPException(status_code=404, detail="Passwordless sign-in is not enabled")
        session = get_session()
        try:
            try:
                email = consume_magic_code(session, req.email, req.code)
            except MagicLinkInvalid as exc:
                # One message for every failure mode. Distinguishing "wrong code"
                # from "no code outstanding" would say whether an address has a
                # pending sign-in.
                raise HTTPException(status_code=400, detail="Invalid or expired sign-in code") from exc
            return _sign_in_by_email(session, email, request, method="magic_code")
        finally:
            session.close()

    @router.post("/v1/auth/refresh", response_model=TokenResponse)
    async def refresh(req: RefreshRequest, request: Request) -> TokenResponse:
        session = get_session()
        try:
            tokens = refresh_token_pair(
                session,
                req.refresh_token,
                user_agent=request.headers.get("User-Agent"),
                ip_address=_client_ip(request),
            )
            if not tokens:
                raise HTTPException(status_code=401, detail="Invalid refresh token")
            return TokenResponse(**tokens)
        finally:
            session.close()

    @router.post("/v1/auth/logout")
    async def logout(req: LogoutRequest) -> dict[str, str]:
        session = get_session()
        try:
            revoke_refresh_token(session, req.refresh_token)
            return {"status": "ok"}
        finally:
            session.close()

    @router.post("/register", response_model=RegisterResponse)
    @router.post("/v1/auth/register", response_model=RegisterResponse)
    async def register_user(req: RegisterRequest, request: Request) -> RegisterResponse:
        if config.SYSTEM_LOCKED:
            raise HTTPException(
                status_code=403,
                detail="System is locked. Registration is disabled.",
            )
        if not (req.email or req.phone or req.telegram_chat_id):
            raise HTTPException(status_code=422, detail="Provide email, phone, or telegram_chat_id")
        if (req.email or req.phone) and not req.password:
            raise HTTPException(status_code=422, detail="Password is required for email or phone registration")
        try:
            user = create_user(
                email=req.email,
                phone=req.phone,
                display_name=req.display_name,
                telegram_chat_id=req.telegram_chat_id,
                password_hash=hash_password(req.password) if req.password else None,
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

        verification_token = None
        if config.REQUIRE_EMAIL_VERIFICATION and user.email:
            session = get_session()
            try:
                db_user = session.query(User).filter(User.id == user.id).first()
                if db_user:
                    verification_token = create_email_verification_token(db_user)
                    session.commit()
            finally:
                session.close()
        session = get_session()
        try:
            record_audit_event(
                session,
                user_id=user.id,
                action="auth.register",
                metadata={"method": user.auth_method, "ip": _client_ip(request)},
            )
        finally:
            session.close()
        return RegisterResponse(
            status="ok",
            user_id=user.id,
            api_key=user.api_key if config.RETURN_API_KEY_ON_REGISTER else None,
            email_verification_required=bool(config.REQUIRE_EMAIL_VERIFICATION and user.email),
            verification_token=verification_token if not config.is_production() else None,
        )

    return router


def _normalize_phone_number(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    cleaned = re.sub(r"[\s().-]+", "", value)
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits.isdigit() or not (7 <= len(digits) <= 15):
        raise ValueError("Phone must contain 7 to 15 digits")
    return f"+{digits}" if cleaned.startswith("+") else digits


def _normalize_email_address(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("Invalid email address")
    return value


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _single_apple_client_id() -> str | None:
    return config.APPLE_OAUTH_CLIENT_IDS[0] if len(config.APPLE_OAUTH_CLIENT_IDS) == 1 else None


def _validated_apple_redirect_uri(value: str | None) -> str | None:
    if not value:
        return None
    if value not in config.APPLE_OAUTH_REDIRECT_URIS:
        raise HTTPException(status_code=400, detail="Apple redirect URI is not configured")
    return value


def _validate_oauth_nonce(token_nonce: str | None, request_nonce: str | None, *, provider: str) -> None:
    if not request_nonce:
        return
    if not token_nonce or not secrets.compare_digest(token_nonce, request_nonce):
        raise HTTPException(status_code=401, detail=f"{provider} sign-in nonce validation failed")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
