from __future__ import annotations

import pytest

from thoughtpins.memory.evaluation_metrics import (
    aggregate_retrieval_metrics,
    evaluate_ranked_results,
)
from thoughtpins.memory.ranking import RankingPolicy, RankingWeights, clone_candidates_for_rerank, rerank_results
from thoughtpins.memory.search_types import SearchResult


def test_metrics_deduplicate_retrieval_channels_by_source_event() -> None:
    results = [
        _result("memory-a", "entry-a", 0.96, "violet keystone", source="keyword"),
        _result("graph-a", "entry-a", 0.94, "same event through graph", source="sql_graph"),
        _result("memory-b", "entry-b", 0.80, "amber compass", source="vector"),
    ]

    metrics = evaluate_ranked_results(
        results,
        relevance_by_source_entry={"entry-a": 2.0, "entry-b": 1.0},
        expected_terms=("violet keystone", "amber compass"),
        cutoff=10,
    )

    assert metrics.retrieved_unique_items == 2
    assert metrics.relevant_retrieved == 2
    assert metrics.recall_at_k == 1.0
    assert metrics.average_precision_at_k == 1.0
    assert metrics.ndcg_at_k == 1.0
    assert metrics.evidence_coverage == 1.0


def test_metrics_expose_rank_and_score_separation_failures() -> None:
    metrics = evaluate_ranked_results(
        [
            _result("decoy", "entry-decoy", 0.91, "generic dinner note"),
            _result("answer", "entry-answer", 0.89, "no phones at Koyo Ramen"),
        ],
        relevance_by_source_entry={"entry-answer": 1.0},
        expected_terms=("Koyo Ramen",),
        cutoff=10,
    )

    assert metrics.reciprocal_rank == 0.5
    assert metrics.ndcg_at_k == pytest.approx(0.63093)
    assert metrics.score_margin == pytest.approx(-0.02)
    assert aggregate_retrieval_metrics([metrics]).worst_case_ndcg_at_k == metrics.ndcg_at_k


def test_ranking_policy_replay_starts_from_recorded_channel_score() -> None:
    candidate = _result("answer", "entry-answer", 0.98, "Maya mentioned orange peel")
    candidate.ranking_signals = {"base": 0.41, "final": 0.98}

    replay = clone_candidates_for_rerank([candidate])
    ranked = rerank_results(
        replay,
        query="what did Maya mention?",
        limit=1,
        policy=RankingPolicy(name="without-lexical", lexical_evidence=False),
    )

    assert ranked[0].ranking_signals["base"] == 0.41
    assert ranked[0].ranking_policy == "without-lexical"
    assert ranked[0].ranking_signals["policy_lexical"] == 0.0


def test_ranking_policy_rejects_invalid_diversity_weight() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        RankingPolicy(name="invalid", diversity_lambda=1.1)


def test_ranking_weights_reject_unbounded_tie_breakers() -> None:
    with pytest.raises(ValueError, match="temporal_query"):
        RankingWeights(temporal_query=0.5)


def test_single_channel_unique_candidates_keep_the_retriever_order() -> None:
    candidates = [
        _result("first", "entry-first", 0.91, "specific career preference in finance"),
        _result("second", "entry-second", 0.89, "specific career preference in design"),
        _result("third", "entry-third", 0.70, "unrelated note"),
    ]

    ranked = rerank_results(candidates, query="What career preference did I mention?", limit=3)

    assert [item.memory_id for item in ranked] == ["first", "second", "third"]


def test_multiple_retrieval_channels_still_enable_diversification() -> None:
    first = _result("first", "entry-first", 0.91, "Maya described the project", source="keyword")
    first.retrieval_sources.append("vector")
    second = _result("second", "entry-second", 0.89, "The meeting happened at Koyo", source="keyword")

    ranked = rerank_results([first, second], query="Who was involved and where?", limit=2)

    assert all(item.ranking_signals["policy_adaptive_diversity"] == 1.0 for item in ranked)


def _result(
    memory_id: str,
    source_entry_id: str,
    score: float,
    text: str,
    *,
    source: str = "keyword",
) -> SearchResult:
    return SearchResult(
        memory_id=memory_id,
        text=text,
        memory_type="observation",
        local_date="2026-07-15",
        confidence="observed_by_user",
        sensitivity="personal",
        source_entry_id=source_entry_id,
        score=score,
        evidence_text=text,
        retrieval_sources=[source],
        source_ranks={source: 1},
    )
