"""Prompt-strategy comparison on the policy questions (Track B deliverable II).

    uv run python -m eval.prompts                       # all strategies
    uv run python -m eval.prompts --only plain cot

Every strategy gets the same retrieval (hybrid + rerank, top-5) so only the prompting differs:
  plain              one call, numbered sources, cite [n]            (the Phase 2 answer route)
  structured         JSON {refuse, sentences[{text, sources}]} + few-shot, prompted only
  structured_strict  same, with response_format json_schema (constrained decoding)
  cot                Qwen3 thinking on (reasoning kept out of the answer), cite [n]
  decompose          call 1 plans <=3 rule lookups, retrieve per lookup, call 2 answers
Structured outputs are validated with Pydantic; a failure is sent back once for a retry.
Writes docs/results/phase3-prompts.json and .md.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from copilot.answer import resolve_handles
from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import load_domain
from copilot.llm import RateGate, call_with_retry, check_budget, get_provider, make_openai_client
from copilot.llm.budget import count_message_tokens, get_tokenizer
from copilot.tools.registry import Toolbox

HEADER = re.compile(r"^\[[^\]]+\]\n?")
REFUSAL = re.compile(
    r"\b(can(?:'|no)t|cannot|unable to|not able to|won't|will not|decline|not indexed|"
    r"competent authority|not among the sources|not in the (?:indexed|provided))\b",
    re.IGNORECASE,
)
STRATEGIES = ("plain", "structured", "structured_strict", "cot", "decompose")


class Sentence(BaseModel):
    text: str = Field(min_length=1)
    sources: list[int]


class StructuredAnswer(BaseModel):
    refuse: bool
    refusal_reason: str | None = None
    sentences: list[Sentence] = Field(min_length=1, max_length=6)


class Lookups(BaseModel):
    lookups: list[str] = Field(min_length=1, max_length=3)


class Runner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.domain = load_domain(self.settings.domain_dir)
        self.toolbox = Toolbox(self.settings, self.domain)
        self.provider = get_provider(self.settings)
        self.client = make_openai_client(self.provider, self.settings.request_timeout_s)
        self.gate = RateGate(self.provider.max_concurrency, self.provider.requests_per_minute)
        self.tok = get_tokenizer(self.settings.tokenizer_id)
        p = self.domain.path
        self.prompts = {
            "answer": p("prompts/answer.md").read_text(encoding="utf-8"),
            "structured": p("prompts/structured.md").read_text(encoding="utf-8"),
            "decompose": p("prompts/decompose.md").read_text(encoding="utf-8"),
        }
        self.examples = self._examples()

    def _examples(self) -> str:
        """Few-shot examples come from dev.jsonl only (never from the frozen eval set)."""
        out = []
        with self.domain.path(self.domain.eval.dev).open(encoding="utf-8") as fh:
            for d in map(json.loads, fh):
                if d["job"] != "policy":
                    continue
                g = d["gold"]
                if d["must_refuse"]:
                    ans = {
                        "refuse": True,
                        "refusal_reason": g["answer"],
                        "sentences": [{"text": g["answer"], "sources": []}],
                    }
                else:
                    text = re.sub(r"\s*\[[^\]]+\]", "", g["answer"]).strip()
                    ans = {
                        "refuse": False,
                        "refusal_reason": None,
                        "sentences": [{"text": text, "sources": [1]}],
                    }
                out.append(f"Question: {d['query']}\nReply: {json.dumps(ans)}")
                if len(out) == 3:
                    break
        return "\n\n".join(out)

    # --- plumbing ------------------------------------------------------------------------------
    def chat(self, messages, max_tokens=600, extra=None, **kw) -> tuple[Any, float]:
        est = count_message_tokens(self.tok, messages)
        check_budget(est, max_tokens, self.settings.context_window_tokens)
        body = {**self.provider.extra_body, **(extra or {})}
        t0 = time.perf_counter()
        resp = call_with_retry(
            lambda: self.client.chat.completions.create(
                model=self.provider.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0,
                extra_body=body,
                **kw,
            ),
            provider=self.provider.name,
            url=f"{self.provider.base_url}/chat/completions",
            delays=self.settings.retry_delays_s,
            gate=self.gate,
        )
        return resp, time.perf_counter() - t0

    def hits(self, query: str, k: int = 5) -> list[dict]:
        return self.toolbox.search_docs(query)["hits"][:k]

    @staticmethod
    def sources_block(hits: list[dict]) -> str:
        return "\n\n".join(
            f"[{i}] {h['title']} ({h['instrument']}, edition {h['edition_date']})\n"
            + HEADER.sub("", h["text"], count=1)
            for i, h in enumerate(hits, start=1)
        )

    # --- strategies ----------------------------------------------------------------------------
    def plain(self, q: str, hits, cot: bool = False) -> dict:
        system = self.prompts["answer"].replace("{sources}", self.sources_block(hits))
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": q}]
        extra = {"enable_thinking": True, "thinking_budget": 512} if cot else None
        resp, secs = self.chat(msgs, max_tokens=1024 if cot else 600, extra=extra)
        msg = resp.choices[0].message
        out = resolve_handles(msg.content or "", [h["citation"] for h in hits])
        out.update(
            calls=1,
            latency_s=secs,
            usage=[resp.usage.model_dump()],
            finish_reason=resp.choices[0].finish_reason,
            refused=bool(REFUSAL.search(out["answer"])),
        )
        if cot:
            reasoning = getattr(msg, "reasoning_content", None) or ""
            out["reasoning_chars"] = len(reasoning)
            out["reasoning_leaked"] = "<think>" in (msg.content or "")
        return out

    def structured(self, q: str, hits, strict: bool) -> dict:
        system = (
            self.prompts["structured"]
            .replace("{examples}", self.examples)
            .replace("{sources}", self.sources_block(hits))
        )
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": q}]
        kw = {}
        if strict:
            kw["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "strict": True,
                    "schema": StructuredAnswer.model_json_schema(),
                },
            }
        usage, secs_total, attempts, first_error = [], 0.0, 0, None
        parsed = None
        for attempt in range(2):
            resp, secs = self.chat(msgs, **kw)
            attempts += 1
            secs_total += secs
            usage.append(resp.usage.model_dump())
            raw = resp.choices[0].message.content or ""
            try:
                parsed = StructuredAnswer.model_validate_json(_strip_fences(raw))
                break
            except ValidationError as err:
                msg = str(err).splitlines()[0]
                first_error = first_error or msg
                if attempt == 0:  # one retry with the validation error fed back
                    msgs += [
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": f"Your reply failed validation: {msg}. "
                            "Reply again with valid JSON only, in the required shape.",
                        },
                    ]
        out = {
            "calls": attempts,
            "latency_s": secs_total,
            "usage": usage,
            "schema_valid_first_try": attempts == 1 and parsed is not None,
            "schema_valid_after_retry": parsed is not None,
            "first_error": first_error,
        }
        if parsed is None:
            out.update(
                answer="", citations=[], uncited_sentences=[], invalid_handles=[], refused=False
            )
            return out
        text = " ".join(
            s.text.strip() + "".join(f"[{n}]" for n in s.sources) for s in parsed.sentences
        )
        out.update(resolve_handles(text, [h["citation"] for h in hits]))
        out["refused"] = parsed.refuse
        out["sources_in_text"] = any(re.search(r"\[\d+\]", s.text) for s in parsed.sentences)
        return out

    def decompose(self, q: str) -> dict:
        msgs = [
            {"role": "system", "content": self.prompts["decompose"]},
            {"role": "user", "content": q},
        ]
        resp, secs1 = self.chat(msgs, max_tokens=200, response_format={"type": "json_object"})
        try:
            lookups = Lookups.model_validate_json(
                _strip_fences(resp.choices[0].message.content or "")
            ).lookups
            plan_ok = True
        except ValidationError:
            lookups, plan_ok = [q], False
        seen, hits = set(), []
        for lk in lookups:
            for h in self.hits(lk, k=3):
                if h["citation"] not in seen and len(hits) < 5:
                    seen.add(h["citation"])
                    hits.append(h)
        out = self.plain(q, hits)
        out.update(
            calls=out["calls"] + 1 + len(lookups),
            latency_s=out["latency_s"] + secs1,
            usage=[resp.usage.model_dump(), *out["usage"]],
            lookups=lookups,
            plan_valid=plan_ok,
            retrieved=[h["citation"] for h in hits],
        )
        return out


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", choices=STRATEGIES)
    args = parser.parse_args()
    r = Runner()
    with r.domain.path(r.domain.eval.queries).open(encoding="utf-8") as fh:
        queries = [q for q in map(json.loads, fh) if q["job"] in r.domain.eval.baseline_jobs]
    strategies = args.only or list(STRATEGIES)
    rows = []
    for q in queries:
        hits = r.hits(q["query"])
        gold = set(q["gold"].get("rule_ids", []) + q["gold"].get("also_accept", []))
        for s in strategies:
            if s == "plain":
                res = r.plain(q["query"], hits)
            elif s == "cot":
                res = r.plain(q["query"], hits, cot=True)
            elif s == "decompose":
                res = r.decompose(q["query"])
            else:
                res = r.structured(q["query"], hits, strict=s == "structured_strict")
            res.update(
                strategy=s,
                id=q["id"],
                must_refuse=q["must_refuse"],
                retrieved_has_gold=bool(gold & {h["citation"] for h in hits}) if gold else None,
                cites_gold=bool(gold & set(res["citations"])) if gold else None,
                refusal_correct=res["refused"] == q["must_refuse"],
                tokens=sum(u.get("total_tokens", 0) for u in res["usage"]),
            )
            rows.append(res)
            print(
                f"{q['id']} {s:17s} cites_gold={res['cites_gold']} refused={res['refused']} "
                f"{res['latency_s']:.1f}s"
            )
    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": r.provider.model,
        "provider": r.provider.name,
        "chunker": r.settings.chunker,
        "reranker": r.domain.retrieval.reranker_model,
        "queries": len(queries),
    }
    out = PROJECT_ROOT / "docs" / "results" / "phase3-prompts"
    out.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out.with_suffix(".md").write_text(summary(meta, rows, strategies), encoding="utf-8")
    print(out.with_suffix(".md").read_text())
    return 0


def summary(meta, rows, strategies) -> str:
    def for_s(s):
        return [x for x in rows if x["strategy"] == s]

    def frac(xs, key):
        vals = [x[key] for x in xs if x.get(key) is not None]
        return f"{sum(bool(v) for v in vals)}/{len(vals)}" if vals else "–"

    metrics = [
        (
            "Cites an acceptable gold source (factual)",
            lambda xs: frac([x for x in xs if not x["must_refuse"]], "cites_gold"),
        ),
        ("Refusal handled correctly (all 25)", lambda xs: frac(xs, "refusal_correct")),
        (
            "Answers with an uncited sentence",
            lambda xs: f"{sum(bool(x['uncited_sentences']) for x in xs)}/{len(xs)}",
        ),
        (
            "Answers with an invalid source handle",
            lambda xs: f"{sum(bool(x['invalid_handles']) for x in xs)}/{len(xs)}",
        ),
        ("Schema-valid first try", lambda xs: frac(xs, "schema_valid_first_try")),
        ("Schema-valid after one retry", lambda xs: frac(xs, "schema_valid_after_retry")),
        ("Mean model calls", lambda xs: f"{sum(x['calls'] for x in xs) / len(xs):.1f}"),
        ("Mean tokens per question", lambda xs: f"{round(sum(x['tokens'] for x in xs) / len(xs))}"),
        ("Mean latency (s)", lambda xs: f"{sum(x['latency_s'] for x in xs) / len(xs):.1f}"),
    ]
    lines = [
        "# Phase 3: prompt-strategy comparison (policy questions)",
        "",
        (
            f"{meta['run_at']} · {meta['provider']} `{meta['model']}` · temperature 0 · retrieval "
            f"{meta['chunker']} + hybrid + `{meta['reranker']}` top-5 (same sources for every strategy "
            "except decompose, which retrieves per planned lookup)"
        ),
        "",
        "| Metric | " + " | ".join(strategies) + " |",
        "|---|" + "---|" * len(strategies),
    ]
    for label, fn in metrics:
        lines.append(f"| {label} | " + " | ".join(fn(for_s(s)) for s in strategies) + " |")
    lines += [
        "",
        (
            "Auto metrics only. Where each strategy breaks is written up by hand in "
            "`docs/small-model-log.md`."
        ),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
