"""Sign-in methods an account holds, and the rules for gaining a password.

Thought Pins deliberately keeps every sign-in method pointed at the same account
rather than at separate identities: an address that signed up with a password can
later use a link or a code, and an address that signed up with a link or with
Google can later gain a password. What changes between those cases is the proof
required before a password is written.

An account that already has a password proves itself with that password. An
account that has never had one has nothing to prove itself with, so it re-proves
control of its inbox with a fresh emailed code. Skipping that second step would
mean a borrowed or stolen session on a link-only account could mint a permanent
credential silently — a password outlives the session that created it, so it is
the one setting that must not be reachable from session possession alone.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from thoughtpins.auth import hash_password, verify_password
from thoughtpins.config import config
from thoughtpins.db import AuthSession, OAuthCredential, User
from thoughtpins.email_verification import is_email_verified, mark_email_verified
from thoughtpins.magic_link import MagicLinkInvalid, consume_magic_code

PROOF_CURRENT_PASSWORD = "current_password"
PROOF_EMAIL_CODE = "email_code"
PROOF_UNAVAILABLE = "unavailable"


class CredentialProofRequired(ValueError):
    """The supplied proof was missing, wrong, or expired."""


class CredentialProofUnavailable(ValueError):
    """This account has no way to prove itself, so no password can be set."""


def required_proof(user: User) -> str:
    """Return which proof this account must supply before a password is set."""
    if user.password_hash:
        return PROOF_CURRENT_PASSWORD
    if user.email and config.MAGIC_LINK_ENABLED:
        return PROOF_EMAIL_CODE
    # Phone-only and Telegram-only accounts have no inbox to mail a code to.
    return PROOF_UNAVAILABLE


def oauth_providers(session: Session, user_id: str) -> list[str]:
    rows = (
        session.query(OAuthCredential.provider)
        .filter(OAuthCredential.user_id == user_id, OAuthCredential.revoked_at_utc.is_(None))
        .all()
    )
    return sorted({row[0] for row in rows})


def sign_in_methods(session: Session, user: User) -> dict[str, object]:
    """Describe every way this account can currently get in."""
    return {
        "email": user.email,
        "phone": user.phone,
        "password_set": bool(user.password_hash),
        "email_verified": bool(user.email) and is_email_verified(user),
        "oauth_providers": oauth_providers(session, user.id),
        # A link or code reaches an account whenever it has a verified address,
        # whichever method originally created it.
        "magic_link_available": bool(user.email and config.MAGIC_LINK_ENABLED),
        "password_change_requires": required_proof(user),
    }


def set_password(
    session: Session,
    user: User,
    *,
    new_password: str,
    current_password: str | None = None,
    code: str | None = None,
    current_auth_session_id: str | None = None,
) -> int:
    """Set or replace this account's password, returning sessions revoked.

    Raises CredentialProofRequired when the proof does not hold, and
    CredentialProofUnavailable when the account cannot supply one at all.
    """
    proof = required_proof(user)

    if proof == PROOF_UNAVAILABLE:
        raise CredentialProofUnavailable("Add a verified email address to this account before setting a password.")

    if proof == PROOF_CURRENT_PASSWORD:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise CredentialProofRequired("Current password is incorrect")
        if verify_password(new_password, user.password_hash):
            raise CredentialProofRequired("Choose a password different from the current one")
    else:
        if not code:
            raise CredentialProofRequired("A sign-in code is required")
        try:
            verified_email = consume_magic_code(session, user.email or "", code)
        except MagicLinkInvalid as exc:
            raise CredentialProofRequired("Invalid or expired sign-in code") from exc
        if verified_email != (user.email or ""):
            raise CredentialProofRequired("Invalid or expired sign-in code")
        # Consuming the code proves inbox control, which is what verification asks
        # for; record it so the new password is usable immediately.
        mark_email_verified(user)

    user.password_hash = hash_password(new_password)
    if user.auth_method != "password":
        # OAuth and link accounts keep their other methods; the label just stops
        # claiming the account has no password of its own.
        user.auth_method = "password"

    revoked = _revoke_other_sessions(session, user.id, current_auth_session_id)
    session.commit()
    return revoked


def _revoke_other_sessions(session: Session, user_id: str, keep_session_id: str | None) -> int:
    """Sign out every other device, the standard response to a credential change."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    query = session.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at_utc.is_(None),
        AuthSession.expires_at_utc > now,
    )
    if keep_session_id:
        query = query.filter(AuthSession.id != keep_session_id)
    rows = query.all()
    for auth_session in rows:
        auth_session.revoked_at_utc = now
    return len(rows)
