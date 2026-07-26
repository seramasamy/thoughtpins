"""Redis-backed rate limiting with local in-memory fallback."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from loguru import logger

from thoughtpins.config import config

_memory_hits: dict[str, list[float]] = defaultdict(list)
_redis_client: Any | None = None
_redis_retry_after = 0.0
_redis_lock = Lock()


class RateLimitBackendUnavailable(RuntimeError):
    """Raised when production traffic controls cannot be enforced globally."""


def _current_redis_client() -> Any | None:
    # Read through a function because another request thread may populate the
    # cache while this caller waits on `_redis_lock`.
    return _redis_client


def _redis():
    global _redis_client, _redis_retry_after
    if not config.REDIS_URL:
        return None
    cached = _current_redis_client()
    if cached is not None:
        return cached
    if time.monotonic() < _redis_retry_after:
        return None
    with _redis_lock:
        cached = _current_redis_client()
        if cached is not None:
            return cached
        if time.monotonic() < _redis_retry_after:
            return None
        try:
            from redis import Redis

            _redis_client = Redis.from_url(
                config.REDIS_URL,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
        except Exception as exc:
            _redis_retry_after = time.monotonic() + 5.0
            logger.warning("Redis client setup failed for rate limiting: {}", type(exc).__name__)
    return _redis_client


def _mark_redis_unavailable() -> None:
    global _redis_client, _redis_retry_after
    client = _redis_client
    _redis_client = None
    _redis_retry_after = time.monotonic() + 5.0
    close = getattr(client, "close", None)
    if close:
        try:
            close()
        except Exception:
            logger.debug("Redis rate-limit client close failed", exc_info=True)


def _require_distributed_backend() -> None:
    if config.is_production():
        raise RateLimitBackendUnavailable("Distributed rate limiting is temporarily unavailable")


def check_rate_limit(key: str, *, limit: int | None = None, window_seconds: int = 60) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds)."""
    if not config.RATE_LIMIT_ENABLED:
        return True, 0

    limit = limit or config.RATE_LIMIT_PER_MINUTE
    redis_client = _redis()
    bucket = f"thoughtpins:rl:{key}:{int(time.time() // window_seconds)}"

    if redis_client:
        try:
            count = int(redis_client.incr(bucket))
            if count == 1:
                redis_client.expire(bucket, window_seconds + 5)
            if count > limit:
                return False, window_seconds - int(time.time() % window_seconds)
            return True, 0
        except Exception as e:
            _mark_redis_unavailable()
            logger.warning("Redis rate limit check failed: {}", type(e).__name__)
            _require_distributed_backend()
    elif config.REDIS_URL or config.is_production():
        _require_distributed_backend()

    now = time.time()
    window_start = now - window_seconds
    hits = [hit for hit in _memory_hits[key] if hit > window_start]
    if len(hits) >= limit:
        _memory_hits[key] = hits
        retry_after = max(1, int(window_seconds - (now - hits[0])))
        return False, retry_after
    hits.append(now)
    _memory_hits[key] = hits
    return True, 0
