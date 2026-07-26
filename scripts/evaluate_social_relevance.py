"""Run the deterministic contemporary social-memory benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.memory.social_benchmark import run_social_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate social-episodic ranking across synthetic settings.")
    parser.add_argument("--cases", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20260721)
    args = parser.parse_args()

    summary = run_social_benchmark(case_count=args.cases, seed=args.seed)
    print(json.dumps(summary.as_dict(), indent=2))
    passed = (
        summary.recall_at_1 >= 0.95
        and summary.recall_at_3 >= 0.995
        and summary.requested_facet_coverage >= 0.98
        and summary.attribution_retention_rate >= 0.995
        and summary.orphan_uncertain_claim_rate == 0.0
        and summary.deterministic_replay
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
