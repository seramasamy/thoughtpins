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


def issue_magic_link(
    session: Session,
    email: str,
    *,
    request_ip_hash: str | None = None,
) -> str:
    """Create and email a sign-in link. Returns the raw token (tests only).

    Raises :class:`MagicLinkRateLimited` when the address has requested too many
    links in the past hour.
    """
    limit = max(1, config.MAGIC_LINK_REQUESTS_PER_HOUR)
    if _recent_request_count(session, email) >= limit:
        raise MagicLinkRateLimited(f"Too many sign-in links requested for {fingerprint_identifier(email)}")

    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    session.add(
        MagicLinkToken(
            email=email,
            token_hash=hash_refresh_token(token),
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
        html=_html_body(link, minutes),
        text=_text_body(link, minutes),
    )
    logger.info("Magic link issued for {}", fingerprint_identifier(email))
    return token


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


def _text_body(link: str, minutes: int) -> str:
    return (
        "Sign in to Thought Pins\n\n"
        f"{link}\n\n"
        f"This link works once and expires in {minutes} minutes.\n"
        "If you did not request it, you can ignore this email. "
        "Nobody can access your account without opening the link above.\n"
    )


def _html_body(link: str, minutes: int) -> str:
    safe_link = escape(link, quote=True)
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
      <p style="margin:24px 0 0;font-size:13px;line-height:1.5;color:#948c7f;">
        If you did not request this, you can ignore this email. Nobody can access
        your account without opening the link.
      </p>
    </div>
  </body>
</html>
"""
