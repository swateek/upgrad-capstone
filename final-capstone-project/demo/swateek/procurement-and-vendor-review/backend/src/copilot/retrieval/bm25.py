"""Sparse retrieval over a chunk file with rank-bm25 (fine at this corpus size)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "may",
        "must",
        "of",
        "on",
        "or",
        "our",
        "shall",
        "should",
        "that",
        "the",
        "their",
        "this",
        "to",
        "under",
        "up",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
    ]
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    citation: str
    score: float
    text: str
    n_tokens: int


class BM25Index:
    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in chunks])

    @classmethod
    def from_jsonl(cls, path: Path) -> BM25Index:
        with path.open(encoding="utf-8") as fh:
            return cls([json.loads(line) for line in fh])

    def search(self, query: str, k: int = 5, doc_ids: set[str] | None = None) -> list[Hit]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[Hit] = []
        for i in order:
            c = self.chunks[i]
            if doc_ids and c["doc_id"] not in doc_ids:
                continue
            hits.append(
                Hit(c["chunk_id"], c["citation"], float(scores[i]), c["text"], c["n_tokens"])
            )
            if len(hits) == k:
                break
        return hits
