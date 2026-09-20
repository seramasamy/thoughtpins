"""Provider-neutral experimental scoring, outside the production ranker."""

import math
from collections import defaultdict
from typing import Any

import numpy as np

from thoughtpins.memory.benchmark_retrieval import _tokens
from thoughtpins.memory.research_retrieval import LexicalIndex

FEATURE_NAMES = ("whole_bm25", "passage_bm25", "dense", "idf_squared")


def normalize(values: np.ndarray | list[float]) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite scores")
    lo = float(x.min(initial=0))
    hi = float(x.max(initial=0))
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def tempered(index: LexicalIndex, query: str, power: float = 1.0, k1: float = 1.2, b: float = 0.75) -> np.ndarray:
    if not all(math.isfinite(v) for v in (power, k1, b)) or power <= 0 or k1 <= 0 or not 0 <= b <= 1:
        raise ValueError("Invalid scorer parameters")
    scores = np.zeros(index.count)
    norm = k1 * (1 - b + b * index.lengths / index.average)
    for term in sorted(set(_tokens(query))):
        posting = index.postings.get(term)
        if posting is None:
            continue
        ids, counts = posting
        idf = math.log1p((index.count - len(ids) + 0.5) / (len(ids) + 0.5))
        scores[ids] += idf**power * counts * (k1 + 1) / (counts + norm[ids])
    return normalize(scores)


class PassageIndex:
    def __init__(self, texts: list[str]) -> None:
        chunks = []
        owners = []
        for i, text in enumerate(texts):
            toks = _tokens(text)
            # Identical windows within the same event provide no extra votes.
            seen = set()
            for start in range(0, max(len(toks), 1), 192):
                value = " ".join(toks[start : start + 256])
                if value not in seen:
                    seen.add(value)
                    chunks.append(value)
                    owners.append(i)
                if start + 256 >= len(toks):
                    break
        self.index = LexicalIndex(chunks)
        self.owners = np.array(owners, dtype=np.int64)
        self.count = len(texts)

    def scores(self, query: str) -> np.ndarray:
        values = self.index.scores(query)
        out = np.zeros(self.count)
        np.maximum.at(out, self.owners, values)
        return normalize(out)


def features(lexical: LexicalIndex, passage: PassageIndex, query: str, dense: np.ndarray) -> np.ndarray:
    return np.column_stack(
        (lexical.scores(query), passage.scores(query), normalize(dense), tempered(lexical, query, 2.0))
    )


def objective(
    weights: np.ndarray,
    pairs: dict[str, tuple[np.ndarray, np.ndarray]],
    risks: dict[str, float],
    regularization: float,
    temperature: float,
    prior: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Smooth worst-group pair loss and exact gradient for fixed pair matrices."""
    from scipy.special import expit, logsumexp

    if not math.isfinite(temperature) or temperature <= 0 or not math.isfinite(regularization) or regularization < 0:
        raise ValueError("Invalid convex objective parameters")

    losses = []
    grads = []
    probabilities = []
    for name, (x, row_weights) in pairs.items():
        if not len(x):
            continue
        margin = x @ weights
        p_rows = row_weights / row_weights.sum()
        losses.append(float(np.logaddexp(0, -margin) @ p_rows))
        grads.append(-x.T @ (expit(-margin) * p_rows))
        probabilities.append(risks[name])
    p = np.array(probabilities)
    p /= p.sum()
    z = np.array(losses) / temperature + np.log(p)
    mix = np.exp(z - logsumexp(z))
    delta = weights - prior
    value = temperature * logsumexp(z) + regularization * 0.5 * float(delta @ delta)
    gradient = np.array(grads).T @ mix + regularization * delta
    return float(value), gradient


def build_pairs(cases: list[dict[str, Any]], conditional: bool = False) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    grouped = defaultdict(list)
    weights = defaultdict(list)
    for case in cases:
        x = np.asarray(case["features"])
        if x.ndim != 2 or x.shape[1] != 4 or not np.isfinite(x).all() or np.any((x < 0) | (x > 1)):
            raise ValueError("Expected four finite bounded features")
        pos = case["positive"]
        # Hard negatives fixed before fitting, never recomputed from weights.
        neg = [i for i in case["baseline_order"] if i not in pos][:8]
        if not pos or not neg:
            continue
        diff = np.array([x[i] - x[j] for i in pos for j in neg])
        if conditional:
            padded = np.zeros((len(diff), 8))
            start = 4 if case["long_query"] else 0
            padded[:, start : start + 4] = diff
            diff = padded
        group = str(case.get("risk_group", case["group"]))
        grouped[group].append(diff)
        weights[group].append(np.full(len(diff), 1 / len(diff)))
    return {g: (np.vstack(rows), np.concatenate(weights[g])) for g, rows in grouped.items()}


def fit(
    cases: list[dict[str, Any]],
    regularization: float = 0.1,
    temperature: float = 0.1,
    conditional: bool = False,
    risk_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    from scipy.optimize import minimize

    pairs = build_pairs(cases, conditional)
    if not pairs:
        raise ValueError("No positive-negative training pairs")
    blocks = 2 if conditional else 1
    prior = np.tile([1.0, 0.0, 0.0, 0.0], blocks)
    risks = {g: 1.0 / len(pairs) for g in pairs} if risk_weights is None else dict(risk_weights)
    if set(risks) != set(pairs) or any(not math.isfinite(v) or v <= 0 for v in risks.values()):
        raise ValueError("Expected positive finite mass for every training group")
    cons = [
        {
            "type": "eq",
            "fun": lambda w, b=b: w[4 * b : 4 * b + 4].sum() - 1,
            "jac": lambda w, b=b: np.array([float(4 * b <= i < 4 * b + 4) for i in range(len(w))]),
        }
        for b in range(blocks)
    ]
    result = minimize(
        lambda w: objective(w, pairs, risks, regularization, temperature, prior),
        prior,
        jac=True,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(prior),
        constraints=cons,
        options={"ftol": 1e-10, "maxiter": 300},
    )
    if not result.success:
        raise ValueError("Optimizer failed: " + result.message)
    w = np.asarray(result.x)
    return {
        "weights": w.tolist(),
        "regularization": regularization,
        "temperature": temperature,
        "conditional": conditional,
        "objective": float(result.fun),
        "iterations": result.nit,
        "features": list(FEATURE_NAMES),
        "group_risk_weights": risks,
        "solver": "SLSQP",
        "gradient": "analytic",
    }


def score(x: np.ndarray | list[list[float]], config: dict[str, Any], long_query: bool = False) -> np.ndarray:
    w = np.asarray(config["weights"])
    values = np.asarray(x)
    if config.get("features") != list(FEATURE_NAMES):
        raise ValueError("Fitted feature schema mismatch")
    if w.shape not in ((4,), (8,)) or not np.isfinite(w).all() or np.any(w < -1e-9):
        raise ValueError("Invalid fitted weights")
    if values.ndim != 2 or values.shape[1] != 4 or not np.isfinite(values).all():
        raise ValueError("Feature schema mismatch")
    if any(abs(block.sum() - 1) > 1e-6 for block in w.reshape(-1, 4)):
        raise ValueError("Weights must lie on the registered simplex")
    if len(w) == 8:
        w = w[4:8] if long_query else w[:4]
    return values @ w
