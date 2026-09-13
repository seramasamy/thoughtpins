"""Exercise installed PDF/OCR parsers with generated, non-personal content."""

from __future__ import annotations

import io
import sys
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
    print("Production PDF and image extraction passed generated content checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
