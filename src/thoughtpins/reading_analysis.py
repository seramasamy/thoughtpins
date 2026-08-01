"""Cheap deterministic analysis for saved reading sources."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9&'.-]{2,}")
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,3}\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_LEADING_ARTICLES = {"a", "an", "the"}
_STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "among",
    "another",
    "article",
    "because",
    "before",
    "being",
    "between",
    "could",
    "during",
    "every",
    "first",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "over",
    "said",
    "same",
    "should",
    "source",
    "their",
    "there",
    "than",
    "that",
    "them",
    "then",
    "these",
    "thing",
    "this",
    "those",
    "through",
    "under",
    "using",
    "where",
    "which",
    "while",
    "with",
    "would",
}
_PUBLISHER_LABELS = {
    "wsj.com": "The Wall Street Journal",
    "economist.com": "The Economist",
    "bloomberg.com": "Bloomberg",
    "ft.com": "Financial Times",
    "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post",
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "semianalysis.com": "SemiAnalysis",
    "stratechery.com": "Stratechery",
    "substack.com": "Substack",
}
_TOPIC_KEYWORDS = {
    "economics": ("inflation", "rates", "central bank", "gdp", "labor", "trade", "recession", "productivity"),
    "markets": ("stock", "bond", "equity", "earnings", "valuation", "yield", "portfolio", "investor"),
    "business": ("company", "revenue", "profit", "strategy", "customers", "industry", "pricing", "competition"),
    "technology": ("software", "ai", "model", "data", "chip", "cloud", "platform", "compute", "security"),
    "politics": ("election", "policy", "government", "law", "regulation", "congress", "minister", "party"),
    "culture": ("book", "film", "music", "art", "media", "culture", "essay", "review"),
    "health": ("doctor", "medical", "health", "disease", "treatment", "clinical", "patient", "study"),
    "science": ("research", "experiment", "physics", "biology", "climate", "energy", "scientists", "paper"),
    "philosophy": ("meaning", "ethics", "attention", "consciousness", "virtue", "truth", "belief", "wisdom"),
}


def reading_analysis_metadata(
    *,
    title: str,
    text: str,
    source_domain: str | None,
    source_url: str | None,
    author: str | None,
    published_at: datetime | None,
    publisher_hint: str | None = None,
) -> dict[str, Any]:
    clean = _clean_text(text)
    domain = (source_domain or (urlparse(source_url).hostname if source_url else "") or "").lower()
    publisher = _clean_text(publisher_hint or "")[:255] or publisher_label(domain)
    topics = infer_reading_topics(title, clean, domain)
    concepts = extract_key_concepts(title, clean)
    word_count = len(_WORD_RE.findall(clean))
    return {
        "publisher": publisher,
        "source_domain": domain,
        "source_url": source_url,
        "title": title,
        "author": author,
        "published_at": published_at.isoformat() if published_at else None,
        "topics": topics,
        "key_concepts": concepts,
        "word_count": word_count,
        "reading_memory_version": 1,
    }


def publisher_label(domain: str) -> str:
    domain = (domain or "").lower().removeprefix("www.")
    if not domain:
        return "Unknown source"
    if domain.endswith(".substack.com"):
        publication = domain.removesuffix(".substack.com").split(".")[-1]
        if publication and publication not in {"open", "www"}:
            return publication.replace("-", " ").title()
    for suffix, label in _PUBLISHER_LABELS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return label
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2].replace("-", " ").title()
    return domain.title()


def infer_reading_topics(title: str, text: str, domain: str) -> list[str]:
    haystack = f"{title}\n{text[:12000]}".lower()
    scores: list[tuple[int, str]] = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            score += haystack.count(keyword)
        if topic in domain:
            score += 2
        if score:
            scores.append((score, topic))
    if not scores:
        return ["general"]
    return [topic for _score, topic in sorted(scores, key=lambda item: (-item[0], item[1]))[:5]]


def extract_key_concepts(title: str, text: str, *, limit: int = 16) -> list[str]:
    sample = _clean_text(f"{title}. {text[:20000]}")
    concepts: list[str] = []
    seen: set[str] = set()

    for phrase in _proper_noun_phrases(sample):
        if _concept_is_useful(phrase, seen):
            seen.add(phrase.lower())
            concepts.append(phrase)
        if len(concepts) >= limit // 2:
            break

    words = [
        word.lower().strip("'.-")
        for word in _WORD_RE.findall(sample)
        if word.lower().strip("'.-") not in _STOPWORDS and len(word) >= 4
    ]
    counts: dict[str, int] = {}
    for size in (2, 3):
        for i in range(0, max(0, len(words) - size + 1)):
            phrase_words = words[i : i + size]
            if len(set(phrase_words)) != len(phrase_words):
                continue
            phrase = " ".join(phrase_words)
            counts[phrase] = counts.get(phrase, 0) + 1
    for phrase, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if count < 2 and len(concepts) >= 6:
            continue
        label = phrase.title()
        if _concept_is_useful(label, seen):
            seen.add(label.lower())
            concepts.append(label)
        if len(concepts) >= limit:
            break
    return concepts


def _proper_noun_phrases(sample: str) -> list[str]:
    """Yield capitalized phrases that look like names rather than sentence starts.

    Scanning the whole sample at once let a match run across a full stop, which
    produced entries like "Atomic Notes. Atomic". Scanning sentence by sentence
    keeps each candidate inside one sentence, and a phrase sitting at the very
    start of a sentence is only kept when it is more than a single word, since
    the first word of any sentence is capitalized by grammar rather than by
    being somebody's name.
    """
    phrases: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(sample):
        sentence = sentence.strip()
        if not sentence:
            continue
        for match in _PROPER_NOUN_RE.finditer(sentence):
            phrase = _clean_text(match.group(0)).strip(".,;: ")
            if not phrase:
                continue
            if match.start() == 0:
                words = phrase.split()
                if words and words[0].lower() in _LEADING_ARTICLES:
                    words = words[1:]
                    phrase = " ".join(words)
                if len(words) < 2:
                    continue
            phrases.append(phrase)
    return phrases


def _concept_is_useful(phrase: str, seen: set[str]) -> bool:
    normalized = phrase.lower().strip()
    if len(normalized) < 4 or normalized in seen:
        return False
    if normalized in _STOPWORDS:
        return False
    words = normalized.split()
    if len(words) > 5:
        return False
    if all(word in _STOPWORDS for word in words):
        return False
    return True


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()
