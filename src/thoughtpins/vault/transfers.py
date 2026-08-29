"""Durable, resumable upload sessions for background Obsidian imports."""

from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.audit import record_audit_event
from thoughtpins.config import config
from thoughtpins.db import User, VaultImportSession
from thoughtpins.store import get_session
from thoughtpins.tenancy import tenant_context
from thoughtpins.vault.importer import (
    MAX_ARCHIVE_BYTES,
    ConflictPolicy,
    ImportMode,
    VaultImportCancelled,
    import_obsidian_vault,
)

VaultOperation = Literal["preview", "apply"]
ACTIVE_STATUSES = {"uploading", "upload_ready", "queued", "running", "preview_ready", "cancel_requested"}
TERMINAL_STATUSES = {"completed", "failed", "canceled", "expired"}
MAX_CHUNK_BYTES = 512 * 1024
_STORAGE_KEY = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thoughtpins-vault-import")


class VaultTransferStateError(ValueError):
    """The requested transfer transition is not valid from its current state."""


def create_vault_import_session(
    session: Session,
    *,
    user_id: str,
    filename: str,
    expected_bytes: int,
    archive_sha256: str | None,
    mode: ImportMode,
    conflict_policy: ConflictPolicy,
) -> VaultImportSession:
    if not filename.casefold().endswith(".zip"):
        raise ValueError("Obsidian vault imports must be ZIP archives")
    if expected_bytes < 1 or expected_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError(f"Vault archive must be between 1 byte and {MAX_ARCHIVE_BYTES} bytes")
    digest = (archive_sha256 or "").strip().casefold() or None
    if digest and not _SHA256.fullmatch(digest):
        raise ValueError("archive_sha256 must be a lowercase SHA-256 digest")
    if mode not in {"auto", "all_library", "all_journal"}:
        raise ValueError("Invalid vault import mode")
    if conflict_policy not in {"skip", "append"}:
        raise ValueError("Invalid vault conflict policy")

    now = _utcnow()
    transfer = VaultImportSession(
        user_id=user_id,
        status="uploading",
        filename=Path(filename).name[:255] or "obsidian-vault.zip",
        mode=mode,
        conflict_policy=conflict_policy,
        expected_bytes=expected_bytes,
        received_bytes=0,
        archive_sha256=digest,
        storage_key=os.urandom(16).hex(),
        progress_current=0,
        progress_total=expected_bytes,
        progress_stage="uploading",
        result_json={},
        created_at_utc=now,
        updated_at_utc=now,
        expires_at_utc=now + timedelta(hours=max(1, config.VAULT_IMPORT_SESSION_HOURS)),
    )
    session.add(transfer)
    session.commit()
    session.refresh(transfer)
    _ensure_storage_root()
    return transfer


def get_vault_import_session(session: Session, *, user_id: str, transfer_id: str) -> VaultImportSession | None:
    return (
        session.query(VaultImportSession)
        .filter(VaultImportSession.id == transfer_id, VaultImportSession.user_id == user_id)
        .first()
    )


def append_vault_import_chunk(
    session: Session,
    *,
    user_id: str,
    transfer_id: str,
    offset: int,
    content: bytes,
    chunk_sha256: str,
) -> VaultImportSession:
    if not content:
        raise ValueError("Upload chunk is empty")
    configured_limit = max(64 * 1024, min(config.VAULT_UPLOAD_CHUNK_BYTES, MAX_CHUNK_BYTES))
    if len(content) > configured_limit:
        raise ValueError(f"Upload chunk exceeds the {configured_limit} byte limit")
    digest = chunk_sha256.strip().casefold()
    if not _SHA256.fullmatch(digest) or hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Upload chunk SHA-256 does not match its content")

    transfer = _locked_transfer(session, user_id=user_id, transfer_id=transfer_id)
    if not transfer:
        raise LookupError("Vault import session not found")
    if transfer.status != "uploading":
        raise VaultTransferStateError(f"Upload is not writable from status {transfer.status}")
    if offset < 0 or offset + len(content) > transfer.expected_bytes:
        raise ValueError("Upload chunk falls outside the declared archive size")

    path = _archive_path(transfer.storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    current_size = path.stat().st_size if path.exists() else 0
    if current_size > transfer.received_bytes:
        with path.open("r+b") as handle:
            handle.truncate(transfer.received_bytes)
        current_size = transfer.received_bytes
    if current_size < transfer.received_bytes:
        raise VaultTransferStateError("Staged upload is incomplete on disk; start a new upload")

    if offset < transfer.received_bytes:
        if offset + len(content) > transfer.received_bytes:
            raise VaultTransferStateError("Retried chunk overlaps the current upload boundary")
        with path.open("rb") as handle:
            handle.seek(offset)
            existing = handle.read(len(content))
        if existing != content:
            raise VaultTransferStateError("Retried chunk differs from the bytes already accepted")
        return transfer
    if offset != transfer.received_bytes:
        raise VaultTransferStateError(f"Expected upload offset {transfer.received_bytes}")

    with path.open("ab") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        path.chmod(0o600)
    except OSError as exc:
        # The write already succeeded, so failing here is not worth losing the
        # transfer over. It does mean the staged vault file kept the directory's
        # default permissions instead of owner-only, which is worth knowing.
        logger.warning("Could not restrict permissions on a staged vault file ({})", type(exc).__name__)
    transfer.received_bytes += len(content)
    transfer.progress_current = transfer.received_bytes
    transfer.progress_total = transfer.expected_bytes
    transfer.updated_at_utc = _utcnow()
    if transfer.received_bytes == transfer.expected_bytes:
        _verify_complete_archive(transfer, path)
        transfer.status = "upload_ready"
        transfer.progress_stage = "uploaded"
    session.commit()
    session.refresh(transfer)
    return transfer


def queue_vault_import_operation(
    session: Session,
    *,
    user_id: str,
    transfer_id: str,
    operation: VaultOperation,
    conflict_policy: ConflictPolicy | None = None,
) -> VaultImportSession:
    transfer = _locked_transfer(session, user_id=user_id, transfer_id=transfer_id)
    if not transfer:
        raise LookupError("Vault import session not found")
    if operation == "preview" and transfer.status != "upload_ready":
        raise VaultTransferStateError(f"Preview cannot start from status {transfer.status}")
    if operation == "apply" and transfer.status != "preview_ready":
        raise VaultTransferStateError("Import can begin only after its preview is ready")
    if conflict_policy is not None:
        if conflict_policy not in {"skip", "append"}:
            raise ValueError("Invalid vault conflict policy")
        transfer.conflict_policy = conflict_policy
    if not transfer.verified_sha256:
        raise VaultTransferStateError("Uploaded archive has not passed integrity verification")

    transfer.operation = operation
    transfer.status = "queued"
    transfer.cancel_requested = False
    transfer.error = None
    transfer.progress_current = 0
    transfer.progress_total = 0
    transfer.progress_stage = "queued"
    transfer.started_at_utc = None
    transfer.finished_at_utc = None
    transfer.updated_at_utc = _utcnow()
    session.commit()
    try:
        enqueue_vault_import_session(transfer.id, user_id=user_id)
    except Exception as exc:
        transfer.status = "upload_ready" if operation == "preview" else "preview_ready"
        transfer.error = "Background import queue is temporarily unavailable"
        transfer.updated_at_utc = _utcnow()
        session.commit()
        raise RuntimeError("Background import queue is temporarily unavailable") from exc
    session.refresh(transfer)
    return transfer


def cancel_vault_import_session(session: Session, *, user_id: str, transfer_id: str) -> VaultImportSession:
    transfer = _locked_transfer(session, user_id=user_id, transfer_id=transfer_id)
    if not transfer:
        raise LookupError("Vault import session not found")
    if transfer.status in TERMINAL_STATUSES:
        return transfer
    transfer.cancel_requested = True
    transfer.updated_at_utc = _utcnow()
    if transfer.status in {"uploading", "upload_ready", "preview_ready", "queued"}:
        transfer.status = "canceled"
        transfer.progress_stage = "canceled"
        transfer.finished_at_utc = _utcnow()
        _remove_archive(transfer.storage_key)
    else:
        transfer.status = "cancel_requested"
        transfer.progress_stage = "canceling"
    session.commit()
    session.refresh(transfer)
    return transfer


def enqueue_vault_import_session(transfer_id: str, user_id: str | None = None) -> None:
    if config.INGESTION_QUEUE_BACKEND == "celery":
        from thoughtpins.worker import enqueue_celery_vault_import

        enqueue_celery_vault_import(transfer_id, user_id=user_id)
        return
    _executor.submit(run_vault_import_session, transfer_id, user_id)


def run_vault_import_session(transfer_id: str, tenant_user_id: str | None = None) -> None:
    if config.is_production() and not tenant_user_id:
        raise RuntimeError("A tenant identity is required to process vault imports")
    with tenant_context(tenant_user_id):
        _run_vault_import_session(transfer_id, tenant_user_id)


def _run_vault_import_session(transfer_id: str, tenant_user_id: str | None) -> None:
    session = get_session()
    transfer: VaultImportSession | None = None
    try:
        query = session.query(VaultImportSession).filter(
            VaultImportSession.id == transfer_id,
            VaultImportSession.status == "queued",
        )
        if tenant_user_id:
            query = query.filter(VaultImportSession.user_id == tenant_user_id)
        transfer = query.first()
        if not transfer:
            return
        transfer.status = "running"
        transfer.progress_stage = "opening"
        transfer.started_at_utc = _utcnow()
        transfer.updated_at_utc = _utcnow()
        session.commit()

        path = _archive_path(transfer.storage_key)
        if not path.is_file() or path.stat().st_size != transfer.expected_bytes:
            raise RuntimeError("Staged vault archive is unavailable")
        archive = path.read_bytes()
        if hashlib.sha256(archive).hexdigest() != transfer.verified_sha256:
            raise RuntimeError("Staged vault archive failed integrity verification")

        last_progress = (-1, -1, "")

        def progress(current: int, total: int, stage: str) -> None:
            nonlocal last_progress
            marker = (current, total, stage)
            if marker == last_progress or (current not in {0, total} and current % 25 != 0):
                return
            last_progress = marker
            transfer.progress_current = current
            transfer.progress_total = total
            transfer.progress_stage = stage
            transfer.updated_at_utc = _utcnow()
            session.commit()

        def canceled() -> bool:
            session.refresh(transfer, attribute_names=["cancel_requested", "status"])
            return bool(transfer.cancel_requested or transfer.status == "cancel_requested")

        result = import_obsidian_vault(
            session,
            user_id=transfer.user_id,
            filename=transfer.filename,
            archive=archive,
            mode=transfer.mode,
            conflict_policy=transfer.conflict_policy,
            dry_run=transfer.operation == "preview",
            enqueue_jobs=transfer.operation == "apply",
            progress_callback=progress,
            cancel_check=canceled,
        )
        transfer.result_json = result.as_dict()
        transfer.status = "preview_ready" if transfer.operation == "preview" else "completed"
        transfer.progress_stage = "preview_ready" if transfer.operation == "preview" else "completed"
        transfer.progress_current = result.notes_discovered
        transfer.progress_total = result.notes_discovered
        transfer.finished_at_utc = _utcnow()
        transfer.updated_at_utc = _utcnow()
        transfer.error = None
        session.commit()
        record_audit_event(
            session,
            user_id=transfer.user_id,
            action="vault.import.previewed" if transfer.operation == "preview" else "vault.imported",
            metadata={
                "transfer_id": transfer.id,
                "archive_sha256": transfer.verified_sha256,
                "notes_discovered": result.notes_discovered,
                "conflicts": result.conflicts,
                "imported": result.imported,
            },
        )
        if transfer.operation == "apply":
            _remove_archive(transfer.storage_key)
    except VaultImportCancelled:
        if transfer is not None:
            transfer.status = "canceled"
            transfer.progress_stage = "canceled"
            transfer.finished_at_utc = _utcnow()
            transfer.updated_at_utc = _utcnow()
            session.commit()
            _remove_archive(transfer.storage_key)
    except Exception as exc:
        logger.exception("Background vault import failed")
        session.rollback()
        if transfer is not None:
            transfer.status = "failed"
            transfer.progress_stage = "failed"
            transfer.error = str(exc)[:500]
            transfer.finished_at_utc = _utcnow()
            transfer.updated_at_utc = _utcnow()
            session.commit()
    finally:
        session.close()


def recover_vault_import_sessions(*, stale_after_seconds: int = 900) -> int:
    user_ids = _active_user_ids() if config.is_production() else [None]
    return sum(_recover_vault_import_sessions_for_user(user_id, stale_after_seconds) for user_id in user_ids)


def _recover_vault_import_sessions_for_user(user_id: str | None, stale_after_seconds: int) -> int:
    with tenant_context(user_id):
        return _recover_vault_import_sessions_in_context(user_id, stale_after_seconds)


def _recover_vault_import_sessions_in_context(user_id: str | None, stale_after_seconds: int) -> int:
    session = get_session()
    try:
        cutoff = _utcnow() - timedelta(seconds=max(60, stale_after_seconds))
        query = session.query(VaultImportSession).filter(
            (VaultImportSession.status == "queued")
            | ((VaultImportSession.status == "running") & (VaultImportSession.updated_at_utc < cutoff)),
        )
        if user_id:
            query = query.filter(VaultImportSession.user_id == user_id)
        rows = query.limit(100).all()
        for transfer in rows:
            transfer.status = "queued"
            transfer.progress_stage = "queued"
            transfer.updated_at_utc = _utcnow()
        session.commit()
        for transfer in rows:
            enqueue_vault_import_session(transfer.id, user_id=transfer.user_id)
        return len(rows)
    finally:
        session.close()


def cleanup_expired_vault_import_sessions(*, limit: int = 100) -> int:
    user_ids = _active_user_ids() if config.is_production() else [None]
    remaining = max(1, min(limit, 1_000))
    cleaned = 0
    for user_id in user_ids:
        if cleaned >= remaining:
            break
        with tenant_context(user_id):
            cleaned += _cleanup_expired_in_context(user_id, remaining - cleaned)
    return cleaned


def _cleanup_expired_in_context(user_id: str | None, limit: int) -> int:
    session = get_session()
    try:
        query = session.query(VaultImportSession).filter(
            VaultImportSession.expires_at_utc < _utcnow(),
            VaultImportSession.status.in_(ACTIVE_STATUSES),
        )
        if user_id:
            query = query.filter(VaultImportSession.user_id == user_id)
        rows = query.limit(max(1, min(limit, 1_000))).all()
        for transfer in rows:
            transfer.status = "expired"
            transfer.progress_stage = "expired"
            transfer.cancel_requested = True
            transfer.finished_at_utc = _utcnow()
            transfer.updated_at_utc = _utcnow()
            _remove_archive(transfer.storage_key)
        session.commit()
        return len(rows)
    finally:
        session.close()


def _active_user_ids() -> list[str]:
    # All users, deliberately including deactivated tombstones: an in-flight
    # upload whose owner deleted their account still has an archive on disk,
    # and filtering to active users left exactly those archives unswept
    # forever. Account deletion removes them too; this is the backstop.
    session = get_session()
    try:
        return [str(row[0]) for row in session.query(User.id).all()]
    finally:
        session.close()


def vault_import_session_payload(transfer: VaultImportSession) -> dict[str, Any]:
    total = transfer.progress_total or transfer.expected_bytes or 1
    current = transfer.progress_current if transfer.progress_total else transfer.received_bytes
    return {
        "id": transfer.id,
        "status": transfer.status,
        "operation": transfer.operation,
        "filename": transfer.filename,
        "mode": transfer.mode,
        "conflict_policy": transfer.conflict_policy,
        "expected_bytes": transfer.expected_bytes,
        "received_bytes": transfer.received_bytes,
        "archive_sha256": transfer.verified_sha256,
        "progress_current": current,
        "progress_total": total,
        "progress_percent": round(min(100.0, max(0.0, current * 100.0 / total)), 2),
        "progress_stage": transfer.progress_stage,
        "cancel_requested": bool(transfer.cancel_requested),
        "result": transfer.result_json or None,
        "error": transfer.error,
        "created_at_utc": _iso(transfer.created_at_utc),
        "updated_at_utc": _iso(transfer.updated_at_utc),
        "finished_at_utc": _iso(transfer.finished_at_utc),
        "expires_at_utc": _iso(transfer.expires_at_utc),
    }


def _locked_transfer(session: Session, *, user_id: str, transfer_id: str) -> VaultImportSession | None:
    return (
        session.query(VaultImportSession)
        .filter(VaultImportSession.id == transfer_id, VaultImportSession.user_id == user_id)
        .with_for_update()
        .first()
    )


def _verify_complete_archive(transfer: VaultImportSession, path: Path) -> None:
    digest = _hash_file(path)
    if transfer.archive_sha256 and digest != transfer.archive_sha256:
        raise ValueError("Completed vault archive SHA-256 does not match the declared digest")
    transfer.verified_sha256 = digest


def _archive_path(storage_key: str) -> Path:
    if not _STORAGE_KEY.fullmatch(storage_key):
        raise RuntimeError("Invalid vault import storage key")
    root = _ensure_storage_root()
    path = (root / f"{storage_key}.zip.part").resolve()
    if root != path.parent:
        raise RuntimeError("Vault import path escaped its storage root")
    return path


def _ensure_storage_root() -> Path:
    root = config.vault_import_path()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _remove_archive(storage_key: str) -> None:
    path = _archive_path(storage_key)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove staged vault archive for transfer {}", storage_key[:8])


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


__all__ = [
    "MAX_CHUNK_BYTES",
    "VaultTransferStateError",
    "append_vault_import_chunk",
    "cancel_vault_import_session",
    "cleanup_expired_vault_import_sessions",
    "create_vault_import_session",
    "enqueue_vault_import_session",
    "get_vault_import_session",
    "queue_vault_import_operation",
    "recover_vault_import_sessions",
    "run_vault_import_session",
    "vault_import_session_payload",
]
