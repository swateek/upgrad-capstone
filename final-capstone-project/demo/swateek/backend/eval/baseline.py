"""Single-agent, single-prompt baseline (Track B deliverable II, brief demo-floor item 6).

    uv run python -m eval.baseline            # both conditions
    uv run python -m eval.baseline --only rag # one condition

Runs the domain's baseline jobs (domain.yaml eval.baseline_jobs) under two conditions:
  closed_book  one call, no retrieved context (shows what the bare model does)
  bm25_top5    one call, top-5 BM25 hits from the by_rule chunks pasted into the prompt
No agent, no tools, no retries beyond the Track B 429/503 policy, no critic.

Writes docs/results/phase1-baseline.json (every answer) and phase1-baseline.md (summary).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import load_domain
from copilot.llm import RateGate, call_with_retry, check_budget, get_provider, make_openai_client
from copilot.llm.budget import count_message_tokens, get_tokenizer
from copilot.retrieval.bm25 import BM25Index

CITE = re.compile(r"\[([a-z0-9_]+:[A-Za-z0-9.()/~\-]+)\]")
REFUSAL = re.compile(
    r"\b(can(?:'|no)t|cannot|unable to|not able to|won't|will not|decline|not (?:in|part of) the "
    r"(?:indexed|context)|not indexed|competent authority)\b",
    re.IGNORECASE,
)
MAX_TOKENS = 400


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text.strip())
    return [p for p in parts if len(p.split()) >= 4]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["closed_book", "bm25_top5"])
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="re-score the saved answers against the current gold (no API calls)",
    )
    args = parser.parse_args()
    if args.rescore:
        return rescore()

    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    provider = get_provider(settings)
    client = make_openai_client(provider, settings.request_timeout_s)
    gate = RateGate(provider.max_concurrency, provider.requests_per_minute)
    tok = get_tokenizer(settings.tokenizer_id)
    chunks_path = settings.data_dir / "processed" / domain.name / "chunks" / "by_rule.jsonl"
    index = BM25Index.from_jsonl(chunks_path)
    known = {c["citation"] for c in index.chunks}
    template = domain.path(domain.eval.baseline_prompt).read_text(encoding="utf-8")
    with domain.path(domain.eval.queries).open(encoding="utf-8") as fh:
        queries = [json.loads(x) for x in fh if json.loads(x)["job"] in domain.eval.baseline_jobs]

    conditions = [args.only] if args.only else ["closed_book", "bm25_top5"]
    rows: list[dict[str, Any]] = []
    for cond in conditions:
        for q in queries:
            hits = index.search(q["query"], k=5) if cond == "bm25_top5" else []
            context = (
                "Context:\n" + "\n\n".join(h.text for h in hits)
                if hits
                else "Context: none. Answer from your own knowledge of these rules."
            )
            messages = [
                {"role": "system", "content": template.replace("{context}", context)},
                {"role": "user", "content": q["query"]},
            ]
            est = count_message_tokens(tok, messages)
            check_budget(est, MAX_TOKENS, settings.context_window_tokens)
            t0 = time.perf_counter()
            resp = call_with_retry(
                lambda m=messages: client.chat.completions.create(
                    model=provider.model,
                    messages=m,
                    max_tokens=MAX_TOKENS,
                    temperature=0,
                    extra_body=provider.extra_body,
                ),
                provider=provider.name,
                url=f"{provider.base_url}/chat/completions",
                delays=settings.retry_delays_s,
                gate=gate,
            )
            latency = round(time.perf_counter() - t0, 2)
            answer = resp.choices[0].message.content or ""
            cited = CITE.findall(answer)
            retrieved = [h.citation for h in hits]
            gold = q["gold"].get("rule_ids", []) + q["gold"].get("also_accept", [])
            sents = sentences(answer)
            rows.append(
                {
                    "condition": cond,
                    "id": q["id"],
                    "query": q["query"],
                    "must_refuse": q["must_refuse"],
                    "gold_rule_ids": gold,
                    "retrieved": retrieved,
                    "gold_in_top5": bool(set(gold) & set(retrieved)) if gold else None,
                    "answer": answer,
                    "cited": cited,
                    "cites_gold": bool(set(gold) & set(cited)) if gold else None,
                    "cited_not_retrieved": [c for c in cited if c not in retrieved] if hits else [],
                    "cited_unknown_ids": [c for c in cited if c not in known],
                    "sentences": len(sents),
                    "uncited_sentences": sum(1 for s in sents if not CITE.search(s)),
                    "looks_like_refusal": bool(REFUSAL.search(answer)),
                    "finish_reason": resp.choices[0].finish_reason,
                    "prompt_tokens_est": est,
                    "usage": resp.usage.model_dump() if resp.usage else {},
                    "latency_s": latency,
                }
            )
            print(f"{cond:11s} {q['id']}  cites_gold={rows[-1]['cites_gold']}  {latency}s")

    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": provider.name,
        "model": provider.model,
        "thinking": settings.enable_thinking,
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
        "chunker": "by_rule",
        "git_sha": git_sha(),
        "n_queries": len(queries),
    }
    out = PROJECT_ROOT / "docs" / "results" / "phase1-baseline.json"
    out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=2, ensure_ascii=False) + "\n")
    (out.with_suffix(".md")).write_text(summary(meta, rows), encoding="utf-8")
    print(f"wrote {out} and {out.with_suffix('.md')}")
    return 0


def rescore() -> int:
    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    with domain.path(domain.eval.queries).open(encoding="utf-8") as fh:
        gold = {q["id"]: q["gold"] for q in map(json.loads, fh)}
    out = PROJECT_ROOT / "docs" / "results" / "phase1-baseline.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    for r in data["rows"]:
        g = gold[r["id"]].get("rule_ids", []) + gold[r["id"]].get("also_accept", [])
        r["gold_rule_ids"] = g
        r["cites_gold"] = bool(set(g) & set(r["cited"])) if g else None
        r["gold_in_top5"] = bool(set(g) & set(r["retrieved"])) if g else None
    data["meta"]["rescored_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    out.with_suffix(".md").write_text(summary(data["meta"], data["rows"]), encoding="utf-8")
    print(f"rescored {len(data['rows'])} rows -> {out.with_suffix('.md')}")
    return 0


def summary(meta: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Phase 1: single-prompt baseline (policy questions)",
        "",
        (
            f"Generated by `python -m eval.baseline` on {meta['run_at']} · {meta['provider']} "
            f"`{meta['model']}` · thinking {'on' if meta['thinking'] else 'off'} · temperature 0 · "
            f"max_tokens {meta['max_tokens']} · git `{meta['git_sha']}`"
        ),
        "",
        "| Metric | closed_book | bm25_top5 |",
        "|---|---|---|",
    ]

    def stat(cond: str, fn) -> str:
        sub = [r for r in rows if r["condition"] == cond]
        return fn(sub) if sub else "–"

    def frac(sub, key):
        vals = [r[key] for r in sub if r[key] is not None]
        return f"{sum(vals)}/{len(vals)}" if vals else "–"

    metrics = [
        (
            "Cites the gold rule id (factual questions)",
            lambda s: frac([r for r in s if not r["must_refuse"]], "cites_gold"),
        ),
        (
            "Gold rule id in retrieved top-5",
            lambda s: frac([r for r in s if not r["must_refuse"]], "gold_in_top5"),
        ),
        (
            "Answers with at least one uncited factual sentence",
            lambda s: f"{sum(r['uncited_sentences'] > 0 for r in s)}/{len(s)}",
        ),
        (
            "Answers citing an id not in the corpus",
            lambda s: f"{sum(bool(r['cited_unknown_ids']) for r in s)}/{len(s)}",
        ),
        (
            "Answers citing an id that was not retrieved",
            lambda s: f"{sum(bool(r['cited_not_retrieved']) for r in s)}/{len(s)}",
        ),
        (
            "Refusal cases that read as a refusal",
            lambda s: (
                f"{sum(r['looks_like_refusal'] for r in s if r['must_refuse'])}/{sum(r['must_refuse'] for r in s)}"
            ),
        ),
        (
            "Non-refusal cases that read as a refusal",
            lambda s: (
                f"{sum(r['looks_like_refusal'] for r in s if not r['must_refuse'])}/{sum(not r['must_refuse'] for r in s)}"
            ),
        ),
        (
            "Mean prompt tokens (usage)",
            lambda s: str(round(sum(r["usage"].get("prompt_tokens", 0) for r in s) / len(s))),
        ),
        (
            "Mean completion tokens (usage)",
            lambda s: str(round(sum(r["usage"].get("completion_tokens", 0) for r in s) / len(s))),
        ),
        ("Mean latency (s)", lambda s: str(round(sum(r["latency_s"] for r in s) / len(s), 2))),
    ]
    for label, fn in metrics:
        lines.append(f"| {label} | {stat('closed_book', fn)} | {stat('bm25_top5', fn)} |")
    lines += [
        "",
        (
            "Automatic checks only; refusal detection is a keyword heuristic and every row is in the "
            "JSON for manual review. The failure note is written by hand in `docs/small-model-log.md`."
        ),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
