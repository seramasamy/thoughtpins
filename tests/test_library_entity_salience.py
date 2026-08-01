"""Entities a saved source introduces have to be ranked like any other.

Importance ordering is what makes recall useful, and it is derived from how
often something appears and how much material sits behind it. An entity that
first appeared in an imported note rather than a typed journal entry is not less
important for that reason.
"""

from __future__ import annotations

from datetime import datetime

from thoughtpins.utils import hash_text


def _library_entry_with_entity(session, user_id: str, *, name: str, memories: int):
    from thoughtpins.db import Entity, EntityMention, Memory, RawEntry

    raw = RawEntry(
        user_id=user_id,
        created_at_utc=datetime(2026, 5, 23, 9, 0),
        local_date=datetime(2026, 5, 23).date(),
        local_time="09:00",
        source="library_doc",
        raw_text=f"A saved source that talks at length about {name}.",
        content_hash=hash_text(f"library salience {name}"),
        processed_status="completed",
    )
    session.add(raw)
    session.flush()
    entity = Entity(user_id=user_id, type="person", canonical_name=name)
    session.add(entity)
    session.flush()
    session.add(EntityMention(user_id=user_id, raw_entry_id=raw.id, entity_id=entity.id, surface_text=name))
    for index in range(memories):
        session.add(
            Memory(
                user_id=user_id,
                raw_entry_id=raw.id,
                memory_type="fact",
                subject_entity_id=entity.id,
                text=f"{name} fact {index}",
                local_date=raw.local_date,
                created_at_utc=raw.created_at_utc,
            )
        )
    session.commit()
    return raw, entity


def test_saved_source_entities_are_scored_not_left_at_zero(isolated_db):
    from thoughtpins.library import _refresh_document_entity_salience
    from thoughtpins.store import get_session
    from thoughtpins.tenancy import tenant_context
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw, entity = _library_entry_with_entity(session, user.id, name="Maya Okonkwo", memories=4)
        assert entity.salience_score in (None, 0.0)

        with tenant_context(user.id):
            _refresh_document_entity_salience(session, raw)
            session.commit()

        session.refresh(entity)
        assert entity.salience_score is not None
        assert entity.salience_score > 0.0
    finally:
        session.close()


def test_recurring_across_sources_ranks_higher_than_a_single_appearance(isolated_db):
    """Presence across separate sources is what lifts an entity's rank.

    Note the model deliberately does not treat raw memory count as importance:
    it weighs how many distinct entries an entity recurs in, how densely it is
    mentioned, and how central it is to those memories. Two entities each named
    once, with one carrying more bullet points, score the same on purpose.
    """
    from thoughtpins.db import EntityMention, Memory, RawEntry
    from thoughtpins.library import _refresh_document_entity_salience
    from thoughtpins.store import get_session
    from thoughtpins.tenancy import tenant_context
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        first_raw, recurring = _library_entry_with_entity(session, user.id, name="Recurring Person", memories=2)
        once_raw, once = _library_entry_with_entity(session, user.id, name="Mentioned Once", memories=2)

        # A second saved source that names the recurring person again.
        second = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 6, 2, 9, 0),
            local_date=datetime(2026, 6, 2).date(),
            local_time="09:00",
            source="library_doc",
            raw_text="Another saved source about Recurring Person.",
            content_hash=hash_text("library salience second source"),
            processed_status="completed",
        )
        session.add(second)
        session.flush()
        session.add(
            EntityMention(
                user_id=user.id,
                raw_entry_id=second.id,
                entity_id=recurring.id,
                surface_text="Recurring Person",
            )
        )
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=second.id,
                memory_type="fact",
                subject_entity_id=recurring.id,
                text="Recurring Person came up again in a different source.",
                local_date=second.local_date,
                created_at_utc=second.created_at_utc,
            )
        )
        session.commit()

        with tenant_context(user.id):
            _refresh_document_entity_salience(session, first_raw)
            _refresh_document_entity_salience(session, second)
            _refresh_document_entity_salience(session, once_raw)
            session.commit()

        session.refresh(recurring)
        session.refresh(once)
        assert (recurring.salience_score or 0.0) > (once.salience_score or 0.0)
    finally:
        session.close()


def test_salience_failure_never_breaks_saving_a_source(isolated_db, monkeypatch):
    """Ranking is derived; the saved source is the record that must survive."""
    from thoughtpins import library
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw, _ = _library_entry_with_entity(session, user.id, name="Fragile Case", memories=1)

        def explode(*args, **kwargs):
            raise RuntimeError("scoring backend is down")

        monkeypatch.setattr("thoughtpins.memory.salience_store.refresh_entity_salience", explode)
        library._refresh_document_entity_salience(session, raw)
    finally:
        session.close()


def test_short_notes_still_reach_the_graph(isolated_db):
    """A person note in a real vault is a few hundred characters, not five."""
    from thoughtpins.config import Config

    assert Config.LIBRARY_GRAPH_MIN_TEXT_CHARS < Config.ARTICLE_MIN_TEXT_CHARS
    assert Config.LIBRARY_GRAPH_MIN_TEXT_CHARS <= 120
