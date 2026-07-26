"""Telegram reminder delivery for due action items."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import ActionItem, RawEntry
from thoughtpins.store import get_session
from thoughtpins.utils import local_now


def _sent_path() -> Path:
    return config.resolve_path("./data/telegram_reminders_sent.json")


def _load_sent_ids() -> set[str]:
    path = _sent_path()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(item) for item in data}
    except Exception as exc:
        logger.warning("Could not load Telegram reminder sent log: {}", exc)
    return set()


def _save_sent_ids(sent_ids: set[str]) -> None:
    path = _sent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(sent_ids), indent=2), encoding="utf-8")


def find_due_telegram_reminders(
    session: Session,
    *,
    now: datetime | None = None,
    sent_ids: set[str] | None = None,
    limit: int = 20,
) -> list[tuple[ActionItem, RawEntry]]:
    """Return open due action items that originated from a Telegram chat."""
    now = now or local_now().replace(tzinfo=None)
    sent_ids = sent_ids if sent_ids is not None else _load_sent_ids()

    rows = (
        session.query(ActionItem, RawEntry)
        .join(RawEntry, ActionItem.raw_entry_id == RawEntry.id)
        .filter(
            ActionItem.status == "open",
            ActionItem.due_at.isnot(None),
            ActionItem.due_at <= now,
            RawEntry.telegram_chat_id.isnot(None),
            RawEntry.telegram_chat_id != "",
        )
        .order_by(ActionItem.due_at.asc())
        .limit(limit)
        .all()
    )
    return [(action, raw) for action, raw in rows if action.id not in sent_ids]


def format_reminder(action: ActionItem) -> str:
    due_text = action.due_at.strftime("%Y-%m-%d %H:%M") if action.due_at else "now"
    return f"Reminder\n{action.description}\nDue: {due_text}"


async def send_due_reminders(bot) -> int:
    sent_ids = _load_sent_ids()
    sent_count = 0
    session = get_session()
    try:
        for action, raw in find_due_telegram_reminders(session, sent_ids=sent_ids):
            await bot.send_message(chat_id=raw.telegram_chat_id, text=format_reminder(action))
            sent_ids.add(action.id)
            sent_count += 1
        if sent_count:
            _save_sent_ids(sent_ids)
    finally:
        session.close()
    return sent_count


async def reminder_loop(application) -> None:
    await asyncio.sleep(5)
    interval = max(30, int(config.TELEGRAM_REMINDER_POLL_SECONDS))
    while True:
        try:
            sent_count = await send_due_reminders(application.bot)
            if sent_count:
                logger.info("Sent {} Telegram reminder(s)", sent_count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Telegram reminder loop failed: {}", exc)
        await asyncio.sleep(interval)


async def start_reminder_loop(application) -> None:
    task = asyncio.create_task(reminder_loop(application), name="telegram-reminders")
    application.bot_data["telegram_reminder_task"] = task
    logger.info("Telegram reminder loop scheduled")


async def stop_reminder_loop(application) -> None:
    task = application.bot_data.pop("telegram_reminder_task", None)
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Telegram reminder loop stopped")
