"""Pure query analysis and lexical relevance helpers for memory search."""

from __future__ import annotations

import math
import re
from collections import Counter

from thoughtpins.memory.search_types import _STOP_WORDS, _TOKEN_RE, QueryAnalysis


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())


def _analyze_query(query: str) -> QueryAnalysis:
    cleaned = _clean_query(query)
    normalized = _normalize_text(cleaned)
    token_sequence = _token_sequence(cleaned)
    tokens = set(token_sequence)
    high_value_tokens = {
        token
        for token in tokens
        if len(token) >= 6 or any(char.isdigit() for char in token) or "-" in token or "_" in token
    }
    phrases = _query_phrases(cleaned, token_sequence)
    specificity = _query_specificity(token_sequence, high_value_tokens, phrases)
    return QueryAnalysis(
        raw=query or "",
        normalized=normalized,
        token_sequence=token_sequence,
        tokens=tokens,
        high_value_tokens=high_value_tokens,
        phrases=phrases,
        specificity=specificity,
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _token_sequence(text: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN_RE.findall((text or "").lower()) if token not in _STOP_WORDS)


def _tokens(text: str) -> set[str]:
    return set(_token_sequence(text))


def _token_score(text: str, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    haystack = _tokens(text)
    if not haystack:
        return 0.0
    overlap = len(query_tokens & haystack)
    if overlap == 0:
        return 0.0
    return min(0.9, 0.45 + (overlap / max(len(query_tokens), 1)) * 0.45)


def _query_phrases(cleaned: str, token_sequence: tuple[str, ...]) -> tuple[str, ...]:
    quoted = [
        _normalize_text(match.group(1))
        for match in re.finditer(r'"([^"]{3,160})"', cleaned or "")
        if len(_token_sequence(match.group(1))) >= 2
    ]
    phrases: list[str] = []
    seen: set[str] = set()
    for phrase in quoted:
        if phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)
    if 2 <= len(token_sequence) <= 9:
        full_phrase = " ".join(token_sequence)
        if full_phrase not in seen:
            seen.add(full_phrase)
            phrases.append(full_phrase)
    for size in (3, 2):
        if len(token_sequence) < size:
            continue
        for start in range(0, len(token_sequence) - size + 1):
            fragment = " ".join(token_sequence[start : start + size])
            if fragment not in seen:
                seen.add(fragment)
                phrases.append(fragment)
    return tuple(phrases[:12])


def _query_specificity(
    token_sequence: tuple[str, ...],
    high_value_tokens: set[str],
    phrases: tuple[str, ...],
) -> float:
    if not token_sequence:
        return 0.0
    high_value_ratio = len(high_value_tokens) / max(len(set(token_sequence)), 1)
    length_signal = min(1.0, len(token_sequence) / 8)
    phrase_signal = min(1.0, len(phrases) / 4)
    return min(1.0, (0.50 * high_value_ratio) + (0.30 * length_signal) + (0.20 * phrase_signal))


def _lexical_signal(text: str, analysis: QueryAnalysis) -> float:
    token_score = _token_score(text, analysis.tokens)
    if token_score == 0:
        return max(_phrase_score(text, analysis), 0.0)
    phrase = _phrase_score(text, analysis)
    proximity = _proximity_score(_token_sequence(text), analysis.tokens)
    return min(1.0, (0.70 * token_score) + (0.18 * phrase) + (0.12 * proximity))


def _phrase_score(text: str, analysis: QueryAnalysis) -> float:
    if not analysis.phrases:
        return 0.0
    normalized = _normalize_text(text)
    if not normalized:
        return 0.0
    matched = 0
    weighted = 0.0
    for phrase in analysis.phrases:
        if phrase and phrase in normalized:
            matched += 1
            weighted += min(1.0, 0.45 + len(_token_sequence(phrase)) * 0.10)
    if matched == 0:
        return 0.0
    return min(1.0, weighted / max(len(analysis.phrases), 1))


def _proximity_score(haystack_tokens: tuple[str, ...], query_tokens: set[str]) -> float:
    if len(query_tokens) < 2 or not haystack_tokens:
        return 0.0
    matched_tokens = query_tokens & set(haystack_tokens)
    if len(matched_tokens) < 2:
        return 0.0

    postings = [(index, token) for index, token in enumerate(haystack_tokens) if token in matched_tokens]
    counts: Counter[str] = Counter()
    covered = 0
    best_span: int | None = None
    left = 0
    for right, (right_index, right_token) in enumerate(postings):
        if counts[right_token] == 0:
            covered += 1
        counts[right_token] += 1
        while covered == len(matched_tokens) and left <= right:
            left_index, left_token = postings[left]
            span = right_index - left_index + 1
            best_span = span if best_span is None else min(best_span, span)
            counts[left_token] -= 1
            if counts[left_token] == 0:
                covered -= 1
            left += 1

    if best_span is None:
        return 0.0
    coverage = len(matched_tokens) / max(len(query_tokens), 1)
    compactness = math.exp(-max(0, best_span - len(matched_tokens)) / 12)
    return min(1.0, coverage * compactness)
