"""Small deterministic lexical helpers used when semantic retrieval is unavailable."""

from __future__ import annotations

import re

QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "all",
        "am",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "did",
        "do",
        "does",
        "for",
        "from",
        "have",
        "hey",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "remember",
        "show",
        "tell",
        "that",
        "the",
        "there",
        "to",
        "up",
        "was",
        "what",
        "when",
        "where",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)


def context_tokens(text: str) -> set[str]:
    """Tokenize query text while retaining useful compound identifiers."""

    return {
        token for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", (text or "").lower()) if token not in QUERY_STOP_WORDS
    }


def fallback_tokens(text: str) -> set[str]:
    """Tokenize text for the conservative local-answer fallback."""

    return {
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(token) > 2 and token not in QUERY_STOP_WORDS
    }
