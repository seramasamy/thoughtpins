"""Independently audit the published retrieval metrics; no Thought Pins imports or API calls."""

from __future__ import annotations

import argparse
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FAMILY = {
    "local_vs_BM25": ("L", "B1"),
    "model_vs_BM25": ("M20", "B1"),
    "model_vs_pilot": ("M20", "P10"),
    "model_vs_matched_model": ("M20", "BM20"),
    "model_vs_true_prior": ("M20", "P10_prior"),
}


def read(path: Path):
    text = path.read_text(encoding="utf-8")
    return (
        [json.loads(line) for line in text.splitlines() if line.strip()]
        if path.suffix == ".jsonl"
        else json.loads(text)
    )


def measure(order: list[str], qrels: dict[str, int], *, graded: bool = False) -> dict[str, float]:
    if len(order) != len(set(order)):
        raise ValueError("Duplicate source in ranking")
    relevant = {sid for sid, grade in qrels.items() if grade > 0}
    if not relevant:
        raise ValueError("Unanswerable query entered answerable retrieval audit")
    gains = {sid: 2 ** qrels[sid] - 1 if graded else 1 for sid in relevant}
    discounts = [1 / math.log2(rank + 1) for rank in range(1, 11)]
    ideal = math.fsum(g * d for g, d in zip(sorted(gains.values(), reverse=True), discounts, strict=False))
    dcg = math.fsum(gains.get(sid, 0) * discounts[i] for i, sid in enumerate(order[:10]))
    first = next((i for i, sid in enumerate(order[:10], 1) if sid in relevant), None)
    result = {
        "ndcg10": dcg / ideal,
        "hit1": float(bool(order) and order[0] in relevant),
        "mrr": 1 / first if first else 0.0,
    }
    for k in (5, 10, 20, 50):
        hits = sum(sid in relevant for sid in order[:k])
        result.update(
            {
                f"recall{k}": hits / len(relevant),
                f"complete{k}": float(hits == len(relevant)),
                f"hit{k}": float(hits > 0),
                f"precision{k}": hits / k,
            }
        )
    return result


def check_numbers(actual: dict, expected: dict) -> None:
    for key, number in actual.items():
        if not math.isclose(number, expected[key], rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"Independent numeric disagreement: {key}")


def paired(differences: list[float], groups: list[str]) -> dict:
    # Matrix grouping is independent of the production/replay statistics helper.
    membership = np.equal.outer(groups, sorted(set(groups)))
    totals = np.asarray(differences) @ membership
    sizes = membership.sum(axis=0)
    rng = np.random.default_rng(20260920)
    sample = rng.integers(len(sizes), size=(10000, len(sizes)))
    bootstrap = totals[sample].sum(axis=1) / sizes[sample].sum(axis=1)
    effect = math.fsum(differences) / len(differences)
    exact = len(sizes) <= 16
    signs = (
        np.array(list(itertools.product((-1, 1), repeat=len(sizes))))
        if exact
        else rng.choice([-1, 1], (10000, len(sizes)))
    )
    extreme = np.count_nonzero(np.abs(signs @ totals / len(differences)) >= abs(effect) - 1e-12)
    return {
        "delta": effect,
        "ci95": np.quantile(bootstrap, [0.025, 0.975]).tolist(),
        "p_value": float(extreme / len(signs) if exact else (extreme + 1) / (len(signs) + 1)),
    }


def check_statistics(arms: dict, queries: dict, expected: dict) -> dict:
    ids = sorted(queries)
    groups = [queries[qid]["group"] for qid in ids]
    result: dict[str, dict] = {}
    for name, (left, right) in FAMILY.items():
        result[name] = {}
        for metric in ("ndcg10", "hit1", "complete5"):
            delta = [arms[left][qid][metric] - arms[right][qid][metric] for qid in ids]
            value = paired(delta, groups)
            target = expected[name][metric]
            check_numbers({k: value[k] for k in ("delta", "p_value")}, target)
            check_numbers(dict(enumerate(value["ci95"])), dict(enumerate(target["ci95"])))
            result[name][metric] = value
    ordered = sorted(result, key=lambda name: result[name]["ndcg10"]["p_value"])
    for i, name in enumerate(ordered):
        adjusted = min(
            1.0, max((len(ordered) - j) * result[n]["ndcg10"]["p_value"] for j, n in enumerate(ordered[: i + 1]))
        )
        check_numbers({"holm_p_five_comparisons": adjusted}, expected[name]["ndcg10"])
        result[name]["ndcg10"]["holm_p_five_comparisons"] = adjusted
    return result


def check_model(row: dict) -> None:
    response = row["response"]
    try:
        data = json.loads(response.get("content", ""))
    except (TypeError, json.JSONDecodeError):
        data = {}
    permutation = data.get("ranking") if isinstance(data, dict) else None
    n = len(row["candidate_ids"])
    valid = (
        response.get("kind") == "chat"
        and response.get("status") == "ok"
        and response.get("finish_reason") == "stop"
        and isinstance(data, dict)
        and set(data) == {"ranking"}
        and isinstance(permutation, list)
        and len(permutation) == n
        and all(type(i) is int for i in permutation)
        and set(permutation) == set(range(n))
    )
    expected = row["baseline_ids"]
    if valid:
        assert isinstance(permutation, list)
        expected = [row["candidate_ids"][i] for i in permutation]
    if expected != row["ranking"] or valid == bool(row["fallback"]):
        raise ValueError("Model ranking/fallback mismatch")
    if len(set(row["candidate_ids"])) != n or set(row["candidate_ids"]) != set(row["baseline_ids"]):
        raise ValueError("Candidate set mismatch")


def summarize_changes(arms: dict, ids: dict) -> dict:
    result: dict[str, dict] = {}
    for baseline in ("B1", "P10_prior", "BM20"):
        result[baseline] = {}
        for metric in ("ndcg10", "hit1", "complete5"):
            changes: Counter[str] = Counter()
            for qid in ids:
                difference = arms["M20"][qid][metric] - arms[baseline][qid][metric]
                changes["better" if difference > 1e-12 else "worse" if difference < -1e-12 else "tied"] += 1
            result[baseline][metric] = dict(changes)
    return result


def audit(bundle: Path) -> dict:
    query_rows = read(bundle / "queries.json")
    queries = {q["query_id"]: q for q in query_rows}
    expected = read(bundle / "expected.json")
    local = read(bundle / "local-rankings.jsonl")
    if len(queries) != len(query_rows) or len(local) != len(queries):
        raise ValueError("Duplicate or missing queries")
    ranking = {row["query_id"]: dict(row["arms"]) for row in local}
    model_rows = read(bundle / "model-decisions.jsonl")
    seen = set()
    for row in model_rows:
        check_model(row)
        key = (row["query_id"], row["arm"])
        if key in seen:
            raise ValueError("Duplicate model case")
        seen.add(key)
        ranking[key[0]][key[1]] = row["ranking"]
    if seen != {(qid, arm) for qid in queries for arm in ("M20", "BM20", "P10", "P10_prior")}:
        raise ValueError("Missing model cases")
    result = {}
    for dataset in sorted({q["dataset"] for q in queries.values()}):
        subset = {qid: q for qid, q in queries.items() if q["dataset"] == dataset}
        arms: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
        for qid, q in subset.items():
            for arm, order in ranking[qid].items():
                arms[arm][qid] = measure(order, q["qrels"])
        if set(arms) != set(expected["aggregate"][dataset]) | {"P10_prior"} or any(
            len(rows) != len(subset) for rows in arms.values()
        ):
            raise ValueError("Incomplete local arm denominator")
        means = {
            a: {m: math.fsum(row[m] for row in rows.values()) / len(rows) for m in next(iter(rows.values()))}
            for a, rows in arms.items()
        }
        for arm, values in means.items():
            check_numbers(
                values,
                expected["prior_aggregate"][dataset] if arm == "P10_prior" else expected["aggregate"][dataset][arm],
            )
        contrasts = check_statistics(arms, subset, expected["statistics"][dataset])
        result[dataset] = {
            "queries": len(subset),
            "groups": len({q["group"] for q in subset.values()}),
            "support_size_distribution": dict(Counter(len(q["qrels"]) for q in subset.values())),
            "aggregate": means,
            "paired": contrasts,
            "changes": summarize_changes(arms, subset),
        }
    return {
        "datasets": result,
        "model_decisions": len(model_rows),
        "fallbacks": dict(Counter(r["arm"] for r in model_rows if r["fallback"])),
        "imports_original_evaluator": False,
        "paid_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(ROOT / "docs/research/2026-09-retrieval/artifacts")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": True,
                "queries": sum(d["queries"] for d in result["datasets"].values()),
                "arms_per_corpus": 17,
                "paired_metric_checks": 30,
                "model_decisions": result["model_decisions"],
                "fallbacks": result["fallbacks"],
            }
        )
    )


if __name__ == "__main__":
    main()
