"""Founder/local backup and restore helpers."""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from thoughtpins.backup_provenance import (
    checksum_path,
    read_backup_provenance,
    remove_backup_provenance,
    sidecar_path,
    verify_backup_provenance,
    write_backup_provenance,
)
from thoughtpins.config import config

EXCLUDED_BACKUP_FILENAMES = {".lock", "LOCK"}


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    size_bytes: int
    created_at_utc: datetime
    sha256: str = ""
    sidecar_path: Path | None = None
    checksum_path: Path | None = None


@dataclass(frozen=True)
class RestoreSmokeInfo:
    backup_path: Path
    target_path: Path
    size_bytes: int
    restored_files: int
    included_roots: list[str]
    cleaned_up: bool


def backup_dir() -> Path:
    path = config.backups_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_backup(*, label: str = "manual", keep: int = 14) -> BackupInfo:
    """Create a zip backup of local persistent stores.

    Secrets such as `.env` are intentionally excluded. This is for founder/local
    recovery of journal data, vault files, and vector store data.
    """
    now = datetime.now(timezone.utc)
    safe_label = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in label)[:40] or "manual"
    out_dir = backup_dir()
    zip_path = out_dir / f"thoughtpins_backup_{now.strftime('%Y-%m-%d_%H%M%S')}_{safe_label}.zip"

    roots = _backup_roots()

    manifest = {
        "created_at_utc": now.isoformat(),
        "label": safe_label,
        "environment": config.ENVIRONMENT,
        "database_url_kind": _database_url_kind(),
        "included_roots": [name for name, path in roots if path.exists()],
        "excluded_runtime_files": sorted(EXCLUDED_BACKUP_FILENAMES),
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        written: set[str] = set()
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for name, root in roots:
            if not root.exists():
                continue
            _write_directory(archive, Path(name), written)
            for path in root.rglob("*"):
                archive_path = Path(name) / path.relative_to(root)
                if path.is_dir():
                    _write_directory(archive, archive_path, written)
                    continue
                if not path.is_file() or _should_skip_backup_file(path):
                    continue
                archive.write(path, archive_path)
                written.add(archive_path.as_posix())
    provenance = write_backup_provenance(
        zip_path,
        created_at_utc=now,
        contains_local_secrets=False,
        encryption_scheme="none",
    )
    _write_marker(now)
    prune_backups(keep=keep)
    return BackupInfo(
        path=zip_path,
        size_bytes=zip_path.stat().st_size,
        created_at_utc=now,
        sha256=str(provenance["sha256"]),
        sidecar_path=sidecar_path(zip_path),
        checksum_path=checksum_path(zip_path),
    )


def list_backups(limit: int = 10) -> list[BackupInfo]:
    items: list[BackupInfo] = []
    for path in sorted(backup_dir().glob("thoughtpins_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        provenance = read_backup_provenance(path)
        items.append(
            BackupInfo(
                path=path,
                size_bytes=stat.st_size,
                created_at_utc=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                sha256=str(provenance.get("sha256", "")) if provenance else "",
                sidecar_path=sidecar_path(path) if provenance else None,
                checksum_path=checksum_path(path) if checksum_path(path).is_file() else None,
            )
        )
    return items[:limit]


def latest_backup() -> BackupInfo | None:
    backups = list_backups(limit=1)
    return backups[0] if backups else None


def latest_backup_age_seconds() -> int | None:
    backup = latest_backup()
    if not backup:
        return None
    return max(0, int(time.time() - backup.path.stat().st_mtime))


def prune_backups(*, keep: int = 14) -> int:
    backups = list(backup_dir().glob("thoughtpins_backup_*.zip"))
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in backups[max(0, keep) :]:
        old.unlink(missing_ok=True)
        remove_backup_provenance(old)
        removed += 1
    return removed


def restore_backup(backup_path: str | Path, *, target_root: str | Path, overwrite: bool = False) -> Path:
    """Extract a backup into a target root.

    This does not mutate the active app directory unless the caller points
    `target_root` there. Prefer restoring into a fresh directory, inspecting the
    manifest, then copying the needed files while the app is stopped.
    """
    source = Path(backup_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Backup not found: {source}")
    if source.suffix.lower() != ".zip":
        raise ValueError("Backup path must be a .zip file")
    verify_backup_provenance(source, required=False)

    target = Path(target_root).resolve()
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise FileExistsError(f"Target directory is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            destination.relative_to(target)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return target


def smoke_restore_backup(
    *,
    backup_path: str | Path | None = None,
    label: str = "smoke",
    target_root: str | Path | None = None,
    cleanup: bool = True,
) -> RestoreSmokeInfo:
    """Create or use a backup, restore it to scratch space, and verify basics."""
    if backup_path:
        source = Path(backup_path).resolve()
        size_bytes = source.stat().st_size
    else:
        backup = create_backup(label=label, keep=14)
        source = backup.path
        size_bytes = backup.size_bytes

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    target = Path(target_root).resolve() if target_root else config.resolve_path(".tmp/restore-smoke") / stamp
    restored = restore_backup(source, target_root=target, overwrite=False)

    manifest_path = restored / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Restored backup is missing manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("Restored manifest.json could not be parsed") from exc

    included_roots = [str(item) for item in manifest.get("included_roots", [])]
    restored_files = sum(1 for path in restored.rglob("*") if path.is_file())
    if restored_files < 1:
        raise RuntimeError("Restored backup did not contain any files")
    for root_name in included_roots:
        if not (restored / root_name).exists():
            raise RuntimeError(f"Manifest listed missing root: {root_name}")

    cleaned_up = False
    if cleanup:
        shutil.rmtree(restored)
        cleaned_up = True

    return RestoreSmokeInfo(
        backup_path=source,
        target_path=restored,
        size_bytes=size_bytes,
        restored_files=restored_files,
        included_roots=included_roots,
        cleaned_up=cleaned_up,
    )


def _should_skip_backup_file(path: Path) -> bool:
    # Runtime lock files are not durable user data and can be recreated.
    return path.name in EXCLUDED_BACKUP_FILENAMES


def _backup_roots() -> list[tuple[str, Path]]:
    """Return durable local roots using the active runtime configuration."""
    data_root = _configured_data_root()
    roots = [
        ("data", data_root),
        ("vault", config.vault_path()),
        ("reports", config.reports_path()),
    ]

    vector_root = config.qdrant_path()
    if vector_root.exists() and not _is_relative_to(vector_root, data_root):
        roots.append(("vectors", vector_root))

    deduped: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for name, path in roots:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append((name, resolved))
    return deduped


def _configured_data_root() -> Path:
    if config.database_url_sync().startswith("sqlite:///"):
        return Path(config.database_path()).resolve().parent
    return config.resolve_path("./data")


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _write_directory(archive: zipfile.ZipFile, path: Path, written: set[str]) -> None:
    name = path.as_posix().rstrip("/") + "/"
    if name in written:
        return
    archive.writestr(zipfile.ZipInfo(name), b"")
    written.add(name)


def _write_marker(created_at: datetime) -> None:
    marker = backup_dir() / ".last_backup"
    marker.write_text(str(created_at.timestamp()), encoding="utf-8")


def _database_url_kind() -> str:
    if config.DATABASE_URL.startswith("sqlite"):
        return "sqlite"
    if config.DATABASE_URL.startswith("postgresql"):
        return "postgresql"
    return "other"
