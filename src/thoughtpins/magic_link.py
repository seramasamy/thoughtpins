"""Passwordless magic-link sign-in.

Solves a concrete gap: the service has no password-reset flow, so an account
created with a forgotten password is unrecoverable. A magic link removes the
password from the critical path entirely.

Security properties:
  - Only a hash of the token is stored, so a database read cannot mint links.
  - Tokens are single-use and short-lived.
  - Issuing is rate limited per email address, so the endpoint cannot be used
    to flood someone's inbox.
  - Requesting a link never reveals whether an account exists.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.auth import hash_refresh_token
from thoughtpins.config import config
from thoughtpins.db import MagicLinkToken
from thoughtpins.email_delivery import send_email
from thoughtpins.privacy import fingerprint_identifier

TOKEN_PREFIX = "tpm_"
CODE_DIGITS = 6
# A 6-digit code is only 10^6 wide, so guessing has to be capped rather than
# rate limited alone. Five tries burns the whole token.
MAX_CODE_ATTEMPTS = 5


class MagicLinkRateLimited(RuntimeError):
    """Too many links requested for one address in the current window."""


class MagicLinkInvalid(RuntimeError):
    """Token is unknown, expired, or already used."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _base_url() -> str:
    configured = (config.MAGIC_LINK_BASE_URL or "").strip().rstrip("/")
    if configured:
        return configured
    web_app = (config.WEB_APP_URL or "/app").strip()
    if web_app.startswith("http"):
        return web_app.rstrip("/")
    return f"https://thoughtpins.com{web_app.rstrip('/')}"


def build_magic_link(token: str) -> str:
    return f"{_base_url()}/?magic={token}"


def _recent_request_count(session: Session, email: str) -> int:
    window_start = _utcnow() - timedelta(hours=1)
    return (
        session.query(MagicLinkToken)
        .filter(MagicLinkToken.email == email, MagicLinkToken.created_at_utc >= window_start)
        .count()
    )


def _new_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def normalize_code(value: str) -> str:
    """Strip spaces and dashes people add when copying a code."""
    return "".join(ch for ch in (value or "") if ch.isdigit())


def issue_magic_link(
    session: Session,
    email: str,
    *,
    request_ip_hash: str | None = None,
) -> tuple[str, str]:
    """Create and email a sign-in link plus code. Returns (token, code).

    The return value exists for tests; callers must not surface it, since both
    values are credentials that belong only in the recipient's inbox.

    Raises :class:`MagicLinkRateLimited` when the address has requested too many
    links in the past hour.
    """
    limit = max(1, config.MAGIC_LINK_REQUESTS_PER_HOUR)
    if _recent_request_count(session, email) >= limit:
        raise MagicLinkRateLimited(f"Too many sign-in links requested for {fingerprint_identifier(email)}")

    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    code = _new_code()
    session.add(
        MagicLinkToken(
            email=email,
            token_hash=hash_refresh_token(token),
            code_hash=hash_refresh_token(code),
            expires_at_utc=_utcnow() + timedelta(minutes=max(1, config.MAGIC_LINK_TTL_MINUTES)),
            request_ip_hash=request_ip_hash,
        )
    )
    session.commit()

    link = build_magic_link(token)
    minutes = max(1, config.MAGIC_LINK_TTL_MINUTES)
    send_email(
        to=email,
        subject="Your Thought Pins sign-in link",
        html=_html_body(link, code, minutes),
        text=_text_body(link, code, minutes),
    )
    logger.info("Magic link issued for {}", fingerprint_identifier(email))
    return token, code


def consume_magic_code(session: Session, email: str, code: str) -> str:
    """Validate and burn a short code for one address.

    Scoped to the newest unconsumed token for that address so an attacker cannot
    spray one guess across many outstanding codes.
    """
    digits = normalize_code(code)
    if len(digits) != CODE_DIGITS:
        raise MagicLinkInvalid("Malformed sign-in code")

    record = (
        session.query(MagicLinkToken)
        .filter(
            MagicLinkToken.email == email,
            MagicLinkToken.consumed_at_utc.is_(None),
            MagicLinkToken.code_hash.isnot(None),
        )
        .order_by(MagicLinkToken.created_at_utc.desc())
        .first()
    )
    if record is None:
        raise MagicLinkInvalid("No sign-in code is outstanding for this address")
    if record.expires_at_utc < _utcnow():
        raise MagicLinkInvalid("Sign-in code expired")
    if record.code_attempts >= MAX_CODE_ATTEMPTS:
        raise MagicLinkInvalid("Too many incorrect attempts; request a new code")

    if not secrets.compare_digest(record.code_hash or "", hash_refresh_token(digits)):
        # Persist the failed attempt before returning, so a crash or a dropped
        # connection cannot reset the counter.
        record.code_attempts = int(record.code_attempts or 0) + 1
        session.commit()
        raise MagicLinkInvalid("Incorrect sign-in code")

    record.consumed_at_utc = _utcnow()
    session.commit()
    return record.email


def consume_magic_link(session: Session, token: str) -> str:
    """Validate and burn a token, returning the email it was issued for."""
    if not token or not token.startswith(TOKEN_PREFIX):
        raise MagicLinkInvalid("Malformed sign-in link")

    record = session.query(MagicLinkToken).filter(MagicLinkToken.token_hash == hash_refresh_token(token)).first()
    if record is None:
        raise MagicLinkInvalid("Unknown sign-in link")
    if record.consumed_at_utc is not None:
        raise MagicLinkInvalid("Sign-in link already used")
    if record.expires_at_utc < _utcnow():
        raise MagicLinkInvalid("Sign-in link expired")

    record.consumed_at_utc = _utcnow()
    session.commit()
    return record.email


def purge_expired_tokens(session: Session, *, older_than_days: int = 7) -> int:
    """Drop long-dead tokens so the table does not grow without bound."""
    cutoff = _utcnow() - timedelta(days=max(1, older_than_days))
    removed = (
        session.query(MagicLinkToken)
        .filter(MagicLinkToken.expires_at_utc < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    return int(removed or 0)


def _text_body(link: str, code: str, minutes: int) -> str:
    return (
        "Sign in to Thought Pins\n\n"
        f"{link}\n\n"
        f"Or enter this code: {code}\n\n"
        f"The link and the code each work once and expire in {minutes} minutes.\n"
        "Use the code if your email is on a different device than the one you "
        "are signing in on.\n\n"
        "If you did not request this, you can ignore this email. Nobody can "
        "access your account without the link or the code above.\n"
    )


def _html_body(link: str, code: str, minutes: int) -> str:
    safe_link = escape(link, quote=True)
    safe_code = escape(code)
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:32px;background:#faf7f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#221d16;">
    <div style="max-width:480px;margin:0 auto;background:#ffffff;border:1px solid #e6e2dd;border-radius:8px;padding:32px;">
      <h1 style="margin:0 0 16px;font-size:22px;font-weight:600;">Sign in to Thought Pins</h1>
      <p style="margin:0 0 24px;font-size:15px;line-height:1.5;color:#6b6459;">
        Use the button below to sign in. It works once and expires in {minutes} minutes.
      </p>
      <a href="{safe_link}"
         style="display:inline-block;padding:13px 26px;border-radius:8px;background:#b33e16;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;">
        Sign in
      </a>
      <p style="margin:28px 0 8px;font-size:13px;line-height:1.5;color:#6b6459;">
        On a different device? Enter this code instead:
      </p>
      <p style="margin:0;font-size:30px;font-weight:600;letter-spacing:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#221d16;">
        {safe_code}
      </p>
      <p style="margin:24px 0 0;font-size:13px;line-height:1.5;color:#948c7f;">
        If you did not request this, you can ignore this email. Nobody can access
        your account without the link or the code.
      </p>
    </div>
  </body>
</html>
"""
