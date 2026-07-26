"""Conflict-aware reconciliation for incremental portable-vault exports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from thoughtpins.vault.markdown import parse_frontmatter

EXPORT_STATE_PATH = PurePosixPath("_System/thoughtpins-export-state.json")
ConflictPolicy = Literal["preserve", "overwrite"]


@dataclass(slots=True)
class IncrementalExportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    conflicts: int = 0
    conflict_paths: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int | list[str]]:
        return asdict(self)


def write_export_state(vault: Path, managed_paths: set[str] | list[str]) -> Path:
    """Record generated-file hashes without claiming ownership of user notes."""

    managed: dict[str, str] = {}
    for raw_path in sorted(set(managed_paths)):
        rel_path = _safe_relative_path(raw_path)
        if rel_path == EXPORT_STATE_PATH:
            continue
        target = _target(vault, rel_path)
        if target.is_file():
            managed[rel_path.as_posix()] = file_sha256(target)
    return write_export_state_hashes(vault, managed)


def write_export_state_hashes(vault: Path, managed: dict[str, str]) -> Path:
    normalized = {
        _safe_relative_path(path).as_posix(): digest
        for path, digest in managed.items()
        if _valid_sha256(digest) and _safe_relative_path(path) != EXPORT_STATE_PATH
    }
    payload = {
        "app": "Thought Pins",
        "schema": "thoughtpins-export-state/1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "managed": dict(sorted(normalized.items())),
    }
    target = _target(vault, EXPORT_STATE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def load_export_state(vault: Path) -> dict[str, str]:
    path = _target(vault, EXPORT_STATE_PATH)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema") != "thoughtpins-export-state/1":
        return {}
    raw_managed = payload.get("managed")
    if not isinstance(raw_managed, dict):
        return {}
    managed: dict[str, str] = {}
    for raw_path, raw_digest in raw_managed.items():
        try:
            path_key = _safe_relative_path(str(raw_path)).as_posix()
        except ValueError:
            continue
        digest = str(raw_digest).casefold()
        if path_key != EXPORT_STATE_PATH.as_posix() and _valid_sha256(digest):
            managed[path_key] = digest
    return managed


def load_managed_note_paths(vault: Path) -> dict[str, PurePosixPath]:
    """Recover stable note identities so incremental exports avoid title-based renames."""

    identities: dict[str, PurePosixPath] = {}
    for raw_path in load_export_state(vault):
        try:
            rel_path = _safe_relative_path(raw_path)
            target = _target(vault, rel_path)
            if rel_path.suffix.casefold() != ".md" or not target.is_file() or target.stat().st_size > 4 * 1024 * 1024:
                continue
            metadata, _ = parse_frontmatter(target.read_text(encoding="utf-8"))
            identity = str(metadata.get("id") or "").strip()
            if identity and identity not in identities:
                identities[identity] = rel_path
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return identities


def reconcile_generated_vault(
    live_vault: Path,
    generated_vault: Path,
    *,
    conflict_policy: ConflictPolicy = "preserve",
) -> IncrementalExportResult:
    """Merge a fresh projection into a live vault using the last export as a baseline."""

    if conflict_policy not in {"preserve", "overwrite"}:
        raise ValueError("Incremental export conflict policy must be preserve or overwrite")
    desired = load_export_state(generated_vault)
    if not desired:
        raise ValueError("Generated vault is missing a valid export state")
    previous = load_export_state(live_vault)
    live_vault.mkdir(parents=True, exist_ok=True)
    result = IncrementalExportResult()
    next_baseline: dict[str, str] = {}

    for raw_path, desired_digest in sorted(desired.items()):
        rel_path = _safe_relative_path(raw_path)
        source = _target(generated_vault, rel_path)
        target = _target(live_vault, rel_path)
        if not source.is_file() or file_sha256(source) != desired_digest:
            raise ValueError(f"Generated vault file failed integrity verification: {raw_path}")
        previous_digest = previous.get(raw_path)
        if not target.exists():
            _atomic_copy(source, target)
            result.created += 1
            next_baseline[raw_path] = desired_digest
            continue
        if not target.is_file():
            _record_conflict(result, raw_path)
            if previous_digest:
                next_baseline[raw_path] = previous_digest
            continue

        live_digest = file_sha256(target)
        if live_digest == desired_digest:
            result.unchanged += 1
            next_baseline[raw_path] = desired_digest
        elif previous_digest and live_digest == previous_digest:
            _atomic_copy(source, target)
            result.updated += 1
            next_baseline[raw_path] = desired_digest
        elif conflict_policy == "overwrite":
            _atomic_copy(source, target)
            result.updated += 1
            next_baseline[raw_path] = desired_digest
        else:
            _record_conflict(result, raw_path)
            if previous_digest:
                next_baseline[raw_path] = previous_digest

    for raw_path, previous_digest in sorted(previous.items()):
        if raw_path in desired:
            continue
        rel_path = _safe_relative_path(raw_path)
        target = _target(live_vault, rel_path)
        if not target.exists():
            continue
        if target.is_file() and (file_sha256(target) == previous_digest or conflict_policy == "overwrite"):
            target.unlink()
            result.removed += 1
            _remove_empty_parents(target.parent, live_vault)
        else:
            _record_conflict(result, raw_path)
            next_baseline[raw_path] = previous_digest

    write_export_state_hashes(live_vault, next_baseline)
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def _record_conflict(result: IncrementalExportResult, path: str) -> None:
    result.conflicts += 1
    if len(result.conflict_paths) < 200:
        result.conflict_paths.append(path)


def _remove_empty_parents(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    current = path.resolve()
    while current != resolved_root and resolved_root in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _target(root: Path, rel_path: PurePosixPath) -> Path:
    resolved_root = root.resolve()
    target = (resolved_root / Path(rel_path.as_posix())).resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError("Vault path escaped its root")
    return target


def _safe_relative_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid export-state path")
    return path


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


__all__ = [
    "EXPORT_STATE_PATH",
    "IncrementalExportResult",
    "file_sha256",
    "load_export_state",
    "load_managed_note_paths",
    "reconcile_generated_vault",
    "write_export_state",
    "write_export_state_hashes",
]
