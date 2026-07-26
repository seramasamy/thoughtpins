"""Reproducible public-domain stress evaluation for social retrieval.

The evaluator keeps downloaded books in an ignored scratch directory and emits
only aggregate metrics, source metadata, and short diagnostic excerpts. It does
not write to a user's memory database or vault.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any
from urllib.parse import urlparse

import httpx

from thoughtpins.memory.ranking import rerank_results
from thoughtpins.memory.search_types import SearchResult

GUTENBERG_TEXT_URL = "https://www.gutenberg.org/ebooks/{book_id}.txt.utf-8"
USER_AGENT = "ThoughtPins-Memory-Evaluation/1.0 (+https://thoughtpins.com)"

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b")
_SPEAKER_PATTERNS = (
    re.compile(r"\b(?:said|asked|replied|cried|answered|whispered)\s+([A-Z][a-z]{2,})\b"),
    re.compile(r"\b([A-Z][a-z]{2,})\s+(?:said|asked|replied|cried|answered|whispered)\b"),
)
_STOP = frozenset(
    {
        "about",
        "after",
        "again",
        "against",
        "almost",
        "among",
        "because",
        "before",
        "being",
        "between",
        "could",
        "every",
        "first",
        "found",
        "great",
        "house",
        "however",
        "little",
        "might",
        "never",
        "other",
        "should",
        "their",
        "there",
        "these",
        "thing",
        "think",
        "those",
        "through",
        "under",
        "until",
        "where",
        "which",
        "while",
        "would",
        "project",
        "gutenberg",
        "chapter",
        "ebook",
        "author",
        "title",
        "language",
    }
)
_NAME_STOP = frozenset(
    {"Chapter", "Project Gutenberg", "English", "United States", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
)


@dataclass(frozen=True)
class CatalogBook:
    book_id: int
    title: str
    authors: str
    subjects: str
    bookshelves: str

    @property
    def source_url(self) -> str:
        return f"https://www.gutenberg.org/ebooks/{self.book_id}"


@dataclass(frozen=True)
class SocialPassage:
    book: CatalogBook
    text: str
    speaker: str
    query_terms: tuple[str, ...]
    first_person_ratio: float
    content_sha256: str

    @property
    def query(self) -> str:
        terms = " ".join(self.query_terms)
        return f"what did {self.speaker} say about {terms}?" if self.speaker else f"what happened with {terms}?"


@dataclass(frozen=True)
class PublicDomainEvalSummary:
    requested_sources: int
    evaluated_sources: int
    attempted_sources: int
    first_person_sources: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mean_reciprocal_rank: float
    attribution_retention_rate: float
    mean_first_person_ratio: float
    failures: tuple[str, ...]
    sources: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_gutenberg_catalog(path: Path) -> list[CatalogBook]:
    books: list[CatalogBook] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                book_id = int(row.get("Text#") or "")
            except ValueError:
                continue
            if (row.get("Language") or "").strip() != "en" or (row.get("Type") or "").strip() != "Text":
                continue
            books.append(
                CatalogBook(
                    book_id=book_id,
                    title=(row.get("Title") or "").strip().replace("\n", " "),
                    authors=(row.get("Authors") or "").strip(),
                    subjects=(row.get("Subjects") or "").strip(),
                    bookshelves=(row.get("Bookshelves") or "").strip(),
                )
            )
    return sorted(books, key=_catalog_priority)


def evaluate_public_domain_corpus(
    catalog_path: Path,
    cache_dir: Path,
    *,
    source_count: int = 200,
    candidate_pool_size: int = 24,
    request_delay_seconds: float = 0.12,
    max_attempt_multiplier: int = 8,
) -> PublicDomainEvalSummary:
    if source_count <= 0:
        raise ValueError("source_count must be positive")
    if candidate_pool_size < 2:
        raise ValueError("candidate_pool_size must be at least two")
    if max_attempt_multiplier < 1:
        raise ValueError("max_attempt_multiplier must be positive")
    cache_dir.mkdir(parents=True, exist_ok=True)

    passages: list[SocialPassage] = []
    failures: list[str] = []
    attempted = 0
    for book in load_gutenberg_catalog(catalog_path):
        if len(passages) >= source_count or attempted >= source_count * max_attempt_multiplier:
            break
        attempted += 1
        try:
            text, downloaded = _load_book_text(book, cache_dir)
            passage = extract_social_passage(book, text)
            if passage is None:
                continue
            passages.append(passage)
            if downloaded and request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
        except (OSError, UnicodeError, httpx.HTTPError, ValueError) as exc:
            failures.append(f"{book.book_id}:{type(exc).__name__}")

    ranks: list[int] = []
    attribution_hits = 0
    for index, passage in enumerate(passages):
        pool = _candidate_pool(passages, index, size=candidate_pool_size)
        ranked = rerank_results(pool, query=passage.query, limit=min(10, len(pool)))
        target_id = f"book:{passage.book.book_id}"
        rank = next((position for position, result in enumerate(ranked, start=1) if result.memory_id == target_id), 11)
        ranks.append(rank)
        if passage.speaker:
            target = next((result for result in ranked if result.memory_id == target_id), None)
            if target and target.evidence_metadata.get("attributed_to") == passage.speaker:
                attribution_hits += 1

    evaluated = len(passages)
    first_person = sum(1 for passage in passages if passage.first_person_ratio >= 0.55)
    sources = tuple(
        {
            "book_id": passage.book.book_id,
            "title": passage.book.title,
            "authors": passage.book.authors,
            "source_url": passage.book.source_url,
            "rights_basis": "Project Gutenberg catalog; item header checked for restriction markers",
            "first_person_ratio": round(passage.first_person_ratio, 6),
            "content_sha256": passage.content_sha256,
            "diagnostic_excerpt": passage.text[:280],
        }
        for passage in passages
    )
    return PublicDomainEvalSummary(
        requested_sources=source_count,
        evaluated_sources=evaluated,
        attempted_sources=attempted,
        first_person_sources=first_person,
        recall_at_1=_rate(ranks, 1),
        recall_at_5=_rate(ranks, 5),
        recall_at_10=_rate(ranks, 10),
        mean_reciprocal_rank=round(fmean(1.0 / rank for rank in ranks), 6) if ranks else 0.0,
        attribution_retention_rate=round(attribution_hits / max(1, sum(1 for item in passages if item.speaker)), 6),
        mean_first_person_ratio=round(fmean(item.first_person_ratio for item in passages), 6) if passages else 0.0,
        failures=tuple(failures[:100]),
        sources=sources,
    )


def extract_social_passage(book: CatalogBook, text: str) -> SocialPassage | None:
    body = _book_body(text)
    if len(body) < 5_000:
        return None
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", body) if 180 <= len(part) <= 1_800]
    if not paragraphs:
        return None
    paragraph = max(paragraphs, key=_paragraph_score)
    speaker = _speaker(paragraph)
    names = [name for name in _NAME_RE.findall(paragraph) if name not in _NAME_STOP]
    if not speaker and names:
        speaker = names[0]
    terms = _distinctive_terms(paragraph, excluded={speaker.casefold()} if speaker else set())
    if len(terms) < 2:
        return None
    first_person = len(re.findall(r"\b(?:I|me|my|mine|we|our|ours)\b", paragraph, re.IGNORECASE))
    third_person = len(re.findall(r"\b(?:he|him|his|she|her|hers|they|them|their)\b", paragraph, re.IGNORECASE))
    ratio = first_person / max(1, first_person + third_person)
    return SocialPassage(
        book=book,
        text=paragraph,
        speaker=speaker,
        query_terms=tuple(terms[:3]),
        first_person_ratio=ratio,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def write_public_domain_eval_report(summary: PublicDomainEvalSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.as_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _load_book_text(book: CatalogBook, cache_dir: Path) -> tuple[str, bool]:
    path = cache_dir / f"{book.book_id}.txt"
    downloaded = False
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        url = GUTENBERG_TEXT_URL.format(book_id=book.book_id)
        payload = bytearray()
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30,
        ) as response:
            response.raise_for_status()
            _assert_gutenberg_url(str(response.url))
            for chunk in response.iter_bytes():
                payload.extend(chunk)
                if len(payload) > 3_000_000:
                    raise ValueError("book exceeds evaluation size limit")
        text = bytes(payload).decode("utf-8-sig")
        downloaded = True
    normalized = _normalize_gutenberg_text(text)
    _assert_public_domain_header(normalized)
    if downloaded or normalized != text:
        _write_cached_book(path, normalized)
    text = normalized
    return text, downloaded


def _normalize_gutenberg_text(text: str) -> str:
    """Normalize transport newlines and repair caches written with CRCRLF."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    sample_lines = normalized[:200_000].split("\n")
    if len(sample_lines) >= 100:
        empty_ratio = sum(not line.strip() for line in sample_lines) / len(sample_lines)
        if empty_ratio >= 0.45:
            normalized = normalized.replace("\n\n", "\n")
    return normalized


def _write_cached_book(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _assert_gutenberg_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"gutenberg.org", "www.gutenberg.org"}:
        raise ValueError("public-domain evaluation redirect left the approved host")


def _assert_public_domain_header(text: str) -> None:
    header = text[:20_000].lower()
    restriction_markers = (
        "copyrighted project gutenberg ebook",
        "copyright holder has given permission",
        "not in the public domain",
    )
    if any(marker in header for marker in restriction_markers):
        raise ValueError("item carries a copyright restriction marker")
    if "project gutenberg" not in header:
        raise ValueError("missing Project Gutenberg item header")


def _book_body(text: str) -> str:
    start_match = re.search(r"\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*{3}", text, re.IGNORECASE)
    end_match = re.search(r"\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", text, re.IGNORECASE)
    start = start_match.end() if start_match else 0
    end = end_match.start() if end_match and end_match.start() > start else len(text)
    return text[start:end]


def _catalog_priority(book: CatalogBook) -> tuple[int, int]:
    metadata = f"{book.subjects} {book.bookshelves}".lower()
    first_person = any(
        term in metadata for term in ("personal narratives", "autobiograph", "diaries", "correspondence", "memoir")
    )
    fiction = any(term in metadata for term in ("fiction", "school stories", "bildungsromans", "detective"))
    excluded = any(term in metadata for term in ("poetry", "drama", "reference", "periodicals"))
    bucket = 0 if first_person else 1 if fiction else 3
    if excluded:
        bucket += 3
    return bucket, book.book_id


def _paragraph_score(paragraph: str) -> float:
    quotes = paragraph.count('"') + paragraph.count("\u201c") + paragraph.count("\u201d")
    speech = len(re.findall(r"\b(?:said|asked|replied|cried|answered|whispered)\b", paragraph, re.IGNORECASE))
    first_person = len(re.findall(r"\b(?:I|me|my|we|our)\b", paragraph, re.IGNORECASE))
    names = len(_NAME_RE.findall(paragraph))
    return (2.0 * min(quotes, 6)) + (3.0 * min(speech, 3)) + min(first_person, 8) + min(names, 6)


def _speaker(paragraph: str) -> str:
    for pattern in _SPEAKER_PATTERNS:
        match = pattern.search(paragraph)
        if match and match.group(1) not in _NAME_STOP:
            return match.group(1)
    return ""


def _distinctive_terms(paragraph: str, *, excluded: set[str]) -> list[str]:
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for token in _TOKEN_RE.findall(paragraph):
        key = token.casefold()
        if key in _STOP or key in excluded or len(key) < 6:
            continue
        counts[key] = counts.get(key, 0) + 1
        display.setdefault(key, token)
    ordered = sorted(counts, key=lambda key: (counts[key] != 1, -len(key), key))
    return [display[key] for key in ordered]


def _candidate_pool(passages: list[SocialPassage], target_index: int, *, size: int) -> list[SearchResult]:
    target = passages[target_index]
    if not passages:
        return []
    indices = [target_index]
    offset = 1
    while len(indices) < min(size, len(passages)):
        candidate_index = (target_index + (offset * 7919)) % len(passages)
        if candidate_index not in indices:
            indices.append(candidate_index)
        offset += 1
    query_tokens = {token.casefold() for token in _TOKEN_RE.findall(target.query)}
    results: list[SearchResult] = []
    for rank, index in enumerate(indices, start=1):
        passage = passages[index]
        text_tokens = {token.casefold() for token in _TOKEN_RE.findall(passage.text)}
        overlap = len(query_tokens & text_tokens) / max(1, len(query_tokens))
        base = min(0.92, 0.18 + (0.72 * overlap))
        results.append(
            SearchResult(
                memory_id=f"book:{passage.book.book_id}",
                text=passage.text,
                memory_type="quote" if passage.speaker else "source_excerpt",
                local_date="",
                confidence="user_reported" if passage.speaker else "observed_by_user",
                sensitivity="personal",
                source_entry_id=f"book:{passage.book.book_id}",
                score=base,
                entity_names=[passage.speaker] if passage.speaker else [],
                source_kind="document",
                source_title=passage.book.title,
                evidence_text=passage.text,
                source_provenance=passage.book.source_url,
                evidence_metadata={
                    "attributed_to": passage.speaker,
                    "people_involved": [passage.speaker] if passage.speaker else [],
                    "epistemic_status": "attributed_statement" if passage.speaker else "source_text",
                    "source_kind": "document",
                    "title": passage.book.title,
                },
                retrieval_sources=["public_domain_lexical"],
                source_ranks={"public_domain_lexical": rank},
            )
        )
    return results


def _rate(ranks: list[int], cutoff: int) -> float:
    return round(sum(1 for rank in ranks if rank <= cutoff) / max(1, len(ranks)), 6)
