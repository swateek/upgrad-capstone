"""Retrieval recall next to end-to-end accuracy (mentor plan, Day 11).

    uv run python eval/recall_vs_accuracy.py   # -> results/recall_vs_accuracy.csv, docs/RECALL_VS_ACCURACY.md

Two views. (1) The Day 5-7 experiment (results/retrieval_experiment*.csv): recall@k of the chosen
retriever on the 60 retrieval queries, search alone. (2) The official runs: for every question
whose gold cites regulations and that reached search, did the 5 clauses given to the writer
contain every gold citation (full recall), and was the answer right? Read from each record's
`retrieved_ids`, the gold set and scores_<mode>.csv.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs"
OUT_CSV = ROOT / "results" / "recall_vs_accuracy.csv"
OUT_MD = ROOT / "docs" / "RECALL_VS_ACCURACY.md"
CHOSEN = ("350", "hybrid_rerank", "no_hard_negatives", "BAAI/bge-reranker-v2-m3")
RUNS_USED = [
    (
        "eval-v3",
        "agent v2, code router",
        "official-v2-eval3-router",
        "router",
        "eval_set_v3.jsonl",
    ),
    (
        "eval-v3",
        "agent v1, code router",
        "official-v1-eval3-router",
        "router",
        "eval_set_v3.jsonl",
    ),
    ("eval-v2", "agent v1, code router", "official-router", "router", "eval_set.jsonl"),
    (
        "eval-v2/gold-v2",
        "agent v2, code router",
        "official-v2-gold2-router",
        "router",
        "eval_set_gold_v2.jsonl",
    ),
]


def chosen_row() -> dict | None:
    for f in ("retrieval_experiment_bge.csv", "retrieval_experiment.csv"):
        p = ROOT / "results" / f
        if not p.exists():
            continue
        for r in csv.DictReader(p.open()):
            if (r["chunk_tokens"], r["method"], r["filter"], r["reranker"]) == CHOSEN:
                return r
    return None


def run_rows(set_name, arm, d, mode, gold_file) -> tuple[dict, list[dict]]:
    gold = {
        r["id"]: r
        for r in map(json.loads, (ROOT / "eval" / gold_file).read_text().splitlines())
    }
    recs = {
        r["id"]: r
        for r in map(json.loads, (RUNS / d / f"{mode}.jsonl").read_text().splitlines())
    }
    scores = {
        r["id"]: r for r in csv.DictReader((RUNS / d / f"scores_{mode}.csv").open())
    }
    items = []
    for i, g in gold.items():
        cites = set(g["gold"].get("citations") or [])
        got = set(recs[i].get("retrieved_ids") or [])
        if not cites or not got:
            continue  # no gold citation, or the agent never reached search (clarify, refusal)
        hit = cites & got
        items.append(
            {
                "set": set_name,
                "arm": arm,
                "id": i,
                "type": g["type"],
                "gold_citations": len(cites),
                "retrieved_gold": len(hit),
                "full_recall": hit == cites,
                "citation_check": scores[i]["citations"] == "True",
                "correct": scores[i]["correct"] == "True",
            }
        )
    full = [x for x in items if x["full_recall"]]
    part = [x for x in items if not x["full_recall"]]

    def acc(xs):
        return round(sum(x["correct"] for x in xs) / len(xs), 3) if xs else None

    summary = {
        "set": set_name,
        "arm": arm,
        "run": d,
        "questions_searched": len(items),
        "citation_recall": round(
            sum(x["retrieved_gold"] for x in items)
            / sum(x["gold_citations"] for x in items),
            3,
        ),
        "full_recall_rate": round(len(full) / len(items), 3),
        "accuracy_if_full_recall": acc(full),
        "accuracy_if_not": acc(part),
        "n_not_full": len(part),
        "wrong_with_full_recall": sum(1 for x in full if not x["correct"]),
        "citation_check_pass": round(
            sum(x["citation_check"] for x in items) / len(items), 3
        ),
    }
    return summary, items


def main() -> int:
    summaries, all_items = [], []
    for spec in RUNS_USED:
        s, items = run_rows(*spec)
        summaries.append(s)
        all_items += items
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0]))
        w.writeheader()
        w.writerows(summaries)
    c = chosen_row()
    md = [
        "# Retrieval recall next to end-to-end accuracy",
        "",
        "Built by `eval/recall_vs_accuracy.py`.",
        "",
        "## Search alone (Day 5–7 experiment, 60 retrieval queries)",
        "",
    ]
    if c:
        md += [
            "Chosen retriever (docs/RETRIEVAL.md): hybrid BM25 + dense (RRF k=60), `BAAI/bge-reranker-v2-m3` on the top 30, hard negatives filtered, 350-token chunks.",
            "",
            "| recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 |",
            "| --- | --- | --- | --- | --- |",
            f"| {c['recall@1']} | {c['recall@3']} | {c['recall@5']} | {c['recall@10']} | {c['mrr@10']} |",
            "",
        ]
    md += [
        "## In the official runs",
        "",
        (
            "Questions whose gold cites regulations and that reached search. The agent fetches each "
            "applied rule's citation by id first (docs/RETRIEVAL.md), then fills the 5-clause budget by "
            "search, so this is the recall of the clauses the writer actually saw. Citation recall: gold "
            "citations retrieved / all gold citations. Full recall: every gold citation retrieved."
        ),
        "",
        "| Set | Arm | Questions | Citation recall | Full recall | Accuracy if full | Accuracy if not (n) | Wrong despite full recall | Citation check |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        md.append(
            f"| {s['set']} | {s['arm']} | {s['questions_searched']} | {s['citation_recall']:.3f} | {s['full_recall_rate']:.3f} | "
            f"{s['accuracy_if_full_recall'] if s['accuracy_if_full_recall'] is not None else '–'} | "
            f"{s['accuracy_if_not'] if s['accuracy_if_not'] is not None else '–'} ({s['n_not_full']}) | "
            f"{s['wrong_with_full_recall']} | {s['citation_check_pass']:.3f} |"
        )
    v2 = summaries[0]
    md += [
        "",
        "## Reading it",
        "",
        (
            f"- On eval-v3, agent v2 had every gold citation in front of the writer on {v2['full_recall_rate']:.0%} of the "
            f"questions that reached search; {v2['wrong_with_full_recall']} of those {'was' if v2['wrong_with_full_recall'] == 1 else 'were'} still wrong (E3-019 is the eval-v3 gold error). Retrieval is not the "
            "bottleneck: the wrong answers start earlier (reading the question, docs/METRICS.md and the failure labels)."
        ),
        (
            '- "Accuracy if not" is 0 by construction: the citation check needs every gold citation. On eval-v3 '
            "agent v2's 4 questions without full recall (E3-022, E3-034, E3-043, E3-044) all began with a misread "
            "fact (failure labels: EXTRACT_WRONG): the agent applied a different rule, so a different source was "
            "fetched. Search itself missed no needed clause in that run."
        ),
        "- Search alone finds the right clause in the top 5 for 95% of the retrieval queries; fetching each applied rule's citation by id makes the clauses the writer sees close to complete.",
        "- Questions that end in a clarifying question or a refusal never reach search, so they are not in this table.",
        "",
    ]
    OUT_MD.write_text("\n".join(md))
    print(f"wrote {OUT_CSV.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")
    for s in summaries:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
