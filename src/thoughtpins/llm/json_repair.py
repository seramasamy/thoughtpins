"""JSON repair boundary for structured model output."""

from __future__ import annotations

from json_repair import repair_json as _repair_json


def repair_json(text: str) -> str:
    """Repair common syntax damage without inventing schema-level values."""
    if not text.strip():
        return ""
    repaired = _repair_json(text, ensure_ascii=False)
    return repaired if isinstance(repaired, str) else ""
