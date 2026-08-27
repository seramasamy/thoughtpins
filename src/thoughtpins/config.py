"""Application configuration loaded from environment and optional .env file."""

from __future__ import annotations

import importlib.util
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from thoughtpins.config_admission import read_admission_defaults
from thoughtpins.config_urls import is_shell_mangled_path, public_client_url  # noqa: F401
from thoughtpins.config_validation import graph_backend_problems, llm_pricing_problems

load_dotenv()

# Re-exported: tests and a few modules import these from thoughtpins.config.
from thoughtpins.config_env import (  # noqa: F401
    _env,
    _env_any,
    _env_bool,
    _env_float,
    _env_int,
    _env_int_list,
    _env_str_list,
)

# Read once, here, so a config reload re-reads the environment the same way
# every other setting does.
_ADMISSION = read_admission_defaults(_env_bool)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Re-exported: validation policy lives in config_validation, but callers and
# tests have always reached it through this module.
__all__ = [
    "Config",
    "config",
    "graph_backend_problems",
    "is_shell_mangled_path",
    "llm_pricing_problems",
    "public_client_url",
]


def _llm_provider() -> str:
    explicit = _env("LLM_PROVIDER")
    if explicit:
        return explicit.lower()
    base_url = _llm_base_url().lower()
    if "api.openai.com" in base_url:
        return "openai"
    return "openai_compatible"


def _llm_api_key() -> str:
    return _env_any(("LLM_API_KEY", "ANTHROPIC_AUTH_TOKEN"))


def _llm_base_url() -> str:
    explicit = _env("LLM_BASE_URL")
    if explicit:
        return explicit
    compatibility_base = _env("ANTHROPIC_BASE_URL")
    if compatibility_base:
        return compatibility_base.rstrip("/").removesuffix("/anthropic")
    return "https://api.openai.com/v1"


def _llm_model() -> str:
    return _env_any(("LLM_MODEL", "ANTHROPIC_MODEL"), "chat-model")


def _is_public_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.hostname
        not in {
            "localhost",
            "127.0.0.1",
            str(ipaddress.IPv4Address(0)),
        }
    )


class Config:
    APP_NAME: str = _env("APP_NAME", "Thought Pins")
    ENVIRONMENT: str = _env("ENVIRONMENT", "development").lower()
    API_VERSION: str = _env("API_VERSION", "1.0.0-rc.1")
    PRIVACY_POLICY_URL: str = _env("PRIVACY_POLICY_URL")
    TERMS_URL: str = _env("TERMS_URL")
    SUPPORT_URL: str = _env("SUPPORT_URL")
    ACCOUNT_DELETION_URL: str = _env("ACCOUNT_DELETION_URL")
    AI_DISCLOSURE_URL: str = _env("AI_DISCLOSURE_URL")
    LEGAL_DOCUMENT_VERSION: str = _env("LEGAL_DOCUMENT_VERSION", "2026-07-13")
    MIN_IOS_VERSION: str = _env("MIN_IOS_VERSION", "0.0.0")
    MIN_ANDROID_VERSION: str = _env("MIN_ANDROID_VERSION", "0.0.0")
    MIN_WEB_VERSION: str = _env("MIN_WEB_VERSION", "0.0.0")
    RECOMMENDED_IOS_VERSION: str = _env("RECOMMENDED_IOS_VERSION", API_VERSION)
    RECOMMENDED_ANDROID_VERSION: str = _env("RECOMMENDED_ANDROID_VERSION", API_VERSION)
    RECOMMENDED_WEB_VERSION: str = _env("RECOMMENDED_WEB_VERSION", API_VERSION)
    IOS_STORE_URL: str = _env("IOS_STORE_URL")
    ANDROID_STORE_URL: str = _env("ANDROID_STORE_URL")
    WEB_APP_URL: str = _env("WEB_APP_URL", "/app")
    MAINTENANCE_MODE: bool = _env_bool("MAINTENANCE_MODE", False)
    MAINTENANCE_MESSAGE: str = _env(
        "MAINTENANCE_MESSAGE",
        "Thought Pins is in maintenance for a short upgrade. Please try again soon.",
    )
    MAINTENANCE_RETRY_AFTER_SECONDS: int = _env_int("MAINTENANCE_RETRY_AFTER_SECONDS", 300)
    MAINTENANCE_ALLOW_READS: bool = _env_bool("MAINTENANCE_ALLOW_READS", True)

    LLM_PROVIDER: str = _llm_provider()
    LLM_API_KEY: str = _llm_api_key()
    LLM_BASE_URL: str = _llm_base_url()
    LLM_MODEL: str = _llm_model()
    LLM_FALLBACK_MODEL: str = _env("LLM_FALLBACK_MODEL", LLM_MODEL)
    LLM_EXTRACTION_MODEL_NAME: str = _env("LLM_EXTRACTION_MODEL", LLM_FALLBACK_MODEL)
    LLM_EXTRACTION_MODEL: str = LLM_EXTRACTION_MODEL_NAME
    LLM_THINKING: str = _env("LLM_THINKING", "disabled")
    LLM_SUPPORTS_THINKING: bool = _env_bool("LLM_SUPPORTS_THINKING", False)
    LLM_REASONING_EFFORT: str = _env("LLM_REASONING_EFFORT", "high")
    OPENAI_API_KEY: str = _env("OPENAI_API_KEY")
    OPENAI_BASE_URL: str = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_EMBEDDING_MODEL: str = _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    OPENAI_EMBEDDING_DIMENSIONS: int = _env_int("OPENAI_EMBEDDING_DIMENSIONS", 1536)
    TRANSCRIPTION_PROVIDER: str = _env("TRANSCRIPTION_PROVIDER", "local").lower()
    TRANSCRIPTION_API_KEY: str = _env("TRANSCRIPTION_API_KEY")
    TRANSCRIPTION_BASE_URL: str = _env("TRANSCRIPTION_BASE_URL", "https://api.openai.com/v1")
    TRANSCRIPTION_MODEL: str = _env("TRANSCRIPTION_MODEL", "whisper-1")
    TRANSCRIPTION_LOCAL_MODEL: str = _env("TRANSCRIPTION_LOCAL_MODEL", "base")
    TRANSCRIPTION_TIMEOUT_SECONDS: int = _env_int("TRANSCRIPTION_TIMEOUT_SECONDS", 120)
    LLM_TIMEOUT_SECONDS: int = _env_int("LLM_TIMEOUT_SECONDS", 180)
    LLM_MAX_RETRIES: int = _env_int("LLM_MAX_RETRIES", 2)
    LLM_EMPTY_RESPONSE_RETRIES: int = _env_int("LLM_EMPTY_RESPONSE_RETRIES", 3)
    LLM_EXTRACTION_MAX_TOKENS: int = _env_int("LLM_EXTRACTION_MAX_TOKENS", 6144)
    LLM_HEALTHCHECK_LIVE: bool = _env_bool("LLM_HEALTHCHECK_LIVE", False)
    MEMORY_CONTEXT_MODE: str = _env("MEMORY_CONTEXT_MODE", "smart").lower()
    MEMORY_CONTEXT_MAX_CHARS: int = _env_int("MEMORY_CONTEXT_MAX_CHARS", 850_000)
    MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS: int = _env_int("MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 180_000)
    MEMORY_CONTEXT_RELEVANT_MEMORIES: int = _env_int("MEMORY_CONTEXT_RELEVANT_MEMORIES", 80)
    MEMORY_CONTEXT_RECENT_MEMORIES: int = _env_int("MEMORY_CONTEXT_RECENT_MEMORIES", 60)
    MEMORY_CONTEXT_RECENT_ENTRIES: int = _env_int("MEMORY_CONTEXT_RECENT_ENTRIES", 25)
    ARTICLE_FETCH_PROVIDERS: list[str] = [
        provider.strip().lower() for provider in _env("ARTICLE_FETCH_PROVIDERS", "local").split(",") if provider.strip()
    ]
    ARTICLE_ALLOW_PRIVATE_URLS: bool = _env_bool("ARTICLE_ALLOW_PRIVATE_URLS", False)
    ARTICLE_FETCH_TIMEOUT_SECONDS: int = _env_int("ARTICLE_FETCH_TIMEOUT_SECONDS", 20)
    ARTICLE_MAX_FETCH_BYTES: int = _env_int("ARTICLE_MAX_FETCH_BYTES", 3_000_000)
    ARTICLE_MIN_TEXT_CHARS: int = _env_int("ARTICLE_MIN_TEXT_CHARS", 500)
    ARTICLE_USER_AGENT: str = _env("ARTICLE_USER_AGENT", "ThoughtPins/0.2 local memory reader")
    # Personal offline builds only. Lets retrieval reach publishers the hosted
    # service refuses, for an operator reading material they subscribe to.
    # validate_startup rejects this outside local development, so the public
    # service cannot enable it by configuration or by accident.
    ARTICLE_ALLOW_RESTRICTED_DOMAINS: bool = _env_bool("ARTICLE_ALLOW_RESTRICTED_DOMAINS", False)
    ARTICLE_RESTRICTED_DOMAINS: list[str] = [
        domain.strip().lower()
        for domain in _env(
            "ARTICLE_RESTRICTED_DOMAINS",
            "wsj.com,bloomberg.com,economist.com,ft.com,nytimes.com,"
            "washingtonpost.com,theatlantic.com,newyorker.com,barrons.com,"
            "marketwatch.com,foreignaffairs.com,technologyreview.com,statnews.com,"
            "scientificamerican.com",
        ).split(",")
        if domain.strip()
    ]
    OPEN_ACCESS_RESOLUTION_ENABLED: bool = _env_bool("OPEN_ACCESS_RESOLUTION_ENABLED", True)
    OPEN_ACCESS_CONTACT_EMAIL: str = _env("OPEN_ACCESS_CONTACT_EMAIL", "support@thoughtpins.com")
    OPEN_ACCESS_BASE_URL: str = _env("OPEN_ACCESS_BASE_URL", "https://api.unpaywall.org/v2")
    OPEN_ACCESS_TIMEOUT_SECONDS: int = _env_int("OPEN_ACCESS_TIMEOUT_SECONDS", 12)
    JINA_API_KEY: str = _env("JINA_API_KEY")
    FIRECRAWL_API_KEY: str = _env("FIRECRAWL_API_KEY")
    FIRECRAWL_BASE_URL: str = _env("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v2")
    APIFY_API_TOKEN: str = _env("APIFY_API_TOKEN")
    APIFY_BASE_URL: str = _env("APIFY_BASE_URL", "https://api.apify.com/v2")
    APIFY_READER_ACTOR: str = _env("APIFY_READER_ACTOR")
    APIFY_READER_INPUT_TEMPLATE: str = _env("APIFY_READER_INPUT_TEMPLATE")
    # A saved article that is not put through extraction becomes an island: it
    # exports as a note with no links to the people, places, and topics it shares
    # with the journal. Extraction is one more LLM call per saved source, which
    # the usage budget already meters, and it is what makes the library and the
    # journal one graph rather than two piles.
    LIBRARY_EXTRACT_GRAPH: bool = _env_bool("LIBRARY_EXTRACT_GRAPH", True)
    LIBRARY_GRAPH_EXTRACT_MAX_CHARS: int = _env_int("LIBRARY_GRAPH_EXTRACT_MAX_CHARS", 12_000)
    # Deliberately far below ARTICLE_MIN_TEXT_CHARS. That threshold decides
    # whether a *fetched page* looks like a real article; this one decides
    # whether saved text is worth extracting from at all. A one-line note about
    # a person still names that person.
    LIBRARY_GRAPH_MIN_TEXT_CHARS: int = _env_int("LIBRARY_GRAPH_MIN_TEXT_CHARS", 80)
    MEMORY_HYBRID_KEYWORD_CANDIDATES: int = _env_int("MEMORY_HYBRID_KEYWORD_CANDIDATES", 3000)
    MEMORY_HYBRID_GRAPH_HOPS: int = _env_int("MEMORY_HYBRID_GRAPH_HOPS", 1)
    MEMORY_HYBRID_GRAPH_RESULTS: int = _env_int("MEMORY_HYBRID_GRAPH_RESULTS", 25)
    GRAPH_PROVIDER: str = _env("GRAPH_PROVIDER", "internal_sql").lower()
    GRAPH_SHADOW_ENABLED: bool = _env_bool("GRAPH_SHADOW_ENABLED", False)
    GRAPHITI_DRIVER: str = _env("GRAPHITI_DRIVER", "kuzu").lower()
    GRAPHITI_KUZU_PATH: str = _env("GRAPHITI_KUZU_PATH", "./data/graphiti.kuzu")
    GRAPHITI_NEO4J_URI: str = _env("GRAPHITI_NEO4J_URI")
    GRAPHITI_NEO4J_USER: str = _env("GRAPHITI_NEO4J_USER")
    GRAPHITI_NEO4J_PASSWORD: str = _env("GRAPHITI_NEO4J_PASSWORD")
    GRAPHITI_FALKOR_HOST: str = _env("GRAPHITI_FALKOR_HOST", "localhost")
    GRAPHITI_FALKOR_PORT: int = _env_int("GRAPHITI_FALKOR_PORT", 6379)
    GRAPHITI_FALKOR_USERNAME: str = _env("GRAPHITI_FALKOR_USERNAME")
    GRAPHITI_FALKOR_PASSWORD: str = _env("GRAPHITI_FALKOR_PASSWORD")
    GRAPHITI_FALKOR_DATABASE: str = _env("GRAPHITI_FALKOR_DATABASE", "thoughtpins")
    GRAPHITI_TELEMETRY_ENABLED: bool = _env_bool("GRAPHITI_TELEMETRY_ENABLED", False)

    API_KEY: str = _env_any(("API_KEY", "THOUGHTPINS_API_KEY"))
    ALLOW_USER_API_KEYS: bool = _env_bool("ALLOW_USER_API_KEYS", ENVIRONMENT not in {"staging", "production"})
    RETURN_API_KEY_ON_REGISTER: bool = _env_bool(
        "RETURN_API_KEY_ON_REGISTER", ENVIRONMENT not in {"staging", "production"}
    )
    JWT_SECRET: str = _env("JWT_SECRET")
    JWT_ALGORITHM: str = _env("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = _env_int("REFRESH_TOKEN_EXPIRE_DAYS", 30)
    GOOGLE_OAUTH_CLIENT_IDS: list[str] = _env_str_list("GOOGLE_OAUTH_CLIENT_IDS")
    APPLE_OAUTH_CLIENT_IDS: list[str] = _env_str_list("APPLE_OAUTH_CLIENT_IDS")
    APPLE_OAUTH_TEAM_ID: str = _env("APPLE_OAUTH_TEAM_ID")
    APPLE_OAUTH_KEY_ID: str = _env("APPLE_OAUTH_KEY_ID")
    APPLE_OAUTH_PRIVATE_KEY: str = _env("APPLE_OAUTH_PRIVATE_KEY")
    APPLE_OAUTH_PRIVATE_KEY_PATH: str = _env("APPLE_OAUTH_PRIVATE_KEY_PATH")
    APPLE_OAUTH_REDIRECT_URIS: list[str] = _env_str_list("APPLE_OAUTH_REDIRECT_URIS")
    APPLE_OAUTH_TIMEOUT_SECONDS: int = _env_int("APPLE_OAUTH_TIMEOUT_SECONDS", 10)
    ALLOW_OAUTH_REGISTRATION: bool = _env_bool("ALLOW_OAUTH_REGISTRATION", False)
    REQUIRE_EMAIL_VERIFICATION: bool = _env_bool("REQUIRE_EMAIL_VERIFICATION", False)

    # Transactional email. "none" keeps delivery disabled and logs instead, so
    # local development never sends real mail.
    EMAIL_PROVIDER: str = _env("EMAIL_PROVIDER", "none").lower()
    RESEND_API_KEY: str = _env("RESEND_API_KEY")
    RESEND_BASE_URL: str = _env("RESEND_BASE_URL", "https://api.resend.com")
    EMAIL_FROM_ADDRESS: str = _env("EMAIL_FROM_ADDRESS")
    EMAIL_TIMEOUT_SECONDS: int = _env_int("EMAIL_TIMEOUT_SECONDS", 10)

    # Passwordless sign-in. Short TTL because the link is a bearer credential
    # sitting in an inbox.
    MAGIC_LINK_ENABLED: bool = _env_bool("MAGIC_LINK_ENABLED", False)
    MAGIC_LINK_TTL_MINUTES: int = _env_int("MAGIC_LINK_TTL_MINUTES", 15)
    MAGIC_LINK_REQUESTS_PER_HOUR: int = _env_int("MAGIC_LINK_REQUESTS_PER_HOUR", 5)
    MAGIC_LINK_ALLOW_REGISTRATION: bool = _env_bool("MAGIC_LINK_ALLOW_REGISTRATION", True)
    MAGIC_LINK_BASE_URL: str = _env("MAGIC_LINK_BASE_URL")
    EMAIL_VERIFICATION_TOKEN_TTL_HOURS: int = _env_int("EMAIL_VERIFICATION_TOKEN_TTL_HOURS", 24)

    # Admission. The rationale, and why each default points the way it does,
    # lives in config_admission.py next to the values.
    INVITE_ONLY: bool = _ADMISSION.invite_only
    ALLOW_INVITE_ONLY_LAUNCH: bool = _ADMISSION.allow_invite_only_launch
    INVITE_REQUEST_EMAIL: str = _env("INVITE_REQUEST_EMAIL", "invite@thoughtpins.com")
    # Where invite digests go. Left empty, requests still queue and are readable
    # from the admin route and the CLI; nothing is emailed anywhere.
    INVITE_NOTIFY_EMAIL: str = _env("INVITE_NOTIFY_EMAIL")
    # Two independent ceilings on how often the operator is written to. Neither
    # depends on how many requests arrive, so a flood of requests cannot become
    # a flood of mail.
    INVITE_DIGEST_MIN_INTERVAL_MINUTES: int = _env_int("INVITE_DIGEST_MIN_INTERVAL_MINUTES", 720)
    INVITE_DIGEST_MAX_PER_DAY: int = _env_int("INVITE_DIGEST_MAX_PER_DAY", 2)
    # Prefixes operator notifications so they can be filtered on arrival.
    EMAIL_SUBJECT_PREFIX: str = _env("EMAIL_SUBJECT_PREFIX", "[THOUGHTPINS]")
    REQUIRE_API_AUTH: bool = _env_bool(
        "REQUIRE_API_AUTH",
        ENVIRONMENT in {"staging", "production"},
    )
    RATE_LIMIT_ENABLED: bool = _env_bool("RATE_LIMIT_ENABLED", ENVIRONMENT in {"staging", "production"})
    RATE_LIMIT_PER_MINUTE: int = _env_int("RATE_LIMIT_PER_MINUTE", 120)
    RATE_LIMIT_BURST: int = _env_int("RATE_LIMIT_BURST", 240)
    RATE_LIMIT_AUTH_PER_MINUTE: int = _env_int("RATE_LIMIT_AUTH_PER_MINUTE", 5)
    RATE_LIMIT_INGEST_PER_MINUTE: int = _env_int("RATE_LIMIT_INGEST_PER_MINUTE", 30)
    RATE_LIMIT_LLM_PER_MINUTE: int = _env_int("RATE_LIMIT_LLM_PER_MINUTE", 20)
    RATE_LIMIT_EXPORT_PER_MINUTE: int = _env_int("RATE_LIMIT_EXPORT_PER_MINUTE", 10)
    RATE_LIMIT_ACCOUNT_PER_MINUTE: int = _env_int("RATE_LIMIT_ACCOUNT_PER_MINUTE", 30)

    # Provider spend metering. Rate limits cap request *frequency*; these cap
    # actual token *cost*, which is what a free tier can otherwise leak without
    # bound. Tracking and enforcement are separate flags so a deployment can
    # observe real per-user spend before committing to a budget number.
    USAGE_TRACKING_ENABLED: bool = _env_bool("USAGE_TRACKING_ENABLED", True)
    USAGE_ENFORCEMENT_ENABLED: bool = _env_bool("USAGE_ENFORCEMENT_ENABLED", ENVIRONMENT in {"staging", "production"})
    USAGE_MONTHLY_BUDGET_USD: float = _env_float("USAGE_MONTHLY_BUDGET_USD", 3.00)
    USAGE_BUDGET_WARN_RATIO: float = _env_float("USAGE_BUDGET_WARN_RATIO", 0.8)
    USAGE_GLOBAL_MONTHLY_BUDGET_USD: float = _env_float("USAGE_GLOBAL_MONTHLY_BUDGET_USD", 50.00)
    USAGE_BUDGET_EXEMPT_ADMINS: bool = _env_bool("USAGE_BUDGET_EXEMPT_ADMINS", True)
    # Per-model USD prices per 1M tokens, as {"model-id": {"input_per_1m": x,
    # "output_per_1m": y}}. Deliberately empty by default and supplied per
    # deployment: prices are provider-specific and change over time, and this
    # source stays provider-neutral. Models absent from the map bill at the
    # conservative defaults below, so an unmapped runtime is never free.
    LLM_PRICING_JSON: str = _env("LLM_PRICING_JSON", "{}")
    LLM_DEFAULT_INPUT_PRICE_PER_1M_USD: float = _env_float("LLM_DEFAULT_INPUT_PRICE_PER_1M_USD", 0.30)
    LLM_DEFAULT_OUTPUT_PRICE_PER_1M_USD: float = _env_float("LLM_DEFAULT_OUTPUT_PRICE_PER_1M_USD", 1.20)

    PROCESS_ENTRIES_ASYNC: bool = _env_bool("PROCESS_ENTRIES_ASYNC", ENVIRONMENT in {"staging", "production"})
    INGESTION_WORKER_THREADS: int = _env_int("INGESTION_WORKER_THREADS", 2)
    INGESTION_STALE_AFTER_MINUTES: int = _env_int("INGESTION_STALE_AFTER_MINUTES", 30)
    INGESTION_QUEUE_BACKEND: str = _env("INGESTION_QUEUE_BACKEND", "thread").lower()
    INGESTION_MAX_RETRIES: int = _env_int("INGESTION_MAX_RETRIES", 3)
    DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS: int = _env_int("DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS", 10)
    CELERY_BROKER_URL: str = _env("CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = _env("CELERY_RESULT_BACKEND")
    CELERY_WORKER_CONCURRENCY: int = _env_int("CELERY_WORKER_CONCURRENCY", 2)
    CELERY_QUEUE_NAME: str = _env("CELERY_QUEUE_NAME", "celery")
    WORKER_HEARTBEAT_TTL_SECONDS: int = _env_int("WORKER_HEARTBEAT_TTL_SECONDS", 120)
    WORKER_RECOVERY_INTERVAL_SECONDS: int = _env_int("WORKER_RECOVERY_INTERVAL_SECONDS", 60)
    METRICS_REQUIRE_AUTH: bool = _env_bool("METRICS_REQUIRE_AUTH", ENVIRONMENT in {"staging", "production"})

    TELEGRAM_BOT_TOKEN: str = _env("TELEGRAM_BOT_TOKEN")
    TELEGRAM_ALLOWED_USER_IDS: list[int] = _env_int_list("TELEGRAM_ALLOWED_USER_IDS")
    ENABLE_TELEGRAM_BOT: bool = _env_bool("ENABLE_TELEGRAM_BOT", bool(TELEGRAM_BOT_TOKEN))
    TELEGRAM_TEST_MODE: bool = _env_bool("TELEGRAM_TEST_MODE", False)
    TELEGRAM_REMINDER_POLL_SECONDS: int = _env_int("TELEGRAM_REMINDER_POLL_SECONDS", 300)
    DEFAULT_TELEGRAM_CHAT_ID: str = _env("DEFAULT_TELEGRAM_CHAT_ID")
    DEFAULT_ADMIN_EMAIL: str = _env("DEFAULT_ADMIN_EMAIL")
    DEFAULT_DISPLAY_NAME: str = _env("DEFAULT_DISPLAY_NAME", "Local Admin")
    ENABLE_FOUNDER_MODE: bool = _env_bool("ENABLE_FOUNDER_MODE", TELEGRAM_TEST_MODE)
    FOUNDER_ACCESS_CODE: str = _env("FOUNDER_ACCESS_CODE")
    CONFIDENTIAL_ACCESS_CODE: str = _env("CONFIDENTIAL_ACCESS_CODE")

    LOCAL_TIMEZONE: str = _env("LOCAL_TIMEZONE", "America/New_York")
    VAULT_NAME: str = _env("VAULT_NAME", "ThoughtPinsVault")
    VAULT_PATH: Path = Path(_env("VAULT_PATH", "./vault"))
    VAULT_IMPORT_PATH: Path = Path(_env("VAULT_IMPORT_PATH", "./data/vault_imports"))
    VAULT_IMPORT_SESSION_HOURS: int = _env_int("VAULT_IMPORT_SESSION_HOURS", 24)
    VAULT_UPLOAD_CHUNK_BYTES: int = _env_int("VAULT_UPLOAD_CHUNK_BYTES", 524_288)
    CONVERSATION_CACHE_PATH: Path = Path(_env("CONVERSATION_CACHE_PATH", "./data/conversation_cache.json"))
    # Retaining a recording is a promise. The archive writes to a filesystem
    # path, and on a container host that path is discarded on every redeploy —
    # so an operator who enables retention without a mounted volume takes the
    # consent and loses the audio. validate_startup refuses that combination
    # rather than letting it fail quietly months later.
    VOICE_ARCHIVE_ENABLED: bool = _env_bool("VOICE_ARCHIVE_ENABLED", False)
    VOICE_ARCHIVE_PATH: Path = Path(_env("VOICE_ARCHIVE_PATH", "./data/voice_archive"))
    # Escape hatch for durable storage this check cannot recognise, such as an
    # NFS mount or a host bind outside a platform's volume convention.
    VOICE_ARCHIVE_DURABLE: bool = _env_bool("VOICE_ARCHIVE_DURABLE", False)
    DATABASE_URL: str = _env("DATABASE_URL", "sqlite:///./data/thoughtpins.sqlite3")
    DB_POOL_SIZE: int = _env_int("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW: int = _env_int("DB_MAX_OVERFLOW", 10)
    DB_POOL_RECYCLE_SECONDS: int = _env_int("DB_POOL_RECYCLE_SECONDS", 1800)
    AUTO_CREATE_TABLES: bool = _env_bool(
        "AUTO_CREATE_TABLES",
        ENVIRONMENT not in {"staging", "production"},
    )
    RUN_STARTUP_RECOVERY: bool = _env_bool(
        "RUN_STARTUP_RECOVERY",
        ENVIRONMENT not in {"staging", "production"},
    )
    SECURITY_HEADERS_ENABLED: bool = _env_bool("SECURITY_HEADERS_ENABLED", True)
    MAX_REQUEST_BODY_BYTES: int = _env_int("MAX_REQUEST_BODY_BYTES", 1_048_576)
    IDEMPOTENCY_TTL_HOURS: int = _env_int("IDEMPOTENCY_TTL_HOURS", 24)
    IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS: int = _env_int(
        "IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS",
        600,
    )
    IDEMPOTENCY_MAX_RESPONSE_BYTES: int = _env_int("IDEMPOTENCY_MAX_RESPONSE_BYTES", 1_048_576)

    REDIS_URL: str = _env("REDIS_URL")
    SENTRY_DSN: str = _env("SENTRY_DSN")
    JSON_LOGS: bool = _env_bool("JSON_LOGS", ENVIRONMENT in {"staging", "production"})
    CORS_ALLOW_ORIGINS: list[str] = [
        origin.strip() for origin in _env("CORS_ALLOW_ORIGINS").split(",") if origin.strip()
    ]

    VECTOR_MODE: str = _env("VECTOR_MODE", "qdrant_local")
    QDRANT_PATH: str = _env("QDRANT_PATH", "./data/qdrant")
    QDRANT_URL: str = _env("QDRANT_URL")
    QDRANT_API_KEY: str = _env("QDRANT_API_KEY")
    QDRANT_TIMEOUT_SECONDS: int = _env_int("QDRANT_TIMEOUT_SECONDS", 10)
    EMBEDDING_PROVIDER: str = _env("EMBEDDING_PROVIDER", "llm")
    VECTOR_HEALTHCHECK_LIVE: bool = _env_bool("VECTOR_HEALTHCHECK_LIVE", False)
    PRIVATE_ALLOW_LLM: bool = _env_bool("PRIVATE_ALLOW_LLM", False)
    DATA_ENCRYPTION_KEY: str = _env("DATA_ENCRYPTION_KEY")
    REPORTS_PATH: Path = Path(_env("REPORTS_PATH", "./reports"))
    BACKUPS_PATH: Path = Path(_env("BACKUPS_PATH", "./backups"))
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
    API_HOST: str = _env("API_HOST", "127.0.0.1")
    API_PORT: int = _env_int("API_PORT", 8420)
    SYSTEM_LOCKED: bool = _ADMISSION.system_locked

    @classmethod
    def is_production(cls) -> bool:
        return cls.ENVIRONMENT in {"staging", "production"}

    @classmethod
    def is_shared_deployment(cls) -> bool:
        """Whether this instance serves anyone other than its operator.

        Distinct from is_production only in intent: retrieval permissions turn
        on who the software is acting for, not on how the box is configured.
        """
        return cls.ENVIRONMENT in {"staging", "production"}

    @classmethod
    def voice_archive_is_durable(cls) -> bool:
        """Whether retained audio would survive a redeploy.

        Only two things count as durable: an explicit operator assertion, or an
        archive path that lives under the platform's mounted volume. Anything
        else is the container's own filesystem, which is rebuilt from the image
        on every deploy.

        Outside a shared deployment this is always true — a laptop's disk is
        durable, and a self-hoster owns the consequences of their own storage.
        """
        if not cls.is_shared_deployment() or cls.VOICE_ARCHIVE_DURABLE:
            return True
        mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
        if not mount:
            return False
        try:
            cls.resolve_path(cls.VOICE_ARCHIVE_PATH).relative_to(Path(mount).resolve())
        except (ValueError, OSError):
            return False
        return True

    @classmethod
    def resolve_path(cls, path: str | Path) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p.resolve()

    @classmethod
    def vault_path(cls) -> Path:
        return cls.resolve_path(cls.VAULT_PATH)

    @classmethod
    def vault_import_path(cls) -> Path:
        return cls.resolve_path(cls.VAULT_IMPORT_PATH)

    @classmethod
    def voice_archive_path(cls) -> Path:
        return cls.resolve_path(cls.VOICE_ARCHIVE_PATH)

    @classmethod
    def conversation_cache_path(cls) -> Path:
        return cls.resolve_path(cls.CONVERSATION_CACHE_PATH)

    @classmethod
    def reports_path(cls) -> Path:
        return cls.resolve_path(cls.REPORTS_PATH)

    @classmethod
    def backups_path(cls) -> Path:
        return cls.resolve_path(cls.BACKUPS_PATH)

    @classmethod
    def qdrant_path(cls) -> Path:
        return cls.resolve_path(cls.QDRANT_PATH)

    @classmethod
    def database_url_sync(cls) -> str:
        """Return a database URL compatible with the current sync SQLAlchemy engine."""
        url = cls.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        return url

    @classmethod
    def database_path(cls) -> str:
        url = cls.database_url_sync()
        if url.startswith("sqlite:///"):
            rel = url[len("sqlite:///") :]
            return str(cls.resolve_path(rel))
        return url

    @classmethod
    def apple_oauth_private_key(cls) -> str:
        """Load the Apple signing key from a secret value or mounted file."""
        if cls.APPLE_OAUTH_PRIVATE_KEY:
            return cls.APPLE_OAUTH_PRIVATE_KEY.replace("\\n", "\n").strip()
        if not cls.APPLE_OAUTH_PRIVATE_KEY_PATH:
            return ""
        try:
            return cls.resolve_path(cls.APPLE_OAUTH_PRIVATE_KEY_PATH).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @classmethod
    def validate_startup(cls) -> list[str]:
        """Return configuration problems that should be surfaced early."""
        if not cls.is_production():
            return []
        problems: list[str] = []
        for validator in (
            cls._validate_core_production,
            cls._validate_vector_production,
            cls._validate_transcription_production,
            cls._validate_apple_oauth_production,
            cls._validate_runtime_production,
            cls._validate_legal_urls_production,
        ):
            problems.extend(validator())
        return problems

    @classmethod
    def _validate_core_production(cls) -> list[str]:
        problems: list[str] = []
        if cls.AUTO_CREATE_TABLES:
            problems.append("AUTO_CREATE_TABLES must be false outside local development.")
        if not cls.REQUIRE_API_AUTH:
            problems.append("REQUIRE_API_AUTH must be true outside local development.")
        if not cls.API_KEY:
            problems.append("API_KEY or THOUGHTPINS_API_KEY must be set.")
        elif len(cls.API_KEY) < 32:
            problems.append("API_KEY or THOUGHTPINS_API_KEY must be at least 32 characters.")
        if not cls.JWT_SECRET:
            problems.append("JWT_SECRET must be set.")
        elif len(cls.JWT_SECRET) < 32:
            problems.append("JWT_SECRET must be at least 32 characters.")
        if not cls.LLM_API_KEY:
            problems.append("LLM_API_KEY must be set.")
        if cls.EMBEDDING_PROVIDER not in {"llm", "local", "openai"}:
            problems.append("EMBEDDING_PROVIDER must be one of: llm, local, openai.")
        if cls.EMBEDDING_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            problems.append("OPENAI_API_KEY must be set when EMBEDDING_PROVIDER=openai.")
        if cls.ALLOW_USER_API_KEYS:
            problems.append("ALLOW_USER_API_KEYS must be false outside local development.")
        if cls.RETURN_API_KEY_ON_REGISTER:
            problems.append("RETURN_API_KEY_ON_REGISTER must be false outside local development.")
        return problems

    @classmethod
    def _validate_vector_production(cls) -> list[str]:
        problems: list[str] = []
        if cls.VECTOR_MODE != "qdrant_remote":
            problems.append("VECTOR_MODE must be qdrant_remote outside local development.")
        if not cls.QDRANT_URL:
            problems.append("QDRANT_URL must be set when VECTOR_MODE=qdrant_remote.")
        if not cls.QDRANT_API_KEY:
            problems.append("QDRANT_API_KEY must be set when VECTOR_MODE=qdrant_remote.")
        if cls.QDRANT_TIMEOUT_SECONDS < 2:
            problems.append("QDRANT_TIMEOUT_SECONDS must be at least 2.")
        if not cls.VECTOR_HEALTHCHECK_LIVE:
            problems.append("VECTOR_HEALTHCHECK_LIVE must be true outside local development.")
        return problems

    @classmethod
    def _validate_transcription_production(cls) -> list[str]:
        problems: list[str] = []
        if cls.TRANSCRIPTION_PROVIDER not in {"local", "hosted"}:
            problems.append("TRANSCRIPTION_PROVIDER must be local or hosted.")
        elif cls.TRANSCRIPTION_PROVIDER == "hosted":
            if not cls.TRANSCRIPTION_API_KEY:
                problems.append("TRANSCRIPTION_API_KEY must be set when TRANSCRIPTION_PROVIDER=hosted.")
            if not _is_public_https_url(cls.TRANSCRIPTION_BASE_URL):
                problems.append("TRANSCRIPTION_BASE_URL must be a public HTTPS URL outside local development.")
            if not cls.TRANSCRIPTION_MODEL:
                problems.append("TRANSCRIPTION_MODEL must be set when TRANSCRIPTION_PROVIDER=hosted.")
        else:
            try:
                local_transcription_available = importlib.util.find_spec("whisper") is not None
            except (ImportError, ValueError):
                local_transcription_available = False
            if not local_transcription_available:
                problems.append(
                    "Local transcription is unavailable; install the voice extra or use hosted transcription."
                )
            if not cls.TRANSCRIPTION_LOCAL_MODEL:
                problems.append("TRANSCRIPTION_LOCAL_MODEL must be set when TRANSCRIPTION_PROVIDER=local.")
        if cls.TRANSCRIPTION_TIMEOUT_SECONDS < 5:
            problems.append("TRANSCRIPTION_TIMEOUT_SECONDS must be at least 5.")
        return problems

    @classmethod
    def _validate_apple_oauth_production(cls) -> list[str]:
        if not cls.APPLE_OAUTH_CLIENT_IDS:
            return []
        problems: list[str] = []
        if not cls.APPLE_OAUTH_TEAM_ID:
            problems.append("APPLE_OAUTH_TEAM_ID must be set when Apple sign-in is enabled.")
        if not cls.APPLE_OAUTH_KEY_ID:
            problems.append("APPLE_OAUTH_KEY_ID must be set when Apple sign-in is enabled.")
        apple_private_key = cls.apple_oauth_private_key()
        if not apple_private_key:
            problems.append(
                "APPLE_OAUTH_PRIVATE_KEY or APPLE_OAUTH_PRIVATE_KEY_PATH must be set when Apple sign-in is enabled."
            )
        elif "BEGIN PRIVATE KEY" not in apple_private_key:
            problems.append("The configured Apple OAuth private key is not a PEM private key.")
        if cls.APPLE_OAUTH_TIMEOUT_SECONDS < 2:
            problems.append("APPLE_OAUTH_TIMEOUT_SECONDS must be at least 2.")
        if any(not _is_public_https_url(uri) for uri in cls.APPLE_OAUTH_REDIRECT_URIS):
            problems.append("APPLE_OAUTH_REDIRECT_URIS must contain only public HTTPS URLs.")
        return problems

    @classmethod
    def _validate_runtime_production(cls) -> list[str]:
        problems: list[str] = []
        if not cls.DATA_ENCRYPTION_KEY:
            problems.append("DATA_ENCRYPTION_KEY must be set outside local development.")
        else:
            try:
                from cryptography.fernet import Fernet

                Fernet(cls.DATA_ENCRYPTION_KEY.encode("utf-8"))
            except Exception:
                problems.append("DATA_ENCRYPTION_KEY must be a valid Fernet key.")
        checks = (
            (cls.DATABASE_URL.startswith("sqlite"), "DATABASE_URL must use PostgreSQL outside local development."),
            (not cls.REDIS_URL, "REDIS_URL must be set outside local development."),
            (not cls.RATE_LIMIT_ENABLED, "RATE_LIMIT_ENABLED must be true outside local development."),
            (
                # Enforcement reads the meter. With tracking off, no usage rows
                # are written, month-to-date spend is always 0.0, and the
                # pre-call budget check can never fire -- so USAGE_ENFORCEMENT
                # says "on" while nothing is enforced, and one looping account
                # can spend without limit.
                cls.USAGE_ENFORCEMENT_ENABLED and not cls.USAGE_TRACKING_ENABLED,
                "USAGE_ENFORCEMENT_ENABLED requires USAGE_TRACKING_ENABLED: enforcement "
                "reads the usage meter, so with tracking off the spend cap never fires.",
            ),
            (not cls.PROCESS_ENTRIES_ASYNC, "PROCESS_ENTRIES_ASYNC must be true outside local development."),
            (
                cls.INGESTION_QUEUE_BACKEND != "celery",
                "INGESTION_QUEUE_BACKEND must be celery outside local development.",
            ),
            (
                cls.INGESTION_QUEUE_BACKEND == "celery" and not (cls.CELERY_BROKER_URL or cls.REDIS_URL),
                "CELERY_BROKER_URL or REDIS_URL must be set for Celery workers.",
            ),
            (
                not 10 <= cls.WORKER_RECOVERY_INTERVAL_SECONDS <= 3_600,
                "WORKER_RECOVERY_INTERVAL_SECONDS must be between 10 and 3600.",
            ),
            (not cls.SENTRY_DSN, "SENTRY_DSN must be set outside local development."),
            (
                cls.MAGIC_LINK_ENABLED and cls.EMAIL_PROVIDER == "none",
                "EMAIL_PROVIDER must deliver real mail when MAGIC_LINK_ENABLED is true; "
                "the 'none' provider logs sign-in links instead of sending them.",
            ),
            (
                cls.MAGIC_LINK_ENABLED and not cls.EMAIL_FROM_ADDRESS,
                "EMAIL_FROM_ADDRESS must be set when MAGIC_LINK_ENABLED is true.",
            ),
            (
                cls.MAGIC_LINK_ENABLED and cls.MAGIC_LINK_TTL_MINUTES > 60,
                "MAGIC_LINK_TTL_MINUTES must be 60 or less; a sign-in link is a bearer credential.",
            ),
            (not cls.SECURITY_HEADERS_ENABLED, "SECURITY_HEADERS_ENABLED must be true outside local development."),
            (cls.MAX_REQUEST_BODY_BYTES < 65_536, "MAX_REQUEST_BODY_BYTES must allow normal journal payloads."),
            (cls.LLM_TIMEOUT_SECONDS < 5, "LLM_TIMEOUT_SECONDS must be at least 5."),
            (cls.MEMORY_CONTEXT_MODE not in {"smart", "full"}, "MEMORY_CONTEXT_MODE must be smart or full."),
            (cls.MEMORY_CONTEXT_MAX_CHARS < 20_000, "MEMORY_CONTEXT_MAX_CHARS must be at least 20000."),
            (cls.TELEGRAM_TEST_MODE, "TELEGRAM_TEST_MODE must be false outside local development."),
            (
                cls.ARTICLE_ALLOW_RESTRICTED_DOMAINS,
                "ARTICLE_ALLOW_RESTRICTED_DOMAINS must be false outside local development: "
                "publisher access limits apply to any deployment serving other people.",
            ),
            (cls.ENABLE_FOUNDER_MODE, "ENABLE_FOUNDER_MODE must be false outside local development."),
            (
                cls.VOICE_ARCHIVE_ENABLED and not cls.voice_archive_is_durable(),
                "VOICE_ARCHIVE_ENABLED requires durable storage. The archive path resolves inside the "
                "container filesystem, which is discarded on every redeploy — a user who consented to "
                "keeping their recordings would silently lose them. Mount a volume and set "
                "VOICE_ARCHIVE_PATH to it, or set VOICE_ARCHIVE_DURABLE=true if the path is durable "
                "by other means.",
            ),
            (
                cls.ENABLE_TELEGRAM_BOT and not cls.TELEGRAM_ALLOWED_USER_IDS,
                "TELEGRAM_ALLOWED_USER_IDS must be set when Telegram is enabled.",
            ),
        )
        problems.extend(message for failed, message in checks if failed)
        problems.extend(graph_backend_problems(cls.GRAPH_PROVIDER, cls.GRAPH_SHADOW_ENABLED))
        problems.extend(llm_pricing_problems((cls.LLM_MODEL, cls.LLM_FALLBACK_MODEL, cls.LLM_EXTRACTION_MODEL)))
        return problems

    @classmethod
    def _validate_legal_urls_production(cls) -> list[str]:
        required_urls = {
            "PRIVACY_POLICY_URL": cls.PRIVACY_POLICY_URL,
            "TERMS_URL": cls.TERMS_URL,
            "SUPPORT_URL": cls.SUPPORT_URL,
            "ACCOUNT_DELETION_URL": cls.ACCOUNT_DELETION_URL,
            "AI_DISCLOSURE_URL": cls.AI_DISCLOSURE_URL,
        }
        problems: list[str] = []
        for name, value in required_urls.items():
            if not value:
                problems.append(f"{name} must be set outside local development.")
            elif name == "SUPPORT_URL":
                if not (_is_public_https_url(value) or value.startswith("mailto:")):
                    problems.append(
                        "SUPPORT_URL must be a public HTTPS URL or mailto address outside local development."
                    )
            elif not _is_public_https_url(value):
                problems.append(f"{name} must be a public HTTPS URL outside local development.")
        return problems

    @classmethod
    def validate_telegram_startup(cls) -> list[str]:
        """Return Telegram runtime problems before polling starts."""
        from thoughtpins.config_telegram import telegram_startup_problems

        return telegram_startup_problems(cls)


config = Config()
