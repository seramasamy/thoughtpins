"""Create or remove the fictional local Thought Pins demonstration profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from thoughtpins.demo import clear_demo_corpus, seed_demo_corpus  # noqa: E402
from thoughtpins.memory.reindex import reindex_vectors  # noqa: E402
from thoughtpins.memory.vector_store import close_vector_store  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_default_user  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or clear the local fictional Thought Pins profile.")
    parser.add_argument("--clear", action="store_true", help="Remove the fictional fixture instead of seeding it.")
    parser.add_argument(
        "--no-reset", action="store_true", help="Add the fixture without first removing earlier fixture rows."
    )
    parser.add_argument("--skip-reindex", action="store_true", help="Skip derived vector-index reconstruction.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable statistics.")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        removed = 0 if args.no_reset else clear_demo_corpus(session, user.id)
        if args.clear:
            return _emit({"status": "cleared", "user_id": user.id, "removed_rows": removed}, args.json)

        stats = seed_demo_corpus(session, user.id)
        if not args.skip_reindex:
            try:
                reindex = reindex_vectors(session=session, user_id=user.id, include_private=True, reset=True)
                stats["reindex"] = {
                    "scanned": reindex.scanned,
                    "indexed": reindex.indexed,
                    "batches": reindex.batches,
                }
            except Exception as exc:
                stats["reindex_error"] = str(exc)[:240]
            finally:
                close_vector_store()
        stats.update({"status": "seeded", "user_id": user.id, "removed_rows": removed})
        return _emit(stats, args.json)
    finally:
        session.close()


def _emit(payload: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "Local fictional profile prepared." if payload["status"] == "seeded" else "Local fictional profile cleared."
        )
        for key in (
            "timeline_start",
            "timeline_end",
            "journal_entries",
            "documents",
            "memories",
            "entities",
            "rated_entries",
            "private_entries",
            "removed_rows",
        ):
            if key in payload:
                print(f"{key}: {payload[key]}")
        if payload.get("reindex_error"):
            print(f"Vector reindex warning: {payload['reindex_error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
