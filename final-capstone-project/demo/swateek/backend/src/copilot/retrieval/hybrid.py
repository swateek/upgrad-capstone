"""Hybrid retrieval: BM25 + dense, merged with reciprocal rank fusion (RRF).

The reranker (Phase 3) slots in after fusion: fuse top-20, rerank, keep top-k.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from copilot.retrieval.bm25 import BM25Index
from copilot.retrieval.dense import DenseStore

RRF_K = 60  # standard constant from Cormack et al.; dampens the head of each list


@dataclass
class FusedHit:
    chunk_id: str
    citation: str
    doc_id: str
    text: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # 1-based rank per retriever


def rrf(rankings: dict[str, list[str]], k: int = RRF_K) -> list[tuple[str, float, dict[str, int]]]:
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, ids in rankings.items():
        for r, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + r)
            ranks.setdefault(cid, {})[name] = r
    order = sorted(scores, key=lambda c: (-scores[c], c))
    return [(c, scores[c], ranks[c]) for c in order]


class HybridRetriever:
    def __init__(
        self,
        bm25: BM25Index,
        dense: DenseStore,
        embed_query: Callable[[str], list[float]],
        candidates: int = 20,
    ) -> None:
        self.bm25 = bm25
        self.dense = dense
        self.embed_query = embed_query
        self.candidates = candidates
        self.by_id = {c["chunk_id"]: c for c in bm25.chunks}

    def search(
        self, query: str, k: int = 5, doc_ids: set[str] | None = None, mode: str = "hybrid"
    ) -> list[FusedHit]:
        rankings: dict[str, list[str]] = {}
        if mode in ("hybrid", "bm25"):
            rankings["bm25"] = [
                h.chunk_id for h in self.bm25.search(query, self.candidates, doc_ids)
            ]
        if mode in ("hybrid", "dense"):
            vec = self.embed_query(query)
            rankings["dense"] = [
                h.chunk_id for h in self.dense.search(vec, self.candidates, doc_ids)
            ]
        hits = []
        for cid, score, ranks in rrf(rankings)[:k]:
            c = self.by_id[cid]
            hits.append(FusedHit(cid, c["citation"], c["doc_id"], c["text"], score, ranks))
        return hits
