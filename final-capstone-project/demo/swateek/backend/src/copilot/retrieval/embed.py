"""Embeddings through an OpenAI-compatible /embeddings endpoint; the provider profile picks it.

siliconflow  Qwen3-Embedding-0.6B. Instruction-aware: queries get "Instruct: <task>\\nQuery: ",
             documents are embedded as they are.
upgrad       bge-small-en-v1.5 (384 d). Queries get bge's retrieval prefix. The endpoint takes
             at most 512 model tokens per text and 16 texts per request, so a longer chunk is
             embedded as overlapping windows; each window becomes its own vector for that
             chunk (copilot.retrieval.dense keeps the best window per chunk at search time).
"""

from __future__ import annotations

from collections.abc import Sequence

from copilot.config import Settings
from copilot.llm.budget import get_tokenizer
from copilot.llm.providers import BGE_QUERY_PREFIX, get_embedding, make_openai_client
from copilot.llm.retry import call_with_retry

# The task wording comes from the domain pack (domain.yaml retrieval.query_instruction).
DEFAULT_TASK = "Given a question, retrieve the passage that answers it"
WINDOW_MARGIN = 12  # tokens kept free for [CLS]/[SEP] and server-side tokenizer differences
WINDOW_OVERLAP = 64


class Embedder:
    def __init__(self, settings: Settings, query_task: str | None = None) -> None:
        self.cfg = get_embedding(settings)
        self.model = self.cfg.model
        if self.cfg.query_style == "bge":
            self.query_prefix = BGE_QUERY_PREFIX
        else:
            self.query_prefix = f"Instruct: {query_task or DEFAULT_TASK}\nQuery: "
        self.settings = settings
        self.url = f"{self.cfg.base_url}/embeddings"
        self.client = make_openai_client(self.cfg, settings.request_timeout_s)
        self.window = (self.cfg.max_tokens - WINDOW_MARGIN) if self.cfg.max_tokens else None
        self.tok = get_tokenizer(self.cfg.tokenizer_id) if self.cfg.tokenizer_id else None
        self.tokens_used = 0

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = call_with_retry(
            lambda: self.client.embeddings.create(model=self.model, input=list(texts)),
            provider=self.cfg.name,
            url=self.url,
            delays=self.settings.retry_delays_s,
        )
        if resp.usage:
            self.tokens_used += resp.usage.total_tokens
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    def windows(self, text: str) -> list[str]:
        """The text itself if it fits the endpoint's token limit, else overlapping windows."""
        if self.window is None or self.tok is None:
            return [text]
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
        query = self.query_prefix + text
        if self.window is not None:  # an over-long query is cut, not rejected (422)
            query = self.windows(query)[0]
        return self._embed([query])[0]
