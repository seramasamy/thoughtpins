"""Run the disposable Project Gutenberg social-memory evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.memory.public_domain_eval import (  # noqa: E402
    evaluate_public_domain_corpus,
    write_public_domain_eval_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate social retrieval across public-domain books.")
    parser.add_argument("--catalog", type=Path, default=ROOT / ".tmp" / "pg_catalog.csv")
    parser.add_argument("--cache", type=Path, default=ROOT / ".tmp" / "public-domain-social-corpus")
    parser.add_argument("--sources", type=int, default=200)
    parser.add_argument("--candidate-pool", type=int, default=24)
    parser.add_argument("--max-attempt-multiplier", type=int, default=8)
    parser.add_argument("--request-delay", type=float, default=0.12)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if not args.catalog.exists():
        parser.error(
            "Project Gutenberg catalog is missing. Download the official pg_catalog.csv offline catalog to "
            f"{args.catalog} before running."
        )
    summary = evaluate_public_domain_corpus(
        args.catalog,
        args.cache,
        source_count=args.sources,
        candidate_pool_size=args.candidate_pool,
        request_delay_seconds=max(0.0, args.request_delay),
        max_attempt_multiplier=args.max_attempt_multiplier,
    )
    report = args.report or ROOT / "reports" / "memory" / (
        f"public-domain-social-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    write_public_domain_eval_report(summary, report)
    print(
        json.dumps({**summary.as_dict(), "sources": f"{len(summary.sources)} entries", "report": str(report)}, indent=2)
    )

    passed = (
        summary.evaluated_sources == args.sources
        and summary.recall_at_10 >= 0.90
        and summary.attribution_retention_rate == 1.0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
