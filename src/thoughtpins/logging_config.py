"""Logging configuration."""

from __future__ import annotations

import sys

from loguru import logger

from thoughtpins.config import config
from thoughtpins.logging_policy import apply_logging_policy


def _scrub_sentry_event(event: dict, hint: dict) -> dict:
    """Strip request bodies and user content before an event leaves the box.

    The FastAPI/Starlette integration attaches the parsed JSON request body to
    every captured exception. On this service a request body is the person's
    journal entry or chat message, so an unhandled 500 would ship user content
    to a third party. Sentry gets the route, the status, and the stack — never
    the payload.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request["query_string"] = ""
        headers = request.get("headers")
        if isinstance(headers, dict):
            for header in ("Authorization", "Cookie", "X-API-Key"):
                headers.pop(header, None)
    event.pop("user", None)
    return event


def setup_logging() -> None:
    logger.remove()

    log_level = config.LOG_LEVEL.upper()
    # backtrace/diagnose default to True in loguru, and diagnose renders local
    # variables into tracebacks. On a content-bearing route the locals are the
    # journal text itself, so a single `logger.exception("Chat failed")` would
    # print what the person wrote into stderr and the log file. Both stay off
    # everywhere: tracebacks still appear, just without variable values.
    logger.add(
        sys.stderr,
        level=log_level,
        serialize=config.JSON_LOGS,
        colorize=not config.JSON_LOGS,
        backtrace=False,
        diagnose=False,
        format=("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"),
    )

    # The file sink exists for local debugging. In production it was a
    # standing bypass of the no-content-in-logs guarantee: an unconditional
    # DEBUG sink with 30-day retention captures payload-bearing records that
    # the stderr sink's LOG_LEVEL would have filtered, on a disk nobody reads.
    if not config.is_production():
        logs_dir = config.resolve_path("./logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            logs_dir / "thoughtpins_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            serialize=config.JSON_LOGS,
            backtrace=False,
            diagnose=False,
            format=("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"),
        )

    if config.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=config.SENTRY_DSN,
                environment=config.ENVIRONMENT,
                traces_sample_rate=0.0,
                before_send=_scrub_sentry_event,
                max_request_body_size="never",
                send_default_pii=False,
            )
            logger.info("Sentry initialized for environment {}", config.ENVIRONMENT)
        except Exception as e:
            logger.warning("Sentry initialization failed: {}", e)

    # Third-party SDKs that echo request bodies are pinned regardless of
    # LOG_LEVEL. The model provider's client logs the full prompt at DEBUG, and
    # for this service that payload is the person's journal entry.
    apply_logging_policy()

    logger.info("Logging initialized at level {}", log_level)
