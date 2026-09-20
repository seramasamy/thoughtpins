import numpy as np

from thoughtpins.memory.research_data import ResearchSource
from thoughtpins.memory.research_features import query_facets, query_features


def features(query, sources):
    return query_features(
        query,
        sources,
        sparse=[0.5] * len(sources),
        dense=[0.5] * len(sources),
        sparse_ranks=list(range(1, len(sources) + 1)),
        dense_ranks=list(range(1, len(sources) + 1)),
    )


def test_time_corrections_and_attribution_are_query_conditional() -> None:
    sources = [
        ResearchSource("a", "assistant: I suggest a violin.\nuser: I play the flute.", "2025-01-01"),
        ResearchSource("b", "user: Correction, I changed to the violin. I now play it.", "2026-01-01"),
    ]
    plain = features("Which instrument do I play?", sources)
    assert np.all(plain[:, 5] == 0) and np.all(plain[:, 7] == 0)
    assert features("What do I play now?", sources)[1, 7] > 0
    assert features("What did I play in 2025?", sources)[:, 5].tolist() == [1, 0]
    assert features("What did the assistant suggest?", sources)[0, 6] > 0


def test_unknown_metadata_is_neutral_and_irrelevant_facets_are_gated() -> None:
    sources = [ResearchSource("a", "a vague note"), ResearchSource("b", "red apples blue berries")]
    assert features("What happened in 2024?", sources)[0, 5] == 0
    support, weights = query_facets("red apples", sources, np.array([1, 0.1]), gate=0.2)
    assert not support.any()
    assert sum(weights) == 1
