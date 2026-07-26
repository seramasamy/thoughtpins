"""Shared immutable results for media extraction pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MediaExtraction:
    text: str = ""
    kind: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text.strip()) and self.error is None
