"""Human-readable summary of what one ingested message actually captured."""

from __future__ import annotations

__all__ = ["format_capture_summary"]

_FIELDS = (
    ("memories", "memory", "memories"),
    ("entities", "entity", "entities"),
    ("events", "event", None),
    ("relationships", "link", None),
    ("action_items", "action item", None),
    ("expenses", "expense", None),
)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    label = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {label}"


def format_capture_summary(stats: dict) -> str:
    parts = [
        _plural(int(stats.get(key, 0) or 0), singular, plural)
        for key, singular, plural in _FIELDS
        if int(stats.get(key, 0) or 0) > 0
    ]
    return ", ".join(parts) if parts else "raw entry"
