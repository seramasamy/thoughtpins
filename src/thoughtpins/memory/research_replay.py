"""Recompute published retrieval tables from public judgments and predictions.

This is an offline experiment artifact reader, never a serving dependency.
Gold labels are accessed here only for scoring, after predictions are fixed.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from thoughtpins.memory.research_model_views import response_ranking
from thoughtpins.memory.research_statistics import holm, paired_analysis, query_metrics

COMPARISONS = {
    "local_vs_BM25": ("L", "B1"),
    "model_vs_BM25": ("M20", "B1"),
    "model_vs_pilot": ("M20", "P10"),
    "model_vs_matched_model": ("M20", "BM20"),
    "model_vs_true_prior": ("M20", "P10_prior"),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_manifest(bundle: Path, root: Path) -> int:
    manifest = read_json(bundle / "manifest.json")
    count = 0
    for section, base in (("artifacts", bundle), ("sources", root)):
        for name, expected in manifest[section].items():
            path = (base / name).resolve()
            if not path.is_relative_to(base.resolve()):
                raise ValueError("Manifest path escapes its root")
            # Source and JSON artifacts are UTF-8 text; tolerate Git CRLF checkout.
            content = path.read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f"Published input hash mismatch: {name}")
            count += 1
    return count


def assert_close(actual: Any, expected: Any, path: str = "result") -> None:
    """Strict schema/identity comparison with a small floating-point tolerance."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError(f"Schema mismatch: {path}")
        for key, value in expected.items():
            assert_close(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"Length mismatch: {path}")
        for i, value in enumerate(expected):
            assert_close(actual[i], value, f"{path}[{i}]")
    elif type(expected) in (float, int):
        if type(actual) not in (float, int) or not math.isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12):
            raise ValueError(f"Numeric mismatch: {path}")
    elif actual != expected:
        raise ValueError(f"Value mismatch: {path}")


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def counts(rows: list[dict[str, float]]) -> dict[str, int]:
    return {"queries": len(rows), **{k: sum(int(r[k]) for r in rows) for k in ("hit1", "complete5", "complete10")}}


def model_predictions(records: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    result = {}
    for row in records:
        key = (row["query_id"], row["arm"])
        if key in result:
            raise ValueError("Duplicate model decision")
        ranking, fallback = response_ranking(
            row["response"], candidate_ids=row["candidate_ids"], baseline_ids=row["baseline_ids"]
        )
        if ranking != row["ranking"] or fallback != row["fallback"]:
            raise ValueError(f"Model decision mismatch: {key}")
        result[key] = ranking
    return result


def final_tables(bundle: Path) -> dict[str, Any]:
    query_rows = read_json(bundle / "queries.json")
    queries = {q["query_id"]: q for q in query_rows}
    local = read_rows(bundle / "local-rankings.jsonl")
    if len(queries) != len(query_rows) or len(local) != len(queries) or {r["query_id"] for r in local} != set(queries):
        raise ValueError("Final query identities are not one-to-one")
    model = model_predictions(read_rows(bundle / "model-decisions.jsonl"))
    required = {(qid, arm) for qid in queries for arm in ("M20", "BM20", "P10", "P10_prior")}
    if set(model) != required:
        raise ValueError("Incomplete final model denominator")
    grouped: dict[str, dict[str, dict[str, dict[str, float]]]] = defaultdict(lambda: defaultdict(dict))
    for row in local:
        qid = row["query_id"]
        q = queries[qid]
        arms = row["arms"] | {a: model[qid, a] for a in ("M20", "BM20", "P10", "P10_prior")}
        for arm, ranking in arms.items():
            metrics = query_metrics(ranking, q["qrels"])
            metrics["mrr"] = query_metrics(ranking[:10], q["qrels"])["mrr"]
            grouped[q["dataset"]][arm][qid] = metrics
    result: dict[str, Any] = {
        k: {} for k in ("aggregate", "counts", "prior_aggregate", "prior_counts", "statistics", "verdict")
    }
    for dataset, arms in grouped.items():
        ids = sorted(qid for qid, q in queries.items() if q["dataset"] == dataset)
        if any(set(rows) != set(ids) for rows in arms.values()):
            raise ValueError("Incomplete arm denominator")
        result["aggregate"][dataset] = {
            a: aggregate(list(rows.values())) for a, rows in arms.items() if a != "P10_prior"
        }
        result["counts"][dataset] = {a: counts(list(rows.values())) for a, rows in arms.items() if a != "P10_prior"}
        result["prior_aggregate"][dataset] = aggregate(list(arms["P10_prior"].values()))
        result["prior_counts"][dataset] = counts(list(arms["P10_prior"].values()))
        stats, verdict = paired_family(arms, queries, ids)
        result["statistics"][dataset] = stats
        result["verdict"][dataset] = verdict
    assert_close(result, read_json(bundle / "expected.json"))
    return result


def auxiliary_tables(bundle: Path) -> dict[str, Any]:
    historical: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    for row in read_rows(bundle / "historical.jsonl"):
        metrics = query_metrics(row["ranking"], row["qrels"])
        metrics["mrr"] = query_metrics(row["ranking"][:10], row["qrels"])["mrr"]
        historical[row["partition"]][row["arm"]].append(metrics)
    hist_aggregate = {p: {a: aggregate(v) for a, v in arms.items()} for p, arms in historical.items()}
    hist_counts = {p: {a: counts(v) for a, v in arms.items()} for p, arms in historical.items()}
    expected = read_json(bundle / "historical-expected.json")
    assert_close(hist_aggregate, expected["aggregate"])
    assert_close(hist_counts, expected["counts"])
    transfer: dict[str, list[dict[str, float]]] = defaultdict(list)
    for row in read_rows(bundle / "nfcorpus.jsonl"):
        transfer[row["arm"]].append(query_metrics(row["ranking"], row["qrels"], exponential=True))
    nfc = {arm: aggregate(values) for arm, values in transfer.items()}
    assert_close(nfc, read_json(bundle / "nfcorpus-expected.json")["aggregate"])
    return {"historical": hist_aggregate, "historical_counts": hist_counts, "nfcorpus": nfc}


def paired_family(arms: dict, queries: dict, ids: list[str]) -> tuple[dict, dict]:
    stats = {
        name: {
            metric: paired_analysis(
                [arms[left][q][metric] for q in ids],
                [arms[right][q][metric] for q in ids],
                [queries[q]["group"] for q in ids],
                seed=20260920,
            )
            for metric in ("ndcg10", "hit1", "complete5")
        }
        for name, (left, right) in COMPARISONS.items()
    }
    raw_p = {name: value["ndcg10"]["p_value"] for name, value in stats.items()}
    original_p = holm({k: v for k, v in raw_p.items() if k != "model_vs_true_prior"})
    adjusted = holm(raw_p)
    verdict = {}
    for name, values in stats.items():
        ndcg = values["ndcg10"]
        if name in original_p:
            ndcg["holm_p"] = original_p[name]
        ndcg["holm_p_five_comparisons"] = adjusted[name]
        checks = {
            "material_ndcg": ndcg["delta"] >= 0.02,
            "positive_lower_ci": ndcg["ci95"][0] > 0,
            "holm_supported": adjusted[name] < 0.05,
            "hit1_noninferior": values["hit1"]["ci95"][0] >= -0.01,
            "complete5_noninferior": values["complete5"]["ci95"][0] >= -0.01,
        }
        verdict[name] = {"checks": checks, "passes_all": all(checks.values())}
    return stats, verdict
