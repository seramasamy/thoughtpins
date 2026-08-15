"""Assembling context must not cost a query per memory.

Every rendered memory line reads `subject_entity`, `object_entity` and
`raw_entry`. Left lazy those are one SELECT each, so context assembly cost one
query per memory — on every message that built context, forever, growing with
the journal. A 400-memory fixture spent 411 queries here.

The defect is invisible from output: the text is identical either way, only
slower. So these assert the shape of the cost rather than the text. Each test
grows one dimension while holding the others fixed, because a test that grows
everything at once cannot say which relationship regressed.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import event

from thoughtpins.db import Entity, Event, EventParticipant, Memory, RawEntry
from thoughtpins.memory.full_context import build_full_context
from thoughtpins.store import get_engine, get_session
from thoughtpins.users import get_or_create_user_for_telegram
from thoughtpins.utils import hash_text


def _seed(session, user_id: str, *, count: int, tag: str, with_events: bool = True) -> None:
    person = Entity(user_id=user_id, type="person", canonical_name=f"Person {tag}")
    place = Entity(user_id=user_id, type="place", canonical_name=f"Place {tag}")
    session.add_all([person, place])
    session.flush()
    for index in range(count):
        entry = RawEntry(
            user_id=user_id,
            raw_text=f"{tag} entry {index}",
            content_hash=hash_text(f"{tag}-{index}"),
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
                user_id=user_id,
                raw_entry_id=entry.id,
                memory_type="user_action",
                text=f"{tag} memory {index}",
                subject_entity_id=person.id,
                local_date=date(2026, 7, 21),
            )
        )
        if with_events:
            happening = Event(
                user_id=user_id,
                name=f"{tag} event {index}",
                event_type="social",
                local_date=date(2026, 7, 21),
                place_entity_id=place.id,
                source_raw_entry_id=entry.id,
            )
            session.add(happening)
            session.flush()
            for role in ("attendee", "host"):
                session.add(
                    EventParticipant(
                        user_id=user_id,
                        event_id=happening.id,
                        entity_id=person.id,
                        role=role,
                    )
                )
    session.commit()


def _queries_to_build(session, user_id: str) -> int:
    counter = {"n": 0}
    engine = get_engine()

    def _count(*_args, **_kwargs) -> None:
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        build_full_context(session, include_private=False, user_id=user_id)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return counter["n"]


def test_memories_do_not_each_cost_a_query(isolated_db):
    """Hold events fixed and triple the memories: the count must not follow."""
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("query-cost-memories", session=session)

        _seed(session, user.id, count=5, tag="base", with_events=True)
        baseline = _queries_to_build(session, user.id)

        _seed(session, user.id, count=40, tag="more", with_events=False)
        grown = _queries_to_build(session, user.id)

        assert grown - baseline <= 4, (
            f"adding 40 memories cost {grown - baseline} extra queries ({baseline} -> {grown}). "
            "A lazy relationship on Memory is being read once per row."
        )
    finally:
        session.close()


def test_event_participants_do_not_each_cost_a_query(isolated_db):
    """Participants per event are batched, so widening an event stays flat.

    Events themselves still cost a fixed couple of queries each; that is
    recorded in the register. What must not happen is a query per participant.
    """
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("query-cost-participants", session=session)
        _seed(session, user.id, count=5, tag="base", with_events=True)
        before = _queries_to_build(session, user.id)

        extra = Entity(user_id=user.id, type="person", canonical_name="Extra Guest")
        session.add(extra)
        session.flush()
        for happening in session.query(Event).all():
            for role in ("guest", "organiser", "speaker"):
                session.add(EventParticipant(user_id=user.id, event_id=happening.id, entity_id=extra.id, role=role))
        session.commit()

        after = _queries_to_build(session, user.id)
        assert after - before <= 2, (
            f"adding 15 participants cost {after - before} extra queries ({before} -> {after}). "
            "Participant entities are being resolved one at a time."
        )
    finally:
        session.close()
