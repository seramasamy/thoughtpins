"""Controlled local memory reset helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from thoughtpins.backup import BackupInfo, create_backup
from thoughtpins.chat import conversation_state
from thoughtpins.config import PROJECT_ROOT, config
from thoughtpins.db import (
    ActionItem,
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    DocumentSource,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    IngestionJob,
    Memory,
    PendingChatAction,
    RawEntry,
    Relationship,
    Report,
)

CONTENT_MODELS = [
    EventParticipant,
    EntityMention,
    ActionItem,
    Expense,
    Relationship,
    Memory,
    DocumentChunk,
    ChatMessage,
    PendingChatAction,
    ChatConversation,
    DocumentSource,
    Event,
    Report,
    IngestionJob,
    RawEntry,
    Entity,
]


@dataclass
class ResetStats:
    dry_run: bool
    backup_path: str = ""
    deleted_rows: dict[str, int] = field(default_factory=dict)
    remaining_rows: dict[str, int] = field(default_factory=dict)
    files_cleared: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    vector_reset: bool = False


def count_content_rows(session: Session) -> dict[str, int]:
    return {model.__tablename__: session.query(model).count() for model in CONTENT_MODELS}


def clear_memory_data(
    session: Session,
    *,
    dry_run: bool = False,
    make_backup: bool = True,
    clear_files: bool = True,
    reset_vectors: bool = True,
    delete_book_folder: str | Path | None = None,
) -> ResetStats:
    """Clear local journal/library data while preserving users/auth configuration."""
    backup: BackupInfo | None = None
    if make_backup and not dry_run:
        backup = create_backup(label="pre_clear_memory", keep=20)

    stats = ResetStats(dry_run=dry_run, backup_path=str(backup.path) if backup else "")
    before = count_content_rows(session)
    stats.deleted_rows = before if dry_run else {}

    if not dry_run:
        for model in CONTENT_MODELS:
            stats.deleted_rows[model.__tablename__] = session.query(model).delete(synchronize_session=False)
        session.commit()

    if clear_files:
        targets = [config.vault_path(), config.reports_path()]
        for target in targets:
            if dry_run:
                stats.files_skipped.append(str(target))
                continue
            if _clear_directory_contents(target):
                stats.files_cleared.append(str(target))
            else:
                stats.files_skipped.append(str(target))

        cache_path = conversation_state.cache_path()
        if not dry_run:
            if conversation_state.clear_conversation_cache(path=cache_path):
                stats.files_cleared.append(str(cache_path))
            else:
                stats.files_skipped.append(str(cache_path))
        else:
            stats.files_skipped.append(str(cache_path))

        if delete_book_folder:
            book_path = Path(delete_book_folder)
            if dry_run:
                stats.files_skipped.append(str(book_path))
            elif _delete_public_domain_test_folder(book_path):
                stats.files_cleared.append(str(book_path))
            else:
                stats.files_skipped.append(str(book_path))

    if reset_vectors and not dry_run:
        try:
            from thoughtpins.memory.vector_store import close_vector_store, get_vector_store

            get_vector_store().reset()
            close_vector_store()
            stats.vector_reset = True
        except Exception:
            stats.vector_reset = False

    stats.remaining_rows = count_content_rows(session)
    return stats


def _clear_directory_contents(path: Path) -> bool:
    target = path.resolve()
    root = PROJECT_ROOT.resolve()
    if target == root or root not in target.parents:
        return False
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
    return True


def _delete_public_domain_test_folder(path: Path) -> bool:
    target = path.resolve()
    parts = {part.lower() for part in target.parts}
    if "thoughtpins_eval_corpus" not in parts or "public domain test series" not in parts:
        return False
    if target.name in {"thoughtpins_eval_corpus", "advisor philosophy", "public domain test series"}:
        return False
    if target.exists():
        shutil.rmtree(target)
    return True
