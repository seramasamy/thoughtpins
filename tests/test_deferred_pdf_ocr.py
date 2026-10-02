"""Scanned PDFs are read by a worker job, never inside the upload request.

With asynchronous processing on, the upload request reads only embedded text.
A PDF that needs OCR is saved and answered at once, with its document id, and a
durable ``pdf_ocr`` job reads it under the worker's longer limits. These tests
drive the real upload route. They catch the job at dispatch, rather than letting
the thread backend race the assertions, and then run it through the real job runner.
"""

from __future__ import annotations

import base64
import io
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from thoughtpins.media import extraction as media_extraction
from thoughtpins.media import pdf as pdf_module

SENTINEL = "QOWT5-HERON-LANTERN-SENTINEL-2e9a"
LEASE = f"Lease clause 4: rent is due on the first of each month {SENTINEL}"


class ScriptedReader:
    engine = "scripted"
    supports_timeout = True

    def __init__(self) -> None:
        self.answers: list[str] = []
        self.reads = 0

    def readtext(self, path: str, *, detail: int = 0, paragraph: bool = True, timeout: float = 30.0) -> list[str]:
        self.reads += 1
        return [self.answers.pop(0) if self.answers else ""]


def scan() -> Image.Image:
    image = Image.new("L", (1700, 2200), "white")
    ImageDraw.Draw(image).rectangle((100, 100, 1600, 400), fill="black")
    return image


def scanned_pdf(pages: int = 1) -> bytes:
    images = [scan() for _ in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def text_pdf(words: str) -> bytes:
    writer = PdfWriter()
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
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def worker_ocr(isolated_db, monkeypatch, tmp_path):
    from thoughtpins import library
    from thoughtpins.config import config

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(media_extraction.config, "vault_path", lambda: tmp_path / "vault")
    monkeypatch.setattr(config, "vault_path", lambda: tmp_path / "vault")
    for target in (config, type(config)):
        monkeypatch.setattr(target, "PDF_OCR_IN_WORKER", True)
    queued: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "thoughtpins.jobs.enqueue_ingestion_job", lambda job_id, user_id=None: queued.append((job_id, user_id))
    )
    reader = ScriptedReader()
    monkeypatch.setattr(media_extraction, "_get_ocr_reader", lambda **_: reader)
    return SimpleNamespace(queued=queued, reader=reader)


@pytest.fixture
def client(worker_ocr):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app

    return TestClient(app)


@pytest.fixture
def loguru_lines():
    from loguru import logger

    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG", backtrace=False, diagnose=False)
    yield lines
    logger.remove(sink)


def _upload(client, content: bytes, *, destination: str = "library", caption: str = "") -> dict[str, Any]:
    response = client.post(
        "/v1/uploads",
        json={
            "filename": "lease-scan.pdf",
            "media_type": "application/pdf",
            "destination": destination,
            "caption": caption,
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _run_queued(worker_ocr) -> list[str]:
    from thoughtpins.jobs import run_ingestion_job

    ran = []
    while worker_ocr.queued:
        job_id, user_id = worker_ocr.queued.pop(0)
        run_ingestion_job(job_id, user_id)
        ran.append(job_id)
    return ran


def _job(job_id: str):
    from thoughtpins.db import IngestionJob
    from thoughtpins.store import get_session

    with get_session() as session:
        job = session.get(IngestionJob, job_id)
        return SimpleNamespace(status=job.status, error=job.error, entry_id=job.entry_id, source=job.source)


def _document(document_id: str):
    from thoughtpins.db import DocumentChunk, DocumentSource, Memory
    from thoughtpins.store import get_session

    with get_session() as session:
        document = session.get(DocumentSource, document_id)
        if document is None:
            return None
        memories = session.query(Memory).filter(Memory.source_provenance == f"document:{document_id}").all()
        return SimpleNamespace(
            status=document.status,
            error=document.processing_error,
            text=document.raw_text,
            summary=document.summary,
            upload=(document.metadata_json or {}).get("upload") or {},
            chunks=session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count(),
            memory_types=sorted(memory.memory_type for memory in memories),
        )


def test_a_scanned_pdf_is_answered_at_once_and_read_by_the_worker(client, worker_ocr):
    worker_ocr.reader.answers = [LEASE]

    body = _upload(client, scanned_pdf())

    assert worker_ocr.reader.reads == 0, "the upload request ran OCR"
    assert body["status"] == "queued"
    assert body["extraction_status"] == "ocr_queued"
    assert body["route_type"] == "library_upload"
    assert body["document_id"] and body["job_id"] and body["entry_id"]
    assert body["metadata"]["extraction"]["ocr_deferred"] is True
    pending = _document(body["document_id"])
    assert pending.status == "processing" and pending.chunks == 0 and pending.memory_types == []
    assert client.get(f"/v1/library/{body['document_id']}").json()["status"] == "processing"
    assert [job_id for job_id, _ in worker_ocr.queued] == [body["job_id"]]

    _run_queued(worker_ocr)

    assert worker_ocr.reader.reads == 1
    done = _document(body["document_id"])
    assert done.status == "processed"
    assert "rent is due on the first" in done.text
    assert done.chunks >= 1 and "source_excerpt" in done.memory_types
    assert done.upload["extraction"]["ocr_pages"] == [1]
    assert _job(body["job_id"]).status == "completed"
    detail = client.get(f"/v1/library/{body['document_id']}").json()
    assert detail["status"] == "processed" and "rent is due" in detail["summary"]


def test_a_pdf_with_embedded_text_is_still_read_in_the_request(client, worker_ocr):
    body = _upload(client, text_pdf("Harbor ledger minutes for the spring meeting"))

    assert body["status"] == "processed"
    assert body["extraction_status"] == "processed"
    assert body["metadata"]["extraction"]["ocr_deferred"] is False
    assert worker_ocr.queued == [] and worker_ocr.reader.reads == 0


def test_a_scan_without_readable_text_ends_as_needs_text_never_stuck_processing(client, worker_ocr):
    worker_ocr.reader.answers = ["~~ ."]

    body = _upload(client, scanned_pdf())
    _run_queued(worker_ocr)

    done = _document(body["document_id"])
    assert done.status == "needs_text"
    assert "OCR could not read the scanned pages" in done.error
    assert done.chunks == 0 and done.memory_types == []
    job = _job(body["job_id"])
    assert job.status == "failed" and job.error == done.error
    assert client.get(f"/v1/library/{body['document_id']}").json()["status"] == "needs_text"


def test_a_journal_upload_saves_its_entry_once_the_worker_has_read_it(client, worker_ocr, monkeypatch):
    from thoughtpins.db import RawEntry
    from thoughtpins.llm import ExtractedMemory, ExtractionResult
    from thoughtpins.store import get_session

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message", lambda text: {"type": "journal_entry", "intent": "test"}
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(memories=[ExtractedMemory(memory_type="event", text=text)]),
    )
    worker_ocr.reader.answers = [LEASE]

    body = _upload(client, scanned_pdf(), destination="journal", caption="Scanned lease from the landlord")

    assert body["status"] == "queued" and body["extraction_status"] == "ocr_queued"
    assert body["route_type"] == "journal_upload"
    assert body["document_id"] is None and body["job_id"]
    _run_queued(worker_ocr)

    job = _job(body["job_id"])
    assert job.status == "completed" and job.entry_id
    with get_session() as session:
        entry = session.get(RawEntry, job.entry_id)
        assert "Scanned lease from the landlord" in entry.raw_text and "rent is due" in entry.raw_text


def test_uploading_the_same_scan_again_finds_the_same_source(client, worker_ocr):
    worker_ocr.reader.answers = [LEASE]
    content = scanned_pdf()

    first = _upload(client, content)
    again = _upload(client, content)

    assert again["document_id"] == first["document_id"] and again["job_id"] == first["job_id"]
    assert again["metadata"]["duplicate"] is True
    assert len(worker_ocr.queued) == 1
    _run_queued(worker_ocr)
    finished = _upload(client, content)
    assert finished["document_id"] == first["document_id"]
    assert finished["status"] == "processed" and finished["extraction_status"] == "processed"
    assert finished["job_id"] is None and worker_ocr.queued == []


def test_a_source_deleted_before_the_worker_runs_is_not_brought_back(client, worker_ocr):
    worker_ocr.reader.answers = [LEASE]
    body = _upload(client, scanned_pdf())

    assert client.delete(f"/v1/entries/{body['entry_id']}").status_code == 200
    _run_queued(worker_ocr)

    assert _document(body["document_id"]) is None
    assert worker_ocr.reader.reads == 0, "a deleted upload was still read"


def test_a_pdf_that_keeps_outliving_the_time_limit_is_finished_as_unreadable(client, worker_ocr):
    from thoughtpins.db import IngestionJob
    from thoughtpins.pdf_ocr_jobs import MAX_ATTEMPTS
    from thoughtpins.store import get_session

    worker_ocr.reader.answers = [LEASE]
    body = _upload(client, scanned_pdf())
    with get_session() as session:
        job = session.get(IngestionJob, body["job_id"])
        job.metadata_json = dict(job.metadata_json or {}) | {"attempts": MAX_ATTEMPTS}
        session.commit()

    _run_queued(worker_ocr)

    done = _document(body["document_id"])
    assert done.status == "needs_text" and "took too long to read" in done.error
    assert worker_ocr.reader.reads == 0


def test_the_worker_reads_past_the_request_limits_and_needs_no_ocr_slot(monkeypatch):
    reader = ScriptedReader()
    reader.answers = ["first scanned page words", "second scanned page words"]
    monkeypatch.setattr(pdf_module, "OCR_PAGE_LIMIT", 1)
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(pdf_module, "_OCR_SLOTS", full)

    in_request = pdf_module.extract_pdf_text(scanned_pdf(2), ".pdf", ocr_reader=lambda: reader)
    in_worker = pdf_module.extract_pdf_text(
        scanned_pdf(2), ".pdf", ocr_reader=lambda: reader, limits=pdf_module.worker_limits()
    )

    assert in_request.metadata["ocr_busy"] is True and in_request.metadata["ocr_pages"] == []
    assert in_worker.metadata["ocr_busy"] is False and in_worker.metadata["ocr_pages"] == [1, 2]
    assert pdf_module.worker_limits().time_budget_seconds > pdf_module.request_limits().time_budget_seconds


def test_the_worker_job_reads_under_the_worker_limits(client, worker_ocr, monkeypatch):
    """Request limits here would read nothing: no OCR slot is free and the page cap is zero."""
    worker_ocr.reader.answers = [LEASE]
    body = _upload(client, scanned_pdf())
    monkeypatch.setattr(pdf_module, "OCR_PAGE_LIMIT", 0)
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(pdf_module, "_OCR_SLOTS", full)

    _run_queued(worker_ocr)

    assert _document(body["document_id"]).status == "processed"
    assert worker_ocr.reader.reads == 1


def test_deferring_stops_at_the_first_scan_without_reading_it():
    reader = ScriptedReader()

    result = pdf_module.extract_pdf_text(scanned_pdf(3), ".pdf", ocr_reader=lambda: reader, defer_ocr=True)

    assert reader.reads == 0
    assert result.metadata["ocr_deferred"] is True
    assert any("being read with OCR" in warning for warning in result.metadata["warnings"])


def test_ocr_text_never_reaches_a_log_line(client, worker_ocr, loguru_lines):
    worker_ocr.reader.answers = [LEASE]

    body = _upload(client, scanned_pdf(), caption=f"Caption mentioning {SENTINEL}")
    _run_queued(worker_ocr)

    assert _document(body["document_id"]).status == "processed"
    rendered = "\n".join(loguru_lines)
    assert "Worker PDF OCR read 1 pages" in rendered, "captured nothing from the worker, so this proves nothing"
    assert SENTINEL not in rendered


def test_production_requires_scanned_pdfs_to_be_read_off_the_request(monkeypatch) -> None:
    from thoughtpins.config import Config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "PDF_OCR_IN_WORKER", False)

    assert "PDF_OCR_IN_WORKER must be true outside local development." in Config.validate_startup()
