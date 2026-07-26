"""Logging configuration."""

from __future__ import annotations

import sys

from loguru import logger

from thoughtpins.config import config


def setup_logging() -> None:
    logger.remove()

    log_level = config.LOG_LEVEL.upper()
    logger.add(
        sys.stderr,
        level=log_level,
        serialize=config.JSON_LOGS,
        colorize=not config.JSON_LOGS,
        format=("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"),
    )

    logs_dir = config.resolve_path("./logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        logs_dir / "thoughtpins_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        serialize=config.JSON_LOGS,
        format=("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"),
    )

    if config.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=config.SENTRY_DSN,
                environment=config.ENVIRONMENT,
                traces_sample_rate=0.0,
            )
            logger.info("Sentry initialized for environment {}", config.ENVIRONMENT)
        except Exception as e:
            logger.warning("Sentry initialization failed: {}", e)

    logger.info("Logging initialized at level {}", log_level)
