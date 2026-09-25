"""Logging configuration."""

from __future__ import annotations

import contextlib
import inspect
import logging
import re
import sys
from typing import Any

from loguru import logger

from thoughtpins.build_info import source_revision
from thoughtpins.config import config
from thoughtpins.log_redaction import WITHHELD, original_exception, withhold_exception_messages
from thoughtpins.logging_policy import apply_logging_policy

# Set on an exception once an event for it has gone to Sentry. The mark lives
# on the exception itself: it lasts exactly as long as the failure, holds
# nothing alive, and built-in exception types cannot be weakly referenced.
_REPORTED = "_thoughtpins_reported_to_sentry"


def _already_reported(hint: dict | None) -> bool:
    """True when this event reports an exception an earlier event already did.

    One unhandled 500 reaches Sentry from Starlette, from the handler's own
    logger.exception() and from uvicorn's re-log. Sentry's own dedupe compares
    the reported object, which the message-withholding stand-ins defeat, so the
    comparison is made on the original exception instead.
    """

    exc_info = (hint or {}).get("exc_info")
    value = exc_info[1] if exc_info else None
    if not isinstance(value, BaseException):
        return False
    original = original_exception(value)
    try:
        if vars(original).get(_REPORTED) is True:
            return True
        setattr(original, _REPORTED, True)
    except (AttributeError, TypeError):
        # An exception that takes no attributes is reported every time.
        pass
    return False


def _scrub_sentry_event(event: dict, hint: dict) -> dict | None:
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
    if _already_reported(hint):
        return None
    # A log event's text is its log line. Later lines are not what a log call
    # wrote: Loguru appends a rendered traceback, and asyncio the failed task's
    # repr, which quotes the exception's text.
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = logentry[key].split("\n", 1)[0]
        logentry.pop("params", None)
    # An exception's message can quote SQL parameters or parser input, and a
    # frame's local variables are the journal text itself on a content route.
    # Sentry keeps each exception's type and stack, never those.
    for container in (event.get("exception"), event.get("threads")):
        values = container.get("values") if isinstance(container, dict) else None
        for value in values or []:
            if not isinstance(value, dict):
                continue
            if value.get("value"):
                value["value"] = WITHHELD
            frames = (value.get("stacktrace") or {}).get("frames") or []
            for frame in frames:
                if isinstance(frame, dict):
                    frame.pop("vars", None)
    # Breadcrumbs carry outbound URLs (saved article links) and earlier log
    # lines; the route, status and stack are enough to act on.
    event.pop("breadcrumbs", None)
    return event


class InterceptHandler(logging.Handler):
    """Carry standard-library records -- uvicorn, Celery, libraries -- into Loguru.

    Starlette re-raises an unhandled 500 after its handler has logged it, so
    uvicorn logs the traceback again through ``logging``; Celery does the same
    for a task that raises. Routed here, those records reach the same sinks and
    the same patcher, and their exception messages are withheld too.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._route(record)
        except Exception as exc:
            # Never raise into the code that logged, and never fall back to
            # logging's handleError, which prints the record's arguments.
            with contextlib.suppress(Exception):
                logger.error(
                    "A log record from {}:{} could not be routed ({})", record.module, record.lineno, type(exc).__name__
                )

    def _route(self, record: logging.LogRecord) -> None:
        # Library lines below WARNING never reached a sink before this handler
        # existed, and some carry what should not: httpx logs each request's
        # full URL at INFO -- a saved article's address, the Telegram bot token
        # -- and uvicorn each request's path and query string at TRACE.
        if record.levelno < logging.INFO:
            return
        if record.levelno < logging.WARNING and not record.name.startswith(_INFO_SOURCES):
            return
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        try:
            text = record.getMessage()
        except Exception:
            text = str(record.msg)
        # A library's message is its first line. What follows is detail, and
        # asyncio's is the failed task's repr, which quotes the exception's text.
        text, _, detail = text.partition("\n")
        if detail.strip():
            text = f"{text} ({len(detail.splitlines())} more lines withheld)"
        # Attribute the line to the code that logged it: the frame at the
        # record's own file and line, past logging's frames and any wrapper's
        # (Sentry wraps Logger.callHandlers).
        frame, depth = inspect.currentframe(), 0
        while frame is not None and (frame.f_code.co_filename, frame.f_lineno) != (record.pathname, record.lineno):
            frame = frame.f_back
            depth += 1
        routed = logger.opt(depth=depth if frame is not None else 0, exception=record.exc_info or None)
        routed.bind(**{_ROUTED: True}).log(level, "{} | {}", record.name, text)


# Standard-library loggers whose INFO lines are kept: server lifecycle and the
# redacted access log, and the worker's task lifecycle.
_INFO_SOURCES = ("uvicorn", "celery")
# Marks a routed record. Sentry takes standard-library records from its own
# logging integration, so its Loguru handler leaves these out rather than
# report them twice.
_ROUTED = "stdlib"


def _not_routed(record: Any) -> bool:
    return not record["extra"].get(_ROUTED)


_ID_SEGMENT = re.compile(r"[A-Za-z0-9._~-]*")
# Collections whose path parameter is free text, however identifier-like it
# looks: a person's or a place's name, or a library title searched for. A
# library reference may also be a document ID, which is kept.
_NAME_COLLECTIONS = frozenset({"person", "place", "people", "places"})
_DOCUMENT_ID = re.compile(r"[0-9a-f]{6,64}")


class AccessLogRedaction(logging.Filter):
    """uvicorn's access line: keep method, route and status; drop the rest.

    The line carried the client's IP address and the full path with its query
    string -- the terms typed into library search among them. A path segment
    that is not identifier-like (a percent-encoded title, say) is redacted, and
    so is the name or title a people, places or library route is given.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            _client, method, path, version, status = record.args
            record.args = ("-", method, redact_path(str(path)), version, status)
        return True


def redact_path(path: str) -> str:
    segments = path.split("?", 1)[0].split("/")
    return "/".join(
        _redact_segment(segment, segments[index - 1] if index else "") for index, segment in enumerate(segments)
    )


def _redact_segment(segment: str, previous: str) -> str:
    if segment and previous in _NAME_COLLECTIONS:
        return "{redacted}"
    if segment and previous == "library" and not _DOCUMENT_ID.fullmatch(segment):
        return "{redacted}"
    return segment if _ID_SEGMENT.fullmatch(segment) else "{redacted}"


class TaskFailureRedaction(logging.Filter):
    """Celery's task-failure line embeds the exception's text in its arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict) and "exc" in record.args:
            exc_type = record.exc_info[0] if record.exc_info else None
            name = exc_type.__name__ if exc_type is not None else "exception"
            record.args = {**record.args, "exc": f"{name} (message withheld)"}
        return True


def route_standard_logging(level: str) -> None:
    """Send the standard-library logging tree through Loguru, filtered."""

    logging.basicConfig(handlers=[InterceptHandler()], level=_standard_level(level), force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        named = logging.getLogger(name)
        named.handlers = []
        named.propagate = True
    for name, redaction in (("uvicorn.access", AccessLogRedaction), ("celery.app.trace", TaskFailureRedaction)):
        named = logging.getLogger(name)
        if not any(isinstance(existing, redaction) for existing in named.filters):
            named.addFilter(redaction())


def _sentry_event_line(record: Any) -> str:
    # The log line alone. A format given as a function gets no traceback
    # appended; the exception reaches Sentry as data -- type and frames, its
    # message withheld -- so a rendering of it would only repeat it.
    return "{name}:{function}:{line} - {message}"


def _standard_level(level: str) -> int:
    # TRACE and SUCCESS are Loguru levels the standard library does not know.
    value: Any = logging.getLevelName(level.upper())
    if isinstance(value, int):
        return value
    return logging.DEBUG if level.upper() == "TRACE" else logging.INFO


def setup_logging() -> None:
    logger.remove()
    # Every sink below, and Sentry's Loguru handler, receives exceptions with
    # their type and frames but not their message; see log_redaction.
    logger.configure(patcher=withhold_exception_messages)

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
            from sentry_sdk.integrations.loguru import LoguruEventHandler, LoguruIntegration

            sentry_sdk.init(
                dsn=config.SENTRY_DSN,
                environment=config.ENVIRONMENT,
                # Ties each error to the commit that raised it. None keeps the
                # SDK's own default, which is what every build had before.
                release=source_revision(),
                traces_sample_rate=0.0,
                before_send=_scrub_sentry_event,
                max_request_body_size="never",
                send_default_pii=False,
                # Both default on. Frame locals on a content route are the
                # journal text, and breadcrumbs hold URLs and earlier logs.
                include_local_variables=False,
                max_breadcrumbs=0,
                # Sentry adds its own Loguru handlers with Loguru's defaults,
                # which render local variable values into a logged traceback,
                # and it sends that rendering as the event's message. Its
                # handlers stay off; the one below is added like every sink.
                integrations=[LoguruIntegration(level=None, event_level=None, sentry_logs_level=None)],
            )
            logger.add(
                LoguruEventHandler(),
                level="ERROR",
                format=_sentry_event_line,
                filter=_not_routed,
                backtrace=False,
                diagnose=False,
            )
            logger.info("Sentry initialized for environment {}", config.ENVIRONMENT)
        except Exception as e:
            logger.warning("Sentry initialization failed: {}", e)

    # uvicorn, Celery and library loggers write through the sinks above too,
    # so the exception patcher and the access-line redaction apply to them.
    route_standard_logging(log_level)

    # Third-party SDKs that echo request bodies are pinned regardless of
    # LOG_LEVEL. The model provider's client logs the full prompt at DEBUG, and
    # for this service that payload is the person's journal entry.
    apply_logging_policy()

    logger.info("Logging initialized at level {}", log_level)
