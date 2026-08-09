"""Conservative natural-language routing for product operational commands."""

from __future__ import annotations

import time
from dataclasses import dataclass

from thoughtpins.chat.natural_command_parser import route_natural_command
from thoughtpins.chat.natural_command_patterns import _normalize
from thoughtpins.chat.natural_command_types import NaturalCommandRoute

__all__ = [
    "NaturalCommandRoute",
    "PENDING_TTL_SECONDS",
    "clear_pending",
    "confirmation_prompt",
    "describe_route",
    "get_pending",
    "interpret_confirmation",
    "pop_pending",
    "route_natural_command",
    "set_pending",
]


PENDING_TTL_SECONDS = 10 * 60


@dataclass
class PendingNaturalCommand:
    route: NaturalCommandRoute
    created_at: float


_PENDING: dict[str, PendingNaturalCommand] = {}


def get_pending(chat_id: str) -> PendingNaturalCommand | None:
    pending = _PENDING.get(chat_id)
    if not pending:
        return None
    if time.monotonic() - pending.created_at > PENDING_TTL_SECONDS:
        _PENDING.pop(chat_id, None)
        return None
    return pending


def set_pending(chat_id: str, route: NaturalCommandRoute) -> None:
    _PENDING[chat_id] = PendingNaturalCommand(route=route, created_at=time.monotonic())


def pop_pending(chat_id: str) -> PendingNaturalCommand | None:
    pending = get_pending(chat_id)
    _PENDING.pop(chat_id, None)
    return pending


def clear_pending(chat_id: str) -> None:
    _PENDING.pop(chat_id, None)


def interpret_confirmation(text: str, route: NaturalCommandRoute) -> str | None:
    """Return 'confirm', 'cancel', or None for a pending command."""
    lowered = _normalize(text)
    action = route.action
    cancel_words = {
        "cancel",
        "cancel that",
        "never mind",
        "nevermind",
        "no",
        "nope",
        "stop",
    }
    if lowered in cancel_words:
        return "cancel"

    confirm_forms = {
        "confirm",
        f"confirm {action}",
        "yes confirm",
        "yes, confirm",
        "proceed",
        "go ahead",
    }
    if lowered in confirm_forms:
        return "confirm"
    if lowered.startswith("confirm ") and action in lowered.split():
        return "confirm"
    return None


def confirmation_prompt(route: NaturalCommandRoute) -> str:
    if route.prompt:
        return route.prompt
    action = route.action.replace("_", " ")
    return f"Confirm {action}? Reply `confirm {route.action}` to proceed, or `cancel`."


def describe_route(route: NaturalCommandRoute) -> str:
    if route.args:
        return f"{route.action} {' '.join(route.args)}".strip()
    return route.action
