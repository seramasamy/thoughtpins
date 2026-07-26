"""Low-level note and relationship rendering for vault projections."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from thoughtpins.db import Entity, RawEntry, Relationship
from thoughtpins.vault.canvas import humanize_relation
from thoughtpins.vault.markdown import frontmatter_block, wikilink


class VaultNoteWriter:
    """Write unique notes and resolve links against mutable projection maps."""

    def __init__(
        self,
        *,
        vault: Path,
        entry_paths: dict[str, PurePosixPath],
        entity_paths: dict[str, PurePosixPath],
        entity_names: dict[str, str],
        written: set[PurePosixPath],
    ) -> None:
        self._vault = vault
        self._entry_paths = entry_paths
        self._entity_paths = entity_paths
        self._entity_names = entity_names
        self._written = written

    def entry_entity_links(self, entry: RawEntry | None) -> list[str]:
        if not entry:
            return []
        links = [
            wikilink(self._entity_paths[mention.entity_id], label=self._entity_names[mention.entity_id])
            for mention in entry.entity_mentions
            if mention.entity_id in self._entity_paths
        ]
        return sorted(set(links))

    def relationship_links(self, entity: Entity, relationships: list[Relationship]) -> list[str]:
        links: list[str] = []
        for relationship in relationships:
            other = (
                relationship.target_entity if relationship.source_entity_id == entity.id else relationship.source_entity
            )
            if other and other.id in self._entity_paths:
                links.append(wikilink(self._entity_paths[other.id], label=self._entity_names[other.id]))
        return links

    def relationship_lines(self, entity: Entity, relationships: list[Relationship]) -> list[str]:
        lines: list[str] = []
        for relationship in relationships:
            other = (
                relationship.target_entity if relationship.source_entity_id == entity.id else relationship.source_entity
            )
            if not other or other.id not in self._entity_paths:
                continue
            source = (
                self.entry_link(relationship.raw_entry_id)
                if relationship.raw_entry_id in self._entry_paths
                else "source entry unavailable"
            )
            lines.append(
                f"- {humanize_relation(relationship.relation_type)}: "
                f"{wikilink(self._entity_paths[other.id], label=self._entity_names[other.id])} "
                f"(confidence: {relationship.confidence}, source: {source})"
            )
        return lines

    def entry_link(self, raw_entry_id: str) -> str:
        return wikilink(self._entry_paths[raw_entry_id], label=f"entry {raw_entry_id[:8]}")

    def write_note(self, rel_path: PurePosixPath, metadata: dict[str, Any], body: str) -> None:
        if rel_path in self._written:
            raise RuntimeError(f"duplicate vault output path: {rel_path}")
        self._written.add(rel_path)
        target = self._vault / Path(rel_path.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(frontmatter_block(metadata) + body.rstrip() + "\n", encoding="utf-8")


__all__ = ["VaultNoteWriter"]
