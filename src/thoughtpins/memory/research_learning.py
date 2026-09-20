"""Small bounded pairwise ranker for offline, group-held-out experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

FEATURE_NAMES = (
    "bm25",
    "dense",
    "sparse_rr",
    "dense_rr",
    "term_coverage",
    "time_match",
    "attribution",
    "current_correction",
    "instruction_penalty",
)


@dataclass(frozen=True)
class LearningParameters:
    regularization: float = 0.1
    bounds: tuple[float, ...] = (2, 2, 1, 1, 0.5, 0.15, 0.15, 0.15, 0.1)
    prior: tuple[float, ...] = (0, 0, 0.5, 0.5, 0, 0, 0, 0, 0)
    max_iterations: int = 400
    tolerance: float = 1e-10

    def __post_init__(self) -> None:
        if not np.isfinite(self.regularization) or self.regularization <= 0:
            raise ValueError("Regularization must be strictly positive")
        if len(self.bounds) != len(FEATURE_NAMES) or len(self.prior) != len(FEATURE_NAMES):
            raise ValueError("Feature schema mismatch")
        if any(
            not np.isfinite(b) or not np.isfinite(w) or not 0 <= w <= b
            for b, w in zip(self.bounds, self.prior, strict=True)
        ):
            raise ValueError("Invalid bounded parameter domain")


def pairwise_rows(features: list[np.ndarray], labels: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Fixed binary pairs; each eligible query has equal total weight.

    Unjudged negatives must be explicitly declared by the experimental caller.
    Queries with no positive/negative pair cannot contribute a ranking gradient.
    """
    if len(features) != len(labels):
        raise ValueError("Queries and judgments must align")
    rows, weights = [], []
    for x, y in zip(features, labels, strict=True):
        x, y = np.asarray(x, dtype=float), np.asarray(y)
        if x.shape != (len(y), len(FEATURE_NAMES)) or not np.isfinite(x).all():
            raise ValueError("Invalid feature matrix")
        positive, negative = x[y > 0], x[y == 0]
        if len(positive) == 0 or len(negative) == 0:
            continue
        difference = (positive[:, None, :] - negative[None, :, :]).reshape(-1, x.shape[1])
        rows.append(difference)
        weights.append(np.full(len(difference), 1 / len(difference)))
    if not rows:
        raise ValueError("No usable judged pairs")
    return np.concatenate(rows), np.concatenate(weights) / len(rows)


def loss_gradient(
    weights: np.ndarray, differences: np.ndarray, pair_weights: np.ndarray, parameters: LearningParameters
) -> tuple[float, np.ndarray]:
    margin = differences @ weights
    displacement = weights - np.array(parameters.prior)
    loss = np.sum(pair_weights * np.logaddexp(0, -margin)) + parameters.regularization * displacement @ displacement
    # Stable sigmoid(-margin), without making inference depend on an optimizer.
    gradient = (
        differences.T @ (-pair_weights * np.exp(-np.logaddexp(0, margin)))
        + 2 * parameters.regularization * displacement
    )
    return float(loss), gradient


def fit_ranker(
    features: list[np.ndarray],
    labels: list[np.ndarray],
    *,
    parameters: LearningParameters,
    seed: int = 20260919,
    training_hash: str = "",
) -> dict:
    # Scientific fitting is optional; applying frozen numeric artifacts requires
    # only NumPy, already used by the repository's vector client.
    from scipy.optimize import minimize

    differences, pair_weights = pairwise_rows(features, labels)
    rng = np.random.default_rng(seed)
    initial = np.clip(np.array(parameters.prior) + rng.normal(0, 0.01, len(FEATURE_NAMES)), 0, parameters.bounds)
    result = minimize(
        loss_gradient,
        initial,
        args=(differences, pair_weights, parameters),
        jac=True,
        method="L-BFGS-B",
        bounds=[(0, bound) for bound in parameters.bounds],
        options={"maxiter": parameters.max_iterations, "ftol": parameters.tolerance, "gtol": 1e-8},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("Bounded optimizer did not converge")
    return {
        "schema": list(FEATURE_NAMES),
        "weights": result.x.tolist(),
        "parameters": asdict(parameters),
        "normalization": "Fixed bounded/query-local feature transforms; no population statistics fitted",
        "objective": "query-averaged fixed-pair logistic plus positive quadratic penalty around prior",
        "optimizer": "scipy L-BFGS-B",
        "loss": float(result.fun),
        "iterations": int(result.nit),
        "pairs": len(differences),
        "seed": seed,
        "training_hash": training_hash,
    }


def apply_ranker(features: np.ndarray, artifact: dict) -> np.ndarray:
    if artifact["schema"] != list(FEATURE_NAMES):
        raise ValueError("Fitted artifact feature schema mismatch")
    weights = np.asarray(artifact["weights"], dtype=float)
    if weights.shape != (len(FEATURE_NAMES),) or not np.isfinite(weights).all():
        raise ValueError("Invalid fitted weights")
    bounds = np.asarray(artifact["parameters"]["bounds"], dtype=float)
    if np.any(weights < 0) or np.any(weights > bounds):
        raise ValueError("Fitted weights outside declared bounds")
    return features @ weights
