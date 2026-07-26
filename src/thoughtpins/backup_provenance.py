"""Checksums and private recovery metadata for local backup archives."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SIDECAR_SUFFIX = ".private-backup.json"
CHECKSUM_SUFFIX = ".sha256"
SIDECAR_FORMAT = "thoughtpins-private-backup-sidecar-v1"


def sidecar_path(archive_path: str | Path) -> Path:
    archive = Path(archive_path)
    return archive.with_name(f"{archive.name}{SIDECAR_SUFFIX}")


def checksum_path(archive_path: str | Path) -> Path:
    archive = Path(archive_path)
    return archive.with_name(f"{archive.name}{CHECKSUM_SUFFIX}")


def sha256_file(path: str | Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def write_backup_provenance(
    archive_path: str | Path,
    *,
    created_at_utc: datetime | None = None,
    contains_local_secrets: bool,
    embedded_secret_file: str | None = None,
    encryption_scheme: str = "none",
    archive_password: str | None = None,
    recovery_key_reference: str | None = None,
) -> dict[str, Any]:
    """Write checksum and recovery metadata beside an already-complete archive.

    The optional password field exists for explicitly private, locally managed
    archives. Keeping a password beside encrypted data offers no theft
    protection, so production backups should use ``recovery_key_reference`` to
    point at a password manager or platform secret instead.
    """
    archive = Path(archive_path).resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Backup archive not found: {archive}")

    created = created_at_utc or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    digest = sha256_file(archive)
    metadata: dict[str, Any] = {
        "format": SIDECAR_FORMAT,
        "created_at_utc": created.astimezone(timezone.utc).isoformat(),
        "archive_name": archive.name,
        "archive_bytes": archive.stat().st_size,
        "sha256": digest,
        "contains_local_secrets": contains_local_secrets,
        "embedded_secret_file": embedded_secret_file,
        "encryption": {
            "scheme": encryption_scheme,
            "archive_password": archive_password,
            "recovery_key_reference": recovery_key_reference,
        },
        "recovery": {
            "verify": f"Compare this SHA-256 with {archive.name}{CHECKSUM_SUFFIX} before restore.",
            "warning": "Keep this sidecar private whenever it names or contains recovery material.",
        },
    }
    checksum_line = f"{digest} *{archive.name}\n"
    _atomic_write_text(checksum_path(archive), checksum_line)
    _atomic_write_text(sidecar_path(archive), json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata


def read_backup_provenance(archive_path: str | Path) -> dict[str, Any] | None:
    path = sidecar_path(archive_path)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != SIDECAR_FORMAT:
        raise ValueError(f"Unsupported backup sidecar: {path}")
    return payload


def verify_backup_provenance(archive_path: str | Path, *, required: bool = False) -> str:
    """Verify adjacent checksum artifacts and return the archive SHA-256."""
    archive = Path(archive_path).resolve()
    sidecar = read_backup_provenance(archive)
    checksum_file = checksum_path(archive)
    if sidecar is None and not checksum_file.is_file():
        if required:
            raise ValueError(f"Backup integrity sidecars are missing for {archive.name}")
        return sha256_file(archive)

    expected_values: list[str] = []
    if sidecar is not None:
        if sidecar.get("archive_name") != archive.name:
            raise ValueError("Backup sidecar archive name does not match the selected archive")
        expected_values.append(str(sidecar.get("sha256", "")).strip().lower())
    if checksum_file.is_file():
        line = checksum_file.read_text(encoding="utf-8").strip()
        expected_values.append(line.split(maxsplit=1)[0].strip().lower())
    if not expected_values or any(len(value) != 64 for value in expected_values):
        raise ValueError("Backup integrity metadata contains an invalid SHA-256 value")
    if len(set(expected_values)) != 1:
        raise ValueError("Backup sidecar and checksum file disagree")

    actual = sha256_file(archive)
    if actual != expected_values[0]:
        raise ValueError("Backup archive failed SHA-256 verification")
    return actual


def remove_backup_provenance(archive_path: str | Path) -> None:
    sidecar_path(archive_path).unlink(missing_ok=True)
    checksum_path(archive_path).unlink(missing_ok=True)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
