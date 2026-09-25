"""PDF text extraction, with bounded OCR for scanned pages.

Pages with embedded text are read with pypdf, exactly as before. A page with
almost no embedded text that draws a page-sized image -- a scan -- is read with
the local OCR engine. OCR only fills pages that had no usable text; it never
replaces embedded text, which is always better.

Extraction runs inside the upload request, and a proxied request has about 100
seconds, so text extraction, image decoding and OCR share one time budget, and
OCR is also capped by page count and by how many uploads may run it at once, so
scanned PDFs cannot occupy every API worker. ``media/pdf_images.py`` finds the
images a page draws, decodes each within a hard bound, and reassembles pages
stored as strips; this module decides what to read and reports every page that
was not read, with the reason, rather than dropping it silently.
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

from thoughtpins.media import pdf_images
from thoughtpins.media.extraction_types import MediaExtraction
from thoughtpins.media.ocr import read_image_text
from thoughtpins.media.pdf_images import DecodeTimeout, DrawnImage, compose, decode, drawn_images, fix_polarity

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
# Drawn images this size or more count as pieces of the page's scan.
MIN_PIECE_PIXELS = 50_000
_WORD = re.compile(r"[^\W\d_]{3,}")


@dataclass(frozen=True)
class _PagePlan:
    """What to OCR on one page: a scan, or the strips of one."""

    images: tuple[DrawnImage, ...]
    # Counter-clockwise degrees that turn the result upright as displayed.
    rotation: int
    # Other sizeable images on the page were left unread.
    pieced: bool


@dataclass
class _OcrOutcome:
    pages: list[int] = field(default_factory=list)
    failed: int = 0
    # Scans found but not read: the page limit, or the time budget mid-page.
    skipped: int = 0
    # Pages without text never examined: the time budget ran out, or OCR had
    # already stopped (no engine, busy, page limit), so walking them buys nothing.
    unchecked: int = 0
    # Pages stored as image pieces that could not be put back together.
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
        unreadable = 0
        for page in pages:
            if _remaining(started, clock) <= 0:
                break
            try:
                texts.append(page.extract_text() or "")
            except Exception as exc:
                # One malformed page is a page without text, not a failed upload:
                # the others keep their text, and it can still be read by OCR.
                logger.warning("PDF page text extraction failed ({})", type(exc).__name__)
                texts.append("")
                unreadable += 1
    except Exception as exc:
        logger.warning("PDF text extraction failed ({})", type(exc).__name__)
        return MediaExtraction(kind="document", metadata={"suffix": suffix}, error="pdf_extract_failed")
    if texts and unreadable == len(texts):
        return MediaExtraction(kind="document", metadata={"suffix": suffix}, error="pdf_extract_failed")
    timed_out = len(pages) - len(texts)
    pages = pages[: len(texts)]

    ocr = _ocr_scanned_pages(pages, texts, ocr_reader, started=started, clock=clock)
    missing = sum(not text.strip() for text in texts)
    truncated = total > PDF_PAGE_LIMIT
    return MediaExtraction(
        text="\n\n".join(texts).strip(),
        kind="document",
        metadata={
            "suffix": suffix,
            "engine": "pypdf",
            "pages_read": len(texts),
            "pages_total": total,
            "pages_without_text": missing,
            "pages_unreadable": unreadable,
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
            "warnings": _warnings(total=total, read=len(texts), timed_out=timed_out, missing=missing, ocr=ocr),
        },
        error="pdf_needs_ocr" if not any(text.strip() for text in texts) else None,
    )


def _warnings(*, total: int, read: int, timed_out: int, missing: int, ocr: _OcrOutcome) -> list[str]:
    warnings = []
    if total > PDF_PAGE_LIMIT:
        warnings.append(f"Only the first {PDF_PAGE_LIMIT} of {total} pages were read.")
    if timed_out:
        warnings.append(f"Reading stopped after {read} pages to stay within the upload time limit.")
    if ocr.pages:
        warnings.append(
            f"{len(ocr.pages)} scanned pages were read with OCR; check names and numbers against the original."
        )
    if ocr.pieced:
        warnings.append(
            f"{ocr.pieced} pages are stored as image layers or pieces that could not be put back together; "
            "text on them may be missing."
        )
    if missing:
        warnings.append(f"{missing} pages had no readable text.{_missing_reason(ocr)}")
    return warnings


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
            try:
                plan = _plan_page(pages[index])
            except Exception as exc:
                # A malformed page fails alone; it must not end the whole upload.
                logger.warning("PDF page planning failed ({})", type(exc).__name__)
                outcome.failed += 1
                continue
            if plan is None:
                continue
            if not plan.images:
                outcome.pieced += plan.pieced
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
            _read_page(index, text, plan, reader, texts, outcome, started=started, clock=clock)
    finally:
        if holding_slot:
            _OCR_SLOTS.release()
    outcome.engine = getattr(reader, "engine", None) if reader is not None else None
    if outcome.pages:
        logger.info("PDF OCR read {} scanned pages", len(outcome.pages))
    return outcome


def _read_page(
    index: int,
    text: str,
    plan: _PagePlan,
    reader: Any,
    texts: list[str],
    outcome: _OcrOutcome,
    *,
    started: float,
    clock: Callable[[], float],
) -> None:
    try:
        recognized = _read_plan(plan, reader, started=started, clock=clock)
    except _BudgetSpent:
        outcome.skipped += 1
        return
    except Exception as exc:
        # Type only: decoder and OCR messages can carry document content.
        logger.warning("PDF page OCR failed ({})", type(exc).__name__)
        outcome.failed += 1
        return
    if _looks_like_text(recognized):
        texts[index] = f"{text.strip()}\n{recognized.strip()}".strip()
        outcome.pages.append(index + 1)
        outcome.pieced += plan.pieced
    else:
        outcome.failed += 1


def _plan_page(page: Any) -> _PagePlan | None:
    drawing = drawn_images(page)
    plan = _plan_drawing(page, drawing.images)
    if drawing.complete:
        return plan
    # The walk stopped at its budget with more left to draw, so whatever is
    # read of this page, it is reported as partly read.
    return _PagePlan(plan.images if plan else (), plan.rotation if plan else 0, pieced=True)


def _plan_drawing(page: Any, images: list[DrawnImage]) -> _PagePlan | None:
    pieces = [image for image in images if image.pixels >= MIN_PIECE_PIXELS]
    if not pieces:
        return None
    total = sum(image.pixels for image in pieces)
    if len(pieces) > 1 and total <= pdf_images.MAX_SCAN_PIXELS and all(_assemblable(image) for image in pieces):
        # Strips or tiles of one scan: read them as one page. Together they are
        # held to the same threshold as a single image, so a few small graphics
        # are not mistaken for a scan.
        return None if total < MIN_SCAN_PIXELS else _PagePlan(tuple(pieces), _rotation(page, 0), pieced=False)
    largest = max(pieces, key=lambda image: image.pixels)
    if largest.pixels < MIN_SCAN_PIXELS:
        # One small image is a logo. Several that cannot be reassembled are a
        # page whose text is in pieces too small to read: report it.
        return None if len(pieces) == 1 else _PagePlan((), 0, pieced=True)
    drawn = pdf_images.orientation(largest.matrix)
    return _PagePlan((largest,), _rotation(page, drawn or 0), pieced=len(pieces) > 1)


def _assemblable(image: DrawnImage) -> bool:
    # Masked layers (mixed raster content) need compositing rules this does not
    # model; turned or skewed pieces need more than a paste.
    return not image.masked and pdf_images.is_upright(image.matrix)


def _rotation(page: Any, drawn: int) -> int:
    # The drawing matrix turns the stored image counter-clockwise; /Rotate then
    # turns the whole page clockwise for display. OCR wants what is displayed.
    try:
        turned = int(page.rotation or 0)
    except (TypeError, ValueError):
        # A malformed /Rotate is read as none, as viewers do.
        turned = 0
    return (drawn - turned) % 360


def _read_plan(plan: _PagePlan, reader: Any, *, started: float, clock: Callable[[], float]) -> str:
    def decode_piece(image: DrawnImage) -> Any:
        timeout = _step_timeout(started, clock)
        try:
            return decode(image, timeout=timeout)
        except DecodeTimeout as exc:
            if timeout < OCR_PAGE_TIMEOUT_SECONDS:
                raise _BudgetSpent from exc
            raise

    images = list(plan.images)
    picture = decode_piece(images[0]) if len(images) == 1 else compose(images, decode_piece)
    # Polarity is judged on the whole page: one dark strip is not an inverted page.
    if all(pdf_images.is_bilevel(image) for image in images):
        picture = fix_polarity(picture)
    if plan.rotation:
        picture = picture.rotate(plan.rotation, expand=True)
    timeout = _step_timeout(started, clock)
    try:
        return read_image_text(reader, picture, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if timeout < OCR_PAGE_TIMEOUT_SECONDS:
            raise _BudgetSpent from exc
        raise


def _step_timeout(started: float, clock: Callable[[], float]) -> float:
    timeout = min(OCR_PAGE_TIMEOUT_SECONDS, _remaining(started, clock))
    if timeout < _OCR_MIN_REMAINING_SECONDS:
        raise _BudgetSpent
    return timeout


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


def _looks_like_text(recognized: str) -> bool:
    # OCR run over a photograph returns stray marks. Keep a result only when it
    # holds some words, so a picture page is not indexed as noise.
    return sum(character.isalnum() for character in recognized) >= 8 and bool(_WORD.search(recognized))
