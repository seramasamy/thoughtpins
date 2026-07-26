"""Small persistence helpers for deterministic memory evaluation fixtures."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from thoughtpins.db import Entity, Memory, RawEntry, Relationship
from thoughtpins.utils import hash_text


def fixture_entity(session: Session, user_id: str, name: str, entity_type: str) -> Entity:
    existing = (
        session.query(Entity)
        .filter(
            Entity.user_id == user_id,
            Entity.type == entity_type,
            Entity.canonical_name == name,
        )
        .first()
    )
    if existing:
        return existing
    entity = Entity(user_id=user_id, type=entity_type, canonical_name=name)
    session.add(entity)
    session.flush()
    return entity


def fixture_raw_entry(session: Session, user_id: str, text: str) -> RawEntry:
    raw = RawEntry(
        user_id=user_id,
        local_date=datetime(2026, 5, 30).date(),
        local_time="09:00",
        source="eval",
        raw_text=text,
        content_hash=hash_text(text),
        processed_status="completed",
    )
    session.add(raw)
    session.flush()
    return raw


def fixture_memory(
    session: Session,
    user_id: str,
    raw: RawEntry,
    text: str,
    *,
    memory_type: str = "observation",
    subject: Entity | None = None,
    obj: Entity | None = None,
    structured_json: dict | None = None,
    confidence: str = "observed_by_user",
    predicate: str | None = None,
) -> Memory:
    memory = Memory(
        user_id=user_id,
        raw_entry_id=raw.id,
        memory_type=memory_type,
        subject_entity_id=subject.id if subject else None,
        object_entity_id=obj.id if obj else None,
        text=text,
        structured_json=structured_json,
        confidence=confidence,
        predicate=predicate,
        local_date=raw.local_date,
        source_provenance=(f"raw_entry:{raw.id}" if memory_type != "source_excerpt" else None),
    )
    session.add(memory)
    session.flush()
    return memory


def fixture_relationship(
    session: Session,
    user_id: str,
    raw: RawEntry,
    source: Entity,
    target: Entity,
    relation: str,
) -> None:
    session.add(
        Relationship(
            user_id=user_id,
            source_entity_id=source.id,
            target_entity_id=target.id,
            relation_type=relation,
            raw_entry_id=raw.id,
            weight=1.0,
        )
    )
