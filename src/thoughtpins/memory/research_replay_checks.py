"""Offline reconciliation of published robustness decisions and numeric costs."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from thoughtpins.memory.research_model_views import response_ranking
from thoughtpins.memory.research_replay import assert_close, read_json, read_rows
from thoughtpins.memory.research_statistics import query_metrics


def replay_robustness(bundle: Path) -> dict:
    artifact = read_json(bundle / "robustness.json")
    results = []

    def ranking(row):
        return response_ranking(row["response"], candidate_ids=row["candidate_ids"], baseline_ids=row["baseline_ids"])

    for row in artifact["records"]:
        order, fallback = ranking(row)
        result = {k: row[k] for k in ("query_id", "kind")}
        result.update(fallback=fallback, ranking=order)
        if row["kind"] == "repeat":
            original, _ = ranking(row["original"])
            result.update(
                permutation=row["permutation"],
                same_first=order[0] == original[0],
                same_first5=order[:5] == original[:5],
                same_full=order == original,
            )
        else:
            result.update(category=row["category"], metrics=query_metrics(order, row["qrels"]))
        results.append(result)
    assert_close(results, artifact["expected"])
    synthetic = [r for r in results if r["kind"] == "synthetic"]
    repeats = {}
    for permutation in (0, 1):
        rows = [r for r in results if r.get("permutation") == permutation]
        repeats[str(permutation)] = {
            "queries": len(rows),
            "same_first": sum(r["same_first"] for r in rows),
            "same_full": sum(r["same_full"] for r in rows),
        }
    return {
        "cases": len(results),
        "repeat_permutation": repeats,
        "synthetic": {
            "queries": len(synthetic),
            "hit1": sum(r["metrics"]["hit1"] for r in synthetic),
            "complete5": sum(r["metrics"]["complete5"] for r in synthetic),
        },
    }


def reconcile_costs(bundle: Path) -> dict:
    rows = read_rows(bundle / "attempt-costs.jsonl")
    expected = read_json(bundle / "costs.json")
    prices = read_json(bundle / "archived-prices.json")["usd_per_million_input_output"]
    totals: dict[str, Decimal] = defaultdict(Decimal)
    if [row["attempt"] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Missing or duplicate published cost attempt")
    for row in rows:
        input_price, output_price = map(lambda x: Decimal(str(x)), prices[row["model"]])
        price = (input_price * row["prompt_tokens"] + output_price * row["completion_tokens"]) / Decimal(1000000)
        charge = Decimal(row["charged_usd"])
        if abs(price - charge) > Decimal("0.000000000001"):
            raise ValueError("Usage/charge mismatch")
        if charge > Decimal(row["reserved_usd"]):
            raise ValueError("Unexplained cost reservation overrun")
        totals[row["stage"]] += charge
    by_stage = {key: float(totals[key]) for key in expected["by_stage"]}
    result = {
        "charged_usd": float(sum(totals.values())),
        "by_stage": by_stage,
        "attempts": len(rows),
        "unsettled": 0,
        "statuses": dict(Counter(r["status"] for r in rows)),
        "unknown_cost_attempts": 0,
    }
    assert_close(result, expected)
    return result
