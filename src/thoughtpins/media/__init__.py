"""Media helpers shared by Telegram, web, and future native upload paths."""

from thoughtpins.media.extraction import (
    extract_document_text,
    extract_image_text,
    save_media_attachment,
)
from thoughtpins.media.extraction_types import MediaExtraction
from thoughtpins.media.transcription import transcribe_audio

__all__ = [
    "MediaExtraction",
    "extract_document_text",
    "extract_image_text",
    "save_media_attachment",
    "transcribe_audio",
]
