"""Embeddings through the provider's OpenAI-compatible /embeddings endpoint (SiliconFlow).

Embeddings stay on SiliconFlow even after chat moves to the course endpoint, which has none.
Qwen3-Embedding is instruction-aware: queries get a task instruction, documents don't.
"""

from __future__ import annotations

from collections.abc import Sequence

from openai import OpenAI

from copilot.config import Settings
from copilot.llm.retry import RateGate, call_with_retry

MAX_BATCH = 32  # SiliconFlow: "the maximum array size is 32"
# Qwen3-Embedding query format. The task wording comes from the domain pack
# (domain.yaml retrieval.query_instruction); documents are embedded without it.
DEFAULT_TASK = "Given a question, retrieve the passage that answers it"


class Embedder:
    def __init__(
        self,
        settings: Settings,
        model: str,
        dimensions: int | None = None,
        query_task: str | None = None,
    ) -> None:
        if settings.siliconflow_api_key is None:
            raise RuntimeError("SILICONFLOW_API_KEY is needed for embeddings")
        self.model = model
        self.query_prefix = f"Instruct: {query_task or DEFAULT_TASK}\nQuery: "
        self.dimensions = dimensions
        self.settings = settings
        self.url = f"{settings.siliconflow_base_url}/embeddings"
        self.client = OpenAI(
            base_url=settings.siliconflow_base_url,
            api_key=settings.siliconflow_api_key.get_secret_value(),
            timeout=settings.request_timeout_s,
            max_retries=0,
        )
        self.gate = RateGate(settings.max_concurrency, settings.requests_per_minute)
        self.tokens_used = 0

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        extra = {"dimensions": self.dimensions} if self.dimensions else {}
        resp = call_with_retry(
            lambda: self.client.embeddings.create(model=self.model, input=list(texts), **extra),
            provider="siliconflow",
            url=self.url,
            delays=self.settings.retry_delays_s,
            gate=self.gate,
        )
        if resp.usage:
            self.tokens_used += resp.usage.total_tokens
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), MAX_BATCH):
            out.extend(self._embed(texts[i : i + MAX_BATCH]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.query_prefix + text])[0]
