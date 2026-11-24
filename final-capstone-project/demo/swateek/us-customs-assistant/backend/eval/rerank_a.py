"""Option A measurement: listwise rerank of the top 10 fused candidates, 120-token passages.

Base variant is the shipped one (window200 | hybrid | prefix on | question + rule name | topic
filter). The baseline is the same retrieval with no reranker, read from the local cache, so it
costs nothing. Only the reranked variant calls the upgrad chat endpoint: one call per claim.

    uv run --group experiment python -m eval.rerank_a --dry-run                 # exact prompt tokens; sends nothing
    uv run --group experiment python -m eval.rerank_a --split dev --who X       # upgrad CHAT (needs the user's OK)
    uv run --group experiment python -m eval.rerank_a --split frozen --who X    # upgrad CHAT (needs the user's OK)
    uv run --group experiment python -m eval.rerank_a --report-only

Parameters are fixed before the run and not tuned on the frozen labels: POOL=10, PASSAGE=120.
Replies are appended to docs/results/retrieval/rerank_a_raw.jsonl, so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import openai

from customs.config import get_settings
from customs.llm.budget import TokenBudgetExceeded, count_message_tokens
from customs.llm.chat import ChatClient
from customs.retrieval.rerank import ListwiseReranker
from eval import retrieval as R

POOL = 10  # candidates the reranker sees (the shipped pool is 20)
PASSAGE = 120  # tokens per passage (the experiment used 300)
OUT = Path(__file__).resolve().parents[2] / "docs" / "results" / "retrieval"
RAW = OUT / "rerank_a_raw.jsonl"
RESULT = OUT / "rerank_a.json"
BASE = R.Variant("window200", "hybrid", "on", "qr", "topic")
RERANKED = R.Variant("window200", "hybrid+listwise", "on", "qr", "topic")


class _Capture:
    """Stands in for the reranker: records what would be sent, sends nothing."""

    model = "capture"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query, documents, top_n):
        self.calls.append((query, list(documents)))
        return [(i, 1.0 / (i + 1)) for i in range(min(top_n, len(documents)))]


def saved() -> dict[str, dict]:
    if not RAW.exists():
        return {}
    return {r["item"]: r for r in map(json.loads, RAW.read_text(encoding="utf-8").splitlines())}


def dry_run(items: list[R.Item], settings) -> None:
    """Exact prompt tokens for each claim, counted locally. Nothing is sent."""
    bench = R.Bench(settings, BASE.chunker, R.make_client(settings), R.query_cache(settings))
    cap = _Capture()
    retr = bench.retriever(BASE.prefix, cap)
    retr.candidates = POOL
    for it in items:
        bench.search(RERANKED, it, retr)
    rr = ListwiseReranker(settings, chat=ChatClient(settings), passage_tokens=PASSAGE)
    tokens = [
        count_message_tokens(rr.tok, rr.messages(q, docs, min(R.DEPTH, len(docs))))
        for q, docs in cap.calls
    ]
    print(f"claims: {len(cap.calls)}; calls: {len(cap.calls)}")
    print(f"prompt tokens per call: mean {statistics.mean(tokens):.0f}, max {max(tokens)}")
    print(
        f"estimated input tokens for the split: {sum(tokens):,} (plus up to 40 reply tokens per call)"
    )


def run(items: list[R.Item], settings, who: str) -> None:
    bench = R.Bench(settings, BASE.chunker, R.make_client(settings), R.query_cache(settings))
    reranker = ListwiseReranker(settings, passage_tokens=PASSAGE)
    retr = bench.retriever(BASE.prefix, reranker)
    retr.candidates = POOL
    seen = saved()
    RAW.parent.mkdir(parents=True, exist_ok=True)
    todo = [it for it in items if it.id not in seen]
    print(
        f"{who}: {len(todo)} listwise calls to send ({len(items) - len(todo)} already saved)",
        flush=True,
    )
    with RAW.open("a", encoding="utf-8") as fh:
        for n, it in enumerate(todo, start=1):
            t0, tok0, fb0 = time.time(), reranker.tokens_used, reranker.fallbacks
            error = None
            try:
                ranking = bench.search(RERANKED, it, retr)
            except (openai.APIStatusError, openai.APIConnectionError) as err:
                error = f"api_error:{getattr(err, 'status_code', 'connection')}"
            except TokenBudgetExceeded as err:
                error = f"budget:{err}"
            if error:  # production keeps the fused order when the reranker fails
                ranking = bench.search(BASE, it, retr)
            rec = {"item": it.id, "split": it.split, "ranking": ranking,
                   "tokens": reranker.tokens_used - tok0, "fallback": reranker.fallbacks > fb0,
                   "error": error, "seconds": round(time.time() - t0, 2)}  # fmt: skip
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 10 == 0 or n == len(todo):
                print(f"listwise {n}/{len(todo)}", flush=True)


def report(items: list[R.Item], settings) -> dict:
    """Hybrid (no reranker) against option A, for each split whose claims are all saved."""
    bench = R.Bench(settings, BASE.chunker, R.make_client(settings), R.query_cache(settings))
    base_retr = bench.retriever(BASE.prefix)
    rows = saved()
    out: dict[str, dict] = {}
    for split in ("dev", "frozen"):
        its = [it for it in items if it.split == split]
        if not its or not all(it.id in rows for it in its):
            continue
        base = {it.id: R.record(bench.search(BASE, it, base_retr), it, bench.chunks) for it in its}
        a: dict[str, dict] = {}
        for it in its:
            r = rows[it.id]
            a[it.id] = R.record(r["ranking"], it, bench.chunks) | {
                "tokens": r["tokens"], "fallback": r["fallback"], "error": r["error"]}  # fmt: skip
        out[split] = {"hybrid": R.metrics(base, its), "option_a": R.metrics(a, its)}
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--split", choices=["dev", "frozen"], default="dev")
    p.add_argument("--who", help="who ran it (quota log); required to call the endpoint")
    p.add_argument("--report-only", action="store_true")
    a = p.parse_args(argv)
    settings = get_settings()
    everything = R.load_items(settings)
    if a.report_only:
        result = report(everything, settings)
    else:
        items = [it for it in everything if it.split == a.split]
        if a.dry_run:
            dry_run(items, settings)
            return
        if not a.who:
            p.error("--who is required: this sends the claims to the upgrad chat endpoint")
        run(items, settings, a.who)
        result = report(everything, settings)
    if result:
        RESULT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        for split, d in result.items():
            for name, m in d.items():
                print(
                    split,
                    name,
                    {k: round(v, 3) if isinstance(v, float) else v for k, v in m.items()},
                )


if __name__ == "__main__":
    main()
