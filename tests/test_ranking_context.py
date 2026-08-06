"""The rerank-scoped cache must be a pure speedup, never a behaviour change.

Reranking touches each candidate several times — scoring, then diversification,
then each coverage repair — and query interpretation and a candidate's facets
are invariant across those passes. Computing them once is worth roughly a 2x
rerank speedup, but only if the memo returns exactly what recomputation would.
"""

from __future__ import annotations

import random
from datetime import date

import pytest

from thoughtpins.memory.ranking import _RankingContext, rerank_results
from thoughtpins.memory.search_types import SearchResult
from thoughtpins.memory.social_relevance import analyze_social_query, candidate_facets
from thoughtpins.memory.temporal_relevance import parse_temporal_window

QUERY = "what did Steve and Sarah say about the festival last week and why did I decide that"
AS_OF = date(2026, 7, 27)


def make_candidate(index: int, *, rng: random.Random) -> SearchResult:
    return SearchResult(
        memory_id=f"m{index}",
        text=f"Talked with Steve about plan {index}; Sarah said she was excited",
        memory_type="event",
        local_date="2026-07-20",
        confidence="observed_by_user",
        sensitivity="personal",
        source_entry_id=f"e{index}",
        score=rng.random(),
        evidence_text="Steve was disappointed; Sarah was excited about the festival",
        entity_names=["Steve", "Sarah"],
        retrieval_sources=["vector", "keyword"],
        source_ranks={"vector": index, "keyword": index},
    )


def pool(size: int, seed: int = 42) -> list[SearchResult]:
    rng = random.Random(seed)
    return [make_candidate(i, rng=rng) for i in range(size)]


# ------------------------------------------------------------------ the memo


def test_the_context_agrees_with_recomputing_query_interpretation():
    context = _RankingContext.build(QUERY, AS_OF)
    assert context.social_intent == analyze_social_query(QUERY)
    assert context.temporal_window == parse_temporal_window(QUERY, as_of=AS_OF)


def test_memoised_facets_equal_a_direct_computation():
    """The property the speedup rests on."""
    context = _RankingContext.build(QUERY, AS_OF)
    for candidate in pool(25):
        assert context.facets(candidate) == candidate_facets(candidate), candidate.memory_id


def test_a_repeated_lookup_returns_the_same_value():
    context = _RankingContext.build(QUERY, AS_OF)
    candidate = pool(1)[0]
    assert context.facets(candidate) == context.facets(candidate) == candidate_facets(candidate)


def test_distinct_candidates_do_not_share_a_memo_entry():
    """The cache is keyed on memory_id; two candidates must not collide."""
    context = _RankingContext.build(QUERY, AS_OF)
    talky = make_candidate(1, rng=random.Random(1))
    quiet = SearchResult(
        memory_id="m2",
        text="rained all afternoon",
        memory_type="observation",
        local_date="2026-07-20",
        confidence="observed_by_user",
        sensitivity="personal",
        source_entry_id="e2",
        score=0.4,
        evidence_text="rained all afternoon",
    )
    assert context.facets(talky) == candidate_facets(talky)
    assert context.facets(quiet) == candidate_facets(quiet)
    assert context.facets(talky) != context.facets(quiet)


def test_a_context_is_not_shared_between_queries():
    """Memoised facets are query-independent, but the intent is not. A context
    built for one query must never answer for another."""
    first = _RankingContext.build("who did I meet at the bar", AS_OF)
    second = _RankingContext.build("why did I quit", AS_OF)
    assert first.social_intent != second.social_intent


# ------------------------------------------------------------- no drift, ever


@pytest.mark.parametrize("size", [5, 30, 120])
def test_reranking_is_reproducible_for_a_fixed_pool(size: int):
    first = rerank_results(pool(size), query=QUERY, limit=12, as_of_date=AS_OF)
    second = rerank_results(pool(size), query=QUERY, limit=12, as_of_date=AS_OF)
    assert [c.memory_id for c in first] == [c.memory_id for c in second]
    assert [c.score for c in first] == [c.score for c in second]


def test_scores_stay_inside_their_bounds_after_caching():
    for candidate in rerank_results(pool(60), query=QUERY, limit=20, as_of_date=AS_OF):
        assert 0.0 <= candidate.score <= 1.0, candidate.memory_id
