"""Tenant-scoped creation and removal of the fictional local demo corpus."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from thoughtpins.crypto import encrypt_for_storage
from thoughtpins.db import (
    ActionItem,
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    DocumentSource,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    Memory,
    RawEntry,
    Relationship,
)
from thoughtpins.demo.corpus import (
    BOOK_TEXT,
    CHAT_ASSISTANT_TEXT,
    CHAT_USER_TEXT,
    ENTITY_NAMES,
    ENTITY_SPECS,
    JOURNAL_FIXTURES,
    MARKER,
    OBSIDIAN_TEXT,
    SATIRE_TEXT,
    SOURCE_TITLES,
    JournalFixture,
)
from thoughtpins.library import flush_document_indexing, ingest_document_text
from thoughtpins.memory.salience import EntrySalienceObservation, score_entry_salience
from thoughtpins.memory.salience_store import refresh_entity_salience
from thoughtpins.utils import hash_text


def clear_demo_corpus(session: Session, user_id: str) -> int:
    """Remove only rows owned by the fictional fixture."""

    raw_ids = [
        row.id
        for row in session.query(RawEntry.id)
        .filter(RawEntry.user_id == user_id, RawEntry.source == "demo_corpus")
        .all()
    ]
    doc_ids = [
        row.id
        for row in session.query(DocumentSource.id)
        .filter(DocumentSource.user_id == user_id, DocumentSource.title.in_(SOURCE_TITLES))
        .all()
    ]
    document_raw_ids = [
        row.raw_entry_id
        for row in session.query(DocumentSource.raw_entry_id)
        .filter(DocumentSource.user_id == user_id, DocumentSource.id.in_(doc_ids or ["__none__"]))
        .all()
    ]
    all_raw_ids = raw_ids + document_raw_ids
    entity_ids = [
        row.id
        for row in session.query(Entity.id)
        .filter(Entity.user_id == user_id, Entity.canonical_name.in_(ENTITY_NAMES))
        .all()
    ]
    event_ids = [
        row.id
        for row in session.query(Event.id)
        .filter(Event.user_id == user_id, Event.source_raw_entry_id.in_(raw_ids or ["__none__"]))
        .all()
    ]
    provenance = [f"raw_entry:{raw_id}" for raw_id in all_raw_ids]
    provenance.extend(f"document:{doc_id}" for doc_id in doc_ids)

    deleted = 0
    delete_specs = (
        (EventParticipant, EventParticipant.event_id.in_(event_ids or ["__none__"])),
        (
            EntityMention,
            or_(
                EntityMention.raw_entry_id.in_(all_raw_ids or ["__none__"]),
                EntityMention.entity_id.in_(entity_ids or ["__none__"]),
            ),
        ),
        (ActionItem, ActionItem.raw_entry_id.in_(all_raw_ids or ["__none__"])),
        (Expense, Expense.raw_entry_id.in_(all_raw_ids or ["__none__"])),
        (
            Relationship,
            or_(
                Relationship.raw_entry_id.in_(all_raw_ids or ["__none__"]),
                Relationship.source_entity_id.in_(entity_ids or ["__none__"]),
                Relationship.target_entity_id.in_(entity_ids or ["__none__"]),
            ),
        ),
        (
            Memory,
            or_(
                Memory.raw_entry_id.in_(all_raw_ids or ["__none__"]),
                Memory.source_provenance.in_(provenance or ["__none__"]),
            ),
        ),
        (DocumentChunk, DocumentChunk.document_id.in_(doc_ids or ["__none__"])),
        (DocumentSource, DocumentSource.id.in_(doc_ids or ["__none__"])),
        (Event, Event.id.in_(event_ids or ["__none__"])),
        (RawEntry, RawEntry.id.in_(all_raw_ids or ["__none__"])),
        (Entity, Entity.id.in_(entity_ids or ["__none__"])),
        (ChatMessage, ChatMessage.text.in_((CHAT_USER_TEXT, CHAT_ASSISTANT_TEXT))),
    )
    for model, condition in delete_specs:
        deleted += session.query(model).filter(condition).delete(synchronize_session=False)
    session.commit()
    return deleted


def seed_demo_corpus(session: Session, user_id: str, *, as_of: date | None = None) -> dict[str, Any]:
    """Create a natural one-week timeline with explicit provenance and stars."""

    reference_day = as_of or datetime.now(timezone.utc).date()
    entries = [_create_journal_entry(session, user_id, fixture, reference_day) for fixture in JOURNAL_FIXTURES]
    session.flush()
    entries_by_key = {fixture.key: entry for fixture, entry in zip(JOURNAL_FIXTURES, entries, strict=True)}

    entities = _create_entities(session, user_id)
    session.flush()
    _create_mentions(session, user_id, entries_by_key, entities)
    _create_memories(session, user_id, reference_day, entries_by_key, entities)
    _create_relationships(session, user_id, entries_by_key, entities)
    _create_events_actions_and_expense(session, user_id, reference_day, entries_by_key, entities)
    session.commit()

    documents = _create_documents(session, user_id, reference_day)
    indexing_flushed = flush_document_indexing(timeout_seconds=30.0)
    _create_chat_sample(session, user_id)
    refresh_entity_salience(session, user_id=user_id)
    session.commit()

    return {
        "entries": len(entries) + len(documents),
        "journal_entries": len(entries),
        "documents": len(documents),
        "document_ids": [document.document_id for document in documents],
        "document_indexing_flushed": indexing_flushed,
        "memories": session.query(Memory).filter(Memory.user_id == user_id).count(),
        "entities": len(entities),
        "private_entries": sum(1 for entry in entries if entry.is_private),
        "rated_entries": sum(1 for entry in entries if entry.user_importance is not None),
        "timeline_start": min(entry.local_date for entry in entries).isoformat(),
        "timeline_end": max(entry.local_date for entry in entries).isoformat(),
        "chat_seeded": True,
    }


def _create_journal_entry(
    session: Session,
    user_id: str,
    fixture: JournalFixture,
    reference_day: date,
) -> RawEntry:
    local_day = reference_day - timedelta(days=fixture.days_ago)
    hour, minute = (int(part) for part in fixture.local_time.split(":"))
    created = datetime.combine(local_day, datetime.min.time()).replace(hour=hour, minute=minute)
    stored_text = encrypt_for_storage(fixture.text) if fixture.is_private else fixture.text
    if fixture.is_private and not stored_text:
        stored_text = fixture.text
    score = score_entry_salience(
        EntrySalienceObservation(
            word_count=len(fixture.text.split()),
            entity_count=len(fixture.entity_keys),
            person_count=1 if "maya" in fixture.entity_keys else 0,
            topic_count=max(1, min(3, len(fixture.entity_keys))),
            memory_count=0 if fixture.is_private else 1,
            relationship_count=fixture.relationship_count,
            event_count=fixture.event_count,
            action_count=fixture.action_count,
            decision_count=fixture.decision_count,
            user_importance=fixture.importance,
            source_kind="journal",
        )
    )
    entry = RawEntry(
        user_id=user_id,
        created_at_utc=created,
        local_date=local_day,
        local_time=fixture.local_time,
        source="demo_corpus",
        raw_text=stored_text,
        content_hash=hash_text(f"{MARKER}:{user_id}:{fixture.key}:{fixture.text}"),
        is_private=fixture.is_private,
        sensitivity="private" if fixture.is_private else "personal",
        processed_status="completed",
        user_importance=fixture.importance,
        importance_source="demo_fixture",
        importance_updated_at=created,
        contextual_salience=score.score,
        salience_uncertainty=score.uncertainty,
        salience_model_version=score.model_version,
        salience_updated_at=created,
        analysis_json={
            "analysis_version": 1,
            "fixture_key": fixture.key,
            "source_kind": "journal",
            "salience": score.as_dict(),
        },
    )
    session.add(entry)
    return entry


def _create_entities(session: Session, user_id: str) -> dict[str, Entity]:
    entities = {
        key: Entity(
            user_id=user_id,
            type=entity_type,
            canonical_name=name,
            aliases_json=list(aliases),
            notes=notes,
            attributes_json=[],
        )
        for key, (entity_type, name, aliases, notes) in ENTITY_SPECS.items()
    }
    session.add_all(entities.values())
    return entities


def _create_mentions(
    session: Session,
    user_id: str,
    entries: dict[str, RawEntry],
    entities: dict[str, Entity],
) -> None:
    fixtures = {fixture.key: fixture for fixture in JOURNAL_FIXTURES}
    mentions = []
    for key, entry in entries.items():
        for entity_key in fixtures[key].entity_keys:
            mentions.append(
                EntityMention(
                    user_id=user_id,
                    raw_entry_id=entry.id,
                    entity_id=entities[entity_key].id,
                    surface_text=entities[entity_key].canonical_name,
                )
            )
    session.add_all(mentions)


def _create_memories(
    session: Session,
    user_id: str,
    reference_day: date,
    entries: dict[str, RawEntry],
    entities: dict[str, Entity],
) -> None:
    memory_specs = (
        (
            "weekly_intention",
            "deliberate_pace",
            None,
            "The user protected the first morning hour for quiet work and planned a short walk after lunch.",
        ),
        (
            "coffee_chat",
            "maya",
            "ceramic_swallow",
            "Maya Arlen recommended testing Quiet Systems with five people; the blue ceramic swallow marked Atlas Cafe.",
        ),
        (
            "recipe_note",
            "lemon_miso_pasta",
            None,
            "For lemon-miso pasta, add lemon juice off heat so the flavor stays bright.",
        ),
        (
            "reading_reflection",
            "sherlock_thread",
            "evidence_bridges",
            "The Sherlock reading prompted a model of memory where bridge facts make small clues relevant later.",
        ),
        (
            "product_decision",
            "quiet_systems",
            "deliberate_pace",
            "Quiet Systems should keep conversation as the front door and reveal structure only when useful.",
        ),
        (
            "river_walk",
            "riverfront_loop",
            "maya",
            "During a Riverfront Loop walk, the user returned to Maya's advice about smaller tests and prioritized sending the prototype.",
        ),
    )
    fixtures = {fixture.key: fixture for fixture in JOURNAL_FIXTURES}
    memories = []
    for entry_key, subject_key, object_key, text in memory_specs:
        fixture = fixtures[entry_key]
        entry = entries[entry_key]
        memories.append(
            Memory(
                user_id=user_id,
                raw_entry_id=entry.id,
                memory_type=fixture.memory_type,
                subject_entity_id=entities[subject_key].id,
                object_entity_id=entities[object_key].id if object_key else None,
                predicate=fixture.predicate,
                text=text,
                structured_json={"fixture": MARKER, "source_kind": "journal"},
                occurred_at_start=entry.created_at_utc,
                local_date=reference_day - timedelta(days=fixture.days_ago),
                sensitivity="personal",
                confidence="observed_by_user",
                source_provenance=f"raw_entry:{entry.id}",
                created_at_utc=entry.created_at_utc,
            )
        )
    session.add_all(memories)


def _create_relationships(
    session: Session,
    user_id: str,
    entries: dict[str, RawEntry],
    entities: dict[str, Entity],
) -> None:
    coffee = entries["coffee_chat"]
    river = entries["river_walk"]
    session.add_all(
        (
            Relationship(
                user_id=user_id,
                source_entity_id=entities["maya"].id,
                target_entity_id=entities["atlas_cafe"].id,
                relation_type="met_at",
                raw_entry_id=coffee.id,
                weight=2.0,
                confidence="observed_by_user",
                first_seen_at=coffee.created_at_utc,
                last_seen_at=coffee.created_at_utc,
                evidence_count=1,
            ),
            Relationship(
                user_id=user_id,
                source_entity_id=entities["maya"].id,
                target_entity_id=entities["quiet_systems"].id,
                relation_type="advised_on",
                raw_entry_id=coffee.id,
                weight=2.5,
                confidence="observed_by_user",
                first_seen_at=coffee.created_at_utc,
                last_seen_at=river.created_at_utc,
                evidence_count=2,
            ),
            Relationship(
                user_id=user_id,
                source_entity_id=entities["quiet_systems"].id,
                target_entity_id=entities["deliberate_pace"].id,
                relation_type="guided_by",
                raw_entry_id=entries["product_decision"].id,
                weight=2.5,
                confidence="observed_by_user",
                first_seen_at=entries["product_decision"].created_at_utc,
                last_seen_at=entries["product_decision"].created_at_utc,
                evidence_count=1,
            ),
            Relationship(
                user_id=user_id,
                source_entity_id=entities["sherlock_thread"].id,
                target_entity_id=entities["evidence_bridges"].id,
                relation_type="inspired",
                raw_entry_id=entries["reading_reflection"].id,
                weight=2.0,
                confidence="observed_by_user",
                first_seen_at=entries["reading_reflection"].created_at_utc,
                last_seen_at=entries["reading_reflection"].created_at_utc,
                evidence_count=1,
            ),
        )
    )


def _create_events_actions_and_expense(
    session: Session,
    user_id: str,
    reference_day: date,
    entries: dict[str, RawEntry],
    entities: dict[str, Entity],
) -> None:
    coffee_entry = entries["coffee_chat"]
    coffee_event = Event(
        user_id=user_id,
        name="Coffee with Maya Arlen",
        event_type="coffee_chat",
        start_at=coffee_entry.created_at_utc,
        local_date=coffee_entry.local_date,
        place_entity_id=entities["atlas_cafe"].id,
        summary="Talked about smaller product tests and agreed to send a revised prototype.",
        source_raw_entry_id=coffee_entry.id,
        sensitivity="personal",
    )
    walk_entry = entries["river_walk"]
    walk_event = Event(
        user_id=user_id,
        name="Riverfront evening walk",
        event_type="walk",
        start_at=walk_entry.created_at_utc,
        local_date=walk_entry.local_date,
        place_entity_id=entities["riverfront_loop"].id,
        summary="Phone-free walk and reflection on smaller tests.",
        source_raw_entry_id=walk_entry.id,
        sensitivity="personal",
    )
    session.add_all((coffee_event, walk_event))
    session.flush()
    session.add(
        EventParticipant(user_id=user_id, event_id=coffee_event.id, entity_id=entities["maya"].id, role="attendee")
    )
    session.add(
        ActionItem(
            user_id=user_id,
            raw_entry_id=walk_entry.id,
            description="Send Maya the revised Quiet Systems prototype",
            due_at=datetime.combine(reference_day + timedelta(days=1), datetime.min.time()).replace(hour=10),
            status="open",
            sensitivity="personal",
        )
    )
    session.add(
        Expense(
            user_id=user_id,
            raw_entry_id=coffee_entry.id,
            amount=8.75,
            currency="USD",
            merchant_or_place_entity_id=entities["atlas_cafe"].id,
            reason="Coffee during conversation with Maya",
            category="food",
            confidence="observed_by_user",
        )
    )


def _create_documents(session: Session, user_id: str, reference_day: date):
    specs = (
        (
            BOOK_TEXT,
            "book",
            SOURCE_TITLES[0],
            "Arthur Conan Doyle",
            "https://www.gutenberg.org/ebooks/244",
            "gutenberg.org",
            "public_domain",
            4,
            4,
        ),
        (
            SATIRE_TEXT,
            "article",
            SOURCE_TITLES[1],
            "Jonathan Swift",
            "https://www.gutenberg.org/ebooks/1080",
            "gutenberg.org",
            "public_domain",
            3,
            3,
        ),
        (
            OBSIDIAN_TEXT,
            "documentation",
            SOURCE_TITLES[2],
            "Thought Pins",
            "https://github.com/obsidianmd",
            "github.com",
            "user_provided",
            3,
            2,
        ),
    )
    results = []
    for text, source_type, title, author, url, domain, rights, importance, days_ago in specs:
        result = ingest_document_text(
            session,
            text,
            user_id=user_id,
            source_type=source_type,
            title=title,
            author=author,
            original_url=url,
            source_url=url,
            canonical_url=url,
            source_domain=domain,
            access_method="public_http",
            rights_basis=rights,
            metadata_json={"fixture": MARKER, "source_kind": "reading"},
            defer_vector_index=True,
            user_importance=importance,
        )
        source_day = reference_day - timedelta(days=days_ago)
        source_time = datetime.combine(source_day, datetime.min.time()).replace(hour=20)
        document = session.get(DocumentSource, result.document_id)
        raw_entry = session.get(RawEntry, result.raw_entry_id)
        if document:
            document.created_at_utc = source_time
            document.local_date = source_day
        if raw_entry:
            raw_entry.created_at_utc = source_time
            raw_entry.local_date = source_day
            raw_entry.local_time = "20:00"
            raw_entry.importance_updated_at = source_time
        session.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.source_provenance == f"document:{result.document_id}",
        ).update({Memory.created_at_utc: source_time, Memory.local_date: source_day}, synchronize_session=False)
        session.commit()
        results.append(result)
    return results


def _create_chat_sample(session: Session, user_id: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conversation = (
        session.query(ChatConversation)
        .filter(ChatConversation.user_id == user_id, ChatConversation.conversation_key == "web:main")
        .first()
    )
    if not conversation:
        conversation = ChatConversation(
            user_id=user_id,
            conversation_key="web:main",
            surface="web",
            title="Memory conversation",
            created_at_utc=now - timedelta(minutes=2),
            metadata_json={"fixture": MARKER},
        )
        session.add(conversation)
        session.flush()
    session.add_all(
        (
            ChatMessage(
                user_id=user_id,
                conversation_id=conversation.id,
                role="user",
                text=CHAT_USER_TEXT,
                route_type="chat",
                status="completed",
                created_at_utc=now - timedelta(minutes=1),
                metadata_json={"fixture": MARKER},
            ),
            ChatMessage(
                user_id=user_id,
                conversation_id=conversation.id,
                role="assistant",
                text=CHAT_ASSISTANT_TEXT,
                route_type="chat",
                status="completed",
                created_at_utc=now,
                metadata_json={"fixture": MARKER, "grounding": "journal"},
            ),
        )
    )
    conversation.updated_at_utc = now
    conversation.last_message_at_utc = now
