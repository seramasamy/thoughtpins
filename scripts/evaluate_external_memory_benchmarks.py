"""Evaluate Thought Pins retrieval on licensed, independently labeled corpora."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.memory.benchmark_datasets import BenchmarkPartition  # noqa: E402
from thoughtpins.memory.litbank_benchmark import evaluate_litbank  # noqa: E402
from thoughtpins.memory.longmemeval_benchmark import evaluate_longmemeval  # noqa: E402

DEFAULT_CORPUS_ROOT = ROOT / ".tmp" / "benchmark-corpora"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument(
        "--partition", choices=("train", "validation", "holdout", "diagnostic", "all"), default="holdout"
    )
    parser.add_argument("--max-longmemeval-cases", type=int)
    parser.add_argument("--max-litbank-works", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    partition: BenchmarkPartition | None = None if args.partition == "all" else args.partition
    long_path = args.corpus_root / "longmemeval-data" / "longmemeval_s_cleaned.json"
    litbank_path = args.corpus_root / "litbank" / "quotations" / "tsv"
    if not long_path.is_file() or not litbank_path.is_dir():
        print("External corpora are missing. Run scripts/prepare_memory_benchmarks.py first.")
        return 2

    report = {
        "schema_version": 1,
        "partition": args.partition,
        "longmemeval": evaluate_longmemeval(
            long_path,
            partition=partition,
            max_cases=args.max_longmemeval_cases,
        ).as_dict(),
        "litbank": evaluate_litbank(
            litbank_path,
            partition=partition,
            max_works=args.max_litbank_works,
        ).as_dict(),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
