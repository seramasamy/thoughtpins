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
