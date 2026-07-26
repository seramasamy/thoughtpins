"""Calibrate bounded ranking tie-breakers without reading the final holdout."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.memory.litbank_benchmark import evaluate_litbank  # noqa: E402
from thoughtpins.memory.longmemeval_benchmark import evaluate_longmemeval  # noqa: E402
from thoughtpins.memory.ranking import (  # noqa: E402
    DEFAULT_RANKING_WEIGHTS,
    RankingPolicy,
)
from thoughtpins.memory.social_benchmark import run_social_benchmark  # noqa: E402

DEFAULT_CORPUS_ROOT = ROOT / ".tmp" / "benchmark-corpora"
TEMPORAL_CANDIDATES = (0.0, 0.04, 0.06, 0.08, 0.10, 0.12)
SOCIAL_UTILITY_CANDIDATES = (0.0, 0.03, 0.06, 0.10, 0.12, 0.15, 0.18, 0.20)
SOCIAL_ADVERSARIAL_CASES = 640


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "memory-ranking-calibration.json")
    parser.add_argument(
        "--reuse-temporal",
        type=Path,
        help="Reuse temporal trials from a prior no-holdout calibration report.",
    )
    args = parser.parse_args()

    long_path = args.corpus_root / "longmemeval-data" / "longmemeval_s_cleaned.json"
    litbank_path = args.corpus_root / "litbank" / "quotations" / "tsv"
    if not long_path.is_file() or not litbank_path.is_dir():
        print("External corpora are missing. Run scripts/prepare_memory_benchmarks.py first.")
        return 2

    temporal_trials = (
        _reused_temporal_trials(args.reuse_temporal)
        if args.reuse_temporal
        else [_temporal_trial(long_path, weight) for weight in TEMPORAL_CANDIDATES]
    )
    social_trials = [_social_utility_trial(litbank_path, weight) for weight in SOCIAL_UTILITY_CANDIDATES]
    selected_temporal = max(
        temporal_trials,
        key=lambda trial: (
            trial["validation"]["mean_reciprocal_rank"],
            trial["validation"]["mean_ndcg_at_10"],
            -trial["weight"],
        ),
    )
    eligible_social = [
        trial
        for trial in social_trials
        if trial["train"]["recall_at_1"] >= 0.98
        and trial["validation"]["recall_at_1"] >= 0.99
        and trial["adversarial"]["recall_at_1"] >= 0.95
        and trial["adversarial"]["recall_at_3"] >= 0.995
        and trial["adversarial"]["orphan_uncertain_claim_rate"] == 0.0
    ]
    selected_social = max(
        eligible_social or social_trials,
        key=lambda trial: (
            trial["validation"]["mean_reciprocal_rank"],
            trial["validation"]["mean_ndcg_at_10"],
            trial["train"]["mean_ndcg_at_10"],
            -trial["weight"],
        ),
    )
    report = {
        "schema_version": 1,
        "method": "bounded-multi-corpus-grid-v2",
        "holdout_accessed": False,
        "temporal_query": {"selected": selected_temporal, "trials": temporal_trials},
        "social_utility": {"selected": selected_social, "trials": social_trials},
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _temporal_trial(dataset_path: Path, weight: float) -> dict[str, Any]:
    policy = _policy(temporal_query=weight)
    train = evaluate_longmemeval(dataset_path, partition="train", policy=policy).thoughtpins
    validation = evaluate_longmemeval(dataset_path, partition="validation", policy=policy).thoughtpins
    return {"weight": weight, "train": train.as_dict(), "validation": validation.as_dict()}


def _social_utility_trial(quotations_dir: Path, weight: float) -> dict[str, Any]:
    policy = _policy(social_utility=weight)
    train = evaluate_litbank(quotations_dir, partition="train", policy=policy).minor_speakers
    validation = evaluate_litbank(quotations_dir, partition="validation", policy=policy).minor_speakers
    adversarial = run_social_benchmark(
        case_count=SOCIAL_ADVERSARIAL_CASES,
        seed=20260721,
        policy=policy,
    )
    return {
        "weight": weight,
        "train": train.as_dict(),
        "validation": validation.as_dict(),
        "adversarial": adversarial.as_dict(),
    }


def _reused_temporal_trials(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("holdout_accessed") is not False:
        raise ValueError("refusing to reuse a report that does not attest holdout_accessed=false")
    trials = payload.get("temporal_query", {}).get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("reused calibration report has no temporal trials")
    return trials


def _policy(**changes: float) -> RankingPolicy:
    return RankingPolicy(
        name="external-calibration",
        weights=replace(DEFAULT_RANKING_WEIGHTS, **changes),
    )


if __name__ == "__main__":
    raise SystemExit(main())
