"""First-class Obsidian-compatible vault exporter for Thought Pins."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import DocumentSource, Entity, Event, Memory, RawEntry, Relationship
from thoughtpins.source_policy import export_policy_for_source
from thoughtpins.store import get_session
from thoughtpins.vault.bases import GENERATED_BASES, write_vault_bases
from thoughtpins.vault.canvas import MEMORY_CANVAS_PATH, write_memory_canvas
from thoughtpins.vault.entity_note import render_entity_note
from thoughtpins.vault.export_format import (
    _entity_stat_bucket,
    _entry_date,
    _entry_datetime,
    _entry_time_label,
    _entry_title,
    _event_date,
    _group_by_local_date,
    _iso,
    _markdown_table,
    _metadata,
    _portable_memory_text,
    _portable_source_reference,
    _tag_for_source,
)
from thoughtpins.vault.export_support import (
    INDEXES,
    clean_generated_vault,
    managed_generated_paths,
    package_vault,
    vault_staging_directory,
    write_vault_manifest,
)
from thoughtpins.vault.incremental import load_managed_note_paths, reconcile_generated_vault, write_export_state
from thoughtpins.vault.library_note import render_library_note
from thoughtpins.vault.markdown import (
    escape_wikilink_tokens,
    fenced_text,
    markdown_list,
    safe_filename,
    safe_markdown_heading,
    wikilink,
)
from thoughtpins.vault.note_writer import VaultNoteWriter
from thoughtpins.vault.obsidian_defaults import write_obsidian_defaults
from thoughtpins.vault.paths import ENTITY_FOLDERS
from thoughtpins.vault.projection import (
    VaultPaths,
    VaultProjectionLoader,
    build_vault_paths,
    entity_public_bounds,
    entity_public_confidence,
)
from thoughtpins.vault.validator import VaultValidationResult, validate_vault


class VaultExporter:
    """Export a user's human-readable notes as a normal Obsidian vault folder."""

    def __init__(
        self,
        session: Session | None = None,
        user_id: str | None = None,
        vault_path: str | Path | None = None,
        *,
        path_hints: dict[str, PurePosixPath] | None = None,
    ):
        self._session = session or get_session()
        self.user_id = user_id
        root = Path(vault_path) if vault_path is not None else config.vault_path()
        self._root = root
        self._vault = root / user_id if user_id else root
        self.validation_result: VaultValidationResult | None = None
        self._entry_paths: dict[str, PurePosixPath] = {}
        self._daily_paths: dict[date, PurePosixPath] = {}
        self._entity_paths: dict[str, PurePosixPath] = {}
        self._entity_names: dict[str, str] = {}
        self._event_paths: dict[str, PurePosixPath] = {}
        self._document_paths: dict[str, PurePosixPath] = {}
        self._written: set[PurePosixPath] = set()
        self._note_writer = VaultNoteWriter(
            vault=self._vault,
            entry_paths=self._entry_paths,
            entity_paths=self._entity_paths,
            entity_names=self._entity_names,
            written=self._written,
        )
        self._path_hints = path_hints or {}

    def export_all(
        self,
        *,
        clean: bool = True,
        validate: bool = True,
        package_zip: bool = False,
        obsidian_defaults: bool = False,
        incremental: bool = False,
        conflict_policy: Literal["preserve", "overwrite"] = "preserve",
    ) -> dict[str, Any]:
        """Regenerate all vault notes and return export statistics."""

        if incremental:
            return self._export_incremental(
                validate=validate,
                package_zip=package_zip,
                obsidian_defaults=obsidian_defaults,
                conflict_policy=conflict_policy,
            )

        self._reset_projection_state()
        if clean:
            clean_generated_vault(self._vault, self._root, self.user_id)
        self._vault.mkdir(parents=True, exist_ok=True)
        (self._vault / "Attachments").mkdir(parents=True, exist_ok=True)
        (self._vault / "_System").mkdir(parents=True, exist_ok=True)

        projection = VaultProjectionLoader(self._session, self.user_id).load()
        entries = projection.entries
        entities = projection.entities
        events = projection.events
        documents = projection.documents
        relationships = projection.relationships
        memories = projection.memories
        paths = build_vault_paths(projection)
        self._apply_path_hints(paths)
        self._entry_paths.update(paths.entries)
        self._daily_paths.update(paths.daily)
        self._entity_paths.update(paths.entities)
        self._entity_names.update(paths.entity_names)
        self._event_paths.update(paths.events)
        self._document_paths.update(paths.documents)
        public_entry_ids = set(self._entry_paths)

        stats: dict[str, Any] = {
            "daily_notes": 0,
            "entries": 0,
            "people": 0,
            "places": 0,
            "organizations": 0,
            "projects": 0,
            "events": 0,
            "things": 0,
            "concepts": 0,
            "documents": 0,
            "indexes": 0,
            "bases": 0,
            "canvases": 0,
            "vault_files": 0,
            "validation_errors": 0,
            "validation_warnings": 0,
            "obsidian_defaults": False,
            "obsidian_default_files": [],
        }

        self._write_home(entries, entities, events, documents)
        stats["indexes"] += self._write_indexes(entries, entities, events, documents)

        for local_date, day_entries in sorted(_group_by_local_date(entries).items()):
            self._write_daily_note(local_date, day_entries)
            stats["daily_notes"] += 1
        for entry in entries:
            self._write_entry_note(entry)
            stats["entries"] += 1
        for entity in entities:
            self._write_entity_note(
                entity,
                memories=memories,
                relationships=relationships,
                events=events,
                public_entry_ids=public_entry_ids,
            )
            stats[_entity_stat_bucket(entity.type)] += 1
        for event in events:
            self._write_event_note(event)
            stats["events"] += 1
        for document in documents:
            self._write_document_note(document)
            stats["documents"] += 1

        stats["base_files"] = write_vault_bases(self._vault)
        stats["bases"] = len(stats["base_files"])
        stats["canvas_files"] = [
            write_memory_canvas(self._vault, entities, relationships, self._entity_paths),
        ]
        stats["canvases"] = len(stats["canvas_files"])

        if obsidian_defaults:
            stats["obsidian_defaults"] = True
            stats["obsidian_default_files"] = write_obsidian_defaults(self._vault)

        write_vault_manifest(self._vault, self.user_id, stats)
        stats["vault_files"] = sum(1 for path in self._vault.rglob("*") if path.is_file())
        write_vault_manifest(self._vault, self.user_id, stats)
        if validate:
            self.validation_result = validate_vault(self._vault)
            stats["validation_errors"] = len(self.validation_result.errors)
            stats["validation_warnings"] = len(self.validation_result.warnings)
            write_vault_manifest(self._vault, self.user_id, stats)
            if not self.validation_result.ok:
                logger.warning("Vault validation found {} errors", len(self.validation_result.errors))
        stats["vault_files"] = sum(1 for path in self._vault.rglob("*") if path.is_file()) + 1
        write_vault_manifest(self._vault, self.user_id, stats)
        write_export_state(self._vault, managed_generated_paths(self._written, stats))
        if package_zip:
            stats["zip_path"] = str(self.export_zip())
        logger.info("Thought Pins vault export complete: {}", stats)
        return stats

    def _export_incremental(
        self,
        *,
        validate: bool,
        package_zip: bool,
        obsidian_defaults: bool,
        conflict_policy: Literal["preserve", "overwrite"],
    ) -> dict[str, Any]:
        """Project to staging, then merge only files that remain generator-owned."""

        # Keep staging outside the destination tree. Deep user-selected vault
        # paths otherwise exceed legacy Windows path limits before projection.
        staging_root = config.vault_import_path().parent / "vault_export_staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        with vault_staging_directory(staging_root) as temporary:
            staged = VaultExporter(
                self._session,
                user_id=self.user_id,
                vault_path=temporary,
                path_hints=load_managed_note_paths(self._vault),
            )
            stats = staged.export_all(
                clean=True,
                validate=False,
                package_zip=False,
                obsidian_defaults=obsidian_defaults,
            )
            reconciliation = reconcile_generated_vault(
                self._vault,
                staged._vault,
                conflict_policy=conflict_policy,
            )

        stats.update(
            {
                "incremental": True,
                "conflict_policy": conflict_policy,
                **reconciliation.as_dict(),
            }
        )
        stats["vault_files"] = sum(1 for path in self._vault.rglob("*") if path.is_file())
        if validate:
            self.validation_result = validate_vault(self._vault)
            stats["validation_errors"] = len(self.validation_result.errors)
            stats["validation_warnings"] = len(self.validation_result.warnings)
        if package_zip:
            stats["zip_path"] = str(self.export_zip())
        logger.info("Thought Pins incremental vault export complete: {}", stats)
        return stats

    def _reset_projection_state(self) -> None:
        self._entry_paths.clear()
        self._daily_paths.clear()
        self._entity_paths.clear()
        self._entity_names.clear()
        self._event_paths.clear()
        self._document_paths.clear()
        self._written.clear()

    def _apply_path_hints(self, paths: VaultPaths) -> None:
        """Keep generated note paths stable after a title or first-line edit."""

        assignments = (
            (paths.entries, "entry-", "Entries"),
            (paths.entities, "entity-", None),
            (paths.events, "event-", "Events"),
            (paths.documents, "document-", "Library"),
        )
        claimed: set[PurePosixPath] = set()
        for mapping, prefix, required_root in assignments:
            for object_id in list(mapping):
                hint = self._path_hints.get(f"{prefix}{object_id}")
                if hint is None or not self._valid_path_hint(hint, required_root=required_root) or hint in claimed:
                    continue
                mapping[object_id] = hint
                claimed.add(hint)
        for day in list(paths.daily):
            hint = self._path_hints.get(f"journal-{day.isoformat()}")
            if hint is None or not self._valid_path_hint(hint, required_root="Journal") or hint in claimed:
                continue
            paths.daily[day] = hint
            claimed.add(hint)

    @staticmethod
    def _valid_path_hint(path: PurePosixPath | None, *, required_root: str | None) -> bool:
        if path is None or path.is_absolute() or path.suffix.casefold() != ".md" or ".." in path.parts:
            return False
        if required_root is not None and (not path.parts or path.parts[0] != required_root):
            return False
        return bool(path.parts)

    def export_zip(self, zip_path: str | Path | None = None) -> Path:
        target = Path(zip_path) if zip_path else self._vault.with_suffix(".zip")
        return package_vault(self._vault, target)

    def _write_home(
        self, entries: list[RawEntry], entities: list[Entity], events: list[Event], documents: list[DocumentSource]
    ) -> None:
        index_links = [wikilink(path) for path in INDEXES.values()]
        view_links = [f"[[{path.as_posix()}|{path.stem}]]" for path in (*GENERATED_BASES, MEMORY_CANVAS_PATH)]
        related = index_links + view_links
        metadata = _metadata(
            note_id="vault-home",
            note_type="home",
            title="Vault Home",
            source="thoughtpins_vault",
            tags=["thoughtpins", "vault"],
            related=related,
        )
        body = "\n".join(
            [
                "# Vault Home",
                "",
                "This is the human-readable Thought Pins vault. It is a normal Markdown folder intended to open directly in Obsidian.",
                "",
                "## Start Here",
                markdown_list(index_links),
                "",
                "## Live Views",
                markdown_list(view_links),
                "",
                "## Current Counts",
                f"- Entries: {len(entries)}",
                f"- Entities: {len(entities)}",
                f"- Events: {len(events)}",
                f"- Library sources: {len(documents)}",
                "",
                "## Open In Obsidian",
                "- Open this folder with Obsidian's `Open folder as vault` flow.",
                "- Start from `Vault Home.md`, then use `_Indexes` to browse by journal day, entity, or saved source.",
                "- `_Views` contains native Bases and a Canvas memory map; no community plugins are required.",
                "- The `Attachments` folder is reserved for future images, PDFs, and imports.",
                "",
                "## System Boundary",
                "The vault is the readable notes layer. SQL rows, vectors, and graph indexes remain internal retrieval infrastructure.",
            ]
        )
        self._note_writer.write_note(PurePosixPath("Vault Home.md"), metadata, body)

    def _write_indexes(
        self, entries: list[RawEntry], entities: list[Entity], events: list[Event], documents: list[DocumentSource]
    ) -> int:
        written = 0
        daily_links = [wikilink(path) for _, path in sorted(self._daily_paths.items())]
        entry_links = [wikilink(self._entry_paths[entry.id], label=_entry_title(entry)) for entry in entries]
        event_links = [wikilink(self._event_paths[event.id], label=event.name) for event in events]
        document_links = [wikilink(self._document_paths[doc.id], label=doc.title) for doc in documents]
        sections: dict[str, list[str]] = defaultdict(list)
        for entity in entities:
            folder = ENTITY_FOLDERS.get((entity.type or "concept").lower(), "Concepts")
            sections[folder].append(wikilink(self._entity_paths[entity.id], label=self._entity_names[entity.id]))

        written += self._write_index("Journal", INDEXES["journal"], daily_links)
        written += self._write_index("Entries", INDEXES["entries"], entry_links)
        written += self._write_index("People", INDEXES["people"], sorted(sections.get("People", [])))
        written += self._write_index("Places", INDEXES["places"], sorted(sections.get("Places", [])))
        written += self._write_index(
            "Organizations", INDEXES["organizations"], sorted(sections.get("Organizations", []))
        )
        written += self._write_index("Projects", INDEXES["projects"], sorted(sections.get("Projects", [])))
        written += self._write_index("Events", INDEXES["events"], sorted(event_links + sections.get("Events", [])))
        written += self._write_index("Things", INDEXES["things"], sorted(sections.get("Things", [])))
        written += self._write_index("Concepts", INDEXES["concepts"], sorted(sections.get("Concepts", [])))
        written += self._write_index("Library", INDEXES["library"], document_links)
        return written

    def _write_index(self, title: str, stem: PurePosixPath, links: list[str]) -> int:
        metadata = _metadata(
            note_id=f"index-{safe_filename(title).lower()}",
            note_type="index",
            title=title,
            source="thoughtpins_vault",
            tags=["thoughtpins", "index"],
            related=links,
        )
        body = f"# {title}\n\n{markdown_list(links, empty='No notes exported yet.')}"
        self._note_writer.write_note(stem.with_suffix(".md"), metadata, body)
        return 1

    def _write_daily_note(self, local_date: date, entries: list[RawEntry]) -> None:
        rel = self._daily_paths[local_date]
        entry_links = [wikilink(self._entry_paths[entry.id], label=_entry_time_label(entry)) for entry in entries]
        entity_links = sorted({link for entry in entries for link in self._note_writer.entry_entity_links(entry)})
        metadata = _metadata(
            note_id=f"journal-{local_date.isoformat()}",
            note_type="daily_journal",
            title=local_date.isoformat(),
            created=local_date.isoformat(),
            updated=local_date.isoformat(),
            source="thoughtpins_vault",
            tags=["thoughtpins", "journal", "daily"],
            related=entry_links + entity_links,
        )
        metadata["date"] = local_date.isoformat()
        metadata["entry_count"] = len(entries)
        body = "\n".join(
            [
                f"# {local_date.isoformat()}",
                "",
                "## Entries",
                markdown_list(entry_links, empty="No entries exported."),
                "",
                "## Mentioned",
                markdown_list(entity_links),
            ]
        )
        self._note_writer.write_note(rel, metadata, body)

    def _write_entry_note(self, entry: RawEntry) -> None:
        rel = self._entry_paths[entry.id]
        day = _entry_date(entry)
        entity_links = self._note_writer.entry_entity_links(entry)
        related = [wikilink(self._daily_paths[day])] + entity_links
        source_document = next(iter(entry.document_sources), None)
        source_policy = export_policy_for_source(source_document) if source_document is not None else None
        text = (
            _portable_source_reference(source_document)
            if source_document is not None and source_policy is not None and not source_policy.include_source_text
            else maybe_decrypt_text(entry.raw_text)
        )
        metadata = _metadata(
            note_id=f"entry-{entry.id}",
            note_type="entry",
            title=_entry_title(entry),
            created=_iso(_entry_datetime(entry)),
            updated=_iso(entry.created_at_utc),
            source=entry.source or "unknown",
            tags=["thoughtpins", "entry", _tag_for_source(entry.source)],
            thoughtpins_id=entry.id,
            related=related,
        )
        metadata["importance"] = entry.user_importance
        metadata["date"] = day.isoformat()
        portable_memories = [
            memory
            for memory in entry.memories
            if source_policy is None or source_policy.include_source_chunks or memory.memory_type != "source_excerpt"
        ]
        memory_lines = [
            f"- {escape_wikilink_tokens(_portable_memory_text(memory, source_document, source_policy))}"
            for memory in portable_memories[:20]
        ]
        body = "\n".join(
            [
                f"# {safe_markdown_heading(_entry_title(entry))}",
                "",
                "## Context",
                f"- Date: {day.isoformat()}",
                f"- Time: {entry.local_time or _entry_datetime(entry).strftime('%H:%M')}",
                f"- Source: {entry.source or 'unknown'}",
                f"- Importance: {entry.user_importance}/5"
                if entry.user_importance is not None
                else "- Importance: Unrated",
                f"- Daily note: {wikilink(self._daily_paths[day])}",
                "",
                "## Mentioned",
                markdown_list(entity_links),
                "",
                "## Memories",
                "\n".join(memory_lines) if memory_lines else "- No extracted memories recorded.",
                "",
                "## Original Text",
                fenced_text(text),
            ]
        )
        self._note_writer.write_note(rel, metadata, body)

    def _write_entity_note(
        self,
        entity: Entity,
        *,
        memories: list[Memory],
        relationships: list[Relationship],
        events: list[Event],
        public_entry_ids: set[str],
    ) -> None:
        rel = self._entity_paths[entity.id]
        portable_name = self._entity_names[entity.id]
        entity_memories = [
            memory
            for memory in memories
            if memory.subject_entity_id == entity.id or memory.object_entity_id == entity.id
        ]
        entity_mentions = [mention for mention in entity.entity_mentions if mention.raw_entry_id in public_entry_ids]
        entity_relationships = [
            relationship
            for relationship in relationships
            if relationship.source_entity_id == entity.id or relationship.target_entity_id == entity.id
        ]
        related = sorted({link for link in self._note_writer.relationship_links(entity, entity_relationships)})
        source_links = sorted(
            {
                self._note_writer.entry_link(mention.raw_entry_id)
                for mention in entity_mentions
                if mention.raw_entry_id in self._entry_paths
            }
        )
        aliases = sorted(
            {
                mention.surface_text.strip()
                for mention in entity_mentions
                if mention.surface_text.strip().casefold() != portable_name.casefold()
            }
        )
        first_seen, last_seen = entity_public_bounds(
            entity,
            entity_mentions=entity_mentions,
            memories=entity_memories,
            relationships=entity_relationships,
            events=events,
        )
        metadata, body = render_entity_note(
            entity,
            portable_name=portable_name,
            memories=entity_memories,
            mention_count=len(entity_mentions),
            relationship_count=len(entity_relationships),
            aliases=aliases,
            related=related,
            source_links=source_links,
            relationship_lines=self._note_writer.relationship_lines(entity, entity_relationships[:40]),
            first_seen=first_seen,
            last_seen=last_seen,
            confidence=entity_public_confidence(
                entity_mentions=entity_mentions,
                memories=entity_memories,
                relationships=entity_relationships,
            ),
            public_entry_ids=public_entry_ids,
            link_name=self._note_writer.entity_link_by_name,
        )
        self._note_writer.write_note(rel, metadata, body)

    def _write_event_note(self, event: Event) -> None:
        rel = self._event_paths[event.id]
        day = _event_date(event)
        source_link = (
            self._note_writer.entry_link(event.source_raw_entry_id)
            if event.source_raw_entry_id in self._entry_paths
            else None
        )
        place_link = None
        if event.place_entity_id and event.place_entity_id in self._entity_paths:
            place_link = wikilink(
                self._entity_paths[event.place_entity_id],
                label=self._entity_names[event.place_entity_id],
            )
        participant_links = []
        for participant in event.participants:
            if participant.entity_id in self._entity_paths:
                participant_links.append(
                    wikilink(
                        self._entity_paths[participant.entity_id], label=self._entity_names[participant.entity_id]
                    ),
                )
        related = sorted(
            set(([source_link] if source_link else []) + ([place_link] if place_link else []) + participant_links)
        )
        metadata = _metadata(
            note_id=f"event-{event.id}",
            note_type="event",
            title=event.name,
            created=_iso(
                event.start_at or event.local_date or event.raw_entry.created_at_utc
                if event.raw_entry
                else event.local_date
            ),
            updated=_iso(
                event.end_at or event.local_date or event.raw_entry.created_at_utc
                if event.raw_entry
                else event.local_date
            ),
            source="thoughtpins_event",
            tags=[
                "thoughtpins",
                "event",
                f"event/{safe_filename(event.event_type or 'other', fallback='other').lower()}",
            ],
            thoughtpins_id=event.id,
            related=related,
        )
        metadata.update(
            {
                "event_type": event.event_type or "other",
                "date": day.isoformat(),
                "participant_count": len(participant_links),
            }
        )
        card = _markdown_table(
            [
                ("Type", event.event_type),
                ("Date", day.isoformat()),
                ("Place", place_link or "unknown"),
                ("Participants", len(participant_links)),
                ("Source entry", source_link or "unavailable"),
            ]
        )
        body = "\n".join(
            [
                f"# {safe_markdown_heading(event.name)}",
                "",
                "## Card",
                card,
                "",
                "## Known Attributes",
                f"- Event type: {escape_wikilink_tokens(event.event_type or 'other')}",
                f"- Sensitivity: {escape_wikilink_tokens(event.sensitivity or 'personal')}",
                "",
                "## Summary",
                escape_wikilink_tokens(event.summary or "No event summary recorded."),
                "",
                "## Participants",
                markdown_list(sorted(set(participant_links))),
                "",
                "## Place",
                markdown_list([place_link] if place_link else []),
                "",
                "## Recent Memories",
                f"- {escape_wikilink_tokens(event.summary)}" if event.summary else "- No memories recorded yet.",
                "",
                "## Relationships",
                markdown_list(sorted(set(participant_links + ([place_link] if place_link else [])))),
                "",
                "## Source Entries",
                markdown_list([source_link] if source_link else []),
            ]
        )
        self._note_writer.write_note(rel, metadata, body)

    def _write_document_note(self, document: DocumentSource) -> None:
        rel = self._document_paths[document.id]
        entity_links = self._note_writer.entry_entity_links(document.raw_entry) if document.raw_entry else []
        source_entry_link = (
            self._note_writer.entry_link(document.raw_entry_id) if document.raw_entry_id in self._entry_paths else None
        )
        related = entity_links + ([source_entry_link] if source_entry_link else [])
        metadata, body = render_library_note(document, related, link_name=self._note_writer.entity_link_by_name)
        self._note_writer.write_note(rel, metadata, body)
