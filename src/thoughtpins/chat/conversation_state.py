"""Bounded, crash-resistant local conversation state for adapter clients."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any

from thoughtpins.config import config

CACHE_MAX_CHATS = 50
HISTORY_MAX_MESSAGES = 200
HISTORY_PROMPT_CHARS = 140_000

ConversationMessage = dict[str, str]
ConversationCache = dict[str, list[ConversationMessage]]
CONVERSATION_CACHE: ConversationCache = {}

_CACHE_LOCK = RLock()


def cache_path() -> Path:
    return config.conversation_cache_path()


def load_conversation_cache(
    cache: ConversationCache = CONVERSATION_CACHE,
    *,
    path: Path | None = None,
) -> bool:
    """Load valid retained turns without replacing the shared cache object."""
    source = path or cache_path()
    if not source.exists():
        return False
    try:
        decoded: Any = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(decoded, dict):
        return False

    normalized: ConversationCache = {}
    for raw_chat_id, raw_history in decoded.items():
        if not isinstance(raw_chat_id, str) or not isinstance(raw_history, list):
            continue
        history: list[ConversationMessage] = []
        for raw_message in raw_history[-HISTORY_MAX_MESSAGES:]:
            if not isinstance(raw_message, dict):
                continue
            role = raw_message.get("role")
            content = raw_message.get("content")
            if role not in {"user", "assistant", "system"} or not isinstance(content, str):
                continue
            history.append({"role": role, "content": content})
        if history:
            normalized[raw_chat_id] = history

    with _CACHE_LOCK:
        cache.clear()
        cache.update(list(normalized.items())[-CACHE_MAX_CHATS:])
    return True


def save_conversation_cache(
    cache: ConversationCache = CONVERSATION_CACHE,
    *,
    path: Path | None = None,
) -> bool:
    """Atomically persist local history so interruption cannot leave partial JSON."""
    destination = path or cache_path()
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_LOCK:
            payload = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(destination)
        return True
    except (OSError, UnicodeError, TypeError, ValueError):
        temporary.unlink(missing_ok=True)
        return False


def remember_conversation_turn(
    chat_id: str,
    history: list[ConversationMessage],
    text: str,
    response: str,
    *,
    cache: ConversationCache = CONVERSATION_CACHE,
    persist: Callable[[], object] | None = None,
) -> None:
    retained = list(history[-HISTORY_MAX_MESSAGES:])
    retained.extend(
        (
            {"role": "user", "content": text},
            {"role": "assistant", "content": response},
        )
    )
    with _CACHE_LOCK:
        cache[chat_id] = retained[-HISTORY_MAX_MESSAGES:]
        while len(cache) > CACHE_MAX_CHATS:
            del cache[next(iter(cache))]
    (persist or save_conversation_cache)()


def history_for_prompt(
    history: list[ConversationMessage],
    max_chars: int = HISTORY_PROMPT_CHARS,
) -> list[ConversationMessage]:
    """Select the newest complete messages that fit the prompt budget."""
    selected: list[ConversationMessage] = []
    used = 0
    for message in reversed(history[-HISTORY_MAX_MESSAGES:]):
        content = str(message.get("content", ""))
        role = str(message.get("role", "user"))
        cost = len(content) + len(role) + 12
        if selected and used + cost > max_chars:
            break
        selected.append({"role": role, "content": content})
        used += cost
    return list(reversed(selected))


def clear_conversation_cache(*, path: Path | None = None) -> bool:
    with _CACHE_LOCK:
        CONVERSATION_CACHE.clear()
    return save_conversation_cache(path=path)
