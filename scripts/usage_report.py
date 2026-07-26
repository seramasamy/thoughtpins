"""Print month-to-date provider spend, overall and per user.

Run locally, or against a deployment with `railway run python scripts/usage_report.py`.
Shares its query path with `GET /v1/admin/usage` so both surfaces always agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.config import config  # noqa: E402
from thoughtpins.store import get_session  # noqa: E402
from thoughtpins.usage import build_usage_report  # noqa: E402


def main() -> int:
    session = get_session()
    try:
        report = build_usage_report(session)
    finally:
        session.close()

    platform = report["platform_spend_usd"]
    platform_text = f"${platform:.4f}" if platform is not None else "unavailable (no Redis counter)"

    print(f"Thought Pins usage — {report['month']}")
    print(f"  tracking:     {'on' if report['tracking_enabled'] else 'OFF'}")
    print(f"  enforcement:  {'on' if report['enforcement_enabled'] else 'OFF (observe-only)'}")
    print(f"  per-user cap: ${report['per_user_budget_usd']:.2f}/month")
    print(f"  global cap:   ${report['global_budget_usd']:.2f}/month")
    print(f"  platform MTD: {platform_text}")
    print()

    users = report["users"]
    if not users:
        print("No metered spend recorded this month.")
        return 0

    tracked_total = sum(row["month_spend_usd"] for row in users)
    print(f"{len(users)} user(s) with spend, ${tracked_total:.4f} total:")
    warn_ratio = config.USAGE_BUDGET_WARN_RATIO
    budget = report["per_user_budget_usd"]
    for row in users:
        spend = row["month_spend_usd"]
        if row["over_budget"]:
            flag = "  OVER BUDGET"
        elif budget > 0 and 0 < warn_ratio < 1 and spend >= budget * warn_ratio:
            flag = "  approaching cap"
        else:
            flag = ""
        label = row["email"] or row["user_id"]
        print(f"  ${spend:9.4f}  {label}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
