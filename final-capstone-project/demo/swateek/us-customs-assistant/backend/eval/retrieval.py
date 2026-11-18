"""Retrieval experiment (plan step 9, §6; Track B item III): recall@1/3/5/10 per variant.

    uv run --group experiment python -m eval.retrieval --dry-run                 # exact upgrad counts; sends nothing
    uv run --group experiment python -m eval.retrieval --embed-queries --who X   # query vectors (upgrad EMBEDDINGS; needs OK)
    uv run --group experiment python -m eval.retrieval --local                   # every variant that needs no call
    uv run --group experiment python -m eval.retrieval --listwise --who X        # Qwen3-8B listwise (upgrad CHAT; needs OK)
    uv run --group experiment python -m eval.retrieval --report-only

Unit: one (question, gold citation claim) pair. A claim is found at k when one of the top-k chunks
holds one of the claim's acceptable clause ids. Labels are clause ids, so every chunker is scored
the same way. Variants:

    chunker    paragraph | section | window200
    retriever  bm25 | dense | hybrid (RRF k=60 over top-20 each) | hybrid+ce | hybrid+listwise
    prefix     bge query instruction on | off (dense and hybrid only)
    query      q  = the question alone (what single_rag sends)
               qr = the question + the rule's name (what search_regulations sends; retrieval/query.py)
    filter     off | topic (qr only: sources whose topic matches the rule's cites)

Rerankers reorder the hybrid top-20 and keep 10. The cross-encoder (ms-marco-MiniLM-L-6-v2, local)
runs on every hybrid variant. Listwise costs one chat call per claim, so it runs on ONE base
variant: the hybrid variant with the best dev recall@5 (ties: recall@10, then fewer tokens in the
top 5). Choices are made on dev (17 questions, 45 claims) and reported on frozen (69, 220).

Query vectors are cached in data/embeddings/<model>.queries.jsonl (sent once, ever); listwise
replies are appended to docs/results/retrieval/listwise_raw.jsonl, so an interrupted run resumes.
Outputs: docs/results/retrieval_experiment.{json,md}.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

import openai

from customs.config import PROJECT_ROOT, Settings, get_settings
from customs.ingest.build_chunks import CHUNKERS
from customs.ingest.index import EmbeddingCache, append_quota_log, load_chunks, windows
from customs.llm.budget import TokenBudgetExceeded
from customs.llm.endpoints import BGE_QUERY_PREFIX, EMBED_BATCH
from customs.retrieval.bm25 import BM25Index
from customs.retrieval.dense import DenseStore, collection_name, make_client
from customs.retrieval.hybrid import HybridRetriever
from customs.retrieval.query import build_query, rule_key, scope
from customs.tools.tables import load_tables

LABELS = PROJECT_ROOT / "pack" / "eval" / "retrieval_labels.jsonl"
OUT = PROJECT_ROOT / "docs" / "results"
RESULTS = OUT / "retrieval_experiment.json"
REPORT = OUT / "retrieval_experiment.md"
LISTWISE_RAW = OUT / "retrieval" / "listwise_raw.jsonl"
KS = (1, 3, 5, 10)
DEPTH = 10  # rankings kept per variant
NEGATIVE_ROLES = {"hard_negative", "injection_fixture"}
PASSAGE_BUDGET = 1500  # tokens of passages a writer call can take under the ~3k input target (§4.6)
PREFIXES = {"on": BGE_QUERY_PREFIX, "off": ""}


@dataclass(frozen=True)
class Item:
    id: str  # "<row id>#<claim index>"
    row: str
    split: str  # dev | frozen
    claim: str
    key: str  # R1..R12 or a state code
    acceptable: frozenset[str]
    q: str
    qr: str
    scope: frozenset[str]


@dataclass(frozen=True)
class Variant:
    chunker: str
    retriever: str  # bm25 | dense | hybrid | hybrid+ce | hybrid+listwise
    prefix: str  # on | off | -
    query: str  # q | qr
    filter: str  # off | topic

    @property
    def name(self) -> str:
        return f"{self.chunker}|{self.retriever}|{self.prefix}|{self.query}|{self.filter}"

    @classmethod
    def parse(cls, name: str) -> Variant:
        return cls(*name.split("|"))


def source_topics(settings: Settings) -> dict[str, str]:
    chunks, _ = load_chunks(settings, "paragraph")
    return {c["doc_id"]: c["topic"] for c in chunks}


def load_items(settings: Settings | None = None) -> list[Item]:
    settings = settings or get_settings()
    tables, topics = load_tables(), source_topics(settings)
    items = []
    for line in LABELS.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        for i, c in enumerate(row["claims"]):
            key = rule_key(c["claim"])
            items.append(
                Item(
                    id=f"{row['id']}#{i}",
                    row=row["id"],
                    split=row["set"],
                    claim=c["claim"],
                    key=key,
                    acceptable=frozenset(c["acceptable"]),
                    q=row["query"],
                    qr=build_query(row["query"], tables, [key]),
                    scope=frozenset(scope(tables, [key], topics)),
                )
            )
    return items


def variants() -> list[Variant]:
    out = []
    for ch in CHUNKERS:
        for query, flt in (("q", "off"), ("qr", "off"), ("qr", "topic")):
            out.append(Variant(ch, "bm25", "-", query, flt))
            for prefix in PREFIXES:
                for retriever in ("dense", "hybrid", "hybrid+ce"):
                    out.append(Variant(ch, retriever, prefix, query, flt))
    return out


# --- query vectors ------------------------------------------------------------------------------


def query_cache(settings: Settings) -> EmbeddingCache:
    model = settings.embedding_model.replace(".", "-")
    return EmbeddingCache(settings.data_dir / "embeddings" / f"{model}.queries.jsonl")


def query_text(text: str, prefix: str) -> str:
    """Exactly what Embedder.embed_query sends: prefix + text, cut to the first window."""
    return windows(PREFIXES[prefix] + text)[0]


def needed_query_texts(items: list[Item]) -> list[str]:
    texts = dict.fromkeys(t for it in items for t in (it.q, it.qr))
    return [query_text(t, p) for t in texts for p in PREFIXES]


def embed_queries(items: list[Item], who: str, settings: Settings, embedder=None) -> int:
    cache = query_cache(settings)
    todo = cache.missing(needed_query_texts(items))
    if not todo:
        print("query vectors: all cached")
        return 0
    if embedder is None:
        from customs.retrieval.embed import Embedder

        embedder = Embedder(settings)
    r0, t0 = embedder.requests, embedder.tokens_used
    cache.add(todo, embedder.embed_documents(todo))
    sent = embedder.requests - r0
    append_quota_log(
        who, "retrieval experiment: query embeddings", 0, sent, embedder.tokens_used - t0,
        f"{len(todo)} query texts (prefix on + off)",
    )  # fmt: skip
    print(f"embedded {len(todo)} query texts in {sent} requests")
    return sent


# --- retrieval ----------------------------------------------------------------------------------


class Memo:
    """Wraps a reranker so a (query, passage) pair is scored once across variants."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.model = inner.model
        self.scores: dict[tuple[str, str], float] = {}

    def rerank(self, query: str, documents, top_n: int) -> list[tuple[int, float]]:
        todo = [d for d in dict.fromkeys(documents) if (query, d) not in self.scores]
        if todo:
            for i, s in self.inner.rerank(query, todo, len(todo)):
                self.scores[(query, todo[i])] = s
        order = sorted(
            range(len(documents)), key=lambda i: (-self.scores[(query, documents[i])], i)
        )
        return [(i, self.scores[(query, documents[i])]) for i in order[:top_n]]


class Bench:
    """The retrievers of one chunker, with query vectors read from the cache only."""

    def __init__(self, settings: Settings, chunker: str, client, cache: EmbeddingCache) -> None:
        chunks, corpus_hash = load_chunks(settings, chunker)
        self.chunks = {c["chunk_id"]: c for c in chunks}
        self.bm25 = BM25Index(chunks)
        self.dense = DenseStore(client, collection_name(chunker, settings.embedding_model))
        self.dense.check(settings.embedding_model, corpus_hash)
        self.cache = cache

    def retriever(self, prefix: str, reranker=None) -> HybridRetriever:
        def embed(text: str) -> list[float]:
            try:
                return self.cache.get(query_text(text, prefix))
            except KeyError:
                raise RuntimeError("query vector not cached: run --embed-queries first") from None

        return HybridRetriever(self.bm25, self.dense, embed, candidates=20, reranker=reranker)

    def search(self, v: Variant, it: Item, retriever: HybridRetriever) -> list[str]:
        text = it.q if v.query == "q" else it.qr
        flt = set(it.scope) if v.filter == "topic" else None
        mode = {"hybrid+ce": "hybrid_rerank", "hybrid+listwise": "hybrid_rerank"}.get(
            v.retriever, v.retriever
        )
        return [h.chunk_id for h in retriever.search(text, DEPTH, flt, mode=mode)]


def first_hit(ranking: list[str], it: Item, chunks: dict[str, dict]) -> int | None:
    for r, cid in enumerate(ranking, start=1):
        if it.acceptable & set(chunks[cid]["clause_ids"]):
            return r
    return None


def record(ranking: list[str], it: Item, chunks: dict[str, dict]) -> dict:
    top5 = [chunks[c] for c in ranking[:5]]
    hit = first_hit(ranking, it, chunks)
    return {
        "hit": hit,
        "hit_tok": sum(chunks[c]["n_tokens"] for c in ranking[:hit]) if hit else None,
        "tok5": sum(c["n_tokens"] for c in top5),
        "neg5": any(c.get("role") in NEGATIVE_ROLES for c in top5),
    }


def run_local(items: list[Item], settings: Settings) -> dict[str, dict[str, dict]]:
    from customs.retrieval.rerank import CrossEncoderReranker

    cache, client = query_cache(settings), make_client(settings)
    ce = Memo(CrossEncoderReranker(settings))
    out: dict[str, dict[str, dict]] = {}
    for ch in CHUNKERS:
        bench = Bench(settings, ch, client, cache)
        for v in (v for v in variants() if v.chunker == ch):
            t0 = time.time()
            r = bench.retriever(v.prefix, ce if v.retriever == "hybrid+ce" else None)
            out[v.name] = {it.id: record(bench.search(v, it, r), it, bench.chunks) for it in items}
            print(f"{v.name:42s} {time.time() - t0:5.1f}s", flush=True)
    return out


# --- listwise -----------------------------------------------------------------------------------


def choose_base(results: dict[str, dict[str, dict]], items: list[Item]) -> Variant:
    dev = [it for it in items if it.split == "dev"]

    def key(name: str):
        m = metrics(results[name], dev)
        return (m["recall@budget"], m["recall@5"], -m["tok5"])

    names = [n for n in results if Variant.parse(n).retriever == "hybrid"]
    return Variant.parse(max(sorted(names), key=key))


def listwise_done() -> dict[tuple[str, str], dict]:
    if not LISTWISE_RAW.exists():
        return {}
    recs = [json.loads(x) for x in LISTWISE_RAW.read_text(encoding="utf-8").splitlines() if x]
    return {(r["variant"], r["item"]): r for r in recs}


def listwise_todo(base: Variant, items: list[Item], splits: set[str]) -> list[Item]:
    v = Variant(base.chunker, "hybrid+listwise", base.prefix, base.query, base.filter)
    done = listwise_done()
    return [it for it in items if it.split in splits and (v.name, it.id) not in done]


def run_listwise(
    base: Variant,
    items: list[Item],
    splits: set[str],
    settings: Settings,
    reranker=None,
    tracer=None,
    client=None,
) -> tuple[int, int]:
    """One chat call per claim; returns (calls, tokens)."""
    from contextlib import nullcontext

    from customs.llm.chat import ChatClient
    from customs.retrieval.rerank import ListwiseReranker

    v = Variant(base.chunker, "hybrid+listwise", base.prefix, base.query, base.filter)
    todo = listwise_todo(base, items, splits)
    if reranker is None:
        reranker = ListwiseReranker(settings, chat=ChatClient(settings, tracer=tracer))
    bench = Bench(settings, base.chunker, client or make_client(settings), query_cache(settings))
    retr = bench.retriever(base.prefix, reranker)
    LISTWISE_RAW.parent.mkdir(parents=True, exist_ok=True)
    calls = tokens = 0
    with LISTWISE_RAW.open("a", encoding="utf-8") as fh:
        for n, it in enumerate(todo, start=1):
            t0, tok0, fb0 = time.time(), reranker.tokens_used, reranker.fallbacks
            ctx = (
                tracer.run(f"retrieval-{it.id}", it.qr if base.query == "qr" else it.q,
                           ["retrieval-experiment", v.name, it.split, it.key], name="customs-retrieval")
                if tracer else nullcontext()
            )  # fmt: skip
            error = None
            with ctx:
                try:
                    ranking = bench.search(v, it, retr)
                except (openai.APIStatusError, openai.APIConnectionError) as err:
                    error = f"api_error:{getattr(err, 'status_code', 'connection')}"
                except TokenBudgetExceeded as err:
                    error = f"budget:{err}"
            if error:  # production keeps the fused order when the reranker fails
                ranking = bench.search(base, it, retr)
            calls += 1
            tokens += reranker.tokens_used - tok0
            rec = {"variant": v.name, "item": it.id, "split": it.split, "ranking": ranking,
                   "tokens": reranker.tokens_used - tok0, "fallback": reranker.fallbacks > fb0,
                   "error": error, "seconds": round(time.time() - t0, 2)}  # fmt: skip
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 10 == 0 or n == len(todo):
                print(f"listwise {n}/{len(todo)}", flush=True)
    if tracer:
        tracer.flush()
    return calls, tokens


def listwise_results(items: list[Item], settings: Settings) -> dict[str, dict[str, dict]]:
    by_id = {it.id: it for it in items}
    chunk_maps: dict[str, dict] = {}
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for (vname, iid), r in listwise_done().items():
        ch = Variant.parse(vname).chunker
        if ch not in chunk_maps:
            chunk_maps[ch] = {c["chunk_id"]: c for c in load_chunks(settings, ch)[0]}
        if iid in by_id:
            rec = record(r["ranking"], by_id[iid], chunk_maps[ch])
            rec |= {"tokens": r["tokens"], "fallback": r["fallback"], "error": r["error"]}
            out[vname][iid] = rec
    return dict(out)


# --- metrics and report -------------------------------------------------------------------------


def metrics(per_item: dict[str, dict], items: list[Item]) -> dict:
    rows = [(it, per_item[it.id]) for it in items if it.id in per_item]
    if not rows:
        return {}
    n = len(rows)
    m = {
        f"recall@{k}": sum(r["hit"] is not None and r["hit"] <= k for _, r in rows) / n for k in KS
    }
    m["mrr@10"] = sum(1 / r["hit"] for _, r in rows if r["hit"]) / n
    m["recall@budget"] = (
        sum(r["hit_tok"] is not None and r["hit_tok"] <= PASSAGE_BUDGET for _, r in rows) / n
    )
    by_row: dict[str, list[bool]] = defaultdict(list)
    for it, r in rows:
        by_row[it.row].append(r["hit"] is not None and r["hit"] <= 5)
    m["full@5"] = sum(all(v) for v in by_row.values()) / len(by_row)
    m["tok5"] = statistics.mean(r["tok5"] for _, r in rows)
    m["neg5"] = sum(r["neg5"] for _, r in rows) / n
    m["n"] = n
    if "tokens" in rows[0][1]:
        m["llm_tokens"] = statistics.mean(r["tokens"] for _, r in rows)
        m["fallbacks"] = sum(bool(r["fallback"]) for _, r in rows)
        m["errors"] = sum(bool(r["error"]) for _, r in rows)
    return m


def save(local: dict[str, dict[str, dict]]) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"variants": local}, indent=0, sort_keys=True) + "\n")


def load_local() -> dict[str, dict[str, dict]]:
    if not RESULTS.exists():
        raise SystemExit("no local results yet: run --local first")
    return json.loads(RESULTS.read_text())["variants"]


def _row(name: str, m: dict) -> str:
    v = Variant.parse(name)
    cells = [v.chunker, v.retriever, v.prefix, v.query, v.filter]
    cells += [f"{m[f'recall@{k}']:.2f}" for k in KS]
    cells += [f"{m['recall@budget']:.2f}", f"{m['mrr@10']:.2f}", f"{m['full@5']:.2f}"]
    cells += [f"{m['tok5']:.0f}", f"{m['neg5']:.2f}"]
    return "| " + " | ".join(cells) + " |"


HEADER = (
    "| chunker | retriever | prefix | query | filter | R@1 | R@3 | R@5 | R@10 | R@1.5k "
    "| MRR@10 | full@5 | tok@5 | neg@5 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
)


def report(items: list[Item], settings: Settings) -> str:
    local = load_local()
    lw = listwise_results(items, settings)
    allv = {**local, **lw}
    base = choose_base(local, items)
    splits = {s: [it for it in items if it.split == s] for s in ("dev", "frozen")}
    lines = [
        "# Retrieval experiment (plan step 9)",
        "",
        (
            "Generated by `eval/retrieval.py`; do not edit by hand. Decisions: "
            "`retrieval-decisions.md`."
        ),
        "",
        (
            f"Unit: one (question, gold citation claim) pair; dev {len(splits['dev'])} claims "
            f"({len({i.row for i in splits['dev']})} questions), frozen {len(splits['frozen'])} "
            f"({len({i.row for i in splits['frozen']})}). R@k: a top-k chunk holds an acceptable "
            "clause id. R@1.5k: found within the first 1,500 tokens of passages (token-matched, "
            "so large chunks get no free ride). full@5: share of questions with every claim found in the top 5. tok@5: tokens "
            "in the top 5 chunks (context cost). neg@5: share with a hard negative or injection "
            "fixture in the top 5. query q = question only, qr = question + rule name."
        ),
        "",
        f"Listwise base variant (best dev R@1.5k among hybrid variants; ties: R@5): `{base.name}`.",
        "",
        "Rows are sorted by R@1.5k.",
    ]
    for s in ("dev", "frozen"):
        lines += ["", f"## {s.capitalize()} labels", "", HEADER]
        ranked = sorted(allv, key=lambda n: -metrics(allv[n], splits[s]).get("recall@budget", -1))
        lines += [
            _row(n, metrics(allv[n], splits[s])) for n in ranked if metrics(allv[n], splits[s])
        ]
    lines += ["", "## R@1.5k by rule on the base variant (frozen)", ""]
    rerank_names = [base.name] + [
        Variant(base.chunker, r, base.prefix, base.query, base.filter).name
        for r in ("hybrid+ce", "hybrid+listwise")
    ]
    present = [n for n in rerank_names if n in allv]
    lines += ["| rule | claims | " + " | ".join(Variant.parse(n).retriever for n in present) + " |",
              "|---|---|" + "---|" * len(present)]  # fmt: skip
    keys = sorted({it.key for it in splits["frozen"]}, key=lambda k: (k[0] != "R", len(k), k))
    for k in keys:
        sub = [it for it in splits["frozen"] if it.key == k]
        cells = [f"{metrics(allv[n], sub).get('recall@budget', float('nan')):.2f}" for n in present]
        lines.append(f"| {k} | {len(sub)} | " + " | ".join(cells) + " |")
    for n in present:
        m = metrics(allv[n], items)
        if "llm_tokens" in m:
            lines += ["", (f"Listwise: {m['n']} calls, {m['llm_tokens']:.0f} tokens per call on "
                      f"average, {m['fallbacks']} replies without a usable order, {m['errors']} "
                      "API errors (fused order kept).")]  # fmt: skip
    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    return text


# --- CLI ----------------------------------------------------------------------------------------


def counts(items: list[Item], settings: Settings) -> dict:
    todo_q = query_cache(settings).missing(needed_query_texts(items))
    out = {
        "query_texts": len(todo_q),
        "embed_requests": -(-len(todo_q) // EMBED_BATCH),
        "listwise_dev": sum(it.split == "dev" for it in items),
        "listwise_frozen": sum(it.split == "frozen" for it in items),
    }
    if RESULTS.exists():
        base = choose_base(load_local(), items)
        out["listwise_base"] = base.name
        out["listwise_todo"] = {s: len(listwise_todo(base, items, {s})) for s in ("dev", "frozen")}
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true", help="exact upgrad counts; send nothing")
    p.add_argument("--embed-queries", action="store_true", help="calls the upgrad embeddings")
    p.add_argument("--local", action="store_true", help="every variant without an upgrad call")
    p.add_argument("--listwise", action="store_true", help="calls the upgrad chat endpoint")
    p.add_argument("--split", choices=["dev", "frozen", "both"], default="both")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--who", help="who ran it (quota log); required to call an endpoint")
    a = p.parse_args(argv)
    settings = get_settings()
    items = load_items(settings)
    if a.dry_run:
        c = counts(items, settings)
        print(f"claims: dev {c['listwise_dev']}, frozen {c['listwise_frozen']}")
        print(f"query embeddings: {c['query_texts']} texts -> {c['embed_requests']} requests "
              f"of <= {EMBED_BATCH}")  # fmt: skip
        if "listwise_base" in c:
            print(f"listwise base: {c['listwise_base']}; chat calls still to run: "
                  f"{c['listwise_todo']}")  # fmt: skip
        else:
            print(f"listwise: one chat call per claim on one base variant "
                  f"(dev {c['listwise_dev']} + frozen {c['listwise_frozen']}); base chosen after --local")  # fmt: skip
        print("dry run: nothing sent")
        return
    if (a.embed_queries or a.listwise) and not a.who:
        print("FAIL calling an upgrad endpoint needs --who (quota log)", file=sys.stderr)
        sys.exit(1)
    if a.embed_queries:
        embed_queries(items, a.who, settings)
    if a.local:
        save(run_local(items, settings))
    if a.listwise:
        from customs.observability.tracing import Tracer

        base = choose_base(load_local(), items)
        splits = {"dev", "frozen"} if a.split == "both" else {a.split}
        print(
            f"listwise on {base.name}: {sum(len(listwise_todo(base, items, {s})) for s in splits)} calls"
        )
        t0 = time.time()
        calls, tokens = run_listwise(base, items, splits, settings, tracer=Tracer(settings))
        append_quota_log(
            a.who, f"retrieval experiment: listwise rerank ({', '.join(sorted(splits))})",
            calls, 0, tokens, f"base {base.name.replace('|', ' / ')}; run took {round((time.time() - t0) / 60)} min",
        )  # fmt: skip
    if a.local or a.listwise or a.report_only:
        print(report(items, settings))


if __name__ == "__main__":
    main()
