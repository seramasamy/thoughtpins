"""Pure formatting and path helpers for portable vault exports."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import DocumentSource, Entity, Event, Memory, RawEntry
from thoughtpins.source_policy import export_policy_for_source
from thoughtpins.vault.markdown import escape_wikilink_tokens, safe_filename, safe_markdown_heading


def _metadata(
    *,
    note_id: str,
    note_type: str,
    title: str,
    source: str,
    tags: list[str],
    aliases: list[str] | None = None,
    thoughtpins_id: str | None = None,
    related: list[str] | None = None,
    created: str | None = None,
    updated: str | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    related_values = list(dict.fromkeys(related or []))
    payload = {
        "thoughtpins_schema": 2,
        "id": note_id,
        "type": note_type,
        "title": safe_markdown_heading(title),
        "created": created or timestamp,
        "updated": updated or created or timestamp,
        "source": source,
        "tags": tags,
        "aliases": aliases or [],
        "thoughtpins_id": thoughtpins_id or note_id,
        "related": related_values[:200],
    }
    if len(related_values) > 200:
        payload["related_count"] = len(related_values)
        payload["related_truncated"] = True
    return payload


def _unique_note_path(folder: PurePosixPath, stem: str, item_id: str, used: set[str]) -> PurePosixPath:
    if stem.casefold().endswith(".md"):
        stem = stem[:-3].rstrip(" .") or "Untitled"
    candidate = folder / f"{stem}.md"
    key = candidate.as_posix().lower()
    if key not in used:
        used.add(key)
        return candidate
    candidate = folder / f"{stem}-{item_id[:8]}.md"
    key = candidate.as_posix().lower()
    suffix = 2
    while key in used:
        candidate = folder / f"{stem}-{item_id[:8]}-{suffix}.md"
        key = candidate.as_posix().lower()
        suffix += 1
    used.add(key)
    return candidate


def _group_by_local_date(entries: Iterable[RawEntry]) -> dict[date, list[RawEntry]]:
    grouped: dict[date, list[RawEntry]] = defaultdict(list)
    for entry in entries:
        grouped[_entry_date(entry)].append(entry)
    return grouped


def _entry_date(entry: RawEntry) -> date:
    if entry.local_date:
        return entry.local_date
    if entry.created_at_utc:
        return entry.created_at_utc.date()
    return datetime.now(timezone.utc).date()


def _entry_datetime(entry: RawEntry) -> datetime:
    if entry.created_at_utc:
        return entry.created_at_utc
    return datetime.combine(_entry_date(entry), datetime.min.time())


def _event_date(event: Event) -> date:
    if event.local_date:
        return event.local_date
    if event.start_at:
        return event.start_at.date()
    if event.raw_entry and event.raw_entry.local_date:
        return event.raw_entry.local_date
    if event.raw_entry and event.raw_entry.created_at_utc:
        return event.raw_entry.created_at_utc.date()
    return datetime.now(timezone.utc).date()


def _entry_time_label(entry: RawEntry) -> str:
    time_label = entry.local_time or _entry_datetime(entry).strftime("%H:%M")
    if entry.user_importance is not None:
        return f"{time_label} ({entry.user_importance}/5)"
    return time_label


_TITLE_WIKILINK_RE = re.compile(r"\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]")
_TITLE_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]*")


def _entry_title(entry: RawEntry) -> str:
    """Build a plain-text label from the start of an entry.

    Text imported from another vault arrives carrying Obsidian syntax. A title
    is a label, not a place to keep links: a wikilink left here points at a path
    that only existed in the source vault, so it exports as a broken link and
    Obsidian offers to create the missing note. A leading heading marker is the
    same kind of leak, rendering as "# #" once the exporter adds its own.
    """
    text = maybe_decrypt_text(entry.raw_text)
    unlinked = _TITLE_WIKILINK_RE.sub(lambda match: (match.group(2) or match.group(1)).strip(), text)
    plain = _TITLE_HEADING_RE.sub("", unlinked)
    first = " ".join(plain.replace("\n", " ").split()[:10])
    return first[:90] or f"Entry {entry.id[:8]}"


def _tag_for_source(source: str | None) -> str:
    cleaned = safe_filename(source or "unknown", fallback="unknown", max_length=40).lower().replace(" ", "-")
    return f"source/{cleaned}"


def _entity_note_type(entity_type: str | None) -> str:
    normalized = (entity_type or "concept").lower()
    if normalized in {"company"}:
        return "organization"
    if normalized in {"technology", "thing", "object"}:
        return "thing"
    if normalized in {"event"}:
        return "event"
    if normalized in {"topic", "document"}:
        return "concept"
    if normalized in {"idea"}:
        return "project"
    return (
        normalized
        if normalized in {"person", "place", "organization", "project", "event", "thing", "concept"}
        else "concept"
    )


def _entity_stat_bucket(entity_type: str | None) -> str:
    note_type = _entity_note_type(entity_type)
    return {
        "person": "people",
        "place": "places",
        "organization": "organizations",
        "project": "projects",
        "event": "events",
        "thing": "things",
        "concept": "concepts",
    }[note_type]


def _attribute_lines(entity: Entity, allowed_entry_ids: set[str]) -> list[str]:
    """Render only attributes whose provenance is in the portable export."""
    lines: list[str] = []
    for attribute in entity.attributes_json or []:
        if not isinstance(attribute, dict):
            continue
        source_entry_id = str(attribute.get("source_entry_id") or "")
        if not source_entry_id or source_entry_id not in allowed_entry_ids:
            continue
        key = str(attribute.get("key") or "attribute")
        value = str(attribute.get("value") or "")
        confidence = attribute.get("confidence") or "unknown"
        lines.append(f"- {escape_wikilink_tokens(key)}: {escape_wikilink_tokens(value)} (confidence: {confidence})")
    return lines


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def _plain_list_items(items: list[str]) -> list[str]:
    return [escape_wikilink_tokens(" ".join(item.split())) for item in items if item.strip()]


def _markdown_table(rows: list[tuple[str, Any]]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in rows:
        lines.append(f"| {_table_cell(key)} | {_table_cell(value)} |")
    return "\n".join(lines)


def _table_cell(value: Any) -> str:
    if value is None:
        text = "unknown"
    else:
        text = " ".join(str(value).split()) or "unknown"
    return escape_wikilink_tokens(text).replace("|", r"\|")


def _document_text_policy(document: DocumentSource) -> str:
    policy = export_policy_for_source(document)
    if not policy.include_source_text:
        return "Third-party source text is excluded from portable exports; source details and derived memory remain available."
    if document.status != "processed":
        return "Full text was not available from an authorized source path."
    return "Full text is included because its rights classification permits portable reuse."


def _portable_document_summary(
    document: DocumentSource,
    analysis: dict[str, Any],
    include_extractive_summary: bool,
) -> str:
    if include_extractive_summary and document.summary:
        return document.summary
    topics = _string_list(analysis.get("topics", []))
    concepts = _string_list(analysis.get("key_concepts", []))
    publisher = document.source_domain or analysis.get("publisher") or "the original publisher"
    parts = [f"Saved source from {publisher}."]
    if topics:
        parts.append("Topics: " + ", ".join(topics[:6]) + ".")
    if concepts:
        parts.append("Key concepts: " + ", ".join(concepts[:10]) + ".")
    return " ".join(parts)


def _portable_source_reference(document: DocumentSource) -> str:
    lines = [f"Saved source: {document.title}"]
    if document.source_domain:
        lines.append(f"Publisher: {document.source_domain}")
    if document.source_url or document.original_url:
        lines.append(f"URL: {document.source_url or document.original_url}")
    lines.append("Third-party source text is intentionally excluded from portable exports.")
    return "\n".join(lines)


def _portable_memory_text(memory: Memory, document: DocumentSource | None, policy) -> str:
    if (
        document is not None
        and policy is not None
        and not policy.include_extractive_summary
        and memory.memory_type == "source_summary"
    ):
        return _portable_source_reference(document).replace("\n", " ")
    return memory.text


def _iso(value: datetime | date | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return value.isoformat()


def _date_only(value: datetime | date | None) -> str:
    if value is None:
        return "unknown"
    return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
