"""Exercise installed PDF/OCR/Office parsers with generated, non-personal content."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    from PIL import Image, ImageDraw, ImageFont
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    from thoughtpins.media import extract_document_text, extract_image_text

    phrase = "VIOLET COMPASS 2048"
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
    stream.set_data(f"BT /F1 24 Tf 60 700 Td ({phrase}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf = io.BytesIO()
    writer.write(pdf)
    document = extract_document_text(pdf.getvalue(), ".pdf")
    if not document.ok or phrase not in document.text:
        raise RuntimeError("Production PDF extraction failed its generated fixture")

    picture = Image.new("RGB", (850, 170), "white")
    ImageDraw.Draw(picture).text((35, 55), phrase, fill="black", font=ImageFont.load_default(size=48))
    image = io.BytesIO()
    picture.save(image, format="PNG")
    extracted = extract_image_text(image.getvalue(), suffix=".png")
    if not extracted.ok or phrase not in " ".join(extracted.text.split()):
        raise RuntimeError("Production OCR failed its generated fixture")
    for suffix, package in ((".docx", _docx(phrase)), (".pptx", _pptx(phrase))):
        office = extract_document_text(package, suffix)
        if not office.ok or phrase not in office.text:
            raise RuntimeError(f"Production {suffix} extraction failed its generated fixture")
    print("Production PDF, image, and Office extraction passed generated content checks.")
    return 0


_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _package(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _rels(kind: str, target: str) -> str:
    return f'<Relationships xmlns="{_RELS}"><Relationship Id="rId1" Type="{_REL_TYPE}/{kind}" Target="{target}"/></Relationships>'


def _docx(phrase: str) -> bytes:
    word = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    return _package(
        {
            "_rels/.rels": _rels("officeDocument", "word/document.xml"),
            "word/document.xml": f'<w:document xmlns:w="{word}"><w:body><w:p><w:r><w:t>{phrase}</w:t></w:r></w:p></w:body></w:document>',
        }
    )


def _pptx(phrase: str) -> bytes:
    slides = "http://schemas.openxmlformats.org/presentationml/2006/main"
    drawing = "http://schemas.openxmlformats.org/drawingml/2006/main"
    return _package(
        {
            "_rels/.rels": _rels("officeDocument", "ppt/presentation.xml"),
            "ppt/presentation.xml": (
                f'<p:presentation xmlns:p="{slides}" xmlns:r="{_REL_TYPE}">'
                '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
            ),
            "ppt/_rels/presentation.xml.rels": _rels("slide", "slides/slide1.xml"),
            "ppt/slides/slide1.xml": (
                f'<p:sld xmlns:p="{slides}" xmlns:a="{drawing}"><p:cSld><p:spTree><p:sp><p:txBody>'
                f"<a:p><a:r><a:t>{phrase}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
            ),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
