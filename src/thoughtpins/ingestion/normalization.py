"""Normalize extracted entities before storage."""

from __future__ import annotations

import re


def normalize_name(name: str) -> str:
    """Normalize a person/place name: strip whitespace, title case."""
    name = name.strip()
    if not name:
        return name
    # Don't title-case acronyms or mixed-case names
    if name.isupper() or any(c.isupper() for c in name[1:]):
        return name
    return name.title()


def normalize_place(name: str) -> str:
    """Normalize place names."""
    name = name.strip()
    # Common place prefixes
    name = re.sub(r"\b(the)\b", "The", name, flags=re.IGNORECASE)
    return name


def canonical_guess(name: str) -> str:
    """Produce a canonical name guess from surface text."""
    return normalize_name(name)


def is_ambiguous_name(name: str) -> bool:
    """Check if a name might be ambiguous (single name without context)."""
    parts = name.strip().split()
    return len(parts) == 1 and len(parts[0]) > 0
