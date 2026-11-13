"""Build the tool set for the active domain.

- The core always provides `search_docs` (hybrid retrieval over the domain's chunk index),
  exposed under the alias the domain pack chooses (domain.yaml tools.aliases).
- The domain's `tools.py` provides the rest via a module-level `TOOLS` dict:
  {name: {"fn": callable, "input": PydanticModel, "description": str, "ui_mode": str}}
  and optionally `LISTINGS` ({name: callable}) for read-only lists the UI needs.
Every tool takes validated input and returns a JSON-serialisable dict. Failures are returned as
{"error": ..., "retryable": bool}, never raised, so a caller (UI or agent) can always render them.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from copilot.config import Settings
from copilot.domains.loader import DomainConfig
from copilot.ingest.index import chunks_path, file_hash
from copilot.retrieval.bm25 import BM25Index
from copilot.retrieval.dense import DenseStore, collection_name, make_client
from copilot.retrieval.embed import Embedder
from copilot.retrieval.hybrid import HybridRetriever
from copilot.retrieval.rerank import Reranker


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[..., dict[str, Any]]
    ui_mode: str | None = None
    compact: Callable[[dict[str, Any]], Any] | None = None  # agent-facing view of the result
    state: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None
    is_search: bool = False

    def call(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = self.input_model.model_validate(args)
        except ValidationError as err:
            return {
                "error": "invalid arguments",
                "details": err.errors(include_url=False),
                "retryable": True,
            }
        try:
            return self.fn(**parsed.model_dump())
        except Exception as err:  # noqa: BLE001 - tools never raise into the caller
            return {"error": f"{type(err).__name__}: {err}", "retryable": False}


class SearchDocsInput(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    instrument: str | None = Field(
        default=None, description="Optional: restrict to one instrument (see GET /domain)"
    )


class Toolbox:
    """Holds the retriever and the domain tools; build once per process."""

    def __init__(self, settings: Settings, domain: DomainConfig) -> None:
        self.settings = settings
        self.domain = domain
        self._domain_module = _load_domain_module(domain)

    @cached_property
    def retriever(self) -> HybridRetriever:
        path = chunks_path(self.settings.data_dir, self.domain.name, self.settings.chunker)
        store = DenseStore(
            make_client(self.settings), collection_name(self.domain.name, self.settings.chunker)
        )
        store.check(self.domain.retrieval.embedding_model, file_hash(path))
        embedder = Embedder(
            self.settings,
            self.domain.retrieval.embedding_model,
            query_task=self.domain.retrieval.query_instruction,
        )
        r = self.domain.retrieval
        reranker = (
            Reranker(self.settings, r.reranker_model, instruction=r.query_instruction)
            if r.reranker_model
            else None
        )
        return HybridRetriever(
            BM25Index.from_jsonl(path),
            store,
            embedder.embed_query,
            candidates=r.top_k_fused,
            reranker=reranker,
        )

    @cached_property
    def instruments(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for c in self.retriever.bm25.chunks:
            out.setdefault(c["instrument"], set()).add(c["doc_id"])
        return out

    def search_docs(self, query: str, instrument: str | None = None) -> dict[str, Any]:
        doc_ids = None
        if instrument:
            if instrument not in self.instruments:
                return {
                    "error": f"unknown instrument '{instrument}'",
                    "known_instruments": sorted(self.instruments),
                    "retryable": True,
                }
            doc_ids = self.instruments[instrument]
        hits = self.retriever.search(query, k=self.domain.retrieval.top_k_final, doc_ids=doc_ids)
        by_id = self.retriever.by_id
        return {
            "query": query,
            "instrument": instrument,
            "hits": [
                {
                    "citation": h.citation,
                    "doc_id": h.doc_id,
                    "title": by_id[h.chunk_id]["title"],
                    "instrument": by_id[h.chunk_id]["instrument"],
                    "edition_date": by_id[h.chunk_id]["edition_date"],
                    "part": by_id[h.chunk_id]["part"],
                    "synthetic": by_id[h.chunk_id]["synthetic"],
                    "score": round(h.score, 5),
                    "ranks": h.ranks,
                    "text": h.text,
                }
                for h in hits
            ],
        }

    @cached_property
    def tools(self) -> dict[str, ToolSpec]:
        alias = self.domain.tools.aliases.get("search_docs", "search_docs")
        specs = {
            alias: ToolSpec(
                alias,
                "Search the indexed rule text. Returns clauses with citations (doc_id:rule_id).",
                SearchDocsInput,
                self.search_docs,
                ui_mode=self.domain.ui_modes[0] if self.domain.ui_modes else None,
                is_search=True,
            )
        }
        for name, t in getattr(self._domain_module, "TOOLS", {}).items():
            specs[name] = ToolSpec(
                name,
                t["description"],
                t["input"],
                t["fn"],
                t.get("ui_mode"),
                compact=t.get("compact"),
                state=t.get("state"),
            )
        return specs

    def listing(self, name: str) -> Any:
        fn = getattr(self._domain_module, "LISTINGS", {}).get(name)
        return None if fn is None else fn()


def _load_domain_module(domain: DomainConfig):
    if not domain.tools.module:
        return None
    path = domain.path(domain.tools.module)
    # domain modules import their own siblings (e.g. `from screening import match`)
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(f"domain_{domain.name}_tools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
