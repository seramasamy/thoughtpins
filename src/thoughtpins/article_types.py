"""Shared values returned by the public article retrieval pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchedSource:
    original_url: str
    url: str
    title: str = ""
    text: str = ""
    status: str = "processed"
    error: str = ""
    source_domain: str = ""
    access_method: str = "public_fetch"
    rights_basis: str = "public_web"
    fetch_status: str = "processed"
    canonical_url: str = ""
    author: str | None = None
    published_at: datetime | None = None
    paywall_detected: bool = False
    retrieval_quality_score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _PublicHttpPayload:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    encoding: str
