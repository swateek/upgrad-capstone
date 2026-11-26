"""One ablation table from the official runs (CLAUDE.md "Next" step 7).

    uv run python eval/ablation.py      # -> results/ablation.csv, docs/ABLATION.md

Every number is read from a run's own files (summary_<mode>.json, <mode>.jsonl) or from
results/week1_strategies.csv (the Day 4 prompting baselines); nothing is re-scored or typed in.
Arms with several runs (the LLM planner) give the mean and the range over runs; latency (p50,
p95) pools every question of every run of the arm.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs"
WEEK1 = ROOT / "results" / "week1_strategies.csv"
OUT_CSV = ROOT / "results" / "ablation.csv"
OUT_MD = ROOT / "docs" / "ABLATION.md"

SETS = {
    "eval-v2": "eval-v2, gold-v1 (agent v1's held-out set)",
    "eval-v3": "eval-v3 (agent v2's held-out set, SPEC v2)",
    "eval-v2/gold-v2": "eval-v2 re-scored under SPEC v2 (gold-v2): informed the v2 fixes",
}
# (set, arm, agent, mode, run directories)
ARMS = [
    ("eval-v2", "single_rag", "v1", "single_rag", ["official-single-rag"]),
    ("eval-v2", "agent v1, code router", "v1", "router", ["official-router"]),
    (
        "eval-v2",
        "agent v1, LLM planner",
        "v1",
        "planner",
        [f"official-planner-{i}" for i in (1, 2, 3)],
    ),
    ("eval-v3", "single_rag", "v2", "single_rag", ["official-v2-eval3-single_rag"]),
    ("eval-v3", "agent v1, code router", "v1", "router", ["official-v1-eval3-router"]),
    ("eval-v3", "agent v2, code router", "v2", "router", ["official-v2-eval3-router"]),
    (
        "eval-v3",
        "agent v2, LLM planner",
        "v2",
        "planner",
        [f"official-v2-eval3-planner-{i}" for i in (1, 2, 3)],
    ),
    (
        "eval-v2/gold-v2",
        "agent v2, code router",
        "v2",
        "router",
        ["official-v2-gold2-router"],
    ),
    (
        "eval-v2/gold-v2",
        "agent v2, LLM planner",
        "v2",
        "planner",
        ["official-v2-gold2-planner"],
    ),
]
CHECKS = [
    ("outcome_acc", "outcome"),
    ("bottom_line_acc", "bottom line"),
    ("dollar_acc", "dollars"),
    ("clarify_acc", "clarify"),
    ("citation_acc", "citations"),
    ("must_not_acc", "must not"),
    ("state_flag_acc", "state flag"),
]
TYPES = [
    "alcohol_excess_800",
    "alcohol_cbi_2L",
    "exemption_200_all_or_nothing",
    "tobacco_over_limit",
    "cuban_origin",
    "under_21",
    "mixed_basket",
    "whatif",
    "clarify",
    "state_flag",
    "sanctions_escalate",
    "out_of_scope",
    "refuse_evasion",
    "injection_doc",
    "injection_user",
]


def pct(xs: list[float]) -> tuple[float | None, float | None]:
    if not xs:
        return None, None
    s = sorted(xs)
    q = statistics.quantiles(s, n=20, method="inclusive") if len(s) > 1 else [s[0]] * 19
    return round(statistics.median(s), 1), round(q[18], 1)


def arm_row(set_name: str, arm: str, agent: str, mode: str, dirs: list[str]) -> dict:
    sums, secs = [], []
    for d in dirs:
        sums.append(json.loads((RUNS / d / f"summary_{mode}.json").read_text()))
        for line in (RUNS / d / f"{mode}.jsonl").read_text().splitlines():
            secs.append(float(json.loads(line).get("seconds") or 0))
    acc = [s["accuracy"] for s in sums]
    p50, p95 = pct(secs)
    row = {
        "set": set_name,
        "arm": arm,
        "agent": agent,
        "mode": mode,
        "runs": len(dirs),
        "n": sums[0]["n"],
        "accuracy": round(statistics.mean(acc), 3),
        "accuracy_min": min(acc),
        "accuracy_max": max(acc),
        **{
            k: sums[0].get(k)
            if len(sums) == 1
            else round(statistics.mean(s[k] for s in sums if s.get(k) is not None), 3)
            if any(s.get(k) is not None for s in sums)
            else None
            for k, _ in CHECKS
        },
        "dollar_n": sums[0].get("dollar_n"),
        "tokens_per_q": round(statistics.mean(s["tokens_per_q"] for s in sums)),
        "calls_per_q": round(statistics.mean(s["calls_per_q"] for s in sums), 2),
        "latency_p50_s": p50,
        "latency_p95_s": p95,
        "frozen_match": all((s.get("freeze") or {}).get("matches") for s in sums),
        "run_dirs": " ".join(dirs),
    }
    for t in TYPES:
        vals = [
            s["by_type"].get(t) for s in sums if s.get("by_type", {}).get(t) is not None
        ]
        row[f"acc_{t}"] = round(statistics.mean(vals), 2) if vals else None
    return row


def week1_rows() -> list[dict]:
    out = []
    for r in csv.DictReader(WEEK1.open()):

        def f(k: str, r: dict = r) -> float | None:
            return float(r[k]) if r.get(k) not in (None, "") else None

        row = {
            "set": "eval-v2",
            "arm": f"prompting: {r['strategy']}",
            "agent": "baseline",
            "mode": r["strategy"],
            "runs": 1,
            "n": int(r["n"]),
            "accuracy": f("accuracy"),
            "accuracy_min": f("accuracy"),
            "accuracy_max": f("accuracy"),
            **{k: f(k) for k, _ in CHECKS},
            "dollar_n": int(r["dollar_n"]) if r.get("dollar_n") else None,
            "tokens_per_q": round(f("tokens_per_q")),
            "calls_per_q": f("calls_per_q"),
            "latency_p50_s": None,
            "latency_p95_s": None,
            "frozen_match": None,
            "run_dirs": "results/week1_strategies.csv",
        }
        for t in TYPES:
            row[f"acc_{t}"] = f(f"acc_{t}")
        out.append(row)
    return out


def fmt(v, digits: int = 2) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def markdown(rows: list[dict]) -> str:
    md = [
        "# Ablation: every arm on the same questions",
        "",
        (
            "Built by `eval/ablation.py` from the run files (`results/runs/*/summary_*.json`, `*.jsonl`) "
            "and `results/week1_strategies.csv`; see `results/ablation.csv` for every column. Accuracy "
            "is the share of questions where every applicable check passes (eval/score.py). The LLM "
            "planner arms are three runs each (mean, with the range); latency pools all questions of an "
            "arm. Cache off for every official run; all v2 runs matched the v2 freeze (`v2.0.0-rc`)."
        ),
        "",
    ]
    for set_name, title in SETS.items():
        rs = [r for r in rows if r["set"] == set_name]
        md += [
            f"## {title}",
            "",
            "| Arm | Runs | Accuracy | "
            + " | ".join(lbl.capitalize() for _, lbl in CHECKS)
            + " | Tokens/q | Calls/q | p50 s | p95 s |",
            "| --- | --- | --- | "
            + " | ".join("---" for _ in CHECKS)
            + " | --- | --- | --- | --- |",
        ]
        for r in rs:
            acc = fmt(r["accuracy"], 3)
            if r["runs"] > 1:
                acc += f" ({fmt(r['accuracy_min'], 2)}–{fmt(r['accuracy_max'], 2)})"
            md.append(
                f"| {r['arm']} | {r['runs']} | {acc} | "
                + " | ".join(fmt(r[k]) for k, _ in CHECKS)
                + f" | {r['tokens_per_q']:,} | {fmt(r['calls_per_q'])} | {fmt(r['latency_p50_s'], 1)} | {fmt(r['latency_p95_s'], 1)} |"
            )
        md.append("")
        present = [t for t in TYPES if any(r[f"acc_{t}"] is not None for r in rs)]
        md += [
            "Accuracy by question type:",
            "",
            "| Type | " + " | ".join(r["arm"] for r in rs) + " |",
            "| --- | " + " | ".join("---" for _ in rs) + " |",
        ]
        for t in present:
            md.append(f"| {t} | " + " | ".join(fmt(r[f"acc_{t}"]) for r in rs) + " |")
        md.append("")
    md += [
        "## Reading it",
        "",
        (
            "- **Tools beat prompting.** On eval-v2 the four Day 4 prompting strategies reach 0.10–0.18 "
            "and single_rag 0.075; the agent with calculators, rules as data and the verifier reaches 0.75. "
            "Dollars are where prompting fails: no strategy gets more than a few amounts right without the calculators."
        ),
        (
            "- **Planner vs router.** On every set the LLM planner and the code router give the same answers; "
            "the planner costs more tokens and model calls. A valid, reportable result (mentor plan): the "
            "fixed plan is enough for this task."
        ),
        (
            "- **Agent v1 vs v2 on the same new questions (eval-v3):** 0.52 → 0.77. Part of the gain is SPEC v2 "
            "rules that v1 never had (sake as beer, the origin question, ABV timing), part is reading."
        ),
        (
            "- **Generalisation gap.** Agent v2 scores 0.991 on dev-v2 (tuned on) and 1.00 on eval-v2 under "
            "gold-v2 (its failures shaped the fixes), but 0.77 on eval-v3 (never seen). eval-v3 is the honest number."
        ),
        (
            "- **State flag is reported, not scored** (eval/score.py). Every miss in the official runs is the same "
            'gap, in v1 and v2 alike: an arrival airport ("landing at JFK") is not read as the arrival state, so '
            "the New York note is left out (E66, E3-077). A known gap for the report; not fixed on a spent set."
        ),
        "",
    ]
    return "\n".join(md)


def main() -> int:
    rows = week1_rows() + [arm_row(*a) for a in ARMS]
    order = list(SETS)
    rows.sort(key=lambda r: order.index(r["set"]))
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[-1]))
        w.writeheader()
        w.writerows(rows)
    OUT_MD.write_text(markdown(rows))
    print(
        f"wrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} arms) and {OUT_MD.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
