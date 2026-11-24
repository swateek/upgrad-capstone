"""Retrieval experiment (Days 5-7): retriever x metadata filter x chunk size -> recall@1/3/5/10.

    uv run python eval/retrieval_experiment.py                         # full grid (needs the embeddings endpoint)
    uv run python eval/retrieval_experiment.py --methods bm25          # keyword only: no endpoint, no reranker
    uv run python eval/retrieval_experiment.py --reranker BAAI/bge-reranker-v2-m3   # compare a second reranker

Queries: eval/retrieval_queries.yaml (60, separate from the eval set). A query counts as a hit at k
when any of the top-k chunks has a citation_id in its gold list. Embeddings go through src/llm.py and
are cached per text, so re-running costs no quota.

Writes results/retrieval_experiment.csv (one row per configuration) and
results/retrieval_per_query.csv (rank of the first gold chunk and the top-3 citation ids, per query).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.score import write_csv
from src.retrieval import FILTERS, METHODS, Retriever, build_chunks

QUERIES = ROOT / "eval" / "retrieval_queries.yaml"
MANIFEST = ROOT / "data" / "rag-corpus" / "corpus" / "MANIFEST.json"
RESULTS = ROOT / "results"
KS = (1, 3, 5, 10)


def load_queries() -> list[dict]:
    qs = yaml.safe_load(QUERIES.read_text())["queries"]
    if MANIFEST.exists():
        have = {d["citation_id"] for d in json.loads(MANIFEST.read_text())["docs"]}
        missing = [(q["id"], g) for q in qs for g in q["gold"] if g not in have]
        if missing:
            raise SystemExit(f"gold ids not in the corpus: {missing}")
    return qs


def first_hit(results: list[dict], gold: set[str]) -> int | None:
    return next((r["rank"] for r in results if r["citation_id"] in gold), None)


def evaluate(retriever: Retriever, queries: list[dict]) -> tuple[dict, list[dict]]:
    per_query, ms = [], []
    for q in queries:
        res = retriever.search(q["query"], k=max(KS))
        ms.append(retriever.last_ms)
        hit = first_hit(res, set(q["gold"]))
        per_query.append(
            {
                "query_id": q["id"],
                "first_hit_rank": hit,
                "top3": " ".join(r["citation_id"] for r in res[:3]),
                "hard_negative_in_top3": any(
                    r.get("authority") == "hard_negative" for r in res[:3]
                ),
                "trap": q.get("trap", ""),
            }
        )
    n = len(queries)
    row = {
        f"recall@{k}": round(
            sum(
                1 for p in per_query if p["first_hit_rank"] and p["first_hit_rank"] <= k
            )
            / n,
            3,
        )
        for k in KS
    }
    row["mrr@10"] = round(
        sum(1 / p["first_hit_rank"] for p in per_query if p["first_hit_rank"]) / n, 3
    )
    row["hard_negative_in_top3"] = round(
        sum(p["hard_negative_in_top3"] for p in per_query) / n, 3
    )
    traps = [p for p in per_query if p["trap"]]
    row["trap_queries_hit@3"] = (
        f"{sum(1 for p in traps if p['first_hit_rank'] and p['first_hit_rank'] <= 3)}/{len(traps)}"
        if traps
        else ""
    )
    row["ms_per_query"] = round(sum(ms) / n, 1)
    return row, per_query


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--chunkings",
        nargs="*",
        type=int,
        default=[200, 350, 450],
        help="max tokens per chunk (the embedding model reads at most 512)",
    )
    ap.add_argument("--methods", nargs="*", default=list(METHODS), choices=METHODS)
    ap.add_argument("--filters", nargs="*", default=list(FILTERS), choices=FILTERS)
    ap.add_argument("--reranker", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    ap.add_argument(
        "--out", default="retrieval_experiment", help="CSV name stem in results/"
    )
    args = ap.parse_args()

    queries = load_queries()
    embed = reranker = None
    if any(m != "bm25" for m in args.methods):
        from src.llm import LLM

        llm = LLM.from_env(run_name="retrieval_experiment")
        embed = lambda texts: llm.embed(texts, stage="retrieval_index")
        print(
            f"embeddings: {llm.embed_model} (cache {'on' if llm.cache_enabled else 'OFF'})"
        )
    if "hybrid_rerank" in args.methods:
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(args.reranker)
        print(f"reranker: {args.reranker}")

    rows, per_query_rows = [], []
    for size in args.chunkings:
        t0 = time.perf_counter()
        chunks = build_chunks(size)
        base = None
        print(f"\nchunk size {size}: {len(chunks)} chunks")
        for flt in args.filters:
            for method in args.methods:
                r = Retriever(
                    chunks, method=method, filter=flt, embed=embed, reranker=reranker
                )
                if base is not None:
                    r.share_indexes(base)
                if method != "bm25":
                    r.dense_matrix()
                r.bm25_index()
                base = r
                row, pq = evaluate(r, queries)
                label = {
                    "chunk_tokens": size,
                    "n_chunks": len(chunks),
                    "method": method,
                    "filter": flt,
                    "reranker": args.reranker if method == "hybrid_rerank" else "",
                }
                rows.append({**label, **row})
                per_query_rows += [{**label, **p} for p in pq]
                print(
                    f"  {method:14} {flt:18} R@1 {row['recall@1']:.2f}  R@3 {row['recall@3']:.2f}  "
                    f"R@5 {row['recall@5']:.2f}  R@10 {row['recall@10']:.2f}  MRR {row['mrr@10']:.2f}  "
                    f"hardneg@3 {row['hard_negative_in_top3']:.2f}  traps {row['trap_queries_hit@3']}"
                )
        print(f"  ({time.perf_counter() - t0:.0f} s)")
    write_csv(RESULTS / f"{args.out}.csv", rows)
    write_csv(
        RESULTS / f"{args.out.replace('experiment', 'per_query')}.csv", per_query_rows
    )
    print(f"\nwrote results/{args.out}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
