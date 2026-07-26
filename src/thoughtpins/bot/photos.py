"""Telegram media handlers for photos, screenshots, and uploaded documents."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from thoughtpins.bot.commands import _e, _process_and_reply, ingest_library_message
from thoughtpins.media import extract_document_text, extract_image_text, save_media_attachment


async def handle_photo_message(update, context):
    """Download a Telegram photo, OCR visible text, and ingest the text as a journal entry."""

    chat_id = str(update.message.chat_id)
    e = lambda emoji: _e(emoji, chat_id)
    photo = update.message.photo[-1]
    caption = update.message.caption or ""
    status_msg = await update.message.reply_text(f"{e('Image')} Processing image... extracting text.")

    try:
        photo_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await photo_file.download_as_bytearray())
        save_media_attachment(img_bytes, category="photos", filename=f"telegram_{photo.file_id}.jpg")
        extracted_text = _ocr_extract(img_bytes)

        if caption:
            extracted_text = f"{caption}\n\n{extracted_text}" if extracted_text else caption

        if not extracted_text or len(extracted_text.strip()) < 3:
            await status_msg.edit_text(f"{e('Info')} No text detected in this image. Saved to vault.")
            return

        await status_msg.edit_text(
            f"{e('OCR')} Text extracted ({len(extracted_text)} chars):\n\n"
            f'"{extracted_text[:200]}{"..." if len(extracted_text) > 200 else ""}"\n\n'
            "Processing as journal entry..."
        )
        await _process_and_reply(update, extracted_text)
    except Exception as exc:
        logger.error("Photo processing failed: {}", exc)
        await status_msg.edit_text(f"{e('Warning')} Couldn't process this image. Saved to vault for manual review.")


def _ocr_extract(img_bytes: bytes) -> str:
    """Compatibility wrapper for image OCR extraction."""

    return extract_image_text(img_bytes, suffix=".jpg").text.strip()


async def handle_document_message(update, context):
    """Handle Telegram document/file uploads and save readable text to library memory."""

    chat_id = str(update.message.chat_id)
    e = lambda emoji: _e(emoji, chat_id)
    document = update.message.document
    if not document:
        await update.message.reply_text(f"{e('Info')} No document found in this message.")
        return

    filename = document.file_name or "uploaded document"
    suffix = Path(filename).suffix.lower()
    status_msg = await update.message.reply_text(f"{e('Info')} Reading document text...")
    try:
        tg_file = await context.bot.get_file(document.file_id)
        content = bytes(await tg_file.download_as_bytearray())
        save_media_attachment(content, category="documents", filename=filename)
        text = _extract_document_text(content, suffix)
        caption = update.message.caption or ""
        if caption:
            text = f"{caption}\n\n{text}" if text else caption
        if not text or len(text.strip()) < 20:
            await status_msg.edit_text(
                f"{e('Warning')} I could not extract enough text from {filename}. "
                "Paste the text with /read if you want it saved."
            )
            return
        await status_msg.edit_text(f"{e('Info')} Extracted {len(text)} chars. Saving to reading memory...")
        await ingest_library_message(update, f"document: {filename}\n\n{text}")
    except Exception as exc:
        logger.error("Document processing failed: {}", exc)
        await status_msg.edit_text(f"{e('Warning')} Could not process {filename}. Paste the text with /read.")


def _extract_document_text(content: bytes, suffix: str) -> str:
    """Compatibility wrapper for document text extraction."""

    return extract_document_text(content, suffix).text.strip()
