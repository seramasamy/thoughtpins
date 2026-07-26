"""Privacy-safe database projection and deterministic vault path planning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy.orm import Session, selectinload

from thoughtpins.db import DocumentSource, Entity, EntityMention, Event, Memory, RawEntry, Relationship
from thoughtpins.vault.export_format import (
    _entry_date,
    _entry_datetime,
    _entry_title,
    _event_date,
    _unique_note_path,
)
from thoughtpins.vault.markdown import safe_filename
from thoughtpins.vault.paths import ENTITY_FOLDERS


@dataclass(frozen=True)
class VaultProjection:
    entries: list[RawEntry]
    entities: list[Entity]
    events: list[Event]
    documents: list[DocumentSource]
    relationships: list[Relationship]
    memories: list[Memory]


@dataclass(frozen=True)
class VaultPaths:
    entries: dict[str, PurePosixPath]
    daily: dict[date, PurePosixPath]
    entities: dict[str, PurePosixPath]
    entity_names: dict[str, str]
    events: dict[str, PurePosixPath]
    documents: dict[str, PurePosixPath]


class VaultProjectionLoader:
    """Load only rows with portable, non-private source provenance."""

    def __init__(self, session: Session, user_id: str | None) -> None:
        self._session = session
        self._user_id = user_id

    def load(self) -> VaultProjection:
        entries = self._load_entries()
        events = self._load_events()
        documents = self._load_documents()
        relationships = self._load_relationships()
        memories = self._load_memories()
        entities = self._load_entities(self._public_entity_ids(entries))
        return VaultProjection(entries, entities, events, documents, relationships, memories)

    def _load_entries(self) -> list[RawEntry]:
        query = (
            self._session.query(RawEntry)
            .options(
                selectinload(RawEntry.document_sources),
                selectinload(RawEntry.entity_mentions).selectinload(EntityMention.entity),
                selectinload(RawEntry.memories),
            )
            .filter(RawEntry.is_private.is_(False))
        )
        if self._user_id:
            query = query.filter(RawEntry.user_id == self._user_id)
        return query.order_by(RawEntry.local_date.asc(), RawEntry.created_at_utc.asc()).all()

    def _load_entities(self, entity_ids: set[str]) -> list[Entity]:
        if not entity_ids:
            return []
        entities: list[Entity] = []
        ordered_ids = sorted(entity_ids)
        for offset in range(0, len(ordered_ids), 500):
            query = self._session.query(Entity).filter(Entity.id.in_(ordered_ids[offset : offset + 500]))
            if self._user_id:
                query = query.filter(Entity.user_id == self._user_id)
            entities.extend(query.all())
        return sorted(entities, key=lambda entity: (entity.type, entity.id))

    def _load_events(self) -> list[Event]:
        query = (
            self._session.query(Event)
            .join(RawEntry, Event.source_raw_entry_id == RawEntry.id)
            .filter(
                RawEntry.is_private.is_(False),
            )
        )
        if self._user_id:
            query = query.filter(Event.user_id == self._user_id, RawEntry.user_id == self._user_id)
        return query.order_by(Event.local_date.asc(), Event.name.asc()).all()

    def _load_documents(self) -> list[DocumentSource]:
        query = (
            self._session.query(DocumentSource)
            .join(
                RawEntry,
                DocumentSource.raw_entry_id == RawEntry.id,
            )
            .filter(RawEntry.is_private.is_(False))
        )
        if self._user_id:
            query = query.filter(DocumentSource.user_id == self._user_id, RawEntry.user_id == self._user_id)
        return query.order_by(DocumentSource.created_at_utc.asc()).all()

    def _load_relationships(self) -> list[Relationship]:
        query = (
            self._session.query(Relationship)
            .join(
                RawEntry,
                Relationship.raw_entry_id == RawEntry.id,
            )
            .filter(RawEntry.is_private.is_(False))
        )
        if self._user_id:
            query = query.filter(Relationship.user_id == self._user_id, RawEntry.user_id == self._user_id)
        return query.order_by(Relationship.relation_type.asc(), Relationship.first_seen_at.asc()).all()

    def _load_memories(self) -> list[Memory]:
        query = (
            self._session.query(Memory)
            .join(RawEntry, Memory.raw_entry_id == RawEntry.id)
            .filter(
                RawEntry.is_private.is_(False),
            )
        )
        if self._user_id:
            query = query.filter(Memory.user_id == self._user_id, RawEntry.user_id == self._user_id)
        return query.order_by(Memory.created_at_utc.desc()).all()

    def _public_entity_ids(self, entries: list[RawEntry]) -> set[str]:
        entry_ids = [entry.id for entry in entries]
        entity_ids: set[str] = set()
        for offset in range(0, len(entry_ids), 500):
            query = self._session.query(EntityMention.entity_id).filter(
                EntityMention.raw_entry_id.in_(entry_ids[offset : offset + 500]),
            )
            if self._user_id:
                query = query.filter(EntityMention.user_id == self._user_id)
            entity_ids.update(str(row[0]) for row in query.all() if row[0])
        return entity_ids


def build_vault_paths(projection: VaultProjection) -> VaultPaths:
    """Assign stable cross-platform paths without exposing private-only names."""
    entry_paths: dict[str, PurePosixPath] = {}
    used: set[str] = set()
    for entry in projection.entries:
        day = _entry_date(entry)
        created = _entry_datetime(entry)
        title = safe_filename(_entry_title(entry), fallback="Entry", max_length=80)
        entry_folder = PurePosixPath("Entries") / str(day.year) / f"{day.month:02d}" / f"{day.day:02d}"
        entry_paths[entry.id] = _unique_note_path(
            entry_folder,
            f"{created.strftime('%H%M%S')}-{title}",
            entry.id,
            used,
        )

    daily_paths = {
        day: PurePosixPath("Journal") / str(day.year) / f"{day.month:02d}" / f"{day.isoformat()}.md"
        for day in sorted({_entry_date(entry) for entry in projection.entries})
    }

    entity_paths: dict[str, PurePosixPath] = {}
    entity_names: dict[str, str] = {}
    public_entry_ids = set(entry_paths)
    used = set()
    for entity in projection.entities:
        name = portable_entity_name(entity, public_entry_ids)
        entity_names[entity.id] = name
        entity_folder = ENTITY_FOLDERS.get((entity.type or "concept").lower(), "Concepts")
        entity_paths[entity.id] = _unique_note_path(
            PurePosixPath(entity_folder),
            safe_filename(name, fallback="Entity"),
            entity.id,
            used,
        )

    event_paths: dict[str, PurePosixPath] = {}
    used = set()
    for event in projection.events:
        day = _event_date(event)
        event_folder = PurePosixPath("Events") / str(day.year) / f"{day.month:02d}"
        stem = safe_filename(f"{day.isoformat()} {event.name}", fallback="Event", max_length=100)
        event_paths[event.id] = _unique_note_path(event_folder, stem, event.id, used)

    document_paths: dict[str, PurePosixPath] = {}
    used = set()
    for document in projection.documents:
        document_folder = PurePosixPath(
            "Library/Articles" if document.source_type in {"url", "article"} else "Library/Documents",
        )
        document_paths[document.id] = _unique_note_path(
            document_folder,
            safe_filename(document.title, fallback="Source"),
            document.id,
            used,
        )
    return VaultPaths(entry_paths, daily_paths, entity_paths, entity_names, event_paths, document_paths)


def portable_entity_name(entity: Entity, public_entry_ids: set[str]) -> str:
    surfaces = [
        mention.surface_text.strip()
        for mention in entity.entity_mentions
        if mention.raw_entry_id in public_entry_ids and mention.surface_text.strip()
    ]
    if not surfaces:
        return f"Entity {entity.id[:8]}"
    counts: dict[str, tuple[int, str]] = {}
    for surface in surfaces:
        key = surface.casefold()
        count, _ = counts.get(key, (0, surface))
        counts[key] = (count + 1, surface)
    canonical_key = entity.canonical_name.casefold()
    if canonical_key in counts:
        return counts[canonical_key][1]
    canonical_pattern = re.compile(rf"(?<!\w){re.escape(entity.canonical_name)}(?!\w)", re.IGNORECASE)
    if any(canonical_pattern.search(surface) for surface in surfaces):
        return entity.canonical_name
    return sorted(counts.values(), key=lambda item: (-item[0], item[1].casefold()))[0][1]


def entity_public_bounds(
    entity: Entity,
    *,
    entity_mentions: list[EntityMention],
    memories: list[Memory],
    relationships: list[Relationship],
    events: list[Event],
) -> tuple[datetime, datetime]:
    timestamps = [
        mention.raw_entry.created_at_utc
        for mention in entity_mentions
        if mention.raw_entry and mention.raw_entry.created_at_utc
    ]
    timestamps.extend(memory.created_at_utc for memory in memories if memory.created_at_utc)
    timestamps.extend(
        relationship.raw_entry.created_at_utc
        for relationship in relationships
        if relationship.raw_entry and relationship.raw_entry.created_at_utc
    )
    for event in events:
        participant_ids = {participant.entity_id for participant in event.participants}
        if event.place_entity_id != entity.id and entity.id not in participant_ids:
            continue
        timestamp = event.start_at or (event.raw_entry.created_at_utc if event.raw_entry else None)
        if timestamp:
            timestamps.append(timestamp)
    if not timestamps:
        generated = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        return generated, generated
    return min(timestamps), max(timestamps)


def entity_public_confidence(
    *,
    entity_mentions: list[EntityMention],
    memories: list[Memory],
    relationships: list[Relationship],
) -> str:
    candidates = [
        *(mention.confidence for mention in entity_mentions),
        *(memory.confidence for memory in memories),
        *(relationship.confidence for relationship in relationships),
    ]
    return next((str(value) for value in candidates if value), "unknown")


__all__ = [
    "VaultProjection",
    "VaultProjectionLoader",
    "VaultPaths",
    "build_vault_paths",
    "entity_public_bounds",
    "entity_public_confidence",
    "portable_entity_name",
]
