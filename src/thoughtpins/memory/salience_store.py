"""Database adapter for the contextual salience model.

The algorithm lives in ``salience.py`` so it can be tested without a database.
This module only gathers tenant-scoped evidence and persists versioned scores.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from thoughtpins.db import (
    ActionItem,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Memory,
    RawEntry,
    Relationship,
)
from thoughtpins.llm import ExtractionResult
from thoughtpins.memory.salience import (
    MODEL_VERSION,
    EntrySalienceObservation,
    SalienceScore,
    rescore_entry_salience,
    score_entity_salience,
    score_entry_salience,
    source_kind,
)
from thoughtpins.memory.salience_evidence import (
    build_entity_observation,
    load_entity_evidence,
    load_evidence_entries,
)
from thoughtpins.memory.salience_evidence import (
    normalized_topics as _normalized_topics,
)


def update_salience_for_entry(
    session: Session,
    raw_entry: RawEntry,
    extraction: ExtractionResult,
    stats: dict[str, Any],
    *,
    source_text: str | None = None,
) -> SalienceScore:
    """Persist extracted analysis, score the entry, and refresh touched entities."""

    scene = extraction.scene_analysis.model_dump(mode="json")
    topics = [topic.strip() for topic in extraction.scene_analysis.primary_topics if topic.strip()]
    raw_entry.analysis_json = {
        "analysis_version": 2,
        "entry_summary": extraction.entry_summary[:2000],
        "entry_type": extraction.entry_type,
        "scene_analysis": scene,
        "primary_topics": topics[:24],
        "sensitivity_tags": list(extraction.sensitivity_tags)[:24],
    }
    score = score_entry_salience(
        EntrySalienceObservation(
            word_count=len((source_text if source_text is not None else raw_entry.raw_text or "").split()),
            entity_count=len(extraction.entities),
            person_count=sum(1 for entity in extraction.entities if entity.type == "person"),
            topic_count=len(topics),
            memory_count=len(extraction.memories),
            relationship_count=len(extraction.relationships),
            event_count=len(extraction.events),
            action_count=len(extraction.action_items),
            decision_count=sum(1 for memory in extraction.memories if memory.memory_type == "decision"),
            quote_count=max(len(extraction.quotes), len(extraction.attributed_quotes)),
            social_dynamic_count=len(extraction.social_dynamics),
            attributed_quote_count=len(extraction.attributed_quotes),
            causal_link_count=sum(1 for memory in extraction.memories if memory.motivation or memory.consequence)
            + sum(1 for event in extraction.events if event.purpose or event.outcome),
            open_loop_count=sum(1 for memory in extraction.memories if memory.open_loop)
            + sum(1 for dynamic in extraction.social_dynamics if dynamic.open_loop)
            + len(extraction.scene_analysis.unresolved_threads),
            high_stakes_count=sum(1 for memory in extraction.memories if memory.social_stakes == "high")
            + sum(1 for event in extraction.events if event.social_stakes == "high")
            + sum(1 for dynamic in extraction.social_dynamics if dynamic.social_stakes == "high"),
            user_importance=raw_entry.user_importance,
            source_kind=source_kind(raw_entry.source),
        )
    )
    raw_entry.contextual_salience = score.score
    raw_entry.salience_uncertainty = score.uncertainty
    raw_entry.salience_model_version = MODEL_VERSION
    raw_entry.salience_updated_at = _utcnow()
    raw_entry.analysis_json["salience"] = score.as_dict()
    raw_entry.analysis_json["stats"] = dict(stats)
    session.flush()

    entity_ids = entity_ids_for_entry(session, raw_entry.id)
    refresh_entity_salience(session, user_id=raw_entry.user_id, entity_ids=entity_ids)
    return score


def refresh_entity_salience(
    session: Session,
    *,
    user_id: str,
    entity_ids: set[str] | list[str] | None = None,
) -> int:
    """Recompute scores for selected entities, or every entity in a tenant."""

    query = session.query(Entity.id).filter(Entity.user_id == user_id)
    if entity_ids is not None:
        wanted = {value for value in entity_ids if value}
        if not wanted:
            return 0
        query = query.filter(Entity.id.in_(wanted))
    ids = [row[0] for row in query.all()]
    for entity_id in ids:
        _refresh_one_entity(session, user_id=user_id, entity_id=entity_id)
    return len(ids)


def refresh_salience_after_importance_change(session: Session, entry: RawEntry) -> SalienceScore:
    """Refresh an entry and every related card after a user changes its stars."""

    payload = dict(entry.analysis_json or {})
    previous = dict(payload.get("salience") or {})
    signals = previous.get("signals")
    if isinstance(signals, dict) and signals:
        score = rescore_entry_salience(signals, user_importance=entry.user_importance)
    else:
        score = _score_persisted_entry(session, entry)
    _write_entry_score(entry, score, payload=payload)
    refresh_entity_salience(
        session,
        user_id=entry.user_id,
        entity_ids=entity_ids_for_entry(session, entry.id),
    )
    return score


def backfill_salience(
    session: Session,
    *,
    user_id: str | None = None,
) -> dict[str, int]:
    """Populate derived scores for data created before the salience model."""

    query = session.query(RawEntry)
    if user_id:
        query = query.filter(RawEntry.user_id == user_id)
    entries = query.order_by(RawEntry.created_at_utc.asc()).all()
    entries_scored = 0
    user_ids = {entry.user_id for entry in entries}
    for entry in entries:
        prior_signals = dict((entry.analysis_json or {}).get("salience") or {}).get("signals")
        if entry.is_private and not isinstance(prior_signals, dict):
            # A private entry that predates an allowed extraction has no safe
            # plaintext available for a derived analysis backfill.
            continue
        if entry.contextual_salience is not None and entry.salience_model_version == MODEL_VERSION:
            continue
        if isinstance(prior_signals, dict) and prior_signals:
            score = rescore_entry_salience(prior_signals, user_importance=entry.user_importance)
        else:
            score = _score_persisted_entry(session, entry)
        payload = dict(entry.analysis_json or {})
        payload.setdefault("analysis_version", 1)
        payload["backfilled"] = True
        _write_entry_score(entry, score, payload=payload)
        entries_scored += 1

    entities_scored = 0
    for owner_id in user_ids:
        entities_scored += refresh_entity_salience(session, user_id=owner_id)
    session.commit()
    return {"entries_scored": entries_scored, "entities_scored": entities_scored}


def _refresh_one_entity(session: Session, *, user_id: str, entity_id: str) -> SalienceScore | None:
    entity = session.query(Entity).filter(Entity.user_id == user_id, Entity.id == entity_id).first()
    if entity is None:
        return None

    evidence = load_entity_evidence(session, user_id=user_id, entity_id=entity_id)
    entries = load_evidence_entries(session, user_id=user_id, entry_ids=evidence.entry_ids)
    score = score_entity_salience(build_entity_observation(entity, evidence, entries))
    entity.salience_score = score.score
    entity.salience_uncertainty = score.uncertainty
    entity.salience_signals_json = score.signals
    entity.salience_model_version = MODEL_VERSION
    entity.salience_updated_at = _utcnow()
    return score


def entity_ids_for_entry(session: Session, raw_entry_id: str) -> set[str]:
    ids = {
        row[0]
        for row in session.query(EntityMention.entity_id).filter(EntityMention.raw_entry_id == raw_entry_id).all()
        if row[0]
    }
    for subject_id, object_id in (
        session.query(Memory.subject_entity_id, Memory.object_entity_id)
        .filter(
            Memory.raw_entry_id == raw_entry_id,
        )
        .all()
    ):
        ids.update(value for value in (subject_id, object_id) if value)
    for source_id, target_id in (
        session.query(Relationship.source_entity_id, Relationship.target_entity_id)
        .filter(
            Relationship.raw_entry_id == raw_entry_id,
        )
        .all()
    ):
        ids.update(value for value in (source_id, target_id) if value)
    event_rows = (
        session.query(Event.id, Event.place_entity_id)
        .filter(
            Event.source_raw_entry_id == raw_entry_id,
        )
        .all()
    )
    event_ids = [event_id for event_id, _place_id in event_rows]
    ids.update(place_id for _event_id, place_id in event_rows if place_id)
    if event_ids:
        ids.update(
            row[0]
            for row in session.query(EventParticipant.entity_id)
            .filter(
                EventParticipant.event_id.in_(event_ids),
            )
            .all()
            if row[0]
        )
    return ids


def _score_persisted_entry(session: Session, entry: RawEntry) -> SalienceScore:
    mention_query = session.query(EntityMention).filter(
        EntityMention.user_id == entry.user_id,
        EntityMention.raw_entry_id == entry.id,
    )
    memory_query = session.query(Memory).filter(
        Memory.user_id == entry.user_id,
        Memory.raw_entry_id == entry.id,
    )
    analysis = dict(entry.analysis_json or {})
    stats = dict(analysis.get("stats") or {})
    topics = _normalized_topics(analysis.get("primary_topics") or [])
    word_count = 0 if entry.is_private else len((entry.raw_text or "").split())
    memory_rows = memory_query.all()
    attributed_quote_count, causal_link_count, open_loop_count, high_stakes_count = _persisted_narrative_counts(
        memory_rows,
        analysis,
    )
    return score_entry_salience(
        EntrySalienceObservation(
            word_count=word_count,
            entity_count=mention_query.count(),
            person_count=mention_query.join(Entity, Entity.id == EntityMention.entity_id)
            .filter(Entity.user_id == entry.user_id, Entity.type == "person")
            .count(),
            topic_count=len(topics),
            memory_count=len(memory_rows),
            relationship_count=session.query(Relationship)
            .filter(
                Relationship.user_id == entry.user_id,
                Relationship.raw_entry_id == entry.id,
            )
            .count(),
            event_count=session.query(Event)
            .filter(
                Event.user_id == entry.user_id,
                Event.source_raw_entry_id == entry.id,
            )
            .count(),
            action_count=session.query(ActionItem)
            .filter(
                ActionItem.user_id == entry.user_id,
                ActionItem.raw_entry_id == entry.id,
            )
            .count(),
            decision_count=sum(1 for memory in memory_rows if memory.memory_type == "decision"),
            quote_count=int(stats.get("quotes", 0) or 0),
            social_dynamic_count=int(stats.get("social_dynamics", 0) or 0),
            attributed_quote_count=attributed_quote_count,
            causal_link_count=causal_link_count,
            open_loop_count=open_loop_count,
            high_stakes_count=high_stakes_count,
            user_importance=entry.user_importance,
            source_kind=source_kind(entry.source),
        )
    )


def _persisted_narrative_counts(
    memories: list[Memory],
    analysis: dict[str, Any],
) -> tuple[int, int, int, int]:
    attributed = 0
    causal = 0
    open_loops = 0
    high_stakes = 0
    for memory in memories:
        metadata = dict(memory.structured_json or {})
        if memory.memory_type == "quote" or metadata.get("attributed_to") or metadata.get("speaker"):
            attributed += 1
        if (
            metadata.get("motivation")
            or metadata.get("consequence")
            or metadata.get("purpose")
            or metadata.get("outcome")
        ):
            causal += 1
        if metadata.get("open_loop"):
            open_loops += 1
        if str(metadata.get("social_stakes") or "").lower() == "high":
            high_stakes += 1
    scene = dict(analysis.get("scene_analysis") or {})
    open_loops += len(scene.get("unresolved_threads") or [])
    return attributed, causal, open_loops, high_stakes


def _write_entry_score(entry: RawEntry, score: SalienceScore, *, payload: dict[str, Any]) -> None:
    entry.contextual_salience = score.score
    entry.salience_uncertainty = score.uncertainty
    entry.salience_model_version = MODEL_VERSION
    entry.salience_updated_at = _utcnow()
    payload["salience"] = score.as_dict()
    entry.analysis_json = payload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
