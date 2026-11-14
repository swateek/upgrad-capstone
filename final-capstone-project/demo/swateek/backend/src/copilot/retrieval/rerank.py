"""Reranking of the fused top-20. Two kinds, picked by the provider profile:

  Reranker      siliconflow: a cross-encoder behind /v1/rerank (Qwen3-Reranker-8B). On
                api.siliconflow.com only Qwen3-Reranker-0.6B and -8B exist (bge-reranker-v2-m3
                is .cn only; checked 13 Nov 2026). It takes an optional task instruction.
  ChatReranker  upgrad: the course endpoints have no reranker, and Track B requires one, so
                Qwen3-8B on the course chat endpoint orders the candidates in one listwise call.
                Each passage is cut so the prompt fits the 8K window. If the reply has no usable
                numbers, the fused order stands (logged), so retrieval never fails on it.

Hosted instead of a local CPU model to keep PyTorch out of the image (plan §1.1).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence

import openai

from copilot.agent.context import current
from copilot.config import Settings
from copilot.llm.budget import count_message_tokens, get_tokenizer
from copilot.llm.providers import RerankConfig, make_http_client, make_openai_client
from copilot.llm.retry import call_with_retry

log = logging.getLogger(__name__)


class RerankError(RuntimeError):
    pass


class Reranker:
    def __init__(
        self, settings: Settings, cfg: RerankConfig, instruction: str | None = None
    ) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.instruction = instruction if cfg.model.startswith("Qwen/Qwen3-Reranker") else None
        self.settings = settings
        self.url = f"{cfg.base_url}/rerank"
        self.http = make_http_client(cfg, settings.request_timeout_s)
        self.http.headers["Authorization"] = f"Bearer {cfg.api_key}"
        self.tokens_used = 0

    def _post(self, payload: dict) -> dict:
        resp = self.http.post(self.url, json=payload)
        if resp.status_code != 200:
            # reuse the Track B retry policy, which keys on openai.APIStatusError
            raise openai.APIStatusError(
                f"rerank HTTP {resp.status_code}", response=resp, body=resp.text[:300]
            )
        return resp.json()

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        """Return (original index, relevance score) for the top_n documents, best first."""
        if not documents:
            return []
        payload = {
            "model": self.model,
            "query": query,
            "documents": list(documents),
            "top_n": min(top_n, len(documents)),
            "return_documents": False,
        }
        if self.instruction:
            payload["instruction"] = self.instruction
        data = call_with_retry(
            lambda: self._post(payload),
            provider=self.cfg.name,
            url=self.url,
            delays=self.settings.retry_delays_s,
        )
        tokens = (data.get("meta") or {}).get("tokens") or {}
        self.tokens_used += int(tokens.get("input_tokens", 0) or 0)
        results = data.get("results")
        if not isinstance(results, list):
            raise RerankError(f"unexpected rerank response: {str(data)[:200]}")
        return [(int(r["index"]), float(r["relevance_score"])) for r in results]


LISTWISE_SYSTEM = (
    "You rank search results. Read the question and the numbered passages. Reply with the "
    "numbers of the {n} passages that best answer the question, most relevant first, separated "
    "by commas. Reply with the numbers only."
)
THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)
PASSAGE_TOKENS = 300  # per passage at most; less when 20 passages would not fit
REPLY_TOKENS = 40


class ChatReranker:
    """Listwise reranking with the chat model: one call per search, best first."""

    def __init__(
        self, settings: Settings, cfg: RerankConfig, instruction: str | None = None
    ) -> None:
        self.cfg = cfg
        self.model = f"{cfg.model} (listwise)"
        self.instruction = instruction
        self.settings = settings
        self.url = f"{cfg.base_url}/chat/completions"
        self.client = make_openai_client(cfg, settings.request_timeout_s)
        self.tok = get_tokenizer(settings.tokenizer_id)
        self.tokens_used = 0
        self.fallbacks = 0  # replies with no usable order; the fused order was kept

    def _cut(self, text: str, limit: int) -> str:
        enc = self.tok.encode(text)
        if len(enc.ids) <= limit:
            return text
        return text[: enc.offsets[limit - 1][1]] + " …"

    def messages(self, query: str, documents: Sequence[str], top_n: int) -> list[dict]:
        """The prompt, with passages cut until it fits the window with room for the reply."""
        limit = self.settings.context_window_tokens - REPLY_TOKENS
        per = PASSAGE_TOKENS
        while True:
            blocks = "\n\n".join(
                f"[{i}] {self._cut(d, per)}" for i, d in enumerate(documents, start=1)
            )
            task = f"Task: {self.instruction}\n\n" if self.instruction else ""
            msgs = [
                {"role": "system", "content": LISTWISE_SYSTEM.format(n=top_n)},
                {
                    "role": "user",
                    "content": f"{task}Question: {query}\n\nPassages:\n{blocks}\n\n"
                    f"The {top_n} most relevant passage numbers, best first:",
                },
            ]
            if count_message_tokens(self.tok, msgs) <= limit or per <= 40:
                return msgs
            per = int(per * 0.8)

    @staticmethod
    def parse(reply: str, n_docs: int, top_n: int) -> list[int] | None:
        """0-based indices in the model's order, filled up from the fused order; None if the
        reply names no valid passage."""
        reply = THINK.sub("", reply)
        order: list[int] = []
        for m in re.findall(r"\d+", reply):
            i = int(m) - 1
            if 0 <= i < n_docs and i not in order:
                order.append(i)
        if not order:
            return None
        order += [i for i in range(n_docs) if i not in order]
        return order[:top_n]

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        """Return (original index, score) for the top_n documents, best first. The score is
        1/rank: the model gives an order, not a relevance value."""
        if not documents:
            return []
        top_n = min(top_n, len(documents))
        msgs = self.messages(query, documents, top_n)
        t0 = time.perf_counter()
        resp = call_with_retry(
            lambda: self.client.chat.completions.create(
                model=self.cfg.model,
                messages=msgs,
                temperature=0,
                max_tokens=REPLY_TOKENS,
                extra_body=self.cfg.extra_body,
            ),
            provider=self.cfg.name,
            url=self.url,
            delays=self.settings.retry_delays_s,
        )
        tokens = resp.usage.total_tokens if resp.usage else 0
        self.tokens_used += tokens
        order = self.parse(resp.choices[0].message.content or "", len(documents), top_n)
        if order is None:
            self.fallbacks += 1
            log.warning("listwise rerank reply had no passage numbers; fused order kept")
            order = list(range(top_n))
        ctx = current()  # inside an agent run: the extra chat call counts and is recorded
        if ctx is not None:
            # counts toward the per-query token cap (team decision), not the 10-step cap: it is
            # part of the search tool, as the SiliconFlow cross-encoder is
            ctx.add_tokens(tokens)
            ctx.emit(
                "rerank",
                model=self.model,
                tokens=tokens,
                seconds=round(time.perf_counter() - t0, 2),
                fallback=order == list(range(top_n)) and self.fallbacks > 0,
            )
        return [(i, 1.0 / rank) for rank, i in enumerate(order, start=1)]


def make_reranker(
    settings: Settings, cfg: RerankConfig | None, instruction: str | None = None
) -> Reranker | ChatReranker | None:
    if cfg is None:
        return None
    if cfg.kind == "chat_listwise":
        return ChatReranker(settings, cfg, instruction)
    return Reranker(settings, cfg, instruction)
