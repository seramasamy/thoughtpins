"""Reusable media extraction helpers for Telegram, web, and future mobile uploads."""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

from loguru import logger

from thoughtpins.config import config  # noqa: F401 - compatibility for extraction configuration
from thoughtpins.media.attachments import save_media_attachment  # noqa: F401
from thoughtpins.media.extraction_types import MediaExtraction

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
PDF_PAGE_LIMIT = 100


def extract_image_text(content: bytes, *, suffix: str = ".jpg") -> MediaExtraction:
    """Extract visible text using the installed local OCR engine."""

    if not content:
        return MediaExtraction(kind="image", error="empty_image")
    try:
        from PIL import Image

        reader = _get_ocr_reader()
        with Image.open(io.BytesIO(content)) as original:
            if original.width * original.height > 25_000_000:
                return MediaExtraction(kind="image", error="image_too_large")
            image = original.convert("RGB")
        with tempfile.TemporaryDirectory(prefix="thoughtpins-ocr-") as directory:
            tmp_path = Path(directory) / "image.png"
            image.save(tmp_path, format="PNG")
            results = reader.readtext(str(tmp_path), detail=0, paragraph=True)
            text = " ".join(str(item) for item in results).strip()
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
    if normalized_suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.debug("pypdf is not installed; PDF extraction unavailable")
            return MediaExtraction(kind="document", metadata={"suffix": normalized_suffix}, error="missing_pypdf")
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [(page.extract_text() or "") for page in reader.pages[:PDF_PAGE_LIMIT]]
            return MediaExtraction(
                text="\n\n".join(pages).strip(),
                kind="document",
                metadata={
                    "suffix": normalized_suffix,
                    "engine": "pypdf",
                    "pages_read": min(len(reader.pages), PDF_PAGE_LIMIT),
                },
            )
        except Exception as exc:
            logger.warning("PDF text extraction failed ({})", type(exc).__name__)
            return MediaExtraction(kind="document", metadata={"suffix": normalized_suffix}, error="pdf_extract_failed")
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


_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        executable = shutil.which("tesseract")
        if executable:
            from thoughtpins.media.ocr import TesseractReader

            _ocr_reader = TesseractReader(executable)
            return _ocr_reader
        import easyocr

        _ocr_reader = easyocr.Reader(["en"], gpu=False)
        logger.info("EasyOCR reader loaded for media extraction")
    return _ocr_reader
