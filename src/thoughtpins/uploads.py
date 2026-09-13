"""Shared upload ingestion for web, mobile, and Telegram-adjacent surfaces."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from sqlalchemy.orm import Session

import thoughtpins.library as library
from thoughtpins.chat.engine import ChatEngineResult, execute_chat_message
from thoughtpins.media import (
    MediaExtraction,
    extract_document_text,
    extract_image_text,
    save_media_attachment,
    transcribe_audio,
)
from thoughtpins.users import lock_active_user_for_write
from thoughtpins.voice_archive import VoiceRetentionOutcome, retain_voice_note_if_consented

Destination = Literal["auto", "journal", "library"]
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_SUFFIXES = {".ogg", ".oga", ".mp3", ".m4a", ".wav", ".webm", ".aac", ".flac"}


@dataclass(frozen=True)
class UploadIngestOutcome:
    status: str
    route_type: str
    filename: str
    media_kind: str
    destination: str
    extraction_status: str
    extracted_chars: int = 0
    attachment_saved: bool = False
    attachment_ref: str | None = None
    voice_asset_id: str | None = None
    title: str | None = None
    entry_id: str | None = None
    job_id: str | None = None
    document_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def decode_upload_content(content_base64: str) -> bytes:
    value = (content_base64 or "").strip()
    if not value:
        return b""
    if "," in value and value[:80].lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc


def ingest_upload(
    session: Session,
    *,
    user_id: str,
    filename: str,
    content: bytes,
    media_type: str = "",
    destination: Destination = "auto",
    caption: str = "",
    title: str = "",
    source_type: str = "",
    surface: str = "upload",
    conversation_id: str = "uploads",
    message_id: str = "",
    author_user_id: str = "",
) -> UploadIngestOutcome:
    clean_filename = Path(filename or "upload.bin").name or "upload.bin"
    if not content:
        raise ValueError("Uploaded file is empty")
    if len(content) > UPLOAD_MAX_BYTES:
        raise ValueError(f"Uploaded file is too large; limit is {UPLOAD_MAX_BYTES // (1024 * 1024)} MB")

    lock_active_user_for_write(session, user_id)
    media_kind = detect_media_kind(clean_filename, media_type)
    # Voice is ephemeral unless the user has separately enabled the encrypted
    # personal archive. Other user-supplied files retain their existing vault flow.
    attachment = (
        None
        if media_kind == "audio"
        else save_media_attachment(
            content,
            category=media_kind,
            filename=clean_filename,
            user_id=user_id,
            session=session,
        )
    )
    extraction = _extract(content, filename=clean_filename, media_type=media_type, media_kind=media_kind)
    text = _combine_caption_and_text(caption, extraction.text)
    resolved_destination = resolve_destination(destination, media_kind)
    attachment_ref = _attachment_ref(attachment) if attachment is not None else None

    if not text.strip():
        return UploadIngestOutcome(
            status="needs_text",
            route_type="upload_needs_text",
            filename=clean_filename,
            media_kind=media_kind,
            destination=resolved_destination,
            extraction_status=extraction.error or "no_text_extracted",
            attachment_saved=attachment is not None,
            attachment_ref=attachment_ref,
            error=_human_extraction_error(extraction, media_kind),
            metadata={"media_type": media_type, "extraction": extraction.metadata},
        )

    if resolved_destination == "journal":
        chat_result = execute_chat_message(
            session,
            "journal: " + text,
            user_id=user_id,
            surface=surface or "upload",
            conversation_id=conversation_id or "uploads",
            message_id=message_id,
            author_user_id=author_user_id,
        )
        retention = _retain_voice_note(
            session,
            user_id=user_id,
            media_kind=media_kind,
            content=content,
            filename=clean_filename,
            media_type=media_type,
            raw_entry_id=chat_result.entry_id,
            extraction=extraction,
        )
        return UploadIngestOutcome(
            status=chat_result.status,
            route_type="journal_upload",
            filename=clean_filename,
            media_kind=media_kind,
            destination=resolved_destination,
            extraction_status=extraction.error or "processed",
            extracted_chars=len(text),
            attachment_saved=retention.retained if media_kind == "audio" else attachment is not None,
            attachment_ref=attachment_ref,
            voice_asset_id=retention.asset_id,
            title=title or clean_filename,
            entry_id=chat_result.entry_id,
            job_id=chat_result.job_id,
            error=chat_result.metadata.get("error") if isinstance(chat_result.metadata, dict) else None,
            metadata={
                "media_type": media_type,
                "chat": _chat_metadata(chat_result),
                "extraction": extraction.metadata,
                **(_voice_archive_metadata(retention) if media_kind == "audio" else {}),
            },
        )

    result = library.ingest_document_text(
        session,
        text,
        user_id=user_id,
        source_type=source_type or _source_type_for_upload(media_kind, clean_filename),
        title=title or Path(clean_filename).stem or clean_filename,
        access_method="user_upload",
        rights_basis="user_provided",
        metadata_json={
            "upload": {
                "filename": clean_filename,
                "media_type": media_type,
                "media_kind": media_kind,
                "attachment_ref": attachment_ref,
                "extraction": extraction.metadata,
            }
        },
        defer_vector_index=True,
    )
    retention = _retain_voice_note(
        session,
        user_id=user_id,
        media_kind=media_kind,
        content=content,
        filename=clean_filename,
        media_type=media_type,
        raw_entry_id=result.raw_entry_id,
        extraction=extraction,
    )
    return UploadIngestOutcome(
        status=result.status,
        route_type="library_upload",
        filename=clean_filename,
        media_kind=media_kind,
        destination=resolved_destination,
        extraction_status=extraction.error or "processed",
        extracted_chars=len(text),
        attachment_saved=retention.retained if media_kind == "audio" else attachment is not None,
        attachment_ref=attachment_ref,
        voice_asset_id=retention.asset_id,
        title=result.title,
        entry_id=result.raw_entry_id,
        document_id=result.document_id,
        job_id=result.job_id,
        error=result.error,
        metadata={
            "media_type": media_type,
            "chunks": result.chunks,
            "memories": result.memories,
            "duplicate": result.duplicate,
            "access_method": result.access_method,
            "rights_basis": result.rights_basis,
            "extraction": extraction.metadata,
            **(_voice_archive_metadata(retention) if media_kind == "audio" else {}),
        },
    )


def detect_media_kind(filename: str, media_type: str = "") -> str:
    lowered_type = (media_type or "").lower()
    suffix = Path(filename or "").suffix.lower()
    if lowered_type.startswith("audio/") or suffix in AUDIO_SUFFIXES:
        return "audio"
    if lowered_type.startswith("image/") or suffix in IMAGE_SUFFIXES:
        return "image"
    if lowered_type == "application/pdf" or suffix in PDF_SUFFIXES:
        return "document"
    if lowered_type.startswith("text/") or suffix in TEXT_SUFFIXES:
        return "document"
    return "document"


def resolve_destination(destination: Destination, media_kind: str) -> str:
    if destination in {"journal", "library"}:
        return destination
    return "journal" if media_kind in {"audio", "image"} else "library"


def _extract(content: bytes, *, filename: str, media_type: str, media_kind: str) -> MediaExtraction:
    suffix = Path(filename or "").suffix.lower()
    if media_kind == "audio":
        return transcribe_audio(content, suffix=suffix or ".audio")
    if media_kind == "image":
        return extract_image_text(content, suffix=suffix or ".jpg")
    return extract_document_text(content, suffix)


def _combine_caption_and_text(caption: str, text: str) -> str:
    caption = (caption or "").strip()
    text = (text or "").strip()
    if caption and text:
        return f"{caption}\n\n{text}"
    return caption or text


def _source_type_for_upload(media_kind: str, filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if media_kind == "audio":
        return "audio_transcript"
    if media_kind == "image":
        return "image_text"
    return "document"


def _attachment_ref(path: Path) -> str:
    try:
        return path.relative_to(path.parents[2]).as_posix()
    except Exception:
        return path.name


def _human_extraction_error(extraction: MediaExtraction, media_kind: str) -> str:
    if media_kind == "audio":
        return "I could not transcribe this audio yet. Type or paste the transcript to save it."
    if media_kind == "image":
        return "I could not read text from this image yet. Type or paste the text to save it."
    return "I could not extract readable text from this file. Paste the text you want remembered."


def _chat_metadata(result: ChatEngineResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "route_type": result.route_type,
        "entry_id": result.entry_id,
        "job_id": result.job_id,
        "context_size_chars": result.context_size_chars,
    }


def _retain_voice_note(
    session: Session,
    *,
    user_id: str,
    media_kind: str,
    content: bytes,
    filename: str,
    media_type: str,
    raw_entry_id: str | None,
    extraction: MediaExtraction,
) -> VoiceRetentionOutcome:
    if media_kind != "audio":
        return VoiceRetentionOutcome(False, "not_audio")
    try:
        return retain_voice_note_if_consented(
            session,
            user_id=user_id,
            content=content,
            filename=filename,
            media_type=media_type,
            raw_entry_id=raw_entry_id,
            transcript=extraction.text,
            language=str(extraction.metadata.get("language") or "") or None,
            transcription_mode=str(extraction.metadata.get("processing") or "local"),
        )
    except Exception as exc:
        logger.warning("Optional voice archive retention failed: {}", type(exc).__name__)
        return VoiceRetentionOutcome(False, "archive_failed")


def _voice_archive_metadata(retention: VoiceRetentionOutcome) -> dict[str, Any]:
    return {
        "voice_archive": {
            "retained": retention.retained,
            "reason": retention.reason,
            "asset_id": retention.asset_id,
        }
    }
