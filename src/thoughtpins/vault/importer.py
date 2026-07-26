"""Secure, tenant-scoped import of Obsidian-compatible vault archives."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import DocumentSource, IngestionJob
from thoughtpins.jobs import (
    IngestionDispatchUnavailable,
    create_ingestion_job,
    dispatch_ingestion_job,
    enqueue_ingestion_job,
    get_job,
)
from thoughtpins.library import ingest_document_text
from thoughtpins.vault.frontmatter import extract_wikilinks
from thoughtpins.vault.import_archive import MAX_ARCHIVE_BYTES, MAX_MEMBERS, VaultNote, read_vault_archive

ImportMode = Literal["auto", "all_library", "all_journal"]
ConflictPolicy = Literal["skip", "append"]
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]

MAX_WARNINGS = 100
MAX_RESULT_IDS = 200
MAX_PREVIEW_ITEMS = 200

_THOUGHTPINS_DERIVED_TYPES = {
    "home",
    "index",
    "daily_journal",
    "person",
    "place",
    "organization",
    "project",
    "event",
    "thing",
    "concept",
}
_JOURNAL_TYPES = {"entry", "journal", "journal_entry", "daily", "daily_note", "diary"}
_JOURNAL_PATH_PARTS = {"entries", "journal", "journals", "diary", "daily", "daily notes", "daily-notes"}
_DATE_IN_NAME = re.compile(r"(?<!\d)(20\d{2})[-_.](0[1-9]|1[0-2])[-_.]([0-2]\d|3[01])(?!\d)")


@dataclass(frozen=True)
class VaultImportPreviewItem:
    path: str
    title: str
    kind: str
    state: str
    action: str


class VaultImportCancelled(RuntimeError):
    """Raised when a background vault import observes a cancellation request."""


@dataclass
class VaultImportResult:
    status: str = "completed"
    format: str = "obsidian_vault"
    mode: str = "auto"
    thoughtpins_export: bool = False
    dry_run: bool = False
    archive_sha256: str = ""
    files_discovered: int = 0
    notes_discovered: int = 0
    attachments_skipped: int = 0
    structural_files_skipped: int = 0
    canvases_discovered: int = 0
    canvas_documents_imported: int = 0
    journal_notes: int = 0
    library_notes: int = 0
    journal_jobs_queued: int = 0
    library_documents_imported: int = 0
    new_notes: int = 0
    changed_notes: int = 0
    unchanged_notes: int = 0
    conflicts: int = 0
    duplicates: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    preview_items: list[VaultImportPreviewItem] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return self.journal_jobs_queued + self.library_documents_imported

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["imported"] = self.imported
        return payload


def import_obsidian_vault(
    session: Session,
    *,
    user_id: str,
    filename: str,
    archive: bytes,
    mode: ImportMode = "auto",
    conflict_policy: ConflictPolicy = "skip",
    dry_run: bool = False,
    enqueue_jobs: bool = True,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> VaultImportResult:
    """Import Markdown notes from a user-provided Obsidian vault ZIP.

    Journal-like notes are queued through the normal extraction pipeline. Other
    notes become library documents, which keeps external knowledge recallable
    without treating it as autobiographical memory.
    """

    _validate_import_request(filename, archive, mode, conflict_policy)
    result = VaultImportResult(
        mode=mode,
        dry_run=dry_run,
        archive_sha256=hashlib.sha256(archive).hexdigest(),
    )
    package = read_vault_archive(archive, lambda message: _warn(result, message))
    _record_package_metadata(result, package)
    notes = package.notes
    result.files_discovered = package.files_discovered
    result.notes_discovered = len(notes)
    result.attachments_skipped = package.attachments_skipped
    result.structural_files_skipped = package.structural_files_skipped
    result.canvases_discovered = package.canvases_discovered

    existing_versions = _existing_import_versions(session, user_id)
    queued_job_ids: list[str] = []
    total_notes = len(notes)
    _notify_progress(progress_callback, 0, total_notes, "classifying")
    for index, note in enumerate(notes, start=1):
        _raise_if_cancelled(cancel_check)
        job_id = _import_one_note(
            session,
            result=result,
            note=note,
            user_id=user_id,
            mode=mode,
            conflict_policy=conflict_policy,
            existing_versions=existing_versions,
            index=index,
            total_notes=total_notes,
            progress_callback=progress_callback,
        )
        if job_id:
            queued_job_ids.append(job_id)

    if enqueue_jobs and not dry_run:
        _dispatch_journal_jobs(
            session,
            result=result,
            user_id=user_id,
            job_ids=queued_job_ids,
            total_notes=total_notes,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    if result.errors:
        result.status = "completed_with_errors"
    elif result.warnings:
        result.status = "completed_with_warnings"
    _notify_progress(progress_callback, total_notes, total_notes, "completed")
    return result


def _validate_import_request(
    filename: str,
    archive: bytes,
    mode: ImportMode,
    conflict_policy: ConflictPolicy,
) -> None:
    if mode not in {"auto", "all_library", "all_journal"}:
        raise ValueError("Import mode must be auto, all_library, or all_journal")
    if conflict_policy not in {"skip", "append"}:
        raise ValueError("Conflict policy must be skip or append")
    if not filename.lower().endswith(".zip"):
        raise ValueError("Obsidian vault imports must be ZIP archives")
    if not archive:
        raise ValueError("Vault archive is empty")
    if len(archive) > MAX_ARCHIVE_BYTES:
        limit_mb = MAX_ARCHIVE_BYTES // (1024 * 1024)
        raise ValueError(f"Vault archive exceeds the {limit_mb} MB compressed limit")


def _record_package_metadata(result: VaultImportResult, package) -> None:
    result.thoughtpins_export = package.thoughtpins_export
    result.format = "thoughtpins_obsidian_vault" if package.thoughtpins_export else "obsidian_vault"


def _import_one_note(
    session: Session,
    *,
    result: VaultImportResult,
    note: VaultNote,
    user_id: str,
    mode: ImportMode,
    conflict_policy: ConflictPolicy,
    existing_versions: dict[str, set[str]],
    index: int,
    total_notes: int,
    progress_callback: ProgressCallback | None,
) -> str | None:
    kind = _classify_note(note, mode=mode, thoughtpins_export=result.thoughtpins_export)
    if kind == "skip":
        result.skipped += 1
        _notify_progress(progress_callback, index, total_notes, "classifying")
        return None

    text = _note_text(note, kind=kind, thoughtpins_export=result.thoughtpins_export)
    if len(text.strip()) < 3:
        result.skipped += 1
        _warn(result, f"Skipped empty note: {note.path}")
        _notify_progress(progress_callback, index, total_notes, "classifying")
        return None

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path_key = note.path.casefold()
    state, action = _revision_state(
        result,
        digest=digest,
        previous_digests=existing_versions.get(path_key, set()),
        conflict_policy=conflict_policy,
    )
    _preview(result, note=note, kind=kind, state=state, action=action)
    if kind == "journal":
        return _queue_journal_note(
            session,
            result=result,
            note=note,
            user_id=user_id,
            text=text,
            digest=digest,
            path_key=path_key,
            state=state,
            conflict_policy=conflict_policy,
            existing_versions=existing_versions,
            index=index,
            total_notes=total_notes,
            progress_callback=progress_callback,
        )
    _persist_library_note(
        session,
        result=result,
        note=note,
        text=text,
        digest=digest,
        path_key=path_key,
        state=state,
        conflict_policy=conflict_policy,
        existing_versions=existing_versions,
        user_id=user_id,
        index=index,
        total_notes=total_notes,
        progress_callback=progress_callback,
    )
    return None


def _revision_state(
    result: VaultImportResult,
    *,
    digest: str,
    previous_digests: set[str],
    conflict_policy: ConflictPolicy,
) -> tuple[str, str]:
    if not previous_digests:
        result.new_notes += 1
        return "new", "import"
    if digest in previous_digests:
        result.unchanged_notes += 1
        result.duplicates += 1
        return "unchanged", "skip_duplicate"
    result.changed_notes += 1
    result.conflicts += 1
    action = "append_revision" if conflict_policy == "append" else "skip_conflict"
    return "changed", action


def _skip_note_write(
    result: VaultImportResult,
    *,
    state: str,
    conflict_policy: ConflictPolicy,
    index: int,
    total_notes: int,
    progress_callback: ProgressCallback | None,
) -> bool:
    if result.dry_run or state == "unchanged":
        _notify_progress(progress_callback, index, total_notes, "classifying")
        return True
    if state == "changed" and conflict_policy == "skip":
        result.skipped += 1
        _notify_progress(progress_callback, index, total_notes, "classifying")
        return True
    return False


def _queue_journal_note(
    session: Session,
    *,
    result: VaultImportResult,
    note: VaultNote,
    user_id: str,
    text: str,
    digest: str,
    path_key: str,
    state: str,
    conflict_policy: ConflictPolicy,
    existing_versions: dict[str, set[str]],
    index: int,
    total_notes: int,
    progress_callback: ProgressCallback | None,
) -> str | None:
    result.journal_notes += 1
    if _skip_note_write(
        result,
        state=state,
        conflict_policy=conflict_policy,
        index=index,
        total_notes=total_notes,
        progress_callback=progress_callback,
    ):
        return None
    user_importance = _note_importance(note)
    if "importance" in note.metadata and user_importance is None and note.metadata.get("importance") is not None:
        _warn(result, f"Ignored invalid importance in {note.path}; expected a value from 1 to 5.")
    job = create_ingestion_job(
        session,
        user_id=user_id,
        text=text,
        source="obsidian_import",
        metadata={
            "force_journal": True,
            "occurred_at_utc": _note_datetime_utc(note).isoformat(),
            "dedup_key": f"obsidian:{path_key}:{digest}",
            "vault_path": note.path,
            "vault_content_sha256": digest,
            "vault_archive_sha256": result.archive_sha256,
            "vault_format": result.format,
            "vault_revision_state": state,
            "user_importance": user_importance,
        },
    )
    result.journal_jobs_queued += 1
    existing_versions.setdefault(path_key, set()).add(digest)
    if len(result.job_ids) < MAX_RESULT_IDS:
        result.job_ids.append(job.id)
    _notify_progress(progress_callback, index, total_notes, "importing")
    return job.id


def _persist_library_note(
    session: Session,
    *,
    result: VaultImportResult,
    note: VaultNote,
    text: str,
    digest: str,
    path_key: str,
    state: str,
    conflict_policy: ConflictPolicy,
    existing_versions: dict[str, set[str]],
    user_id: str,
    index: int,
    total_notes: int,
    progress_callback: ProgressCallback | None,
) -> None:
    result.library_notes += 1
    if _skip_note_write(
        result,
        state=state,
        conflict_policy=conflict_policy,
        index=index,
        total_notes=total_notes,
        progress_callback=progress_callback,
    ):
        return
    try:
        imported = _ingest_library_note(
            session,
            user_id=user_id,
            note=note,
            text=text,
            archive_sha256=result.archive_sha256,
            thoughtpins_export=result.thoughtpins_export,
            content_sha256=digest,
            revision_state=state,
        )
        if imported.duplicate:
            result.duplicates += 1
        else:
            result.library_documents_imported += 1
            if str(note.metadata.get("type") or "").casefold() == "canvas":
                result.canvas_documents_imported += 1
            if len(result.document_ids) < MAX_RESULT_IDS:
                result.document_ids.append(imported.document_id)
            existing_versions.setdefault(path_key, set()).add(digest)
    except Exception as exc:
        session.rollback()
        _error(result, f"Could not import {note.path}: {str(exc)[:240]}")
    _notify_progress(progress_callback, index, total_notes, "importing")


def _dispatch_journal_jobs(
    session: Session,
    *,
    result: VaultImportResult,
    user_id: str,
    job_ids: list[str],
    total_notes: int,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> None:
    _notify_progress(progress_callback, total_notes, total_notes, "dispatching")
    for job_id in job_ids:
        _raise_if_cancelled(cancel_check)
        queued_job = get_job(session, user_id=user_id, job_id=job_id)
        if not queued_job:
            continue
        try:
            dispatch_ingestion_job(
                session,
                queued_job,
                user_id=user_id,
                enqueue_fn=enqueue_ingestion_job,
            )
        except IngestionDispatchUnavailable:
            _warn(result, "Journal processing will resume when the background queue is available.")
            break


def _classify_note(note: VaultNote, *, mode: ImportMode, thoughtpins_export: bool) -> str:
    note_type = str(note.metadata.get("type") or "").casefold().replace(" ", "_")
    source = str(note.metadata.get("source") or "").casefold()
    if thoughtpins_export:
        if note_type == "entry":
            return "skip" if source.startswith("library_") else "journal"
        if note_type in {"article", "document"}:
            return "library"
        if note_type in _THOUGHTPINS_DERIVED_TYPES or note.path.casefold() == "vault home.md":
            return "skip"

    if mode == "all_library":
        return "library"
    if mode == "all_journal":
        return "journal"

    tags = {tag.casefold() for tag in _as_string_list(note.metadata.get("tags"))}
    path_parts = {part.casefold() for part in PurePosixPath(note.path).parts[:-1]}
    journal_tag = any(tag in {"journal", "diary", "daily"} or tag.startswith("journal/") for tag in tags)
    if note_type in _JOURNAL_TYPES or journal_tag or bool(path_parts & _JOURNAL_PATH_PARTS):
        return "journal"
    return "library"


def _note_text(note: VaultNote, *, kind: str, thoughtpins_export: bool) -> str:
    if thoughtpins_export and kind == "journal":
        extracted = _section_fence(note.body, "Original Text")
        if extracted is not None:
            return extracted.strip()
    if thoughtpins_export and kind == "library":
        extracted = _section_fence(note.body, "Extracted Text")
        if extracted is not None:
            return extracted.strip()
    return note.body.strip()


def _section_fence(markdown: str, heading: str) -> str | None:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}\s*\n\s*```[^\n]*\n(.*?)\n```(?:\s*$|\s*\n)",
    )
    match = pattern.search(markdown)
    return match.group(1) if match else None


def _note_datetime_utc(note: VaultNote) -> datetime:
    candidates = [note.metadata.get("created"), note.metadata.get("date"), note.metadata.get("updated")]
    name_match = _DATE_IN_NAME.search(PurePosixPath(note.path).stem)
    if name_match:
        candidates.append("-".join(name_match.groups()))
    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed is not None:
            return parsed
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: Any) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        normalized = text_value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if "T" not in normalized and " " not in normalized:
            parsed = datetime.combine(parsed.date(), time(hour=12))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(config.LOCAL_TIMEZONE))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return None


def _existing_import_versions(session: Session, user_id: str) -> dict[str, set[str]]:
    versions: dict[str, set[str]] = {}
    jobs = (
        session.query(IngestionJob)
        .filter(IngestionJob.user_id == user_id, IngestionJob.source == "obsidian_import")
        .order_by(IngestionJob.created_at_utc.desc())
        .limit(MAX_MEMBERS * 2)
    )
    for row in jobs.yield_per(1_000):
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        path = str(metadata.get("vault_path") or "").casefold()
        digest = (
            str(metadata.get("vault_content_sha256") or "")
            or hashlib.sha256(
                str(row.raw_text or "").encode("utf-8"),
            ).hexdigest()
        )
        if path and digest:
            versions.setdefault(path, set()).add(digest)

    documents = (
        session.query(DocumentSource)
        .filter(DocumentSource.user_id == user_id, DocumentSource.access_method == "obsidian_vault_import")
        .order_by(DocumentSource.created_at_utc.desc())
        .limit(MAX_MEMBERS * 2)
    )
    for document in documents.yield_per(1_000):
        metadata = document.metadata_json if isinstance(document.metadata_json, dict) else {}
        imported = metadata.get("obsidian_import")
        if not isinstance(imported, dict):
            continue
        path = str(imported.get("path") or "").casefold()
        digest = (
            str(imported.get("content_sha256") or "")
            or hashlib.sha256(
                str(document.raw_text or "").encode("utf-8"),
            ).hexdigest()
        )
        if path and digest:
            versions.setdefault(path, set()).add(digest)
    return versions


def _ingest_library_note(
    session: Session,
    *,
    user_id: str,
    note: VaultNote,
    text: str,
    archive_sha256: str,
    thoughtpins_export: bool,
    content_sha256: str,
    revision_state: str,
):
    note_type = str(note.metadata.get("type") or "").casefold()
    source_type = {
        "article": "article",
        "canvas": "obsidian_canvas",
    }.get(note_type, "obsidian_note")
    source_url = _source_value(note.body, "URL") if thoughtpins_export else None
    if not source_url or source_url in {"not provided", "unknown"}:
        source_url = f"obsidian://vault/{quote(note.path, safe='/')}"
    author = str(note.metadata.get("author") or "").strip() or _source_value(note.body, "Author")
    metadata = {
        "obsidian_import": {
            "path": note.path,
            "frontmatter": note.metadata,
            "wikilinks": extract_wikilinks(note.body, note.metadata)[:200],
            "archive_sha256": archive_sha256,
            "thoughtpins_export": thoughtpins_export,
            "content_sha256": content_sha256,
            "revision_state": revision_state,
        }
    }
    return ingest_document_text(
        session,
        text,
        user_id=user_id,
        source_type=source_type,
        title=note.title,
        author=author,
        original_url=source_url if source_url.startswith(("http://", "https://")) else None,
        source_url=source_url,
        access_method="obsidian_vault_import",
        rights_basis="user_provided",
        metadata_json=metadata,
        defer_vector_index=True,
        user_importance=_note_importance(note),
    )


def _source_value(markdown: str, label: str) -> str | None:
    match = re.search(rf"(?mi)^-\s*{re.escape(label)}:\s*(.+?)\s*$", markdown)
    return match.group(1).strip()[:4_000] if match else None


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [str(value).strip()] if str(value).strip() else []


def _note_importance(note: VaultNote) -> int | None:
    value = note.metadata.get("importance")
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError):
        return None
    return rating if 1 <= rating <= 5 else None


def _preview(
    result: VaultImportResult,
    *,
    note: VaultNote,
    kind: str,
    state: str,
    action: str,
) -> None:
    if len(result.preview_items) >= MAX_PREVIEW_ITEMS:
        return
    result.preview_items.append(
        VaultImportPreviewItem(
            path=note.path,
            title=note.title,
            kind=kind,
            state=state,
            action=action,
        ),
    )


def _notify_progress(callback: ProgressCallback | None, current: int, total: int, stage: str) -> None:
    if callback is not None:
        callback(current, total, stage)


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise VaultImportCancelled("Vault import canceled")


def _warn(result: VaultImportResult, message: str) -> None:
    if len(result.warnings) < MAX_WARNINGS:
        result.warnings.append(message)


def _error(result: VaultImportResult, message: str) -> None:
    if len(result.errors) < MAX_WARNINGS:
        result.errors.append(message)


__all__ = [
    "ConflictPolicy",
    "ImportMode",
    "MAX_ARCHIVE_BYTES",
    "VaultImportCancelled",
    "VaultImportPreviewItem",
    "VaultImportResult",
    "VaultNote",
    "import_obsidian_vault",
]
