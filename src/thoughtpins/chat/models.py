"""Stable value contracts returned by the unified chat engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from thoughtpins.chat.natural_commands import NaturalCommandRoute


@dataclass(frozen=True)
class ChatRouteDecision:
    route_type: str
    routed_text: str
    classification: dict = field(default_factory=dict)
    natural_route: NaturalCommandRoute | None = None


@dataclass
class ChatEngineResult:
    status: str
    route_type: str
    reply: str
    entry_id: str | None = None
    job_id: str | None = None
    document_id: str | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    context_size_chars: int = 0
    metadata: dict = field(default_factory=dict)
