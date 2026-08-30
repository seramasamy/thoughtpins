"""Rules about which configuration combinations may serve real traffic.

Separated from `config.py` so the module that defines settings does not also
carry the policy about how they may be combined. Each function takes the values
it judges rather than reading them, so a caller can ask the question about a
hypothetical configuration — which is what the tests do.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any


def graph_backend_problems(provider: str, shadow_enabled: bool) -> list[str]:
    """Return privacy blockers for auxiliary graph backends."""

    if provider == "internal_sql" and not shadow_enabled:
        return []
    return [
        "External graph backends are evaluation-only until tenant-scoped account deletion is verified; "
        "use GRAPH_PROVIDER=internal_sql and GRAPH_SHADOW_ENABLED=false in production."
    ]


def llm_pricing_problems(models: Iterable[str]) -> list[str]:
    """Refuse to serve on a spend cap that cannot match the provider bill.

    The cap in `usage.py` is only as honest as the price map behind it. An
    unpriced runtime meters at `LLM_DEFAULT_*`, and if the real model costs more,
    spend runs past the cap by that multiple before anything stops it — a
    frontier open model at $3/$15 against the $0.30/$1.20 default overshoots
    tenfold. That is a budget reporting headroom while the balance drains, so it
    is a startup failure rather than a warning.

    Names are normalised first, because the client requests the normalised form
    and metering falls back to it. Pricing the display label "model[variant]"
    while the request sends "model" would validate cleanly and still meter at
    the default.

    This closes the deterministic half only. Usage is recorded against the name
    the provider echoes in its response, falling back to the requested one, and
    an echoed name is not knowable before a call. Where they differ, the runtime
    warning in `usage.py` is the remaining signal.
    """
    from thoughtpins.llm.client import normalize_llm_model_name
    from thoughtpins.usage import is_priced

    unpriced = sorted(
        {
            normalize_llm_model_name(model)
            for model in models
            if model and not is_priced(normalize_llm_model_name(model))
        }
    )
    if not unpriced:
        return []
    return [
        "LLM_PRICING_JSON must carry input_per_1m and output_per_1m for every configured "
        f"runtime; {len(unpriced)} of them are unpriced and would meter at the default rate, "
        "so USAGE_MONTHLY_BUDGET_USD would not match what the provider actually charges."
    ]


def usage_enforcement_problem(enforcement_enabled: bool, tracking_enabled: bool) -> tuple[bool, str]:
    """Enforcement without tracking is enforcement in name only.

    The spend cap reads the usage meter. With tracking off no usage rows are
    written, month-to-date spend is always 0.0, and the pre-call budget check
    can therefore never fire -- so the configuration says enforcement is on
    while one looping account can spend without limit.

    Returned as a (condition, message) pair to match the shape of the checks
    tuple in `Config.validate_startup`.
    """
    return (
        enforcement_enabled and not tracking_enabled,
        "USAGE_ENFORCEMENT_ENABLED requires USAGE_TRACKING_ENABLED: enforcement "
        "reads the usage meter, so with tracking off the spend cap never fires.",
    )


def runtime_production_problems(cfg: Any) -> list[str]:
    """Production runtime checks that flag a message when their condition holds.

    Takes the resolved config object. Lives here, beside the other production
    validators, so `config.py`'s settings class stays within its size budget;
    it reads `cfg.<SETTING>` rather than importing config, so the two modules do
    not form a cycle.
    """
    checks = (
        (cfg.DATABASE_URL.startswith("sqlite"), "DATABASE_URL must use PostgreSQL outside local development."),
        (not cfg.REDIS_URL, "REDIS_URL must be set outside local development."),
        (not cfg.RATE_LIMIT_ENABLED, "RATE_LIMIT_ENABLED must be true outside local development."),
        usage_enforcement_problem(cfg.USAGE_ENFORCEMENT_ENABLED, cfg.USAGE_TRACKING_ENABLED),
        (not cfg.PROCESS_ENTRIES_ASYNC, "PROCESS_ENTRIES_ASYNC must be true outside local development."),
        (
            cfg.INGESTION_QUEUE_BACKEND != "celery",
            "INGESTION_QUEUE_BACKEND must be celery outside local development.",
        ),
        (
            cfg.INGESTION_QUEUE_BACKEND == "celery" and not (cfg.CELERY_BROKER_URL or cfg.REDIS_URL),
            "CELERY_BROKER_URL or REDIS_URL must be set for Celery workers.",
        ),
        (
            not 10 <= cfg.WORKER_RECOVERY_INTERVAL_SECONDS <= 3_600,
            "WORKER_RECOVERY_INTERVAL_SECONDS must be between 10 and 3600.",
        ),
        (not cfg.SENTRY_DSN, "SENTRY_DSN must be set outside local development."),
        (
            cfg.MAGIC_LINK_ENABLED and cfg.EMAIL_PROVIDER == "none",
            "EMAIL_PROVIDER must deliver real mail when MAGIC_LINK_ENABLED is true; "
            "the 'none' provider logs sign-in links instead of sending them.",
        ),
        (
            cfg.MAGIC_LINK_ENABLED and not cfg.EMAIL_FROM_ADDRESS,
            "EMAIL_FROM_ADDRESS must be set when MAGIC_LINK_ENABLED is true.",
        ),
        (
            cfg.MAGIC_LINK_ENABLED and cfg.MAGIC_LINK_TTL_MINUTES > 60,
            "MAGIC_LINK_TTL_MINUTES must be 60 or less; a sign-in link is a bearer credential.",
        ),
        (not cfg.SECURITY_HEADERS_ENABLED, "SECURITY_HEADERS_ENABLED must be true outside local development."),
        (cfg.MAX_REQUEST_BODY_BYTES < 65_536, "MAX_REQUEST_BODY_BYTES must allow normal journal payloads."),
        (cfg.LLM_TIMEOUT_SECONDS < 5, "LLM_TIMEOUT_SECONDS must be at least 5."),
        (cfg.MEMORY_CONTEXT_MODE not in {"smart", "full"}, "MEMORY_CONTEXT_MODE must be smart or full."),
        (cfg.MEMORY_CONTEXT_MAX_CHARS < 20_000, "MEMORY_CONTEXT_MAX_CHARS must be at least 20000."),
        (cfg.TELEGRAM_TEST_MODE, "TELEGRAM_TEST_MODE must be false outside local development."),
        (
            cfg.ARTICLE_ALLOW_RESTRICTED_DOMAINS,
            "ARTICLE_ALLOW_RESTRICTED_DOMAINS must be false outside local development: "
            "publisher access limits apply to any deployment serving other people.",
        ),
        (cfg.ENABLE_FOUNDER_MODE, "ENABLE_FOUNDER_MODE must be false outside local development."),
        (
            cfg.VOICE_ARCHIVE_ENABLED and not cfg.voice_archive_is_durable(),
            "VOICE_ARCHIVE_ENABLED requires durable storage. The archive path resolves inside the "
            "container filesystem, which is discarded on every redeploy — a user who consented to "
            "keeping their recordings would silently lose them. Mount a volume and set "
            "VOICE_ARCHIVE_PATH to it, or set VOICE_ARCHIVE_DURABLE=true if the path is durable "
            "by other means.",
        ),
        (
            cfg.ENABLE_TELEGRAM_BOT and not cfg.TELEGRAM_ALLOWED_USER_IDS,
            "TELEGRAM_ALLOWED_USER_IDS must be set when Telegram is enabled.",
        ),
        # The next entries refuse states nobody chose. Each is legal when the
        # operator sets it explicitly; what boots must never do is arrive there
        # by a default or a side effect, because each one silently changes who
        # can use the service.
        (
            cfg.REQUIRE_EMAIL_VERIFICATION,
            "REQUIRE_EMAIL_VERIFICATION must be false: no code path delivers the "
            "verification token with any EMAIL_PROVIDER, so email/password accounts "
            "could register but never log in. Build delivery before turning this on.",
        ),
        (
            cfg.SYSTEM_LOCKED and "SYSTEM_LOCKED" not in os.environ,
            "SYSTEM_LOCKED is locked by its default, not by choice. Set SYSTEM_LOCKED=false "
            "to open registration, or SYSTEM_LOCKED=true to state that a locked deployment "
            "is intended.",
        ),
        (
            cfg.ENABLE_TELEGRAM_BOT,
            "ENABLE_TELEGRAM_BOT must be false in production. The Telegram bot is a second "
            "client that writes journal data outside the API's consent and audit path, and it "
            "is disabled for v1 (removal is scheduled as a 1.1 refactor; it is not a leaf, so "
            "it cannot be excised safely before launch). Set ENABLE_TELEGRAM_BOT=false and do "
            "not set TELEGRAM_BOT_TOKEN in production.",
        ),
    )
    return [message for failed, message in checks if failed]
