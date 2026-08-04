"""Unified server entry point for FastAPI and optional Telegram polling.

Usage:
    python -m thoughtpins.server              # API, plus bot when enabled
    python -m thoughtpins.server --api-only   # API only
    python -m thoughtpins.server --bot-only   # Telegram bot only
"""

from __future__ import annotations

import sys
import threading
import time

import uvicorn
from loguru import logger

from thoughtpins.api import _recover_orphaned_entries
from thoughtpins.backup import create_backup
from thoughtpins.branding import print_banner
from thoughtpins.config import config
from thoughtpins.logging_config import setup_logging
from thoughtpins.store import init_db


def _start_backup_thread() -> None:
    """Start a daemon thread that performs daily backups."""

    def backup_loop() -> None:
        while True:
            time.sleep(3600)
            try:
                _daily_backup()
            except Exception as e:
                logger.warning("Backup failed: {}", e)

    thread = threading.Thread(target=backup_loop, daemon=True, name="backup")
    thread.start()
    logger.info("Daily backup thread started")


def _daily_backup() -> None:
    """Create a timestamped ZIP backup if the last backup is older than 24 hours."""
    backup_dir = config.resolve_path("./backups")
    marker = backup_dir / ".last_backup"

    if marker.exists():
        try:
            last_ts = float(marker.read_text().strip())
            if time.time() - last_ts < 86400:
                return
        except (OSError, ValueError):
            logger.debug("Daily backup marker was unreadable; creating a fresh backup")

    info = create_backup(label="daily", keep=14)
    size_mb = info.size_bytes / (1024 * 1024)
    logger.info("Backup created: {} ({:.1f} MB)", info.path.name, size_mb)


def run_api(host: str = "127.0.0.1", port: int = 8420) -> None:
    """Start the FastAPI server via uvicorn."""
    logger.info("Starting FastAPI on {}:{}", host, port)
    uvicorn.run(
        "thoughtpins.api:app",
        host=host,
        port=port,
        log_level=config.LOG_LEVEL.lower(),
        reload=False,
        timeout_keep_alive=120,
    )


def run_bot() -> None:
    """Start the Telegram bot polling loop."""
    problems = config.validate_telegram_startup()
    if problems:
        raise RuntimeError("Telegram startup validation failed: " + "; ".join(problems))

    from telegram import Update

    from thoughtpins.bot.telegram_app import build_application

    logger.info("Starting Telegram bot")
    app = build_application()
    logger.info("Bot polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def main() -> None:
    setup_logging()

    api_only = "--api-only" in sys.argv
    bot_only = "--bot-only" in sys.argv

    print_banner(config.API_VERSION)
    logger.info("Thought Pins Server v{}", config.API_VERSION)

    logger.info("Initializing database")
    init_db()

    from thoughtpins.users import get_or_create_default_user

    default_user = get_or_create_default_user()
    logger.info("Default user ready: {}", default_user.id)

    if config.RUN_STARTUP_RECOVERY:
        _recover_orphaned_entries()
    _start_backup_thread()

    if api_only:
        run_api(config.API_HOST, config.API_PORT)
    elif bot_only:
        run_bot()
    elif not config.ENABLE_TELEGRAM_BOT:
        run_api(config.API_HOST, config.API_PORT)
    else:
        api_thread = threading.Thread(
            target=run_api,
            args=(config.API_HOST, config.API_PORT),
            daemon=True,
            name="fastapi",
        )
        api_thread.start()
        logger.info("FastAPI thread started on {}:{}", config.API_HOST, config.API_PORT)
        run_bot()


if __name__ == "__main__":
    main()
