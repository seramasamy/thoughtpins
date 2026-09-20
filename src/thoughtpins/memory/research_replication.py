"""Re-fit and rank from the published numeric features, without corpus text/API calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from thoughtpins.memory.research_replay import read_json, read_rows
from thoughtpins.memory.research_retrieval import fuse_rankings, stable_order
from thoughtpins.memory.research_robust import fit, score


def numeric_rankings(row: dict[str, Any], config: dict[str, Any]) -> dict[str, list[str]]:
    ids = row["ids"]
    x = np.asarray(row["features"])

    def rank(values, identities=True):
        return [ids[i] for i in stable_order(np.asarray(values), ids if identities else None)[:50]]

    arms = {
        "B0": rank(x[:, 0], False),
        "B1": rank(row["tuned_bm25"], False),
        "B3": rank(x[:, 2]),
        "L": rank(score(x, config, row["long_query"])),
        "CC50": rank(0.5 * x[:, 0] + 0.5 * x[:, 2]),
    }
    for name, sparse in (("B4", rank(row["rrf_bm25"], False)), ("RRF_tuned", arms["B1"])):
        arms[name] = [sid for sid, _ in fuse_rankings({"sparse": sparse, "dense": arms["B3"]})[:50]]
    weights = np.asarray(config["weights"])
    active = weights[4:] if row["long_query"] else weights[:4]
    for j, name in enumerate(("whole", "passage", "dense", "idf")):
        ablated = active.copy()
        ablated[j] = 0
        if ablated.sum() > 0:
            ablated /= ablated.sum()
        arms["A_no_" + name] = rank(x @ ablated)
    arms["A_no_gate"] = rank(x @ weights[:4])
    return arms


def verify_numeric_replication(bundle: Path) -> dict[str, Any]:
    config = read_json(bundle / "config.json")["selected"]["config"]
    training = read_rows(bundle / "training-pairs.jsonl")
    fitted = fit(
        training,
        config["regularization"],
        config["temperature"],
        config["conditional"],
        risk_weights=config["group_risk_weights"],
    )
    # SLSQP/BLAS can differ slightly between platforms. This is a numerical,
    # not bitwise, solver check; all frozen ranking identities must still match.
    np.testing.assert_allclose(fitted["weights"], config["weights"], rtol=0, atol=1e-7)
    expected = {r["query_id"]: r["arms"] for r in read_rows(bundle / "local-rankings.jsonl")}
    seen: set[str] = set()
    arm_count = 0
    with (bundle / "final-features.jsonl").open(encoding="utf-8") as handle:
        import json

        for line in handle:
            row = json.loads(line)
            qid = row["query_id"]
            if qid in seen or qid not in expected:
                raise ValueError("Unexpected numeric query identity")
            seen.add(qid)
            for arm, ranking in numeric_rankings(row, config).items():
                if ranking != expected[qid][arm]:
                    raise ValueError(f"Numeric ranking mismatch: {qid}/{arm}")
                arm_count += 1
    if seen != set(expected):
        raise ValueError("Missing numeric query features")
    return {
        "training_queries": len(training),
        "fitted_weights": fitted["weights"],
        "queries": len(seen),
        "numeric_rankings_recomputed": arm_count,
        "current_policy_B2": "Archived predictions scored; raw-text feature construction is not replayed.",
        "feature_origin": "Frozen public-corpus score cache; embeddings are not regenerated.",
    }
