"""Scanned PDF pages are read with OCR, boundedly, and never at the cost of real text.

Before this, a scanned PDF saved with "no selectable text" and the person was
asked to photograph each page. The PDFs here are real -- page images made with
Pillow, text pages made with pypdf -- and the OCR engine is scripted, because
Tesseract is exercised for real by the image build (scripts/check_media_runtime.py).
"""

from __future__ import annotations

import base64
import io
import subprocess
import time
from typing import Any

import pytest
from PIL import Image, ImageDraw, ImageStat
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from thoughtpins.media import extract_document_text
from thoughtpins.media import extraction as media_extraction
from thoughtpins.media import pdf as pdf_module
from thoughtpins.media.ocr import TesseractReader, read_image_text


class ScriptedReader:
    engine = "scripted"
    supports_timeout = True

    def __init__(self, answers: list[str | Exception] | None = None, *, on_read=None) -> None:
        self.answers = list(answers or [])
        self.sizes: list[tuple[int, int]] = []
        self.timeouts: list[float] = []
        self.on_read = on_read

    def readtext(self, path: str, *, detail: int = 0, paragraph: bool = True, timeout: float = 30.0) -> list[str]:
        with Image.open(path) as image:
            self.sizes.append(image.size)
        self.timeouts.append(timeout)
        if self.on_read:
            self.on_read()
        answer = self.answers.pop(0) if self.answers else ""
        if isinstance(answer, Exception):
            raise answer
        return [answer]


def scan(size: tuple[int, int] = (1700, 2200), mode: str = "L") -> Image.Image:
    image = Image.new(mode, size, "white")
    ImageDraw.Draw(image).rectangle((100, 100, size[0] - 100, 400), fill="black")
    return image


def scanned_pdf(*pages: Image.Image) -> bytes:
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=list(pages[1:]))
    return buffer.getvalue()


def text_page(writer: PdfWriter, words: str) -> None:
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 18 Tf 60 700 Td ({words}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)


def written(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def use_reader(monkeypatch, reader: Any) -> None:
    monkeypatch.setattr(media_extraction, "_get_ocr_reader", lambda **_: reader)


def test_a_scanned_page_is_read_with_ocr(monkeypatch):
    reader = ScriptedReader(["Receipt total 42.10 paid to Harbor Books"])
    use_reader(monkeypatch, reader)

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert result.ok, result.error
    assert "Receipt total 42.10 paid to Harbor Books" in result.text
    assert result.metadata["ocr_pages"] == [1]
    assert result.metadata["ocr_engine"] == "scripted"
    assert result.metadata["pages_without_text"] == 0
    assert result.metadata["partial"] is False
    assert reader.sizes == [(1700, 2200)]
    assert any("read with OCR" in warning for warning in result.metadata["warnings"])


def test_embedded_text_is_never_replaced_and_only_scans_are_read(monkeypatch):
    reader = ScriptedReader(["Scanned appendix: tide table for March"])
    use_reader(monkeypatch, reader)
    writer = PdfWriter()
    text_page(writer, "SYNTHETIC PAGE ONE")
    writer.add_page(PdfReader(io.BytesIO(scanned_pdf(scan()))).pages[0])

    result = extract_document_text(written(writer), ".pdf")

    assert result.ok
    assert len(reader.sizes) == 1, "the text page must not be sent to OCR"
    assert result.text.index("SYNTHETIC PAGE ONE") < result.text.index("Scanned appendix")
    assert result.metadata["ocr_pages"] == [2]


def test_ocr_stops_at_the_page_limit_and_says_so(monkeypatch):
    monkeypatch.setattr(pdf_module, "OCR_PAGE_LIMIT", 2)
    use_reader(monkeypatch, ScriptedReader(["page one text", "page two text", "never read"]))

    result = extract_document_text(scanned_pdf(scan(), scan(), scan()), ".pdf")

    assert result.metadata["ocr_pages"] == [1, 2]
    # Once the limit is reached the rest are not even examined.
    assert result.metadata["ocr_unchecked_pages"] == 1
    assert result.metadata["partial"] is True
    assert "never read" not in result.text
    assert any("1 pages were not reached" in warning for warning in result.metadata["warnings"])


def test_ocr_stops_inside_the_time_budget():
    now = [0.0]

    def slow_page() -> None:
        now[0] += 25.0

    reader = ScriptedReader(["first page words", "second page words", "third page words"], on_read=slow_page)

    result = pdf_module.extract_pdf_text(
        scanned_pdf(scan(), scan(), scan()), ".pdf", ocr_reader=lambda: reader, clock=lambda: now[0]
    )

    # 40 s budget: page 1 at 0 s, page 2 with 15 s left, page 3 with none, so
    # page 3 is not even examined -- finding its scan would cost time too.
    assert result.metadata["ocr_pages"] == [1, 2]
    assert result.metadata["ocr_unchecked_pages"] == 1
    assert result.metadata["ocr_skipped_pages"] == 0
    assert "third" not in result.text
    # Each page's OCR is held to what is left of the budget, not a flat 30 s.
    assert reader.timeouts == [30.0, 15.0]


def test_unavailable_ocr_is_reported_not_hidden(monkeypatch):
    def missing(**_: Any) -> Any:
        raise ImportError("no OCR engine")

    monkeypatch.setattr(media_extraction, "_get_ocr_reader", missing)

    result = extract_document_text(scanned_pdf(scan(), scan()), ".pdf")

    assert result.error == "pdf_needs_ocr"
    assert result.metadata["ocr_skipped_pages"] == 1
    assert result.metadata["ocr_unchecked_pages"] == 1
    assert any("not set up on this server" in warning for warning in result.metadata["warnings"])


def test_an_oversized_scan_is_refused_before_it_is_decoded(monkeypatch):
    monkeypatch.setattr(pdf_module, "MAX_SCAN_PIXELS", 1_000_000)
    reader = ScriptedReader(["never read"])
    use_reader(monkeypatch, reader)

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert reader.sizes == [], "a scan over the limit is never decoded or sent to OCR"
    assert result.metadata["ocr_failed_pages"] == 1
    assert result.error == "pdf_needs_ocr"


def test_a_small_logo_is_not_mistaken_for_a_scan(monkeypatch):
    reader = ScriptedReader(["logo text"])
    use_reader(monkeypatch, reader)

    result = extract_document_text(scanned_pdf(scan(size=(300, 200))), ".pdf")

    assert reader.sizes == []
    assert result.error == "pdf_needs_ocr"


def test_a_scan_wrapped_in_a_form_object_is_read(monkeypatch):
    reader = ScriptedReader(["Wrapped scan text"])
    use_reader(monkeypatch, reader)
    source = PdfReader(io.BytesIO(scanned_pdf(scan())))
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    image = writer._add_object(source.pages[0]["/Resources"]["/XObject"].get_object()["/image"].get_object())
    form = DecodedStreamObject()
    form.set_data(b"q 612 0 0 792 0 0 cm /Im1 Do Q")
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(612), NumberObject(792)]),
            NameObject("/Resources"): DictionaryObject(
                {NameObject("/XObject"): DictionaryObject({NameObject("/Im1"): image})}
            ),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Fm0"): writer._add_object(form)})}
    )
    content = DecodedStreamObject()
    content.set_data(b"q /Fm0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(content)

    result = extract_document_text(written(writer), ".pdf")

    assert result.ok
    assert "Wrapped scan text" in result.text
    assert reader.sizes == [(1700, 2200)]


def test_one_unreadable_page_does_not_lose_the_others(monkeypatch):
    use_reader(monkeypatch, ScriptedReader([RuntimeError("engine crashed"), "second page text"]))

    result = extract_document_text(scanned_pdf(scan(), scan()), ".pdf")

    assert result.ok
    assert result.metadata["ocr_pages"] == [2]
    assert result.metadata["ocr_failed_pages"] == 1
    assert result.metadata["pages_without_text"] == 1
    assert result.metadata["partial"] is True


def test_large_scans_are_downscaled_before_ocr(monkeypatch):
    reader = ScriptedReader(["high resolution page"])
    use_reader(monkeypatch, reader)

    result = extract_document_text(scanned_pdf(scan(size=(4500, 5800))), ".pdf")

    assert result.ok
    assert max(reader.sizes[0]) <= pdf_module.OCR_LONG_SIDE


def test_tesseract_receives_the_remaining_budget_as_its_timeout(monkeypatch):
    from thoughtpins.media import ocr

    seen: dict[str, Any] = {}

    class Completed:
        stdout = b"tesseract words"

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return Completed()

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)

    text = read_image_text(TesseractReader("tesseract"), scan(size=(400, 300)), timeout=12.5)

    assert text == "tesseract words"
    assert seen["timeout"] == 12.5
    assert seen["env"]["OMP_THREAD_LIMIT"] == "1"


@pytest.fixture
def upload_client(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import library
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(media_extraction.config, "vault_path", lambda: tmp_path / "vault")
    monkeypatch.setattr(config, "vault_path", lambda: tmp_path / "vault")
    return TestClient(app)


def test_an_uploaded_scanned_pdf_becomes_a_readable_source(upload_client, monkeypatch):
    use_reader(monkeypatch, ScriptedReader(["Lease clause 4: rent is due on the first"]))

    response = upload_client.post(
        "/v1/uploads",
        json={
            "filename": "lease-scan.pdf",
            "media_type": "application/pdf",
            "destination": "library",
            "content_base64": base64.b64encode(scanned_pdf(scan())).decode("ascii"),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route_type"] == "library_upload"
    assert body["extraction_status"] == "processed"
    assert body["document_id"]
    assert body["metadata"]["extraction"]["ocr_pages"] == [1]


def image_xobject(writer: PdfWriter, size: tuple[int, int]) -> Any:
    source = PdfReader(io.BytesIO(scanned_pdf(scan(size=size))))
    return writer._add_object(source.pages[0]["/Resources"]["/XObject"].get_object()["/image"].get_object())


def drawing_page(writer: PdfWriter, resources: DictionaryObject, operations: bytes) -> None:
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = resources
    content = DecodedStreamObject()
    content.set_data(operations)
    page[NameObject("/Contents")] = writer._add_object(content)


def test_pages_sharing_one_resource_dictionary_each_read_their_own_image(monkeypatch):
    """Some producers list every page's image on every page; only drawn images count."""

    reader = ScriptedReader(["first scanned page words", "second scanned page words"])
    use_reader(monkeypatch, reader)
    writer = PdfWriter()
    shared = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {
                    NameObject("/ImA"): image_xobject(writer, (1700, 2200)),
                    NameObject("/ImB"): image_xobject(writer, (1600, 2100)),
                }
            )
        }
    )
    drawing_page(writer, shared, b"q 612 0 0 792 0 0 cm /ImA Do Q")
    drawing_page(writer, shared, b"q 612 0 0 792 0 0 cm /ImB Do Q")

    result = extract_document_text(written(writer), ".pdf")

    assert reader.sizes == [(1700, 2200), (1600, 2100)]
    assert result.metadata["ocr_pages"] == [1, 2]


def test_a_self_referencing_form_cannot_make_the_walk_expensive(monkeypatch):
    """1,000 references to one form, nested in itself, once fanned out to ~1e9 visits."""

    use_reader(monkeypatch, ScriptedReader())
    writer = PdfWriter()
    form = DecodedStreamObject()
    form.set_data(b" ".join(f"/F{i} Do".encode() for i in range(1000)))
    form_ref = writer._add_object(form)
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(612), NumberObject(792)]),
            NameObject("/Resources"): DictionaryObject(
                {NameObject("/XObject"): DictionaryObject({NameObject(f"/F{i}"): form_ref for i in range(1000)})}
            ),
        }
    )
    resources = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/F0"): form_ref})})
    drawing_page(writer, resources, b"/F0 Do")

    started = time.perf_counter()
    result = extract_document_text(written(writer), ".pdf")

    assert time.perf_counter() - started < 5
    assert result.error == "pdf_needs_ocr"


def test_a_jpeg_that_understates_its_size_is_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(pdf_module, "MAX_SCAN_PIXELS", 1_000_000)
    reader = ScriptedReader(["never decoded"])
    use_reader(monkeypatch, reader)
    source = PdfReader(io.BytesIO(scanned_pdf(scan(size=(2000, 2000)))))
    writer = PdfWriter()
    writer.add_page(source.pages[0])
    image = writer.pages[0]["/Resources"]["/XObject"].get_object()["/image"].get_object()
    # The PDF claims 500x500 (under the limit); the JPEG itself is 2000x2000.
    image[NameObject("/Width")] = NumberObject(500)
    image[NameObject("/Height")] = NumberObject(500)

    result = extract_document_text(written(writer), ".pdf")

    assert reader.sizes == []
    assert result.metadata["ocr_failed_pages"] == 1


def test_an_engine_that_cannot_be_timed_out_is_not_used_for_pdfs(monkeypatch):
    class UnboundedReader(ScriptedReader):
        supports_timeout = False

    reader = UnboundedReader(["would run without a limit"])
    use_reader(monkeypatch, reader)

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert reader.sizes == []
    assert result.metadata["ocr_unavailable"] is True
    assert result.error == "pdf_needs_ocr"


def test_marks_recognised_in_a_photograph_are_not_kept_as_text(monkeypatch):
    use_reader(monkeypatch, ScriptedReader(["~ | . ;"]))

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert result.error == "pdf_needs_ocr"
    assert result.metadata["ocr_failed_pages"] == 1


def test_a_page_cut_off_by_the_budget_counts_as_skipped_not_failed():
    ticks = iter([0.0] + [20.0] * 50)
    reader = ScriptedReader([subprocess.TimeoutExpired("tesseract", 20)])

    result = pdf_module.extract_pdf_text(
        scanned_pdf(scan()), ".pdf", ocr_reader=lambda: reader, clock=lambda: next(ticks)
    )

    assert reader.timeouts == [20.0]
    assert result.metadata["ocr_skipped_pages"] == 1
    assert result.metadata["ocr_failed_pages"] == 0


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"ocr_unavailable": True}, "not set up on this server"),
        ({"ocr_busy": True}, "busy with other uploads"),
        ({"ocr_skipped_pages": 2}, "more OCR time"),
        ({"ocr_unchecked_pages": 1}, "more OCR time"),
        ({"pages_timed_out": 3}, "more OCR time"),
        ({"ocr_failed_pages": 1}, "OCR could not read"),
        ({}, "No readable text was found"),
    ],
)
def test_the_no_text_message_says_what_actually_happened(metadata, expected):
    from thoughtpins.media import MediaExtraction
    from thoughtpins.uploads import _human_extraction_error

    message = _human_extraction_error(
        MediaExtraction(kind="document", metadata=metadata, error="pdf_needs_ocr"), "document"
    )

    assert expected in message


def test_ocr_is_refused_rather_than_queued_when_every_slot_is_busy(monkeypatch):
    """Scanned uploads may not occupy every request worker for the whole budget."""

    import threading

    reader = ScriptedReader(["would have been read"])
    use_reader(monkeypatch, reader)
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(pdf_module, "_OCR_SLOTS", full)

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert reader.sizes == []
    assert result.metadata["ocr_busy"] is True
    assert result.error == "pdf_needs_ocr"


def test_a_page_turned_by_rotate_is_read_upright(monkeypatch):
    class EdgeReader(ScriptedReader):
        """Records where the dark band drawn along the scan's top edge ended up."""

        def readtext(self, path: str, **kwargs: Any) -> list[str]:
            with Image.open(path) as image:
                width, height = image.size
                self.right_edge = ImageStat.Stat(image.crop((width - 400, 0, width - 100, height))).mean[0]
                self.left_edge = ImageStat.Stat(image.crop((100, 0, 400, height))).mean[0]
            return super().readtext(path, **kwargs)

    reader = EdgeReader(["landscape ledger page"])
    use_reader(monkeypatch, reader)
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(scanned_pdf(scan()))).pages[0])
    writer.pages[0].rotate(90)

    result = extract_document_text(written(writer), ".pdf")

    assert result.ok
    # Stored 1700x2200; displayed, and so read, turned a quarter clockwise --
    # which carries the band along the top edge to the right-hand side.
    assert reader.sizes == [(2200, 1700)]
    assert reader.right_edge < reader.left_edge, "rotated the wrong way"


def test_text_extraction_itself_stops_at_the_time_budget():
    ticks = iter([0.0, 0.0, 0.0] + [60.0] * 200)
    writer = PdfWriter()
    for number in range(5):
        text_page(writer, f"TEXT PAGE {number + 1} WITH ENOUGH EMBEDDED WORDS TO NEED NO OCR AT ALL")

    result = pdf_module.extract_pdf_text(written(writer), ".pdf", ocr_reader=ScriptedReader, clock=lambda: next(ticks))

    assert result.ok
    assert result.metadata["pages_read"] == 2
    assert result.metadata["pages_timed_out"] == 3
    assert result.metadata["partial"] is True
    assert "TEXT PAGE 3" not in result.text


def test_uploads_extract_before_taking_the_account_lock(monkeypatch):
    """OCR can take 40 s; the account row lock, which deletion waits on, must not be held."""

    from thoughtpins import uploads
    from thoughtpins.media import MediaExtraction

    order: list[str] = []

    def extract(content, *, filename, media_type, media_kind):
        order.append("extract")
        return MediaExtraction(kind="document", error="pdf_needs_ocr")

    def lock(session, user_id):
        order.append("lock")

    monkeypatch.setattr(uploads, "_extract", extract)
    monkeypatch.setattr(uploads, "lock_active_user_for_write", lock)
    monkeypatch.setattr(uploads, "save_media_attachment", lambda content, **kwargs: None)

    uploads.ingest_upload(object(), user_id="user-1", filename="scan.pdf", content=b"%PDF")

    assert order == ["extract", "lock"]


def test_the_ocr_engine_is_built_once_under_concurrent_first_use(monkeypatch):
    import threading

    monkeypatch.setattr(media_extraction, "_ocr_reader", None)
    monkeypatch.setattr(media_extraction.shutil, "which", lambda name: "tesseract")
    barrier = threading.Barrier(8)
    seen: list[Any] = []

    def first_use() -> None:
        barrier.wait()
        seen.append(media_extraction._get_ocr_reader())

    threads = [threading.Thread(target=first_use) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(reader) for reader in seen}) == 1


def strips_pdf(count: int, size: tuple[int, int]) -> bytes:
    """One page drawing `count` image strips stacked down the page, as some scanners store it."""

    writer = PdfWriter()
    xobjects = DictionaryObject()
    drawing = []
    for index in range(count):
        name = f"/S{index}"
        xobjects[NameObject(name)] = image_xobject(writer, size)
        drawing.append(f"q 612 0 0 {792 // count} 0 {index * (792 // count)} cm {name} Do Q")
    drawing_page(writer, DictionaryObject({NameObject("/XObject"): xobjects}), " ".join(drawing).encode())
    return written(writer)


def test_a_page_stored_as_strips_is_reported_as_partly_read(monkeypatch):
    use_reader(monkeypatch, ScriptedReader(["one strip of the page"]))

    result = extract_document_text(strips_pdf(4, (1700, 550)), ".pdf")

    assert result.metadata["ocr_pages"] == [1]
    assert result.metadata["ocr_pieced_pages"] == 1
    assert result.metadata["partial"] is True
    assert any("several image strips" in warning for warning in result.metadata["warnings"])


def test_strips_too_small_to_read_are_still_reported(monkeypatch):
    reader = ScriptedReader(["never read"])
    use_reader(monkeypatch, reader)

    result = extract_document_text(strips_pdf(8, (1700, 110)), ".pdf")

    assert reader.sizes == []
    assert result.metadata["ocr_pieced_pages"] == 1
    assert result.error == "pdf_needs_ocr"


def test_once_ocr_is_busy_the_remaining_pages_are_not_walked(monkeypatch):
    import threading

    use_reader(monkeypatch, ScriptedReader(["would have been read"]))
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(pdf_module, "_OCR_SLOTS", full)
    walks: list[int] = []
    original = pdf_module._largest_drawn_image

    def counting(page: Any) -> Any:
        walks.append(1)
        return original(page)

    monkeypatch.setattr(pdf_module, "_largest_drawn_image", counting)

    result = extract_document_text(scanned_pdf(scan(), scan(), scan()), ".pdf")

    assert len(walks) == 1
    assert result.metadata["ocr_busy"] is True
    assert result.metadata["ocr_unchecked_pages"] == 2


def test_a_large_content_stream_is_refused_before_it_is_parsed(monkeypatch):
    from pypdf import PageObject

    monkeypatch.setattr(pdf_module, "MAX_SCAN_CONTENT_BYTES", 10)
    reader = ScriptedReader(["never read"])
    use_reader(monkeypatch, reader)
    parsed: list[int] = []
    original = PageObject.get_contents

    def spying(self: Any) -> Any:
        parsed.append(1)
        return original(self)

    monkeypatch.setattr(PageObject, "get_contents", spying)

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert parsed == [], "the size guard must run before the content stream is parsed"
    assert reader.sizes == []
    assert result.error == "pdf_needs_ocr"


def test_a_pdf_never_loads_an_ocr_engine_it_would_refuse(monkeypatch):
    """Without Tesseract, building EasyOCR (a large model) only to reject it held the request."""

    import sys
    import types

    built: list[str] = []
    fake = types.ModuleType("easyocr")
    fake.Reader = lambda *args, **kwargs: built.append("easyocr")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "easyocr", fake)
    monkeypatch.setattr(media_extraction, "_ocr_reader", None)
    monkeypatch.setattr(media_extraction.shutil, "which", lambda name: None)

    result = extract_document_text(scanned_pdf(scan()), ".pdf")

    assert built == []
    assert result.metadata["ocr_unavailable"] is True
