"""Reusable media extraction helpers for Telegram, web, and future mobile uploads."""

from __future__ import annotations

import io
import shutil
import threading
from typing import Any

from loguru import logger

from thoughtpins.config import config  # noqa: F401 - compatibility for extraction configuration
from thoughtpins.media.attachments import save_media_attachment  # noqa: F401
from thoughtpins.media.extraction_types import MediaExtraction
from thoughtpins.media.ocr import read_image_text
from thoughtpins.media.office import OFFICE_SUFFIXES, extract_office_text
from thoughtpins.media.pdf import PDF_PAGE_LIMIT, extract_pdf_text  # noqa: F401 - PDF_PAGE_LIMIT compatibility

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}


def extract_image_text(content: bytes, *, suffix: str = ".jpg") -> MediaExtraction:
    """Extract visible text using the installed local OCR engine."""

    if not content:
        return MediaExtraction(kind="image", error="empty_image")
    try:
        from PIL import Image, ImageOps

        reader = _get_ocr_reader()
        with Image.open(io.BytesIO(content)) as original:
            if original.width * original.height > 25_000_000:
                return MediaExtraction(kind="image", error="image_too_large")
            image = ImageOps.exif_transpose(original).convert("RGB")
        text = read_image_text(reader, image)
        if text:
            logger.info("OCR extracted {} chars from image", len(text))
        return MediaExtraction(text=text, kind="image", metadata={"engine": getattr(reader, "engine", "easyocr")})
    except ImportError:
        logger.debug("An OCR dependency is not installed")
        return MediaExtraction(kind="image", error="missing_ocr_dependency")
    except Exception as exc:
        logger.warning("Image OCR failed ({})", type(exc).__name__)
        return MediaExtraction(kind="image", error="ocr_failed")


def extract_document_text(content: bytes, suffix: str) -> MediaExtraction:
    """Extract text from files the user deliberately supplied for processing."""

    normalized_suffix = (suffix or "").lower()
    if not content:
        return MediaExtraction(kind="document", metadata={"suffix": normalized_suffix}, error="empty_document")
    if normalized_suffix in TEXT_SUFFIXES:
        return MediaExtraction(
            text=content.decode("utf-8", errors="replace").strip(),
            kind="document",
            metadata={"suffix": normalized_suffix, "engine": "utf8"},
        )
    if normalized_suffix in OFFICE_SUFFIXES:
        # Before the textish-bytes fallback: a .docx is a ZIP of XML, and must
        # never be decoded as if its compressed bytes were text.
        return extract_office_text(content, normalized_suffix)
    if normalized_suffix == ".pdf":
        # Resolved at call time so tests and callers can swap the OCR engine.
        return extract_pdf_text(content, normalized_suffix, ocr_reader=lambda: _get_ocr_reader(require_timeout=True))
    if _looks_textish(content):
        return MediaExtraction(
            text=content.decode("utf-8", errors="replace").strip(),
            kind="document",
            metadata={"suffix": normalized_suffix, "engine": "textish-bytes"},
        )
    return MediaExtraction(kind="document", metadata={"suffix": normalized_suffix}, error="unsupported_binary_document")


def _looks_textish(content: bytes) -> bool:
    if not content:
        return False
    sample = content[:2048]
    control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
    return control / max(len(sample), 1) < 0.05


_ocr_reader: Any = None
# Uploads reach this from request worker threads and the Telegram bot from
# asyncio.to_thread, so the lazy engine is built once, under a lock.
_ocr_reader_lock = threading.Lock()


def _get_ocr_reader(*, require_timeout: bool = False):
    global _ocr_reader
    with _ocr_reader_lock:
        if _ocr_reader is None:
            executable = shutil.which("tesseract")
            if executable:
                from thoughtpins.media.ocr import TesseractReader

                _ocr_reader = TesseractReader(executable)
                return _ocr_reader
            if require_timeout:
                # Building EasyOCR loads a large model, possibly downloading it;
                # a caller that would refuse it anyway must not pay for that.
                raise ImportError("a time-bounded OCR engine (Tesseract) is not installed")
            import easyocr

            from thoughtpins.media.ocr import SerializedReader

            # One EasyOCR model is hundreds of MB and not safe to call from two
            # threads at once; share one and let calls take turns.
            _ocr_reader = SerializedReader(easyocr.Reader(["en"], gpu=False), engine="easyocr")
            logger.info("EasyOCR reader loaded for media extraction")
    return _ocr_reader
