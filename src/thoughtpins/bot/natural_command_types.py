"""Value types and routing guardrails for natural command interpretation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NaturalCommandRoute:
    action: str
    args: list[str] = field(default_factory=list)
    needs_confirmation: bool = False
    prompt: str = ""
    reason: str = ""


JOURNAL_PREFIX_BLOCKLIST = (
    "bar note",
    "business idea",
    "coffee chat",
    "daily note",
    "date night note",
    "deep contemplative journal",
    "deep journal",
    "dinner note",
    "errand note",
    "journal",
    "journal note",
    "networking event note",
    "networking note",
    "note:",
    "note to self",
    "quick bar note",
    "quick daily thought",
    "quick errand note",
    "quick journal",
    "quick note",
    "random thought",
    "recipe idea",
    "recipe note",
    "small social read",
    "spiritual note",
    "thought:",
)
