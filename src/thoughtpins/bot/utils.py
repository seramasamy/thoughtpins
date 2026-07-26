"""Shared Telegram adapter utilities."""

from __future__ import annotations

from sqlalchemy.orm import Session

from thoughtpins.users import get_or_create_user_for_telegram


def chat_id(update) -> str:
    return str(update.message.chat_id)


def telegram_user_id(update, session: Session) -> str:
    return get_or_create_user_for_telegram(chat_id(update), session=session).id


def parse_limit(args: list[str], default: int, maximum: int) -> int:
    if not args:
        return default
    try:
        return max(1, min(maximum, int(args[0])))
    except ValueError:
        return default


def trim_for_telegram(text: str, max_chars: int = 3900) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 80].rstrip() + "\n\n... truncated. Ask for a more specific view."
