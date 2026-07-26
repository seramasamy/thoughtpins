from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from thoughtpins.memory.reindex import reindex_vectors
from thoughtpins.memory.search import search
from thoughtpins.memory.vector_store import close_vector_store
from thoughtpins.store import get_session, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the Thought Pins vector index from database memories.")
    parser.add_argument("--user-id", help="Scope reindex to one user id.")
    parser.add_argument("--public-only", action="store_true", help="Exclude private entries from indexing.")
    parser.add_argument("--no-reset", action="store_true", help="Do not clear existing vector rows before indexing.")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--verify-query", help="Run a search query after indexing and print top results.")
    parser.add_argument("--verify-limit", type=int, default=5)
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        stats = reindex_vectors(
            session=session,
            user_id=args.user_id,
            include_private=not args.public_only,
            batch_size=args.batch_size,
            reset=not args.no_reset,
            limit=args.limit,
        )
        payload: dict[str, object] = {
            "scanned": stats.scanned,
            "indexed": stats.indexed,
            "batches": stats.batches,
            "deleted_existing": stats.deleted_existing,
            "reset_index": stats.reset_index,
            "user_id": stats.user_id,
            "include_private": stats.include_private,
        }
        if args.verify_query:
            payload["verify_results"] = [
                {
                    "memory_id": result.memory_id,
                    "date": result.local_date,
                    "type": result.memory_type,
                    "score": round(result.score, 4),
                    "source": result.source_title,
                    "preview": result.text[:240],
                }
                for result in search(
                    args.verify_query,
                    session=session,
                    user_id=args.user_id,
                    include_private=not args.public_only,
                    limit=args.verify_limit,
                )
            ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    finally:
        close_vector_store()
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
