"""API projections for source records and explainable memory cards."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import DocumentSource, Entity, EntityMention, Event, Memory, RawEntry, Relationship
from thoughtpins.memory.salience import salience_tier
from thoughtpins.vault.paths import document_note_path, entity_note_path, event_note_path


class LibrarySourceResponse(BaseModel):
    id: str
    title: str
    source_type: str
    status: str
    source_url: str | None = None
    original_url: str | None = None
    canonical_url: str | None = None
    source_domain: str | None = None
    author: str | None = None
    published_at: str | None = None
    publisher: str | None = None
    topics: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    access_method: str | None = None
    rights_basis: str | None = None
    fetch_status: str | None = None
    paywall_detected: bool = False
    retrieval_quality_score: float | None = None
    summary: str | None = None
    created_at_utc: str | None = None
    chunks: int = 0


class MemoryCardMemoryResponse(BaseModel):
    id: str | None = None
    entry_id: str | None = None
    date: str | None = None
    type: str
    text: str
    confidence: str | None = None


class MemoryCardRelationshipResponse(BaseModel):
    type: str
    other: str
    confidence: str | None = None
    evidence_count: int = 1


class MemoryCardSourceResponse(BaseModel):
    id: str
    title: str
    source_type: str
    status: str
    source_url: str | None = None
    obsidian_path: str | None = None


class MemoryCardTimelineResponse(BaseModel):
    date: str | None = None
    label: str
    source: str | None = None


class MemoryCardResponse(BaseModel):
    id: str
    name: str
    type: str
    subtitle: str | None = None
    aliases: list[str] = Field(default_factory=list)
    attributes: list[Any] = Field(default_factory=list)
    memory_count: int = 0
    mention_count: int = 0
    relationship_count: int = 0
    salience_score: float = 0.0
    salience_uncertainty: float = 1.0
    salience_tier: str = "background"
    salience_model_version: str | None = None
    first_seen_at_utc: str | None = None
    last_seen: str | None = None
    statline: dict[str, Any] = Field(default_factory=dict)
    recent_memories: list[MemoryCardMemoryResponse] = Field(default_factory=list)
    relationships: list[MemoryCardRelationshipResponse] = Field(default_factory=list)
    source_documents: list[MemoryCardSourceResponse] = Field(default_factory=list)
    timeline: list[MemoryCardTimelineResponse] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    ask_prompt: str | None = None
    obsidian_path: str | None = None


class MemoryCardsResponse(BaseModel):
    section: str
    query: str = ""
    sections: dict[str, list[str]]
    items: list[MemoryCardResponse]
    total: int


class MemoryCardEntryResponse(BaseModel):
    id: str
    created_at_utc: str | None = None
    local_date: str | None = None
    source: str
    raw_text: str
    processed_status: str


class MemoryCardDetailResponse(MemoryCardResponse):
    all_memories: list[MemoryCardMemoryResponse] = Field(default_factory=list)
    entries: list[MemoryCardEntryResponse] = Field(default_factory=list)


MEMORY_CARD_SECTIONS: dict[str, list[str]] = {
    "people": ["person"],
    "places": ["place"],
    "projects": ["project", "idea"],
    "organizations": ["organization"],
    "events": ["event"],
    "things": ["thing", "object", "technology"],
    "concepts": ["concept", "topic", "document"],
    "all": [
        "person",
        "place",
        "organization",
        "project",
        "idea",
        "event",
        "thing",
        "object",
        "technology",
        "concept",
        "topic",
        "document",
    ],
}
EVENT_CARD_SECTIONS = {"events", "all"}


def source_response(document: DocumentSource, *, include_summary: bool = False) -> LibrarySourceResponse:
    reading_analysis = (document.metadata_json or {}).get("reading_analysis", {})
    if not isinstance(reading_analysis, dict):
        reading_analysis = {}
    return LibrarySourceResponse(
        id=document.id,
        title=document.title,
        source_type=document.source_type,
        status=document.status,
        source_url=document.source_url,
        original_url=document.original_url,
        canonical_url=document.canonical_url,
        source_domain=document.source_domain,
        author=document.author,
        published_at=document.published_at.isoformat() if document.published_at else None,
        publisher=str(reading_analysis.get("publisher") or "").strip() or None,
        topics=[str(item) for item in reading_analysis.get("topics", []) if str(item).strip()][:8],
        key_concepts=[str(item) for item in reading_analysis.get("key_concepts", []) if str(item).strip()][:16],
        access_method=document.access_method,
        rights_basis=document.rights_basis,
        fetch_status=document.fetch_status,
        paywall_detected=bool(document.paywall_detected),
        retrieval_quality_score=document.retrieval_quality_score,
        summary=document.summary if include_summary else None,
        created_at_utc=document.created_at_utc.isoformat() if document.created_at_utc else None,
        chunks=len(document.chunks),
    )


def event_card(event: Event, session: Session) -> MemoryCardResponse:
    participants = [participant.entity for participant in event.participants if participant.entity]
    participant_names = [participant.canonical_name for participant in participants]
    relationships = [
        MemoryCardRelationshipResponse(type="participant", other=name, confidence="observed_by_user")
        for name in participant_names[:8]
    ]
    if event.place_entity:
        relationships.insert(
            0,
            MemoryCardRelationshipResponse(
                type="located_at",
                other=event.place_entity.canonical_name,
                confidence="observed_by_user",
            ),
        )
    source_documents = [
        source_projection(document) for document in (event.raw_entry.document_sources if event.raw_entry else [])[:5]
    ]
    event_date = (
        str(event.local_date) if event.local_date else (event.start_at.date().isoformat() if event.start_at else None)
    )
    memory_count = 1 if event.summary else 0
    return MemoryCardResponse(
        id=f"event:{event.id}",
        name=event.name,
        type="event",
        subtitle=event.summary,
        attributes=[
            {"key": "event_type", "value": event.event_type, "confidence": "observed_by_user"},
            {
                "key": "place",
                "value": event.place_entity.canonical_name if event.place_entity else "",
                "confidence": "observed_by_user",
            },
        ],
        memory_count=memory_count,
        mention_count=len(participant_names),
        relationship_count=len(relationships),
        first_seen_at_utc=(
            event.start_at.isoformat()
            if event.start_at
            else event.raw_entry.created_at_utc.isoformat()
            if event.raw_entry and event.raw_entry.created_at_utc
            else None
        ),
        last_seen=event_date,
        statline={
            "MEM": memory_count,
            "MENT": len(participant_names),
            "REL": len(relationships),
            "LAST": event_date or "never",
        },
        recent_memories=[
            MemoryCardMemoryResponse(
                id=event.id,
                entry_id=event.source_raw_entry_id,
                date=event_date,
                type="event",
                text=event.summary or event.name,
                confidence="observed_by_user",
            )
        ]
        if event.summary
        else [],
        relationships=relationships,
        source_documents=source_documents,
        timeline=[
            MemoryCardTimelineResponse(
                date=event_date, label=event.summary or event.name, source=event.source_raw_entry_id
            )
        ],
        provenance={
            "kind": "event",
            "event_id": event.id,
            "confidence": "observed_by_user",
            "sensitivity": event.sensitivity,
            "source_entry_id": event.source_raw_entry_id,
        },
        ask_prompt=card_ask_prompt(event.name, "event"),
        obsidian_path=event_note_path(
            event_name=event.name, local_date=event.local_date, start_at=event.start_at
        ).as_posix(),
    )


def event_card_detail(event: Event, session: Session) -> MemoryCardDetailResponse:
    card = event_card(event, session)
    entries = []
    if event.raw_entry:
        entries.append(entry_projection(event.raw_entry))
    return MemoryCardDetailResponse(**card.model_dump(), all_memories=card.recent_memories, entries=entries)


def memory_card(entity: Entity, session: Session) -> MemoryCardResponse:
    memories_query = (
        session.query(Memory)
        .filter(Memory.user_id == entity.user_id, Memory.valid_to.is_(None))
        .filter(or_(Memory.subject_entity_id == entity.id, Memory.object_entity_id == entity.id))
    )
    memory_count = memories_query.count()
    recent_memories = memories_query.order_by(Memory.local_date.desc(), Memory.created_at_utc.desc()).limit(3).all()
    relationships_query = (
        session.query(Relationship)
        .filter(Relationship.user_id == entity.user_id)
        .filter(or_(Relationship.source_entity_id == entity.id, Relationship.target_entity_id == entity.id))
    )
    relationships = (
        relationships_query.order_by(Relationship.evidence_count.desc(), Relationship.last_seen_at.desc())
        .limit(5)
        .all()
    )
    mention_count = (
        session.query(func.count(EntityMention.id))
        .filter(EntityMention.user_id == entity.user_id, EntityMention.entity_id == entity.id)
        .scalar()
        or 0
    )
    last_seen = _last_seen(recent_memories, relationships)
    relation_items = [_relationship_projection(entity, relationship) for relationship in relationships]
    relationship_count = relationships_query.count()
    return MemoryCardResponse(
        id=entity.id,
        name=entity.canonical_name,
        type=entity.type,
        subtitle=recent_memories[0].text[:180] if recent_memories else entity.notes,
        aliases=list(entity.aliases_json or []),
        attributes=list(entity.attributes_json or []),
        memory_count=memory_count,
        mention_count=mention_count,
        relationship_count=relationship_count,
        salience_score=float(entity.salience_score or 0.0),
        salience_uncertainty=float(entity.salience_uncertainty if entity.salience_uncertainty is not None else 1.0),
        salience_tier=salience_tier(float(entity.salience_score or 0.0)),
        salience_model_version=entity.salience_model_version,
        first_seen_at_utc=entity.created_at_utc.isoformat() if entity.created_at_utc else None,
        last_seen=last_seen,
        statline={"MEM": memory_count, "MENT": mention_count, "REL": relationship_count, "LAST": last_seen or "never"},
        recent_memories=[memory_projection(memory) for memory in recent_memories],
        relationships=relation_items,
        source_documents=source_documents_for_entity(entity, session),
        timeline=memory_timeline(recent_memories),
        provenance={
            "kind": "entity",
            "entity_id": entity.id,
            "confidence": entity.confidence,
            "sensitivity": entity.sensitivity,
            "salience": {
                "score": float(entity.salience_score or 0.0),
                "uncertainty": float(entity.salience_uncertainty if entity.salience_uncertainty is not None else 1.0),
                "tier": salience_tier(float(entity.salience_score or 0.0)),
                "signals": dict(entity.salience_signals_json or {}),
                "model_version": entity.salience_model_version,
            },
            "created_at_utc": entity.created_at_utc.isoformat() if entity.created_at_utc else None,
            "updated_at_utc": entity.updated_at_utc.isoformat() if entity.updated_at_utc else None,
        },
        ask_prompt=card_ask_prompt(entity.canonical_name, entity.type),
        obsidian_path=entity_note_path(entity.type, entity.canonical_name).as_posix(),
    )


def memory_card_detail(entity: Entity, session: Session, *, limit: int = 50) -> MemoryCardDetailResponse:
    card = memory_card(entity, session)
    memories = (
        session.query(Memory)
        .filter(Memory.user_id == entity.user_id, Memory.valid_to.is_(None))
        .filter(or_(Memory.subject_entity_id == entity.id, Memory.object_entity_id == entity.id))
        .order_by(Memory.local_date.desc(), Memory.created_at_utc.desc())
        .limit(limit)
        .all()
    )
    entries = (
        session.query(RawEntry)
        .join(EntityMention, EntityMention.raw_entry_id == RawEntry.id)
        .filter(RawEntry.user_id == entity.user_id, EntityMention.user_id == entity.user_id)
        .filter(EntityMention.entity_id == entity.id)
        .order_by(RawEntry.created_at_utc.desc())
        .limit(12)
        .all()
    )
    return MemoryCardDetailResponse(
        **card.model_dump(),
        all_memories=[memory_projection(memory) for memory in memories],
        entries=[entry_projection(entry) for entry in entries],
    )


def source_projection(document: DocumentSource) -> MemoryCardSourceResponse:
    return MemoryCardSourceResponse(
        id=document.id,
        title=document.title,
        source_type=document.source_type,
        status=document.status,
        source_url=document.source_url,
        obsidian_path=document_note_path(document.source_type, document.title).as_posix(),
    )


def source_documents_for_entity(entity: Entity, session: Session, *, limit: int = 5) -> list[MemoryCardSourceResponse]:
    entry_ids = [mention.raw_entry_id for mention in entity.entity_mentions if mention.raw_entry_id]
    provenance_ids = []
    memories = (
        session.query(Memory.source_provenance)
        .filter(Memory.user_id == entity.user_id, Memory.valid_to.is_(None))
        .filter(or_(Memory.subject_entity_id == entity.id, Memory.object_entity_id == entity.id))
        .all()
    )
    for (source_provenance,) in memories:
        if isinstance(source_provenance, str) and source_provenance.startswith("document:"):
            provenance_ids.append(source_provenance.split(":", 1)[1])
    filters = []
    if entry_ids:
        filters.append(DocumentSource.raw_entry_id.in_(entry_ids))
    if provenance_ids:
        filters.append(DocumentSource.id.in_(provenance_ids))
    if not filters:
        return []
    documents = (
        session.query(DocumentSource)
        .filter(DocumentSource.user_id == entity.user_id)
        .filter(or_(*filters))
        .order_by(DocumentSource.created_at_utc.desc())
        .limit(limit)
        .all()
    )
    return [source_projection(document) for document in documents]


def memory_timeline(memories: list[Memory], *, limit: int = 5) -> list[MemoryCardTimelineResponse]:
    return [
        MemoryCardTimelineResponse(
            date=str(memory.local_date)
            if memory.local_date
            else (memory.created_at_utc.date().isoformat() if memory.created_at_utc else None),
            label=memory.text[:220],
            source=memory.raw_entry_id,
        )
        for memory in memories[:limit]
    ]


def memory_projection(memory: Memory) -> MemoryCardMemoryResponse:
    return MemoryCardMemoryResponse(
        id=memory.id,
        entry_id=memory.raw_entry_id,
        date=str(memory.local_date or ""),
        type=memory.memory_type,
        text=memory.text,
        confidence=memory.confidence,
    )


def entry_projection(entry: RawEntry) -> MemoryCardEntryResponse:
    return MemoryCardEntryResponse(
        id=entry.id,
        created_at_utc=entry.created_at_utc.isoformat() if entry.created_at_utc else None,
        local_date=str(entry.local_date) if entry.local_date else None,
        source=entry.source,
        raw_text=maybe_decrypt_text(entry.raw_text),
        processed_status=entry.processed_status,
    )


def card_ask_prompt(name: str, card_type: str) -> str:
    clean_name = (name or "this memory").strip() or "this memory"
    clean_type = (card_type or "memory").strip() or "memory"
    return (
        f"What do you remember about {clean_name}? "
        f"Treat it as a {clean_type} memory card and include journal facts, source documents, timeline, "
        "relationships, open loops, and exact evidence where available."
    )


def _relationship_projection(entity: Entity, relationship: Relationship) -> MemoryCardRelationshipResponse:
    if relationship.source_entity_id == entity.id:
        other = relationship.target_entity.canonical_name if relationship.target_entity else "unknown"
    else:
        other = relationship.source_entity.canonical_name if relationship.source_entity else "unknown"
    return MemoryCardRelationshipResponse(
        type=relationship.relation_type,
        other=other,
        confidence=relationship.confidence,
        evidence_count=relationship.evidence_count or 1,
    )


def _last_seen(memories: list[Memory], relationships: list[Relationship]) -> str | None:
    if memories:
        memory = memories[0]
        if memory.local_date:
            return str(memory.local_date)
        if memory.created_at_utc:
            return memory.created_at_utc.date().isoformat()
    if relationships and relationships[0].last_seen_at:
        return relationships[0].last_seen_at.date().isoformat()
    return None
