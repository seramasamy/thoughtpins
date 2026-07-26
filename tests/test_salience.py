from __future__ import annotations

import json
from datetime import date
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "literary_salience_corpus.json"


def _entity_observation(row: dict):
    from thoughtpins.memory.salience import EntitySalienceObservation

    allowed = set(EntitySalienceObservation.__dataclass_fields__)
    return EntitySalienceObservation(**{key: value for key, value in row.items() if key in allowed})


def test_literary_corpus_ranks_recurring_protagonist_and_narrator_above_case_roles():
    from thoughtpins.memory.salience import score_entity_salience

    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ranked = sorted(
        (
            row["name"],
            score_entity_salience(_entity_observation(row), as_of=date(1905, 12, 31)),
        )
        for row in corpus["characters"]
    )
    ranked = sorted(ranked, key=lambda item: item[1].score, reverse=True)
    assert ranked[0][0] == "Sherlock Holmes"
    assert ranked[1][0] == "Dr. John Watson"
    assert ranked[0][1].tier == "central"
    assert ranked[1][1].tier in {"central", "notable"}
    assert ranked[-1][0] == "A Study in Scarlet client"
    assert ranked[0][1].uncertainty < ranked[-1][1].uncertainty


def test_thematic_recurrence_beats_a_single_vivid_reference():
    from thoughtpins.memory.salience import score_entity_salience

    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    themes = {
        row["name"]: score_entity_salience(_entity_observation(row), as_of=date(1905, 12, 31))
        for row in corpus["themes"]
    }
    assert themes["deduction"].score > themes["red herrings"].score
    assert themes["deduction"].signals["recurrence"] > themes["red herrings"].signals["recurrence"]


def test_manual_rating_is_bounded_and_monotonic():
    from thoughtpins.memory.salience import EntitySalienceObservation, score_entity_salience

    low = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=3,
            mention_count=8,
            direct_memory_count=4,
            supporting_memory_count=2,
            relationship_count=3,
            relationship_evidence_count=5,
            user_rating_mean=1,
            user_rating_count=1,
        )
    )
    high = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=3,
            mention_count=8,
            direct_memory_count=4,
            supporting_memory_count=2,
            relationship_count=3,
            relationship_evidence_count=5,
            user_rating_mean=5,
            user_rating_count=1,
        )
    )
    assert high.score > low.score
    assert 0 <= low.score <= 1
    assert 0 <= high.score <= 1
    assert high.score - low.score <= 0.10


def test_structural_role_beats_passive_name_frequency():
    from thoughtpins.memory.salience import EntitySalienceObservation, score_entity_salience

    passive = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=2,
            mention_count=40,
            supporting_memory_count=8,
            observed_evidence_count=12,
        )
    )
    active = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=3,
            mention_count=10,
            direct_memory_count=8,
            supporting_memory_count=2,
            relationship_count=4,
            relationship_evidence_count=7,
            event_count=4,
            agency_count=6,
            observed_evidence_count=20,
        )
    )
    assert active.score > passive.score
    assert active.signals["structural_role"] > passive.signals["structural_role"]


def test_temporal_and_source_persistence_distinguish_a_pattern_from_a_burst():
    from thoughtpins.memory.salience import EntitySalienceObservation, score_entity_salience

    burst = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=5,
            mention_count=15,
            direct_memory_count=6,
            supporting_memory_count=4,
            source_count=1,
            active_day_count=1,
            temporal_span_days=0,
            observed_evidence_count=20,
        )
    )
    durable = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=5,
            mention_count=15,
            direct_memory_count=6,
            supporting_memory_count=4,
            source_count=4,
            active_day_count=5,
            temporal_span_days=365,
            observed_evidence_count=20,
        )
    )
    assert durable.score > burst.score
    assert durable.signals["source_diversity"] > burst.signals["source_diversity"]
    assert durable.signals["temporal_persistence"] > burst.signals["temporal_persistence"]
    assert durable.uncertainty < burst.uncertainty


def test_duplicate_mentions_do_not_masquerade_as_independent_evidence():
    from thoughtpins.memory.salience import EntitySalienceObservation, score_entity_salience

    once = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=1,
            mention_count=1,
            direct_memory_count=1,
            observed_evidence_count=2,
        )
    )
    repeated = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=1,
            mention_count=100,
            direct_memory_count=1,
            observed_evidence_count=101,
        )
    )
    independent = score_entity_salience(
        EntitySalienceObservation(
            distinct_entry_count=8,
            mention_count=8,
            direct_memory_count=8,
            active_day_count=8,
            source_count=3,
            temporal_span_days=90,
            observed_evidence_count=16,
        )
    )
    assert repeated.uncertainty > independent.uncertainty
    assert once.uncertainty - repeated.uncertainty < 0.10


def test_versioned_weights_are_normalized_and_contributions_reconcile():
    from thoughtpins.memory.salience import (
        ENTITY_SIGNAL_WEIGHTS,
        ENTRY_SIGNAL_WEIGHTS,
        EntrySalienceObservation,
        score_entry_salience,
    )

    assert sum(ENTITY_SIGNAL_WEIGHTS.values()) == 1.0
    assert sum(ENTRY_SIGNAL_WEIGHTS.values()) == 1.0
    score = score_entry_salience(
        EntrySalienceObservation(
            word_count=80,
            entity_count=3,
            person_count=1,
            topic_count=2,
            memory_count=3,
            relationship_count=1,
            decision_count=1,
            user_importance=4,
        )
    )
    assert abs(score.score - sum(score.contributions.values())) < 0.00001
    assert score.model_version == "salience-v4"


def test_entry_salience_preserves_short_important_notes():
    from thoughtpins.memory.salience import EntrySalienceObservation, score_entry_salience

    short_important = score_entry_salience(
        EntrySalienceObservation(
            word_count=12,
            entity_count=1,
            person_count=1,
            memory_count=1,
            decision_count=1,
            user_importance=5,
        )
    )
    long_unrated = score_entry_salience(EntrySalienceObservation(word_count=900, entity_count=1, memory_count=1))
    assert short_important.score > 0.30
    assert short_important.score > long_unrated.score * 0.55


def test_salience_is_persisted_with_analysis_and_refreshes_entity(isolated_db):
    from datetime import datetime

    from thoughtpins.db import Entity, EntityMention, Memory, RawEntry, User
    from thoughtpins.llm import ExtractedEntity, ExtractedMemory, ExtractionResult, SceneAnalysis
    from thoughtpins.memory.salience_store import update_salience_for_entry
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = User(email="salience-integration@example.com")
        session.add(user)
        session.flush()
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 7, 12, 12, 0),
            local_date=date(2026, 7, 12),
            local_time="12:00",
            source="api",
            raw_text="Maya made a decision about the restore drill.",
            content_hash=hash_text("salience integration"),
            processed_status="processing",
            user_importance=5,
        )
        maya = Entity(user_id=user.id, type="person", canonical_name="Maya")
        session.add_all([raw, maya])
        session.flush()
        session.add(EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=maya.id, surface_text="Maya"))
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="decision",
                subject_entity_id=maya.id,
                text="Maya made a decision about the restore drill.",
                local_date=raw.local_date,
                confidence="observed_by_user",
            )
        )
        extraction = ExtractionResult(
            scene_analysis=SceneAnalysis(domain="work", primary_topics=["reliability", "memory"]),
            entry_summary="Maya made a decision about the restore drill.",
            entities=[ExtractedEntity(surface_name="Maya", type="person")],
            memories=[
                ExtractedMemory(
                    memory_type="decision", text="Maya made a decision about the restore drill.", subject="Maya"
                )
            ],
        )
        score = update_salience_for_entry(session, raw, extraction, {"memories": 1})
        session.commit()

        stored_raw = session.query(RawEntry).filter_by(id=raw.id).one()
        stored_entity = session.query(Entity).filter_by(id=maya.id).one()
        assert stored_raw.analysis_json["primary_topics"] == ["reliability", "memory"]
        assert stored_raw.contextual_salience == score.score
        assert stored_entity.salience_score is not None
        assert stored_entity.salience_model_version == "salience-v4"
        assert stored_entity.salience_signals_json["thematic_breadth"] > 0

        from thoughtpins.importance import set_entry_importance

        entry_score_before = stored_raw.contextual_salience
        entity_score_before = stored_entity.salience_score
        set_entry_importance(session, user_id=user.id, entry_id=raw.id, value=1)
        session.commit()
        session.refresh(stored_raw)
        session.refresh(stored_entity)
        assert stored_raw.contextual_salience < entry_score_before
        assert stored_entity.salience_score < entity_score_before
        assert stored_raw.salience_model_version == "salience-v4"
    finally:
        session.close()
