"""Bounded inference features; no gold, answer or evaluator-type arguments."""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

from thoughtpins.memory.benchmark_retrieval import _tokens
from thoughtpins.memory.research_data import ResearchSource
from thoughtpins.memory.research_learning import FEATURE_NAMES


def query_features(
    query: str,
    sources: Sequence[ResearchSource],
    *,
    sparse: Sequence[float],
    dense: Sequence[float],
    sparse_ranks: Sequence[int],
    dense_ranks: Sequence[int],
) -> np.ndarray:
    n = len(sources)
    if not all(len(values) == n for values in (sparse, dense, sparse_ranks, dense_ranks)):
        raise ValueError("Feature inputs must describe the same source pool")
    lexical: np.ndarray = np.asarray(sparse, dtype=float)
    semantic: np.ndarray = np.asarray(dense, dtype=float)
    if not np.isfinite(lexical).all() or not np.isfinite(semantic).all():
        raise ValueError("Missing channels require explicit zero evidence")
    # Fixed cosine transform retains meaningful scale, avoiding a fitted final-data normalizer.
    semantic = np.maximum(0, semantic)
    terms = set(_tokens(query))
    lower = query.lower()
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", query))
    assistant = bool(
        re.search(
            r"\b(?:assistant|you)\b.*\b(?:recommend|suggest)|\b(?:recommend|suggest)\w*\b.*\b(?:assistant|you)\b", lower
        )
    )
    user = bool(re.search(r"\b(?:i|my|me)\b", lower)) and not assistant
    current = bool(re.search(r"\b(?:currently|current|now|latest)\b", lower))
    matrix = np.zeros((n, len(FEATURE_NAMES)))
    for i, source in enumerate(sources):
        text = source.text.lower()
        matched = len(terms.intersection(_tokens(text))) / max(1, len(terms))
        date_match = float(bool(years) and any(year in source.date or year in text for year in years))
        role_lines = [
            line for line in source.text.splitlines() if line.lower().startswith("assistant:" if assistant else "user:")
        ]
        role_match = (
            max((len(terms.intersection(_tokens(line))) / max(1, len(terms)) for line in role_lines), default=0)
            if assistant or user
            else 0
        )
        correction = matched * float(
            current and any(cue in text for cue in ("correction", "actually", "no longer", "changed to"))
        )
        instruction = -float(
            any(
                cue in text
                for cue in ("ignore previous instructions", "ignore all instructions", "return only the ranking")
            )
        )
        matrix[i] = [
            np.clip(lexical[i], 0, 1),
            np.clip(semantic[i], 0, 1),
            61 / (60 + sparse_ranks[i]) if sparse_ranks[i] > 0 else 0,
            61 / (60 + dense_ranks[i]) if dense_ranks[i] > 0 else 0,
            matched,
            date_match,
            role_match,
            correction,
            instruction,
        ]
    return matrix


def query_facets(
    query: str, sources: Sequence[ResearchSource], relevance: np.ndarray, *, gate: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """Fixed lexical facets gated by relevance; support values are not probabilities."""
    if not 0 <= gate <= 1 or len(sources) != len(relevance):
        raise ValueError("Invalid coverage gate or source alignment")
    terms = list(dict.fromkeys(_tokens(query)))[:16]
    if not terms:
        return np.zeros((len(sources), 0)), np.zeros(0)
    token_sets = [set(_tokens(source.text)) for source in sources]
    support = np.array([[float(term in tokens) for term in terms] for tokens in token_sets])
    r = np.clip(relevance, 0, 1)
    support *= np.where(r >= gate, r, 0)[:, None]
    return support, np.full(len(terms), 1 / len(terms))
