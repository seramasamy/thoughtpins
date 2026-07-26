"""Shared utilities: hashing, time helpers, text normalization."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from thoughtpins.config import config


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def local_now() -> datetime:
    return datetime.now(ZoneInfo(config.LOCAL_TIMEZONE))


def local_today() -> date:
    return local_now().date()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_relative_date(relative_text: str, from_date: date) -> dict:
    """Parse a relative date expression like 'next month' into a date range."""
    relative_text = relative_text.strip().lower()
    result = {
        "relative_text": relative_text,
        "inferred_start": None,
        "inferred_end": None,
        "precision": "unknown",
    }
    try:
        if "next month" in relative_text:
            next_month = from_date.replace(day=1) + relativedelta(months=1)
            end_of_next = next_month + relativedelta(months=1) - timedelta(days=1)
            result["inferred_start"] = next_month.isoformat()
            result["inferred_end"] = end_of_next.isoformat()
            result["precision"] = "month"
        elif "next week" in relative_text:
            days_until_monday = (7 - from_date.weekday()) % 7 or 7
            next_monday = from_date + timedelta(days=days_until_monday)
            result["inferred_start"] = next_monday.isoformat()
            result["inferred_end"] = (next_monday + timedelta(days=6)).isoformat()
            result["precision"] = "week"
        elif "next year" in relative_text:
            next_year = from_date.replace(year=from_date.year + 1, month=1, day=1)
            result["inferred_start"] = next_year.isoformat()
            result["inferred_end"] = next_year.replace(month=12, day=31).isoformat()
            result["precision"] = "year"
        elif "tomorrow" in relative_text:
            tomorrow = from_date + timedelta(days=1)
            result["inferred_start"] = tomorrow.isoformat()
            result["inferred_end"] = tomorrow.isoformat()
            result["precision"] = "day"
        elif "today" in relative_text or "tonight" in relative_text:
            result["inferred_start"] = from_date.isoformat()
            result["inferred_end"] = from_date.isoformat()
            result["precision"] = "day"
    except (OverflowError, ValueError):
        return result
    return result


SENSITIVITY_LABELS = frozenset(
    {
        "public_ok",
        "personal",
        "private",
        "confidential_work",
        "sensitive_third_party",
        "finance",
        "health",
        "relationship",
        "substance_use",
        "legal",
        "location_sensitive",
    }
)

MEMORY_TYPES = frozenset(
    {
        "fact",
        "event",
        "thought",
        "user_action",
        "quote",
        "commitment",
        "decision",
        "expense",
        "future_plan",
        "observation",
        "relationship_update",
        "correction",
    }
)

ENTITY_TYPES = frozenset(
    {
        "person",
        "place",
        "organization",
        "project",
        "technology",
        "document",
        "idea",
        "topic",
        "event",
        "thing",
        "object",
        "concept",
    }
)

RELATION_TYPES = frozenset(
    {
        "knows",
        "works_with",
        "works_on",
        "uses_technology",
        "met_at",
        "located_at",
        "discussed",
        "created",
        "read",
        "associated_with",
    }
)

CONFIDENCE_LEVELS = frozenset(
    {
        "observed_by_user",
        "user_reported",
        "hearsay_from_person",
        "inferred_by_model",
        "unknown",
    }
)
