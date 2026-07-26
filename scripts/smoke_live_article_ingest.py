"""Live smoke test for public article ingestion with cleanup.

This is intentionally for public or user-authorized URLs. It verifies the full
URL -> document source -> chunks -> memories -> vector index path, then deletes
the temporary user so no test data remains in the main database.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
for path in (SCRIPTS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eval_runtime import cleanup_eval_state, isolate_eval_state  # noqa: E402

EVAL_STATE = isolate_eval_state(ROOT, "live-article-ingest")

from thoughtpins.data_lifecycle import delete_user_data  # noqa: E402
from thoughtpins.db import User  # noqa: E402
from thoughtpins.library import ingest_url  # noqa: E402
from thoughtpins.memory.vector_store import close_vector_store  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402

DEFAULT_URL = "https://www.paulgraham.com/greatwork.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test live public article ingestion.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Public URL to ingest.")
    parser.add_argument("--min-chunks", type=int, default=2, help="Minimum expected document chunks.")
    parser.add_argument("--min-memories", type=int, default=2, help="Minimum expected generated memories.")
    args = parser.parse_args()

    init_db()
    session = get_session()
    external_label = f"article-smoke-{uuid4().hex[:10]}"
    user = User(
        email=f"{external_label}@example.com",
        display_name="Article Smoke User",
        auth_method="smoke",
    )
    session.add(user)
    session.commit()

    deleted: dict[str, int] = {}
    try:
        result = ingest_url(session, args.url, user_id=user.id)
        if result.status != "processed":
            raise RuntimeError(f"expected processed, got {result.status}: {result.error}")
        if result.chunks < args.min_chunks:
            raise RuntimeError(f"expected at least {args.min_chunks} chunks, got {result.chunks}")
        if result.memories < args.min_memories:
            raise RuntimeError(f"expected at least {args.min_memories} memories, got {result.memories}")
        print(
            json.dumps(
                {
                    "status": result.status,
                    "title": result.title[:120],
                    "source_type": result.source_type,
                    "chunks": result.chunks,
                    "memories": result.memories,
                    "access_method": result.access_method,
                    "rights_basis": result.rights_basis,
                    "temporary_user": user.id,
                    "state_isolated": True,
                },
                ensure_ascii=True,
            )
        )
    finally:
        deleted = delete_user_data(session, user.id)
        session.close()
        close_vector_store()
        cleanup_eval_state(EVAL_STATE)

    print(json.dumps({"cleanup": "ok", "deleted": deleted}, ensure_ascii=True))
    print("Live article ingest smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
