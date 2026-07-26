"""High-level query interface over the relational memory store."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

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
from thoughtpins.store import get_session


class MemoryStore:
    """Query interface for structured memory retrieval."""

    def __init__(self, session: Session | None = None, user_id: str | None = None):
        self._session = session or get_session()
        self.user_id = user_id

    def _scope(self, query, model):
        if self.user_id:
            return query.filter(model.user_id == self.user_id)
        return query

    def get_entity_by_name(self, name: str, entity_type: str | None = None) -> Optional[Entity]:
        q = self._scope(self._session.query(Entity), Entity).filter(Entity.canonical_name == name)
        if entity_type:
            q = q.filter(Entity.type == entity_type)
        result = q.first()
        if result:
            return result

        q = self._scope(self._session.query(Entity), Entity).filter(Entity.canonical_name.ilike(name))
        if entity_type:
            q = q.filter(Entity.type == entity_type)
        result = q.first()
        if result:
            return result

        name_stripped = name.lower().removeprefix("the ").strip()
        q = self._scope(self._session.query(Entity), Entity)
        if entity_type:
            q = q.filter(Entity.type == entity_type)
        all_entities = q.all()
        for ent in all_entities:
            ent_stripped = ent.canonical_name.lower().removeprefix("the ").strip()
            if ent_stripped == name_stripped:
                return ent

        for ent in all_entities:
            if name_stripped and name_stripped in ent.canonical_name.lower():
                return ent

        return None

    def find_entities(self, name_fragment: str, entity_type: str | None = None) -> list[Entity]:
        q = self._scope(self._session.query(Entity), Entity).filter(Entity.canonical_name.ilike(f"%{name_fragment}%"))
        if entity_type:
            q = q.filter(Entity.type == entity_type)
        return q.all()

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        return self._scope(self._session.query(Entity), Entity).filter(Entity.type == entity_type).all()

    def get_events_by_place(self, place_name: str, limit: int = 10) -> list[Event]:
        place = self.get_entity_by_name(place_name, "place")
        if not place:
            return []
        return (
            self._scope(self._session.query(Event), Event)
            .filter(Event.place_entity_id == place.id)
            .order_by(desc(Event.local_date))
            .limit(limit)
            .all()
        )

    def get_events_by_date_range(self, start: date, end: date) -> list[Event]:
        return (
            self._scope(self._session.query(Event), Event)
            .filter(Event.local_date >= start, Event.local_date <= end)
            .order_by(desc(Event.local_date))
            .all()
        )

    def get_event_participants(self, event_id: str) -> list[tuple[Entity, str]]:
        q = (
            self._session.query(Entity, EventParticipant.role)
            .join(EventParticipant, EventParticipant.entity_id == Entity.id)
            .filter(EventParticipant.event_id == event_id)
        )
        if self.user_id:
            q = q.filter(Entity.user_id == self.user_id, EventParticipant.user_id == self.user_id)
        return q.all()

    def get_memories_by_entity(self, entity_id: str, limit: int = 50) -> list[Memory]:
        return (
            self._scope(self._session.query(Memory), Memory)
            .filter(Memory.valid_to.is_(None))
            .filter((Memory.subject_entity_id == entity_id) | (Memory.object_entity_id == entity_id))
            .order_by(desc(Memory.local_date))
            .limit(limit)
            .all()
        )

    def get_memories_by_type(self, memory_type: str, limit: int = 50) -> list[Memory]:
        return (
            self._scope(self._session.query(Memory), Memory)
            .filter(Memory.memory_type == memory_type, Memory.valid_to.is_(None))
            .order_by(desc(Memory.local_date))
            .limit(limit)
            .all()
        )

    def get_recent_memories(self, days: int = 7, limit: int = 100) -> list[Memory]:
        since = date.today() - timedelta(days=days)
        return (
            self._scope(self._session.query(Memory), Memory)
            .filter(Memory.local_date >= since, Memory.valid_to.is_(None))
            .order_by(desc(Memory.local_date))
            .limit(limit)
            .all()
        )

    def get_relationships_for_entity(self, entity_id: str) -> list[Relationship]:
        return (
            self._scope(self._session.query(Relationship), Relationship)
            .filter((Relationship.source_entity_id == entity_id) | (Relationship.target_entity_id == entity_id))
            .order_by(desc(Relationship.last_seen_at))
            .all()
        )

    def get_recent_entries(self, limit: int = 10) -> list[RawEntry]:
        return (
            self._scope(self._session.query(RawEntry), RawEntry)
            .filter(RawEntry.is_private == False)
            .order_by(desc(RawEntry.created_at_utc))
            .limit(limit)
            .all()
        )

    def get_entries_by_date(self, target_date: date) -> list[RawEntry]:
        return (
            self._scope(self._session.query(RawEntry), RawEntry)
            .filter(RawEntry.local_date == target_date)
            .order_by(RawEntry.created_at_utc)
            .all()
        )

    def get_entries_by_date_range(self, start: date, end: date) -> list[RawEntry]:
        return (
            self._scope(self._session.query(RawEntry), RawEntry)
            .filter(RawEntry.local_date >= start, RawEntry.local_date <= end)
            .order_by(RawEntry.created_at_utc)
            .all()
        )

    def get_stats(self) -> dict:
        return {
            "raw_entries": self._scope(self._session.query(func.count(RawEntry.id)), RawEntry).scalar(),
            "entities": self._scope(self._session.query(func.count(Entity.id)), Entity).scalar(),
            "memories": self._scope(self._session.query(func.count(Memory.id)), Memory).scalar(),
            "relationships": self._scope(self._session.query(func.count(Relationship.id)), Relationship).scalar(),
            "events": self._scope(self._session.query(func.count(Event.id)), Event).scalar(),
            "action_items": self._scope(self._session.query(func.count(ActionItem.id)), ActionItem).scalar(),
            "expenses": self._scope(self._session.query(func.count(Expense.id)), Expense).scalar(),
            "sources": self._scope(self._session.query(func.count(DocumentSource.id)), DocumentSource).scalar(),
        }

    def get_all_memories_as_messages(self, limit: int = 100) -> list[dict]:
        memories = (
            self._scope(self._session.query(Memory), Memory)
            .filter(Memory.valid_to.is_(None))
            .order_by(desc(Memory.local_date))
            .limit(limit)
            .all()
        )
        return [
            {
                "role": "user",
                "content": m.text,
                "metadata": {
                    "memory_id": m.id,
                    "memory_type": m.memory_type,
                    "date": str(m.local_date),
                    "confidence": m.confidence,
                },
            }
            for m in memories
        ]

    def commit(self) -> None:
        self._session.commit()

    def close(self) -> None:
        self._session.close()
