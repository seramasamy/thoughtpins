import numpy as np
import pytest

from thoughtpins.memory.benchmark_retrieval import rank_documents_bm25
from thoughtpins.memory.research_retrieval import (
    LexicalIndex,
    Representation,
    fuse_rankings,
    stable_order,
    unit_vectors,
)


def test_index_matches_unchanged_historical_equation_and_ties() -> None:
    docs = ["Alice bought red apples.", "Bob ate blue berries.", "red red apple", "", "Alice bought red apples."]
    for query in ("red apples", "Alice red", "zzzz", "the and"):
        expected = rank_documents_bm25(query, docs)
        scores = LexicalIndex(docs).scores(query)
        assert stable_order(scores) == [i for i, _ in expected]
        assert scores[[i for i, _ in expected]] == pytest.approx([s for _, s in expected])


def test_duplicate_paths_and_channels_do_not_inflate_family_votes() -> None:
    base = {"sparse": ["a", "b"], "dense": ["b", "c"]}
    expected = fuse_rankings(base)
    assert fuse_rankings({"sparse": ["a", "a", "b"], "dense": ["b", "c"]}) == expected
    assert fuse_rankings({**base, "clone": ["a", "b"]}, families={"clone": "sparse"}) == expected
    assert [sid for sid, _ in expected] == ["b", "a", "c"]
    assert fuse_rankings({}) == []


def test_cosine_normalization_and_tie_identity_are_order_invariant() -> None:
    vectors = unit_vectors(np.array([[3, 4], [0, 2]]))
    assert np.sum(vectors * vectors, axis=1) == pytest.approx([1, 1])
    assert stable_order(np.array([0.5, 0.5]), ["b", "a"]) == [1, 0]
    with pytest.raises(ValueError):
        unit_vectors(np.array([[0, 0]]))


def test_context_boundary_is_bounded_and_retains_both_ends() -> None:
    rendered = Representation(max_bytes=100).render("START " + "日" * 200 + " END")
    assert len(rendered.encode()) <= 100
    assert rendered.startswith("START") and rendered.endswith("END")
    assert "omitted" in rendered
