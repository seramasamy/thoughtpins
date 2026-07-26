"""Reusable media extraction helpers for Telegram, web, and future mobile uploads."""

from __future__ import annotations

import io
import tempfile
from datetime import datetime
from pathlib import Path

from loguru import logger

from thoughtpins.config import config
from thoughtpins.media.extraction_types import MediaExtraction
from thoughtpins.vault.markdown import safe_filename

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
PDF_PAGE_LIMIT = 100


def extract_image_text(content: bytes, *, suffix: str = ".jpg") -> MediaExtraction:
    """Extract visible text from screenshots, photos, or document images when EasyOCR exists."""

    if not content:
        return MediaExtraction(kind="image", error="empty_image")
    try:
        from PIL import Image

        reader = _get_ocr_reader()
        image = Image.open(io.BytesIO(content))
        if image.mode in {"RGBA", "P"}:
            image = image.convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=suffix or ".jpg", delete=False) as tmp:
            image.save(tmp, format="JPEG", quality=85)
            tmp_path = Path(tmp.name)
        try:
            results = reader.readtext(str(tmp_path), detail=0, paragraph=True)
            text = " ".join(str(item) for item in results).strip()
            if text:
                logger.info("OCR extracted {} chars from image", len(text))
            return MediaExtraction(text=text, kind="image", metadata={"engine": "easyocr"})
        finally:
            tmp_path.unlink(missing_ok=True)
    except ImportError:
        logger.debug("EasyOCR/Pillow is not installed; image extraction unavailable")
        return MediaExtraction(kind="image", error="missing_ocr_dependency")
    except Exception as exc:
        logger.warning("Image OCR failed: {}", exc)
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
            logger.warning("PDF text extraction failed: {}", exc)
            return MediaExtraction(kind="document", metadata={"suffix": normalized_suffix}, error="pdf_extract_failed")
    if _looks_textish(content):
        return MediaExtraction(
            text=content.decode("utf-8", errors="replace").strip(),
            kind="document",
            metadata={"suffix": normalized_suffix, "engine": "textish-bytes"},
        )
    return MediaExtraction(kind="document", metadata={"suffix": normalized_suffix}, error="unsupported_binary_document")


def save_media_attachment(content: bytes, *, category: str, filename: str | None = None) -> Path:
    """Persist original media in the local vault attachment area for review/export."""

    category_name = safe_filename(category or "media", fallback="media", max_length=40).lower().replace(" ", "-")
    suffix = Path(filename or "").suffix.lower() or ".bin"
    stem = safe_filename(Path(filename or category_name).stem, fallback=category_name, max_length=80)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = config.vault_path() / "09_Attachments" / category_name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stamp}_{stem}{suffix}"
    path.write_bytes(content)
    return path


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
        import easyocr

        _ocr_reader = easyocr.Reader(["en"], gpu=False)
        logger.info("EasyOCR reader loaded for media extraction")
    return _ocr_reader
