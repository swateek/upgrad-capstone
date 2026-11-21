"""Retrieval over the regulation corpus: BM25, dense, hybrid (RRF k=60), reranker, metadata filter.

    from src.retrieval import Retriever, load_chunks
    r = Retriever(load_chunks(), method="hybrid", embed=llm_embed_fn)
    hits = r.search("how many cigars duty free", k=5)   # [{"chunk_id", "citation_id", "text", "score", ...}]

The writer may cite only the `citation_id`s of chunks returned here (CLAUDE.md rule 2).
"""

from src.retrieval.corpus import build_chunks, load_chunks
from src.retrieval.retriever import FILTERS, METHODS, Retriever

__all__ = ["FILTERS", "METHODS", "Retriever", "build_chunks", "load_chunks"]
