"""Telegram runtime preconditions.

Separated from :mod:`thoughtpins.config`, which answers "what did the operator
set". Whether a particular adapter may start is policy about one surface, and
keeping it here leaves the configuration module describing values only.

The bot is a private, owner-only adapter, so these checks are deliberately
stricter than the shared service: an allowlist is required before it will
answer anyone at all.
"""

from __future__ import annotations

from typing import Any


def telegram_startup_problems(cfg: Any) -> list[str]:
    """Return Telegram runtime problems before polling starts."""
    """Return Telegram runtime problems before polling starts."""
    problems: list[str] = []
    if not cfg.ENABLE_TELEGRAM_BOT:
        problems.append("ENABLE_TELEGRAM_BOT must be true to run the Telegram bot.")
    if not cfg.TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN must be set.")
    elif ":" not in cfg.TELEGRAM_BOT_TOKEN or len(cfg.TELEGRAM_BOT_TOKEN) < 30:
        problems.append("TELEGRAM_BOT_TOKEN does not look like a valid Telegram bot token.")

    if cfg.is_production():
        if cfg.TELEGRAM_TEST_MODE:
            problems.append("TELEGRAM_TEST_MODE must be false outside local development.")
        if cfg.ENABLE_FOUNDER_MODE:
            problems.append("ENABLE_FOUNDER_MODE must be false outside local development.")
        if not cfg.TELEGRAM_ALLOWED_USER_IDS:
            problems.append("TELEGRAM_ALLOWED_USER_IDS must be set when Telegram is enabled in production.")
    else:
        if not cfg.TELEGRAM_ALLOWED_USER_IDS and not cfg.TELEGRAM_TEST_MODE:
            problems.append("Set TELEGRAM_ALLOWED_USER_IDS or enable TELEGRAM_TEST_MODE for local testing.")
        if cfg.ENABLE_FOUNDER_MODE and not cfg.TELEGRAM_TEST_MODE:
            problems.append("ENABLE_FOUNDER_MODE requires TELEGRAM_TEST_MODE in local founder testing.")
        if cfg.ENABLE_FOUNDER_MODE and not cfg.FOUNDER_ACCESS_CODE:
            problems.append("FOUNDER_ACCESS_CODE must be set when founder mode is enabled.")
        if not cfg.CONFIDENTIAL_ACCESS_CODE:
            problems.append("CONFIDENTIAL_ACCESS_CODE should be set before using private-entry queries.")
    return problems
