"""Validate that the environment is suitable for a production deployment."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.config import config


def oauth_web_build_problems(
    google_client_ids: Sequence[str],
    apple_client_ids: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Return frontend/backend OAuth configuration mismatches."""
    values = os.environ if environ is None else environ
    google_web_client = values.get("VITE_GOOGLE_CLIENT_ID", "").strip()
    apple_web_client = values.get("VITE_APPLE_CLIENT_ID", "").strip()
    problems: list[str] = []
    if google_client_ids:
        if not google_web_client:
            problems.append("VITE_GOOGLE_CLIENT_ID is required when Google OAuth is enabled for the web app.")
        elif google_web_client not in google_client_ids:
            problems.append("VITE_GOOGLE_CLIENT_ID must be included in GOOGLE_OAUTH_CLIENT_IDS.")
    if apple_client_ids:
        if not apple_web_client:
            problems.append("VITE_APPLE_CLIENT_ID is required when Apple OAuth is enabled for the web app.")
        elif apple_web_client not in apple_client_ids:
            problems.append("VITE_APPLE_CLIENT_ID must be included in APPLE_OAUTH_CLIENT_IDS.")
    return problems


def main() -> int:
    problems = config.validate_startup()

    if config.ENVIRONMENT != "production":
        problems.append("ENVIRONMENT must be production for a production deploy.")

    if not config.DATABASE_URL.startswith("postgresql"):
        problems.append("DATABASE_URL must point at PostgreSQL.")

    if config.ENABLE_TELEGRAM_BOT and config.TELEGRAM_TEST_MODE:
        problems.append("Telegram test mode cannot be enabled with the production bot.")

    if config.INGESTION_QUEUE_BACKEND != "celery":
        problems.append("INGESTION_QUEUE_BACKEND must be celery for production.")

    problems.extend(
        oauth_web_build_problems(
            config.GOOGLE_OAUTH_CLIENT_IDS,
            config.APPLE_OAUTH_CLIENT_IDS,
        )
    )
    if problems:
        print("Production validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Production validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
