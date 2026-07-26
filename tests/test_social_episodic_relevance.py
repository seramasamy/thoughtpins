from __future__ import annotations

import random

import pytest

from thoughtpins.memory.evidence_plan import build_response_evidence_plan
from thoughtpins.memory.ranking import RankingPolicy, rerank_results
from thoughtpins.memory.search_types import SearchResult
from thoughtpins.memory.social_relevance import (
    FACET_CAUSE,
    FACET_PEOPLE,
    FACET_PLACE,
    FACET_STATEMENT,
    FACET_UNCERTAINTY,
    analyze_social_query,
    score_social_evidence,
)


def test_social_query_analysis_identifies_human_scene_facets() -> None:
    intent = analyze_social_query("Who said the rumor about Eli, where were they, and why?")

    assert {FACET_PEOPLE, FACET_STATEMENT, FACET_PLACE, FACET_CAUSE, FACET_UNCERTAINTY} <= intent.facets
    assert intent.social_focus == 1.0
    assert intent.asks_about_uncertainty is True


def test_social_query_analysis_extracts_the_speaker_slot_not_a_title_name() -> None:
    intent = analyze_social_query("What did Watson say in The Adventures of Sherlock Holmes?")

    assert intent.requested_person == "Watson"


def test_social_query_analysis_extracts_a_named_rumor_source() -> None:
    intent = analyze_social_query("What rumor did Marcus share about Daniel at Westbridge Library?")

    assert intent.requested_person == "Marcus"


def test_uncertain_claim_requires_attribution_to_avoid_factualization_risk() -> None:
    intent = analyze_social_query("what rumor did Nora mention?")
    attributed = _result(
        "attributed",
        0.70,
        "Nora said she heard Eli might leave.",
        confidence="hearsay_from_person",
        metadata={"attributed_to": "Nora", "people_involved": ["Nora", "Eli"]},
    )
    orphaned = _result(
        "orphaned",
        0.70,
        "Eli might leave.",
        confidence="hearsay_from_person",
    )

    attributed_features = score_social_evidence(attributed, intent)
    orphaned_features = score_social_evidence(orphaned, intent)

    assert attributed_features.factualization_risk == 0.0
    assert orphaned_features.factualization_risk == 1.0
    assert attributed_features.utility > orphaned_features.utility


def test_attributed_social_evidence_breaks_a_close_relevance_tie() -> None:
    query = "what did Nora say about Eli at Halcyon House?"
    attributed = _result(
        "attributed",
        0.70,
        "Nora said she heard Eli might leave the paper.",
        memory_type="quote",
        confidence="hearsay_from_person",
        metadata={
            "attributed_to": "Nora",
            "people_involved": ["Nora", "Eli"],
            "place": "Halcyon House",
            "epistemic_status": "hearsay_from_person",
            "social_stakes": "high",
        },
    )
    generic = _result("generic", 0.71, "Nora and Eli were associated with Halcyon House.")

    ranked = rerank_results([generic, attributed], query=query, limit=2)

    assert ranked[0].memory_id == "attributed"
    assert ranked[0].ranking_signals["attribution_quality"] == 1.0
    assert ranked[0].ranking_signals["social_bonus"] > 0.0


def test_named_person_match_is_scored_separately_from_a_shared_source_title() -> None:
    target = _result(
        "target",
        0.5,
        "I will stay.",
        memory_type="quote",
        metadata={"attributed_to": "Eli North", "people_involved": ["Eli North"]},
    )
    decoy = _result(
        "decoy",
        0.5,
        "We should leave.",
        memory_type="quote",
        metadata={"attributed_to": "Maya Stone", "people_involved": ["Maya Stone"]},
    )
    target.source_title = decoy.source_title = "A Very Long Shared Source Title"

    ranked = rerank_results(
        [decoy, target], query="What did Eli North say in A Very Long Shared Source Title?", limit=2
    )

    assert ranked[0].memory_id == "target"
    assert ranked[0].ranking_signals["social_identity_match"] == 1.0
    assert ranked[1].ranking_signals["social_identity_match"] == 0.0


def test_star_importance_cannot_overrule_a_large_query_relevance_gap() -> None:
    target = _result("target", 0.92, "Celia said the blue canvases held together best.")
    target.user_importance = 1
    unrelated = _result("unrelated", 0.25, "A highly rated grocery list.")
    unrelated.user_importance = 5

    ranked = rerank_results([unrelated, target], query="why did Celia choose the blue canvases?", limit=2)

    assert ranked[0].memory_id == "target"
    assert (
        ranked[0].ranking_signals["relevance_before_importance"]
        > ranked[1].ranking_signals["relevance_before_importance"]
    )


def test_star_importance_is_identity_gated_for_a_specific_social_scene() -> None:
    query = "what rumor did Marcus share about Daniel at Westbridge Library and what happened afterward?"
    target = _result(
        "target",
        0.68,
        "At Westbridge Library, Marcus said Daniel missed rehearsal because the draft was mocked; "
        "afterward the director offered another slot.",
        memory_type="quote",
        confidence="hearsay_from_person",
        metadata={
            "attributed_to": "Marcus",
            "people_involved": ["Marcus", "Daniel"],
            "place": "Westbridge Library",
            "motivation": "the draft was mocked",
            "consequence": "the director offered another slot",
        },
    )
    vague_starred = _result(
        "vague",
        0.74,
        "A highly rated old note mentioned Marcus and Daniel without describing the scene.",
    )
    vague_starred.user_importance = 5

    ranked = rerank_results([vague_starred, target], query=query, limit=2)

    assert ranked[0].memory_id == "target"
    assert ranked[0].ranking_signals["importance_query_gate"] > ranked[1].ranking_signals["importance_query_gate"]


def test_narrative_coverage_selects_distinct_scene_facets() -> None:
    query = "who said it, where, and why did it happen?"
    candidates = [
        _result(
            "speaker",
            0.86,
            "Ava explained what happened.",
            memory_type="quote",
            metadata={"attributed_to": "Ava", "people_involved": ["Ava", "Sam"]},
        ),
        _result(
            "place", 0.73, "The conversation happened at Westbridge Library.", metadata={"place": "Westbridge Library"}
        ),
        _result(
            "cause",
            0.72,
            "Sam skipped rehearsal because an older student mocked his draft.",
            metadata={"motivation": "He was mocked."},
        ),
        _result(
            "duplicate", 0.80, "Ava repeated the explanation.", memory_type="quote", metadata={"attributed_to": "Ava"}
        ),
    ]

    ranked = rerank_results(candidates, query=query, limit=3)
    covered = set().union(*(score_social_evidence(item, analyze_social_query(query)).facets for item in ranked))

    assert {FACET_PEOPLE, FACET_STATEMENT, FACET_PLACE, FACET_CAUSE} <= covered
    assert {item.memory_id for item in ranked} >= {"speaker", "place", "cause"}


def test_response_plan_retains_speaker_status_place_and_provenance() -> None:
    result = _result(
        "rumor",
        0.91,
        "Nora said she heard Eli might leave.",
        confidence="hearsay_from_person",
        metadata={"attributed_to": "Nora", "people_involved": ["Nora", "Eli"], "place": "Halcyon House"},
    )
    result.source_provenance = "raw_entry:abc123"

    rendered = build_response_evidence_plan("what rumor did Nora share and where?", [result]).render()

    assert "status=hearsay_from_person" in rendered
    assert "speaker=Nora" in rendered
    assert "people=Nora, Eli" in rendered
    assert "place=Halcyon House" in rendered
    assert "source=raw_entry:abc123" in rendered
    assert "Do not restate them as verified facts" in rendered


def test_non_social_query_does_not_receive_social_ranking_bonus() -> None:
    result = _result(
        "recipe",
        0.75,
        "The lentil stew uses cumin and chickpeas.",
        metadata={"attributed_to": "Maya", "social_stakes": "high"},
    )

    ranked = rerank_results([result], query="lentil stew ingredients", limit=1)

    assert ranked[0].ranking_signals["social_focus"] == 0.0
    assert ranked[0].ranking_signals["social_bonus"] == 0.0


def test_ranking_is_deterministic_and_bounded_across_random_candidate_pools() -> None:
    rng = random.Random(20260721)
    for pool_index in range(50):
        pool = [
            _result(
                f"{pool_index}-{index}",
                rng.random(),
                f"Person {index} said detail {rng.randrange(12)} at place {rng.randrange(5)}.",
                memory_type=rng.choice(["observation", "quote", "social_dynamic", "decision"]),
                confidence=rng.choice(
                    ["observed_by_user", "user_reported", "hearsay_from_person", "inferred_by_model"]
                ),
                metadata={
                    "attributed_to": f"Person {index}" if rng.random() > 0.35 else "",
                    "social_stakes": rng.choice(["low", "medium", "high"]),
                    "open_loop": rng.random() > 0.8,
                },
            )
            for index in range(20)
        ]
        first = rerank_results(pool, query="who said the rumor, where, and why?", limit=8)
        replay = [_copy_result(item) for item in pool]
        second = rerank_results(replay, query="who said the rumor, where, and why?", limit=8)

        assert [item.memory_id for item in first] == [item.memory_id for item in second]
        assert all(0.0 <= item.score <= 1.0 for item in first)
        assert all(0.0 <= value <= 1.0 for item in first for value in item.ranking_signals.values())


def test_attributed_quotes_are_persisted_as_atomic_memories(isolated_db) -> None:
    from datetime import date

    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.ingestion.storage import store_extraction
    from thoughtpins.llm import AttributedQuote, ExtractedEntity, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = User(email="quote-test@example.local")
        session.add(user)
        session.flush()
        raw = RawEntry(
            user_id=user.id,
            local_date=date(2026, 7, 21),
            raw_text="Nora said Eli might leave.",
            content_hash=hash_text("attributed quote persistence"),
            processed_status="processing",
        )
        session.add(raw)
        session.flush()
        extraction = ExtractionResult(
            entities=[
                ExtractedEntity(surface_name="Nora", type="person"),
                ExtractedEntity(surface_name="Eli", type="person"),
            ],
            attributed_quotes=[
                AttributedQuote(
                    speaker="Nora",
                    quote="Eli might leave.",
                    is_exact=True,
                    people_discussed=["Eli"],
                    confidence="hearsay_from_person",
                    epistemic_status="hearsay",
                    social_stakes="high",
                )
            ],
        )

        stats = store_extraction(session, raw, extraction, raw.local_date, raw.raw_text)
        session.flush()
        stored = session.query(Memory).filter(Memory.raw_entry_id == raw.id, Memory.memory_type == "quote").one()

        assert stats["attributed_quotes"] == 1
        assert stored.subject_entity.canonical_name == "Nora"
        assert stored.confidence == "hearsay_from_person"
        assert stored.structured_json["attributed_to"] == "Nora"
        assert stored.structured_json["people_involved"] == ["Nora", "Eli"]
    finally:
        session.close()


def test_ranking_policy_can_ablate_social_signals() -> None:
    result = _result(
        "social",
        0.7,
        "Nora said she heard Eli might leave.",
        memory_type="quote",
        confidence="hearsay_from_person",
        metadata={"attributed_to": "Nora", "people_involved": ["Nora", "Eli"]},
    )

    ranked = rerank_results(
        [result],
        query="what rumor did Nora share?",
        limit=1,
        policy=RankingPolicy(name="ablation", social_evidence=False, narrative_coverage=False),
    )

    assert ranked[0].ranking_signals["policy_social_evidence"] == 0.0
    assert ranked[0].ranking_signals["social_bonus"] == 0.0


@pytest.mark.parametrize("force_full", [False, True])
def test_context_package_includes_attributed_response_plan(isolated_db, monkeypatch, force_full: bool) -> None:
    from thoughtpins.config import config
    from thoughtpins.memory import search as memory_search
    from thoughtpins.memory.context_package import build_memory_context_package
    from thoughtpins.memory.eval import seed_memory_infra_fixture
    from thoughtpins.store import get_session

    class EmptyVectorStore:
        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory_search, "get_vector_store", lambda: EmptyVectorStore())
    monkeypatch.setattr(config, "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    monkeypatch.setattr(type(config), "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    session = get_session()
    try:
        user_id = seed_memory_infra_fixture(session)
        context = build_memory_context_package(
            "what rumor did Nora share about Eli and what happened later?",
            session,
            user_id=user_id,
            include_private=True,
            include_vault=False,
            force_full=force_full,
        )

        assert "QUERY-CONDITIONED RESPONSE EVIDENCE PLAN" in context
        assert "speaker=Nora" in context
        assert "status=hearsay_from_person" in context
        assert "Nora retracted" in context
    finally:
        session.close()


def _result(
    memory_id: str,
    score: float,
    text: str,
    *,
    memory_type: str = "observation",
    confidence: str = "observed_by_user",
    metadata: dict | None = None,
) -> SearchResult:
    return SearchResult(
        memory_id=memory_id,
        text=text,
        memory_type=memory_type,
        local_date="2026-07-21",
        confidence=confidence,
        sensitivity="personal",
        source_entry_id=f"entry-{memory_id}",
        score=score,
        evidence_text=text,
        evidence_metadata=dict(metadata or {}),
        retrieval_sources=["keyword"],
        source_ranks={"keyword": 1},
    )


def _copy_result(result: SearchResult) -> SearchResult:
    return SearchResult(
        memory_id=result.memory_id,
        text=result.text,
        memory_type=result.memory_type,
        local_date=result.local_date,
        confidence=result.confidence,
        sensitivity=result.sensitivity,
        source_entry_id=result.source_entry_id,
        score=float(result.ranking_signals.get("base", result.score)),
        evidence_text=result.evidence_text,
        evidence_metadata=dict(result.evidence_metadata),
        retrieval_sources=list(result.retrieval_sources),
        source_ranks=dict(result.source_ranks),
    )
