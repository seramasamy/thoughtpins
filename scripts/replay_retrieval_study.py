"""Replay the September 2026 publication without credentials or network access."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.memory.research_replay import auxiliary_tables, final_tables, read_rows, verify_manifest  # noqa: E402
from thoughtpins.memory.research_replay_checks import reconcile_costs, replay_robustness  # noqa: E402
from thoughtpins.memory.research_replication import verify_numeric_replication  # noqa: E402


def offline(*args, **kwargs):
    raise RuntimeError("Network disabled during the published replay")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional output JSON, normally under ignored reports/.")
    args = parser.parse_args()
    for target, attribute in (
        (socket, "create_connection"),
        (socket, "getaddrinfo"),
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
    ):
        setattr(target, attribute, offline)
    bundle = ROOT / "docs/research/2026-09-retrieval/artifacts"
    verified = verify_manifest(bundle, ROOT)
    result = final_tables(bundle)
    result["auxiliary"] = auxiliary_tables(bundle)
    result["replication"] = verify_numeric_replication(bundle)
    result["robustness"] = replay_robustness(bundle)
    result["costs"] = reconcile_costs(bundle)
    result["verification"] = {
        "files": verified,
        "model_decisions": len(read_rows(bundle / "model-decisions.jsonl")),
        "paid_calls": 0,
        "network_disabled": True,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for dataset, arms in result["aggregate"].items():
        print(f"\n{dataset}: nDCG@10 / Hit@1 / complete@5")
        for arm, values in arms.items():
            count = result["counts"][dataset][arm]
            print(
                f"  {arm:14} {values['ndcg10']:.6f}  {count['hit1']}/{count['queries']}  {count['complete5']}/{count['queries']}"
            )
        print("  Exact prior P10:", result["prior_aggregate"][dataset]["ndcg10"])
    print(json.dumps(result["verification"]))
    print("Verified reported tables, paired statistics, model fallbacks, local numeric rankings and fitted weights.")


if __name__ == "__main__":
    main()
