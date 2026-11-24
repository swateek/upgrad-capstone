"""Day 11 metrics tables from the official runs (mentor plan, Day 11).

    uv run python eval/metrics.py                       # -> results/metrics.csv, docs/METRICS.md
    uv run python eval/metrics.py --price-per-mtok 0.10 # also a cost column at that price

Read from each run's files (scores_<mode>.csv, <mode>.jsonl, summary_<mode>.json) and the gold
set; the same arms as eval/ablation.py. Per arm (mean over runs where an arm has several):

- accuracy; dollar accuracy (priced items, within $0.01); citation accuracy;
- clarify precision (asked when gold asks / all asks) and recall (asked / gold asks), and the
  share of gold-clarify items where exactly the right facts were asked;
- completion: the run produced an outcome with no error and inside the budget;
- outcome mix (answered, clarify, refused, escalated), over-escalation (escalated when gold
  answers or asks) and over-refusal (refused when gold does not refuse);
- tool steps, model calls and tokens per question, total tokens; cost only at a stated price
  (the shared endpoint has none); p50/p95 latency.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from eval.ablation import ARMS, RUNS, SETS, pct

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "results" / "metrics.csv"
OUT_MD = ROOT / "docs" / "METRICS.md"
OUTCOMES = ("answered", "clarify", "refused", "escalated")


def _b(v: str) -> bool | None:
    return {"True": True, "False": False}.get(v)


def run_metrics(d: str, mode: str) -> dict:
    scores = list(csv.DictReader((RUNS / d / f"scores_{mode}.csv").open()))
    recs = {
        r["id"]: r
        for r in map(json.loads, (RUNS / d / f"{mode}.jsonl").read_text().splitlines())
    }
    summ = json.loads((RUNS / d / f"summary_{mode}.json").read_text())
    n = len(scores)
    pred = [s["pred_outcome"] for s in scores]
    gold = [s["gold_outcome"] for s in scores]
    asked = [i for i, p in enumerate(pred) if p == "clarify"]
    gold_ask = [i for i, g in enumerate(gold) if g == "clarify"]
    both = [i for i in asked if gold[i] == "clarify"]
    right_facts = [i for i in gold_ask if _b(scores[i]["clarify"])]
    errors = [s for s in scores if s["error"]]
    steps = [recs[s["id"]].get("tool_steps") or 0 for s in scores]
    secs = [float(recs[s["id"]].get("seconds") or 0) for s in scores]
    tokens = [int(s["tokens"] or 0) for s in scores]
    over_esc = sum(
        1
        for p, g in zip(pred, gold, strict=True)
        if p == "escalated" and g in ("answered", "clarify")
    )
    over_ref = sum(
        1 for p, g in zip(pred, gold, strict=True) if p == "refused" and g != "refused"
    )
    return {
        "accuracy": summ["accuracy"],
        "dollar_acc": summ.get("dollar_acc"),
        "dollar_n": summ.get("dollar_n"),
        "citation_acc": summ.get("citation_acc"),
        "clarify_precision": round(len(both) / len(asked), 3) if asked else None,
        "clarify_recall": round(len(both) / len(gold_ask), 3) if gold_ask else None,
        "clarify_right_facts": round(len(right_facts) / len(gold_ask), 3)
        if gold_ask
        else None,
        "clarify_asked": len(asked),
        "clarify_gold": len(gold_ask),
        "completion": round((n - len(errors)) / n, 3),
        **{f"pred_{o}": sum(1 for p in pred if p == o) for o in OUTCOMES},
        "over_escalation": over_esc,
        "over_refusal": over_ref,
        "tool_steps_per_q": round(statistics.mean(steps), 2),
        "calls_per_q": summ["calls_per_q"],
        "tokens_per_q": summ["tokens_per_q"],
        "tokens_total": sum(tokens),
        "_secs": secs,
        "n": n,
    }


def arm_metrics(set_name, arm, agent, mode, dirs, price) -> dict:
    per = [run_metrics(d, mode) for d in dirs]
    secs = [x for p in per for x in p.pop("_secs")]
    row = {"set": set_name, "arm": arm, "agent": agent, "mode": mode, "runs": len(dirs)}
    for k in per[0]:
        vals = [p[k] for p in per if p[k] is not None]
        if not vals:
            row[k] = None
        elif isinstance(vals[0], int) and k not in ("tokens_per_q",):
            row[k] = round(statistics.mean(vals), 1) if len(vals) > 1 else vals[0]
        else:
            row[k] = round(statistics.mean(vals), 3)
    row["latency_p50_s"], row["latency_p95_s"] = pct(secs)
    row["cost_usd_per_100q"] = (
        round(row["tokens_per_q"] * 100 * price / 1e6, 4) if price is not None else None
    )
    row["run_dirs"] = " ".join(dirs)
    return row


def fmt(v, d: int = 2) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    if isinstance(v, int) and v >= 10000:
        return f"{v:,}"
    return str(v)


def markdown(rows: list[dict], price: float | None) -> str:
    md = [
        "# Day 11 metrics",
        "",
        (
            "Built by `eval/metrics.py` from the official runs (`results/runs/*`: scores, records, "
            "summaries); the same arms as `docs/ABLATION.md`, where accuracy by type and each "
            "check are tabled. Planner arms: mean over 3 runs. Clarify precision = asks that gold "
            "also asks / all asks; recall = gold asks that were asked; right facts = gold asks "
            "where exactly the gold facts were asked. Completion = an outcome with no error inside "
            "the budget. Over-escalation = escalated where gold answers or asks; over-refusal = "
            "refused where gold does not refuse."
        ),
        "",
    ]
    for set_name, title in SETS.items():
        rs = [r for r in rows if r["set"] == set_name]
        if not rs:
            continue
        md += [
            f"## {title}",
            "",
            "| Arm | Accuracy | $ accuracy (n) | Citations | Clarify P / R / right facts | Completion | Over-escalation | Over-refusal |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in rs:
            md.append(
                f"| {r['arm']} | {fmt(r['accuracy'], 3)} | {fmt(r['dollar_acc'])} ({fmt(r['dollar_n'])}) | "
                f"{fmt(r['citation_acc'])} | {fmt(r['clarify_precision'])} / {fmt(r['clarify_recall'])} / "
                f"{fmt(r['clarify_right_facts'])} | {fmt(r['completion'])} | {fmt(r['over_escalation'])} | {fmt(r['over_refusal'])} |"
            )
        md += [
            "",
            "| Arm | Answered / clarify / refused / escalated | Tool steps/q | Model calls/q | Tokens/q | Tokens per run | p50 s | p95 s |"
            + (" Cost per 100 q |" if price is not None else ""),
            "| --- | --- | --- | --- | --- | --- | --- | --- |"
            + (" --- |" if price is not None else ""),
        ]
        for r in rs:
            mix = " / ".join(fmt(r[f"pred_{o}"]) for o in OUTCOMES)
            md.append(
                f"| {r['arm']} | {mix} | {fmt(r['tool_steps_per_q'])} | {fmt(r['calls_per_q'])} | "
                f"{r['tokens_per_q']:,.0f} | {r['tokens_total']:,.0f} | {fmt(r['latency_p50_s'], 1)} | {fmt(r['latency_p95_s'], 1)} |"
                + (f" ${r['cost_usd_per_100q']:.4f} |" if price is not None else "")
            )
        md.append("")
    md += [
        "Cost: the shared course endpoint has no price, so cost is reported in tokens; "
        + (
            f"the cost column assumes ${price}/M tokens."
            if price is not None
            else "pass `--price-per-mtok` for a cost at a stated price."
        ),
        "",
    ]
    return "\n".join(md)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-per-mtok", type=float, default=None)
    args = ap.parse_args()
    rows = [arm_metrics(*a, args.price_per_mtok) for a in ARMS]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    OUT_MD.write_text(markdown(rows, args.price_per_mtok))
    print(
        f"wrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} arms) and {OUT_MD.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
