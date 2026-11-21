"""Retriever: BM25, dense, hybrid (reciprocal rank fusion, k=60) and hybrid + cross-encoder reranker.

Metadata filter runs before ranking and reranking (CLAUDE.md, corpus: rerankers can pick the wrong
near-duplicate CFR section): "no_hard_negatives" drops chunks whose authority is hard_negative
(crew rules, off-topic CBP sections, food, currency, visitors).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

METHODS = ("bm25", "dense", "hybrid", "hybrid_rerank")
FILTERS = ("none", "no_hard_negatives")
RRF_K = 60
CANDIDATES = 50  # per retriever, fed to RRF
RERANK_POOL = 30  # hybrid candidates the reranker re-scores
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")  # keeps 148.33 and 9816.00.20 whole

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank)."""
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            score[idx] = score.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(score, key=lambda i: (-score[i], i))


@dataclass
class Retriever:
    chunks: list[dict]
    method: str = "hybrid"
    filter: str = "no_hard_negatives"
    embed: EmbedFn | None = None
    reranker: object | None = (
        None  # anything with .predict(list[(query, text)]) -> scores
    )
    query_prefix: str = BGE_QUERY_PREFIX
    _bm25: object | None = field(default=None, init=False, repr=False)
    _matrix: np.ndarray | None = field(default=None, init=False, repr=False)
    last_ms: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ValueError(f"method must be one of {METHODS}")
        if self.filter not in FILTERS:
            raise ValueError(f"filter must be one of {FILTERS}")
        if self.method != "bm25" and self.embed is None:
            raise ValueError(f"{self.method} needs an embed function")
        if self.method == "hybrid_rerank" and self.reranker is None:
            raise ValueError("hybrid_rerank needs a reranker")
        self._allowed = np.array(
            [
                not (
                    self.filter == "no_hard_negatives"
                    and c.get("authority") == "hard_negative"
                )
                for c in self.chunks
            ]
        )

    # ------------------------------------------------------------ indexes (built lazily, shareable)
    def bm25_index(self):
        if self._bm25 is None:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])
        return self._bm25

    def dense_matrix(self) -> np.ndarray:
        if self._matrix is None:
            m = np.asarray(
                self.embed([c["text"] for c in self.chunks]), dtype=np.float32
            )
            self._matrix = m / np.clip(
                np.linalg.norm(m, axis=1, keepdims=True), 1e-12, None
            )
        return self._matrix

    def share_indexes(self, other: Retriever) -> Retriever:
        """Reuse another retriever's built indexes (same chunks), e.g. across filters."""
        self._bm25, self._matrix = other._bm25, other._matrix
        return self

    # ------------------------------------------------------------ ranking
    def _bm25_rank(self, query: str) -> list[int]:
        scores = np.asarray(self.bm25_index().get_scores(tokenize(query)))
        scores = np.where(self._allowed, scores, -np.inf)
        order = np.argsort(-scores, kind="stable")
        return [int(i) for i in order if np.isfinite(scores[i]) and scores[i] > 0][
            :CANDIDATES
        ]

    def _dense_rank(self, query: str) -> list[int]:
        q = np.asarray(self.embed([self.query_prefix + query])[0], dtype=np.float32)
        q /= max(float(np.linalg.norm(q)), 1e-12)
        scores = np.where(self._allowed, self.dense_matrix() @ q, -np.inf)
        order = np.argsort(-scores, kind="stable")
        return [int(i) for i in order if np.isfinite(scores[i])][:CANDIDATES]

    def rank(self, query: str) -> list[int]:
        if self.method == "bm25":
            return self._bm25_rank(query)
        if self.method == "dense":
            return self._dense_rank(query)
        fused = rrf([self._bm25_rank(query), self._dense_rank(query)])
        if self.method == "hybrid":
            return fused
        pool = fused[:RERANK_POOL]
        scores = self.reranker.predict([(query, self.chunks[i]["text"]) for i in pool])
        return [pool[j] for j in np.argsort(-np.asarray(scores), kind="stable")]

    def search(self, query: str, k: int = 5) -> list[dict]:
        t0 = time.perf_counter()
        ranked = self.rank(query)[:k]
        self.last_ms = (time.perf_counter() - t0) * 1000
        return [{**self.chunks[i], "rank": r} for r, i in enumerate(ranked, start=1)]
