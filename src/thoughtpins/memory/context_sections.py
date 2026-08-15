"""Section renderers for exhaustive and navigational memory context."""

from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from thoughtpins.chat.message_memory import is_chat_memory_entry
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import (
    ActionItem,
    DocumentSource,
    Entity,
    Event,
    EventParticipant,
    Expense,
    Memory,
    RawEntry,
    Relationship,
)
from thoughtpins.memory.context_scope import scope_user
from thoughtpins.memory.entity_stats import entity_reference_counts


def _full_section_builders():
    """Resolved at call time so section order stays declarative, not import-ordered."""

    return (
        _full_entity_lines,
        _full_document_lines,
        _full_event_lines,
        _full_memory_lines,
        _full_relationship_lines,
        _full_action_lines,
        _full_expense_lines,
        _full_raw_entry_lines,
    )


def build_full_context_lines(session, *, include_private: bool, user_id: str | None) -> list[str]:
    """Render every exhaustive context section in a stable order."""

    return [
        line for build_section in _full_section_builders() for line in build_section(session, include_private, user_id)
    ]


def build_full_context_lines_within(
    session,
    *,
    include_private: bool,
    user_id: str | None,
    max_chars: int,
) -> list[str] | None:
    """Render the exhaustive sections, or give up as soon as they exceed max_chars.

    The smart package discards this context entirely when it does not fit, so
    building an entire journal in order to measure it is work nobody reads. This
    stops at the first line that pushes the joined length past the limit, which
    also stops the queries the remaining sections would have run. The accounting
    matches `"\\n".join(lines)`: every line after the first costs its separator.
    """

    lines: list[str] = []
    used = 0
    for build_section in _full_section_builders():
        for line in build_section(session, include_private, user_id):
            used += len(line) + (1 if lines else 0)
            if used > max_chars:
                return None
            lines.append(line)
    return lines


def build_navigation_context_lines(session, *, include_private: bool, user_id: str | None) -> list[str]:
    """Render a compact index whose counts obey the same privacy scope as details."""

    entities = _navigation_entities(session, include_private, user_id)
    sections = (
        _navigation_overview_lines(session, entities, include_private, user_id),
        _navigation_entity_lines(session, entities, include_private, user_id),
        _navigation_document_lines(session, include_private, user_id),
        _navigation_event_lines(session, include_private, user_id),
        _navigation_relationship_lines(session, include_private, user_id),
        _navigation_memory_lines(session, include_private, user_id),
        _navigation_action_lines(session, include_private, user_id),
        _navigation_cross_reference_lines(),
    )
    return ["# NAVIGATIONAL MEMORY MAP (compact index)", *[line for section in sections for line in section]]


def _section(heading: str, body: list[str]) -> list[str]:
    return [heading, *body, ""] if body else []


def _public_entity_ids(session, user_id: str | None) -> set[str]:
    public_ids: set[str] = set()
    for column in (Memory.subject_entity_id, Memory.object_entity_id):
        query = (
            session.query(column)
            .join(RawEntry, Memory.raw_entry_id == RawEntry.id)
            .filter(RawEntry.is_private == False)
        )
        query = scope_user(query, Memory, user_id)
        public_ids.update(row[0] for row in query.distinct().all() if row[0])
    user_entity = scope_user(session.query(Entity).filter(Entity.canonical_name == "User"), Entity, user_id).first()
    if user_entity:
        public_ids.add(user_entity.id)
    return public_ids


def _full_entity_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    entities = scope_user(session.query(Entity), Entity, user_id).order_by(Entity.type, Entity.canonical_name).all()
    people = [entity for entity in entities if entity.type == "person"]
    places = [entity for entity in entities if entity.type == "place"]
    if not include_private:
        public_ids = _public_entity_ids(session, user_id)
        people = [entity for entity in people if entity.id in public_ids]
        places = [entity for entity in places if entity.id in public_ids]

    lines: list[str] = []
    people_body: list[str] = []
    for person in people:
        aliases = person.aliases_json or []
        alias_text = f" (aliases: {', '.join(aliases)})" if aliases else ""
        people_body.append(f"- {person.canonical_name}{alias_text}")
        for attribute in person.attributes_json or []:
            people_body.append(
                f"  - {attribute.get('key', '?')}: {attribute.get('value', '?')} [{attribute.get('confidence', '?')}]"
            )
    lines.extend(_section("## PEOPLE", people_body))
    lines.extend(_section("## PLACES", [f"- {place.canonical_name}" for place in places]))
    return lines


def _document_query(session, include_private: bool, user_id: str | None):
    query = scope_user(session.query(DocumentSource), DocumentSource, user_id)
    if not include_private:
        query = query.join(RawEntry, DocumentSource.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _full_document_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    documents = (
        _document_query(session, include_private, user_id)
        .order_by(DocumentSource.created_at_utc.desc())
        .limit(100)
        .all()
    )
    body: list[str] = []
    for document in documents:
        body.append(
            f"- [{document.local_date}] {document.title} ({document.source_type}, {document.status}) id={document.id}"
        )
        if document.source_url:
            body.append(f"  URL: {document.source_url}")
        if document.summary:
            body.append(f"  Summary: {document.summary[:500]}")
    return _section("## READING AND DOCUMENT SOURCES", body)


def _event_query(session, include_private: bool, user_id: str | None):
    query = scope_user(session.query(Event), Event, user_id)
    if not include_private:
        query = query.join(RawEntry, Event.source_raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _event_participant_labels(session, event_id: str, user_id: str | None) -> list[str]:
    participants = (
        scope_user(session.query(EventParticipant), EventParticipant, user_id)
        .filter(EventParticipant.event_id == event_id)
        .all()
    )
    if not participants:
        return []

    # One scoped lookup for the whole event instead of one per participant. The
    # scoping stays: resolving these through the relationship would return an
    # entity belonging to another tenant, where this drops it exactly as the
    # per-participant query did.
    entity_ids = {participant.entity_id for participant in participants if participant.entity_id}
    entities = {
        entity.id: entity
        for entity in scope_user(session.query(Entity), Entity, user_id).filter(Entity.id.in_(entity_ids)).all()
    }

    labels: list[str] = []
    for participant in participants:
        entity = entities.get(participant.entity_id)
        if entity:
            labels.append(f"{entity.canonical_name} ({participant.role})")
    return labels


def _full_event_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    events = (
        _event_query(session, include_private, user_id)
        .options(selectinload(Event.place_entity))
        .order_by(Event.local_date)
        .all()
    )
    body: list[str] = []
    for event in events:
        place_name = event.place_entity.canonical_name if event.place_entity else "unknown location"
        participants = _event_participant_labels(session, event.id, user_id)
        participant_text = ", ".join(participants) if participants else "no participants recorded"
        body.extend(
            [
                f"- [{event.local_date}] {event.name} ({event.event_type})",
                f"  Place: {place_name}",
                f"  Participants: {participant_text}",
            ]
        )
        if event.summary:
            body.append(f"  Summary: {event.summary}")
    return _section("## EVENTS", body)


def _memory_query(session, include_private: bool, user_id: str | None):
    query = scope_user(session.query(Memory), Memory, user_id).filter(Memory.valid_to.is_(None))
    if not include_private:
        query = query.join(RawEntry, Memory.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _full_memory_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    # Every rendered line reads subject_entity, object_entity and raw_entry. Left
    # lazy, that is one SELECT per memory: a 400-memory journal spent 400 queries
    # here on every message that assembled context. Loading them up front makes
    # the section a fixed handful of queries regardless of journal size.
    memories = (
        _memory_query(session, include_private, user_id)
        .options(
            selectinload(Memory.subject_entity),
            selectinload(Memory.object_entity),
            selectinload(Memory.raw_entry),
        )
        .order_by(Memory.local_date)
        .all()
    )
    body: list[str] = []
    for memory in memories:
        parts = [f"[{memory.local_date}] [{memory.memory_type}]"]
        if memory.subject_entity:
            parts.append(f"subject={memory.subject_entity.canonical_name}")
        if memory.predicate:
            parts.append(f"predicate={memory.predicate}")
        if memory.object_entity:
            parts.append(f"object={memory.object_entity.canonical_name}")
        parts.extend(
            [
                f"sensitivity={memory.sensitivity}",
                f"confidence={memory.confidence}",
            ]
        )
        if memory.raw_entry and memory.raw_entry.user_importance is not None:
            parts.append(f"user_importance={memory.raw_entry.user_importance}/5")
        body.extend([" ".join(parts), f"  {memory.text}"])
    return _section("## MEMORIES", body)


def _relationship_query(session, include_private: bool, user_id: str | None):
    query = scope_user(session.query(Relationship), Relationship, user_id)
    if not include_private:
        query = query.join(RawEntry, Relationship.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _full_relationship_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    body: list[str] = []
    for relationship in _relationship_query(session, include_private, user_id).all():
        source = relationship.source_entity.canonical_name if relationship.source_entity else "?"
        target = relationship.target_entity.canonical_name if relationship.target_entity else "?"
        body.append(
            f"- {source} --[{relationship.relation_type}]--> {target} "
            f"(weight={relationship.weight}, confidence={relationship.confidence})"
        )
    return _section("## RELATIONSHIPS", body)


def _action_query(session, include_private: bool, user_id: str | None):
    query = scope_user(session.query(ActionItem), ActionItem, user_id)
    if not include_private:
        query = query.join(RawEntry, ActionItem.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _full_action_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    actions = (
        _action_query(session, include_private, user_id)
        .order_by(ActionItem.due_at.is_(None), ActionItem.due_at, ActionItem.id)
        .all()
    )
    body = []
    for action in actions:
        due = action.due_at.isoformat(sep=" ", timespec="minutes") if action.due_at else "no due date"
        body.append(f"- [{action.status}] due={due} sensitivity={action.sensitivity}: {action.description}")
    return _section("## ACTION ITEMS", body)


def _expense_query(session, include_private: bool, user_id: str | None):
    query = scope_user(session.query(Expense), Expense, user_id)
    if not include_private:
        query = query.join(RawEntry, Expense.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _merchant_name(session, entity_id: str | None, user_id: str | None) -> str:
    if not entity_id:
        return "unknown merchant/place"
    entity = scope_user(session.query(Entity), Entity, user_id).filter(Entity.id == entity_id).first()
    return entity.canonical_name if entity else "unknown merchant/place"


def _full_expense_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    body = []
    for expense in _expense_query(session, include_private, user_id).order_by(Expense.id).all():
        amount = expense.amount if expense.amount is not None else "unknown"
        merchant = _merchant_name(session, expense.merchant_or_place_entity_id, user_id)
        body.append(
            f"- {amount} {expense.currency or ''} at {merchant}: "
            f"{expense.reason or 'unknown reason'} [{expense.category or 'other'}]"
        )
    return _section("## EXPENSES", body)


def _full_raw_entry_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    query = scope_user(session.query(RawEntry), RawEntry, user_id).order_by(RawEntry.local_date)
    if not include_private:
        query = query.filter(RawEntry.is_private == False)
    body = []
    for entry in query.all():
        prefix = "[PRIVATE] " if entry.is_private else ""
        source = "chat" if is_chat_memory_entry(entry) else (entry.source or "journal")
        body.append(
            f"- [{entry.local_date} {entry.local_time}] [{source}] {prefix}{maybe_decrypt_text(entry.raw_text)}"
        )
    heading = "## RAW JOURNAL AND CHAT ENTRIES"
    if include_private:
        heading += " (INCLUDING PRIVATE - DISCLOSURE MODE)"
    return _section(heading, body)


def _navigation_entities(session, include_private: bool, user_id: str | None) -> list[Entity]:
    entities = scope_user(session.query(Entity), Entity, user_id).order_by(Entity.type, Entity.canonical_name).all()
    if include_private:
        return entities
    return [
        entity
        for entity in entities
        if entity_reference_counts(session, entity.id, user_id or "", include_private=False)["total"] > 0
    ]


def _count_query(session, model, id_column, include_private: bool, user_id: str | None):
    query = scope_user(session.query(func.count(id_column)), model, user_id)
    if include_private or model is RawEntry:
        return query if include_private else query.filter(RawEntry.is_private == False)
    raw_entry_column = {
        Memory: Memory.raw_entry_id,
        Relationship: Relationship.raw_entry_id,
        Event: Event.source_raw_entry_id,
        DocumentSource: DocumentSource.raw_entry_id,
    }[model]
    return query.join(RawEntry, raw_entry_column == RawEntry.id).filter(RawEntry.is_private == False)


def _navigation_overview_lines(
    session,
    entities: list[Entity],
    include_private: bool,
    user_id: str | None,
) -> list[str]:
    counts = {
        "entries": _count_query(session, RawEntry, RawEntry.id, include_private, user_id).scalar() or 0,
        "memories": _count_query(session, Memory, Memory.id, include_private, user_id).scalar() or 0,
        "relationships": _count_query(session, Relationship, Relationship.id, include_private, user_id).scalar() or 0,
        "events": _count_query(session, Event, Event.id, include_private, user_id).scalar() or 0,
        "sources": _count_query(session, DocumentSource, DocumentSource.id, include_private, user_id).scalar() or 0,
    }
    return [
        f"Overview: {counts['entries']} entries, {len(entities)} entities, "
        f"{counts['memories']} memories, {counts['relationships']} relationships, "
        f"{counts['events']} events, {counts['sources']} sources",
        "",
    ]


def _navigation_entity_lines(
    session,
    entities: list[Entity],
    include_private: bool,
    user_id: str | None,
) -> list[str]:
    people = [entity for entity in entities if entity.type == "person"]
    places = [entity for entity in entities if entity.type == "place"]
    others = [entity for entity in entities if entity.type not in {"person", "place"}]
    body = [f"### People ({len(people)})"]
    for person in people:
        attributes = person.attributes_json or []
        key_attributes = [f"{attribute.get('key', '?')}={attribute.get('value', '?')}" for attribute in attributes[:3]]
        attribute_text = f"  [{'; '.join(key_attributes)}]" if key_attributes else ""
        counts = entity_reference_counts(session, person.id, user_id or "", include_private=include_private)
        body.append(
            f"- {person.canonical_name}{attribute_text}  (memories: {counts['memories']}, links: {counts['links']})"
        )
    body.append(f"\n### Places ({len(places)})")
    for place in places:
        counts = entity_reference_counts(session, place.id, user_id or "", include_private=include_private)
        body.append(f"- {place.canonical_name} (visits: {counts['place_events']})")
    if others:
        body.append(f"\n### Other ({len(others)})")
        body.extend(f"- {entity.canonical_name} [{entity.type}]" for entity in others)
    return _section("## ENTITY INDEX", body)


def _navigation_document_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    documents = (
        _document_query(session, include_private, user_id)
        .order_by(DocumentSource.created_at_utc.desc())
        .limit(25)
        .all()
    )
    return _section(
        "## READING SOURCE INDEX",
        [
            f"- {document.title} [{document.source_type}, {document.status}, id={document.id[:8]}]"
            for document in documents
        ],
    )


def _navigation_event_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    events = _event_query(session, include_private, user_id).order_by(Event.local_date).all()
    body = []
    for event in events:
        place = event.place_entity.canonical_name if event.place_entity else "?"
        participants = _event_participant_labels(session, event.id, user_id)[:5]
        names = [label.rsplit(" (", 1)[0] for label in participants]
        body.append(
            f"- {event.local_date} | {event.name} | {event.event_type} | at {place} | "
            f"with {', '.join(names) if names else 'alone'}"
        )
    return _section("## EVENT TIMELINE", body)


def _navigation_relationship_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    relationships = _relationship_query(session, include_private, user_id).all()
    if not relationships:
        return []
    relation_types = Counter(relationship.relation_type for relationship in relationships)
    connections: Counter[str] = Counter()
    for relationship in relationships:
        connections[relationship.source_entity_id] += 1
        connections[relationship.target_entity_id] += 1
    body = [
        f"Total: {len(relationships)} edges across {len(relation_types)} types",
        "Edge types: " + ", ".join(f"{name}({count})" for name, count in relation_types.most_common()),
        "Most connected:",
    ]
    for entity_id, count in connections.most_common(10):
        entity = scope_user(session.query(Entity), Entity, user_id).filter(Entity.id == entity_id).first()
        if entity:
            body.append(f"  - {entity.canonical_name} [{entity.type}]: {count} links")
    return _section("## RELATIONSHIP GRAPH", body)


def _navigation_memory_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    memories = _memory_query(session, include_private, user_id).order_by(Memory.local_date).all()
    if not memories:
        return []
    memory_types = Counter(memory.memory_type for memory in memories)
    body = ["By type: " + ", ".join(f"{name}: {count}" for name, count in memory_types.most_common())]
    dates = [memory.local_date for memory in memories if memory.local_date]
    if dates:
        body.extend([f"Date range: {min(dates)} to {max(dates)}", "Recent:"])
        recent = sorted(memories, key=lambda memory: memory.local_date or date.min, reverse=True)[:10]
        body.extend(f"  - [{memory.local_date}] [{memory.memory_type}] {memory.text[:120]}" for memory in recent)
    return _section("## MEMORY CLUSTERS", body)


def _navigation_action_lines(session, include_private: bool, user_id: str | None) -> list[str]:
    actions = (
        _action_query(session, include_private, user_id)
        .order_by(ActionItem.due_at.is_(None), ActionItem.due_at, ActionItem.id)
        .limit(20)
        .all()
    )
    body = []
    for action in actions:
        due = action.due_at.isoformat(sep=" ", timespec="minutes") if action.due_at else "no due date"
        body.append(f"- [{action.status}] due={due}: {action.description}")
    return _section("## ACTION ITEMS", body)


def _navigation_cross_reference_lines() -> list[str]:
    return [
        "## CROSS-REFERENCES",
        "Use the ENTITY INDEX above to find a person, then check their memory count. ",
        "Use the EVENT TIMELINE to find dates. ",
        "Use RELATIONSHIP GRAPH to understand connections between people. ",
        "For full detail on any item, the complete database follows below. ",
        "",
    ]
