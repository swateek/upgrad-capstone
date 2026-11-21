"""Hybrid retrieval: BM25 + dense, merged with reciprocal rank fusion (RRF, k=60).

The reranker under study (plan D6) slots in after fusion: fuse top-20, rerank, keep top-k.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from customs.retrieval.bm25 import BM25Index
from customs.retrieval.dense import DenseStore
from customs.retrieval.rerank import Reranker

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
        reranker: Reranker | None = None,
    ) -> None:
        self.bm25 = bm25
        self.dense = dense
        self.embed_query = embed_query
        self.candidates = candidates
        self.reranker = reranker
        self.by_id = {c["chunk_id"]: c for c in bm25.chunks}

    def search(
        self, query: str, k: int = 5, doc_ids: set[str] | None = None, mode: str | None = None
    ) -> list[FusedHit]:
        """mode: bm25 | dense | hybrid | hybrid_rerank (default: hybrid_rerank if a reranker
        is configured, else hybrid)."""
        mode = mode or ("hybrid_rerank" if self.reranker else "hybrid")
        rerank = mode == "hybrid_rerank"
        if rerank and self.reranker is None:
            raise ValueError("hybrid_rerank needs a reranker")
        if rerank:
            mode = "hybrid"
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
        fused = rrf(rankings)
        if rerank:
            pool = fused[: self.candidates]
            order = self.reranker.rerank(query, [self.by_id[c]["text"] for c, _, _ in pool], k)
            fused = []
            for pos, (idx, score) in enumerate(order, start=1):
                cid, _, ranks = pool[idx]
                fused.append((cid, score, {**ranks, "rerank": pos}))
        hits = []
        for cid, score, ranks in fused[:k]:
            c = self.by_id[cid]
            hits.append(FusedHit(cid, c["citation"], c["doc_id"], c["text"], score, ranks))
        return hits
