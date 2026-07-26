"""Bounded ZIP parsing for user-provided Obsidian vaults."""

from __future__ import annotations

import io
import json
import re
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from thoughtpins.vault.canvas import MEMORY_CANVAS_PATH, canvas_to_markdown, load_canvas_bytes
from thoughtpins.vault.frontmatter import parse_obsidian_frontmatter

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_MEMBERS = 100_100
MAX_PATH_DEPTH = 24
MAX_COMPRESSION_RATIO = 200

_THOUGHTPINS_MANIFEST = "thoughtpins-vault-manifest.json"
_JOURNAL_PATH_PARTS = {"entries", "journal", "journals", "diary", "daily", "daily notes", "daily-notes"}
_IGNORED_PATH_PARTS = {".git", ".obsidian", ".trash", "__macosx", "_system", "_indexes"}


@dataclass(frozen=True)
class VaultNote:
    path: str
    title: str
    metadata: dict[str, Any]
    body: str


@dataclass(frozen=True)
class VaultArchive:
    notes: list[VaultNote]
    thoughtpins_export: bool
    files_discovered: int
    attachments_skipped: int
    structural_files_skipped: int
    canvases_discovered: int


def read_vault_archive(archive: bytes, warning_sink: Callable[[str], None]) -> VaultArchive:
    """Read a ZIP into normalized notes while enforcing archive safety limits."""

    try:
        package = zipfile.ZipFile(io.BytesIO(archive))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("Vault upload is not a valid ZIP archive") from exc

    with package:
        members = package.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError(f"Vault archive contains more than {MAX_MEMBERS} files")

        safe_members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        expanded_bytes = 0
        for member in members:
            path = _safe_member_path(member)
            if member.is_dir():
                continue
            expanded_bytes += member.file_size
            if expanded_bytes > MAX_EXPANDED_BYTES:
                raise ValueError("Vault archive expands beyond the safe size limit")
            safe_members.append((member, path))

        root = _common_archive_root([path for _, path in safe_members])
        thoughtpins_export = _is_thoughtpins_export(package, safe_members)
        notes: list[VaultNote] = []
        attachments_skipped = 0
        structural_files_skipped = 0
        canvases_discovered = 0
        for member, raw_path in safe_members:
            path = _without_root(raw_path, root)
            if _ignored_path(path):
                continue
            suffix = path.suffix.casefold()
            if suffix == ".base":
                structural_files_skipped += 1
                continue
            if suffix == ".canvas":
                canvases_discovered += 1
                if thoughtpins_export and path.as_posix().casefold() == MEMORY_CANVAS_PATH.as_posix().casefold():
                    structural_files_skipped += 1
                    continue
                try:
                    canvas = load_canvas_bytes(_read_member(package, member))
                    title, body = canvas_to_markdown(path, canvas)
                except ValueError as exc:
                    warning_sink(f"Skipped invalid Canvas {path.as_posix()}: {exc}")
                    continue
                notes.append(
                    VaultNote(
                        path=path.as_posix(),
                        title=title,
                        metadata={
                            "type": "canvas",
                            "source": "obsidian_canvas",
                            "tags": ["obsidian", "canvas"],
                        },
                        body=body,
                    ),
                )
                continue
            if suffix != ".md":
                attachments_skipped += 1
                continue
            try:
                payload = _read_member(package, member)
                markdown = payload.decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError:
                warning_sink(f"Skipped non-UTF-8 note: {path.as_posix()}")
                continue
            try:
                metadata, body = parse_obsidian_frontmatter(markdown)
            except ValueError as exc:
                warning_sink(f"Ignored invalid properties in {path.as_posix()}: {exc}")
                metadata, body = {}, markdown
            notes.append(
                VaultNote(
                    path=path.as_posix(),
                    title=_note_title(path, metadata, body),
                    metadata=metadata,
                    body=body.strip(),
                )
            )

        return VaultArchive(
            notes=notes,
            thoughtpins_export=thoughtpins_export,
            files_discovered=len(safe_members),
            attachments_skipped=attachments_skipped,
            structural_files_skipped=structural_files_skipped,
            canvases_discovered=canvases_discovered,
        )


def _safe_member_path(member: zipfile.ZipInfo) -> PurePosixPath:
    name = member.filename
    if not name or "\x00" in name:
        raise ValueError("Vault archive contains an invalid path")
    if len(name) > 2_048:
        raise ValueError("Vault archive contains an overlong path")
    if member.flag_bits & 0x1:
        raise ValueError("Encrypted ZIP members are not supported")
    unix_mode = (member.external_attr >> 16) & 0xFFFF
    if unix_mode and stat.S_ISLNK(unix_mode):
        raise ValueError("Vault archive may not contain symbolic links")

    path = PurePosixPath(name.replace(chr(92), "/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Vault archive contains an unsafe path")
    if path.parts and re.fullmatch(r"[A-Za-z]:", path.parts[0]):
        raise ValueError("Vault archive contains an absolute Windows path")
    if len(path.parts) > MAX_PATH_DEPTH:
        raise ValueError("Vault archive path nesting is too deep")
    if any(len(part) > 255 for part in path.parts):
        raise ValueError("Vault archive path component exceeds 255 characters")
    if member.file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"Vault member exceeds the {MAX_MEMBER_BYTES // (1024 * 1024)} MB per-file limit")
    if member.file_size and member.compress_size == 0:
        raise ValueError("Vault archive contains an invalid compression record")
    if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
        raise ValueError("Vault archive contains an unsafe compression ratio")
    return path


def _read_member(package: zipfile.ZipFile, member: zipfile.ZipInfo) -> bytes:
    with package.open(member, "r") as handle:
        payload = handle.read(MAX_MEMBER_BYTES + 1)
    if len(payload) > MAX_MEMBER_BYTES:
        raise ValueError("Vault member exceeded the safe size limit while reading")
    return payload


def _common_archive_root(paths: list[PurePosixPath]) -> str | None:
    if not paths or any(len(path.parts) < 2 for path in paths):
        return None
    roots = {path.parts[0] for path in paths}
    if len(roots) != 1:
        return None
    candidate = next(iter(roots))
    if candidate.casefold() in _JOURNAL_PATH_PARTS | _IGNORED_PATH_PARTS | {"library"}:
        return None
    has_vault_marker = any(
        len(path.parts) > 1 and path.parts[1].casefold() in {".obsidian", "_system"} for path in paths
    )
    return candidate if has_vault_marker else None


def _is_thoughtpins_export(
    package: zipfile.ZipFile,
    members: list[tuple[zipfile.ZipInfo, PurePosixPath]],
) -> bool:
    for member, path in members:
        if path.name.casefold() != _THOUGHTPINS_MANIFEST:
            continue
        try:
            payload = json.loads(_read_member(package, member).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return False
        return payload.get("app") == "Thought Pins" and payload.get("format") == "obsidian-compatible-vault"
    return False


def _without_root(path: PurePosixPath, root: str | None) -> PurePosixPath:
    if root and path.parts and path.parts[0] == root:
        return PurePosixPath(*path.parts[1:])
    return path


def _ignored_path(path: PurePosixPath) -> bool:
    parts = {part.casefold() for part in path.parts}
    return bool(parts & _IGNORED_PATH_PARTS) or path.name.casefold() in {".ds_store", "thumbs.db"}


def _note_title(path: PurePosixPath, metadata: dict[str, Any], body: str) -> str:
    title = str(metadata.get("title") or "").strip()
    if not title:
        heading = re.search(r"(?m)^#\s+(.+?)\s*$", body)
        title = heading.group(1).strip() if heading else path.stem
    return title[:512] or "Untitled"


__all__ = ["MAX_ARCHIVE_BYTES", "MAX_MEMBERS", "VaultArchive", "VaultNote", "read_vault_archive"]
