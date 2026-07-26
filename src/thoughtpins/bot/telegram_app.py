"""Telegram bot application entry point."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from thoughtpins.bot.auth import check_rate_limit, is_user_allowed
from thoughtpins.bot.commands import (
    cmd_ask,
    cmd_askfull,
    cmd_audit,
    cmd_backup,
    cmd_concepts,
    cmd_confidential,
    cmd_context,
    cmd_correct,
    cmd_disclosure,
    cmd_doctor,
    cmd_emojis,
    cmd_export,
    cmd_forget,
    cmd_founder,
    cmd_graph,
    cmd_help,
    cmd_jobs,
    cmd_library,
    cmd_log,
    cmd_memory,
    cmd_merge,
    cmd_people,
    cmd_person,
    cmd_personality,
    cmd_place,
    cmd_places,
    cmd_private,
    cmd_read,
    cmd_recent,
    cmd_reindex,
    cmd_rename,
    cmd_report,
    cmd_search,
    cmd_source,
    cmd_start,
    cmd_status,
    cmd_today,
    cmd_undo,
    cmd_week,
    handle_callback,
)
from thoughtpins.bot.handlers import handle_natural_language
from thoughtpins.bot.photos import handle_document_message, handle_photo_message
from thoughtpins.bot.voice import handle_voice_message
from thoughtpins.config import config
from thoughtpins.logging_config import setup_logging
from thoughtpins.privacy import fingerprint_identifier
from thoughtpins.store import init_db
from thoughtpins.tenancy import tenant_context
from thoughtpins.users import get_or_create_user_for_telegram


def build_application() -> Application:
    """Construct the Telegram bot application with all handlers."""
    token = config.TELEGRAM_BOT_TOKEN
    problems = config.validate_telegram_startup()
    if problems:
        raise RuntimeError("Telegram startup validation failed: " + "; ".join(problems))

    app = Application.builder().token(token).post_init(_post_init).post_shutdown(_post_shutdown).build()

    # Command handlers
    app.add_handler(CommandHandler("start", auth_wrapper(cmd_start)))
    app.add_handler(CommandHandler("help", auth_wrapper(cmd_help)))
    app.add_handler(CommandHandler("log", auth_wrapper(cmd_log)))
    app.add_handler(CommandHandler("private", auth_wrapper(cmd_private)))
    app.add_handler(CommandHandler("ask", auth_wrapper(cmd_ask)))
    app.add_handler(CommandHandler("askfull", auth_wrapper(cmd_askfull)))
    app.add_handler(CommandHandler("context", auth_wrapper(cmd_context)))
    app.add_handler(CommandHandler("person", auth_wrapper(cmd_person)))
    app.add_handler(CommandHandler("place", auth_wrapper(cmd_place)))
    app.add_handler(CommandHandler("people", auth_wrapper(cmd_people)))
    app.add_handler(CommandHandler("places", auth_wrapper(cmd_places)))
    app.add_handler(CommandHandler("concepts", auth_wrapper(cmd_concepts)))
    app.add_handler(CommandHandler("read", auth_wrapper(cmd_read)))
    app.add_handler(CommandHandler("article", auth_wrapper(cmd_read)))
    app.add_handler(CommandHandler("library", auth_wrapper(cmd_library)))
    app.add_handler(CommandHandler("source", auth_wrapper(cmd_source)))
    app.add_handler(CommandHandler("memory", auth_wrapper(cmd_memory)))
    app.add_handler(CommandHandler("today", auth_wrapper(cmd_today)))
    app.add_handler(CommandHandler("week", auth_wrapper(cmd_week)))
    app.add_handler(CommandHandler("recent", auth_wrapper(cmd_recent)))
    app.add_handler(CommandHandler("report", auth_wrapper(cmd_report)))
    app.add_handler(CommandHandler("pdf", auth_wrapper(cmd_report)))
    app.add_handler(CommandHandler("search", auth_wrapper(cmd_search)))
    app.add_handler(CommandHandler("graph", auth_wrapper(cmd_graph)))
    app.add_handler(CommandHandler("status", auth_wrapper(cmd_status)))
    app.add_handler(CommandHandler("doctor", auth_wrapper(cmd_doctor)))
    app.add_handler(CommandHandler("audit", auth_wrapper(cmd_audit)))
    app.add_handler(CommandHandler("backup", auth_wrapper(cmd_backup)))
    app.add_handler(CommandHandler("jobs", auth_wrapper(cmd_jobs)))
    app.add_handler(CommandHandler("correct", auth_wrapper(cmd_correct)))
    app.add_handler(CommandHandler("rename", auth_wrapper(cmd_rename)))
    app.add_handler(CommandHandler("forget", auth_wrapper(cmd_forget)))
    app.add_handler(CommandHandler("undo", auth_wrapper(cmd_undo)))
    app.add_handler(CommandHandler("export", auth_wrapper(cmd_export)))
    app.add_handler(CommandHandler("reindex", auth_wrapper(cmd_reindex)))
    app.add_handler(CommandHandler("personality", auth_wrapper(cmd_personality)))
    app.add_handler(CommandHandler("founder", auth_wrapper(cmd_founder)))
    app.add_handler(CommandHandler("disclosure", auth_wrapper(cmd_disclosure)))
    app.add_handler(CommandHandler("confidential", auth_wrapper(cmd_confidential)))
    app.add_handler(CommandHandler("emojis", auth_wrapper(cmd_emojis)))
    app.add_handler(CommandHandler("merge", auth_wrapper(cmd_merge)))
    # Voice message handler
    app.add_handler(MessageHandler(filters.VOICE, auth_wrapper(handle_voice_message)))

    # Photo/image handler (OCR screenshots, handwriting, documents)
    app.add_handler(MessageHandler(filters.PHOTO, auth_wrapper(handle_photo_message)))

    # Document handler (PDF, etc. - future)
    app.add_handler(MessageHandler(filters.Document.ALL, auth_wrapper(handle_document_message)))

    # Inline keyboard callback handler
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Natural language handler (must be last)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            auth_wrapper(handle_natural_language),
        )
    )

    return app


async def _post_init(application: Application) -> None:
    from thoughtpins.bot.reminders import start_reminder_loop

    await start_reminder_loop(application)


async def _post_shutdown(application: Application) -> None:
    from thoughtpins.bot.reminders import stop_reminder_loop

    await stop_reminder_loop(application)


def auth_wrapper(handler_func):
    """Decorator to enforce allowlist auth on all handlers."""

    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.from_user:
            return
        user_id = update.message.from_user.id
        if not is_user_allowed(user_id):
            await update.message.reply_text("Access denied. You are not in the allowed users list.")
            logger.warning("Blocked message from user_hash={}", fingerprint_identifier(user_id))
            return
        if not check_rate_limit(user_id):
            await update.message.reply_text("Please slow down. You're sending messages too quickly.")
            return
        session = None
        tenant_user_id = None
        try:
            from thoughtpins.store import get_session

            session = get_session()
            tenant_user_id = get_or_create_user_for_telegram(str(update.message.chat_id), session=session).id
        finally:
            if session is not None:
                session.close()
        with tenant_context(tenant_user_id):
            await handler_func(update, context)

    return wrapped


def main():
    setup_logging()
    logger.info("Initializing database...")
    init_db()

    logger.info("Starting Telegram bot...")
    app = build_application()
    logger.info("Bot polling started. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
