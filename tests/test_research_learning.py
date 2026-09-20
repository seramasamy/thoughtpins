import itertools
import math

import numpy as np
import pytest

from thoughtpins.memory.research_learning import (
    FEATURE_NAMES,
    LearningParameters,
    apply_ranker,
    fit_ranker,
    loss_gradient,
    pairwise_rows,
)
from thoughtpins.memory.research_selection import coverage_value, greedy_coverage


def test_analytic_gradient_matches_finite_difference_and_query_weights() -> None:
    rng = np.random.default_rng(7)
    x = [rng.uniform(size=(n, len(FEATURE_NAMES))) for n in (3, 7)]
    y = [np.array([1, 0, 0]), np.array([1, 1, 0, 0, 0, 0, 0])]
    d, pw = pairwise_rows(x, y)
    assert pw[:2].sum() == pytest.approx(0.5)
    params = LearningParameters()
    w = np.array(params.prior)
    step = 1e-6
    numerical = np.array(
        [
            (
                loss_gradient(w + direction * step, d, pw, params)[0]
                - loss_gradient(w - direction * step, d, pw, params)[0]
            )
            / (2 * step)
            for direction in np.eye(len(w))
        ]
    )
    error = np.linalg.norm(numerical - loss_gradient(w, d, pw, params)[1])
    assert error < 1e-6


def test_bounded_fit_agrees_across_seeds_and_rejects_wrong_schema() -> None:
    pytest.importorskip("scipy", reason="Optional scientific fitting dependency")
    x = np.zeros((3, len(FEATURE_NAMES)))
    x[:, 0] = [1, 0.3, 0.1]
    y = np.array([1, 0, 0])
    models = [fit_ranker([x], [y], parameters=LearningParameters(), seed=i) for i in (10, 20, 30)]
    assert max(np.max(np.abs(np.array(m["weights"]) - models[0]["weights"])) for m in models) < 1e-5
    assert np.argmax(apply_ranker(x, models[0])) == 0
    broken = {**models[0], "schema": ["wrong"]}
    with pytest.raises(ValueError, match="schema"):
        apply_ranker(x, broken)


def test_coverage_diminishing_returns_and_tiny_bruteforce_bound() -> None:
    rng = np.random.default_rng(42)
    for _ in range(20):
        p, r, a = rng.uniform(size=(5, 3)), rng.uniform(size=5), rng.uniform(size=3)
        f = lambda s, p=p, r=r, a=a: coverage_value(list(s), p, r, a, 0.3)
        assert f([]) == 0
        for size in range(3):
            for subset in itertools.combinations(range(4), size):
                superset = sorted(set(subset) | {3})
                assert f([*subset, 4]) - f(subset) >= f([*superset, 4]) - f(superset) - 1e-12
                assert f([*subset, 4]) >= f(subset)
        selected = greedy_coverage(list("abcde"), p, r, a, eta=0.3, limit=2)
        optimum = max(f(s) for s in itertools.combinations(range(5), 2))
        assert f(selected) >= (1 - 1 / math.e) * optimum


def test_coverage_rejects_negative_penalty_and_handles_irrelevant_facets() -> None:
    p = np.array([[1, 0], [0, 0]])
    assert greedy_coverage(["a", "b"], p, np.array([1, 0]), np.ones(2), eta=1, limit=1) == [0]
    with pytest.raises(ValueError, match="nonnegative"):
        greedy_coverage(["a", "b"], p, np.array([1, 0]), np.ones(2), eta=-1, limit=1)
