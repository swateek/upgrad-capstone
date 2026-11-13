"""Retrieval recall@k, measured separately from answer quality (Track B requirement).

    uv run python -m eval.retrieval                    # active chunker, all modes
    uv run python -m eval.retrieval --chunker fixed_512

Labelled set = factual policy questions of the frozen eval set (gold rule ids + also_accept)
plus the retrieval-only labels. A query counts as a hit at k if any acceptable citation is in
the top k. Writes docs/results/retrieval-<chunker>.md and .json.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from copilot.config import PROJECT_ROOT, get_settings
from copilot.domains.loader import load_domain
from copilot.ingest.index import chunks_path, file_hash
from copilot.retrieval.bm25 import BM25Index
from copilot.retrieval.dense import DenseStore, collection_name, make_client
from copilot.retrieval.embed import Embedder
from copilot.retrieval.hybrid import HybridRetriever

KS = (1, 5, 10)
MODES = ("bm25", "dense", "hybrid")


def labelled(domain) -> list[dict]:
    out = []
    with domain.path(domain.eval.queries).open(encoding="utf-8") as fh:
        for q in map(json.loads, fh):
            gold = q["gold"].get("rule_ids", []) + q["gold"].get("also_accept", [])
            if gold and not q["must_refuse"]:
                out.append({"id": q["id"], "query": q["query"], "gold": gold})
    with domain.path(domain.eval.retrieval_labels).open(encoding="utf-8") as fh:
        for q in map(json.loads, fh):
            out.append({"id": q["id"], "query": q["query"], "gold": q["gold_rule_ids"]})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunker")
    args = parser.parse_args()
    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    chunker = args.chunker or settings.chunker
    path = chunks_path(settings.data_dir, domain.name, chunker)
    store = DenseStore(make_client(settings), collection_name(domain.name, chunker))
    store.check(domain.retrieval.embedding_model, file_hash(path))
    embedder = Embedder(
        settings, domain.retrieval.embedding_model, query_task=domain.retrieval.query_instruction
    )
    cache: dict[str, list[float]] = {}

    def embed(q: str) -> list[float]:
        if q not in cache:
            cache[q] = embedder.embed_query(q)
        return cache[q]

    retriever = HybridRetriever(BM25Index.from_jsonl(path), store, embed)
    queries = labelled(domain)
    rows = []
    for q in queries:
        row = {"id": q["id"], "gold": q["gold"]}
        for mode in MODES:
            cites = [h.citation for h in retriever.search(q["query"], k=max(KS), mode=mode)]
            first = next((i + 1 for i, c in enumerate(cites) if c in q["gold"]), None)
            row[mode] = {"first_hit_rank": first, "top": cites[:5]}
        rows.append(row)

    def recall(mode: str, k: int) -> float:
        hits = sum(1 for r in rows if r[mode]["first_hit_rank"] and r[mode]["first_hit_rank"] <= k)
        return hits / len(rows)

    table = {m: {f"recall@{k}": round(recall(m, k), 3) for k in KS} for m in MODES}
    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "chunker": chunker,
        "embedding_model": domain.retrieval.embedding_model,
        "queries": len(rows),
        "candidates_per_retriever": retriever.candidates,
        "fusion": "RRF k=60",
        "reranker": None,
    }
    out = PROJECT_ROOT / "docs" / "results" / f"retrieval-{chunker}"
    out.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "recall": table, "rows": rows}, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Retrieval recall: `{chunker}` chunks",
        "",
        (
            f"{meta['run_at']} · {len(rows)} labelled policy questions · "
            f"{meta['embedding_model']} · BM25 and dense top-{retriever.candidates}, RRF k=60 · "
            "no reranker yet"
        ),
        "",
        "| Mode | " + " | ".join(f"recall@{k}" for k in KS) + " |",
        "|---|" + "---|" * len(KS),
    ]
    for m in MODES:
        lines.append(f"| {m} | " + " | ".join(f"{table[m][f'recall@{k}']:.2f}" for k in KS) + " |")
    misses = [r["id"] for r in rows if not r["hybrid"]["first_hit_rank"]]
    lines += ["", f"Hybrid misses at k=10: {', '.join(misses) if misses else 'none'}", ""]
    out.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
