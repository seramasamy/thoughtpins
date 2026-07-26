"""Telegram help surface for optional commands and privacy controls."""

from __future__ import annotations

from thoughtpins.bot.disclosure import is_disclosure_mode
from thoughtpins.bot.personality import get_active_profile
from thoughtpins.bot.profile_commands import _emojis_enabled


async def cmd_help(update, context) -> None:
    """Render the command reference while keeping natural chat primary."""
    chat_id = str(update.message.chat_id)
    emoji_state = "ON" if _emojis_enabled(chat_id) else "OFF"
    confidential_state = "ON" if is_disclosure_mode(chat_id) else "OFF"

    message = (
        "*Thought Pins User Guide*\n\n"
        "Just send me a message about your day. I'll extract people, places, events, and memories automatically. "
        "You can also ask questions, chat casually, or use any command below.\n\n"
        "*How to journal:*\n"
        'Type naturally - no command needed. "Had lunch with Sarah, she\'s stressed about the product launch" '
        "becomes a searchable memory.\n\n"
        "*Natural requests:*\n"
        'You can write "search my memory for Sarah", "what did I write today", "show saved articles", '
        '"rate that five stars", or "run a health check". Say "undo that rating" to restore the previous importance. '
        "Destructive or private-data actions like undo, forget, export, backup, reindex, rename, and merge require "
        "a confirmation reply first.\n\n"
        "*Commands:*\n"
        "/ask <query> - Ask about your journal memories\n"
        "/askfull <query> - Force full-context audit for one question\n"
        "/context - Show memory context mode and prompt budget\n"
        "/context why <query> - Show smart-context diagnostics without memory text\n"
        "/person <name> - View a person's profile and history\n"
        "/place <name> - View a place's visit history\n"
        "/people - List people in the memory graph\n"
        "/places - List places in the memory graph\n"
        "/concepts - List concepts and other entities\n"
        "/read <url or text> - Save an article/document into reading memory\n"
        "/library - List saved articles and documents\n"
        "/source <id or title> - Inspect a saved source\n"
        "/memory - Compact memory health and retrieval view\n"
        "/today - Today's journal summary\n"
        "/week - Weekly digest\n"
        "/recent - Last 10 entries\n"
        "/search <query> - Search all memories\n"
        "/undo - Delete the most recent Telegram-saved item\n"
        "/report <type> - Generate a markdown report\n"
        "/graph - Interactive memory graph\n"
        "/status - System health, library size, last entry\n\n"
        "/doctor - Operational health check\n"
        "/audit - Memory quality and retrieval infrastructure audit\n"
        "/jobs - Ingestion queue and failed jobs\n"
        "/backup - Create and send a local backup zip\n"
        "/backup list - Show recent backups\n"
        "/backup smoke - Create and verify a scratch restore\n\n"
        "*Modes & Toggles (current state):*\n"
        f"/personality - Bot personality ({get_active_profile(chat_id).name})\n"
        "/founder - Local founder test mode setup/status\n"
        f"/confidential - Private-memory recall ({confidential_state})\n"
        f"/emojis - Emoji toggle ({emoji_state})\n\n"
        "*Private entries:*\n"
        "/private <text> - Store an encrypted private entry\n"
        'Or write "this is private" in your message.\n'
        "Private memories stay out of replies unless private recall is ON.\n\n"
        "*Private recall:*\n"
        "/confidential on - Use private memories (security code required)\n"
        "/confidential off - Keep private memories out (no code needed)\n"
        "When ON, private memories may inform replies.\n\n"
        "*Personality:*\n"
        "/personality - See available personalities\n"
        "/personality set <id> - Switch (friendly, clear, mirror)\n"
        "/personality derive - Auto-detect from your writing style\n\n"
        "*Other:*\n"
        "/correct <text> - Fix a previous entry\n"
        "/rename <old> -> <new> - Rename an entity and keep the old alias\n"
        "/merge <keep> <duplicate> - Merge duplicate entities\n"
        "/forget memory <id> - Remove one extracted memory\n"
        "/export - Export Obsidian vault\n"
        "/export data - Export account data as JSON\n"
        "/reindex - Rebuild search index\n"
        "/start - Quick actions menu"
    )
    await update.message.reply_text(message, parse_mode="Markdown")
