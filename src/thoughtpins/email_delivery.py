"""Transactional email delivery.

Delivery was deliberately left unimplemented until a provider was configured
(see :mod:`thoughtpins.email_verification`). This is that layer.

The default provider is "none", which logs instead of sending, so development
and tests never deliver real mail or need credentials.
"""

from __future__ import annotations

import httpx
from loguru import logger

from thoughtpins.config import config
from thoughtpins.privacy import fingerprint_identifier


class EmailDeliveryError(RuntimeError):
    """Delivery failed. Message text is safe to log but not to show a caller."""


def delivery_configured() -> bool:
    """Whether a real provider is wired up and able to send."""
    if config.EMAIL_PROVIDER == "resend":
        return bool(config.RESEND_API_KEY and config.EMAIL_FROM_ADDRESS)
    return False


def send_email(*, to: str, subject: str, html: str, text: str) -> None:
    """Send one transactional email.

    Raises :class:`EmailDeliveryError` on failure so callers can decide whether
    the failure is user-visible.
    """
    provider = config.EMAIL_PROVIDER

    if provider == "none" or not provider:
        # Log the body in development so magic links remain usable without a
        # provider. Guarded on provider="none", which production forbids.
        logger.info(
            "Email delivery disabled (EMAIL_PROVIDER=none). Would send to {}: {}\n{}",
            fingerprint_identifier(to),
            subject,
            text,
        )
        return

    if provider != "resend":
        raise EmailDeliveryError(f"Unsupported EMAIL_PROVIDER: {provider}")

    if not config.RESEND_API_KEY:
        raise EmailDeliveryError("RESEND_API_KEY is required when EMAIL_PROVIDER=resend")
    if not config.EMAIL_FROM_ADDRESS:
        raise EmailDeliveryError("EMAIL_FROM_ADDRESS is required when EMAIL_PROVIDER=resend")

    try:
        response = httpx.post(
            f"{config.RESEND_BASE_URL.rstrip('/')}/emails",
            headers={
                "Authorization": f"Bearer {config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": config.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            },
            timeout=max(5, config.EMAIL_TIMEOUT_SECONDS),
        )
    except httpx.HTTPError as exc:
        raise EmailDeliveryError(f"Email provider request failed: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        # Provider errors can echo the recipient address; keep it out of logs.
        raise EmailDeliveryError(f"Email provider returned {response.status_code}")

    logger.info("Email sent to {} subject={}", fingerprint_identifier(to), subject)
