"""Properties hybrid retrieval has to hold regardless of which channel breaks.

A hybrid retriever earns its name by losing a channel gracefully. These tests
assert the three things that were previously untrue: the session is released on
every path, one failing provider costs recall rather than the whole query, and
candidate identities are reproducible across processes.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from thoughtpins.memory import search as search_module
from thoughtpins.memory.search import _stable_key, search


class RecordingSession:
    """A stand-in that reports whether it was closed."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def owned_session(monkeypatch) -> RecordingSession:
    """Make `search` open its own session so ownership is under test."""
    session = RecordingSession()
    monkeypatch.setattr(search_module, "get_session", lambda: session)
    monkeypatch.setattr(search_module, "_attach_user_importance", lambda *a, **k: None)
    monkeypatch.setattr(search_module, "rerank_results", lambda candidates, **k: list(candidates))
    return session


def _break_every_channel(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("provider down")

    for name in (
        "_memory_query",
        "_token_search_memories",
        "_graph_memory_expansion",
        "_document_title_search",
        "_raw_entry_search",
        "graph_search_hits",
        "get_vector_store",
    ):
        monkeypatch.setattr(search_module, name, explode)


# ------------------------------------------------------------------- ownership


def test_a_session_this_call_opened_is_closed(owned_session, monkeypatch):
    _break_every_channel(monkeypatch)
    search("anything")
    assert owned_session.closed


def test_the_session_is_closed_even_when_a_channel_raises(owned_session, monkeypatch):
    """The original code closed on the success path only, so a raising channel
    leaked the connection — under load, the pool."""
    _break_every_channel(monkeypatch)

    def explode_late(*args, **kwargs):
        raise RuntimeError("ranking blew up")

    monkeypatch.setattr(search_module, "rerank_results", explode_late)

    with pytest.raises(RuntimeError):
        search("anything")
    assert owned_session.closed, "session leaked when ranking raised"


def test_a_caller_supplied_session_is_left_open(monkeypatch):
    """Closing a session we were handed would break the caller's transaction."""
    caller_session = RecordingSession()
    monkeypatch.setattr(search_module, "_attach_user_importance", lambda *a, **k: None)
    monkeypatch.setattr(search_module, "rerank_results", lambda candidates, **k: list(candidates))
    _break_every_channel(monkeypatch)

    search("anything", session=caller_session)
    assert not caller_session.closed


# ----------------------------------------------------------------- degradation


def test_every_channel_failing_still_returns_an_answer(owned_session, monkeypatch):
    """Fewer candidates is a worse answer. Raising is no answer at all."""
    _break_every_channel(monkeypatch)
    assert search("what did I decide") == []


def test_one_failing_channel_does_not_hide_the_others(owned_session, monkeypatch):
    """Only the vector channel used to be guarded; the rest took the query down."""
    from thoughtpins.memory.search_types import SearchResult

    survivor = SearchResult(
        memory_id="m1",
        text="the copper lantern",
        memory_type="event",
        local_date="2026-01-01",
        confidence="observed_by_user",
        sensitivity="personal",
        source_entry_id="e1",
        score=0.5,
    )

    _break_every_channel(monkeypatch)
    monkeypatch.setattr(
        search_module,
        "_token_search_memories",
        lambda *a, **k: [(type("M", (), {"id": "m1"})(), 0.5)],
    )
    monkeypatch.setattr(search_module, "_mem_to_result", lambda *a, **k: survivor)

    results = search("lantern")
    assert [r.memory_id for r in results] == ["m1"]


# ---------------------------------------------------------------- determinism


def test_a_candidate_key_is_stable_within_a_process():
    assert _stable_key("graph", "Maya mentioned the festival") == _stable_key("graph", "Maya mentioned the festival")


def test_different_text_gets_a_different_key():
    assert _stable_key("graph", "Maya") != _stable_key("graph", "Nora")


def test_a_candidate_key_is_stable_across_processes():
    """The reason this exists: str hashing is salted per interpreter, so the
    previous key gave graph evidence one identity in the API and another in the
    worker. Two fresh interpreters must agree."""
    program = (
        "import sys; sys.path.insert(0, 'src');"
        "from thoughtpins.memory.search import _stable_key;"
        "print(_stable_key('graph', 'Maya mentioned the festival'))"
    )
    seen = {
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(3)
    }
    assert len(seen) == 1, f"candidate identity differed across processes: {seen}"


def test_the_builtin_hash_this_replaced_really_is_unstable():
    """Guards the premise. If CPython ever made str hashing stable by default
    this test fails and the fix above can be revisited rather than cargo-culted."""
    program = "print(hash('Maya mentioned the festival'))"
    seen = {
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(5)
    }
    assert len(seen) > 1, "str hashing appears stable; revisit _stable_key's rationale"
