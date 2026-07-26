"""Natural language message handler -- classify and route."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from thoughtpins.bot.commands import (
    cmd_audit,
    cmd_backup,
    cmd_confidential,
    cmd_context,
    cmd_doctor,
    cmd_export,
    cmd_forget,
    cmd_help,
    cmd_library,
    cmd_mark_chat,
    cmd_memory,
    cmd_merge,
    cmd_recent,
    cmd_reindex,
    cmd_rename,
    cmd_report,
    cmd_save_last_chat,
    cmd_search,
    cmd_source,
    cmd_status,
    cmd_today,
    cmd_undo,
    handle_disclosure_code,
)
from thoughtpins.bot.natural_commands import (
    NaturalCommandRoute,
    clear_pending,
    confirmation_prompt,
    get_pending,
    interpret_confirmation,
    pop_pending,
    set_pending,
)
from thoughtpins.bot.utils import telegram_user_id, trim_for_telegram
from thoughtpins.chat.engine import execute_chat_message, route_chat_message
from thoughtpins.store import get_session

LEGACY_NATURAL_ACTIONS = {
    "audit",
    "backup",
    "confidential",
    "context_why",
    "doctor",
    "export",
    "forget",
    "merge",
    "reindex",
    "rename",
    "source",
}


async def handle_natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command text messages -- classify and route accordingly."""
    try:
        text = update.message.text.strip()

        # Keep pasted essays intact up to the backend request limit.
        if len(text) > 50_000:
            await update.message.reply_text(
                "That message is too long to save safely in one entry. "
                "Please send it as smaller sections under 50,000 characters."
            )
            return

        # Check if this is a disclosure code entry
        if await handle_disclosure_code(update, text):
            return

        # If a journal entry is already processing, route as follow-up
        from thoughtpins.bot.processing import handle_follow_up, is_processing

        chat_id = str(update.message.chat_id)
        if is_processing(chat_id):
            response = handle_follow_up(chat_id, text)
            if response:
                await update.message.reply_text(response)
            return

        pending = get_pending(chat_id)
        if pending:
            decision = interpret_confirmation(text, pending.route)
            if decision == "confirm":
                pending_command = pop_pending(chat_id)
                if pending_command:
                    await _execute_natural_command_route(update, context, pending_command.route)
                return
            if decision == "cancel":
                clear_pending(chat_id)
                await update.message.reply_text("Canceled.")
                return
            clear_pending(chat_id)

        route_decision = route_chat_message(text)
        if route_decision.natural_route:
            if route_decision.natural_route.action not in LEGACY_NATURAL_ACTIONS:
                await _execute_durable_chat_turn(update, text)
                return
            if route_decision.natural_route.needs_confirmation:
                set_pending(chat_id, route_decision.natural_route)
                await update.message.reply_text(confirmation_prompt(route_decision.natural_route))
                return
            await _execute_natural_command_route(update, context, route_decision.natural_route)
            return

        if route_decision.route_type == "command":
            await update.message.reply_text("Commands start with /. Try /help for available commands.")
            return

        await _execute_durable_chat_turn(update, text)

    except Exception as e:
        logger.error("Handler crashed: {}", e)
        try:
            await update.message.reply_text("Something went wrong. Try /status to check whether the message was saved.")
        except Exception:
            pass


async def _execute_durable_chat_turn(update: Update, text: str) -> None:
    """Run a plain Telegram message through the shared durable chat engine."""
    message = update.message
    chat_id = str(message.chat_id)
    chat = getattr(message, "chat", None)
    if chat and hasattr(chat, "send_action"):
        try:
            await chat.send_action("typing")
        except Exception:
            pass

    session = get_session()
    try:
        from thoughtpins.bot.disclosure import is_disclosure_mode

        user_id = telegram_user_id(update, session)
        from_user = getattr(message, "from_user", None)
        result = execute_chat_message(
            session,
            text,
            user_id=user_id,
            surface="telegram",
            conversation_id=chat_id,
            message_id=str(getattr(message, "message_id", "") or ""),
            author_user_id=str(getattr(from_user, "id", "") or ""),
            include_private=is_disclosure_mode(chat_id),
        )
    finally:
        session.close()

    await message.reply_text(trim_for_telegram(result.reply))


async def _execute_natural_command_route(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    route: NaturalCommandRoute,
) -> None:
    """Dispatch a routed natural-language command through the slash-command code."""
    context.args = list(route.args)
    action = route.action

    if action == "help":
        await cmd_help(update, context)
    elif action == "status":
        await cmd_status(update, context)
    elif action == "doctor":
        await cmd_doctor(update, context)
    elif action == "audit":
        await cmd_audit(update, context)
    elif action == "today":
        await cmd_today(update, context)
    elif action == "recent":
        await cmd_recent(update, context)
    elif action == "memory":
        await cmd_memory(update, context)
    elif action == "search":
        await cmd_search(update, context)
    elif action == "candidate_delete_search":
        await cmd_search(update, context)
        await update.message.reply_text(
            "Deletion needs an exact memory id. If one of those is the right item, "
            "reply `forget memory <id>` and I will ask for confirmation."
        )
    elif action == "library":
        await cmd_library(update, context)
    elif action == "source":
        await cmd_source(update, context)
    elif action == "context_why":
        await cmd_context(update, context)
    elif action == "report":
        await cmd_report(update, context)
    elif action == "undo":
        await cmd_undo(update, context)
    elif action == "mark_chat":
        await cmd_mark_chat(update, context)
    elif action == "save_last_chat":
        await cmd_save_last_chat(update, context)
    elif action == "backup":
        await cmd_backup(update, context)
    elif action == "export":
        await cmd_export(update, context)
    elif action == "reindex":
        await cmd_reindex(update, context)
    elif action == "forget":
        await cmd_forget(update, context)
    elif action == "rename":
        await cmd_rename(update, context)
    elif action == "merge":
        await cmd_merge(update, context)
    elif action == "confidential":
        await cmd_confidential(update, context)
    else:
        logger.warning("Unknown natural command route: {}", action)
        await update.message.reply_text("I understood that as a command, but I cannot route it yet.")


def _strip_route_prefix(text: str, msg_type: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()
    prefixes: tuple[str, ...] = ()
    if msg_type == "journal_entry":
        prefixes = ("save:", "journal:", "log:", "note to self:")
    elif msg_type == "conversation":
        prefixes = ("chat:", "just chat:", "talk:")
    elif msg_type in {"document_link", "document_text"}:
        prefixes = ("read:", "article:", "source:", "doc:", "document:")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return stripped
