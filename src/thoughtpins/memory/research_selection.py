"""Fixed-facet monotone coverage surrogate under a cardinality constraint.

The cardinality guarantee is about this surrogate, not answer correctness. No
token-cost ratio, changing facet score or negative diversity penalty is used.
"""

from __future__ import annotations

import math

import numpy as np


def _validate(support: np.ndarray, relevance: np.ndarray, facet_weights: np.ndarray, eta: float) -> None:
    if support.ndim != 2 or support.shape != (len(relevance), len(facet_weights)):
        raise ValueError("Coverage arrays must align")
    if (
        not np.isfinite(support).all()
        or not np.isfinite(relevance).all()
        or not np.isfinite(facet_weights).all()
        or np.any(support < 0)
        or np.any(support > 1)
        or np.any(relevance < 0)
        or np.any(facet_weights < 0)
        or not math.isfinite(eta)
        or eta < 0
    ):
        raise ValueError("Monotone coverage requires fixed nonnegative bounded support")


def coverage_value(
    selected: list[int], support: np.ndarray, relevance: np.ndarray, facet_weights: np.ndarray, eta: float
) -> float:
    _validate(support, relevance, facet_weights, eta)
    if len(set(selected)) != len(selected) or any(i < 0 or i >= len(relevance) for i in selected):
        raise ValueError("Selection must be a unique valid subset")
    if not selected:
        return 0.0
    return float(facet_weights @ (1 - np.prod(1 - support[selected], axis=0)) + eta * relevance[selected].sum())


def greedy_coverage(
    ids: list[str], support: np.ndarray, relevance: np.ndarray, facet_weights: np.ndarray, *, eta: float, limit: int
) -> list[int]:
    _validate(support, relevance, facet_weights, eta)
    if len(ids) != len(relevance) or len(set(ids)) != len(ids):
        raise ValueError("Expected unique candidate identities")
    uncovered = np.ones(len(facet_weights))
    remaining = set(range(len(ids)))
    selected = []
    for _ in range(min(max(0, limit), len(ids))):
        gains = support @ (facet_weights * uncovered) + eta * relevance
        best = min(remaining, key=lambda i: (-gains[i], ids[i]))
        selected.append(best)
        remaining.remove(best)
        uncovered *= 1 - support[best]
    return selected
