"""JWT and refresh-session authentication helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import AuthSession, User

_password_hasher = PasswordHasher()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def _jwt_secret() -> str:
    # Boot validation already refuses production without JWT_SECRET, but this
    # function is the thing that signs every access token, so it refuses on its
    # own too: a process that somehow reached here misconfigured must not mint
    # tokens under the API key or a string printed in this file.
    if not config.JWT_SECRET and config.is_production():
        raise RuntimeError("JWT_SECRET is not set; refusing to sign tokens with a fallback secret in production.")
    return config.JWT_SECRET or config.API_KEY or "thoughtpins-local-dev-secret"


def create_access_token(user: User, session_id: str | None = None) -> str:
    now = _utcnow()
    expires_at = now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user.id,
        "email": user.email,
        "sid": session_id,
        "type": "access",
        "exp": expires_at,
        "iat": now,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[config.JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def create_refresh_session(
    session: Session,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[AuthSession, str]:
    refresh_token = "tpr_" + secrets.token_urlsafe(48)
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at_utc=_utcnow() + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=(user_agent or "")[:255] or None,
        ip_address=(ip_address or "")[:64] or None,
    )
    session.add(auth_session)
    session.flush()
    return auth_session, refresh_token


def issue_token_pair(
    session: Session,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    auth_session, refresh_token = create_refresh_session(
        session,
        user,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.commit()
    session.refresh(auth_session)
    return {
        "access_token": create_access_token(user, auth_session.id),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def authenticate_access_token(session: Session, token: str) -> User | None:
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = (
        session.query(User)
        .filter(
            User.id == user_id,
            User.is_active == True,
            User.deleted_at_utc.is_(None),
        )
        .first()
    )
    if not user:
        return None

    session_id = payload.get("sid")
    if session_id:
        auth_session = (
            session.query(AuthSession)
            .filter(
                AuthSession.id == session_id,
                AuthSession.user_id == user.id,
                AuthSession.revoked_at_utc.is_(None),
                AuthSession.expires_at_utc > _utcnow(),
            )
            .first()
        )
        if not auth_session:
            return None
    return user


def refresh_token_pair(
    session: Session,
    refresh_token: str,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any] | None:
    token_hash = hash_refresh_token(refresh_token)
    auth_session = (
        session.query(AuthSession)
        .filter(
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at_utc.is_(None),
            AuthSession.expires_at_utc > _utcnow(),
        )
        .first()
    )
    if not auth_session:
        return None

    consumed_at = _utcnow()
    claimed = (
        session.query(AuthSession)
        .filter(
            AuthSession.id == auth_session.id,
            AuthSession.revoked_at_utc.is_(None),
            AuthSession.expires_at_utc > consumed_at,
        )
        .update({AuthSession.revoked_at_utc: consumed_at}, synchronize_session=False)
    )
    if claimed != 1:
        session.rollback()
        return None

    user = (
        session.query(User)
        .filter(
            User.id == auth_session.user_id,
            User.is_active == True,
            User.deleted_at_utc.is_(None),
        )
        .first()
    )
    if not user:
        session.rollback()
        return None

    auth_session.revoked_at_utc = consumed_at
    new_session, new_refresh_token = create_refresh_session(
        session,
        user,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    auth_session.replaced_by_session_id = new_session.id
    session.commit()

    return {
        "access_token": create_access_token(user, new_session.id),
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def revoke_refresh_token(session: Session, refresh_token: str) -> bool:
    revoked_at = _utcnow()
    revoked = (
        session.query(AuthSession)
        .filter(
            AuthSession.refresh_token_hash == hash_refresh_token(refresh_token),
            AuthSession.revoked_at_utc.is_(None),
        )
        .update({AuthSession.revoked_at_utc: revoked_at}, synchronize_session=False)
    )
    if revoked != 1:
        session.rollback()
        return False
    session.commit()
    return True
