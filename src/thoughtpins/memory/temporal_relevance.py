"""Deterministic temporal windows for relative-date memory queries."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class TemporalWindow:
    start: date
    end: date
    expression: str

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("temporal window end must not precede start")


def parse_temporal_window(query: str, *, as_of: date) -> TemporalWindow | None:
    normalized = re.sub(r"\s+", " ", query.lower()).strip()
    if match := re.search(r"\b(\d{1,4})\s+days?\s+ago\b", normalized):
        days = int(match.group(1))
        target = as_of - timedelta(days=days)
        return TemporalWindow(target, target, match.group(0))
    if "yesterday" in normalized:
        target = as_of - timedelta(days=1)
        return TemporalWindow(target, target, "yesterday")
    if match := re.search(r"\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", normalized):
        weekday = _WEEKDAYS[match.group(1)]
        days_back = (as_of.weekday() - weekday) % 7 or 7
        target = as_of - timedelta(days=days_back)
        return TemporalWindow(target, target, match.group(0))
    if "last week" in normalized:
        current_week_start = as_of - timedelta(days=as_of.weekday())
        start = current_week_start - timedelta(days=7)
        return TemporalWindow(start, start + timedelta(days=6), "last week")
    if "last month" in normalized:
        current_month_start = as_of.replace(day=1)
        end = current_month_start - timedelta(days=1)
        return TemporalWindow(end.replace(day=1), end, "last month")
    if match := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", normalized):
        try:
            target = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
        return TemporalWindow(target, target, match.group(0))
    return None


def temporal_window_match(candidate_date: str, window: TemporalWindow | None) -> float:
    if window is None:
        return 0.0
    try:
        observed = date.fromisoformat(candidate_date)
    except (TypeError, ValueError):
        return 0.0
    if window.start <= observed <= window.end:
        return 1.0
    distance = min(abs((observed - window.start).days), abs((observed - window.end).days))
    return 0.35 * math.exp(-distance / 3.0)
