"""Pure text shaping primitives for document-library ingestion."""

from __future__ import annotations

import re
from urllib.parse import urlparse

CHUNK_CHARS = 1800
CHUNK_OVERLAP = 180


def chunk_text(
    text: str,
    *,
    max_chars: int = CHUNK_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[tuple[str, int, int]]:
    if len(text) <= max_chars:
        return [(text, 0, len(text))]

    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def rough_token_count(text: str) -> int:
    return max(1, round(len(text) / 4))


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()


def summarize_text(text: str, max_chars: int = 700) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = ""
    for sentence in sentences:
        if len(summary) + len(sentence) + 1 > max_chars:
            break
        summary = (summary + " " + sentence).strip()
    return summary or text[:max_chars].rstrip()


def title_from_text(text: str, *, source_url: str | None, title: str) -> str:
    if title.strip():
        return title.strip()[:512]
    first_line = re.split(r"[\n.!?]", text, maxsplit=1)[0].strip()
    if 8 <= len(first_line) <= 160:
        return first_line[:512]
    if source_url:
        parsed = urlparse(source_url)
        return (parsed.netloc + parsed.path).strip("/")[:512] or "Saved source"
    return "Saved source"


def raw_entry_text(title: str, text: str, source_url: str | None, status: str, error: str | None) -> str:
    header = [f"Library source: {title}", f"Status: {status}"]
    if source_url:
        header.append(f"URL: {source_url}")
    if error:
        header.append(f"Note: {error}")
    return "\n".join(header) + "\n\n" + text
