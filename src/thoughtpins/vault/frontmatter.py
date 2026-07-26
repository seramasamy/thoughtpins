"""Bounded parsing for user-authored Obsidian YAML properties."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import yaml

MAX_FRONTMATTER_BYTES = 64 * 1024
MAX_PROPERTY_DEPTH = 8
MAX_PROPERTY_KEYS = 128
MAX_COLLECTION_ITEMS = 512
MAX_PROPERTY_NODES = 10_000
MAX_SCALAR_CHARS = 10_000
WIKILINK_RE = re.compile(r"\[\[([^\]\n]{1,500})\]\]")


def parse_obsidian_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Parse Obsidian properties with safe YAML and deterministic JSON values."""
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4, MAX_FRONTMATTER_BYTES + 5)
    if end < 0:
        raise ValueError("YAML frontmatter is unterminated or exceeds 64 KiB")

    raw = normalized[4:end]
    if len(raw.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        raise ValueError("YAML frontmatter exceeds 64 KiB")
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError("YAML frontmatter is invalid") from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError("YAML frontmatter root must be a mapping")
    if len(loaded) > MAX_PROPERTY_KEYS:
        raise ValueError(f"YAML frontmatter exceeds {MAX_PROPERTY_KEYS} top-level properties")

    counter = [0]
    metadata = _normalize_value(loaded, depth=0, counter=counter, seen=set())
    if not isinstance(metadata, dict):
        raise ValueError("YAML frontmatter root must be a mapping")
    return metadata, normalized[end + 5 :]


def extract_wikilinks(*values: object) -> list[str]:
    """Collect wikilinks from note text and nested property values."""
    found: set[str] = set()

    def visit(value: object, depth: int = 0) -> None:
        if depth > MAX_PROPERTY_DEPTH:
            return
        if isinstance(value, str):
            found.update(match.group(1).strip() for match in WIKILINK_RE.finditer(value))
        elif isinstance(value, dict):
            for key, item in list(value.items())[:MAX_COLLECTION_ITEMS]:
                visit(key, depth + 1)
                visit(item, depth + 1)
        elif isinstance(value, (list, tuple, set)):
            for item in list(value)[:MAX_COLLECTION_ITEMS]:
                visit(item, depth + 1)

    for value in values:
        visit(value)
    return sorted(item for item in found if item)


def _normalize_value(
    value: object,
    *,
    depth: int,
    counter: list[int],
    seen: set[int],
) -> Any:
    counter[0] += 1
    if counter[0] > MAX_PROPERTY_NODES:
        raise ValueError("YAML frontmatter is too complex")
    if depth > MAX_PROPERTY_DEPTH:
        raise ValueError(f"YAML frontmatter exceeds nesting depth {MAX_PROPERTY_DEPTH}")

    if isinstance(value, dict):
        object_id = id(value)
        if object_id in seen:
            raise ValueError("YAML frontmatter contains a recursive alias")
        if len(value) > MAX_PROPERTY_KEYS:
            raise ValueError(f"YAML mapping exceeds {MAX_PROPERTY_KEYS} properties")
        seen.add(object_id)
        try:
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key).strip()
                if not key_text or len(key_text) > 128:
                    raise ValueError("YAML property name is empty or too long")
                normalized[key_text] = _normalize_value(item, depth=depth + 1, counter=counter, seen=seen)
            return normalized
        finally:
            seen.remove(object_id)

    if isinstance(value, (list, tuple, set)):
        object_id = id(value)
        if object_id in seen:
            raise ValueError("YAML frontmatter contains a recursive alias")
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError(f"YAML list exceeds {MAX_COLLECTION_ITEMS} values")
        seen.add(object_id)
        try:
            return [_normalize_value(item, depth=depth + 1, counter=counter, seen=seen) for item in value]
        finally:
            seen.remove(object_id)

    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value)
    if len(text) > MAX_SCALAR_CHARS:
        raise ValueError(f"YAML property value exceeds {MAX_SCALAR_CHARS} characters")
    return text


__all__ = ["extract_wikilinks", "parse_obsidian_frontmatter"]
