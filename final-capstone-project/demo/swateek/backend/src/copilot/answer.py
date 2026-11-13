"""Single-call grounded answer over retrieved hits (demo floor; the agent harness comes later).

Compensation for the small model (small-model-log #10): sources are shown as short handles
[1]..[n] and the model cites handles only. Code maps handles back to real citations, so the
model never types a citation id and cannot corrupt one. Sentences without a valid handle are
reported as uncited instead of being silently passed through.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from copilot.config import Settings
from copilot.llm import RateGate, call_with_retry, check_budget, get_provider, make_openai_client
from copilot.llm.budget import count_message_tokens, get_tokenizer

HANDLE = re.compile(r"\[(\d{1,2})\]")
HEADER = re.compile(r"^\[[^\]]+\]\n?")  # chunk text starts with "[doc_id:rule_id title]"
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


@dataclass
class Answerer:
    settings: Settings
    prompt_template: str
    max_tokens: int = 500

    def __post_init__(self) -> None:
        self.provider = get_provider(self.settings)
        self.client = make_openai_client(self.provider, self.settings.request_timeout_s)
        self.gate = RateGate(self.provider.max_concurrency, self.provider.requests_per_minute)
        self.tokenizer = get_tokenizer(self.settings.tokenizer_id)

    def answer(self, question: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
        blocks = []
        for i, h in enumerate(hits, start=1):
            body = HEADER.sub("", h["text"], count=1)
            blocks.append(
                f"[{i}] {h['title']} ({h['instrument']}, edition {h['edition_date']})\n{body}"
            )
        system = self.prompt_template.replace("{sources}", "\n\n".join(blocks))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        prompt_tokens = count_message_tokens(self.tokenizer, messages)
        check_budget(prompt_tokens, self.max_tokens, self.settings.context_window_tokens)
        t0 = time.perf_counter()
        resp = call_with_retry(
            lambda: self.client.chat.completions.create(
                model=self.provider.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0,
                extra_body=self.provider.extra_body,
            ),
            provider=self.provider.name,
            url=f"{self.provider.base_url}/chat/completions",
            delays=self.settings.retry_delays_s,
            gate=self.gate,
        )
        raw = resp.choices[0].message.content or ""
        result = resolve_handles(raw, [h["citation"] for h in hits])
        result.update(
            {
                "latency_s": round(time.perf_counter() - t0, 2),
                "usage": resp.usage.model_dump() if resp.usage else {},
                "prompt_tokens_est": prompt_tokens,
                "finish_reason": resp.choices[0].finish_reason,
            }
        )
        return result


def resolve_handles(raw: str, citations: list[str]) -> dict[str, Any]:
    invalid: list[str] = []
    used: list[str] = []

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if 1 <= n <= len(citations):
            c = citations[n - 1]
            if c not in used:
                used.append(c)
            return f"[{c}]"
        invalid.append(m.group(0))
        return ""

    text = HANDLE.sub(repl, raw).strip()
    sentences = [s for s in SENTENCE.split(text) if len(s.split()) >= 4]
    uncited = [s for s in sentences if "[" not in s]
    return {
        "answer": text,
        "citations": used,
        "uncited_sentences": uncited,
        "invalid_handles": invalid,
        "raw_answer": raw,
    }
