"""Telegram memory overview, digest, and search commands."""

from __future__ import annotations

from sqlalchemy import func

from thoughtpins.bot.utils import telegram_user_id, trim_for_telegram
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import Memory, RawEntry
from thoughtpins.library import list_documents
from thoughtpins.memory.search import search
from thoughtpins.memory.store import MemoryStore
from thoughtpins.reports.generator import ReportGenerator
from thoughtpins.store import get_session
from thoughtpins.utils import local_today


def _scope_user(query, model, user_id: str | None):
    if user_id:
        return query.filter(model.user_id == user_id)
    return query


def _memory_query(session, include_private: bool, user_id: str | None):
    query = _scope_user(session.query(Memory), Memory, user_id).filter(Memory.valid_to.is_(None))
    if not include_private:
        query = query.join(RawEntry).filter(RawEntry.is_private == False)
    return query


async def cmd_today(update, context) -> None:
    """Show today's journal summary."""
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        today = local_today()
        store = MemoryStore(session, user_id=user_id)
        entries = store.get_entries_by_date(today)

        if not entries:
            await update.message.reply_text(f"No entries for {today.isoformat()}.")
            return

        lines = [f"Today: {today.isoformat()}", f"Entries: {len(entries)}\n"]
        for entry in entries:
            raw_text = maybe_decrypt_text(entry.raw_text)
            lines.append(f"- {raw_text[:200]}")
            if len(raw_text) > 200:
                lines.append("  ...")

        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()


async def cmd_week(update, context) -> None:
    """Weekly digest."""
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        gen = ReportGenerator(session, user_id=user_id)
        md = gen.generate_markdown("weekly")
        await update.message.reply_text(trim_for_telegram(md))
    finally:
        session.close()


async def cmd_recent(update, context) -> None:
    """Last 10 entries."""
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        store = MemoryStore(session, user_id=user_id)
        entries = store.get_recent_entries(limit=10)
        if not entries:
            await update.message.reply_text("No entries yet.")
            return

        lines = ["Recent entries:\n"]
        for entry in entries:
            raw_text = maybe_decrypt_text(entry.raw_text)
            lines.append(f"[{entry.local_date}] {raw_text[:150]}")
            if len(raw_text) > 150:
                lines.append("  ...")

        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()


async def cmd_search(update, context) -> None:
    """Semantic + structured search."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return

    session = get_session()
    try:
        from thoughtpins.bot.disclosure import is_disclosure_mode

        user_id = telegram_user_id(update, session)
        results = search(
            query,
            session=session,
            user_id=user_id,
            include_private=is_disclosure_mode(str(update.message.chat_id)),
            limit=10,
        )
        if not results:
            await update.message.reply_text("No results found.")
            return

        lines = [f"Search: {query}\n"]
        for i, result in enumerate(results, 1):
            source = f" source={result.source_title}" if result.source_title else ""
            lines.append(f"{i}. [{result.local_date}] [{result.memory_type}]{source} {result.text[:200]}")
            lines.append(f"   memory:`{result.memory_id}`")

        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()


async def cmd_memory(update, context) -> None:
    """Compact memory health and retrieval view."""
    args = context.args or []
    sub = args[0].lower() if args else "summary"
    if sub in {"search", "find"}:
        context.args = args[1:]
        await cmd_search(update, context)
        return
    if sub in {"recent", "entries"}:
        await cmd_recent(update, context)
        return

    session = get_session()
    try:
        from thoughtpins.bot.disclosure import is_disclosure_mode

        user_id = telegram_user_id(update, session)
        include_private = is_disclosure_mode(str(update.message.chat_id))
        store = MemoryStore(session, user_id=user_id)
        stats = store.get_stats()
        active_memory_count = (
            _memory_query(session, include_private, user_id).with_entities(func.count(Memory.id)).scalar() or 0
        )
        memory_types = (
            _memory_query(session, include_private, user_id)
            .with_entities(Memory.memory_type, func.count(Memory.id))
            .group_by(Memory.memory_type)
            .order_by(func.count(Memory.id).desc())
            .limit(8)
            .all()
        )
        recent_memories = (
            _memory_query(session, include_private, user_id)
            .order_by(Memory.local_date.desc(), Memory.created_at_utc.desc())
            .limit(5)
            .all()
        )
        docs = list_documents(session, user_id, limit=5)
        lines = [
            "Memory status",
            f"Entries: {stats.get('raw_entries', 0)}",
            f"Active memories: {active_memory_count}",
            f"Entities: {stats.get('entities', 0)}",
            f"Sources: {stats.get('sources', 0)}",
            f"Confidential included: {include_private}",
        ]
        if memory_types:
            lines.append("")
            lines.append("Top memory types:")
            for kind, count in memory_types:
                lines.append(f"- {kind}: {count}")
        if recent_memories:
            lines.append("")
            lines.append("Recent memories:")
            for memory in recent_memories:
                lines.append(f"- [{memory.local_date}] {memory.memory_type} {memory.id[:10]}: {memory.text[:140]}")
        if docs:
            lines.append("")
            lines.append("Recent sources:")
            for doc in docs:
                lines.append(f"- {doc.title} ({doc.status}, id={doc.id[:10]})")
        lines.extend(
            [
                "",
                "Use /memory search <query>, /context why <query>, or /reindex.",
            ]
        )
        await update.message.reply_text(trim_for_telegram("\n".join(lines)))
    finally:
        session.close()
