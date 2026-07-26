"""Telegram bot authentication, allowlist, and in-process rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

from loguru import logger

from thoughtpins.config import config
from thoughtpins.privacy import fingerprint_identifier

_RATE_WINDOW = 60
_RATE_LIMIT = 10
_request_counts: dict[int, list[float]] = defaultdict(list)


def _test_user_path() -> Path:
    return config.resolve_path("./data/telegram_test_user.txt")


def _get_test_user_id() -> int | None:
    path = _test_user_path()
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _claim_test_user(user_id: int) -> bool:
    path = _test_user_path()
    existing = _get_test_user_id()
    if existing is not None:
        return existing == user_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(user_id), encoding="utf-8")
    logger.warning("Telegram test mode claimed first user_hash={}", fingerprint_identifier(user_id))
    return True


def is_user_allowed(user_id: int) -> bool:
    """Check whether a Telegram user ID is explicitly allowed."""
    allowed = config.TELEGRAM_ALLOWED_USER_IDS
    if allowed:
        return user_id in allowed

    if config.TELEGRAM_TEST_MODE and not config.is_production():
        return _claim_test_user(user_id)

    if not allowed:
        logger.warning("No TELEGRAM_ALLOWED_USER_IDS configured; Telegram access is blocked")
        return False
    return False


def check_rate_limit(user_id: int) -> bool:
    """Check whether a Telegram user is within local rate limits."""
    now = time.time()
    window_start = now - _RATE_WINDOW
    _request_counts[user_id] = [t for t in _request_counts[user_id] if t > window_start]
    count = len(_request_counts[user_id])
    if count >= _RATE_LIMIT:
        logger.warning(
            "Rate limit hit for user_hash={} ({} requests in {}s)", fingerprint_identifier(user_id), count, _RATE_WINDOW
        )
        return False
    _request_counts[user_id].append(now)
    return True


def check_auth(user_id: int) -> bool:
    """Verify Telegram authorization and rate limit."""
    if not is_user_allowed(user_id):
        logger.warning("Unauthorized Telegram access attempt from user_hash={}", fingerprint_identifier(user_id))
        return False
    if not check_rate_limit(user_id):
        return False
    return True
