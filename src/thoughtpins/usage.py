"""Provider spend metering and per-user budget enforcement.

Rate limiting (:mod:`thoughtpins.rate_limit`) caps how *often* a user can call
the LLM. This module caps how much that usage actually *costs*, which is the
control a free tier needs: one user with a script can stay under any per-minute
limit and still run up an unbounded provider bill.

Token counts come from the provider response, never from an estimate. Costs are
derived from a configurable price map so provider price changes are a config
edit rather than a code change.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from loguru import logger
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import LlmUsageEvent
from thoughtpins.privacy import fingerprint_identifier

_PriceMap = dict[str, dict[str, float]]

_price_map: _PriceMap | None = None
_price_map_lock = Lock()

_redis_client: Any | None = None
_redis_retry_after = 0.0
_redis_lock = Lock()


class UsageBudgetExceeded(RuntimeError):
    """Raised when a metered call would exceed a configured spend budget."""

    def __init__(self, scope: Literal["user", "global"] = "user") -> None:
        self.scope = scope
        if scope == "global":
            message = "Service spend budget reached; new AI processing is paused."
        else:
            message = "Monthly AI usage budget reached for this account."
        super().__init__(message)


# ---------------------------------------------------------------- pricing


def _load_price_map() -> _PriceMap:
    global _price_map
    # Read the global into a local at each check. The second check is the
    # double-checked locking idiom and is genuinely reachable, because another
    # thread can populate the map while this one waits for the lock; reading
    # through a local keeps that visible to type checkers, which otherwise
    # narrow the global to None after the first check and call the second dead.
    cached = _price_map
    if cached is not None:
        return cached
    with _price_map_lock:
        cached = _price_map
        if cached is not None:
            return cached
        parsed: _PriceMap = {}
        try:
            raw = json.loads(config.LLM_PRICING_JSON or "{}")
        except (TypeError, ValueError) as exc:
            logger.warning("LLM_PRICING_JSON is not valid JSON ({}); using default prices only", type(exc).__name__)
            raw = {}
        if isinstance(raw, dict):
            for model, prices in raw.items():
                if not isinstance(prices, dict):
                    continue
                entry: dict[str, float] = {}
                for key in ("input_per_1m", "output_per_1m"):
                    value = prices.get(key)
                    if isinstance(value, (int, float)) and value >= 0:
                        entry[key] = float(value)
                if entry:
                    parsed[str(model)] = entry
        _price_map = parsed
    return parsed


def _price_for(model: str) -> tuple[float, float]:
    """Return (input, output) USD per 1M tokens for a model.

    An unmapped model falls back to the configured default price rather than
    zero, so a newly introduced runtime is never silently billed as free.
    """
    prices = _load_price_map().get(model or "")
    if prices is None:
        return (
            config.LLM_DEFAULT_INPUT_PRICE_PER_1M_USD,
            config.LLM_DEFAULT_OUTPUT_PRICE_PER_1M_USD,
        )
    return (
        prices.get("input_per_1m", config.LLM_DEFAULT_INPUT_PRICE_PER_1M_USD),
        prices.get("output_per_1m", config.LLM_DEFAULT_OUTPUT_PRICE_PER_1M_USD),
    )


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_per_1m, output_per_1m = _price_for(model)
    return (max(0, prompt_tokens) / 1_000_000) * input_per_1m + (max(0, completion_tokens) / 1_000_000) * output_per_1m


# ---------------------------------------------------------------- redis


def _redis():
    """Mirror rate_limit's lazy client so a Redis outage never hard-fails here."""
    global _redis_client, _redis_retry_after
    if not config.REDIS_URL:
        return None
    cached = _redis_client
    if cached is not None:
        return cached
    if time.monotonic() < _redis_retry_after:
        return None
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
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
            logger.warning("Redis client setup failed for usage metering: {}", type(exc).__name__)
    return _redis_client


def _mark_redis_unavailable() -> None:
    global _redis_client, _redis_retry_after
    _redis_client = None
    _redis_retry_after = time.monotonic() + 5.0


def _current_month_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _global_counter_key() -> str:
    return f"thoughtpins:usage:global:{_current_month_key()}"


def _month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1).replace(tzinfo=None)


# ---------------------------------------------------------------- recording


def record_llm_usage(
    *,
    user_id: str | None,
    provider: str,
    model: str,
    operation: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
    request_id: str | None = None,
) -> None:
    """Persist one metered provider call. Never raises into the caller.

    Follows :func:`thoughtpins.audit.record_audit_event`: metering must not be
    able to fail a user's request, so every error here is logged and swallowed.
    """
    if not config.USAGE_TRACKING_ENABLED:
        return
    if not user_id:
        # No attributable tenant (startup probes, health checks). An RLS-scoped
        # row with no owner is not representable, so skip rather than guess.
        logger.debug("Skipping usage record with no tenant: provider={} operation={}", provider, operation)
        return

    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    session: Session | None = None
    try:
        from thoughtpins.store import get_session

        session = get_session()
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_user_id', :user_id, true)"),
                {"user_id": user_id},
            )
        session.add(
            LlmUsageEvent(
                user_id=user_id,
                provider=(provider or "unknown")[:32],
                model=(model or "unknown")[:128],
                operation=(operation or "unknown")[:32],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=cost_usd,
                request_id=str(request_id)[:64] if request_id else None,
            )
        )
        session.commit()
    except Exception as exc:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                logger.debug("Usage rollback failed", exc_info=True)
        logger.warning(
            "Usage record failed provider={} operation={} user_id_hash={}: {}",
            provider,
            operation,
            fingerprint_identifier(user_id),
            type(exc).__name__,
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                logger.debug("Usage session close failed", exc_info=True)

    _increment_global_spend(cost_usd)


def _increment_global_spend(cost_usd: float) -> None:
    """Best-effort platform-wide month counter (micro-USD to stay integral)."""
    client = _redis()
    if client is None or cost_usd <= 0:
        return
    try:
        key = _global_counter_key()
        new_total = client.incrby(key, int(round(cost_usd * 1_000_000)))
        if int(new_total) == int(round(cost_usd * 1_000_000)):
            # First write this month; expire well after the month rolls over so
            # old counters clean themselves up without a scheduled job.
            client.expire(key, 40 * 24 * 3600)
    except Exception as exc:
        _mark_redis_unavailable()
        logger.warning("Global usage counter update failed: {}", type(exc).__name__)


# ---------------------------------------------------------------- reading


def get_user_month_spend_usd(user_id: str, *, session: Session | None = None) -> float:
    """Month-to-date spend for one user.

    Relies on the caller's tenant context for RLS scoping, so this never needs a
    privileged cross-tenant read.
    """
    owned_session = False
    if session is None:
        from thoughtpins.store import get_session

        session = get_session()
        owned_session = True
    try:
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_user_id', :user_id, true)"),
                {"user_id": user_id},
            )
        total = (
            session.query(func.coalesce(func.sum(LlmUsageEvent.cost_usd), 0.0))
            .filter(
                LlmUsageEvent.user_id == user_id,
                LlmUsageEvent.created_at_utc >= _month_start_utc(),
            )
            .scalar()
        )
        return float(total or 0.0)
    finally:
        if owned_session:
            try:
                session.close()
            except Exception:
                logger.debug("Usage read session close failed", exc_info=True)


def get_platform_month_spend_usd() -> float | None:
    """Platform-wide month spend, or None when the counter is unavailable."""
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(_global_counter_key())
        return float(int(raw)) / 1_000_000 if raw is not None else 0.0
    except Exception as exc:
        _mark_redis_unavailable()
        logger.warning("Global usage counter read failed: {}", type(exc).__name__)
        return None


# ---------------------------------------------------------------- enforcement


def ensure_budget_available(user_id: str | None, *, is_admin: bool = False) -> None:
    """Raise :class:`UsageBudgetExceeded` when a metered call must not proceed."""
    if not config.USAGE_ENFORCEMENT_ENABLED or not user_id:
        return
    if is_admin and config.USAGE_BUDGET_EXEMPT_ADMINS:
        return

    global_budget = config.USAGE_GLOBAL_MONTHLY_BUDGET_USD
    if global_budget > 0:
        platform_spend = get_platform_month_spend_usd()
        # None means the counter is unreadable; the per-user cap below is the
        # primary control, so degrade to it rather than blocking all traffic.
        if platform_spend is not None and platform_spend >= global_budget:
            logger.error(
                "Platform monthly spend budget reached: {:.4f} >= {:.2f} USD",
                platform_spend,
                global_budget,
            )
            raise UsageBudgetExceeded("global")

    user_budget = config.USAGE_MONTHLY_BUDGET_USD
    if user_budget <= 0:
        return
    spend = get_user_month_spend_usd(user_id)
    if spend >= user_budget:
        logger.info(
            "User monthly budget reached user_id_hash={} spend={:.4f} budget={:.2f}",
            fingerprint_identifier(user_id),
            spend,
            user_budget,
        )
        raise UsageBudgetExceeded("user")
    warn_ratio = config.USAGE_BUDGET_WARN_RATIO
    if 0 < warn_ratio < 1 and spend >= user_budget * warn_ratio:
        logger.info(
            "User approaching monthly budget user_id_hash={} spend={:.4f} budget={:.2f}",
            fingerprint_identifier(user_id),
            spend,
            user_budget,
        )


# ---------------------------------------------------------------- reporting


def get_all_users_month_spend(session: Session) -> list[dict[str, Any]]:
    """Per-user month-to-date spend, newest-spend first.

    Iterates tenants explicitly instead of issuing one cross-tenant aggregate:
    the per-user query stays RLS-correct with no elevated database role, and a
    solo-operator install has few enough users for this to be trivially fast.
    """
    from thoughtpins.db import User
    from thoughtpins.tenancy import tenant_context

    rows: list[dict[str, Any]] = []
    users = session.query(User.id, User.email, User.is_admin).filter(User.deleted_at_utc.is_(None)).all()
    for user_id, email, is_admin in users:
        with tenant_context(user_id):
            spend = get_user_month_spend_usd(user_id, session=session)
        if spend <= 0:
            continue
        rows.append(
            {
                "user_id": user_id,
                "email": email,
                "is_admin": bool(is_admin),
                "month_spend_usd": round(spend, 6),
                "budget_usd": config.USAGE_MONTHLY_BUDGET_USD,
                "over_budget": spend >= config.USAGE_MONTHLY_BUDGET_USD > 0,
            }
        )
    rows.sort(key=lambda row: row["month_spend_usd"], reverse=True)
    return rows


def build_usage_report(session: Session) -> dict[str, Any]:
    users = get_all_users_month_spend(session)
    return {
        "month": _current_month_key(),
        "tracking_enabled": config.USAGE_TRACKING_ENABLED,
        "enforcement_enabled": config.USAGE_ENFORCEMENT_ENABLED,
        "per_user_budget_usd": config.USAGE_MONTHLY_BUDGET_USD,
        "global_budget_usd": config.USAGE_GLOBAL_MONTHLY_BUDGET_USD,
        "platform_spend_usd": get_platform_month_spend_usd(),
        "users_with_spend": len(users),
        "users": users,
    }
