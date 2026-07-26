"""Native Obsidian Bases views for a portable Thought Pins vault."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

BASE_DIRECTORY = PurePosixPath("_Views")
GENERATED_BASES = (
    BASE_DIRECTORY / "Journal.base",
    BASE_DIRECTORY / "Daily Notes.base",
    BASE_DIRECTORY / "Memory Cards.base",
    BASE_DIRECTORY / "Library.base",
)
ALLOWED_VIEW_TYPES = {"table", "cards", "list"}
_FORMULA_REFERENCE = re.compile(r"\bformula\.([A-Za-z_][A-Za-z0-9_-]*)\b")


def write_vault_bases(vault: str | Path) -> list[str]:
    """Write plugin-free Bases views and return their vault-relative paths."""
    root = Path(vault)
    payloads = _base_payloads()
    written: list[str] = []
    for rel_path in GENERATED_BASES:
        payload = payloads[rel_path.name]
        errors = validate_base_payload(payload)
        if errors:
            raise ValueError(f"invalid generated Base {rel_path}: {'; '.join(errors)}")
        target = root / Path(rel_path.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8",
        )
        written.append(rel_path.as_posix())
    return written


def load_base(path: str | Path) -> dict[str, Any]:
    """Load a Base as bounded, safe YAML for validation."""
    source = Path(path)
    if source.stat().st_size > 256 * 1024:
        raise ValueError("Base file exceeds 256 KiB")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("Base file is not valid UTF-8 YAML") from exc
    if not isinstance(payload, dict):
        raise ValueError("Base root must be a mapping")
    return payload


def validate_base_payload(payload: Mapping[str, Any]) -> list[str]:
    """Validate the stable subset of the Obsidian Bases schema we generate."""
    errors = _validate_yaml_structure(payload)
    formulas = payload.get("formulas", {})
    if not isinstance(formulas, Mapping):
        errors.append("formulas must be a mapping")
        formulas = {}
    formula_names = {str(name) for name in formulas}

    properties = payload.get("properties", {})
    if not isinstance(properties, Mapping):
        errors.append("properties must be a mapping")

    views = payload.get("views")
    if not isinstance(views, list) or not views:
        errors.append("views must be a non-empty list")
        views = []
    for index, view in enumerate(views):
        if not isinstance(view, Mapping):
            errors.append(f"view {index} must be a mapping")
            continue
        view_type = str(view.get("type") or "")
        if view_type not in ALLOWED_VIEW_TYPES:
            errors.append(f"view {index} has unsupported type {view_type!r}")
        if not str(view.get("name") or "").strip():
            errors.append(f"view {index} is missing a name")
        limit = view.get("limit")
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000):
            errors.append(f"view {index} limit must be an integer from 1 to 1000")
        order = view.get("order")
        if order is not None and not isinstance(order, list):
            errors.append(f"view {index} order must be a list")

    for reference in sorted(_formula_references(payload)):
        if reference not in formula_names:
            errors.append(f"formula.{reference} is referenced but not defined")
    return errors


def _formula_references(
    value: object,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> set[str]:
    if depth > 16:
        return set()
    if seen is None:
        seen = set()
    references: set[str] = set()
    if isinstance(value, str):
        references.update(_FORMULA_REFERENCE.findall(value))
    elif isinstance(value, Mapping):
        object_id = id(value)
        if object_id in seen:
            return references
        seen.add(object_id)
        try:
            for key, item in value.items():
                references.update(_formula_references(str(key), depth=depth + 1, seen=seen))
                references.update(_formula_references(item, depth=depth + 1, seen=seen))
        finally:
            seen.remove(object_id)
    elif isinstance(value, list | tuple):
        object_id = id(value)
        if object_id in seen:
            return references
        seen.add(object_id)
        try:
            for item in value:
                references.update(_formula_references(item, depth=depth + 1, seen=seen))
        finally:
            seen.remove(object_id)
    return references


def _validate_yaml_structure(value: object) -> list[str]:
    errors: list[str] = []
    nodes = [0]

    def visit(item: object, *, depth: int, seen: set[int]) -> None:
        nodes[0] += 1
        if nodes[0] > 20_000:
            if "Base structure exceeds 20,000 values" not in errors:
                errors.append("Base structure exceeds 20,000 values")
            return
        if depth > 16:
            if "Base structure exceeds nesting depth 16" not in errors:
                errors.append("Base structure exceeds nesting depth 16")
            return
        if isinstance(item, Mapping):
            object_id = id(item)
            if object_id in seen:
                errors.append("Base structure contains a recursive YAML alias")
                return
            if len(item) > 1_000:
                errors.append("Base mapping exceeds 1,000 properties")
                return
            seen.add(object_id)
            try:
                for key, child in item.items():
                    if len(str(key)) > 256:
                        errors.append("Base property name exceeds 256 characters")
                    visit(child, depth=depth + 1, seen=seen)
            finally:
                seen.remove(object_id)
        elif isinstance(item, list | tuple):
            object_id = id(item)
            if object_id in seen:
                errors.append("Base structure contains a recursive YAML alias")
                return
            if len(item) > 2_000:
                errors.append("Base list exceeds 2,000 values")
                return
            seen.add(object_id)
            try:
                for child in item:
                    visit(child, depth=depth + 1, seen=seen)
            finally:
                seen.remove(object_id)
        elif isinstance(item, str) and len(item) > 20_000:
            errors.append("Base scalar exceeds 20,000 characters")

    visit(value, depth=0, seen=set())
    return list(dict.fromkeys(errors))


def _base_payloads() -> dict[str, dict[str, Any]]:
    return {
        "Journal.base": {
            "filters": {
                "and": [
                    'file.inFolder("Entries")',
                    'type == "entry"',
                ],
            },
            "formulas": {
                "importance_label": 'if(importance, importance.toString() + "/5", "Unrated")',
            },
            "properties": {
                "created": {"displayName": "Created"},
                "formula.importance_label": {"displayName": "Importance"},
                "source": {"displayName": "Source"},
            },
            "views": [
                {
                    "type": "table",
                    "name": "Recent entries",
                    "limit": 200,
                    "order": ["file.name", "created", "formula.importance_label", "source"],
                },
                {
                    "type": "cards",
                    "name": "Important entries",
                    "filters": {"and": ["importance >= 4"]},
                    "limit": 100,
                    "order": ["file.name", "created", "formula.importance_label"],
                },
            ],
        },
        "Daily Notes.base": {
            "filters": {
                "and": [
                    'file.inFolder("Journal")',
                    'type == "daily_journal"',
                ],
            },
            "properties": {
                "date": {"displayName": "Date"},
                "entry_count": {"displayName": "Entries"},
                "updated": {"displayName": "Updated"},
            },
            "views": [
                {
                    "type": "table",
                    "name": "Daily notes",
                    "limit": 366,
                    "order": ["file.name", "date", "entry_count", "updated"],
                },
            ],
        },
        "Memory Cards.base": {
            "filters": {
                "and": [
                    'file.hasTag("entity")',
                ],
            },
            "formulas": {
                "activity": "if(memory_count, memory_count, 0) + if(relationship_count, relationship_count, 0)",
            },
            "properties": {
                "type": {"displayName": "Kind"},
                "memory_count": {"displayName": "Memories"},
                "relationship_count": {"displayName": "Connections"},
                "formula.activity": {"displayName": "Activity"},
                "last_seen": {"displayName": "Last seen"},
                "confidence": {"displayName": "Confidence"},
            },
            "views": [
                {
                    "type": "cards",
                    "name": "Memory cards",
                    "limit": 250,
                    "order": ["file.name", "type", "formula.activity", "last_seen"],
                },
                {
                    "type": "table",
                    "name": "Memory index",
                    "limit": 500,
                    "order": [
                        "file.name",
                        "type",
                        "memory_count",
                        "relationship_count",
                        "last_seen",
                        "confidence",
                    ],
                },
            ],
        },
        "Library.base": {
            "filters": {
                "and": [
                    'file.inFolder("Library")',
                    "type != null",
                ],
            },
            "properties": {
                "author": {"displayName": "Author"},
                "publisher": {"displayName": "Publisher"},
                "published": {"displayName": "Published"},
                "status": {"displayName": "Status"},
                "topics": {"displayName": "Topics"},
            },
            "views": [
                {
                    "type": "table",
                    "name": "Sources",
                    "limit": 500,
                    "order": ["file.name", "author", "publisher", "published", "status", "topics"],
                },
                {
                    "type": "cards",
                    "name": "Reading shelf",
                    "limit": 250,
                    "order": ["file.name", "publisher", "topics"],
                },
            ],
        },
    }


__all__ = [
    "GENERATED_BASES",
    "load_base",
    "validate_base_payload",
    "write_vault_bases",
]
