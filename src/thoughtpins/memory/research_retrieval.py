"""Offline lexical indexing, exact dense search and identity-preserving fusion."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from thoughtpins.memory.benchmark_retrieval import _tokens


@dataclass(frozen=True)
class Representation:
    version: str = "dated-head-tail-v1"
    max_bytes: int = 32768

    def render(self, text: str, day: str = "") -> str:
        prefix = f"Source date: {day}\n" if day else ""
        raw = (prefix + text).encode("utf-8")
        if len(raw) <= self.max_bytes:
            return raw.decode("utf-8")
        marker = "\n[Middle omitted by fixed byte budget]\n"
        size = (self.max_bytes - len(marker.encode())) // 2
        return raw[:size].decode("utf-8", errors="ignore") + marker + raw[-size:].decode("utf-8", errors="ignore")


class LexicalIndex:
    """Same tokenizer and BM25 equation as the unchanged historical evaluator."""

    def __init__(self, documents: list[str]) -> None:
        self.count = len(documents)
        self.lengths: np.ndarray = np.empty(self.count, dtype=np.float64)
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, text in enumerate(documents):
            tokens = _tokens(text)
            self.lengths[index] = len(tokens)
            for term, count in Counter(tokens).items():
                postings[term].append((index, count))
        self.average = max(1.0, float(self.lengths.mean())) if self.count else 1.0
        self.postings = {
            term: (np.array([i for i, _ in values]), np.array([n for _, n in values], dtype=float))
            for term, values in postings.items()
        }

    def scores(self, query: str, *, k1: float = 1.2, b: float = 0.75) -> np.ndarray:
        if not math.isfinite(k1) or not math.isfinite(b) or k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Invalid BM25 parameters")
        scores: np.ndarray = np.zeros(self.count, dtype=np.float64)
        norm = k1 * (1 - b + b * self.lengths / self.average)
        for term in sorted(set(_tokens(query))):
            posting = self.postings.get(term)
            if posting is None:
                continue
            indices, counts = posting
            frequency = len(indices)
            idf = math.log(1 + (self.count - frequency + 0.5) / (frequency + 0.5))
            scores[indices] += idf * counts * (k1 + 1) / (counts + norm[indices])
        maximum = scores.max(initial=0)
        return scores / maximum if maximum > 0 else scores


def stable_order(scores: np.ndarray, identities: list[str] | None = None) -> list[int]:
    if np.isnan(scores).any():
        raise ValueError("NaN retrieval score")
    if identities is None:
        return sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
    if len(identities) != len(scores) or len(set(identities)) != len(identities):
        raise ValueError("Expected unique identities aligned with scores")
    return sorted(range(len(scores)), key=lambda i: (-float(scores[i]), identities[i]))


def unit_vectors(vectors: np.ndarray) -> np.ndarray:
    values = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    if not np.isfinite(values).all() or (norms == 0).any():
        raise ValueError("Embeddings must be finite nonzero vectors")
    return values / norms


def fuse_rankings(
    channels: dict[str, list[str]], *, k: int = 60, families: dict[str, str] | None = None
) -> list[tuple[str, float]]:
    """Equal-weight RRF with source deduplication within each retrieval family.

    Cloned paths with the same declared provenance family do not get extra votes.
    Independent lexical/dense families contribute ordinary RRF terms.
    """
    if k <= 0:
        raise ValueError("RRF k must be positive")
    votes: dict[tuple[str, str], float] = {}
    for name, ids in channels.items():
        family = families.get(name, name) if families else name
        for rank, sid in enumerate(dict.fromkeys(ids), 1):
            key = (family, sid)
            votes[key] = max(votes.get(key, 0), 1 / (k + rank))
    totals: dict[str, float] = defaultdict(float)
    for (_, sid), vote in votes.items():
        totals[sid] += vote
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))
