"""Telegram personality controls and journal-processing presentation."""

from __future__ import annotations

from loguru import logger

from thoughtpins.bot.utils import telegram_user_id as _telegram_user_id
from thoughtpins.chat import conversation_state as _conversation_state
from thoughtpins.chat.capture_summary import format_capture_summary
from thoughtpins.chat.personality import (
    derive_personality_from_history,
    get_active_profile,
    is_founder_mode_available,
    load_personality,
    save_personality,
)
from thoughtpins.chat.style_memory import record_user_style_sample
from thoughtpins.config import config
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.store import get_session

CONVERSATION_CACHE = _conversation_state.CONVERSATION_CACHE


async def cmd_personality(update, context) -> None:
    """View, set, or derive bot personality."""
    chat_id = str(update.message.chat_id)
    args = context.args if context.args else []
    current = load_personality(chat_id)
    profile = get_active_profile(chat_id)

    if not args:
        # Show current personality and options
        lines = [
            f"Current personality: **{profile.name}**",
            f"_{profile.description}_",
            "",
            "Available personalities:",
        ]
        from thoughtpins.chat.personality import get_visible_personalities

        visible = get_visible_personalities(chat_id)
        for pid, p in visible.items():
            marker = " (active)" if pid == current else ""
            lines.append(f"  `{pid}` - {p.name}{marker}")
        lines.extend(
            [
                "",
                "Commands:",
                "  `/personality set <id>` - switch personality",
                "  `/personality derive` - auto-detect from your chat history",
                "  `/personality about` - explain the active personality's voice",
            ]
        )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    sub = args[0].lower()

    if sub == "set" and len(args) > 1:
        pid = args[1].lower()
        from thoughtpins.chat.personality import get_visible_personalities

        visible = get_visible_personalities(chat_id)
        if pid not in visible:
            available = ", ".join(f"`{k}`" for k in visible)
            await update.message.reply_text(
                f"Unknown personality. Available: {available}",
                parse_mode="Markdown",
            )
            return
        if save_personality(pid, chat_id=chat_id):
            p = visible[pid]
            # Clear conversation cache on personality change
            CONVERSATION_CACHE.pop(chat_id, None)
            await update.message.reply_text(
                f"Personality set to **{p.name}**.\n\n{p.description}\n\n"
                f"I'll be speaking in this voice from now on. Send me a message!",
                parse_mode="Markdown",
            )

    elif sub == "derive":
        await update.message.reply_text(
            "Analyzing your chat history to derive a matching personality... (this takes a moment)"
        )
        session = get_session()
        try:
            user_id = _telegram_user_id(update, session)
            voice = derive_personality_from_history(session=session, user_id=user_id)
        finally:
            session.close()
        if voice:
            save_personality("mirror", chat_id=chat_id)
            CONVERSATION_CACHE.pop(chat_id, None)
            await update.message.reply_text(
                "Mirror personality derived from your chat style and set as active.\n\n"
                "I analyzed your vocabulary, tone, humor, and communication patterns "
                "to create a voice that matches how you naturally communicate. "
                "Send me a message and see how it feels!"
            )
        else:
            await update.message.reply_text(
                "Not enough journal entries yet to derive a personality. "
                "I need at least 3 journal entries to analyze your style. "
                "Keep journaling and try again later!"
            )

    elif sub == "about":
        await update.message.reply_text(
            f"**{profile.name}**\n\nTone: {profile.tone}\n\nVoice instruction:\n_{profile.voice_instruction}_",
            parse_mode="Markdown",
        )

    else:
        await update.message.reply_text(
            "Usage:\n"
            "  `/personality` - show current and options\n"
            "  `/personality set <id>` - switch\n"
            "  `/personality derive` - auto-detect from history\n"
            "  `/personality about` - explain current voice",
        )


async def cmd_founder(update, context) -> None:
    """Enable or inspect local founder test mode."""
    chat_id = str(update.message.chat_id)
    args = context.args if context.args else []

    if not args:
        state = "available" if is_founder_mode_available() else "disabled"
        active = "ON" if load_personality(chat_id) == "founder" else "OFF"
        await update.message.reply_text(
            "Founder test mode\n"
            f"State: {state}\n"
            f"Active personality: {active}\n\n"
            "Setup for local Telegram testing:\n"
            "1. Set ENABLE_TELEGRAM_BOT=true and TELEGRAM_BOT_TOKEN.\n"
            "2. Set TELEGRAM_TEST_MODE=true for first-user local test allowlisting, or set TELEGRAM_ALLOWED_USER_IDS.\n"
            "3. Set ENABLE_FOUNDER_MODE=true.\n"
            "4. Run /founder on <FOUNDER_ACCESS_CODE>.\n\n"
            "Use /founder off to return to clear mode."
        )
        return

    sub = args[0].lower()
    if sub == "off":
        save_personality("clear", chat_id=chat_id)
        CONVERSATION_CACHE.pop(chat_id, None)
        await update.message.reply_text("Founder test mode OFF. Personality set to clear.")
        return

    if sub != "on":
        await update.message.reply_text("Usage: /founder, /founder on <code>, or /founder off")
        return

    if not is_founder_mode_available():
        await update.message.reply_text(
            "Founder test mode is disabled. Set ENABLE_FOUNDER_MODE=true in local development."
        )
        return

    expected = config.FOUNDER_ACCESS_CODE.strip()
    supplied = args[1].strip() if len(args) > 1 else ""
    if expected and supplied != expected:
        await update.message.reply_text("Founder code required or incorrect.")
        return

    save_personality("founder", chat_id=chat_id)
    CONVERSATION_CACHE.pop(chat_id, None)
    await update.message.reply_text(
        "Founder test mode ON. Personality set to founder.\n"
        "This does not enable confidential/private entries; use /confidential on for that."
    )


# -- Journal entry processor --------------------------

# -- Emoji toggle -------------------------------------
_EMOJI_STATE: dict[str, bool] = {}  # chat_id -> emojis enabled (default True)


def _emojis_enabled(chat_id: str) -> bool:
    return _EMOJI_STATE.get(chat_id, True)


def _e(emoji: str, chat_id: str) -> str:
    """Return emoji only if enabled for this chat."""
    return emoji if _emojis_enabled(chat_id) else ""


# -- Welcome-back tracking ----------------------------
_LAST_ACTIVITY: dict[str, float] = {}  # chat_id -> timestamp


def _welcome_back_msg(chat_id: str) -> str | None:
    """Return a welcome-back message if user was away > 6 hours, or None."""
    import time

    now = time.time()
    last = _LAST_ACTIVITY.get(chat_id, 0)
    _LAST_ACTIVITY[chat_id] = now
    gap_hours = (now - last) / 3600 if last else 999

    if gap_hours < 6:
        return None
    if gap_hours < 24:
        return f"Welcome back. It has been {int(gap_hours)}h since your last entry."
    days = int(gap_hours / 24)
    return f"Welcome back. It has been {days} days. Your journal is ready."


# -- Emoji toggle command -----------------------------


async def cmd_emojis(update, context) -> None:
    """Toggle emoji usage on/off."""
    chat_id = str(update.message.chat_id)
    args = context.args if context.args else []

    if not args:
        state = "ON" if _emojis_enabled(chat_id) else "OFF"
        await update.message.reply_text(f"Emojis are currently {state}.\nUse `/emojis on` or `/emojis off`")
        return

    sub = args[0].lower()
    if sub == "on":
        _EMOJI_STATE[chat_id] = True
        await update.message.reply_text("Emojis ON. I'll use them in my messages.")
    elif sub == "off":
        _EMOJI_STATE[chat_id] = False
        await update.message.reply_text("Emojis OFF. Clean text from now on.")
    else:
        await update.message.reply_text("Use `/emojis on` or `/emojis off`")


# -- Journal entry processor (with status updates) ----


_format_capture_summary = format_capture_summary


def _format_journal_stored_reply(result: dict, elapsed: float) -> str:
    summary = _format_capture_summary(result.get("stats", {}))
    return f"Saved.\nProcessed in {max(0, int(elapsed))}s.\nCaptured: {summary}."


async def _process_and_reply(update, text: str) -> None:
    """Process a journal entry with ETA status updates and welcome-back."""
    import asyncio
    import time

    from thoughtpins.bot.processing import finish_processing, is_processing, start_processing

    chat_id = str(update.message.chat_id)

    # If already processing, this is a follow-up
    if is_processing(chat_id):
        from thoughtpins.bot.processing import handle_follow_up

        response = handle_follow_up(chat_id, text)
        if response:
            await update.message.reply_text(response)
        return

    # Welcome-back check
    wb = _welcome_back_msg(chat_id)
    if wb:
        await update.message.reply_text(wb)

    # Track processing state for ETA
    proc_state = start_processing(chat_id, text)
    start_time = time.time()

    # Send initial status with ETA
    status_msg = await update.message.reply_text(
        f"Processing your entry ({len(text)} chars)\nETA: {proc_state.eta_text()}"
    )

    # Background status updater every 10 seconds
    stop_status = False

    async def status_updater():
        while not stop_status:
            await asyncio.sleep(10)
            if not stop_status and is_processing(chat_id):
                pct = proc_state.progress_pct
                bar = "".join(["#" if i < pct // 10 else "." for i in range(10)])
                try:
                    await status_msg.edit_text(f"Processing your entry\n[{bar}] {pct}%\nETA: {proc_state.eta_text()}")
                except Exception as exc:
                    logger.debug("Progress message update skipped: {}", type(exc).__name__)

    updater_task = asyncio.create_task(status_updater())

    session = get_session()
    try:
        user_id = _telegram_user_id(update, session)
        record_user_style_sample(session, user_id=user_id, text=text)
        result = process_message(
            session,
            text,
            user_id=user_id,
            telegram_message_id=str(getattr(update.message, "message_id", "") or ""),
            telegram_chat_id=chat_id,
            author_user_id=str(getattr(getattr(update.message, "from_user", None), "id", "") or ""),
        )

        elapsed = time.time() - start_time
        stop_status = True
        updater_task.cancel()
        finish_processing(chat_id, elapsed, len(text))

        if result["type"] == "journal_stored":
            await status_msg.edit_text(_format_journal_stored_reply(result, elapsed))
            # If follow-ups were appended, note it
            if proc_state.follow_ups:
                await update.message.reply_text(
                    f"{len(proc_state.follow_ups)} follow-up message(s) were merged into this entry."
                )
        elif result["type"] == "duplicate":
            await status_msg.edit_text("Already saved recently. I skipped the duplicate.")
        elif result["type"] == "queued":
            await status_msg.edit_text(
                "Saved. The AI service is temporarily unavailable, so extraction is queued for retry."
            )
        elif result["type"] == "private_stored":
            await status_msg.edit_text(
                "Saved privately. It is excluded from AI queries unless confidential mode is enabled."
            )
        elif result["type"] == "error":
            await status_msg.edit_text(
                "Saved the raw entry, but AI extraction failed. Use /status or /doctor for details."
            )
        else:
            await status_msg.edit_text("Saved.")
    except Exception as exc:
        elapsed = time.time() - start_time
        stop_status = True
        updater_task.cancel()
        finish_processing(chat_id, elapsed, len(text))
        logger.error("Processing failed: {}", exc)
        await status_msg.edit_text("Processing failed before I could confirm the save. Use /status or try again.")
    finally:
        session.close()
