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

from thoughtpins.config import config, is_shell_mangled_path


def oauth_web_build_problems(
    google_client_ids: Sequence[str],
    apple_client_ids: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Return frontend/backend OAuth configuration mismatches."""
    values = os.environ if environ is None else environ
    google_web_client = values.get("VITE_GOOGLE_CLIENT_ID", "").strip()
    apple_web_client = (values.get("APPLE_OAUTH_WEB_CLIENT_ID") or values.get("VITE_APPLE_CLIENT_ID", "")).strip()
    problems: list[str] = []
    if google_client_ids:
        if not google_web_client:
            problems.append("VITE_GOOGLE_CLIENT_ID is required when Google OAuth is enabled for the web app.")
        elif google_web_client not in google_client_ids:
            problems.append("VITE_GOOGLE_CLIENT_ID must be included in GOOGLE_OAUTH_CLIENT_IDS.")
    # Native-only Apple sign-in needs no Services ID. The web UI stays hidden
    # until an explicit web audience exists; a bundle ID cannot substitute for it.
    if apple_web_client and apple_web_client not in apple_client_ids:
        problems.append("Apple web client ID must be included in APPLE_OAUTH_CLIENT_IDS.")
    return problems


def client_url_problems() -> list[str]:
    """Catch URLs a Windows shell rewrote into filesystem paths.

    Git Bash and MSYS rewrite a bare leading-slash argument before the program
    sees it, so `WEB_APP_URL=/app` set from that shell is stored as
    `C:/Program Files/Git/app`. Production served exactly that, and every client
    reads store_urls to build its update link -- the web app printed it verbatim
    in the legal screen.

    This is checked here rather than in Config.validate_startup on purpose:
    init_db raises on a startup problem, and refusing to boot the API over a
    wrong store link would turn a bad link into an outage. Blocking the deploy
    is the proportionate place to stop it.
    """
    problems: list[str] = []
    for name, value in (
        ("WEB_APP_URL", config.WEB_APP_URL),
        ("IOS_STORE_URL", config.IOS_STORE_URL),
        ("ANDROID_STORE_URL", config.ANDROID_STORE_URL),
    ):
        if is_shell_mangled_path(value):
            problems.append(
                f"{name} is a filesystem path, not a URL: {value!r}. "
                "A leading-slash value set from Git Bash on Windows is rewritten before it "
                "reaches the service. Re-set it with MSYS_NO_PATHCONV=1, or use a full https:// URL."
            )
    return problems


def client_version_problems() -> list[str]:
    """Refuse a deploy that would nag every user to install a version that does not exist.

    RECOMMENDED_IOS_VERSION defaults to API_VERSION, whose own default is a
    release-candidate string ("1.0.0-rc.1"). Production is serving exactly that
    today. A shipping 1.0.0 build compares as *older* than 1.0.0-rc.1 under
    semver, so the update prompt would fire on day one, for everyone, pointing
    at a build nobody can install.

    The version comparison itself was also wrong and is fixed in
    ThoughtPinsCore; this check is the other half, so the config cannot
    reintroduce the problem from the server side.
    """
    problems: list[str] = []
    for platform, recommended in (
        ("ios", config.RECOMMENDED_IOS_VERSION),
        ("android", config.RECOMMENDED_ANDROID_VERSION),
        ("web", config.RECOMMENDED_WEB_VERSION),
    ):
        value = (recommended or "").strip()
        if not value:
            problems.append(
                f"RECOMMENDED_{platform.upper()}_VERSION is empty; set it to the version actually published."
            )
        elif "-" in value or "+" in value:
            problems.append(
                f"RECOMMENDED_{platform.upper()}_VERSION is {value!r}, a pre-release or build-metadata string. "
                "Clients compare it against their own release version and would prompt every user to "
                "update to something that was never published. Set a plain release version."
            )
    # A minimum above the recommendation locks everyone out on purpose.
    if config.MIN_IOS_VERSION and config.RECOMMENDED_IOS_VERSION:
        if _version_tuple(config.MIN_IOS_VERSION) > _version_tuple(config.RECOMMENDED_IOS_VERSION):
            problems.append(
                f"MIN_IOS_VERSION ({config.MIN_IOS_VERSION}) is above RECOMMENDED_IOS_VERSION "
                f"({config.RECOMMENDED_IOS_VERSION}), so every client is blocked and told to install "
                "a version below the minimum."
            )
    return problems


def _version_tuple(value: str) -> tuple[int, ...]:
    head = value.split("+", 1)[0].split("-", 1)[0]
    return tuple(int("".join(ch for ch in part if ch.isdigit()) or 0) for part in head.split("."))


def invite_gate_problems() -> list[str]:
    """Refuse a production deploy that would stop new accounts working.

    INVITE_ONLY closes the product to anyone without a redeemed code. During the
    closed beta that was the point. For an open launch it is a Guideline 2.1
    rejection waiting on an environment variable: a reviewer who ignores the
    demo credentials registers, hits the wall, and files.

    The gate can still be turned on -- deliberately, by also setting
    ALLOW_INVITE_ONLY_LAUNCH. Requiring two variables rather than one means a
    partially restored environment fails the deploy instead of silently closing
    the product.
    """
    problems: list[str] = []
    if config.INVITE_ONLY and not config.ALLOW_INVITE_ONLY_LAUNCH:
        problems.append(
            "INVITE_ONLY is true, which walls every newly registered account behind an "
            "invite code. If that is intended, set ALLOW_INVITE_ONLY_LAUNCH=true as well. "
            "If this is the open launch, unset INVITE_ONLY."
        )
    # SYSTEM_LOCKED is the same failure through a different variable, and a
    # blunter one: registration answers 403 outright rather than showing a wall.
    # Its default stays True, because that is the right protection for a fresh
    # or self-hosted deploy that should not accept strangers the moment it
    # boots. What must not happen is *our* production losing the override
    # silently, so the deploy check carries it instead of the default.
    if config.SYSTEM_LOCKED:
        problems.append(
            "SYSTEM_LOCKED is true, so /v1/auth/register answers 403 and nobody can "
            "create an account -- including an App Store reviewer. Set SYSTEM_LOCKED=false "
            "for a launch deploy."
        )
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
    problems.extend(client_url_problems())
    problems.extend(invite_gate_problems())
    problems.extend(client_version_problems())
    if problems:
        print("Production validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Production validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
