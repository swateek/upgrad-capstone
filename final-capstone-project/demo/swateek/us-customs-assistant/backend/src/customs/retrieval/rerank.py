"""Reranking of the fused top-20 (plan D6: measure none vs listwise vs a local cross-encoder).

ListwiseReranker  Qwen3-8B on the course chat endpoint orders the candidates in one call. Each
                  passage is cut so the prompt fits the 8K window. If the reply names no valid
                  passage, the fused order stands (counted), so retrieval never fails on it.
                  Its chat call counts toward the question's model-call and token caps
                  (plan §4.6); `observer` receives one record per call for the trace.
CrossEncoderReranker  ms-marco-MiniLM-L-6-v2 run locally (ONNX, via fastembed; no upgrad call).
                  Scores each (question, passage) pair; passages are cut at 512 tokens.
                  fastembed is in the `experiment` dependency group (`uv sync --group
                  experiment`); it joins the main dependencies only if the experiment picks it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from customs.config import Settings
from customs.llm.budget import count_message_tokens
from customs.llm.chat import ChatClient

log = logging.getLogger(__name__)


class Reranker(Protocol):
    model: str

    def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[tuple[int, float]]: ...


LISTWISE_SYSTEM = (
    "You rank search results. Read the question and the numbered passages. Reply with the "
    "numbers of the {n} passages that best answer the question, most relevant first, separated "
    "by commas. Reply with the numbers only."
)
PASSAGE_TOKENS = 300  # per passage at most; less when 20 passages would not fit
REPLY_TOKENS = 40


class ListwiseReranker:
    """Listwise reranking with the chat model: one call per search, best first."""

    def __init__(
        self,
        settings: Settings,
        chat: ChatClient | None = None,
        observer: Callable[[dict[str, Any]], None] | None = None,
        passage_tokens: int = PASSAGE_TOKENS,
    ) -> None:
        self.settings = settings
        self.passage_tokens = passage_tokens  # per passage, cut to this many tokens at most
        self.chat = chat or ChatClient(settings)
        self.model = f"{self.chat.endpoint.model} (listwise)"
        self.tok = self.chat.tok
        self.observer = observer
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
        per = self.passage_tokens
        while True:
            blocks = "\n\n".join(
                f"[{i}] {self._cut(d, per)}" for i, d in enumerate(documents, start=1)
            )
            msgs = [
                {"role": "system", "content": LISTWISE_SYSTEM.format(n=top_n)},
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nPassages:\n{blocks}\n\n"
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
        """(original index, 1/rank) for the top_n documents, best first."""
        if not documents:
            return []
        top_n = min(top_n, len(documents))
        res = self.chat.complete(self.messages(query, documents, top_n), max_tokens=REPLY_TOKENS)
        self.tokens_used += res.total_tokens
        order = self.parse(res.text, len(documents), top_n)
        fallback = order is None
        if fallback:
            self.fallbacks += 1
            log.warning("listwise rerank reply had no passage numbers; fused order kept")
            order = list(range(top_n))
        if self.observer is not None:
            self.observer(
                {
                    "event": "rerank",
                    "model": self.model,
                    "tokens": res.total_tokens,
                    "seconds": res.seconds,
                    "fallback": fallback,
                }
            )
        return [(i, 1.0 / rank) for rank, i in enumerate(order, start=1)]


CROSS_ENCODER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Local cross-encoder: one forward pass per (question, passage) pair, best first."""

    def __init__(self, settings: Settings, model_name: str = CROSS_ENCODER_MODEL) -> None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as err:  # pragma: no cover - depends on the optional group
            raise RuntimeError(
                "the cross-encoder needs fastembed: uv sync --group experiment"
            ) from err
        self.model = f"{model_name} (local)"
        cache = settings.data_dir / "models"
        cache.mkdir(parents=True, exist_ok=True)
        self.encoder = TextCrossEncoder(model_name, cache_dir=str(cache))

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        if not documents:
            return []
        scores = [float(x) for x in self.encoder.rerank(query, list(documents), batch_size=32)]
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [(i, scores[i]) for i in order[: min(top_n, len(documents))]]


def make_reranker(
    settings: Settings, observer: Callable[[dict[str, Any]], None] | None = None
) -> Reranker | None:
    if settings.reranker == "none":
        return None
    if settings.reranker == "listwise":
        return ListwiseReranker(settings, observer=observer)
    return CrossEncoderReranker(settings)
