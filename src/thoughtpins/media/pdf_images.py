"""The images a PDF page draws: finding them, decoding them within a bound,
and assembling a page stored in pieces.

Used by ``media/pdf.py`` to read scanned pages.

* Finding: a bounded, cycle-safe walk of the page's content stream that tracks
  the transformation matrix, so each image's on-page rotation and position are
  known. Images listed in resources but never drawn are ignored.
* Decoding: JPEG is sized from its own header and decoded at reduced size in
  process. JPEG 2000 and JBIG2 decoders can run long on crafted input, so they
  run in a subprocess with a hard timeout -- pypdf's own JBIG2 path has none,
  which is why ``get_data()`` is never called on a JBIG2 image here. Other
  encodings are decoded by pypdf in process, at the size the pixel limit was
  checked against, and never with the image's soft mask (see ``_decode_raw``).
* Assembling: a page some scanners store as strips or tiles is pasted back
  together, so OCR reads the whole page rather than its largest piece.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# A 600 dpi Letter page is 33.7M pixels. JPEG and JPEG 2000 sizes come from the
# image header, which is what decoding costs; other encodings are decoded at
# their declared size, which their sample data must match.
MAX_SCAN_PIXELS = 36_000_000
MAX_RAW_SCAN_PIXELS = 25_000_000
# Downscaled before OCR: about 350 dpi on Letter, as much as Tesseract uses.
OCR_LONG_SIDE = 4_000
# A scanned page draws its images in a few dozen bytes. A page whose content
# stream is larger is vector drawing, which OCR cannot read without rendering.
MAX_SCAN_CONTENT_BYTES = 256 * 1024
MAX_XOBJECTS_PER_PAGE = 64
MAX_FORM_DEPTH = 3
# jbig2dec refuses to allocate a bitmap larger than this.
JBIG2_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
# Address-space ceiling the JPEG 2000 child sets on itself (Linux), so a
# crafted image fails in the child rather than exhausting the container.
DECODER_MEMORY_BYTES = 1536 * 1024 * 1024
# Image codecs end a filter chain. One anywhere else is a crafted chain, and
# pypdf would decode it through a path with no bound -- refuse it instead.
_CODECS = frozenset({"/JBIG2Decode", "/JPXDecode", "/DCTDecode", "/CCITTFaxDecode"})
_ORIENTATION_TOLERANCE_DEGREES = 5.0
# Scanned pages are mostly paper; a bilevel page that is mostly black was
# decoded with its polarity reversed, which Tesseract reads badly.
_INVERTED_MEAN = 96

# Run as `python -I -c` so a decoder that hangs or crashes on crafted input
# takes a child process with it, not the request.
_JPX_CHILD = """
import sys
if sys.platform == "linux":
    import resource
    limit = int(sys.argv[5])
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
from PIL import Image
source, target, max_pixels, long_side = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
image = Image.open(source)
if image.width * image.height > max_pixels:
    sys.exit(3)
factor = 0
while factor < 5 and max(image.width, image.height) >> (factor + 1) >= long_side:
    factor += 1
image.reduce = factor
image = image.convert("L")
image.thumbnail((long_side, long_side))
image.save(target, "PNG")
"""


class DecodeTimeout(Exception):
    """A subprocess decoder ran past the time it was given."""


@dataclass(frozen=True)
class DrawnImage:
    pixels: int
    xobject: Any
    matrix: Matrix
    # Drawn through a mask, or a stencil itself: one layer of a composed page.
    masked: bool


@dataclass(frozen=True)
class Drawing:
    """The images a page draws, and whether the walk saw all of them."""

    images: list[DrawnImage]
    # False when the walk stopped at its XObject budget with more left to draw.
    complete: bool = True


def drawn_images(page: Any) -> Drawing:
    """Images the page draws, in drawing order, with the matrix each is drawn with."""

    try:
        if content_bytes(page) > MAX_SCAN_CONTENT_BYTES:
            return Drawing([])
        contents = page.get_contents()
        if contents is None:
            return Drawing([])
        walk = _Walk(page)
        walk.visit(contents.operations, page.get("/Resources"), IDENTITY, 0)
        return Drawing(walk.found, complete=not walk.exhausted)
    except Exception as exc:
        logger.debug("PDF page content unreadable ({})", type(exc).__name__)
        return Drawing([])


def content_bytes(page: Any) -> int:
    """Decoded content-stream size, measured before anything is parsed."""

    contents = page.get("/Contents")
    if contents is None:
        return 0
    contents = contents.get_object()
    streams = contents if isinstance(contents, list) else [contents]
    return sum(len(stream.get_object().get_data()) for stream in streams)


class _Walk:
    """One page's walk: shared XObject budget and seen-set across nested forms."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.found: list[DrawnImage] = []
        self.seen: set[Any] = set()
        self.budget = MAX_XOBJECTS_PER_PAGE
        self.exhausted = False

    def visit(self, operations: Any, resources: Any, ctm: Matrix, depth: int) -> None:
        if resources is None or depth > MAX_FORM_DEPTH:
            return
        xobjects = resources.get_object().get("/XObject")
        if xobjects is None:
            return
        xobjects = xobjects.get_object()
        stack: list[Matrix] = []
        for operands, operator in operations:
            if operator == b"q":
                stack.append(ctm)
            elif operator == b"Q":
                ctm = stack.pop() if stack else ctm
            elif operator == b"cm" and len(operands) == 6:
                ctm = multiply(_matrix(operands), ctm)
            elif operator == b"Do" and operands and str(operands[0]) in xobjects:
                if self.budget <= 0:
                    self.exhausted = True
                    return
                self.budget -= 1
                self._draw(xobjects, str(operands[0]), ctm, depth)

    def _draw(self, xobjects: Any, name: str, ctm: Matrix, depth: int) -> None:
        from pypdf.generic import ContentStream, IndirectObject

        reference = xobjects.raw_get(name)
        identity = (reference.idnum, reference.generation) if isinstance(reference, IndirectObject) else id(reference)
        if identity in self.seen:
            return
        self.seen.add(identity)
        xobject = reference.get_object()
        subtype = xobject.get("/Subtype")
        if subtype == "/Image":
            masked = "/SMask" in xobject or "/Mask" in xobject or bool(xobject.get("/ImageMask"))
            self.found.append(DrawnImage(_declared_pixels(xobject), xobject, ctm, masked))
        elif subtype == "/Form" and len(xobject.get_data()) <= MAX_SCAN_CONTENT_BYTES:
            form_ctm = multiply(_matrix(xobject.get("/Matrix") or IDENTITY), ctm)
            operations = ContentStream(xobject, self.page.pdf).operations
            self.visit(operations, xobject.get("/Resources"), form_ctm, depth + 1)


def multiply(first: Matrix, second: Matrix) -> Matrix:
    """``first`` then ``second``, as PDF concatenates matrices."""

    a, b, c, d, e, f = first
    a2, b2, c2, d2, e2, f2 = second
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def orientation(matrix: Matrix) -> int | None:
    """Degrees counter-clockwise the page turns the stored image: 0, 90, 180 or 270.

    None when the image is mirrored, degenerate, or skewed off a right angle,
    none of which a quarter turn can make upright.
    """

    a, b, c, d = matrix[:4]
    if a * d - b * c <= 0:
        return None
    angle = math.degrees(math.atan2(b, a)) % 360
    nearest = int(round(angle / 90.0) * 90) % 360
    if abs((angle - nearest + 180) % 360 - 180) > _ORIENTATION_TOLERANCE_DEGREES:
        return None
    return nearest


def is_upright(matrix: Matrix) -> bool:
    a, b, c, d = matrix[:4]
    return a > 0 and d > 0 and abs(b) <= 0.01 * a and abs(c) <= 0.01 * d


def decode(image: DrawnImage, *, timeout: float) -> Any:
    """The image as grayscale, long side at most OCR_LONG_SIDE, polarity as stored."""

    names = _filter_names(image.xobject)
    codecs = [name for name in names if name in _CODECS]
    if codecs and (len(codecs) > 1 or names[-1] != codecs[0]):
        raise ValueError("unsupported filter chain")
    last = names[-1] if names else None
    if last == "/JBIG2Decode":
        picture = _decode_jbig2(image.xobject, names, timeout=timeout)
    elif last == "/JPXDecode":
        picture = _decode_jpx(image.xobject.get_data(), timeout=timeout)
    elif last == "/DCTDecode":
        picture = _open_jpeg(image.xobject.get_data())
    else:
        picture = _decode_raw(image, names)
    grayscale = picture.convert("L")
    if max(grayscale.size) > OCR_LONG_SIDE:
        grayscale.thumbnail((OCR_LONG_SIDE, OCR_LONG_SIDE))
    return grayscale


def is_bilevel(image: DrawnImage) -> bool:
    names = _filter_names(image.xobject)
    return bool({"/JBIG2Decode", "/CCITTFaxDecode"} & set(names)) or image.xobject.get("/BitsPerComponent") == 1


def fix_polarity(picture: Any) -> Any:
    """Invert a bilevel page decoded mostly black; paper is mostly white."""

    from PIL import ImageOps, ImageStat

    return ImageOps.invert(picture) if ImageStat.Stat(picture).mean[0] < _INVERTED_MEAN else picture


def compose(pieces: list[DrawnImage], decode_piece: Callable[[DrawnImage], Any]) -> Any:
    """Paste upright pieces back into one page image by their on-page boxes.

    Each piece is decoded, shrunk to its box and pasted before the next is
    decoded, so memory holds the canvas and one piece, never every piece.
    """

    from PIL import Image

    boxes = [(m[4], m[5], m[4] + m[0], m[5] + m[3]) for m in (piece.matrix for piece in pieces)]
    left, bottom = min(box[0] for box in boxes), min(box[1] for box in boxes)
    right, top = max(box[2] for box in boxes), max(box[3] for box in boxes)
    width, height = max(right - left, 1.0), max(top - bottom, 1.0)
    # Keep the pieces' own declared resolution, within the OCR size limit.
    density = max(_declared_width(piece.xobject) / piece.matrix[0] for piece in pieces)
    scale = min(max(density, 1e-3), OCR_LONG_SIDE / max(width, height))
    canvas = Image.new("L", (max(1, round(width * scale)), max(1, round(height * scale))), 255)
    for piece, box in zip(pieces, boxes, strict=True):
        size = (max(1, round((box[2] - box[0]) * scale)), max(1, round((box[3] - box[1]) * scale)))
        picture = decode_piece(piece).resize(size)
        # PDF measures up from the bottom; images measure down from the top.
        canvas.paste(picture, (round((box[0] - left) * scale), round((top - box[3]) * scale)))
    return canvas


def _decode_jbig2(xobject: Any, names: list[str], *, timeout: float) -> Any:
    from PIL import Image
    from pypdf.generic import StreamObject

    executable = shutil.which("jbig2dec")
    if executable is None:
        raise ValueError("jbig2dec is not installed")
    raw = getattr(xobject, "_data", None)
    if not isinstance(raw, bytes):
        raise ValueError("JBIG2 stream data is unavailable")
    parameters = _decode_parameters(xobject, len(names))
    if len(names) > 1:
        # Undo the general-purpose filters before JBIG2 (Flate, say) with pypdf,
        # which bounds those, and leave only the JBIG2 step to jbig2dec.
        raw = _decode_prefix(raw, names[:-1], parameters[:-1])
    params = parameters[-1]
    with tempfile.TemporaryDirectory(prefix="thoughtpins-jbig2-") as directory:
        paths = []
        global_segments = params.get("/JBIG2Globals") if params is not None else None
        global_segments = global_segments.get_object() if global_segments is not None else None
        if isinstance(global_segments, StreamObject):
            globals_path = Path(directory) / "globals.jbig2"
            globals_path.write_bytes(global_segments.get_data())
            paths.append(str(globals_path))
        image_path = Path(directory) / "image.jbig2"
        image_path.write_bytes(raw)
        paths.append(str(image_path))
        command = [executable, "--embedded", "--format", "png", "--output", "-", "-M", str(JBIG2_MAX_OUTPUT_BYTES)]
        output = _run([*command, *paths], timeout=timeout)
    picture = Image.open(io.BytesIO(output))
    # The decoded size, not the PDF's claim, is what converting will cost.
    if picture.width * picture.height > MAX_SCAN_PIXELS:
        raise ValueError("scan image exceeds the pixel limit")
    return picture


def _decode_prefix(raw: bytes, names: list[str], parameters: list[Any]) -> bytes:
    from pypdf.generic import ArrayObject, EncodedStreamObject, NameObject, NullObject

    stream = EncodedStreamObject()
    stream._data = raw
    stream[NameObject("/Filter")] = ArrayObject([NameObject(name) for name in names])
    stream[NameObject("/DecodeParms")] = ArrayObject(
        [value if value is not None else NullObject() for value in parameters]
    )
    data = stream.get_data()
    return data if isinstance(data, bytes) else bytes(data)


def _decode_parameters(xobject: Any, count: int) -> list[Any]:
    """Each filter's /DecodeParms dictionary, or None; entries may be indirect or null."""

    from pypdf.generic import DictionaryObject

    params = xobject.get("/DecodeParms")
    params = params.get_object() if params is not None else None
    entries = list(params) if isinstance(params, list) else [params] * count
    resolved = []
    for entry in (entries + [None] * count)[:count]:
        value = entry.get_object() if entry is not None else None
        resolved.append(value if isinstance(value, DictionaryObject) else None)
    return resolved


def _decode_raw(image: DrawnImage, names: list[str]) -> Any:
    """Sample data, decoded by pypdf at the size the pixel limit was checked against.

    Left to itself, pypdf would also decode the image's /SMask -- JBIG2 through
    jbig2dec with no timeout, JPEG 2000 in this process -- open LZW or ASCII85
    data as an embedded PNG or TIFF of whatever size that declares, and size
    CCITT data by its /Columns rather than the image's /Width. OCR needs no
    mask, so a copy without one is decoded; LZW and ASCII85 data is handed over
    already decoded, as plain samples; and CCITT data must be as wide as the
    image says it is.
    """

    from pypdf.generic import DecodedStreamObject, NameObject

    xobject = image.xobject
    if image.pixels > MAX_RAW_SCAN_PIXELS:
        raise ValueError("scan image exceeds the pixel limit")
    last = names[-1] if names else None
    if last == "/CCITTFaxDecode":
        params = _decode_parameters(xobject, len(names))[-1]
        columns = params.get("/Columns", 1728) if params is not None else 1728
        if int(columns) != int(xobject.get("/Width", 0)):
            raise ValueError("CCITT columns differ from the image width")
    dropped = {"/SMask", "/Mask"}
    copy: Any
    if last in ("/LZWDecode", "/ASCII85Decode"):
        copy = DecodedStreamObject()
        copy.set_data(xobject.get_data())
        dropped |= {"/Filter", "/DecodeParms", "/Length"}
    else:
        copy = type(xobject)()
        copy._data = xobject._data
    for key, value in xobject.items():
        if key not in dropped:
            copy[NameObject(key)] = value
    return copy.decode_as_image()


def _decode_jpx(data: bytes, *, timeout: float) -> Any:
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="thoughtpins-jpx-") as directory:
        source, target = Path(directory) / "image.jp2", Path(directory) / "image.png"
        source.write_bytes(data)
        arguments = [str(source), str(target), str(MAX_SCAN_PIXELS), str(OCR_LONG_SIDE), str(DECODER_MEMORY_BYTES)]
        _run([sys.executable, "-I", "-c", _JPX_CHILD, *arguments], timeout=timeout)
        with Image.open(target) as decoded:
            decoded.load()
            return decoded.copy()


def _open_jpeg(data: bytes) -> Any:
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    # The header's size, not the PDF's claim, decides what decoding costs.
    if image.width * image.height > MAX_SCAN_PIXELS:
        raise ValueError("scan image exceeds the pixel limit")
    # Decode straight to grayscale at reduced size, so a 600 dpi colour page
    # never exists in memory at full resolution.
    image.draft("L", (OCR_LONG_SIDE, OCR_LONG_SIDE))
    return image


def _run(command: list[str], *, timeout: float) -> bytes:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=True,
            env=_decoder_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise DecodeTimeout(command[0]) from exc
    return result.stdout


def _decoder_environment() -> dict[str, str]:
    # Decoders read untrusted bytes. They get what they need to start, and none
    # of the server's database URLs, provider keys or DSNs.
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME")
    environment = {name: os.environ[name] for name in keep if name in os.environ}
    return {**environment, "LC_ALL": "C", "OMP_THREAD_LIMIT": "1"}


def _declared_width(xobject: Any) -> float:
    try:
        return float(xobject.get("/Width", 0))
    except (TypeError, ValueError):
        return 0.0


def _filter_names(xobject: Any) -> list[str]:
    filters = xobject.get("/Filter")
    if filters is None:
        return []
    filters = filters.get_object()
    return [str(item) for item in filters] if isinstance(filters, list) else [str(filters)]


def _declared_pixels(xobject: Any) -> int:
    try:
        return int(xobject.get("/Width", 0)) * int(xobject.get("/Height", 0))
    except (TypeError, ValueError):
        return 0


def _matrix(values: Any) -> Matrix:
    numbers = [float(value) for value in values]
    if len(numbers) != 6:
        return IDENTITY
    return (numbers[0], numbers[1], numbers[2], numbers[3], numbers[4], numbers[5])
