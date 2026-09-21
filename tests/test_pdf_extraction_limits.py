"""Real synthetic PDFs verify the boundary between saved and actually read."""

from __future__ import annotations

import io

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from thoughtpins.media import extract_document_text


def _pdf(*, count: int, blank_last: bool = False) -> bytes:
    writer = PdfWriter()
    for number in range(count):
        page = writer.add_blank_page(width=612, height=792)
        if blank_last and number == count - 1:
            continue
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
        stream.set_data(f"BT /F1 24 Tf 60 700 Td (SYNTHETIC PAGE {number + 1}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    content = io.BytesIO()
    writer.write(content)
    return content.getvalue()


def test_pdf_limit_reports_partial_content_instead_of_silent_success():
    result = extract_document_text(_pdf(count=101), ".pdf")
    assert result.ok
    assert "SYNTHETIC PAGE 100" in result.text
    assert "SYNTHETIC PAGE 101" not in result.text
    assert result.metadata["partial"] is True
    assert result.metadata["pages_total"] == 101
    assert result.metadata["warnings"] == ["Only the first 100 of 101 pages were read."]


def test_mixed_pdf_identifies_pages_without_text():
    result = extract_document_text(_pdf(count=2, blank_last=True), ".pdf")
    assert result.ok
    assert result.metadata["pages_without_text"] == 1
    assert result.metadata["partial"] is True


def test_image_only_or_blank_pdf_requests_ocr():
    result = extract_document_text(_pdf(count=1, blank_last=True), ".pdf")
    assert not result.ok
    assert result.error == "pdf_needs_ocr"
