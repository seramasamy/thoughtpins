"""PDF text extraction, with bounded OCR for scanned pages.

Pages with embedded text are read with pypdf, exactly as before. A page with
almost no embedded text that draws a page-sized image -- a scan -- is read with
the local OCR engine. OCR only fills pages that had no usable text; it never
replaces embedded text, which is always better.

Extraction runs inside the upload request, and a proxied request has about 100
seconds, so text extraction, image decoding and OCR share one time budget, and
OCR is also capped by page count and by how many uploads may run it at once, so
scanned PDFs cannot occupy every API worker. Only images a page actually draws
are considered, found by a bounded, cycle-safe walk of its content stream. JPEG
and JPEG 2000 scans are sized from their own headers before decoding, because a
declared PDF size can lie, and JPEGs decode at reduced resolution. Every page
that was not read is counted, with the reason, rather than silently dropped.
"""

from __future__ import annotations

import io
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from thoughtpins.media.extraction_types import MediaExtraction
from thoughtpins.media.ocr import read_image_text

PDF_PAGE_LIMIT = 100
OCR_PAGE_LIMIT = 20
# Shared by text extraction, image decoding and OCR, well inside the ~100 s a
# proxied request may take.
OCR_TIME_BUDGET_SECONDS = 40.0
OCR_PAGE_TIMEOUT_SECONDS = 30.0
_OCR_MIN_REMAINING_SECONDS = 3.0
# Uploads that may run PDF OCR at once in one process. Others are told OCR is
# busy instead of holding a request worker for up to the whole budget.
OCR_CONCURRENCY = 2
_OCR_SLOTS = threading.BoundedSemaphore(OCR_CONCURRENCY)
# Fewer non-space characters than this is a page without usable text: blank,
# or a scan carrying only a scanner app's stamp.
MIN_EMBEDDED_CHARS = 40
# Smaller images are logos and icons, not page scans.
MIN_SCAN_PIXELS = 200_000
# Some scanners store a page as several strips. Drawn images this size or more
# besides the largest mean OCR saw only part of the page, which is reported.
MIN_PIECE_PIXELS = 50_000
# A 600 dpi Letter page is 33.7M pixels. JPEG and JPEG 2000 sizes are read from
# the image header; other encodings are decoded by pypdf at their declared size,
# which their sample data must match, and re-encoded, so they get a lower cap.
MAX_SCAN_PIXELS = 36_000_000
MAX_RAW_SCAN_PIXELS = 25_000_000
# Downscaled before OCR: about 350 dpi on Letter, as much as Tesseract uses.
OCR_LONG_SIDE = 4_000
# A scanned page draws its image in a few dozen bytes. A page whose content
# stream is larger is vector drawing, which OCR cannot read without rendering.
MAX_SCAN_CONTENT_BYTES = 256 * 1024
MAX_XOBJECTS_PER_PAGE = 64
_MAX_FORM_DEPTH = 3
_HEADER_SIZED_FILTERS = {"/DCTDecode", "/JPXDecode"}
_WORD = re.compile(r"[^\W\d_]{3,}")


@dataclass(frozen=True)
class _Scan:
    pixels: int
    xobject: Any
    # Other sizeable images the page draws: strips or tiles of one scan.
    pieces: int = 0


@dataclass
class _OcrOutcome:
    pages: list[int] = field(default_factory=list)
    failed: int = 0
    # Scans found but not read: the page limit, or the time budget mid-page.
    skipped: int = 0
    # Pages without text never examined: the time budget ran out, or OCR had
    # already stopped (no engine, busy, page limit), so walking them buys nothing.
    unchecked: int = 0
    # Pages stored as several image pieces, of which OCR read at most one.
    pieced: int = 0
    unavailable: bool = False
    busy: bool = False
    engine: str | None = None


class _BudgetSpent(Exception):
    """The shared time budget ran out before this page could be read."""


def extract_pdf_text(
    content: bytes,
    suffix: str,
    *,
    ocr_reader: Callable[[], Any],
    clock: Callable[[], float] = time.monotonic,
) -> MediaExtraction:
    started = clock()
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.debug("pypdf is not installed; PDF extraction unavailable")
        return MediaExtraction(kind="document", metadata={"suffix": suffix}, error="missing_pypdf")
    try:
        reader = PdfReader(io.BytesIO(content))
        total = len(reader.pages)
        pages = list(reader.pages[:PDF_PAGE_LIMIT])
        texts: list[str] = []
        for page in pages:
            if _remaining(started, clock) <= 0:
                break
            texts.append(page.extract_text() or "")
    except Exception as exc:
        logger.warning("PDF text extraction failed ({})", type(exc).__name__)
        return MediaExtraction(kind="document", metadata={"suffix": suffix}, error="pdf_extract_failed")
    timed_out = len(pages) - len(texts)
    pages = pages[: len(texts)]

    ocr = _ocr_scanned_pages(pages, texts, ocr_reader, started=started, clock=clock)
    missing = sum(not text.strip() for text in texts)
    truncated = total > PDF_PAGE_LIMIT
    warnings = []
    if truncated:
        warnings.append(f"Only the first {PDF_PAGE_LIMIT} of {total} pages were read.")
    if timed_out:
        warnings.append(f"Reading stopped after {len(texts)} pages to stay within the upload time limit.")
    if ocr.pages:
        warnings.append(
            f"{len(ocr.pages)} scanned pages were read with OCR; check names and numbers against the original."
        )
    if ocr.pieced:
        warnings.append(
            f"{ocr.pieced} pages are stored as several image strips; OCR read only the largest, so text may be missing."
        )
    if missing:
        warnings.append(f"{missing} pages had no readable text.{_missing_reason(ocr)}")
    return MediaExtraction(
        text="\n\n".join(texts).strip(),
        kind="document",
        metadata={
            "suffix": suffix,
            "engine": "pypdf",
            "pages_read": len(texts),
            "pages_total": total,
            "pages_without_text": missing,
            "pages_timed_out": timed_out,
            "ocr_pages": ocr.pages,
            "ocr_engine": ocr.engine if ocr.pages else None,
            "ocr_failed_pages": ocr.failed,
            "ocr_skipped_pages": ocr.skipped,
            "ocr_unchecked_pages": ocr.unchecked,
            "ocr_unavailable": ocr.unavailable,
            "ocr_busy": ocr.busy,
            "ocr_pieced_pages": ocr.pieced,
            "partial": bool(missing or truncated or timed_out or ocr.pieced),
            "warnings": warnings,
        },
        error="pdf_needs_ocr" if not any(text.strip() for text in texts) else None,
    )


def _missing_reason(ocr: _OcrOutcome) -> str:
    if ocr.unavailable:
        return " OCR for PDFs is not set up on this server."
    if ocr.busy:
        return " OCR was busy with other uploads; try again in a minute."
    if ocr.skipped or ocr.unchecked:
        return (
            f" OCR reads up to {OCR_PAGE_LIMIT} scanned pages within {int(OCR_TIME_BUDGET_SECONDS)} seconds"
            f" per upload; {ocr.skipped + ocr.unchecked} pages were not reached."
        )
    if ocr.failed:
        return f" OCR could not read {ocr.failed} scanned pages."
    return ""


def _ocr_scanned_pages(
    pages: list[Any],
    texts: list[str],
    reader_factory: Callable[[], Any],
    *,
    started: float,
    clock: Callable[[], float],
) -> _OcrOutcome:
    """OCR pages without usable text in place, within the page, time and concurrency limits."""

    outcome = _OcrOutcome()
    reader: Any = None
    holding_slot = False
    try:
        for index, text in enumerate(texts):
            if len("".join(text.split())) >= MIN_EMBEDDED_CHARS:
                continue
            stopped = outcome.unavailable or outcome.busy or len(outcome.pages) + outcome.failed >= OCR_PAGE_LIMIT
            if stopped or _remaining(started, clock) < _OCR_MIN_REMAINING_SECONDS:
                # Finding a scan walks the page; once OCR cannot run, or the
                # budget is spent, that walk buys nothing.
                outcome.unchecked += 1
                continue
            scan = _largest_drawn_image(pages[index])
            if scan is None:
                continue
            if scan.pixels < MIN_SCAN_PIXELS:
                # Strips too small to read on their own are still text lost.
                outcome.pieced += scan.pieces > 0
                continue
            if not holding_slot:
                holding_slot = _OCR_SLOTS.acquire(blocking=False)
                if not holding_slot:
                    outcome.busy = True
                    outcome.skipped += 1
                    continue
            if reader is None:
                reader = _start_reader(reader_factory, outcome)
                if reader is None:
                    outcome.skipped += 1
                    continue
            try:
                recognized = _read_scan(pages[index], scan, reader, started=started, clock=clock)
            except _BudgetSpent:
                outcome.skipped += 1
                continue
            except Exception as exc:
                # Type only: decoder and OCR messages can carry document content.
                logger.warning("PDF page OCR failed ({})", type(exc).__name__)
                outcome.failed += 1
                continue
            if _looks_like_text(recognized):
                texts[index] = f"{text.strip()}\n{recognized.strip()}".strip()
                outcome.pages.append(index + 1)
                outcome.pieced += scan.pieces > 0
            else:
                outcome.failed += 1
    finally:
        if holding_slot:
            _OCR_SLOTS.release()
    outcome.engine = getattr(reader, "engine", None) if reader is not None else None
    if outcome.pages:
        logger.info("PDF OCR read {} scanned pages", len(outcome.pages))
    return outcome


def _start_reader(reader_factory: Callable[[], Any], outcome: _OcrOutcome) -> Any:
    try:
        reader = reader_factory()
    except Exception as exc:
        logger.warning("PDF OCR unavailable ({})", type(exc).__name__)
        outcome.unavailable = True
        return None
    if not getattr(reader, "supports_timeout", False):
        # The budget holds only if each page's OCR can be stopped, which the
        # optional EasyOCR fallback cannot do. Photos still use it; PDFs do not.
        logger.warning("PDF OCR needs a time-bounded engine; {} is not", getattr(reader, "engine", "this engine"))
        outcome.unavailable = True
        return None
    return reader


def _remaining(started: float, clock: Callable[[], float]) -> float:
    return OCR_TIME_BUDGET_SECONDS - (clock() - started)


def _largest_drawn_image(page: Any) -> _Scan | None:
    """The largest image the page draws, following the forms it draws.

    Bounded by content size, form depth and a per-page XObject count, and safe
    against shared or cyclic references, so a crafted file cannot make the walk
    itself expensive. Images listed in resources but never drawn are ignored:
    some producers share one resource dictionary across every page.
    """

    from pypdf.generic import ContentStream, IndirectObject

    found: list[_Scan] = []
    seen: set[Any] = set()
    budget = [MAX_XOBJECTS_PER_PAGE]

    def visit(operations: Any, resources: Any, depth: int) -> None:
        if resources is None or depth > _MAX_FORM_DEPTH:
            return
        xobjects = resources.get_object().get("/XObject")
        if xobjects is None:
            return
        xobjects = xobjects.get_object()
        for operands, operator in operations:
            if operator != b"Do" or not operands or str(operands[0]) not in xobjects:
                continue
            if budget[0] <= 0:
                return
            budget[0] -= 1
            reference = xobjects.raw_get(str(operands[0]))
            identity = (
                (reference.idnum, reference.generation) if isinstance(reference, IndirectObject) else id(reference)
            )
            if identity in seen:
                continue
            seen.add(identity)
            xobject = reference.get_object()
            subtype = xobject.get("/Subtype")
            if subtype == "/Image":
                found.append(_Scan(int(xobject.get("/Width", 0)) * int(xobject.get("/Height", 0)), xobject))
            elif subtype == "/Form" and len(xobject.get_data()) <= MAX_SCAN_CONTENT_BYTES:
                visit(ContentStream(xobject, page.pdf).operations, xobject.get("/Resources"), depth + 1)

    try:
        # Measured on the decoded stream bytes before anything is parsed, so a
        # multi-megabyte vector page costs a length check, not a parse.
        if _content_bytes(page) > MAX_SCAN_CONTENT_BYTES:
            return None
        contents = page.get_contents()
        if contents is not None:
            visit(contents.operations, page.get("/Resources"), 0)
    except Exception as exc:
        logger.debug("PDF page content unreadable ({})", type(exc).__name__)
        return None
    if not found:
        return None
    largest = max(found, key=lambda scan: scan.pixels)
    pieces = sum(1 for scan in found if scan is not largest and scan.pixels >= MIN_PIECE_PIXELS)
    return _Scan(largest.pixels, largest.xobject, pieces)


def _content_bytes(page: Any) -> int:
    contents = page.get("/Contents")
    if contents is None:
        return 0
    contents = contents.get_object()
    streams = contents if isinstance(contents, list) else [contents]
    return sum(len(stream.get_object().get_data()) for stream in streams)


def _read_scan(page: Any, scan: _Scan, reader: Any, *, started: float, clock: Callable[[], float]) -> str:
    from PIL import Image

    filters = scan.xobject.get("/Filter")
    names = [str(item) for item in filters] if isinstance(filters, list) else ([str(filters)] if filters else [])
    if names and names[-1] in _HEADER_SIZED_FILTERS:
        image = Image.open(io.BytesIO(scan.xobject.get_data()))
        # The header's size, not the PDF's claim, decides what decoding costs.
        if image.width * image.height > MAX_SCAN_PIXELS:
            raise ValueError("scan image exceeds the pixel limit")
        if names[-1] == "/DCTDecode":
            # Decode straight to grayscale at reduced size; a 600 dpi colour
            # page then never exists in memory at full resolution.
            image.draft("L", (OCR_LONG_SIDE, OCR_LONG_SIDE))
    else:
        # Raw samples must match their declared size, so the declared size is
        # the decoded size. Decoded from the object already found, not through
        # page.images, which would walk every XObject on the page again.
        if scan.pixels > MAX_RAW_SCAN_PIXELS:
            raise ValueError("scan image exceeds the pixel limit")
        image = scan.xobject.decode_as_image()
    grayscale = image.convert("L")
    if max(grayscale.size) > OCR_LONG_SIDE:
        grayscale.thumbnail((OCR_LONG_SIDE, OCR_LONG_SIDE))
    # /Rotate turns the page clockwise for display; the image is stored
    # unrotated, and Tesseract reads sideways text as noise.
    rotation = int(page.rotation or 0) % 360
    if rotation in (90, 180, 270):
        grayscale = grayscale.rotate(-rotation, expand=True)
    timeout = min(OCR_PAGE_TIMEOUT_SECONDS, _remaining(started, clock))
    if timeout < _OCR_MIN_REMAINING_SECONDS:
        raise _BudgetSpent
    try:
        return read_image_text(reader, grayscale, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if timeout < OCR_PAGE_TIMEOUT_SECONDS:
            raise _BudgetSpent from exc
        raise


def _looks_like_text(recognized: str) -> bool:
    # OCR run over a photograph returns stray marks. Keep a result only when it
    # holds some words, so a picture page is not indexed as noise.
    return sum(character.isalnum() for character in recognized) >= 8 and bool(_WORD.search(recognized))
