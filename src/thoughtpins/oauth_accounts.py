"""Durable OAuth identity linking and revocable credential storage."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from thoughtpins.crypto import decrypt_text, encrypt_for_storage
from thoughtpins.db import OAuthCredential, User
from thoughtpins.oauth import OAuthIdentity
from thoughtpins.users import get_user_by_email, register_user


class OAuthAccountError(RuntimeError):
    pass


class OAuthRegistrationDisabled(OAuthAccountError):
    pass


class OAuthIdentityConflict(OAuthAccountError):
    pass


def provider_subject_hash(provider: str, subject: str) -> str:
    normalized = f"{provider.strip().lower()}\0{subject}".encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def resolve_oauth_user(
    session: Session,
    identity: OAuthIdentity,
    *,
    display_name: str | None,
    allow_registration: bool,
) -> tuple[User, OAuthCredential]:
    """Resolve an existing provider link or create one without unsafe email linking."""
    subject_hash = provider_subject_hash(identity.provider, identity.subject)
    credential = (
        session.query(OAuthCredential)
        .filter(
            OAuthCredential.provider == identity.provider,
            OAuthCredential.provider_subject_hash == subject_hash,
        )
        .first()
    )
    if credential:
        user = (
            session.query(User)
            .filter(
                User.id == credential.user_id,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
        if not user:
            raise OAuthIdentityConflict("The linked account is unavailable")
        credential.last_used_at_utc = _utcnow()
        credential.updated_at_utc = _utcnow()
        credential.revoked_at_utc = None
        return user, credential

    # Email is an account-linking key only when the identity provider attests it.
    user = get_user_by_email(identity.email, session=session) if identity.email and identity.email_verified else None
    if not user:
        if not allow_registration:
            raise OAuthRegistrationDisabled("OAuth registration is disabled")
        user = register_user(
            email=identity.email if identity.email_verified else None,
            display_name=display_name or identity.email or f"{identity.provider.title()} user",
            session=session,
            bypass_system_lock=True,
        )

    existing_link = (
        session.query(OAuthCredential)
        .filter(OAuthCredential.user_id == user.id, OAuthCredential.provider == identity.provider)
        .first()
    )
    if existing_link:
        raise OAuthIdentityConflict("This account is already linked to a different provider identity")

    credential = OAuthCredential(
        user_id=user.id,
        provider=identity.provider,
        provider_subject_hash=subject_hash,
        client_id=identity.audience,
    )
    session.add(credential)
    session.flush()
    return user, credential


def store_refresh_credential(
    credential: OAuthCredential,
    *,
    refresh_token: str,
    client_id: str,
) -> None:
    encrypted = encrypt_for_storage(refresh_token)
    if not encrypted:
        raise OAuthAccountError("Credential encryption is unavailable")
    credential.refresh_token_encrypted = encrypted
    credential.client_id = client_id
    credential.updated_at_utc = _utcnow()
    credential.revoked_at_utc = None


def revoke_apple_credentials(
    session: Session,
    user_id: str,
    *,
    revoke_fn: Callable[..., None],
) -> dict[str, int]:
    """Attempt remote revocation while retaining failed credentials for retry."""
    credentials = (
        session.query(OAuthCredential)
        .filter(
            OAuthCredential.user_id == user_id,
            OAuthCredential.provider == "apple",
            OAuthCredential.revoked_at_utc.is_(None),
        )
        .all()
    )
    result = {"attempted": 0, "revoked": 0, "failed": 0}
    for credential in credentials:
        if not credential.refresh_token_encrypted or not credential.client_id:
            continue
        result["attempted"] += 1
        refresh_token = decrypt_text(credential.refresh_token_encrypted)
        if not refresh_token:
            result["failed"] += 1
            continue
        try:
            revoke_fn(refresh_token, client_id=credential.client_id)
        except Exception:
            result["failed"] += 1
            continue
        credential.revoked_at_utc = _utcnow()
        credential.updated_at_utc = _utcnow()
        result["revoked"] += 1
    session.flush()
    return result


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
