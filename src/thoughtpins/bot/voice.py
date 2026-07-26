"""Founder Telegram voice adapter backed by the shared product upload path."""

from __future__ import annotations

import asyncio

from loguru import logger

from thoughtpins.audit import record_audit_event
from thoughtpins.bot.commands import _e
from thoughtpins.bot.utils import telegram_user_id
from thoughtpins.media import transcribe_audio
from thoughtpins.store import get_session
from thoughtpins.uploads import UploadIngestOutcome, ingest_upload


async def handle_voice_message(update, context) -> None:
    """Download one Telegram voice note, transcribe it, and apply normal retention rules."""

    chat_id = str(update.message.chat_id)
    e = lambda emoji: _e(emoji, chat_id)
    voice = update.message.voice
    status_msg = await update.message.reply_text(
        f"{e('Microphone')} Voice note received ({voice.duration}s). Transcribing..."
    )

    try:
        voice_file = await context.bot.get_file(voice.file_id)
        ogg_bytes = bytes(await voice_file.download_as_bytearray())
        outcome = await asyncio.to_thread(
            _ingest_voice,
            update,
            ogg_bytes,
        )
        if outcome.status == "needs_text":
            await status_msg.edit_text(
                f"{e('Warning')} I could not hear enough speech to save this note. Try again or type it instead."
            )
            return
        retention = (
            "The encrypted recording is in your Personal voice archive."
            if outcome.voice_asset_id
            else "The recording was discarded after transcription."
        )
        await status_msg.edit_text(f"{e('Microphone')} Saved voice note. {retention}")
    except Exception as exc:
        logger.error("Voice processing failed: {}", type(exc).__name__)
        await status_msg.edit_text(f"{e('Warning')} Voice processing failed. You can type your entry instead.")


def _ingest_voice(update, ogg_bytes: bytes) -> UploadIngestOutcome:
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        outcome = ingest_upload(
            session,
            user_id=user_id,
            filename="telegram-voice-note.ogg",
            content=ogg_bytes,
            media_type="audio/ogg",
            destination="journal",
            surface="telegram",
            conversation_id=str(update.message.chat_id),
            message_id=str(getattr(update.message, "message_id", "") or ""),
            author_user_id=str(getattr(getattr(update.message, "from_user", None), "id", "") or ""),
        )
        record_audit_event(
            session,
            user_id=user_id,
            action="voice.note.processed",
            metadata={
                "status": outcome.status,
                "route_type": outcome.route_type,
                "surface": "telegram",
                "entry_id": outcome.entry_id,
                "voice_asset_id": outcome.voice_asset_id,
                "voice_retained": bool(outcome.voice_asset_id),
                "extraction_status": outcome.extraction_status,
            },
        )
        return outcome
    finally:
        session.close()


def _transcribe(ogg_bytes: bytes) -> str:
    """Compatibility wrapper retained for focused adapter tests."""

    return transcribe_audio(ogg_bytes, suffix=".ogg").text.strip()
