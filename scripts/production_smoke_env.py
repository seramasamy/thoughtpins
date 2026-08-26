"""The one definition of a production-shaped environment for config validation.

CI and the local release gate both need to ask whether a configuration would be
allowed to serve production traffic, without a real production environment to
ask it about. They answered it from two hand-maintained lists that had drifted
by twenty-six keys, so a newly required setting could pass the local gate and
fail in CI — which is what happened the moment the LLM price map became
mandatory. One list now, imported by both.

Every secret here is generated or obviously fake. The step validates the shape
of a configuration and never opens a connection.
"""

from __future__ import annotations

import base64
import json
import os
import secrets


def _fake_secret(prefix: str) -> str:
    return f"release-check-{prefix}-{secrets.token_urlsafe(32)}"


def production_smoke_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "production",
            # Production transcribes through a hosted provider. The default is
            # local, which needs the voice extra and the whisper model CI does
            # not install, so mirror the real deployment.
            "TRANSCRIPTION_PROVIDER": "hosted",
            "TRANSCRIPTION_API_KEY": "ci-transcription-key",
            "TRANSCRIPTION_BASE_URL": "https://api.openai.com/v1",
            "TRANSCRIPTION_MODEL": "whisper-1",
            "API_VERSION": "1.0.0-rc.1",
            "PRIVACY_POLICY_URL": "https://thoughtpins.com/privacy",
            "TERMS_URL": "https://thoughtpins.com/terms",
            "SUPPORT_URL": "https://thoughtpins.com/support",
            "ACCOUNT_DELETION_URL": "https://thoughtpins.com/account/delete",
            "AI_DISCLOSURE_URL": "https://thoughtpins.com/ai-disclosure",
            "MIN_IOS_VERSION": "1.0.0",
            "MIN_ANDROID_VERSION": "1.0.0",
            "MIN_WEB_VERSION": "1.0.0",
            "RECOMMENDED_IOS_VERSION": "1.0.0",
            "RECOMMENDED_ANDROID_VERSION": "1.0.0",
            "RECOMMENDED_WEB_VERSION": "1.0.0",
            "IOS_STORE_URL": "https://apps.apple.com/app/id0000000000",
            "ANDROID_STORE_URL": "https://play.google.com/store/apps/details?id=com.thoughtpins.app",
            "WEB_APP_URL": "https://thoughtpins.com/app",
            # A launch deploy must accept new registrations, or an App Store
            # reviewer who ignores the demo credentials cannot get in at all.
            # SYSTEM_LOCKED defaults closed, which is right for a fresh
            # self-hosted install and wrong for the public service, so the
            # simulated production config states the launch value explicitly.
            "SYSTEM_LOCKED": "false",
            "REQUIRE_API_AUTH": "true",
            "API_KEY": _fake_secret("api"),
            "JWT_SECRET": _fake_secret("jwt"),
            "ALLOW_USER_API_KEYS": "false",
            "RETURN_API_KEY_ON_REGISTER": "false",
            "GOOGLE_OAUTH_CLIENT_IDS": "",
            "APPLE_OAUTH_CLIENT_IDS": "",
            "VITE_GOOGLE_CLIENT_ID": "",
            "VITE_APPLE_CLIENT_ID": "",
            "AUTO_CREATE_TABLES": "false",
            "DATABASE_URL": "postgresql+psycopg2://thoughtpins_app:password@127.0.0.1:5432/thoughtpins",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "RATE_LIMIT_ENABLED": "true",
            "PROCESS_ENTRIES_ASYNC": "true",
            "INGESTION_QUEUE_BACKEND": "celery",
            "CELERY_BROKER_URL": "redis://127.0.0.1:6379/1",
            "CELERY_RESULT_BACKEND": "redis://127.0.0.1:6379/2",
            "LLM_PROVIDER": "openai_compatible",
            "LLM_API_KEY": _fake_secret("llm"),
            # Production refuses an unpriced runtime, because the spend cap is
            # computed from the price map. Name the runtimes and price them here
            # so this gate tests the production shape rather than whichever model
            # the developer happens to have configured locally.
            "LLM_MODEL": "release-check-chat",
            "LLM_FALLBACK_MODEL": "release-check-chat",
            "LLM_EXTRACTION_MODEL": "release-check-extract",
            "LLM_PRICING_JSON": json.dumps(
                {
                    "release-check-chat": {"input_per_1m": 3.0, "output_per_1m": 15.0},
                    "release-check-extract": {"input_per_1m": 0.3, "output_per_1m": 1.2},
                }
            ),
            "EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": _fake_secret("openai"),
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
            "OPENAI_EMBEDDING_DIMENSIONS": "1536",
            "VECTOR_MODE": "qdrant_remote",
            "QDRANT_URL": "http://127.0.0.1:6333",
            "QDRANT_API_KEY": _fake_secret("qdrant"),
            "QDRANT_TIMEOUT_SECONDS": "10",
            "VECTOR_HEALTHCHECK_LIVE": "true",
            "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
            "SENTRY_DSN": "https://public@example.com/1",
            "SECURITY_HEADERS_ENABLED": "true",
            "RUN_STARTUP_RECOVERY": "false",
            "TELEGRAM_TEST_MODE": "false",
            "ENABLE_FOUNDER_MODE": "false",
            "ENABLE_TELEGRAM_BOT": "false",
            # A machine set up per founder/README.md keeps the voice archive on
            # for local testing, and its path is not a durable mount, so the
            # shared-deployment rule fires and this gate fails for a reason that
            # describes the laptop rather than production. Production ships it
            # off (.env.production.example), and the durability rule itself is
            # asserted directly by tests/test_voice_archive_durability.py, so
            # pin the shipped shape instead of letting a local .env decide.
            "VOICE_ARCHIVE_ENABLED": "false",
        }
    )
    return env
