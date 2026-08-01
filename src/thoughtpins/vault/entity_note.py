"""Entity-note rendering for exported vaults.

Split out of the exporter for the same reason `library_note` was: the exporter
should decide which notes exist, not carry the Markdown for each kind.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from thoughtpins.db import Entity, Memory
from thoughtpins.vault.export_format import (
    _attribute_lines,
    _date_only,
    _entity_note_type,
    _iso,
    _markdown_table,
    _metadata,
)
from thoughtpins.vault.markdown import escape_wikilink_tokens, markdown_list, safe_markdown_heading

QUOTE_MEMORY_TYPES = {"quote", "quotation"}


def is_quote(memory: Memory) -> bool:
    """Extraction has labelled these both ways, so accept either spelling."""
    return (memory.memory_type or "").strip().casefold() in QUOTE_MEMORY_TYPES


def quote_lines(
    quotes: list[Memory],
    *,
    speaker: str,
    link_name: Callable[[str], str | None],
) -> list[str]:
    """Render quotes, linking the other people each one names."""
    lines: list[str] = []
    for memory in quotes:
        structured = memory.structured_json if isinstance(memory.structured_json, dict) else {}
        names = [
            name
            for key in ("people_involved", "people_discussed")
            for name in _as_names(structured.get(key))
            if name.casefold() != speaker.casefold()
        ]
        mentioned = sorted({link for link in (link_name(name) for name in names) if link})
        suffix = f" — mentions {', '.join(mentioned)}" if mentioned else ""
        lines.append(f"- {escape_wikilink_tokens(memory.text)}{suffix}")
    return lines


def render_entity_note(
    entity: Entity,
    *,
    portable_name: str,
    memories: list[Memory],
    mention_count: int,
    relationship_count: int,
    aliases: list[str],
    related: list[str],
    source_links: list[str],
    relationship_lines: list[str],
    first_seen: Any,
    last_seen: Any,
    confidence: str,
    public_entry_ids: set[str],
    link_name: Callable[[str], str | None],
) -> tuple[dict[str, Any], str]:
    """Return frontmatter and Markdown for one entity note."""
    metadata = _metadata(
        note_id=f"entity-{entity.id}",
        note_type=_entity_note_type(entity.type),
        title=portable_name,
        created=_iso(first_seen),
        updated=_iso(last_seen),
        source="thoughtpins_memory",
        tags=["thoughtpins", "entity", _entity_note_type(entity.type)],
        aliases=aliases,
        thoughtpins_id=entity.id,
        related=related + source_links[:20],
    )
    # Quotes get their own section: a remembered sentence is worth more than a
    # line buried in a memory list, and the people it names become real links.
    quotes = [memory for memory in memories if is_quote(memory)]
    others = [memory for memory in memories if not is_quote(memory)]
    metadata.update(
        {
            "memory_count": len(memories),
            "quote_count": len(quotes),
            "mention_count": mention_count,
            "relationship_count": relationship_count,
            "first_seen": _date_only(first_seen),
            "last_seen": _date_only(last_seen),
            "confidence": confidence,
        }
    )
    attr_lines = _attribute_lines(entity, public_entry_ids)
    rendered_quotes = quote_lines(quotes[:25], speaker=portable_name, link_name=link_name)
    memory_lines = [f"- {escape_wikilink_tokens(memory.text)}" for memory in others[:25]]
    card = _markdown_table(
        [
            ("Type", entity.type),
            ("Memories", len(memories)),
            ("Quotes", len(quotes)),
            ("Mentions", mention_count),
            ("Relationships", relationship_count),
            ("First seen", _date_only(first_seen)),
            ("Last seen", _date_only(last_seen)),
        ]
    )
    body = "\n".join(
        [
            f"# {safe_markdown_heading(portable_name)}",
            "",
            "## Card",
            card,
            "",
            "## Known Attributes",
            "\n".join(attr_lines) if attr_lines else "- No attributes recorded yet.",
            "",
            "## Quotes",
            "\n".join(rendered_quotes) if rendered_quotes else "- No quotes recorded yet.",
            "",
            "## Recent Memories",
            "\n".join(memory_lines) if memory_lines else "- No memories recorded yet.",
            "",
            "## Relationships",
            "\n".join(relationship_lines) if relationship_lines else "- No relationships recorded yet.",
            "",
            "## Source Entries",
            markdown_list(source_links[:30]),
        ]
    )
    return metadata, body


def _as_names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


__all__ = ["is_quote", "quote_lines", "render_entity_note", "QUOTE_MEMORY_TYPES"]
