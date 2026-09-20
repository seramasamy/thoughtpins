import numpy as np
import pytest

from thoughtpins.memory.research_retrieval import LexicalIndex
from thoughtpins.memory.research_robust import PassageIndex, build_pairs, fit, normalize, objective, score, tempered


def test_gradient_independent_centered_differences():
    rng = np.random.default_rng(920)
    pairs = {str(i): (rng.normal(size=(17 + i, 4)), rng.uniform(0.1, 1, size=17 + i)) for i in range(3)}
    risk = {"0": 0.5, "1": 0.3, "2": 0.2}
    w = np.array([0.4, 0.3, 0.2, 0.1])
    prior = np.array([1.0, 0, 0, 0])
    for temp in (0.1, 1.0):
        _, grad = objective(w, pairs, risk, 0.1, temp, prior)
        numeric = []
        for j in range(4):
            shift = np.eye(4)[j] * 1e-6
            numeric.append(
                (
                    objective(w + shift, pairs, risk, 0.1, temp, prior)[0]
                    - objective(w - shift, pairs, risk, 0.1, temp, prior)[0]
                )
                / 2e-6
            )
        np.testing.assert_allclose(grad, numeric, rtol=1e-6, atol=1e-7)


def test_known_convex_solution_and_query_weights():
    cases = [
        {
            "features": [[0, 1, 0, 0], [1, 0, 0, 0], [0.5, 0, 0, 0]],
            "positive": [0],
            "baseline_order": [1, 2, 0],
            "dataset": "longmemeval",
            "group": str(i),
            "risk_group": "lme",
            "long_query": bool(i % 2),
        }
        for i in range(8)
    ]
    pairs = build_pairs(cases)
    assert pairs["lme"][1].sum() == 8
    config = fit(cases, regularization=0.01, conditional=True)
    assert config["weights"][1] > 0.99 and config["weights"][5] > 0.99
    assert score(np.asarray(cases[0]["features"]), config).argmax() == 0


def test_invalid_objective_and_model_schema_fail_closed():
    with pytest.raises(ValueError):
        fit([])
    with pytest.raises(ValueError):
        objective(np.ones(4), {}, {}, 0.1, 0, np.ones(4))
    with pytest.raises(ValueError):
        score(np.ones((2, 4)), {"weights": [1, 0, 0, 0], "features": ["wrong"]})
    assert PassageIndex([]).scores("absent").shape == (0,)


def test_bm25_equivalence_and_normalization():
    texts = ["alpha beta alpha", "beta gamma delta", "no matching thing"]
    idx = LexicalIndex(texts)
    np.testing.assert_allclose(tempered(idx, "alpha gamma"), idx.scores("alpha gamma"))
    np.testing.assert_array_equal(normalize(np.zeros(4)), np.zeros(4))
    with pytest.raises(ValueError):
        normalize([float("nan")])


def test_late_passage_evidence_and_empty_sources():
    idx = PassageIndex(["ordinary words " * 300 + "unique target fact", "unrelated text", ""])
    assert idx.scores("unique target fact").argmax() == 0
    assert np.isfinite(idx.scores("absent")).all()


def test_source_input_permutation_equivariance():
    texts = ["alpha beta gamma", "delta alpha", "gamma gamma epsilon"]
    a = PassageIndex(texts).scores("delta epsilon")
    b = PassageIndex(texts[::-1]).scores("delta epsilon")[::-1]
    np.testing.assert_allclose(a, b)
