"""Declarative base and the row defaults every model shares.

Separated from the model definitions so :mod:`thoughtpins.db` describes tables
and nothing else. Identifier and timestamp defaults live here because every
table uses them and none of them owns them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Registry for every Thought Pins table."""


def _new_id() -> str:
    """A short opaque row identifier, unique enough for a personal corpus."""
    return uuid.uuid4().hex[:16]


def _utcnow() -> datetime:
    """Naive UTC, matching the DateTime columns this schema declares.

    Stored without a timezone because every column is naive; attaching one here
    would make comparisons silently inconsistent across the codebase.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


__all__ = ["Base", "_new_id", "_utcnow"]
