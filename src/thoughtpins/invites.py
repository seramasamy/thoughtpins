"""Private-launch admission: who may actually use Thought Pins yet.

Registration is deliberately left open. Someone can create an account, verify
their address, and have their details kept — they simply cannot use the product
until they redeem a code. Keeping those two steps apart means the waiting list
is made of real accounts rather than a separate list of email addresses, and
turning the gate off later admits everyone without a migration.

Codes are stored hashed for the same reason refresh tokens are: a leaked
database should not hand out working invitations.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from thoughtpins.auth import hash_refresh_token
from thoughtpins.config import config
from thoughtpins.db import InviteCode, User

# Unambiguous alphabet: no O/0, I/1, or U, so a code read aloud or copied from a
# handwritten note does not fail for the wrong reason.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTVWXYZ23456789"
CODE_GROUPS = 3
CODE_GROUP_SIZE = 4
MAX_REDEEM_ATTEMPTS = 10


class InviteInvalid(ValueError):
    """The supplied code is unknown, expired, revoked, or fully used."""


class InviteAttemptsExhausted(ValueError):
    """Too many wrong codes from this account."""


def normalize_code(value: str) -> str:
    """Accept what people actually type: spaces, dashes, and any case."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def format_code(code: str) -> str:
    """Group a normalized code for display, the way it is issued."""
    normalized = normalize_code(code)
    return "-".join(normalized[index : index + CODE_GROUP_SIZE] for index in range(0, len(normalized), CODE_GROUP_SIZE))


def generate_code() -> str:
    """Return a new random code in its display form."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUPS * CODE_GROUP_SIZE))
    return format_code(raw)


def create_invite_code(
    session: Session,
    *,
    label: str | None = None,
    max_uses: int = 1,
    expires_at: datetime | None = None,
) -> tuple[InviteCode, str]:
    """Mint a code, returning the row and the plaintext, which is not stored."""
    code = generate_code()
    record = InviteCode(
        code_hash=hash_refresh_token(normalize_code(code)),
        label=(label or "").strip()[:128] or None,
        max_uses=max(1, int(max_uses)),
        used_count=0,
        expires_at_utc=expires_at,
    )
    session.add(record)
    session.flush()
    return record, code


def invite_required() -> bool:
    return bool(config.INVITE_ONLY)


def has_redeemed(user: User) -> bool:
    return user.invite_redeemed_at_utc is not None


def admitted(user: User) -> bool:
    """Whether this account may use the product right now."""
    if not invite_required():
        return True
    # An operator has to be able to get in to issue the first code.
    if user.is_admin:
        return True
    return has_redeemed(user)


def redeem(session: Session, user: User, code: str) -> InviteCode:
    """Admit this account, or raise. Never reveals which part was wrong."""
    if has_redeemed(user):
        # Redeeming twice is a no-op rather than an error: a double-submitted
        # form should not look like a failure.
        existing = session.query(InviteCode).filter(InviteCode.id == user.invite_code_id).first()
        if existing is not None:
            return existing

    attempts = _attempt_count(user)
    if attempts >= MAX_REDEEM_ATTEMPTS:
        raise InviteAttemptsExhausted("Too many attempts. Request a new code by email.")

    normalized = normalize_code(code)
    record = (
        session.query(InviteCode).filter(InviteCode.code_hash == hash_refresh_token(normalized)).first()
        if normalized
        else None
    )
    now = _utcnow()
    if record is None or not _usable(record, now):
        _record_attempt(user, attempts + 1)
        session.commit()
        raise InviteInvalid("That code is not valid.")

    record.used_count = int(record.used_count or 0) + 1
    user.invite_code_id = record.id
    user.invite_redeemed_at_utc = now
    _record_attempt(user, 0)
    session.commit()
    return record


def status(user: User) -> dict[str, object]:
    return {
        "invite_required": invite_required(),
        "invite_redeemed": has_redeemed(user),
        "admitted": admitted(user),
        "contact_email": config.INVITE_REQUEST_EMAIL,
        "attempts_remaining": max(0, MAX_REDEEM_ATTEMPTS - _attempt_count(user)),
    }


def _usable(record: InviteCode, now: datetime) -> bool:
    if record.revoked_at_utc is not None:
        return False
    if record.expires_at_utc is not None and record.expires_at_utc < now:
        return False
    return int(record.used_count or 0) < int(record.max_uses or 1)


def _attempt_count(user: User) -> int:
    prefs = user.preferences_json or {}
    invite = prefs.get("invite") if isinstance(prefs, dict) else None
    if not isinstance(invite, dict):
        return 0
    try:
        return int(invite.get("attempts") or 0)
    except (TypeError, ValueError):
        return 0


def _record_attempt(user: User, attempts: int) -> None:
    prefs = dict(user.preferences_json or {})
    invite = dict(prefs.get("invite") or {}) if isinstance(prefs.get("invite"), dict) else {}
    invite["attempts"] = attempts
    prefs["invite"] = invite
    user.preferences_json = prefs


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
