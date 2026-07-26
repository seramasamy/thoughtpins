"""Shared Obsidian vault note path helpers."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath

from thoughtpins.vault.markdown import safe_filename

ENTITY_FOLDERS = {
    "person": "People",
    "place": "Places",
    "organization": "Organizations",
    "company": "Organizations",
    "project": "Projects",
    "idea": "Projects",
    "event": "Events",
    "thing": "Things",
    "object": "Things",
    "technology": "Things",
    "concept": "Concepts",
    "topic": "Concepts",
    "document": "Concepts",
}


def entity_note_path(entity_type: str | None, canonical_name: str, *, fallback: str = "Entity") -> PurePosixPath:
    folder = ENTITY_FOLDERS.get((entity_type or "concept").lower(), "Concepts")
    return PurePosixPath(folder) / f"{safe_filename(canonical_name, fallback=fallback)}.md"


def event_note_path(
    *,
    event_name: str,
    local_date: date | None = None,
    start_at: datetime | None = None,
    fallback: str = "Event",
) -> PurePosixPath:
    day = local_date or (start_at.date() if start_at else date.today())
    folder = PurePosixPath("Events") / str(day.year) / f"{day.month:02d}"
    stem = safe_filename(f"{day.isoformat()} {event_name}", fallback=fallback, max_length=100)
    return folder / f"{stem}.md"


def document_note_path(source_type: str | None, title: str, *, fallback: str = "Source") -> PurePosixPath:
    folder = PurePosixPath("Library/Articles" if source_type in {"url", "article"} else "Library/Documents")
    return folder / f"{safe_filename(title, fallback=fallback)}.md"
