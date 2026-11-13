"""Cross-encoder reranking through SiliconFlow's /v1/rerank.

On api.siliconflow.com only Qwen3-Reranker-0.6B and -8B exist (bge-reranker-v2-m3 is .cn only;
checked 13 Nov 2026). Qwen3-Reranker takes an optional task instruction.

Hosted instead of a local CPU model to keep PyTorch out of the image (plan §1.1). Only the
fused top-20 is sent; the 8B chat model never reranks.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import openai

from copilot.config import Settings
from copilot.llm.retry import RateGate, call_with_retry


class RerankError(RuntimeError):
    pass


class Reranker:
    def __init__(self, settings: Settings, model: str, instruction: str | None = None) -> None:
        if settings.siliconflow_api_key is None:
            raise RuntimeError("SILICONFLOW_API_KEY is needed for reranking")
        self.model = model
        self.instruction = instruction if model.startswith("Qwen/Qwen3-Reranker") else None
        self.settings = settings
        self.url = f"{settings.siliconflow_base_url}/rerank"
        self.http = httpx.Client(
            timeout=settings.request_timeout_s,
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key.get_secret_value()}"},
        )
        self.gate = RateGate(settings.max_concurrency, settings.requests_per_minute)
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
            provider="siliconflow",
            url=self.url,
            delays=self.settings.retry_delays_s,
            gate=self.gate,
        )
        tokens = (data.get("meta") or {}).get("tokens") or {}
        self.tokens_used += int(tokens.get("input_tokens", 0) or 0)
        results = data.get("results")
        if not isinstance(results, list):
            raise RerankError(f"unexpected rerank response: {str(data)[:200]}")
        return [(int(r["index"]), float(r["relevance_score"])) for r in results]
