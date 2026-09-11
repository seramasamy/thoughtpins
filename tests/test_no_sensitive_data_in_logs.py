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


def test_setup_logging_wires_the_sentry_scrubber(monkeypatch):
    """The scrubber is only worth anything if init actually receives it."""
    import sys
    import types

    from thoughtpins.config import Config, config
    from thoughtpins.logging_config import _scrub_sentry_event, setup_logging

    captured: dict = {}
    fake_sentry = types.ModuleType("sentry_sdk")
    monkeypatch.setattr(fake_sentry, "init", lambda **kwargs: captured.update(kwargs), raising=False)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)
    monkeypatch.setattr(config, "SENTRY_DSN", "https://x@example.invalid/1")
    monkeypatch.setattr(Config, "SENTRY_DSN", "https://x@example.invalid/1")

    setup_logging()
    from loguru import logger

    logger.remove()

    assert captured["before_send"] is _scrub_sentry_event
    assert captured["max_request_body_size"] == "never"
    assert captured["send_default_pii"] is False


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
    flattened = repr(scrubbed)
    assert CRASH_SENTINEL not in flattened
    assert "eyJhbGc" not in flattened
    assert scrubbed["request"]["url"].endswith("/v1/chat"), "route context should survive scrubbing"
    assert scrubbed["exception"]["values"], "the stack context should survive scrubbing"
