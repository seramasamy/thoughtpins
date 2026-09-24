"""Word and PowerPoint uploads are read as documents, boundedly and truthfully.

Before this, a .docx or .pptx fell through to the "does it look like text"
heuristic, failed it, and the person was told to export a PDF. The fixtures
here are built in memory from the Office Open XML parts real editors write, so
they exercise revision marks, field codes, text boxes, notes and slide order
without committing binary documents.
"""

from __future__ import annotations

import base64
import io
import zipfile

import pytest

from thoughtpins.media import extract_document_text, office
from thoughtpins.media import extraction as media_extraction

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def rels(*entries: tuple[str, str, str] | tuple[str, str, str, str]) -> str:
    body = "".join(
        f'<Relationship Id="{entry[0]}" Type="{R}/{entry[1]}" Target="{entry[2]}"'
        + (f' TargetMode="{entry[3]}"' if len(entry) > 3 else "")
        + "/>"
        for entry in entries
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG}">{body}</Relationships>'


def package(parts: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        )
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def paragraph(*runs: str) -> str:
    return f"<w:p>{''.join(runs)}</w:p>"


def docx(body: str, *, footnotes: str | None = None, document_prolog: str = "") -> bytes:
    document = (
        f'{document_prolog}<w:document xmlns:w="{W}" xmlns:mc="{MC}" xmlns:r="{R}"><w:body>{body}<w:sectPr/></w:body>'
        "</w:document>"
    )
    parts: dict[str, str | bytes] = {
        "_rels/.rels": rels(("rId1", "officeDocument", "word/document.xml")),
        "word/document.xml": document,
        "word/_rels/document.xml.rels": rels(
            ("rId1", "footnotes", "footnotes.xml"),
            ("rId2", "hyperlink", "https://example.com/syllabus", "External"),
            ("rId3", "image", "../../../outside.png"),
        ),
    }
    if footnotes is not None:
        parts["word/footnotes.xml"] = f'<w:footnotes xmlns:w="{W}">{footnotes}</w:footnotes>'
    return package(parts)


HOMEWORK = "".join(
    [
        paragraph(run("Homework 3: Orbital mechanics")),
        paragraph(
            run("Kepler's third law "),
            f"<w:ins>{run('relates period to axis.')}</w:ins>",
            "<w:del><w:r><w:delText>DELETED DRAFT SENTENCE</w:delText></w:r></w:del>",
        ),
        paragraph(
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>',
            '<w:r><w:instrText xml:space="preserve"> HYPERLINK "https://example.com" </w:instrText></w:r>',
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>',
            run("Course page"),
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>',
        ),
        "<w:tbl><w:tblPr/>"
        f"<w:tr><w:tc>{paragraph(run('Planet'))}</w:tc><w:tc>{paragraph(run('Period'))}</w:tc></w:tr>"
        f"<w:tr><w:tc>{paragraph(run('Mars'))}</w:tc><w:tc>{paragraph(run('687 days'))}</w:tc></w:tr>"
        "</w:tbl>",
        paragraph(
            "<w:r><mc:AlternateContent>"
            f'<mc:Choice Requires="wps"><w:drawing><w:txbxContent>{paragraph(run("Margin box: check units"))}'
            "</w:txbxContent></w:drawing></mc:Choice>"
            f"<mc:Fallback><w:pict><w:txbxContent>{paragraph(run('Margin box: check units'))}</w:txbxContent>"
            "</w:pict></mc:Fallback>"
            "</mc:AlternateContent></w:r>"
        ),
        paragraph(run("Line one"), "<w:r><w:br/></w:r>", run("line two")),
    ]
)
FOOTNOTES = (
    f'<w:footnote w:type="separator" w:id="-1">{paragraph("<w:r><w:separator/></w:r>")}</w:footnote>'
    f'<w:footnote w:id="1">{paragraph(run("Source: lecture 4 handout."))}</w:footnote>'
)


def test_docx_reads_what_the_author_sees_and_nothing_they_removed():
    result = extract_document_text(docx(HOMEWORK, footnotes=FOOTNOTES), ".docx")

    assert result.ok, result
    text = result.text
    assert "Homework 3: Orbital mechanics" in text
    assert "Kepler's third law relates period to axis." in text
    assert "Course page" in text
    assert "Planet | Period" in text
    assert "Mars | 687 days" in text
    assert "Line one\nline two" in text
    assert "Source: lecture 4 handout." in text
    # A tracked deletion, a field instruction and a duplicate fallback rendering
    # are not document text.
    assert "DELETED DRAFT" not in text
    assert "HYPERLINK" not in text
    assert text.count("Margin box: check units") == 1
    assert result.metadata["engine"] == "ooxml"
    assert result.metadata["tables"] == 1
    assert result.metadata["notes"] == 1
    assert result.metadata["partial"] is False


def test_pptx_follows_presentation_order_and_keeps_speaker_notes():
    def slide(*paragraphs: str) -> str:
        shapes = "".join(
            f"<p:sp><p:nvSpPr><p:nvPr/></p:nvSpPr><p:txBody>{body}</p:txBody></p:sp>" for body in paragraphs
        )
        return (
            f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:mc="{MC}"><p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>'
        )

    def para(*runs: str) -> str:
        return (
            "<a:p>"
            + "".join(f"<a:r><a:t>{text}</a:t></a:r>" if text != "<br>" else "<a:br/>" for text in runs)
            + "</a:p>"
        )

    notes = (
        f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree>'
        '<p:sp><p:nvSpPr><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr></p:sp>'
        f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:txBody>{para("Mention eccentricity")}'
        "</p:txBody></p:sp>"
        f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="sldNum" idx="5"/></p:nvPr></p:nvSpPr><p:txBody>{para("99")}'
        "</p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:notes>"
    )
    duplicated = (
        "<mc:AlternateContent>"
        f'<mc:Choice Requires="a14"><p:sp><p:txBody>{para("Equation: T2 = a3")}</p:txBody></p:sp></mc:Choice>'
        f"<mc:Fallback><p:sp><p:txBody>{para('Equation: T2 = a3')}</p:txBody></p:sp></mc:Fallback>"
        "</mc:AlternateContent>"
    )
    results_slide = slide(para("Results"), para("Mars", "<br>", "687 days")).replace(
        "</p:spTree>", duplicated + "</p:spTree>"
    )
    content = package(
        {
            "_rels/.rels": rels(("rId1", "officeDocument", "ppt/presentation.xml")),
            "ppt/presentation.xml": (
                f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'
                '<p:sldId id="256" r:id="rId3"/><p:sldId id="257" r:id="rId2"/><p:sldId id="258" r:id="rId4"/>'
                "</p:sldIdLst></p:presentation>"
            ),
            "ppt/_rels/presentation.xml.rels": rels(
                ("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                ("rId2", "slide", "slides/slide1.xml"),
                ("rId3", "slide", "slides/slide2.xml"),
                ("rId4", "slide", "slides/slide3.xml"),
            ),
            "ppt/slides/slide1.xml": results_slide,
            "ppt/slides/_rels/slide1.xml.rels": rels(
                ("rId1", "notesSlide", "../notesSlides/notesSlide1.xml"),
                ("rId2", "hyperlink", "https://example.com", "External"),
            ),
            "ppt/slides/slide2.xml": slide(para("Agenda"), para("Review Kepler")),
            "ppt/slides/slide3.xml": slide(),
            "ppt/notesSlides/notesSlide1.xml": notes,
        }
    )

    result = extract_document_text(content, ".pptx")

    assert result.ok, result
    assert result.text.split("\n\n") == [
        "Slide 1\nAgenda\nReview Kepler",
        "Slide 2\nResults\nMars\n687 days\nEquation: T2 = a3\nSpeaker notes: Mention eccentricity",
    ]
    assert result.metadata["slides_total"] == 3
    assert result.metadata["slides_with_notes"] == 1
    assert result.metadata["slides_without_text"] == 1
    # An image-only slide is content that was not read, so the result says so.
    assert result.metadata["partial"] is True
    assert "1 slides had no readable text" in result.metadata["warnings"][0]


BILLION_LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
)


def test_a_part_declaring_a_dtd_is_refused_before_any_expansion():
    result = extract_document_text(docx(paragraph(run("&lol3;")), document_prolog=BILLION_LAUGHS), ".docx")

    assert result.error == "office_extract_failed"
    assert result.text == ""


def test_a_utf16_dtd_is_refused_as_well():
    """A byte search for <!DOCTYPE would miss this; the parser does not."""

    document = f'<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY x "boom">]><w:document xmlns:w="{W}"/>'
    content = package(
        {
            "_rels/.rels": rels(("rId1", "officeDocument", "word/document.xml")),
            "word/document.xml": document.encode("utf-16"),
        }
    )

    assert b"<!DOCTYPE" not in document.encode("utf-16")
    assert extract_document_text(content, ".docx").error == "office_extract_failed"


def test_oversized_parts_and_packages_are_refused(monkeypatch):
    large = docx(paragraph(run("x" * 5_000)))

    monkeypatch.setattr(office, "MAX_PART_BYTES", 2_000)
    assert extract_document_text(large, ".docx").error == "office_too_large"

    monkeypatch.setattr(office, "MAX_PART_BYTES", 10_000_000)
    monkeypatch.setattr(office, "MAX_TOTAL_BYTES", 1_000)
    assert extract_document_text(large, ".docx").error == "office_too_large"

    monkeypatch.setattr(office, "MAX_TOTAL_BYTES", 10_000_000)
    monkeypatch.setattr(office, "MAX_ENTRIES", 2)
    assert extract_document_text(large, ".docx").error == "office_too_large"


def encrypted_entries(content: bytes) -> bytes:
    """Set the ZIP "encrypted" flag on every entry; zipfile clears it when writing."""

    data = bytearray(content)
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = data.find(signature)
        while start != -1:
            data[start + flag_offset] |= 0x1
            start = data.find(signature, start + 4)
    return bytes(data)


def test_protected_legacy_and_damaged_files_say_what_they_are():
    compound = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512
    assert extract_document_text(compound, ".docx").error == "office_protected"

    assert extract_document_text(encrypted_entries(docx(HOMEWORK)), ".docx").error == "office_protected"

    assert extract_document_text(b"PK\x03\x04 not really a zip", ".docx").error == "office_extract_failed"
    assert extract_document_text(package({"_rels/.rels": rels()}), ".pptx").error == "office_extract_failed"
    assert extract_document_text(docx(""), ".docx").error == "office_no_text"


def test_very_long_documents_are_truncated_and_marked_partial(monkeypatch):
    monkeypatch.setattr(office, "MAX_TEXT_CHARS", 40)

    result = extract_document_text(docx(HOMEWORK), ".docx")

    assert result.ok
    assert len(result.text) <= 40
    assert result.metadata["partial"] is True
    assert "Only the first 40 characters" in result.metadata["warnings"][0]


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


def test_an_uploaded_docx_becomes_a_library_source_with_its_original_kept(upload_client):
    from thoughtpins.db import DocumentSource
    from thoughtpins.store import get_session

    response = upload_client.post(
        "/v1/uploads",
        json={
            "filename": "orbital-homework.docx",
            "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "destination": "library",
            "content_base64": base64.b64encode(docx(HOMEWORK, footnotes=FOOTNOTES)).decode("ascii"),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route_type"] == "library_upload"
    assert body["extraction_status"] == "processed"
    assert body["document_id"]
    assert body["attachment_saved"] is True
    session = get_session()
    try:
        source = session.query(DocumentSource).filter(DocumentSource.id == body["document_id"]).one()
        extraction = source.metadata_json["upload"]["extraction"]
        assert extraction["engine"] == "ooxml"
        assert extraction["suffix"] == ".docx"
    finally:
        session.close()


def test_a_protected_office_file_asks_for_text_with_a_specific_reason(upload_client):
    response = upload_client.post(
        "/v1/uploads",
        json={
            "filename": "locked.pptx",
            "content_base64": base64.b64encode(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512).decode("ascii"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_text"
    assert body["extraction_status"] == "office_protected"
    assert "password-protected" in body["error"]
    assert body["attachment_saved"] is True


def corrupt_entry(content: bytes, name: str = "word/document.xml") -> bytes:
    """Damage one entry's compressed bytes while leaving the ZIP envelope intact."""

    header = zipfile.ZipFile(io.BytesIO(content)).getinfo(name).header_offset
    data = bytearray(content)
    name_length = int.from_bytes(data[header + 26 : header + 28], "little")
    extra_length = int.from_bytes(data[header + 28 : header + 30], "little")
    start = header + 30 + name_length + extra_length
    for offset in range(8):
        data[start + offset] ^= 0xA5
    return bytes(data)


def recompressed(content: bytes, compression: int) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(content))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for info in source.infolist():
            archive.writestr(info.filename, source.read(info.filename))
    return buffer.getvalue()


@pytest.mark.parametrize("compression", [zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_a_damaged_compressed_stream_is_an_unreadable_file_not_a_crash(compression):
    """zlib.error and bz2's OSError used to escape extraction and become HTTP 500s."""

    damaged = corrupt_entry(recompressed(docx(HOMEWORK), compression))

    result = extract_document_text(damaged, ".docx")

    assert result.error == "office_extract_failed"
    assert result.text == ""


def test_a_part_that_inflates_implausibly_is_refused_before_inflating():
    # About 665:1 -- what a decompression-cost attack looks like, not a document.
    bomb = docx("<w:p/>" * 600_000)
    ratio_info = next(i for i in zipfile.ZipFile(io.BytesIO(bomb)).infolist() if i.filename == "word/document.xml")
    assert ratio_info.file_size > office.MAX_COMPRESSION_RATIO * ratio_info.compress_size

    assert extract_document_text(bomb, ".docx").error == "office_too_large"


def test_a_long_real_looking_document_is_still_read():
    import random

    rng = random.Random(7)
    words = [f"{rng.choice('bcdfghjklmnpqrstvwz')}{rng.choice('aeiou')}{rng.randrange(10_000)}" for _ in range(120_000)]
    body = "".join(paragraph(run(" ".join(words[i : i + 12]))) for i in range(0, len(words), 12))
    content = docx(body)
    part = next(i for i in zipfile.ZipFile(io.BytesIO(content)).infolist() if i.filename == "word/document.xml")
    assert part.file_size > 1024 * 1024, "the fixture must exceed the ratio exemption to exercise the cap"

    result = extract_document_text(content, ".docx")

    assert result.ok, result.error
    assert words[-1] in result.text


def test_a_damaged_office_upload_asks_for_text_instead_of_failing(upload_client):
    damaged = corrupt_entry(docx(HOMEWORK))

    response = upload_client.post(
        "/v1/uploads",
        json={"filename": "damaged.docx", "content_base64": base64.b64encode(damaged).decode("ascii")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "needs_text"
    assert body["extraction_status"] == "office_extract_failed"
    assert "Paste the text" in body["error"]


def test_a_large_table_of_identical_empty_cells_is_still_read():
    """Generators that omit Word's paragraph IDs reach ~150:1 on empty tables."""

    cell = '<w:tc><w:tcPr><w:tcW w:w="1870" w:type="dxa"/></w:tcPr><w:p/></w:tc>'
    table = "<w:tbl>" + ("<w:tr>" + cell * 6 + "</w:tr>") * 8_000 + "</w:tbl>"
    content = docx(paragraph(run("Inspection form, section 2")) + table)
    part = next(i for i in zipfile.ZipFile(io.BytesIO(content)).infolist() if i.filename == "word/document.xml")
    assert part.file_size > 100 * part.compress_size, "the fixture must be as compressible as the real case"

    result = extract_document_text(content, ".docx")

    assert result.ok, result.error
    assert "Inspection form, section 2" in result.text
