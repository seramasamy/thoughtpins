"""Deterministic judgment-only metrics and paired dependence-aware analysis."""

from __future__ import annotations

import itertools
import math
from collections import defaultdict

import numpy as np


def query_metrics(ranking: list[str], grades: dict[str, int], *, exponential: bool = False) -> dict[str, float]:
    relevant = {sid for sid, grade in grades.items() if grade > 0}
    if not relevant:
        raise ValueError("Empty-gold abstention is a separate evaluation task")
    ranked = list(dict.fromkeys(ranking))
    gain = (lambda grade: 2.0**grade - 1) if exponential else (lambda grade: float(grade > 0))
    ideal = sorted((gain(grade) for grade in grades.values() if grade > 0), reverse=True)
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal[:10]))
    dcg = sum(gain(grades.get(sid, 0)) / math.log2(i + 2) for i, sid in enumerate(ranked[:10]))
    first = next((i for i, sid in enumerate(ranked, 1) if sid in relevant), None)
    metrics = {
        "ndcg10": dcg / idcg,
        "hit1": float(bool(ranked) and ranked[0] in relevant),
        "mrr": 1 / first if first else 0.0,
    }
    for k in (5, 10, 20, 50):
        recovered = len(relevant.intersection(ranked[:k]))
        metrics.update(
            {
                f"recall{k}": recovered / len(relevant),
                f"complete{k}": float(recovered == len(relevant)),
                f"hit{k}": float(recovered > 0),
                f"precision{k}": recovered / k,
            }
        )
    return metrics


def paired_analysis(
    left: list[float], right: list[float], groups: list[str], *, seed: int = 20260919, resamples: int = 10000
) -> dict:
    if not left or not len(left) == len(right) == len(groups):
        raise ValueError("Expected identical nonempty paired cases")
    differences = np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
    if not np.isfinite(differences).all():
        raise ValueError("Nonfinite paired differences")
    grouped: dict[str, list[float]] = defaultdict(list)
    for group, value in zip(groups, differences, strict=True):
        grouped[group].append(float(value))
    names = sorted(grouped)
    totals = np.array([sum(grouped[g]) for g in names])
    sizes = np.array([len(grouped[g]) for g in names])
    means = totals / sizes
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(names), size=(resamples, len(names)))
    bootstrap = totals[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    observed = float(differences.mean())
    if len(names) <= 16:
        signs = np.array(list(itertools.product((-1, 1), repeat=len(names))))
        null = signs @ totals / sizes.sum()
        p = float(np.mean(np.abs(null) >= abs(observed) - 1e-12))
        test = "exact two-sided group-sign randomization"
    else:
        signs = rng.choice(np.array([-1, 1]), size=(resamples, len(names)))
        null = signs @ totals / sizes.sum()
        p = float((1 + np.sum(np.abs(null) >= abs(observed) - 1e-12)) / (resamples + 1))
        test = "Monte Carlo two-sided group-sign randomization, plus-one correction"
    return {
        "queries": len(left),
        "groups": len(names),
        "delta": observed,
        "ci95": np.quantile(bootstrap, [0.025, 0.975]).tolist(),
        "group_mean_delta": float(means.mean()),
        "per_group": {g: {"count": int(sizes[i]), "delta": float(means[i])} for i, g in enumerate(names)},
        "p_value": p,
        "test": test,
        "bootstrap": "paired cluster resampling, query weighted",
        "resamples": resamples,
        "seed": seed,
        "assumption": "group sign exchangeability under null; sampled groups represent target population",
        "limited_power": len(names) < 10,
    }


def holm(p_values: dict[str, float]) -> dict[str, float]:
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in p_values.values()):
        raise ValueError("Invalid probability")
    result, lower = {}, 0.0
    for i, (name, p) in enumerate(sorted(p_values.items(), key=lambda item: (item[1], item[0]))):
        lower = min(1.0, max(lower, (len(p_values) - i) * p))
        result[name] = lower
    return result
