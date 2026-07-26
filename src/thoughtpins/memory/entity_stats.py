"""Tenant-scoped aggregate counts for memory entities."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from thoughtpins.db import (
    ActionItem,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    Memory,
    RawEntry,
    Relationship,
)


def entity_reference_counts(
    session: Session,
    entity_id: str,
    user_id: str,
    *,
    include_private: bool,
) -> dict[str, int]:
    """Count every supported reference to an entity inside one tenant."""

    memory_q = _scope_user(session.query(func.count(Memory.id)), Memory, user_id).filter(
        (Memory.subject_entity_id == entity_id) | (Memory.object_entity_id == entity_id)
    )
    relationship_q = _scope_user(session.query(func.count(Relationship.id)), Relationship, user_id).filter(
        (Relationship.source_entity_id == entity_id) | (Relationship.target_entity_id == entity_id)
    )
    mention_q = _scope_user(session.query(func.count(EntityMention.id)), EntityMention, user_id).filter(
        EntityMention.entity_id == entity_id
    )
    place_event_q = _scope_user(session.query(func.count(Event.id)), Event, user_id).filter(
        Event.place_entity_id == entity_id
    )
    participant_q = (
        _scope_user(session.query(func.count(EventParticipant.id)), EventParticipant, user_id)
        .join(Event, EventParticipant.event_id == Event.id)
        .filter(EventParticipant.entity_id == entity_id)
    )
    action_q = _scope_user(session.query(func.count(ActionItem.id)), ActionItem, user_id).filter(
        ActionItem.owner_entity_id == entity_id
    )
    expense_q = _scope_user(session.query(func.count(Expense.id)), Expense, user_id).filter(
        Expense.merchant_or_place_entity_id == entity_id
    )

    if not include_private:
        public = RawEntry.is_private.is_(False)
        memory_q = memory_q.join(RawEntry, Memory.raw_entry_id == RawEntry.id).filter(public)
        relationship_q = relationship_q.join(RawEntry, Relationship.raw_entry_id == RawEntry.id).filter(public)
        mention_q = mention_q.join(RawEntry, EntityMention.raw_entry_id == RawEntry.id).filter(public)
        place_event_q = place_event_q.join(RawEntry, Event.source_raw_entry_id == RawEntry.id).filter(public)
        participant_q = participant_q.join(RawEntry, Event.source_raw_entry_id == RawEntry.id).filter(public)
        action_q = action_q.join(RawEntry, ActionItem.raw_entry_id == RawEntry.id).filter(public)
        expense_q = expense_q.join(RawEntry, Expense.raw_entry_id == RawEntry.id).filter(public)

    counts = {
        "memories": memory_q.scalar() or 0,
        "links": relationship_q.scalar() or 0,
        "mentions": mention_q.scalar() or 0,
        "place_events": place_event_q.scalar() or 0,
        "participations": participant_q.scalar() or 0,
        "actions": action_q.scalar() or 0,
        "expenses": expense_q.scalar() or 0,
    }
    counts["total"] = sum(counts.values())
    return counts


def _scope_user(query, model, user_id: str):
    return query.filter(model.user_id == user_id)
