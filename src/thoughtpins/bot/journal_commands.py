"""Telegram commands for journal maintenance, context inspection, and export."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.bot.personality import get_active_profile
from thoughtpins.bot.profile_commands import _process_and_reply
from thoughtpins.bot.style_memory import CHAT_SOURCE, CHAT_STATUS, build_user_style_prompt
from thoughtpins.bot.utils import chat_id as _chat_id
from thoughtpins.bot.utils import telegram_user_id as _telegram_user_id
from thoughtpins.chat.memory_answer import answer_with_llm as _answer_with_llm
from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.data_lifecycle import export_user_data
from thoughtpins.db import Memory, RawEntry
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.llm.client import get_llm_client
from thoughtpins.memory.context_package import (
    _format_context_diagnostics,
    build_memory_context_package,
    describe_memory_context_package,
)
from thoughtpins.memory.context_scope import scope_user as _scope_user
from thoughtpins.obsidian.exporter import ObsidianExporter
from thoughtpins.reports.generator import ReportGenerator
from thoughtpins.reports.graph_visuals import export_all_graphs
from thoughtpins.store import get_session
from thoughtpins.utils import local_today
from thoughtpins.voice_archive import delete_voice_assets_for_entry


def answer_with_llm(
    query: str,
    session,
    personality_profile=None,
    include_private: bool = False,
    user_id: str | None = None,
    force_full_context: bool = False,
) -> str:
    """Apply Telegram's response limit to the shared answer engine."""

    return _answer_with_llm(
        query,
        session,
        personality_profile=personality_profile,
        include_private=include_private,
        user_id=user_id,
        force_full_context=force_full_context,
        max_response_chars=3900,
        _context_builder_override=build_memory_context_package,
        _style_builder_override=build_user_style_prompt,
        _llm_factory_override=get_llm_client,
    )


async def cmd_log(update, context) -> None:
    """Force a journal entry from /log command."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /log <your journal entry>")
        return

    await _process_and_reply(update, text)


async def cmd_private(update, context) -> None:
    """Store an encrypted private entry."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /private <sensitive entry>")
        return

    from thoughtpins.store import get_session as gs

    session = gs()
    try:
        result = process_message(
            session,
            text,
            telegram_message_id=str(update.message.message_id),
            telegram_chat_id=str(update.message.chat_id),
            author_user_id=str(update.message.from_user.id),
            is_private=True,
        )
        if result.get("type") == "private_stored":
            await update.message.reply_text("Private entry stored (encrypted, not processed by LLM).")
        else:
            await update.message.reply_text("Private entry stored.")
    finally:
        session.close()


async def _answer_question_command(update, context, *, force_full_context: bool = False) -> None:
    """Answer a question using full-context LLM synthesis of the entire database."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        command = "/askfull" if force_full_context else "/ask"
        await update.message.reply_text(f"Usage: {command} <your question>")
        return

    if getattr(update.message, "chat", None):
        await update.message.chat.send_action("typing")

    # Respect disclosure mode
    from thoughtpins.bot.disclosure import is_disclosure_mode

    chat_id = str(update.message.chat_id)
    include_private = is_disclosure_mode(chat_id)

    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        profile = get_active_profile(chat_id)
        answer = answer_with_llm(
            query,
            session,
            profile,
            include_private=include_private,
            user_id=user_id,
            force_full_context=force_full_context,
        )
        if include_private:
            answer = "[Confidential mode - including private entries]\n\n" + answer
        if force_full_context:
            answer = "[Full context audit]\n\n" + answer
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error("ask failed: {}", e)
        await update.message.reply_text("I had trouble answering that. Try again or check if the database has entries.")
    finally:
        session.close()


async def cmd_ask(update, context) -> None:
    """Answer a question using the configured memory context mode."""
    await _answer_question_command(update, context, force_full_context=False)


async def cmd_askfull(update, context) -> None:
    """Answer a question with the exhaustive context package for one request."""
    await _answer_question_command(update, context, force_full_context=True)


async def cmd_context(update, context) -> None:
    """Show current memory context mode and command options."""
    args = context.args or []
    if args and args[0].lower() in {"why", "debug", "diagnose", "full"}:
        force_full = args[0].lower() == "full"
        question = " ".join(args[1:]).strip()
        if not question:
            usage = "/context full <question>" if force_full else "/context why <question>"
            await update.message.reply_text(f"Usage: {usage}")
            return

        from thoughtpins.bot.disclosure import is_disclosure_mode

        chat_id = str(update.message.chat_id)
        session = get_session()
        try:
            user_id = _telegram_user_id(update, session)
            info = describe_memory_context_package(
                question,
                session,
                chat_id=chat_id,
                include_private=is_disclosure_mode(chat_id),
                user_id=user_id,
                force_full=force_full,
            )
            await update.message.reply_text(_format_context_diagnostics(info))
        finally:
            session.close()
        return

    mode = config.MEMORY_CONTEXT_MODE
    full_threshold = config.MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS
    max_chars = config.MEMORY_CONTEXT_MAX_CHARS
    lines = [
        f"Context mode: {mode}",
        f"Prompt budget: {max_chars:,} chars",
        f"Small-library full inline threshold: {full_threshold:,} chars",
        "",
        "/ask uses the configured context mode.",
        "/askfull forces the exhaustive context package for one question.",
        "/context why <question> shows why smart mode attached specific sections.",
        "/context full <question> previews full-context diagnostics.",
        "Casual chat uses the configured mode plus retained recent chat history.",
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_report(update, context) -> None:
    """Generate a markdown report."""
    query = " ".join(context.args) if context.args else "weekly"
    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        gen = ReportGenerator(session, user_id=user_id)
        parts = query.split(maxsplit=1)
        qtype = parts[0].lower()
        qtext = parts[1] if len(parts) > 1 else ""
        md = gen.generate_markdown(qtype, qtext)

        reports_dir = config.reports_path()
        reports_dir.mkdir(parents=True, exist_ok=True)
        safe_name = query.replace(" ", "_")[:60]
        md_path = reports_dir / f"{safe_name}_{local_today().isoformat()}.md"
        md_path.write_text(md, encoding="utf-8")

        # Send file
        with open(md_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=md_path.name,
                caption=f"Report: {query}",
            )
    finally:
        session.close()


async def cmd_undo(update, context) -> None:
    """Delete the most recent Telegram-saved entry/source/correction from this chat."""
    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        chat_id = str(update.message.chat_id)
        entry = (
            _scope_user(session.query(RawEntry), RawEntry, user_id)
            .filter(RawEntry.telegram_chat_id == chat_id)
            .order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
            .first()
        )
        if not entry:
            await update.message.reply_text("Nothing to undo for this Telegram chat.")
            return

        memory_ids = [memory.id for memory in entry.memories]
        superseded_ids = [memory.supersedes_memory_id for memory in entry.memories if memory.supersedes_memory_id]
        restored_memories: list[Memory] = []
        if superseded_ids:
            restored_memories = (
                _scope_user(session.query(Memory), Memory, user_id).filter(Memory.id.in_(superseded_ids)).all()
            )
            for memory in restored_memories:
                memory.valid_to = None

        preview = maybe_decrypt_text(entry.raw_text)[:180]
        entry_id = entry.id
        delete_voice_assets_for_entry(session, user_id=user_id, raw_entry_id=entry.id)
        session.delete(entry)
        session.commit()

        try:
            from thoughtpins.memory.vector_store import get_vector_store

            vector_store = get_vector_store()
            if memory_ids:
                vector_store.delete(memory_ids)
            if restored_memories:
                vector_store.add(
                    [memory.id for memory in restored_memories],
                    [memory.text for memory in restored_memories],
                    [{"user_id": memory.user_id} for memory in restored_memories],
                )
        except Exception as exc:
            logger.warning("Undo vector refresh failed for entry {}: {}", entry_id, exc)

        restored = f"\nRestored {len(restored_memories)} superseded memory record(s)." if restored_memories else ""
        await update.message.reply_text(f"Undid latest saved item {entry_id[:10]}.\nPreview: {preview}{restored}")
    finally:
        session.close()


async def cmd_mark_chat(update, context) -> None:
    """Demote the latest structured Telegram save into plain chat memory."""
    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        chat_id = str(update.message.chat_id)
        entry = (
            _scope_user(session.query(RawEntry), RawEntry, user_id)
            .filter(
                RawEntry.telegram_chat_id == chat_id,
                RawEntry.source != CHAT_SOURCE,
                RawEntry.processed_status != CHAT_STATUS,
            )
            .order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
            .first()
        )
        if not entry:
            await update.message.reply_text("I could not find a recent journal save to mark as chat.")
            return

        preview = maybe_decrypt_text(entry.raw_text)[:180]
        entry_id = entry.id
        memory_ids, restored_memories = _demote_entry_to_chat(session, entry, user_id=user_id)
        session.commit()
        _refresh_vectors_after_removed_memories(memory_ids, restored_memories, entry_id)

        restored = f" Restored {len(restored_memories)} older memory record(s)." if restored_memories else ""
        await update.message.reply_text(
            f"Marked the latest saved entry as chat memory, not journal memory.\nPreview: {preview}{restored}"
        )
    finally:
        session.close()


async def cmd_save_last_chat(update, context) -> None:
    """Promote the latest chat-memory turn into a structured journal entry."""
    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        chat_id = str(update.message.chat_id)
        entry = (
            _scope_user(session.query(RawEntry), RawEntry, user_id)
            .filter(
                RawEntry.telegram_chat_id == chat_id,
                RawEntry.source == CHAT_SOURCE,
                RawEntry.processed_status == CHAT_STATUS,
            )
            .order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
            .first()
        )
        if not entry:
            await update.message.reply_text("I could not find a recent chat message to save as a journal entry.")
            return
        text = maybe_decrypt_text(entry.raw_text)
    finally:
        session.close()

    await _process_and_reply(update, text)


def _demote_entry_to_chat(
    session: Session,
    entry: RawEntry,
    *,
    user_id: str,
) -> tuple[list[str], list[Memory]]:
    memory_ids = [memory.id for memory in entry.memories]
    superseded_ids = [memory.supersedes_memory_id for memory in entry.memories if memory.supersedes_memory_id]
    restored_memories: list[Memory] = []
    if superseded_ids:
        restored_memories = (
            _scope_user(session.query(Memory), Memory, user_id).filter(Memory.id.in_(superseded_ids)).all()
        )
        for memory in restored_memories:
            memory.valid_to = None

    for attr in (
        "entity_mentions",
        "relationships_ref",
        "action_items",
        "expenses",
        "document_sources",
        "events",
        "memories",
    ):
        for item in list(getattr(entry, attr, []) or []):
            session.delete(item)

    entry.source = CHAT_SOURCE
    entry.processed_status = CHAT_STATUS
    entry.sensitivity = "personal"
    entry.processing_error = None
    return memory_ids, restored_memories


def _refresh_vectors_after_removed_memories(
    memory_ids: list[str],
    restored_memories: list[Memory],
    entry_id: str,
) -> None:
    try:
        from thoughtpins.memory.vector_store import get_vector_store

        vector_store = get_vector_store()
        if memory_ids:
            vector_store.delete(memory_ids)
        if restored_memories:
            vector_store.add(
                [memory.id for memory in restored_memories],
                [memory.text for memory in restored_memories],
                [{"user_id": memory.user_id} for memory in restored_memories],
            )
    except Exception as exc:
        logger.warning("Vector refresh failed after entry rewrite {}: {}", entry_id, exc)


async def cmd_graph(update, context) -> None:
    """Generate and send graph HTML."""
    await update.message.reply_text("Generating memory graph...")
    try:
        session = get_session()
        try:
            user_id = _telegram_user_id(update, session)
        finally:
            session.close()
        results = export_all_graphs(user_id=user_id)
        html_path = results.get("html")
        if html_path and html_path.exists():
            with open(html_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename="memory_graph.html",
                    caption="Interactive memory graph (open in browser).",
                )
        else:
            await update.message.reply_text("Graph generation failed. Check logs.")
    except Exception as e:
        await update.message.reply_text(f"Graph generation failed: {e}")


async def cmd_correct(update, context) -> None:
    """Correction workflow -- actually fixes entities/memories based on correction text."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "Usage: /correct <correction>\n\n"
            "Examples:\n"
            "  /correct Steve's kid is Geoff, not Jeff\n"
            "  /correct The Green Bar is actually The Greene Bar\n"
            "  /correct Andrew went to Maui, not Hawaii"
        )
        return

    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        from thoughtpins.memory.corrections import store_and_apply_correction

        result = store_and_apply_correction(
            session,
            text,
            user_id=user_id,
            source="telegram",
            telegram_message_id=str(update.message.message_id),
            telegram_chat_id=str(update.message.chat_id),
            author_user_id=str(update.message.from_user.id),
        )
        fixes = result.fixes

        if fixes:
            lines = ["Correction applied:"]
            for f in fixes:
                lines.append(f"  - {f}")
            await update.message.reply_text("\n".join(lines))
        else:
            await update.message.reply_text("Correction stored. No matching entities found to update automatically.")
    finally:
        session.close()


def _apply_correction(session, text: str, user_id: str | None = None) -> list[str]:
    """Try to parse a correction and update matching entities/memories."""
    if not user_id:
        return []
    from thoughtpins.memory.corrections import store_and_apply_correction

    result = store_and_apply_correction(session, text, user_id=user_id, source="manual")
    return result.fixes


# -- Entity merge command ------------------------------


async def cmd_export(update, context) -> None:
    """Export Obsidian vault or account data."""
    args = [arg.lower() for arg in (context.args or [])]
    if args and args[0] in {"data", "json", "account"}:
        await update.message.reply_text("Preparing account data export...")
        session = get_session()
        try:
            user_id = _telegram_user_id(update, session)
            payload = export_user_data(session, user_id)
        finally:
            session.close()
        import json

        out_dir = config.resolve_path(".tmp/telegram-exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"thoughtpins_account_export_{_chat_id(update)}.json"
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with open(out_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="thoughtpins_account_export.json",
                caption="Account data export. Store this somewhere safe.",
            )
        return

    await update.message.reply_text("Exporting Obsidian vault...")
    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        exporter = ObsidianExporter(session, user_id=user_id)
        with_defaults = any(
            arg in {"defaults", "with-defaults", "obsidian-defaults", "--obsidian-defaults"} for arg in args
        )
        stats = exporter.export_all(obsidian_defaults=with_defaults)
        lines = ["Obsidian export complete:\n"]
        for k, v in stats.items():
            lines.append(f"{k}: {v}")
        lines.append(f"\nVault: {config.vault_path()}")
        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()


async def cmd_reindex(update, context) -> None:
    """Rebuild vector index."""
    await update.message.reply_text("Rebuilding index...")
    from thoughtpins.memory.reindex import reindex_vectors

    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        stats = reindex_vectors(session=session, user_id=user_id, include_private=True, reset=True)
        await update.message.reply_text(
            f"Index rebuilt.\nScanned: {stats.scanned}\nIndexed: {stats.indexed}\nBatches: {stats.batches}"
        )
    finally:
        session.close()
