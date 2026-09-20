import numpy as np

from thoughtpins.memory.research_data import ResearchQuery, ResearchSource
from thoughtpins.memory.research_engine import ResearchIndex


def test_offline_engine_has_no_judgment_dependency_and_is_repeatable() -> None:
    sources = [
        ResearchSource("a", "user: I play violin.", "2024-01-01"),
        ResearchSource("b", "user: I bake bread.", "2025-01-01"),
    ]
    index = ResearchIndex(sources, np.array([[1.0, 0.0], [0.0, 1.0]]))
    q = ResearchQuery("q", "Which instrument do I play?", "fixture", "2026-01-01")
    first = index.rank(q, np.array([1.0, 0.0]), k1=1.2, b=0.25)
    second = index.rank(q, np.array([1.0, 0.0]), k1=1.2, b=0.25)
    assert first["arms"] == second["arms"]
    assert all(ids[0] == "a" for ids in first["arms"].values())


def test_missing_dense_channel_does_not_fabricate_ranks() -> None:
    index = ResearchIndex([ResearchSource("a", "red apples"), ResearchSource("b", "blue berries")], None)
    result = index.rank(ResearchQuery("q", "red apples", "fixture"), None, k1=1.2, b=0.25, include_current=False)
    assert result["dense_available"] is False
    assert result["arms"]["B3"] == []
    assert result["arms"]["B4"] == result["arms"]["B1"]
