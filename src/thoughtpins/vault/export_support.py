"""Filesystem and ownership primitives for vault exports."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from uuid import uuid4

INDEXES = {
    "journal": PurePosixPath("_Indexes/Journal"),
    "entries": PurePosixPath("_Indexes/Entries"),
    "people": PurePosixPath("_Indexes/People"),
    "places": PurePosixPath("_Indexes/Places"),
    "organizations": PurePosixPath("_Indexes/Organizations"),
    "projects": PurePosixPath("_Indexes/Projects"),
    "events": PurePosixPath("_Indexes/Events"),
    "things": PurePosixPath("_Indexes/Things"),
    "concepts": PurePosixPath("_Indexes/Concepts"),
    "library": PurePosixPath("_Indexes/Library"),
}

MANAGED_TOP_LEVEL = {
    "Vault Home.md",
    "Journal",
    "Entries",
    "People",
    "Places",
    "Organizations",
    "Projects",
    "Events",
    "Things",
    "Concepts",
    "Library",
    "Attachments",
    "_Indexes",
    "_Views",
    "_System",
}


@contextmanager
def vault_staging_directory(root: Path) -> Iterator[Path]:
    """Create an isolated projection directory without Windows temp ACL drift."""

    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f"tpv-{uuid4().hex}"
    temporary.mkdir(mode=0o700 if os.name != "nt" else 0o777)
    try:
        yield temporary
    finally:
        shutil.rmtree(temporary, ignore_errors=False)


def package_vault(vault: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(vault.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(vault).as_posix())
    return target


def clean_generated_vault(vault: Path, root: Path, user_id: str | None) -> None:
    """Delete only a tenant projection or known generator-owned top-level paths."""

    if user_id:
        resolved = vault.resolve()
        resolved_root = root.resolve()
        if resolved_root == resolved or resolved_root not in resolved.parents:
            raise RuntimeError(f"Refusing to clean unsafe vault path: {resolved}")
        shutil.rmtree(resolved, ignore_errors=True)
        return

    vault.mkdir(parents=True, exist_ok=True)
    for name in MANAGED_TOP_LEVEL:
        target = vault / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def managed_generated_paths(written: set[PurePosixPath], stats: dict[str, Any]) -> set[str]:
    paths = {path.as_posix() for path in written}
    for key in ("base_files", "canvas_files", "obsidian_default_files"):
        values = stats.get(key, [])
        if isinstance(values, list):
            paths.update(str(value).replace(chr(92), "/") for value in values)
    paths.add("_System/thoughtpins-vault-manifest.json")
    return paths


def write_vault_manifest(vault: Path, user_id: str | None, stats: dict[str, Any]) -> None:
    payload = {
        "app": "Thought Pins",
        "format": "obsidian-compatible-vault",
        "version": 2,
        "schema": "thoughtpins-vault/2",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scope": "account_export" if user_id else "local_export",
        "stats": stats,
    }
    path = vault / "_System" / "thoughtpins-vault-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "INDEXES",
    "clean_generated_vault",
    "managed_generated_paths",
    "package_vault",
    "vault_staging_directory",
    "write_vault_manifest",
]
