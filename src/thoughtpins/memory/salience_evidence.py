"""Tenant-scoped evidence projection for entity salience scoring."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from thoughtpins.db import Entity, EntityMention, Event, EventParticipant, Memory, RawEntry, Relationship
from thoughtpins.memory.salience import EntitySalienceObservation, source_kind

_AGENCY_MEMORY_TYPES = {"decision", "commitment", "user_action", "future_plan", "progress_update"}


@dataclass(frozen=True)
class EntityEvidence:
    mentions: list[EntityMention]
    memories: list[Memory]
    relationships: list[Relationship]
    participant_events: list[tuple[str, str | None]]
    place_events: list[tuple[str, str | None]]

    @property
    def entry_ids(self) -> set[str]:
        ids = {item.raw_entry_id for item in [*self.mentions, *self.memories, *self.relationships] if item.raw_entry_id}
        ids.update(entry_id for _event_id, entry_id in [*self.participant_events, *self.place_events] if entry_id)
        return ids

    @property
    def event_count(self) -> int:
        return len({event_id for event_id, _entry_id in [*self.participant_events, *self.place_events]})


def load_entity_evidence(session: Session, *, user_id: str, entity_id: str) -> EntityEvidence:
    mentions = (
        session.query(EntityMention)
        .filter(EntityMention.user_id == user_id, EntityMention.entity_id == entity_id)
        .all()
    )
    memories = (
        session.query(Memory)
        .filter(
            Memory.user_id == user_id,
            Memory.valid_to.is_(None),
            or_(Memory.subject_entity_id == entity_id, Memory.object_entity_id == entity_id),
        )
        .all()
    )
    relationships = (
        session.query(Relationship)
        .filter(
            Relationship.user_id == user_id,
            or_(Relationship.source_entity_id == entity_id, Relationship.target_entity_id == entity_id),
        )
        .all()
    )
    participant_rows = (
        session.query(Event.id, Event.source_raw_entry_id)
        .join(EventParticipant, EventParticipant.event_id == Event.id)
        .filter(
            Event.user_id == user_id,
            EventParticipant.user_id == user_id,
            EventParticipant.entity_id == entity_id,
        )
        .all()
    )
    place_rows = (
        session.query(Event.id, Event.source_raw_entry_id)
        .filter(Event.user_id == user_id, Event.place_entity_id == entity_id)
        .all()
    )
    return EntityEvidence(
        mentions=mentions,
        memories=memories,
        relationships=relationships,
        participant_events=[(row[0], row[1]) for row in participant_rows],
        place_events=[(row[0], row[1]) for row in place_rows],
    )


def load_evidence_entries(session: Session, *, user_id: str, entry_ids: set[str]) -> list[RawEntry]:
    if not entry_ids:
        return []
    return session.query(RawEntry).filter(RawEntry.user_id == user_id, RawEntry.id.in_(entry_ids)).all()


def build_entity_observation(
    entity: Entity,
    evidence: EntityEvidence,
    entries: list[RawEntry],
) -> EntitySalienceObservation:
    topic_breadth, topic_entropy = topic_structure(entries)
    observed_dates = sorted({value for entry in entries if (value := entry_date(entry)) is not None})
    temporal_span_days = (observed_dates[-1] - observed_dates[0]).days if len(observed_dates) > 1 else 0
    observed, reported, inferred = confidence_counts(
        evidence.mentions,
        evidence.memories,
        evidence.relationships,
    )
    rating_values = [entry.user_importance for entry in entries if entry.user_importance is not None]
    last_seen = _last_seen(entries, evidence.relationships)
    return EntitySalienceObservation(
        entity_type=entity.type,
        distinct_entry_count=len(evidence.entry_ids),
        mention_count=len(evidence.mentions),
        direct_memory_count=sum(1 for memory in evidence.memories if memory.subject_entity_id == entity.id),
        supporting_memory_count=sum(1 for memory in evidence.memories if memory.object_entity_id == entity.id),
        relationship_count=len(evidence.relationships),
        relationship_evidence_count=sum(int(relation.evidence_count or 1) for relation in evidence.relationships),
        event_count=evidence.event_count,
        agency_count=sum(
            1
            for memory in evidence.memories
            if memory.subject_entity_id == entity.id and memory.memory_type in _AGENCY_MEMORY_TYPES
        ),
        topic_breadth=topic_breadth,
        topic_entropy=topic_entropy,
        source_count=source_diversity(entries),
        temporal_span_days=temporal_span_days,
        active_day_count=len(observed_dates),
        observed_evidence_count=observed,
        reported_evidence_count=reported,
        inferred_evidence_count=inferred,
        user_rating_mean=mean(rating_values) if rating_values else None,
        user_rating_count=len(rating_values),
        last_seen=last_seen,
    )


def topic_structure(entries: list[RawEntry]) -> tuple[int, float]:
    counts: Counter[str] = Counter()
    for entry in entries:
        counts.update(normalized_topics((entry.analysis_json or {}).get("primary_topics") or []))
    if not counts:
        return 0, 0.0
    total = sum(counts.values())
    entropy = 0.0
    if len(counts) > 1:
        entropy = -sum((count / total) * math.log(count / total) for count in counts.values()) / math.log(len(counts))
    return len(counts), max(0.0, min(1.0, entropy))


def normalized_topics(values: list[Any]) -> list[str]:
    return sorted({" ".join(str(value).strip().lower().split()) for value in values if str(value).strip()})


def source_diversity(entries: list[RawEntry]) -> int:
    keys: set[str] = set()
    for entry in entries:
        documents = list(entry.document_sources or [])
        if documents:
            keys.update(f"document:{document.id}" for document in documents)
        else:
            keys.add(f"{source_kind(entry.source)}:{entry.source or 'unknown'}")
    return len(keys)


def entry_date(entry: RawEntry) -> date | None:
    return entry.local_date or (entry.created_at_utc.date() if entry.created_at_utc else None)


def confidence_counts(
    mentions: list[EntityMention],
    memories: list[Memory],
    relationships: list[Relationship],
) -> tuple[int, int, int]:
    values = [item.confidence for item in [*mentions, *memories, *relationships]]
    observed = sum(1 for value in values if value in {"observed_by_user", "user_observed"})
    reported = sum(1 for value in values if value in {"user_reported", "hearsay_from_person"})
    inferred = sum(1 for value in values if value in {"inferred_by_model", "inferred"})
    return observed, reported, inferred


def _last_seen(entries: list[RawEntry], relationships: list[Relationship]) -> date | None:
    candidates = [entry.local_date for entry in entries if entry.local_date]
    candidates.extend(relation.last_seen_at.date() for relation in relationships if relation.last_seen_at)
    return max(candidates, default=None)
