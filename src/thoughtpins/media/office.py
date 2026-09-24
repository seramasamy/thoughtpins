"""Bounded text extraction from Word (.docx) and PowerPoint (.pptx) uploads.

Office Open XML files are ZIP packages of XML parts. Nothing here executes,
follows or fetches anything: macro parts are never opened, external
relationships (linked images, remote templates) are skipped, and any part that
declares a DTD is refused, because OOXML never needs one and entity expansion
is the classic way to turn a small upload into a large allocation. Every read
is bounded by entry count, per-part size and total bytes before inflation.

Only the standard library is used, so the image gains no parser dependency.
Tracked deletions, field codes and duplicate fallback renderings are excluded;
slides are read in presentation order with their speaker notes, and each slide
is labelled so a retrieved passage can still be traced to its slide.
"""

from __future__ import annotations

import io
import lzma
import posixpath
import zipfile
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, NoReturn
from xml.etree import ElementTree
from xml.parsers import expat

from loguru import logger

from thoughtpins.media.extraction_types import MediaExtraction

OFFICE_SUFFIXES = frozenset({".docx", ".pptx"})
MAX_ENTRIES = 5_000
# Parsing is in the request and costs roughly nine times the XML size in
# memory: a 31 MiB part took 14 s and 277 MiB. 16 MiB still holds a document
# far longer than MAX_TEXT_CHARS, since markup outweighs the text it carries.
MAX_PART_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 48 * 1024 * 1024
# Word's own output compresses about 30:1 even for large empty tables, because
# it gives every paragraph a unique ID; generators that omit the IDs reach about
# 150:1. Deflate tops out near 1,000:1, which only a file built to cost the
# server approaches. MAX_PART_BYTES is the real memory bound; this refuses the
# extreme before inflating anything.
MAX_COMPRESSION_RATIO = 400
_RATIO_EXEMPT_BYTES = 1024 * 1024
MAX_SLIDES = 500
MAX_TEXT_CHARS = 2_000_000

# Password-protected OOXML and the legacy binary formats are both OLE compound
# files, not ZIP packages. Neither can be read here, and saying so is kinder
# than a generic failure.
_COMPOUND_FILE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_PACKAGE_RELS = "_rels/.rels"
# Branches of revision history and field machinery, not visible document text.
_WORD_SKIP = frozenset({"del", "moveFrom", "delText", "instrText", "fldData", "rPr", "pPr", "sectPr"})
_NOTE_SEPARATORS = frozenset({"separator", "continuationSeparator", "continuationNotice"})


class OfficeReadError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class _Package:
    archive: zipfile.ZipFile
    names: frozenset[str]
    budget: int

    def read(self, name: str) -> bytes:
        info = self.archive.getinfo(name)
        if info.flag_bits & 0x1:
            raise OfficeReadError("office_protected")
        if info.file_size > MAX_PART_BYTES or info.file_size > self.budget:
            raise OfficeReadError("office_too_large")
        if info.file_size > _RATIO_EXEMPT_BYTES and info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
            raise OfficeReadError("office_too_large")
        self.budget -= info.file_size
        with self.archive.open(info) as handle:
            data = handle.read(MAX_PART_BYTES + 1)
        if len(data) > MAX_PART_BYTES:
            raise OfficeReadError("office_too_large")
        return data

    def xml(self, name: str) -> ElementTree.Element:
        return _parse_xml(self.read(name))

    def relationships(self, part: str) -> dict[str, tuple[str, str]]:
        """Internal relationships of a part: id -> (type, resolved part name)."""

        folder, filename = posixpath.split(part)
        rels_name = posixpath.join(folder, "_rels", f"{filename}.rels") if part else _PACKAGE_RELS
        if rels_name not in self.names:
            return {}
        resolved: dict[str, tuple[str, str]] = {}
        for rel in self.xml(rels_name):
            if _local(rel.tag) != "Relationship" or rel.get("TargetMode") == "External":
                continue
            target = _resolve_target(folder, rel.get("Target") or "")
            if target and target in self.names:
                resolved[rel.get("Id") or ""] = (rel.get("Type") or "", target)
        return resolved

    def related(self, part: str, kind: str) -> list[str]:
        return [target for rel_type, target in self.relationships(part).values() if rel_type.endswith(f"/{kind}")]


@dataclass
class _Text:
    lines: list[str] = field(default_factory=list)
    chars: int = 0
    truncated: bool = False

    def add(self, line: str) -> bool:
        line = line.strip()
        if not line or self.truncated:
            return False
        if self.chars + len(line) > MAX_TEXT_CHARS:
            self.truncated = True
            return False
        self.lines.append(line)
        self.chars += len(line) + 1
        return True


def extract_office_text(content: bytes, suffix: str) -> MediaExtraction:
    """Read the text of a .docx or .pptx the user deliberately uploaded."""

    metadata: dict[str, Any] = {"suffix": suffix, "engine": "ooxml"}
    if content.startswith(_COMPOUND_FILE_MAGIC):
        return MediaExtraction(kind="document", metadata=metadata, error="office_protected")
    reader: Callable[[_Package], tuple[str, dict[str, Any]]] = _read_docx if suffix == ".docx" else _read_pptx
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise OfficeReadError("office_too_large")
            package = _Package(archive, frozenset(info.filename for info in entries), MAX_TOTAL_BYTES)
            text, details = reader(package)
    except OfficeReadError as exc:
        return MediaExtraction(kind="document", metadata=metadata, error=exc.code)
    except (
        zipfile.BadZipFile,
        # A damaged compressed stream fails in the decompressor, not in
        # zipfile, and used to escape as an HTTP 500 instead of this result.
        zlib.error,
        lzma.LZMAError,
        OSError,
        EOFError,
        expat.ExpatError,
        KeyError,
        ValueError,
        RuntimeError,
    ) as exc:
        # Type only: parser messages can quote the document's own text.
        logger.warning("Office extraction failed ({})", type(exc).__name__)
        return MediaExtraction(kind="document", metadata=metadata, error="office_extract_failed")
    metadata.update(details)
    return MediaExtraction(
        text=text,
        kind="document",
        metadata=metadata,
        error=None if text.strip() else "office_no_text",
    )


def _read_docx(package: _Package) -> tuple[str, dict[str, Any]]:
    main = _main_part(package, "word/document.xml")
    body = next((child for child in package.xml(main) if _local(child.tag) == "body"), None)
    text = _Text()
    counts = {"tables": 0}
    if body is not None:
        _word_blocks(body, text, counts)
    body_blocks = len(text.lines)
    notes = 0
    for kind in ("footnotes", "endnotes"):
        for part in package.related(main, kind):
            for note in package.xml(part):
                if _local(note.tag) in {"footnote", "endnote"} and _attribute(note, "type") not in _NOTE_SEPARATORS:
                    before = len(text.lines)
                    _word_blocks(note, text, counts)
                    notes += len(text.lines) > before
    warnings = [f"Only the first {MAX_TEXT_CHARS:,} characters were read."] if text.truncated else []
    details = {
        # Non-empty paragraphs and table rows in the body, before any notes.
        "blocks": body_blocks,
        "tables": counts["tables"],
        "notes": notes,
        "partial": text.truncated,
        "warnings": warnings,
    }
    return "\n".join(text.lines), details


def _word_blocks(container: ElementTree.Element, text: _Text, counts: dict[str, int]) -> None:
    for child in container:
        name = _local(child.tag)
        if name == "p":
            text.add(_word_inline(child))
        elif name == "tbl":
            counts["tables"] += 1
            for row in _children(child, "tr"):
                cells = []
                for cell in _children(row, "tc"):
                    cell_text = _Text()
                    _word_blocks(cell, cell_text, counts)
                    cells.append(" ".join(cell_text.lines))
                if any(cells):
                    text.add(" | ".join(cells))
        elif name == "AlternateContent":
            branch = _preferred_branch(child)
            if branch is not None:
                _word_blocks(branch, text, counts)
        elif name not in _WORD_SKIP:
            _word_blocks(child, text, counts)


def _word_inline(element: ElementTree.Element) -> str:
    parts: list[str] = []

    def walk(node: ElementTree.Element) -> None:
        for child in node:
            name = _local(child.tag)
            if name in _WORD_SKIP:
                continue
            if name == "t":
                parts.append(child.text or "")
            elif name == "tab":
                parts.append("\t")
            elif name in {"br", "cr"}:
                parts.append("\n")
            elif name == "noBreakHyphen":
                parts.append("-")
            elif name == "AlternateContent":
                branch = _preferred_branch(child)
                if branch is not None:
                    walk(branch)
            elif name == "txbxContent":
                box = _Text()
                _word_blocks(child, box, {"tables": 0})
                parts.append("\n" + "\n".join(box.lines) + "\n")
            else:
                walk(child)

    walk(element)
    return "".join(parts)


def _read_pptx(package: _Package) -> tuple[str, dict[str, Any]]:
    main = _main_part(package, "ppt/presentation.xml")
    relationships = package.relationships(main)
    slide_ids = next((child for child in package.xml(main) if _local(child.tag) == "sldIdLst"), None)
    slides = [
        relationships[rel_id][1]
        for rel_id in (_relationship_id(entry) for entry in _children(slide_ids, "sldId"))
        if rel_id in relationships and relationships[rel_id][0].endswith("/slide")
    ]
    text = _Text()
    blocks: list[str] = []
    without_text = with_notes = 0
    for number, slide in enumerate(slides[:MAX_SLIDES], start=1):
        body = _Text()
        _drawing_paragraphs(package.xml(slide), body)
        notes = _Text()
        for notes_part in package.related(slide, "notesSlide"):
            for shape in package.xml(notes_part).iter():
                if _local(shape.tag) == "sp" and _placeholder_type(shape) == "body":
                    _drawing_paragraphs(shape, notes)
        without_text += not body.lines
        with_notes += bool(notes.lines)
        if body.lines or notes.lines:
            lines = [f"Slide {number}", *body.lines]
            if notes.lines:
                lines.append("Speaker notes: " + "\n".join(notes.lines))
            kept = [line for line in lines if text.add(line)]
            if kept:
                blocks.append("\n".join(kept))
    warnings = []
    if len(slides) > MAX_SLIDES:
        warnings.append(f"Only the first {MAX_SLIDES} of {len(slides)} slides were read.")
    if without_text:
        warnings.append(f"{without_text} slides had no readable text; text inside images is not read.")
    if text.truncated:
        warnings.append(f"Only the first {MAX_TEXT_CHARS:,} characters were read.")
    details = {
        "slides_total": len(slides),
        "slides_read": min(len(slides), MAX_SLIDES),
        "slides_without_text": without_text,
        "slides_with_notes": with_notes,
        "partial": bool(warnings),
        "warnings": warnings,
    }
    return "\n\n".join(blocks), details


def _drawing_paragraphs(element: ElementTree.Element, text: _Text) -> None:
    for child in element:
        name = _local(child.tag)
        if name == "AlternateContent":
            branch = _preferred_branch(child)
            if branch is not None:
                _drawing_paragraphs(branch, text)
        elif name == "p":
            text.add("".join(_drawing_runs(child)))
        else:
            _drawing_paragraphs(child, text)


def _drawing_runs(paragraph: ElementTree.Element) -> Iterable[str]:
    for node in paragraph.iter():
        name = _local(node.tag)
        if name == "t":
            yield node.text or ""
        elif name == "br":
            yield "\n"


def _main_part(package: _Package, default: str) -> str:
    documents = package.related("", "officeDocument")
    main = documents[0] if documents else default
    if main not in package.names:
        raise OfficeReadError("office_extract_failed")
    return main


def _parse_xml(data: bytes) -> ElementTree.Element:
    """Parse one part with DTDs refused by the parser itself.

    A raw expat parser feeds ElementTree's builder because the C-accelerated
    ``XMLParser`` does not expose expat's declaration handlers. Refusing there,
    rather than searching the bytes, also covers a UTF-16 part, whose DTD a byte
    search for ``<!DOCTYPE`` would miss.
    """

    builder = ElementTree.TreeBuilder()
    parser = expat.ParserCreate(namespace_separator="}")

    def refuse(*_args: object) -> NoReturn:
        raise OfficeReadError("office_extract_failed")

    def start(name: str, attributes: dict[str, str]) -> None:
        builder.start(_qualified(name), {_qualified(key): value for key, value in attributes.items()})

    def end(name: str) -> None:
        builder.end(_qualified(name))

    parser.buffer_text = True
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.UnparsedEntityDeclHandler = refuse
    parser.ExternalEntityRefHandler = refuse
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = builder.data
    parser.Parse(data, True)
    return builder.close()


def _qualified(name: str) -> str:
    # expat reports "uri}local"; ElementTree spells it "{uri}local".
    return "{" + name if "}" in name else name


def _resolve_target(folder: str, target: str) -> str | None:
    if not target or "://" in target:
        return None
    joined = target.lstrip("/") if target.startswith("/") else posixpath.join(folder, target)
    normalized = posixpath.normpath(joined)
    return None if normalized.startswith("../") or normalized == ".." else normalized


def _preferred_branch(alternate: ElementTree.Element) -> ElementTree.Element | None:
    # Choice and Fallback render the same content twice; read it once.
    branches = [child for child in alternate if _local(child.tag) in {"Choice", "Fallback"}]
    return branches[0] if branches else None


def _placeholder_type(shape: ElementTree.Element) -> str | None:
    placeholder = next((node for node in shape.iter() if _local(node.tag) == "ph"), None)
    return None if placeholder is None else placeholder.get("type")


def _relationship_id(element: ElementTree.Element) -> str:
    # sldId carries a plain numeric `id` and a namespaced relationship `id`.
    return next((value for key, value in element.attrib.items() if key.startswith("{") and _local(key) == "id"), "")


def _attribute(element: ElementTree.Element, name: str) -> str | None:
    return next((value for key, value in element.attrib.items() if _local(key) == name), None)


def _children(element: ElementTree.Element | None, name: str) -> list[ElementTree.Element]:
    return [] if element is None else [child for child in element if _local(child.tag) == name]


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
