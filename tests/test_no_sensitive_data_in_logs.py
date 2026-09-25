"""The logging rule, enforced instead of trusted.

`AGENTS.md` says: "Do not log raw journal text, source text, access tokens,
refresh tokens, authorization headers, cookies, or provider credentials." The
privacy policy depends on that being true, and until now nothing checked it.
A rule nothing tests is a hope.

The approach is deliberately black-box. Rather than reading the logging calls
and reasoning about them -- which only ever proves something about the lines
someone thought to look at -- this drives real requests through the real app
with a distinctive sentinel in the journal text, captures every record emitted
by every logger at DEBUG, and asserts the sentinel is in none of them. A new
`logger.info(f"saving {text}")` anywhere in the request path fails this test
without anyone having to remember the rule.

Tokens are checked the same way, including a suffix of each, so a truncated or
partially-redacted token is still caught.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

PASSPHRASE = "correct horse battery staple"

# Distinctive enough that a substring match cannot be a coincidence, and it
# contains no characters a formatter would escape or split.
JOURNAL_SENTINEL = "ZQXJ7-PANGOLIN-VESTIBULE-SENTINEL-9f2a"
CHAT_SENTINEL = "KWVM4-ALBATROSS-TURNSTILE-SENTINEL-1c8e"


@pytest.fixture
def client(isolated_db):
    from thoughtpins.api import app

    return TestClient(app)


class _Capture(logging.Handler):
    """Every record, formatted, from every logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # a broken formatter must not hide a leak
            self.lines.append(f"{record.name}:{record.msg!r}:{record.args!r}")


@pytest.fixture
def captured_logs():
    handler = _Capture()
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    # Loggers that opted out of propagation would otherwise escape the net.
    touched = []
    for name in list(logging.root.manager.loggerDict):
        candidate = logging.getLogger(name)
        if not candidate.propagate:
            candidate.addHandler(handler)
            touched.append(candidate)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        for candidate in touched:
            candidate.removeHandler(handler)


def _register_and_sign_in(client: TestClient, email: str) -> dict[str, str]:
    registration = client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE})
    assert registration.status_code == 200, registration.text
    signin = client.post("/v1/auth/login", json={"identifier": email, "password": PASSPHRASE})
    assert signin.status_code == 200, signin.text
    return signin.json()


def _assert_absent(lines: list[str], needle: str, what: str) -> None:
    hits = [line for line in lines if needle in line]
    assert not hits, f"{what} appeared in {len(hits)} log line(s); first: {hits[0][:300]}"


def test_journal_text_and_tokens_never_reach_a_log_line(client, captured_logs):
    tokens = _register_and_sign_in(client, "sentinel-logs@thoughtpins.com")
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]
    headers = {"Authorization": f"Bearer {access}"}

    client.post(
        "/v1/legal/acceptances",
        headers=headers,
        json={"document": "ai_disclosure", "version": "2026-07-13"},
    )
    entry = client.post(
        "/v1/entries",
        headers=headers,
        json={"text": f"A private note that mentions {JOURNAL_SENTINEL} and nothing else."},
    )
    assert entry.status_code in (200, 201, 202), entry.text
    client.get("/v1/entries", headers=headers, params={"limit": 5})
    client.post("/v1/chat", headers=headers, json={"text": f"what about {CHAT_SENTINEL}?", "surface": "ios"})
    client.post("/v1/auth/refresh", json={"refresh_token": refresh})

    lines = captured_logs.lines
    assert lines, "captured no log records at all, so this test would pass vacuously"

    _assert_absent(lines, JOURNAL_SENTINEL, "journal text")
    _assert_absent(lines, CHAT_SENTINEL, "chat text")
    _assert_absent(lines, access, "the access token")
    _assert_absent(lines, refresh, "the refresh token")
    # A partially redacted token is still a leaked token.
    _assert_absent(lines, access[-24:], "the tail of the access token")
    _assert_absent(lines, refresh[-20:], "the tail of the refresh token")
    _assert_absent(lines, PASSPHRASE, "the password")
    _assert_absent(lines, "Bearer ey", "an Authorization header value")


def test_the_capture_would_actually_catch_a_leak(captured_logs):
    """Guard against the guard.

    If the capture fixture ever stopped receiving records -- a logging config
    change, a propagate=False logger added somewhere -- the test above would
    pass while proving nothing. This proves the net catches what is thrown at
    it, including from a logger that does not propagate.
    """
    logging.getLogger("thoughtpins.leak_probe").warning("contains %s here", JOURNAL_SENTINEL)
    assert any(JOURNAL_SENTINEL in line for line in captured_logs.lines)


# --------------------------------------------------------- loguru and Sentry
#
# The capture above hooks stdlib logging, and the application's own logging is
# loguru -- a separate pipeline the stdlib net never sees. Two bypasses lived
# there: loguru renders tracebacks with local-variable values unless
# diagnose=False is set per sink, and the DEBUG file sink captured payload-
# bearing records regardless of LOG_LEVEL. These tests drive a real request
# into a real in-handler exception and assert the sentinel stays out of what
# the configured sinks would emit.

CRASH_SENTINEL = "XRTB2-CASSOWARY-PALISADE-SENTINEL-7d4c"


@pytest.fixture
def captured_loguru():
    """Everything the app's sinks would emit, rendered with their settings."""
    from loguru import logger

    from thoughtpins.logging_config import setup_logging

    restore = _snapshot_standard_logging()
    setup_logging()
    lines: list[str] = []
    handler_id = logger.add(
        lambda message: lines.append(str(message)),
        level="DEBUG",
        backtrace=False,
        diagnose=False,
    )
    try:
        yield lines
    finally:
        logger.remove(handler_id)
        logger.remove()
        # setup_logging installs a process-wide patcher and routes the standard
        # logging tree; later tests start clean.
        # configure(patcher=None) is a no-op in Loguru 0.7; install a no-op patcher.
        logger.configure(patcher=lambda record: None)
        restore()


def _snapshot_standard_logging():
    import logging

    names = ("uvicorn", "uvicorn.error", "uvicorn.access", "celery.app.trace")
    root = logging.getLogger()
    saved = (
        root.handlers[:],
        root.level,
        {
            n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate, logging.getLogger(n).filters[:])
            for n in names
        },
    )

    def restore() -> None:
        root.handlers, root.level = saved[0], saved[1]
        for name, (handlers, propagate, filters) in saved[2].items():
            named = logging.getLogger(name)
            named.handlers, named.propagate, named.filters = handlers, propagate, filters

    return restore


def test_a_chat_crash_does_not_print_the_message_into_the_logs(client, captured_loguru, monkeypatch):
    tokens = _register_and_sign_in(client, "sentinel-crash@thoughtpins.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post(
        "/v1/legal/acceptances",
        headers=headers,
        json={"document": "ai_disclosure", "version": "2026-07-13"},
    )

    def crash(session, text, **kwargs):
        the_message_being_processed = text  # noqa: F841 -- the local diagnose would print
        raise RuntimeError("engine exploded mid-request")

    import thoughtpins.api as api_module

    monkeypatch.setattr(api_module, "execute_chat_message", crash)
    response = client.post(
        "/v1/chat",
        headers=headers,
        json={"text": f"please remember {CRASH_SENTINEL} for me", "surface": "ios"},
    )
    assert response.status_code == 500

    rendered = "\n".join(captured_loguru)
    assert "Chat failed" in rendered, "the handler did not log the failure, so this proves nothing"
    assert CRASH_SENTINEL not in rendered, (
        "the chat message reached the logs through the exception path -- "
        "a diagnose-rendered traceback prints handler locals, which here is what the person wrote"
    )


def test_the_loguru_capture_would_catch_a_diagnose_leak(captured_loguru):
    """Guard against the guard: with diagnose on, the same shape DOES leak.

    This is the exact mechanism the fix turned off. If loguru's rendering ever
    changes so that diagnose no longer prints locals, this canary fails and the
    test above needs a new leak model rather than silent confidence.
    """
    from loguru import logger

    diagnose_lines: list[str] = []
    handler_id = logger.add(
        lambda message: diagnose_lines.append(str(message)),
        level="DEBUG",
        backtrace=True,
        diagnose=True,
    )
    try:
        try:
            # diagnose annotates the values of names referenced on the lines it
            # renders, so the raising line must mention the variable -- while
            # keeping the sentinel itself out of the source text.
            secret_local = "the payload " + CRASH_SENTINEL + " in a local"
            raise RuntimeError("boom" + secret_local[:0])
        except RuntimeError:
            logger.exception("Probe failed")
    finally:
        logger.remove(handler_id)

    assert any(CRASH_SENTINEL in line for line in diagnose_lines), (
        "diagnose=True no longer prints locals; the leak model behind these tests is stale"
    )
    assert not any(CRASH_SENTINEL in line for line in captured_loguru), "the diagnose=False sink printed locals anyway"


# A production-mode process with the real Sentry SDK and a transport that keeps
# what it would have sent. It runs apart from this test session because
# sentry_sdk.init patches the standard library and frameworks process-wide, and
# from a file, because Loguru can only annotate variables in source it can read.
_SENTRY_CHILD = """
import base64, json, logging, os, sys

import sentry_sdk
from sentry_sdk.transport import Transport

sent = []


class Keep(Transport):
    def capture_envelope(self, envelope):
        sent.append(envelope.serialize())


real_init = sentry_sdk.init
sentry_sdk.init = lambda *args, **kwargs: real_init(*args, transport=Keep, **kwargs)

from loguru import logger

from thoughtpins import logging_config
from thoughtpins.logging_config import setup_logging

# Each event as Sentry built it, before the scrubber: the handler's own output.
scrub = logging_config._scrub_sentry_event
unscrubbed = []


def recording(event, hint):
    unscrubbed.append({"logger": event.get("logger"), "logentry": dict(event.get("logentry") or {})})
    return scrub(event, hint)


recording.__name__ = scrub.__name__
logging_config._scrub_sentry_event = recording
setup_logging()
sentinel = os.environ["THOUGHTPINS_TEST_SENTINEL"]


def reply(text):
    note = "remember " + text
    raise RuntimeError("failed on " + note)


try:
    reply(sentinel)
except RuntimeError as error:
    logger.exception("Chat failed")
    # uvicorn logs an unhandled failure again, through the standard library.
    logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=error)
try:
    raise ValueError("second " + sentinel)
except ValueError:
    logger.exception("Import failed")


async def fail():
    raise LookupError("third " + sentinel)


# What asyncio logs for a failed task nobody awaited: its repr, on a second
# line, quotes the exception's text.
import asyncio

loop = asyncio.new_event_loop()
task = loop.create_task(fail())
loop.run_until_complete(asyncio.wait([task]))
context = {"message": "Task exception was never retrieved", "exception": task.exception(), "future": task}
loop.default_exception_handler(context)
loop.close()
# A standard-library error with no exception attached: Sentry's logging
# integration reports it, and its Loguru handler leaves routed records alone.
logging.getLogger("thoughtpins.probe").error("Routed failure line")
sentry_sdk.flush()
options = sentry_sdk.get_client().options
report = {
    "options": {
        "before_send": getattr(options["before_send"], "__name__", None),
        "max_request_body_size": options["max_request_body_size"],
        "send_default_pii": options["send_default_pii"],
        "include_local_variables": options["include_local_variables"],
        "max_breadcrumbs": options["max_breadcrumbs"],
    },
    "envelopes": [base64.b64encode(envelope).decode("ascii") for envelope in sent],
    "unscrubbed": unscrubbed,
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(report, handle)
"""


@pytest.fixture(scope="module")
def sentry_child(tmp_path_factory) -> dict[str, Any]:
    import base64
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sentry_sdk.envelope import Envelope

    folder = tmp_path_factory.mktemp("sentry")
    output, child = folder / "report.json", folder / "sentry_child.py"
    child.write_text(_SENTRY_CHILD, encoding="utf-8")
    environment = {
        name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME") if name in os.environ
    }
    environment.update(
        SENTRY_DSN="https://public@example.invalid/1",
        ENVIRONMENT="production",
        LOG_LEVEL="INFO",
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
        # Not an argument: Sentry attaches sys.argv to every event.
        THOUGHTPINS_TEST_SENTINEL=CRASH_SENTINEL,
    )
    completed = subprocess.run(
        [sys.executable, str(child), str(output)],
        cwd=folder,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    report = json.loads(output.read_text(encoding="utf-8"))
    envelopes = [base64.b64decode(envelope) for envelope in report["envelopes"]]
    report["payload"] = b"\n".join(envelopes)
    report["events"] = [
        item.payload.json
        for envelope in envelopes
        for item in Envelope.deserialize(envelope).items
        if item.headers.get("type") == "event"
    ]
    report["logs"] = completed.stderr
    return report


def test_setup_logging_wires_the_sentry_scrubber(sentry_child):
    """The scrubber is only worth anything if init actually receives it."""
    options = sentry_child["options"]

    assert options["before_send"] == "_scrub_sentry_event"
    assert options["max_request_body_size"] == "never"
    assert options["send_default_pii"] is False
    # Both default on in sentry-sdk: frame locals are journal text on a content
    # route, and breadcrumbs hold saved-article URLs and earlier log lines.
    assert options["include_local_variables"] is False
    assert options["max_breadcrumbs"] == 0


def test_what_sentry_is_sent_for_a_logged_failure_holds_no_content(sentry_child):
    """Loguru renders local values into a traceback by default, and Sentry's own
    Loguru handler used that rendering as the event message."""
    assert sentry_child["events"], "the logged failures should have reached Sentry"
    assert CRASH_SENTINEL.encode() not in sentry_child["payload"]
    assert CRASH_SENTINEL not in sentry_child["logs"]

    chat = next(event for event in sentry_child["events"] if "Chat failed" in event["logentry"]["formatted"])
    (exception,) = chat["exception"]["values"]
    assert exception["type"] == "RuntimeError"
    frames = exception["stacktrace"]["frames"]
    assert [frame["function"] for frame in frames][-1] == "reply", "the stack should survive"
    assert not any("vars" in frame for frame in frames)


def test_the_loguru_handler_hands_sentry_the_log_line_alone(sentry_child):
    """Before any scrubbing: no rendered traceback, so no local values to leak."""
    from_loguru = [event["logentry"] for event in sentry_child["unscrubbed"] if event["logger"] == "__main__"]

    assert len(from_loguru) == 2, "one per logger.exception() call, and nothing from Sentry's own handlers"
    for logentry in from_loguru:
        assert "\n" not in logentry["formatted"], logentry["formatted"][:300]
        assert CRASH_SENTINEL not in repr(logentry)


def test_the_scrubber_keeps_only_a_log_events_first_line():
    from thoughtpins.logging_config import _scrub_sentry_event

    text = f"Task exception was never retrieved\nfuture: <Task exception=LookupError('{CRASH_SENTINEL}')>"
    event = {"logentry": {"message": text, "formatted": text, "params": [CRASH_SENTINEL]}}

    scrubbed = _scrub_sentry_event(event, {})

    assert scrubbed is not None
    assert scrubbed["logentry"] == {
        "message": "Task exception was never retrieved",
        "formatted": "Task exception was never retrieved",
    }


def test_a_failed_task_nobody_awaited_is_logged_without_its_text(captured_loguru):
    import asyncio

    async def fail() -> None:
        raise LookupError(CRASH_SENTINEL)

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(fail())
        loop.run_until_complete(asyncio.wait([task]))
        context = {"message": "Task exception was never retrieved", "exception": task.exception(), "future": task}
        loop.default_exception_handler(context)
    finally:
        loop.close()

    rendered = "\n".join(captured_loguru)
    assert "Task exception was never retrieved (1 more lines withheld)" in rendered
    assert CRASH_SENTINEL not in rendered


def test_one_failure_logged_twice_reaches_sentry_once(sentry_child):
    failures = [event for event in sentry_child["events"] if "exception" in event]
    kinds = sorted(event["exception"]["values"][-1]["type"] for event in failures)

    assert kinds == ["LookupError", "RuntimeError", "ValueError"]


def test_a_standard_library_error_reaches_sentry_once(sentry_child):
    reports = [
        event
        for event in sentry_child["events"]
        if "Routed failure line" in event.get("logentry", {}).get("formatted", "")
    ]

    assert len(reports) == 1, [event.get("logger") for event in reports]


def test_the_scrubbed_sentry_event_for_a_chat_crash_has_no_content():
    """The event shape the FastAPI integration builds, put through the scrubber."""
    from thoughtpins.logging_config import _scrub_sentry_event

    event = {
        "request": {
            "url": "https://api.thoughtpins.com/v1/chat",
            "method": "POST",
            "data": {"text": f"please remember {CRASH_SENTINEL} for me", "surface": "ios"},
            "query_string": "",
            "headers": {"Authorization": "Bearer eyJhbGc", "Content-Type": "application/json"},
            "cookies": {},
        },
        "user": {"id": "user-123"},
        "exception": {"values": [{"type": "RuntimeError", "value": "engine exploded mid-request"}]},
    }
    scrubbed = _scrub_sentry_event(event, {})
    assert scrubbed is not None
    flattened = repr(scrubbed)
    assert CRASH_SENTINEL not in flattened
    assert "eyJhbGc" not in flattened
    assert scrubbed["request"]["url"].endswith("/v1/chat"), "route context should survive scrubbing"
    assert scrubbed["exception"]["values"], "the stack context should survive scrubbing"


def test_an_exception_message_is_withheld_but_its_type_and_frames_are_kept(captured_loguru):
    """logger.exception() attaches the traceback itself; its last line is the message.

    A SQLAlchemy error prints its statement parameters, which on this service
    are what someone wrote. The patcher keeps the type and every frame.
    """
    import json

    from loguru import logger
    from sqlalchemy.exc import IntegrityError

    json_lines: list[str] = []
    json_sink = logger.add(lambda message: json_lines.append(str(message)), serialize=True, diagnose=False)
    try:

        def store_entry() -> None:
            raise IntegrityError("INSERT INTO raw_entries (raw_text) VALUES (?)", (CRASH_SENTINEL,), Exception("dup"))

        try:
            try:
                store_entry()
            except IntegrityError as exc:
                raise RuntimeError(f"ingest failed for {CRASH_SENTINEL}") from exc
        except RuntimeError:
            logger.exception("Upload ingest failed")
    finally:
        logger.remove(json_sink)

    rendered = "\n".join(captured_loguru)
    assert CRASH_SENTINEL not in rendered
    assert CRASH_SENTINEL not in "\n".join(json_lines)
    assert "sqlalchemy.exc.IntegrityError" in rendered and "RuntimeError" in rendered
    assert "store_entry" in rendered, "frames are what make the log useful; they must survive"
    record = json.loads(json_lines[0])["record"]["exception"]
    assert record["type"] == "RuntimeError"


def test_a_chat_crash_whose_error_quotes_the_message_stays_out_of_the_logs(client, captured_loguru, monkeypatch):
    tokens = _register_and_sign_in(client, "sentinel-quoting-crash@thoughtpins.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post(
        "/v1/legal/acceptances",
        headers=headers,
        json={"document": "ai_disclosure", "version": "2026-07-13"},
    )

    def crash(session, text, **kwargs):
        raise RuntimeError(f"could not parse {text!r}")

    import thoughtpins.api as api_module

    monkeypatch.setattr(api_module, "execute_chat_message", crash)
    response = client.post(
        "/v1/chat", headers=headers, json={"text": f"please remember {CRASH_SENTINEL}", "surface": "ios"}
    )
    assert response.status_code == 500

    rendered = "\n".join(captured_loguru)
    assert "Chat failed" in rendered and "RuntimeError" in rendered
    assert CRASH_SENTINEL not in rendered


def test_sentry_keeps_the_stack_but_not_messages_locals_or_breadcrumbs():
    from thoughtpins.logging_config import _scrub_sentry_event

    frame = {"filename": "thoughtpins/chat/engine.py", "function": "reply", "vars": {"text": CRASH_SENTINEL}}
    event = {
        "exception": {
            "values": [
                {"type": "IntegrityError", "value": f"params ({CRASH_SENTINEL},)", "stacktrace": {"frames": [frame]}}
            ]
        },
        "threads": {"values": [{"stacktrace": {"frames": [dict(frame)]}}]},
        "breadcrumbs": {"values": [{"category": "httpx", "data": {"url": f"https://example.com/{CRASH_SENTINEL}"}}]},
    }

    scrubbed = _scrub_sentry_event(event, {})

    assert scrubbed is not None
    assert CRASH_SENTINEL not in repr(scrubbed)
    exception = scrubbed["exception"]["values"][0]
    assert exception["type"] == "IntegrityError"
    assert exception["stacktrace"]["frames"][0]["function"] == "reply"


def test_uvicorns_own_traceback_for_an_unhandled_500_is_redacted_too(captured_loguru):
    """Starlette re-raises after its handler, so uvicorn logs the error again via logging."""
    import logging

    try:
        raise RuntimeError(f"could not parse {CRASH_SENTINEL!r}")
    except RuntimeError:
        logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=True)

    rendered = "\n".join(captured_loguru)
    assert "Exception in ASGI application" in rendered and "RuntimeError" in rendered
    assert CRASH_SENTINEL not in rendered


def test_the_access_log_keeps_route_and_status_but_not_ip_or_query(captured_loguru):
    import logging

    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "203.0.113.9:51234", "GET", f"/v1/library?q={CRASH_SENTINEL}", "1.1", 200
    )
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "203.0.113.9:51234", "GET", "/v1/library/Therapy%20notes%20March", "1.1", 200
    )

    rendered = "\n".join(captured_loguru)
    assert '"GET /v1/library HTTP/1.1" 200' in rendered
    assert "/v1/library/{redacted}" in rendered
    assert CRASH_SENTINEL not in rendered and "203.0.113.9" not in rendered and "Therapy" not in rendered


def test_a_celery_task_failure_line_withholds_the_exception_text(captured_loguru):
    import logging

    try:
        raise ValueError(f"extraction failed on {CRASH_SENTINEL!r}")
    except ValueError as exc:
        logging.getLogger("celery.app.trace").error(
            "Task %(name)s[%(id)s] %(description)s: %(exc)s",
            {"name": "thoughtpins.ingest_job", "id": "job-1", "description": "raised unexpected", "exc": repr(exc)},
            exc_info=True,
        )

    rendered = "\n".join(captured_loguru)
    assert "thoughtpins.ingest_job" in rendered and "ValueError (message withheld)" in rendered
    assert CRASH_SENTINEL not in rendered


def test_uvicorn_is_started_without_its_own_logging_config(monkeypatch):
    import uvicorn

    from thoughtpins import server

    captured: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    server.run_api()

    assert "log_config" in captured and captured["log_config"] is None


def test_the_celery_worker_leaves_the_root_logger_to_setup_logging(monkeypatch):
    pytest.importorskip("celery")
    from thoughtpins.config import config

    monkeypatch.setattr(config, "CELERY_BROKER_URL", "memory://")
    monkeypatch.setattr(config, "CELERY_RESULT_BACKEND", "cache+memory://")
    import thoughtpins.worker as worker

    assert worker.celery_app.conf.worker_hijack_root_logger is False


def test_an_exception_groups_children_keep_types_and_frames_without_text():
    from loguru import logger

    from thoughtpins.log_redaction import withhold_exception_messages

    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), backtrace=False, diagnose=False)
    try:

        def first_child() -> None:
            raise KeyError(CRASH_SENTINEL)

        errors: list[Exception] = []
        try:
            first_child()
        except KeyError as exc:
            errors.append(exc)
        try:
            raise ExceptionGroup(f"group {CRASH_SENTINEL}", errors)
        except ExceptionGroup:
            logger.patch(withhold_exception_messages).exception("Task group failed")
    finally:
        logger.remove(sink)

    rendered = "\n".join(lines)
    assert CRASH_SENTINEL not in rendered
    assert "KeyError" in rendered and "first_child" in rendered


def test_library_info_lines_stay_out_but_warnings_come_through(captured_loguru):
    """httpx logs every request's full URL at INFO: saved article links, the bot token."""
    import logging

    logging.getLogger("httpx").info(f"HTTP Request: GET https://api.telegram.org/bot{CRASH_SENTINEL}/getUpdates")
    logging.getLogger("httpx").warning("connection pool is full, discarding connection")

    rendered = "\n".join(captured_loguru)
    assert CRASH_SENTINEL not in rendered
    assert "connection pool is full" in rendered


def test_a_routed_record_names_where_it_came_from(captured_loguru, monkeypatch):
    """Sentry wraps Logger.callHandlers, so walking past logging's own frames is not enough."""
    import logging

    handle = logging.Logger.callHandlers

    def wrapped(self: logging.Logger, record: logging.LogRecord) -> None:
        handle(self, record)

    monkeypatch.setattr(logging.Logger, "callHandlers", wrapped)
    logging.getLogger("uvicorn.error").warning("worker timeout")

    line = next(line for line in captured_loguru if "worker timeout" in line)
    assert ":test_a_routed_record_names_where_it_came_from:" in line, line


def test_a_record_that_cannot_be_routed_never_reaches_the_caller(captured_loguru, monkeypatch):
    """logging's own fallback, handleError, would print the record's arguments."""
    import logging

    from thoughtpins.logging_config import InterceptHandler

    def broken(self: Any, record: logging.LogRecord) -> None:
        raise TypeError("routing failed")

    monkeypatch.setattr(InterceptHandler, "_route", broken)
    logging.getLogger("thoughtpins.probe").warning("about %s", CRASH_SENTINEL)

    rendered = "\n".join(captured_loguru)
    assert "A log record from test_no_sensitive_data_in_logs:" in rendered
    assert "could not be routed (TypeError)" in rendered
    assert CRASH_SENTINEL not in rendered


def test_an_unhashable_exception_is_withheld_and_never_raises(captured_loguru):
    """A dataclass exception compares by value, so it cannot be hashed."""
    from dataclasses import dataclass

    from loguru import logger

    @dataclass
    class Rejected(Exception):
        detail: str

    try:
        raise Rejected(CRASH_SENTINEL)
    except Rejected:
        logger.exception("Import failed")

    rendered = "\n".join(captured_loguru)
    assert "Import failed" in rendered and "Rejected" in rendered
    assert CRASH_SENTINEL not in rendered


def test_library_lines_below_info_stay_out_whatever_their_level(captured_loguru):
    """At LOG_LEVEL=TRACE uvicorn sets uvicorn.asgi to TRACE itself, then logs
    every request's scope -- its path and query string."""
    import logging

    from loguru import logger

    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="TRACE")
    asgi = logging.getLogger("uvicorn.asgi")
    previous = asgi.level
    asgi.setLevel(5)
    try:
        asgi.log(5, "ASGI [1] Started scope=%s", {"path": "/v1/library", "query_string": CRASH_SENTINEL})
    finally:
        asgi.setLevel(previous)
        logger.remove(sink)

    assert CRASH_SENTINEL not in "\n".join(lines)


@pytest.mark.parametrize(
    ("path", "logged"),
    [
        ("/v1/people/Alice", "/v1/people/{redacted}"),
        ("/v1/places/paris", "/v1/places/{redacted}"),
        ("/person/Alice", "/person/{redacted}"),
        ("/v1/library/Diary", "/v1/library/{redacted}"),
        ("/v1/library/3f9a2b7c1d4e5f60", "/v1/library/3f9a2b7c1d4e5f60"),
        ("/v1/library?q=Alice", "/v1/library"),
        ("/personality", "/personality"),
        ("/v1/jobs/3f9a2b7c1d4e5f60/retry", "/v1/jobs/3f9a2b7c1d4e5f60/retry"),
    ],
)
def test_names_and_titles_in_paths_stay_out_of_the_access_log(path, logged):
    from thoughtpins.logging_config import redact_path

    assert redact_path(path) == logged


def test_every_path_parameter_is_an_identifier_or_redacted_in_the_access_log():
    """A new route that takes free text in its path must be added to the redaction."""
    import re

    from thoughtpins.api import app
    from thoughtpins.logging_config import redact_path

    unredacted = []
    for path in app.openapi()["paths"]:
        for match in re.finditer(r"\{([^}]+)\}", path):
            if match.group(1).endswith("_id"):
                continue
            probe = path[: match.start()] + "Alice" + path[match.end() :]
            if "Alice" in redact_path(re.sub(r"\{[^}]+\}", "x1", probe)):
                unredacted.append(path)
    assert not unredacted, f"free-text path parameters reach the access log: {unredacted}"


@pytest.mark.parametrize("level", ["TRACE", "SUCCESS"])
def test_loguru_only_log_levels_do_not_break_startup(monkeypatch, level):
    from loguru import logger

    from thoughtpins.config import Config, config
    from thoughtpins.logging_config import setup_logging

    monkeypatch.setattr(config, "LOG_LEVEL", level)
    monkeypatch.setattr(Config, "LOG_LEVEL", level)
    restore = _snapshot_standard_logging()
    try:
        setup_logging()
    finally:
        logger.remove()
        logger.configure(patcher=lambda record: None)
        restore()


def test_the_patcher_never_raises_out_of_a_logging_call(monkeypatch):
    """Loguru does not guard patchers; a failure would escape the caller's except block."""
    from loguru import logger

    from thoughtpins import log_redaction

    def broken(*args, **kwargs):
        raise TypeError("stand-in construction failed")

    monkeypatch.setattr(log_redaction, "_stand_in", broken)
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), backtrace=False, diagnose=False)
    try:
        try:
            raise RuntimeError(CRASH_SENTINEL)
        except RuntimeError:
            logger.patch(log_redaction.withhold_exception_messages).exception("Still logged")
    finally:
        logger.remove(sink)

    rendered = "\n".join(lines)
    assert "Still logged" in rendered and log_redaction.WITHHELD in rendered
    assert CRASH_SENTINEL not in rendered


def test_group_and_plain_stand_ins_of_one_class_do_not_collide():
    from thoughtpins.log_redaction import _stand_in_type

    group = _stand_in_type(ExceptionGroup, group=True)
    plain = _stand_in_type(ExceptionGroup, group=False)

    assert group is not plain
    plain()  # constructible without arguments, unlike a group
    group("withheld", [ValueError()])


def _logged_stand_ins(error: BaseException, *, times: int = 1, patches: int = 1) -> list[BaseException]:
    """What the patcher hands every sink, Sentry's among them, for each logging of *error*."""
    from loguru import logger

    from thoughtpins.log_redaction import withhold_exception_messages

    patched = logger
    for _ in range(patches):
        patched = patched.patch(withhold_exception_messages)
    stand_ins: list[BaseException] = []

    def keep(message: Any) -> None:
        exception = message.record["exception"]
        assert exception is not None and exception.value is not None
        stand_ins.append(exception.value)

    sink = logger.add(keep, catch=False)
    try:
        for _ in range(times):
            patched.opt(exception=error).error("Request failed")
    finally:
        logger.remove(sink)
    return stand_ins


def _sentry_event() -> dict:
    return {"exception": {"values": [{"type": "RuntimeError", "value": "x"}]}}


def test_sentry_reports_one_failure_once_however_many_paths_log_it():
    """The handler's logger.exception(), Starlette and uvicorn's re-log all report one 500."""
    from thoughtpins.logging_config import _scrub_sentry_event

    try:
        raise RuntimeError("request failed")
    except RuntimeError as error:
        original = error
    handler_log, uvicorn_log = _logged_stand_ins(original, times=2)
    assert original is not handler_log is not uvicorn_log

    assert _scrub_sentry_event(_sentry_event(), {"exc_info": (RuntimeError, handler_log, None)}) is not None
    assert _scrub_sentry_event(_sentry_event(), {"exc_info": (RuntimeError, original, None)}) is None
    assert _scrub_sentry_event(_sentry_event(), {"exc_info": (RuntimeError, uvicorn_log, None)}) is None
    try:
        raise RuntimeError("a different failure")
    except RuntimeError as other:
        assert _scrub_sentry_event(_sentry_event(), {"exc_info": (RuntimeError, other, None)}) is not None


def test_a_stand_in_leads_back_to_its_original_even_when_patched_twice():
    from thoughtpins.log_redaction import original_exception

    error = ValueError("built-in exceptions cannot be weakly referenced")

    (stand_in,) = _logged_stand_ins(error, patches=2)

    assert stand_in is not error
    assert original_exception(stand_in) is error
    assert original_exception(error) is error


def test_an_exception_that_takes_no_mark_is_reported_every_time():
    """Never a lost report: when the mark cannot be set, duplicates go through."""
    from thoughtpins.logging_config import _scrub_sentry_event

    class Frozen(Exception):
        def __setattr__(self, name: str, value: object) -> None:
            raise AttributeError(name)

    error = Frozen()
    assert _scrub_sentry_event(_sentry_event(), {"exc_info": (Frozen, error, None)}) is not None
    assert _scrub_sentry_event(_sentry_event(), {"exc_info": (Frozen, error, None)}) is not None


def test_the_web_proxy_is_started_without_uvicorns_logging_config(monkeypatch):
    import uvicorn

    from thoughtpins import web_proxy

    captured: dict = {}
    monkeypatch.setattr(web_proxy, "setup_logging", lambda: None)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    web_proxy.main()

    assert "log_config" in captured and captured["log_config"] is None
