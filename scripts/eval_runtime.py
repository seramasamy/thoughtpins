"""Helpers for live eval scripts.

Live evals should not share the main local Qdrant path with a running API
server. Qdrant local is file-backed, so sharing it across processes can block
maintenance/test scripts for minutes.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class IsolatedEvalState:
    root: Path
    database: Path
    qdrant: Path
    vault: Path
    reports: Path
    backups: Path
    conversation_cache: Path


def isolate_eval_state(root: Path, name: str) -> IsolatedEvalState:
    """Redirect every writable local runtime surface into one disposable root."""
    token = uuid4().hex[:10]
    state_root = root / ".tmp" / "eval-state" / f"{name}-{token}"
    state = IsolatedEvalState(
        root=state_root,
        database=state_root / "data" / "thoughtpins.sqlite3",
        qdrant=state_root / "qdrant",
        vault=state_root / "vault",
        reports=state_root / "reports",
        backups=state_root / "backups",
        conversation_cache=state_root / "data" / "conversation_cache.json",
    )
    for path in (state.database.parent, state.qdrant, state.vault, state.reports, state.backups):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite:///{state.database.as_posix()}",
            "AUTO_CREATE_TABLES": "true",
            "RUN_STARTUP_RECOVERY": "false",
            "QDRANT_PATH": str(state.qdrant),
            "VAULT_PATH": str(state.vault),
            "REPORTS_PATH": str(state.reports),
            "BACKUPS_PATH": str(state.backups),
            "CONVERSATION_CACHE_PATH": str(state.conversation_cache),
        }
    )
    return state


def cleanup_eval_state(state: IsolatedEvalState | None) -> bool:
    """Close local stores and remove only the state root created by this process."""
    if state is None:
        return False
    try:
        from thoughtpins.memory.vector_store import close_vector_store

        close_vector_store()
    except Exception:
        pass
    try:
        import thoughtpins.store as store

        if store._engine is not None:
            store._engine.dispose()
        store._engine = None
        store._SessionLocal = None
    except Exception:
        pass
    shutil.rmtree(state.root, ignore_errors=True)
    return not state.root.exists()


def isolate_eval_qdrant(root: Path, name: str) -> Path | None:
    """Point this process at a disposable Qdrant path unless explicitly disabled."""
    if os.getenv("THOUGHTPINS_EVAL_USE_MAIN_VECTOR_STORE", "").strip().lower() in {"1", "true", "yes"}:
        return None
    vector_mode = os.getenv("VECTOR_MODE", "qdrant_local").strip().lower()
    if vector_mode and vector_mode != "qdrant_local":
        return None
    qdrant_path = root / ".tmp" / "eval-qdrant" / f"{name}-{uuid4().hex[:10]}"
    os.environ["QDRANT_PATH"] = str(qdrant_path)
    return qdrant_path


def isolate_eval_database(root: Path, name: str) -> Path | None:
    """Point an evaluation process at a disposable SQLite database by default."""
    if os.getenv("THOUGHTPINS_EVAL_USE_MAIN_DATABASE", "").strip().lower() in {"1", "true", "yes"}:
        return None
    database_path = root / ".tmp" / "eval-db" / f"{name}-{uuid4().hex[:10]}.sqlite3"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    os.environ["AUTO_CREATE_TABLES"] = "true"
    os.environ["RUN_STARTUP_RECOVERY"] = "false"
    return database_path


def cleanup_eval_qdrant(path: Path | None) -> bool:
    if path is None:
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


def cleanup_eval_database(path: Path | None) -> bool:
    if path is None:
        return False
    removed = True
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            removed = False
    return removed and not path.exists()
