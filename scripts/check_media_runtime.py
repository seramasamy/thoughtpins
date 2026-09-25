"""Exercise installed PDF/OCR/Office parsers with generated, non-personal content."""

from __future__ import annotations

import io
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

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
    # A scanned page: a page-sized image with no text layer, read by the same
    # OCR engine through the PDF path's image decoding and page budget.
    page = Image.new("L", (1275, 1650), "white")
    ImageDraw.Draw(page).text((120, 200), phrase, fill="black", font=ImageFont.load_default(size=56))
    scanned = io.BytesIO()
    page.save(scanned, format="PDF", resolution=150)
    scan = extract_document_text(scanned.getvalue(), ".pdf")
    if not scan.ok or phrase not in " ".join(scan.text.split()) or scan.metadata.get("ocr_pages") != [1]:
        raise RuntimeError("Production scanned-PDF OCR failed its generated fixture")
    for suffix, package in ((".docx", _docx(phrase)), (".pptx", _pptx(phrase))):
        office = extract_document_text(package, suffix)
        if not office.ok or phrase not in office.text:
            raise RuntimeError(f"Production {suffix} extraction failed its generated fixture")
    # A page stored sideways and drawn turned upright, as scanners write
    # landscape pages: real OCR proves the turn goes the right way.
    upright = Image.new("L", (1275, 1650), "white")
    ImageDraw.Draw(upright).text((120, 200), phrase, fill="black", font=ImageFont.load_default(size=56))
    sideways = io.BytesIO()
    upright.rotate(-90, expand=True).save(sideways, "JPEG", quality=90)
    turned = _image_page(sideways.getvalue(), "/DCTDecode", (1650, 1275), b"q 0 792 -612 0 612 0 cm /Im Do Q")
    result = extract_document_text(turned, ".pdf")
    if not result.ok or phrase not in " ".join(result.text.split()):
        raise RuntimeError("Production OCR did not read a page drawn turned upright")
    # JPEG 2000 scans decode in a child process with a hard timeout.
    jpx = io.BytesIO()
    upright.save(jpx, "JPEG2000")
    result = extract_document_text(_image_page(jpx.getvalue(), "/JPXDecode", (1275, 1650)), ".pdf")
    if not result.ok or phrase not in " ".join(result.text.split()):
        raise RuntimeError("Production OCR did not read a JPEG 2000 scan")
    # Office scanners and Acrobat's scan optimisation write JBIG2 images, decoded
    # by jbig2dec (--embedded, with a -M memory limit) in a timed subprocess.
    _check_jbig2dec()
    result = extract_document_text(_image_page(_jbig2(upright), "/JBIG2Decode", (1275, 1650), bits=1), ".pdf")
    if not result.ok or phrase not in " ".join(result.text.split()):
        raise RuntimeError("Production OCR did not read a JBIG2 scan")
    print("Production PDF, scanned-PDF OCR, image, and Office extraction passed generated content checks.")
    return 0


def _image_page(
    data: bytes, filter_name: str, size: tuple[int, int], drawing: bytes | None = None, *, bits: int = 8
) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    image = DecodedStreamObject()
    image.set_data(data)
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(size[0]),
            NameObject("/Height"): NumberObject(size[1]),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(bits),
            NameObject("/Filter"): NameObject(filter_name),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): writer._add_object(image)})}
    )
    content = DecodedStreamObject()
    content.set_data(drawing or b"q 612 0 0 792 0 0 cm /Im Do Q")
    page[NameObject("/Contents")] = writer._add_object(content)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _jbig2(page: Any) -> bytes:
    """*page* as a PDF stores JBIG2: an embedded stream holding one MMR generic region."""
    from PIL import Image, ImageOps, TiffImagePlugin

    width, height = page.size
    # CCITT Group 4 is the MMR coding a JBIG2 generic region may use. In one
    # strip, the TIFF's image data is exactly the region's data. Group 4 codes
    # 0 bits as white and JBIG2 reads 1 as black, so ink is stored as 1.
    tiff = io.BytesIO()
    ImageOps.invert(page.convert("L")).convert("1").save(
        tiff, "TIFF", compression="group4", tiffinfo={TiffImagePlugin.ROWSPERSTRIP: height}
    )
    with Image.open(tiff) as stored:
        (offset,) = stored.tag_v2[TiffImagePlugin.STRIPOFFSETS]
        (length,) = stored.tag_v2[TiffImagePlugin.STRIPBYTECOUNTS]
    coded = tiff.getvalue()[offset : offset + length]

    def segment(number: int, kind: int, data: bytes) -> bytes:
        # Number, type, no referred-to segments, page 1, data length (T.88 7.2).
        return struct.pack(">IBBBI", number, kind, 0, 1, len(data)) + data

    page_information = struct.pack(">IIIIBH", width, height, 0, 0, 0, 0)
    generic_region = struct.pack(">IIIIB", width, height, 0, 0, 0) + b"" + coded  # MMR on
    return segment(0, 48, page_information) + segment(1, 38, generic_region)


def _check_jbig2dec() -> None:
    executable = shutil.which("jbig2dec")
    if executable is None:
        raise RuntimeError("jbig2dec is missing; JBIG2-compressed scans cannot be decoded")
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
    reported = f"{result.stdout} {result.stderr}"
    match = re.search(r"(\d+)\.(\d+)", reported)
    if result.returncode != 0 or match is None:
        raise RuntimeError(f"jbig2dec --version did not report a version: {reported.strip()!r}")
    if (int(match.group(1)), int(match.group(2))) < (0, 19):
        raise RuntimeError(f"jbig2dec {match.group(0)} is older than 0.19, the oldest release this path is verified on")


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
