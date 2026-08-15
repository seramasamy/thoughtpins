"""The bounded full-context builder must be indistinguishable from measuring the whole thing.

`build_smart_memory_context_package` used to build the entire journal on every
message and then discard it whenever it was too large to inline. The bounded
builder stops early instead, which is only safe if it returns exactly what the
old code would have produced:

    build_full_context_within(max_chars=n) == build_full_context()  if len <= n
                                           == None                  otherwise

These tests assert that identity at every boundary, including the off-by-one on
each side, because the failure mode is silent: a wrong limit does not raise, it
quietly swaps a full journal for a sliced one or the reverse.
"""

from __future__ import annotations

from datetime import date

import pytest

from thoughtpins.db import DocumentSource, Memory, RawEntry
from thoughtpins.memory.full_context import build_full_context, build_full_context_within
from thoughtpins.store import get_session
from thoughtpins.users import get_or_create_user_for_telegram
from thoughtpins.utils import hash_text


def _seed(session, chat_id: str, *, entries: int = 6):
    user = get_or_create_user_for_telegram(chat_id, session=session)
    for index in range(entries):
        text = f"entry {index} about the harbour project and the rain in Lisbon"
        entry = RawEntry(
            user_id=user.id,
            raw_text=text,
            content_hash=hash_text(f"{chat_id}-{index}"),
            local_date=date(2026, 7, 21),
            local_time="12:00",
            source="app",
            is_private=False,
            processed_status="completed",
        )
        session.add(entry)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=entry.id,
                memory_type="user_action",
                text=f"User noted detail {index} about the harbour project.",
                local_date=date(2026, 7, 21),
            )
        )
        session.add(
            DocumentSource(
                user_id=user.id,
                raw_entry_id=entry.id,
                source_type="article",
                title=f"Saved reading {index}",
                content_hash=hash_text(f"{chat_id}-doc-{index}"),
                raw_text=f"Body for saved reading {index}",
                local_date=date(2026, 7, 21),
                status="processed",
            )
        )
    session.commit()
    return user


def test_bounded_builder_matches_the_unbounded_one_at_every_boundary(isolated_db):
    session = get_session()
    try:
        user = _seed(session, "bounded-context-boundary")
        full = build_full_context(session, include_private=False, user_id=user.id)
        exact = len(full)
        assert exact > 0, "fixture produced no context, so the comparison proves nothing"

        def bounded(limit):
            return build_full_context_within(session, include_private=False, user_id=user.id, max_chars=limit)

        # At and above the true length, the bounded builder must return the
        # identical string the old code would have inlined.
        assert bounded(exact) == full
        assert bounded(exact + 1) == full
        assert bounded(exact * 4) == full

        # One character short is the case the old code sent down the sliced
        # branch, so the bounded builder has to decline.
        assert bounded(exact - 1) is None
        assert bounded(0) is None
    finally:
        session.close()


@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75, 0.99, 1.0, 1.5])
def test_bounded_builder_agrees_with_the_length_test_it_replaced(isolated_db, fraction):
    """Sweep the limit and compare against the exact predicate from the old code."""
    session = get_session()
    try:
        user = _seed(session, f"bounded-context-sweep-{fraction}")
        full = build_full_context(session, include_private=False, user_id=user.id)
        limit = int(len(full) * fraction)

        bounded = build_full_context_within(session, include_private=False, user_id=user.id, max_chars=limit)
        would_have_inlined = len(full) <= limit

        assert (bounded is not None) is would_have_inlined
        if would_have_inlined:
            assert bounded == full
    finally:
        session.close()


def test_bounded_builder_respects_the_private_scope(isolated_db):
    """A cheaper builder must not become a way around the privacy filter."""
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("bounded-context-privacy", session=session)
        for is_private, text in ((False, "public harbour note"), (True, "private harbour note")):
            entry = RawEntry(
                user_id=user.id,
                raw_text=text,
                content_hash=hash_text(text),
                local_date=date(2026, 7, 21),
                local_time="12:00",
                source="app",
                is_private=is_private,
                processed_status="completed",
            )
            session.add(entry)
        session.commit()

        standard = build_full_context_within(session, include_private=False, user_id=user.id, max_chars=1_000_000)
        disclosure = build_full_context_within(session, include_private=True, user_id=user.id, max_chars=1_000_000)

        assert standard is not None and disclosure is not None
        assert "public harbour note" in standard
        assert "private harbour note" not in standard
        assert "private harbour note" in disclosure
    finally:
        session.close()


def test_empty_corpus_is_inlined_rather_than_declined(isolated_db):
    """An empty journal joins to "", which fits any limit including zero."""
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("bounded-context-empty", session=session)
        full = build_full_context(session, include_private=False, user_id=user.id)
        bounded = build_full_context_within(session, include_private=False, user_id=user.id, max_chars=len(full))
        assert bounded == full
    finally:
        session.close()
