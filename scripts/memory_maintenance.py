from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from thoughtpins.memory.maintenance import run_memory_maintenance
from thoughtpins.store import get_session, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline Thought Pins memory maintenance.")
    parser.add_argument("--user-id", help="Scope diagnostics and reindexing to one user.")
    parser.add_argument("--reindex", action="store_true", help="Rebuild vector rows as part of maintenance.")
    parser.add_argument("--public-only", action="store_true", help="Exclude private memories from reindexing.")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        report = run_memory_maintenance(
            session=session,
            user_id=args.user_id,
            reindex=args.reindex,
            include_private=not args.public_only,
        )
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
