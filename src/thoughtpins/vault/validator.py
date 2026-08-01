"""Validation for generated Obsidian-compatible Thought Pins vaults."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thoughtpins.vault.bases import GENERATED_BASES, load_base, validate_base_payload
from thoughtpins.vault.canvas import MEMORY_CANVAS_PATH, load_canvas_bytes, validate_canvas_payload
from thoughtpins.vault.frontmatter import parse_obsidian_frontmatter
from thoughtpins.vault.incremental import load_export_state
from thoughtpins.vault.markdown import strip_fenced_blocks

REQUIRED_FIELDS = (
    "id",
    "type",
    "title",
    "created",
    "updated",
    "source",
    "tags",
    "aliases",
    "thoughtpins_id",
    "related",
)
REQUIRED_INDEXES = (
    "Vault Home.md",
    "_Indexes/Journal.md",
    "_Indexes/Entries.md",
    "_Indexes/People.md",
    "_Indexes/Places.md",
    "_Indexes/Organizations.md",
    "_Indexes/Projects.md",
    "_Indexes/Events.md",
    "_Indexes/Things.md",
    "_Indexes/Concepts.md",
    "_Indexes/Library.md",
    "_System/thoughtpins-vault-manifest.json",
)
REQUIRED_V2_VIEWS = tuple(path.as_posix() for path in (*GENERATED_BASES, MEMORY_CANVAS_PATH))
# Event notes come from two shapes: Event rows and entities typed "event". Only
# the entity shape carries quotes, so "## Quotes" is required of the entity note
# types and left optional for "event".
_ENTITY_SECTIONS = (
    "## Card",
    "## Known Attributes",
    "## Quotes",
    "## Recent Memories",
    "## Relationships",
    "## Source Entries",
)
TYPE_REQUIRED_SECTIONS = {
    "home": ("## Start Here", "## Current Counts", "## Open In Obsidian", "## System Boundary"),
    "index": (),
    "daily_journal": ("## Entries", "## Mentioned"),
    "entry": ("## Context", "## Mentioned", "## Memories", "## Original Text"),
    "person": _ENTITY_SECTIONS,
    "place": _ENTITY_SECTIONS,
    "organization": _ENTITY_SECTIONS,
    "project": _ENTITY_SECTIONS,
    "event": ("## Card", "## Known Attributes", "## Recent Memories", "## Relationships", "## Source Entries"),
    "thing": _ENTITY_SECTIONS,
    "concept": _ENTITY_SECTIONS,
    "article": (
        "## Reading Card",
        "## Source",
        "## Topics",
        "## Concepts",
        "## Related Thought Pins",
        "## Summary",
        "## Text Policy",
    ),
    "document": (
        "## Reading Card",
        "## Source",
        "## Topics",
        "## Concepts",
        "## Related Thought Pins",
        "## Summary",
        "## Text Policy",
    ),
}
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
ILLEGAL_COMPONENT_CHARS = re.compile(r'[<>:"\\|?*\x00-\x1f]')
WIKILINK_RE = re.compile(r"!?(?<!`)\[\[([^\]\n]+)\]\]")
SECRET_PATTERNS = (
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{24,}"),
    re.compile(r"\b\d{8,}:[A-Za-z0-9_\-]{24,}\b"),
    re.compile(r"(?i)(api_key|auth_token|bot_token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{24,}"),
)
EXCLUDED_REFERENCES = tuple(
    "".join(parts)
    for parts in (
        ("telegram", "-journal", "-companion"),
        ("telegram", "_journal", "_companion"),
        ("founder", "_memory", "_backup", "_2026-05-20_2226", ".zip"),
    )
)


@dataclass(frozen=True)
class VaultValidationFinding:
    severity: str
    path: str
    message: str


@dataclass
class VaultValidationResult:
    root: str
    checked_files: int = 0
    findings: list[VaultValidationFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    @property
    def errors(self) -> list[VaultValidationFinding]:
        return [finding for finding in self.findings if finding.severity == "error"]

    @property
    def warnings(self) -> list[VaultValidationFinding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "ok": self.ok,
            "checked_files": self.checked_files,
            "errors": [finding.__dict__ for finding in self.errors],
            "warnings": [finding.__dict__ for finding in self.warnings],
        }


def validate_vault(root: str | Path) -> VaultValidationResult:
    root_path = Path(root).resolve()
    result = VaultValidationResult(root=str(root_path))
    seen_note_keys: dict[str, str] = {}
    if not root_path.exists() or not root_path.is_dir():
        result.findings.append(VaultValidationFinding("error", str(root_path), "vault root does not exist"))
        return result

    markdown_files = sorted(root_path.rglob("*.md"))
    if not markdown_files:
        result.findings.append(VaultValidationFinding("error", ".", "vault contains no Markdown notes"))
        return result

    manifest_version = _validate_required_layout(root_path, result)
    _validate_obsidian_config(root_path, result)
    managed_paths = set(load_export_state(root_path))

    note_keys = {_note_key(path.relative_to(root_path)) for path in markdown_files}
    all_files = sorted(path for path in root_path.rglob("*") if path.is_file())
    file_keys = {path.relative_to(root_path).as_posix().casefold() for path in all_files}
    link_keys = note_keys | file_keys
    seen_paths: dict[str, str] = {}
    for path in all_files:
        rel = path.relative_to(root_path).as_posix()
        _validate_path(rel, result)
        key = rel.casefold()
        if key in seen_paths:
            result.findings.append(
                VaultValidationFinding("error", rel, f"duplicate file path collides with {seen_paths[key]}"),
            )
        seen_paths[key] = rel

    for path in sorted(root_path.rglob("*.base")):
        _validate_base(path, root_path, result)
    for path in sorted(root_path.rglob("*.canvas")):
        _validate_canvas(path, root_path, file_keys, result)

    for path in markdown_files:
        rel = path.relative_to(root_path).as_posix()
        result.checked_files += 1
        key = rel.lower()
        if key in seen_note_keys:
            result.findings.append(
                VaultValidationFinding("error", rel, f"duplicate note path collides with {seen_note_keys[key]}")
            )
        seen_note_keys[key] = rel

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            result.findings.append(VaultValidationFinding("error", rel, "note is not valid UTF-8"))
            continue
        if not text.strip():
            result.findings.append(VaultValidationFinding("error", rel, "note is empty"))
            continue
        _validate_secrets(rel, text, result)
        try:
            metadata, body = parse_obsidian_frontmatter(text)
        except Exception as exc:
            if rel in managed_paths or rel in REQUIRED_INDEXES:
                result.findings.append(VaultValidationFinding("error", rel, f"frontmatter parse failed: {exc}"))
            else:
                _validate_wikilinks(rel, text, link_keys, result)
            continue
        generated = rel in managed_paths or _is_generated_note(metadata)
        if generated:
            _validate_required_fields(rel, metadata, result, require_schema=manifest_version >= 2)
            _validate_type_contract(rel, metadata, body, result)
        _validate_metadata_links(rel, metadata, link_keys, result)
        if not body.strip():
            result.findings.append(VaultValidationFinding("error", rel, "note body is empty"))
        _validate_wikilinks(rel, body, link_keys, result)
        if generated:
            _validate_backlinks(rel, metadata, body, result)
    return result


def _is_generated_note(metadata: dict[str, Any]) -> bool:
    if metadata.get("thoughtpins_schema") == 2:
        return True
    source = str(metadata.get("source") or "").casefold()
    tags = metadata.get("tags")
    return source.startswith("thoughtpins_") or (
        isinstance(tags, list) and any(str(tag).casefold() == "thoughtpins" for tag in tags)
    )


def _validate_required_layout(root: Path, result: VaultValidationResult) -> int:
    for rel in REQUIRED_INDEXES:
        if not (root / rel).exists():
            result.findings.append(VaultValidationFinding("error", rel, "required vault layout file is missing"))
    manifest = root / "_System" / "thoughtpins-vault-manifest.json"
    if not manifest.exists():
        return 0
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        result.findings.append(
            VaultValidationFinding(
                "error", "_System/thoughtpins-vault-manifest.json", f"manifest JSON is invalid: {exc}"
            )
        )
        return 0
    if payload.get("app") != "Thought Pins":
        result.findings.append(
            VaultValidationFinding(
                "error", "_System/thoughtpins-vault-manifest.json", "manifest app is not Thought Pins"
            )
        )
    if payload.get("format") != "obsidian-compatible-vault":
        result.findings.append(
            VaultValidationFinding(
                "error", "_System/thoughtpins-vault-manifest.json", "manifest format is not obsidian-compatible-vault"
            )
        )
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        result.findings.append(
            VaultValidationFinding("error", "_System/thoughtpins-vault-manifest.json", "manifest version is invalid")
        )
        return 0
    if version >= 2:
        if payload.get("schema") != "thoughtpins-vault/2":
            result.findings.append(
                VaultValidationFinding(
                    "error", "_System/thoughtpins-vault-manifest.json", "manifest schema is not thoughtpins-vault/2"
                ),
            )
        for rel in REQUIRED_V2_VIEWS:
            if not (root / rel).exists():
                result.findings.append(VaultValidationFinding("error", rel, "required version 2 view is missing"))
        stats = payload.get("stats")
        if isinstance(stats, dict):
            if stats.get("bases") != len(GENERATED_BASES):
                result.findings.append(
                    VaultValidationFinding(
                        "error", "_System/thoughtpins-vault-manifest.json", "manifest Base count is inconsistent"
                    ),
                )
            if stats.get("canvases") != 1:
                result.findings.append(
                    VaultValidationFinding(
                        "error", "_System/thoughtpins-vault-manifest.json", "manifest Canvas count is inconsistent"
                    ),
                )
    return version


def _validate_base(path: Path, root: Path, result: VaultValidationResult) -> None:
    rel = path.relative_to(root).as_posix()
    result.checked_files += 1
    try:
        text = path.read_text(encoding="utf-8")
        _validate_secrets(rel, text, result)
        payload = load_base(path)
    except ValueError as exc:
        result.findings.append(VaultValidationFinding("error", rel, str(exc)))
        return
    for message in validate_base_payload(payload):
        result.findings.append(VaultValidationFinding("error", rel, message))


def _validate_canvas(path: Path, root: Path, file_keys: set[str], result: VaultValidationResult) -> None:
    rel = path.relative_to(root).as_posix()
    result.checked_files += 1
    try:
        payload_bytes = path.read_bytes()
        _validate_secrets(rel, payload_bytes.decode("utf-8"), result)
        payload = load_canvas_bytes(payload_bytes)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        result.findings.append(VaultValidationFinding("error", rel, str(exc)))
        return
    strict = rel.casefold() == MEMORY_CANVAS_PATH.as_posix().casefold()
    for message in validate_canvas_payload(payload, existing_files=file_keys, strict_generated=strict):
        result.findings.append(VaultValidationFinding("error", rel, message))


def _validate_obsidian_config(root: Path, result: VaultValidationResult) -> None:
    config_dir = root / ".obsidian"
    if not config_dir.exists():
        return
    if not config_dir.is_dir():
        result.findings.append(VaultValidationFinding("error", ".obsidian", ".obsidian exists but is not a directory"))
        return
    for path in sorted(config_dir.rglob("*")):
        rel = path.relative_to(root).as_posix()
        _validate_path(rel, result)
        if path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            result.findings.append(VaultValidationFinding("error", rel, ".obsidian file is not valid UTF-8"))
            continue
        _validate_secrets(rel, text, result)
        if path.suffix.lower() == ".json":
            try:
                json.loads(text or "{}")
            except Exception as exc:
                result.findings.append(VaultValidationFinding("error", rel, f".obsidian JSON is invalid: {exc}"))
        if path.name in {"community-plugins.json", "plugins.json"}:
            result.findings.append(
                VaultValidationFinding(
                    "warning",
                    rel,
                    "vault-local community plugin state is present; generated vaults should not require plugins",
                )
            )


def _validate_path(rel: str, result: VaultValidationResult) -> None:
    parts = rel.split("/")
    if len(rel) > 240:
        result.findings.append(
            VaultValidationFinding("error", rel, "relative path is too long for conservative cross-platform sync")
        )
    for part in parts:
        if not part or part in {".", ".."}:
            result.findings.append(VaultValidationFinding("error", rel, "unsafe empty or traversal path component"))
        if part.endswith(" ") or part.endswith("."):
            result.findings.append(VaultValidationFinding("error", rel, "path component ends with space or period"))
        if ILLEGAL_COMPONENT_CHARS.search(part):
            result.findings.append(
                VaultValidationFinding("error", rel, "path contains illegal Windows filename characters")
            )
        stem = part.rsplit(".", 1)[0].upper()
        if stem in RESERVED_WINDOWS_NAMES:
            result.findings.append(
                VaultValidationFinding("error", rel, f"path component uses reserved Windows name {stem}")
            )
    lowered = rel.lower()
    for forbidden in EXCLUDED_REFERENCES:
        if forbidden.lower() in lowered:
            result.findings.append(VaultValidationFinding("error", rel, f"references excluded path {forbidden}"))


def _validate_required_fields(
    rel: str,
    metadata: dict[str, Any],
    result: VaultValidationResult,
    *,
    require_schema: bool,
) -> None:
    if require_schema and metadata.get("thoughtpins_schema") != 2:
        result.findings.append(VaultValidationFinding("error", rel, "missing or invalid thoughtpins_schema 2"))
    for field_name in REQUIRED_FIELDS:
        if field_name not in metadata:
            result.findings.append(VaultValidationFinding("error", rel, f"missing frontmatter field {field_name}"))
        else:
            value = metadata.get(field_name)
            if value in ("", None) and field_name not in {"aliases", "related"}:
                result.findings.append(VaultValidationFinding("error", rel, f"frontmatter field {field_name} is empty"))
    if "tags" in metadata and not isinstance(metadata["tags"], list):
        result.findings.append(VaultValidationFinding("error", rel, "tags must be a list"))
    elif isinstance(metadata.get("tags"), list):
        for tag in metadata["tags"]:
            if not str(tag).strip() or any(ch.isspace() for ch in str(tag)):
                result.findings.append(VaultValidationFinding("error", rel, f"tag is not Obsidian-safe: {tag!r}"))
    if "aliases" in metadata and not isinstance(metadata["aliases"], list):
        result.findings.append(VaultValidationFinding("error", rel, "aliases must be a list"))
    if "related" in metadata and not isinstance(metadata["related"], list):
        result.findings.append(VaultValidationFinding("error", rel, "related must be a list"))


def _validate_type_contract(rel: str, metadata: dict[str, Any], body: str, result: VaultValidationResult) -> None:
    note_type = str(metadata.get("type") or "")
    expected_sections = TYPE_REQUIRED_SECTIONS.get(note_type)
    if expected_sections is None:
        result.findings.append(VaultValidationFinding("error", rel, f"unknown generated note type {note_type!r}"))
        return
    for section in expected_sections:
        if section not in body:
            result.findings.append(VaultValidationFinding("error", rel, f"missing generated section {section}"))
    if note_type in {"article", "document"}:
        if "- Rights basis:" not in body:
            result.findings.append(VaultValidationFinding("error", rel, "library note is missing rights basis"))
        if "- Fetch status:" not in body:
            result.findings.append(VaultValidationFinding("error", rel, "library note is missing fetch status"))
        if "## Extracted Text" in body and "```text" not in body:
            result.findings.append(VaultValidationFinding("error", rel, "library extracted text is not fenced as text"))
    if note_type == "entry" and "## Original Text" in body and "```text" not in body:
        result.findings.append(VaultValidationFinding("error", rel, "entry original text is not fenced as text"))


def _validate_metadata_links(
    rel: str, metadata: dict[str, Any], link_keys: set[str], result: VaultValidationResult
) -> None:
    related = metadata.get("related")
    if not isinstance(related, list):
        return
    for item in related:
        text = str(item)
        for match in WIKILINK_RE.finditer(text):
            raw_target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
            normalized = _link_key(raw_target)
            if normalized and not _link_exists(normalized, link_keys):
                result.findings.append(
                    VaultValidationFinding("error", rel, f"broken frontmatter wikilink target [[{raw_target}]]")
                )


def _validate_wikilinks(rel: str, body: str, link_keys: set[str], result: VaultValidationResult) -> None:
    searchable = strip_fenced_blocks(body)
    for match in WIKILINK_RE.finditer(searchable):
        raw_target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if not raw_target:
            result.findings.append(VaultValidationFinding("error", rel, "empty wikilink target"))
            continue
        if raw_target.startswith(("http://", "https://", "mailto:")):
            continue
        normalized = _link_key(raw_target)
        if not _link_exists(normalized, link_keys):
            result.findings.append(VaultValidationFinding("error", rel, f"broken wikilink target [[{raw_target}]]"))


def _validate_backlinks(rel: str, metadata: dict[str, Any], body: str, result: VaultValidationResult) -> None:
    note_type = str(metadata.get("type") or "")
    if note_type != "entry" or not rel.startswith("Entries/"):
        return
    parts = rel.split("/")
    if len(parts) < 5:
        result.findings.append(VaultValidationFinding("error", rel, "entry note is outside Entries/YYYY/MM/DD layout"))
        return
    daily_target = f"Journal/{parts[1]}/{parts[2]}/{parts[1]}-{parts[2]}-{parts[3]}"
    if f"[[{daily_target}]]" not in body and f"[[{daily_target}|" not in body:
        result.findings.append(
            VaultValidationFinding("error", rel, f"entry note does not link its daily note [[{daily_target}]]")
        )


def _validate_secrets(rel: str, text: str, result: VaultValidationResult) -> None:
    lowered = text.lower()
    for forbidden in EXCLUDED_REFERENCES:
        if forbidden.lower() in lowered:
            result.findings.append(VaultValidationFinding("error", rel, f"references excluded path {forbidden}"))
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            result.findings.append(VaultValidationFinding("error", rel, "possible secret leaked into vault"))


def _note_key(path: Path) -> str:
    return path.with_suffix("").as_posix().lower()


def _link_key(raw_target: str) -> str:
    return raw_target.replace("\\", "/").removeprefix("/").casefold()


def _link_exists(normalized: str, link_keys: set[str]) -> bool:
    if normalized in link_keys:
        return True
    return normalized.endswith(".md") and normalized.removesuffix(".md") in link_keys
