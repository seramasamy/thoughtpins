"""Backfill and refresh contextual salience for an existing Thought Pins DB."""

from __future__ import annotations

import argparse
import json

from thoughtpins.memory.salience_store import backfill_salience
from thoughtpins.store import get_session, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default=None, help="Only rescore one tenant.")
    args = parser.parse_args()
    init_db()
    session = get_session()
    try:
        print(json.dumps(backfill_salience(session, user_id=args.user_id), sort_keys=True))
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
