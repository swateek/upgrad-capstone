"""Embeddings on the course endpoint: bge-small-en-v1.5, 384 dimensions.

The endpoint takes at most 16 texts per request and fewer than 512 model tokens per text, so a
longer chunk is embedded as overlapping windows; each window becomes its own vector for that
chunk (customs.retrieval.dense keeps the best window per chunk at search time). Queries get
bge's retrieval prefix unless the prefix experiment turns it off (plan §6). A capacity error
(429/503) is retried like every other upgrad call. Index and query use the same model.
"""

from __future__ import annotations

from collections.abc import Sequence

from openai import OpenAI

from customs.config import Settings
from customs.llm.budget import get_tokenizer
from customs.llm.endpoints import (
    BGE_QUERY_PREFIX,
    EmbeddingEndpoint,
    embedding_endpoint,
    make_openai_client,
)
from customs.llm.retry import call_with_retry

WINDOW_MARGIN = 12  # tokens kept free for [CLS]/[SEP] and server-side tokenizer differences
WINDOW_OVERLAP = 64


class Embedder:
    def __init__(
        self,
        settings: Settings,
        use_query_prefix: bool = True,
        endpoint: EmbeddingEndpoint | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.cfg = endpoint or embedding_endpoint(settings)
        self.model = self.cfg.model
        self.query_prefix = BGE_QUERY_PREFIX if use_query_prefix else ""
        self.settings = settings
        self.url = f"{self.cfg.base_url}/embeddings"
        self.client = client or make_openai_client(self.cfg, settings.request_timeout_s)
        self.window = self.cfg.max_tokens - WINDOW_MARGIN
        self.tok = get_tokenizer(self.cfg.tokenizer_id)
        self.tokens_used = 0
        self.requests = 0

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = call_with_retry(
            lambda: self.client.embeddings.create(model=self.model, input=list(texts)),
            endpoint=self.cfg.name,
            url=self.url,
            delays=self.settings.retry_delays_s,
        )
        self.requests += 1
        if resp.usage:
            self.tokens_used += resp.usage.total_tokens
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    def windows(self, text: str) -> list[str]:
        """The text itself if it fits the endpoint's token limit, else overlapping windows."""
        enc = self.tok.encode(text, add_special_tokens=False)
        n = len(enc.ids)
        if n <= self.window:
            return [text]
        out, start, step = [], 0, self.window - WINDOW_OVERLAP
        while True:
            end = min(start + self.window, n)
            out.append(text[enc.offsets[start][0] : enc.offsets[end - 1][1]])
            if end == n:
                return out
            start += step

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text; texts must already fit the endpoint (see embed_chunks)."""
        out: list[list[float]] = []
        size = self.cfg.batch_size
        for i in range(0, len(texts), size):
            out.extend(self._embed(texts[i : i + size]))
        return out

    def embed_chunks(self, texts: Sequence[str]) -> list[list[list[float]]]:
        """One or more vectors per chunk: one per window."""
        spans = [self.windows(t) for t in texts]
        flat = self.embed_documents([w for ws in spans for w in ws])
        out, i = [], 0
        for ws in spans:
            out.append(flat[i : i + len(ws)])
            i += len(ws)
        return out

    def embed_query(self, text: str) -> list[float]:
        # an over-long query is cut to the first window, not rejected (422)
        return self._embed([self.windows(self.query_prefix + text)[0]])[0]
