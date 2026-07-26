"""Offline deterministic memory-infrastructure evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import thoughtpins.store as store  # noqa: E402
from thoughtpins.config import config  # noqa: E402


def main() -> int:
    db_path = ROOT / ".tmp" / f"memory-infra-eval-{uuid4().hex}.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    old = {
        "DATABASE_URL": (config.DATABASE_URL, type(config).DATABASE_URL),
        "AUTO_CREATE_TABLES": (config.AUTO_CREATE_TABLES, type(config).AUTO_CREATE_TABLES),
        "VECTOR_MODE": (config.VECTOR_MODE, type(config).VECTOR_MODE),
        "EMBEDDING_PROVIDER": (config.EMBEDDING_PROVIDER, type(config).EMBEDDING_PROVIDER),
        "GRAPH_PROVIDER": (config.GRAPH_PROVIDER, type(config).GRAPH_PROVIDER),
        "GRAPH_SHADOW_ENABLED": (config.GRAPH_SHADOW_ENABLED, type(config).GRAPH_SHADOW_ENABLED),
    }
    overrides = {
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "AUTO_CREATE_TABLES": True,
        "VECTOR_MODE": "memory",
        "EMBEDDING_PROVIDER": "local",
        "GRAPH_PROVIDER": "internal_sql",
        "GRAPH_SHADOW_ENABLED": False,
    }
    try:
        for key, value in overrides.items():
            setattr(config, key, value)
            setattr(type(config), key, value)
        store._engine = None
        store._SessionLocal = None
        store.init_db()

        from thoughtpins.memory import search as memory_search
        from thoughtpins.memory.eval import run_memory_infra_eval, seed_memory_infra_fixture

        class FakeVectorStore:
            def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
                return []

        memory_search.get_vector_store = cast(Any, lambda: FakeVectorStore())

        session = store.get_session()
        try:
            user_id = seed_memory_infra_fixture(session)
            result = run_memory_infra_eval(session, user_id=user_id)
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
            return 0 if result.score >= 90 else 1
        finally:
            session.close()
    finally:
        for key, (instance_value, class_value) in old.items():
            setattr(config, key, instance_value)
            setattr(type(config), key, class_value)
        if store._engine is not None:
            store._engine.dispose()
        store._engine = None
        store._SessionLocal = None
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
