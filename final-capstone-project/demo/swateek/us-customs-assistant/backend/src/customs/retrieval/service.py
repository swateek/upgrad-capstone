"""search_regulations: sources for the rules an answer relies on (plan §4.4, D20; SPEC §8).

For each rule the calculators used (`rule_refs`: R9, R4:third_country, state:CA, ...), one search
with the configuration the retrieval experiment chose (docs/results/retrieval-decisions.md):
window200 chunks, hybrid BM25 + bge, the question + the rule's name as the query, the rule's topic
filter, passages up to the token budget. The first passage in that budget that holds one of the
rule's signed-off clause ids becomes the rule's source. If none does, the clause is fetched by id
from the corpus and the miss is logged (`retrieval_miss_recovered`), so citations never depend on
retrieval alone. All of the question's queries are embedded in one request.

Retrieved text is data: only passages holding a rule's own clause ids reach the writer, so
planted lines in other documents (pack/corpus/synthetic) never do.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cached_property

import yaml

from customs.config import Settings
from customs.retrieval.query import build_query, scope
from customs.tools.tables import Tables, load_tables

SNIPPET_TOKENS = 200


@dataclass
class Source:
    handle: str  # S1, S2, ...
    clause_id: str  # e.g. cfr19_p148:148.35(a)
    citation: str  # e.g. 19 CFR 148.35
    text: str
    url: str | None
    rules: list[str] = field(default_factory=list)  # rule refs it supports
    retrieved: bool = True  # False: fetched by id after a retrieval miss

    def as_dict(self) -> dict:
        return {
            "handle": self.handle,
            "clause_id": self.clause_id,
            "citation": self.citation,
            "url": self.url,
            "rules": self.rules,
            "retrieved": self.retrieved,
        }


def split_ref(ref: str) -> tuple[str, str | None]:
    """'R4:third_country' -> ('R4', 'third_country'); 'state:CA' -> ('CA', None)."""
    if ref.startswith("state:"):
        return ref.split(":", 1)[1], None
    key, _, part = ref.partition(":")
    return key, part or None


def cites_for(tables: Tables, ref: str) -> list[str]:
    key, part = split_ref(ref)
    if ref.startswith("state:"):
        return list(tables.states[key]["cites"])
    return tables.cites(key, part)


class Corpus:
    """Clause text by id (documents.jsonl) and source URLs (manifest)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def docs(self) -> dict[str, dict]:
        path = self.settings.data_dir / "chunks" / "documents.jsonl"
        out = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                d = json.loads(line)
                out[d["doc_id"]] = d
        return out

    @cached_property
    def urls(self) -> dict[str, str]:
        man = yaml.safe_load(
            (self.settings.pack_dir / "corpus" / "manifest.yaml").read_text(encoding="utf-8")
        )
        return {s["id"]: s.get("source_page") or s.get("url") for s in man["sources"]}

    def url(self, clause_id: str) -> str | None:
        return self.urls.get(clause_id.split(":", 1)[0])


class RegulationSearch:
    """Retrieve-first sources for a set of rule refs. `rankings` is injected in tests."""

    def __init__(
        self,
        settings: Settings,
        rankings: Callable[[list[str], list[set[str] | None]], list[list[dict]]] | None = None,
        corpus: Corpus | None = None,
        tables: Tables | None = None,
    ) -> None:
        self.settings = settings
        self.tables = tables or load_tables()
        self.corpus = corpus or Corpus(settings)
        self._rankings = rankings
        self.embed_requests = 0

    # --- the real retriever (built lazily: tests inject `rankings`) ---------------------------
    @cached_property
    def _retriever(self):
        from customs.ingest.index import load_chunks
        from customs.retrieval.bm25 import BM25Index
        from customs.retrieval.dense import DenseStore, collection_name, make_client
        from customs.retrieval.hybrid import HybridRetriever

        chunks, corpus_hash = load_chunks(self.settings, self.settings.chunker)
        dense = DenseStore(
            make_client(self.settings),
            collection_name(self.settings.chunker, self.settings.embedding_model),
        )
        dense.check(self.settings.embedding_model, corpus_hash)
        self._vectors: dict[str, list[float]] = {}
        return HybridRetriever(BM25Index(chunks), dense, lambda q: self._vectors[q])

    @cached_property
    def _embedder(self):
        from customs.retrieval.embed import Embedder

        return Embedder(self.settings, use_query_prefix=self.settings.use_query_prefix)

    @cached_property
    def source_topics(self) -> dict[str, str]:
        return {d["source_id"]: d["topic"] for d in self.corpus.docs.values()}

    @cached_property
    def _reranker(self):
        """Option A (listwise, Qwen3-8B) by default; none or the local cross-encoder if configured."""
        from customs.retrieval.rerank import CrossEncoderReranker, ListwiseReranker

        if self.settings.reranker == "listwise":
            return ListwiseReranker(
                self.settings,
                observer=self._observe_rerank,
                passage_tokens=self.settings.reranker_passage_tokens,
            )
        if self.settings.reranker == "cross_encoder":
            return CrossEncoderReranker(self.settings)
        return None

    def _observe_rerank(self, rec: dict) -> None:
        """Each rerank call counts toward the question's model-call and token caps (plan 4.6)."""
        from types import SimpleNamespace

        from customs.agent import context

        try:
            ctx = context.current()
        except RuntimeError:  # outside a question (offline tools): nothing to count against
            return
        ctx.after_model_call("rerank", SimpleNamespace(
            total_tokens=rec["tokens"], seconds=rec["seconds"], calls=1))  # fmt: skip

    def _real_rankings(
        self, queries: list[str], filters: list[set[str] | None], rerank: bool = False
    ) -> list[list[dict]]:
        retr = self._retriever
        missing = [q for q in dict.fromkeys(queries) if q not in self._vectors]
        if missing:
            texts = [self._embedder.windows(self._embedder.query_prefix + q)[0] for q in missing]
            before = self._embedder.requests
            for q, v in zip(missing, self._embedder.embed_documents(texts), strict=True):
                self._vectors[q] = v
            self.embed_requests += self._embedder.requests - before
        out = []
        rerank = rerank and self._reranker is not None
        for q, flt in zip(queries, filters, strict=True):
            if not rerank:
                hits = retr.search(q, k=20, doc_ids=flt, mode="hybrid")
            else:
                import logging

                import openai

                retr.reranker = self._reranker
                retr.candidates = self.settings.reranker_pool
                try:
                    hits = retr.search(q, k=20, doc_ids=flt, mode="hybrid_rerank")
                except (openai.APIStatusError, openai.APIConnectionError) as err:
                    logging.getLogger(__name__).warning("rerank failed, fused order kept: %s", err)
                    hits = retr.search(q, k=20, doc_ids=flt, mode="hybrid")
                finally:
                    retr.candidates = 20
            out.append([retr.by_id[h.chunk_id] for h in hits])
        return out

    # --- search -------------------------------------------------------------------------------
    def search(self, question: str, rule_refs: Sequence[str]) -> tuple[list[Source], dict]:
        """One source per rule ref (shared when two rules cite the same clause)."""
        refs = [r for r in dict.fromkeys(rule_refs) if self._known(r)]
        stats = {"queries": len(refs), "retrieved": 0, "recovered": [], "embed_requests": 0}
        if not refs:
            return [], stats
        keys = [split_ref(r)[0] for r in refs]
        queries = [build_query(question, self.tables, [k]) for k in keys]
        filters = [
            scope(self.tables, [k], self.source_topics) if self.settings.topic_filter else None
            for k in keys
        ]
        before = self.embed_requests
        flts = [f or None for f in filters]
        if self._rankings:
            rankings = self._rankings(queries, flts)
        else:
            rankings = self._real_rankings(queries, flts, rerank=True)
        stats["embed_requests"] = self.embed_requests - before
        by_clause: dict[str, Source] = {}
        for ref, ranking in zip(refs, rankings, strict=True):
            cites = cites_for(self.tables, ref)
            found = self._first_in_budget(ranking, cites)
            if found is not None:
                chunk, clause = found
                stats["retrieved"] += 1
                text, retrieved = chunk["text"], True
            else:
                clause = next((c for c in cites if c in self.corpus.docs), None)
                if clause is None:
                    continue
                stats["recovered"].append(ref)
                text, retrieved = self.corpus.docs[clause]["text"], False
            src = by_clause.get(clause)
            if src is None:
                doc = self.corpus.docs.get(clause, {})
                src = Source(
                    handle=f"S{len(by_clause) + 1}",
                    clause_id=clause,
                    citation=doc.get("citation", clause),
                    text=self._cut(text),
                    url=self.corpus.url(clause),
                    retrieved=retrieved,
                )
                by_clause[clause] = src
            src.rules.append(ref)
        return list(by_clause.values()), stats

    def _known(self, ref: str) -> bool:
        key, _ = split_ref(ref)
        return key in self.tables.rules or (ref.startswith("state:") and key in self.tables.states)

    def _first_in_budget(self, ranking: list[dict], cites: list[str]) -> tuple[dict, str] | None:
        used = 0
        for chunk in ranking:
            used += chunk.get("n_tokens", 0)
            if used > self.settings.passage_budget_tokens and used != chunk.get("n_tokens", 0):
                return None
            hit = [c for c in cites if c in chunk.get("clause_ids", [])]
            if hit:
                return chunk, hit[0]
        return None

    def _cut(self, text: str) -> str:
        words = text.split()
        limit = int(SNIPPET_TOKENS * 0.75)  # ~words per token for regulatory English
        return text if len(words) <= limit else " ".join(words[:limit]) + " …"

    # --- plain RAG (single_rag mode): the question alone, no filter -------------------------
    def top_passages(self, question: str, k: int = 5) -> list[Source]:
        ranking = (self._rankings or self._real_rankings)([question], [None])[0][:k]
        out = []
        for i, chunk in enumerate(ranking, start=1):
            clause = (chunk.get("clause_ids") or [chunk.get("doc_id", "")])[0]
            out.append(
                Source(
                    handle=f"S{i}",
                    clause_id=clause,
                    citation=chunk.get("citation", clause),
                    text=self._cut(chunk["text"]),
                    url=self.corpus.url(clause),
                )
            )
        return out
