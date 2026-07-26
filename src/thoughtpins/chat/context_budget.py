"""Deterministic character-budget helpers for model context assembly."""

from __future__ import annotations


def truncate_middle(text: str, max_chars: int) -> str:
    """Fit text while retaining both its orienting prefix and recent tail."""
    if len(text) <= max_chars:
        return text
    if max_chars <= 200:
        return text[:max_chars]
    keep = (max_chars - 80) // 2
    omitted = len(text) - (keep * 2)
    return text[:keep] + f"\n\n... [{omitted} chars omitted] ...\n\n" + text[-keep:]
