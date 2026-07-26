"""Operational summary contracts."""

from pydantic import BaseModel


class StatsResponse(BaseModel):
    raw_entries: int
    entities: int
    memories: int
    relationships: int
    events: int
    action_items: int
    expenses: int
    sources: int = 0
    uptime_seconds: float
    vault_files: int = 0
