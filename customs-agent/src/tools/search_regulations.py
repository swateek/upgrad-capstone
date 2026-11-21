"""search_regulations: the regulation clauses for one question (docs/RETRIEVAL.md).

Two ways in, one budget of k clauses (default 5 x <= 350 tokens):
  1. citation_ids: the rules the other tools applied (every rule in rules.yaml / rates.yaml carries
     its citation). Fetched by id: exact, no ranking. Within a section, the chunk that best matches
     the query (BM25) is taken.
  2. query: hybrid search (BM25 + dense, RRF k=60), re-ranked by BAAI/bge-reranker-v2-m3, fills the
     remaining slots, one chunk per citation.

Hard negatives (crew rules, off-topic sections) and curated secondary notes are never returned:
they are filtered before ranking and refused by id (CLAUDE.md rule 2; retrieval trap).

    search = RegulationSearch.from_env(llm)
    out = search(Args(query="4 bottles of wine after 10 days in Italy", citation_ids=["19cfr148.33"]))
    out.retrieved_ids   # the only ids the writer may cite

Settings (environment): RERANKER = model name, or "none" for plain hybrid (default
BAAI/bge-reranker-v2-m3). If the reranker cannot load, search falls back to plain hybrid and says so
in `method`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from src.retrieval.corpus import load_chunks
from src.retrieval.index import INDEX_DIR, load_or_build
from src.retrieval.retriever import Retriever
from src.schemas import Clause, Clauses
from src.tools.common import ToolError

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"
MAX_K = 5
NOT_CITABLE = frozenset({"hard_negative", "curated_secondary"})

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


class Args(BaseModel):
    query: str = Field(min_length=1, description="The traveller's question, or a sub-question")
    citation_ids: list[str] = Field(
        [], description="citation_ids of the rules the tools applied; fetched by id"
    )
    k: int = Field(MAX_K, ge=1, le=MAX_K)


def norm_id(s: str) -> str:
    return "".join(s.split()).lower()


class RegulationSearch:
    def __init__(
        self,
        chunks: list[dict],
        embed: EmbedFn,
        *,
        matrix: np.ndarray | None = None,
        reranker: object | None = None,
        reranker_name: str = "",
    ) -> None:
        self.chunks = chunks
        method = "hybrid_rerank" if reranker is not None else "hybrid"
        self.retriever = Retriever(
            chunks, method=method, filter="no_hard_negatives", embed=embed, reranker=reranker
        )
        if matrix is not None:
            self.retriever.set_matrix(matrix)
        self.method = f"hybrid+{reranker_name}" if reranker is not None else "hybrid"
        self._by_id: dict[str, list[int]] = {}
        for i, c in enumerate(chunks):
            self._by_id.setdefault(norm_id(c["citation_id"]), []).append(i)

    @classmethod
    def from_env(
        cls,
        llm,
        *,
        chunks: list[dict] | None = None,
        index_dir: Path = INDEX_DIR,
        reranker_name: str | None = None,
        log: Callable[[str], None] = print,
    ) -> RegulationSearch:
        chunks = chunks if chunks is not None else load_chunks()
        embed = lambda texts: llm.embed(texts, stage="search_regulations")  # noqa: E731
        index_embed = lambda texts: llm.embed(texts, stage="retrieval_index")  # noqa: E731
        matrix = load_or_build(chunks, index_embed, llm.embed_model, index_dir, log=log)
        name = reranker_name or os.environ.get("RERANKER", DEFAULT_RERANKER)
        reranker = None
        if name.lower() != "none":
            try:
                from sentence_transformers import CrossEncoder

                reranker = CrossEncoder(name)
            except Exception as e:  # model download or load failure: plain hybrid
                log(f"reranker {name} not loaded ({e.__class__.__name__}: {e}); using plain hybrid")
                reranker = None
        return cls(chunks, embed, matrix=matrix, reranker=reranker, reranker_name=name)

    # ------------------------------------------------------------------ search
    def _citable(self, i: int) -> bool:
        return self.chunks[i].get("authority") not in NOT_CITABLE

    def _clause(self, i: int, found_by: str, rank: int | None = None) -> Clause:
        c = self.chunks[i]
        meta = c.get("metadata") or {}
        return Clause(
            citation_id=c["citation_id"],
            chunk_id=c["chunk_id"],
            heading=c.get("heading_path") or meta.get("heading") or "",
            text=c["text"],
            authority=c.get("authority", ""),
            source_url=meta.get("source_url"),
            as_of=meta.get("as_of"),
            tokens=c.get("tokens"),
            found_by=found_by,
            rank=rank,
        )

    def __call__(self, args: Args) -> Clauses:
        t0 = time.perf_counter()
        picked: list[tuple[int, str, int | None]] = []
        seen: set[str] = set()
        not_found: list[str] = []

        # 1. by id, in the order the tools gave them
        bm25 = None
        for raw in args.citation_ids:
            cid = norm_id(raw)
            if cid in seen or raw in not_found:
                continue
            idx = [i for i in self._by_id.get(cid, []) if self._citable(i)]
            if not idx:
                not_found.append(raw)
                continue
            if len(picked) >= args.k:
                break
            if len(idx) > 1:
                bm25 = self.retriever.bm25_scores(args.query) if bm25 is None else bm25
                idx.sort(key=lambda i: (-bm25[i], i))
            picked.append((idx[0], "citation_id", None))
            seen.add(cid)

        # 2. search fills what is left, one chunk per citation
        if len(picked) < args.k:
            for rank, i in enumerate(self.retriever.rank(args.query), start=1):
                cid = norm_id(self.chunks[i]["citation_id"])
                if cid in seen or not self._citable(i):
                    continue
                picked.append((i, "search", rank))
                seen.add(cid)
                if len(picked) >= args.k:
                    break

        if not picked:
            raise ToolError("escalate", f"no regulation text found for: {args.query!r}")
        clauses = [self._clause(i, how, rank) for i, how, rank in picked]
        return Clauses(
            query=args.query,
            clauses=clauses,
            retrieved_ids=list(dict.fromkeys(c.citation_id for c in clauses)),
            not_found=not_found,
            method=self.method,
            ms=round((time.perf_counter() - t0) * 1000, 1),
        )


def search_regulations(args: Args, search: RegulationSearch) -> Clauses:
    return search(args)

