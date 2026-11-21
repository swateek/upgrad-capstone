"""Retrieval recall@k, measured separately from answer quality (Track B requirement).

    uv run python -m eval.retrieval                    # active chunker, all modes
    uv run python -m eval.retrieval --chunker fixed_512

Labelled set = factual policy questions of the frozen eval set (gold rule ids + also_accept)
plus the retrieval-only labels. A query counts as a hit at k if any acceptable citation is in
the top k. Writes docs/results/<provider>/retrieval-<chunker>--<reranker>.md and .json.

Embeddings and reranker are the active provider's: on upgrad, Qwen3-8B on the course chat
endpoint ranks the candidates (one chat call per question); with UPGRAD_RERANKER=none the
hybrid_rerank row is skipped. --reranker picks another SiliconFlow cross-encoder.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime

from copilot.config import get_settings
from copilot.domains.loader import load_domain
from copilot.ingest.index import chunks_path, file_hash
from copilot.llm.providers import get_embedding, get_reranker, siliconflow_reranker
from copilot.retrieval.bm25 import BM25Index
from copilot.retrieval.dense import DenseStore, collection_name, make_client
from copilot.retrieval.embed import Embedder
from copilot.retrieval.hybrid import HybridRetriever
from copilot.retrieval.rerank import make_reranker

KS = (1, 5, 10)
MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")


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
    parser.add_argument("--reranker", help="another SiliconFlow reranker (PROVIDER=siliconflow)")
    args = parser.parse_args()
    settings = get_settings()
    domain = load_domain(settings.domain_dir)
    chunker = args.chunker or settings.chunker
    path = chunks_path(settings.data_dir, domain.name, chunker)
    emb = get_embedding(settings)
    emb_model = emb.model
    store = DenseStore(
        make_client(settings), collection_name(domain.name, chunker, emb.collection_suffix)
    )
    store.check(emb_model, file_hash(path))
    embedder = Embedder(settings, query_task=domain.retrieval.query_instruction)
    cache: dict[str, list[float]] = {}

    def embed(q: str) -> list[float]:
        if q not in cache:
            cache[q] = embedder.embed_query(q)
        return cache[q]

    cfg = get_reranker(settings)
    if args.reranker:
        if settings.provider != "siliconflow":
            raise SystemExit(
                "--reranker picks a SiliconFlow model; use it with PROVIDER=siliconflow"
            )
        cfg = siliconflow_reranker(settings, args.reranker)
    reranker = make_reranker(settings, cfg, instruction=domain.retrieval.query_instruction)
    rerank_model = reranker.model if reranker else None
    modes = MODES if reranker else tuple(m for m in MODES if m != "hybrid_rerank")
    retriever = HybridRetriever(BM25Index.from_jsonl(path), store, embed, reranker=reranker)
    queries = labelled(domain)
    rows = []
    for q in queries:
        row = {"id": q["id"], "gold": q["gold"]}
        for mode in modes:
            hits = retriever.search(q["query"], k=max(KS), mode=mode)
            # re-cut chunks can span several rules: a hit if any overlapped rule is gold
            covered = [retriever.by_id[h.chunk_id].get("citations", [h.citation]) for h in hits]
            first = next(
                (i + 1 for i, cits in enumerate(covered) if set(cits) & set(q["gold"])), None
            )
            row[mode] = {"first_hit_rank": first, "top": [h.citation for h in hits[:5]]}
        rows.append(row)

    def recall(mode: str, k: int) -> float:
        hits = sum(1 for r in rows if r[mode]["first_hit_rank"] and r[mode]["first_hit_rank"] <= k)
        return hits / len(rows)

    table = {m: {f"recall@{k}": round(recall(m, k), 3) for k in KS} for m in modes}
    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": settings.provider,
        "chunker": chunker,
        "embedding_model": emb_model,
        "collection": store.collection,
        "queries": len(rows),
        "candidates_per_retriever": retriever.candidates,
        "fusion": "RRF k=60",
        "reranker": rerank_model,
        "rerank_tokens": reranker.tokens_used if reranker else 0,
        "rerank_fallbacks": getattr(reranker, "fallbacks", 0),
    }
    tag = (rerank_model or "no-reranker").split("/")[-1].lower()
    tag = re.sub(r"[^a-z0-9_-]+", "-", tag.replace(".", "_")).strip("-")
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    out = settings.results_dir / f"retrieval-{chunker}--{tag}"
    out.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "recall": table, "rows": rows}, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Retrieval recall: `{chunker}` chunks ({settings.provider})",
        "",
        (
            f"{meta['run_at']} · provider {settings.provider} · {len(rows)} labelled questions · "
            f"{meta['embedding_model']} · BM25 and dense top-{retriever.candidates}, RRF k=60 · "
            f"reranker {rerank_model} on the fused top-{retriever.candidates}"
        ),
        "",
        "| Mode | " + " | ".join(f"recall@{k}" for k in KS) + " |",
        "|---|" + "---|" * len(KS),
    ]
    for m in modes:
        lines.append(f"| {m} | " + " | ".join(f"{table[m][f'recall@{k}']:.2f}" for k in KS) + " |")
    last = modes[-1]
    misses = [r["id"] for r in rows if not r[last]["first_hit_rank"]]
    lines += ["", f"{last} misses at k=10: {', '.join(misses) if misses else 'none'}", ""]
    out.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
