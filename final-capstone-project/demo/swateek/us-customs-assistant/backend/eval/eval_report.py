"""The evaluation report (plan §10.4–10.5): docs/eval-report.md + docs/results/official.json.

    uv run python -m eval.eval_report [--usd-per-m 0.10]          # the official runs
    uv run python -m eval.eval_report --runs dev-08 --out /tmp/x  # any runs (testing)

Per run: turn and scenario accuracy, accuracy per category, dollar and citation accuracy,
extraction accuracy, clarify precision/recall, task completion, tool calls, tokens, cost at a
labelled ASSUMED price, p50/p95 latency, plan-fallback and retrieval-miss-recovered rates.
The three planner runs are reported as mean and range. Every wrong turn gets a fine failure
label, rolled up into the template's four buckets (+ "not built" for the stretch what-if);
docs/results/failures-to-check.md lists them for the hand-check (at least 15); the hand labels
in docs/results/hand-check.yaml replace the automatic ones and the report gives the agreement.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from customs.config import PROJECT_ROOT
from eval import run_agent as ra
from eval.official import RUNS

DOCS = PROJECT_ROOT / "docs"
HAND = DOCS / "results" / "hand-check.yaml"
BUCKETS = {
    "retrieval_miss": "Retrieval miss",
    "extraction_error": "Reasoning error",
    "unit_error": "Reasoning error",
    "rule_selection_error": "Reasoning error",
    "citation_mapping": "Reasoning error",
    "plan_invalid": "Reasoning error",
    "clarify_miss": "Reasoning error",
    "refusal_miss": "Reasoning error",
    "malformed_output": "Reasoning error",
    "budget_exceeded": "Reasoning error",
    "tool_arg_error": "Tool-call error",
    "wrong_tool": "Tool-call error",
    "repeated_call": "Tool-call error",
    "tool_failure": "Tool-call error",
    "invented_figure": "Hallucination",
    "invented_citation": "Hallucination",
    "unsupported_claim": "Hallucination",
    "feature_not_built": "Not built (stretch)",
    "infrastructure": "Infrastructure",
}
SYSTEM_ESCALATIONS = {"budget", "verifier_failed", "malformed_output", "model_unavailable",
                      "tool_error", "plan_failed"}  # fmt: skip


def load(run: str) -> list[dict]:
    p = ra.raw_path(run)
    return (
        [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
        if p.exists()
        else []
    )


def events(card: dict) -> list[dict]:
    return card.get("meta", {}).get("events", [])


def classify(rec: dict, t: dict) -> str:
    """One fine label for a wrong turn (first rule that applies)."""
    card, mode, labels = t["card"], rec["mode"], set(t["labels"])
    esc = card.get("meta", {}).get("escalation")
    ext = rec.get("extraction") or {}
    facts_ok = not ext or (ext.get("correct") == ext.get("fields") and not ext.get("invented"))
    tc = next((e for e in events(card) if e["event"] == "tool_calling"), {})
    if rec["category"] == "whatif":
        return "feature_not_built"
    if card["outcome"] == "escalated" and t["gold_outcome"] != "escalated":
        return {"budget": "tool_failure" if mode == "tool_calling" else "budget_exceeded",
                "verifier_failed": "unsupported_claim", "malformed_output": "malformed_output",
                "model_unavailable": "infrastructure", "tool_error": "tool_failure",
                "plan_failed": "plan_invalid"}.get(esc, "extraction_error")  # fmt: skip
    if labels & {"no_clarify", "unnecessary_clarify"}:
        return "clarify_miss" if facts_ok else "extraction_error"
    if t["gold_outcome"] == "refused" and card["outcome"] != "refused":
        return "refusal_miss"  # hand-check 18 Nov: these fell through to extraction_error
    if "refusal_miss" in labels or any(lb.endswith("->refused") for lb in labels):
        return "refusal_miss"
    if mode == "single_rag" and labels & {"wrong_amount", "wrong_kind"}:
        return "invented_figure"
    if mode == "tool_calling" and (tc.get("transcription_diffs") or tc.get("bad_arguments")):
        return "tool_arg_error"
    if mode == "tool_calling" and tc.get("repeated_blocked"):
        return "repeated_call"
    if labels & {"wrong_amount", "wrong_kind", "scope_miss", "escalation_miss"} or any(
        lb.startswith("wrong_outcome") for lb in labels
    ):
        return "extraction_error" if not facts_ok else "rule_selection_error"
    if "invented_citation" in labels:
        return "invented_citation"
    if "missing_citation" in labels:
        if mode == "single_rag":
            return "retrieval_miss"
        # a missing source because a fact was never read (e.g. the arrival state) is an
        # extraction error, not a mapping one (hand-check 18 Nov)
        return "citation_mapping" if facts_ok else "extraction_error"
    return "rule_selection_error"


def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def quantile(v: list[float], q: float) -> float:
    if not v:
        return 0.0
    v = sorted(v)
    return v[min(len(v) - 1, round(q * (len(v) - 1)))]


def hand_doc(path: Path = HAND) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def hand_labels(path: Path = HAND) -> list[dict]:
    return hand_doc(path).get("items", [])


def run_metrics(
    recs: list[dict], usd_per_m: float | None, run: str = "", hand: list[dict] | None = None
) -> dict:
    turns = [(r, t) for r in recs for t in r["turns"]]
    n = len(turns)
    metas = [t["card"].get("meta", {}) for _, t in turns]
    answered = [(r, t) for r, t in turns if t["gold_outcome"] == "answered"]
    by_cat: dict[str, list[bool]] = defaultdict(list)
    for r, t in turns:
        by_cat[r["category"]].append(t["correct"])
    cg = [t for _, t in turns if t["gold_outcome"] == "clarify"]
    cp = [t for _, t in turns if t["card"]["outcome"] == "clarify"]
    tp = sum(t["card"]["outcome"] == "clarify" for t in cg)
    ext = [r["extraction"] for r in recs if r.get("extraction")]
    sys_esc = sum(m.get("escalation") in SYSTEM_ESCALATIONS for m in metas)
    tokens = [m.get("tokens", 0) for m in metas]
    planned = [m for m in metas if m.get("plan_source")]
    sources = sum(len(t["card"].get("sources") or []) for _, t in turns)
    recovered = sum(len(m.get("retrieval_miss_recovered") or []) for m in metas)
    by_hand = {(h["id"], h["turn"]): h["hand"] for h in hand or [] if run in h["runs"]}
    fails = [(r, t, by_hand.get((r["id"], t["turn"])) or classify(r, t), classify(r, t))
             for r, t in turns if not t["correct"]]  # fmt: skip
    out = {
        "turns": n,
        "turn_accuracy": sum(t["correct"] for _, t in turns) / n if n else 0,
        "scenario_accuracy": sum(all(t["correct"] for t in r["turns"]) for r in recs) / len(recs)
        if recs
        else 0,
        "by_category": {c: sum(v) / len(v) for c, v in sorted(by_cat.items())},
        "amount_accuracy": sum(bool(t["score"]["owe_ok"]) for _, t in answered) / len(answered)
        if answered
        else 0,
        "citation_turns": sum(bool(t["score"]["cite_ok"]) for _, t in answered) / len(answered)
        if answered
        else 0,
        "citation_claims": (
            sum(t["score"]["claims_met"] for _, t in answered)
            / max(1, sum(t["score"]["claims"] for _, t in answered))
        ),
        "extraction": (sum(e["correct"] for e in ext) / sum(e["fields"] for e in ext))
        if ext
        else None,
        "invented_fields": sum(e["invented"] for e in ext) if ext else None,
        "clarify_recall": tp / len(cg) if cg else None,
        "clarify_precision": tp / len(cp) if cp else None,
        "completion": 1 - sys_esc / n if n else 0,
        "system_escalations": sys_esc,
        "model_calls_mean": statistics.mean(m.get("model_calls", 0) for m in metas) if n else 0,
        "tool_calls_mean": statistics.mean(m.get("tool_calls", 0) for m in metas) if n else 0,
        "tokens_mean": statistics.mean(tokens) if n else 0,
        "tokens_total": sum(tokens),
        "cost_per_1k_turns_usd": (statistics.mean(tokens) * usd_per_m / 1e3)
        if (n and usd_per_m)
        else None,
        "latency_p50": quantile([m.get("seconds", 0) for m in metas], 0.5),
        "latency_p95": quantile([m.get("seconds", 0) for m in metas], 0.95),
        "plan_fallback_rate": (
            sum(m["plan_source"] == "fallback" for m in planned) / len(planned) if planned else None
        ),
        "retrieval_miss_recovered_rate": recovered / sources if sources else None,
        "failures": Counter(f for _, _, f, _ in fails),
        "failure_rows": [
            {
                "id": r["id"],
                "turn": t["turn"],
                "category": r["category"],
                "label": f,
                "bucket": BUCKETS[f],
                "gold": f"{t['gold_outcome']}/{t['gold_kind']} {t['gold_owe'] or ''}",
                "got": f"{t['card']['outcome']}/{t['card']['kind']} {t['card'].get('owe_usd') or ''}",
                "score_labels": t["labels"],
                "auto": a,
                "hand_checked": (r["id"], t["turn"]) in by_hand,
            }
            for r, t, f, a in fails
        ],
    }
    return out


def fmt(v, kind="pct") -> str:
    if v is None:
        return "-"
    if kind == "pct":
        return f"{100 * v:.1f}%"
    if kind == "s":
        return f"{v:.1f} s"
    if kind == "usd":
        return f"${v:,.2f}"
    return f"{v:,.1f}" if isinstance(v, float) else str(v)


def spread(vals: list[float | None], kind="pct") -> str:
    vals = [v for v in vals if v is not None]
    if not vals:
        return "-"
    if len(vals) == 1:
        return fmt(vals[0], kind)
    return f"{fmt(statistics.mean(vals), kind)} ({fmt(min(vals), kind)}–{fmt(max(vals), kind)})"


ROWS = [
    ("Turns correct", "turn_accuracy", "pct"), ("Scenarios fully correct", "scenario_accuracy", "pct"),
    ("Amount right (answered turns)", "amount_accuracy", "pct"),
    ("All citation claims met (answered)", "citation_turns", "pct"),
    ("Citation claims met", "citation_claims", "pct"), ("Fact extraction (fields)", "extraction", "pct"),
    ("Clarify recall", "clarify_recall", "pct"), ("Clarify precision", "clarify_precision", "pct"),
    ("Task completion (no system escalation)", "completion", "pct"),
    ("Model calls per turn", "model_calls_mean", "num"), ("Tool calls per turn", "tool_calls_mean", "num"),
    ("Tokens per turn", "tokens_mean", "num"), ("Cost per 1,000 turns (assumed price)", "cost_per_1k_turns_usd", "usd"),
    ("Latency p50", "latency_p50", "s"), ("Latency p95", "latency_p95", "s"),
    ("Plan fallback rate", "plan_fallback_rate", "pct"),
    ("Retrieval miss recovered (share of sources)", "retrieval_miss_recovered_rate", "pct"),
]  # fmt: skip


def build(runs: list[str], usd_per_m: float | None, out_dir: Path) -> str:
    hand = hand_labels()
    m = {r: run_metrics(load(r), usd_per_m, r, hand) for r in runs if load(r)}
    groups = defaultdict(list)
    for r in m:
        groups[r.rsplit("-", 1)[0] if r.startswith("planner-") and not r.endswith("corr") else
               ("planner-corrections" if r.endswith("-corr") else r)].append(r)  # fmt: skip
    cols = list(groups)
    lines = ["# Evaluation report (plan §10)", "",
             ("Generated by `eval/eval_report.py` from `docs/results/runs/*/raw.jsonl`; scored with "
             "`eval/score.py` (SPEC §10). Frozen agent and eval set (see `runs/official.yaml`). "
             "Planner: mean and range over its runs."), ""]  # fmt: skip
    if usd_per_m:
        lines += [(f"**Cost uses an ASSUMED price of ${usd_per_m:.2f} per million tokens** "
                  "(upgrad publishes none)."), ""]  # fmt: skip
    lines += ["| metric | " + " | ".join(f"{c} ({len(groups[c])} run{'s' if len(groups[c]) > 1 else ''})" for c in cols) + " |",
              "|---|" + "---|" * len(cols)]  # fmt: skip
    for label, key, kind in ROWS:
        lines.append(
            f"| {label} | "
            + " | ".join(spread([m[r][key] for r in groups[c]], kind) for c in cols)
            + " |"
        )
    cats = sorted({c for r in m for c in m[r]["by_category"]})
    lines += ["", "## Accuracy per category (turns)", "",
              "| category | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]  # fmt: skip
    for cat in cats:
        lines.append(f"| {cat} | " + " | ".join(
            spread([m[r]["by_category"].get(cat) for r in groups[c]]) for c in cols) + " |")  # fmt: skip
    lines += ["", "## Failure taxonomy (wrong turns, all runs per column)", "",
              "| bucket | fine label | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]  # fmt: skip
    labels = sorted({f for r in m for f in m[r]["failures"]}, key=lambda f: (BUCKETS[f], f))
    for f in labels:
        lines.append(f"| {BUCKETS[f]} | {f} | " + " | ".join(
            str(sum(m[r]["failures"].get(f, 0) for r in groups[c])) for c in cols) + " |")  # fmt: skip
    lines += hand_section(hand, m) + repeat_section(groups)
    text = "\n".join(lines) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval-report.md").write_text(text, encoding="utf-8")
    res = out_dir / "results" if out_dir == DOCS else out_dir  # docs/results/ for the official run
    res.mkdir(parents=True, exist_ok=True)
    rows = [dict(run=r, **row) for r in m for row in m[r]["failure_rows"]]
    check = ["# Failures to hand-check (plan §10.5: at least 15)", "",
             ("Each wrong turn with its label. `hand` = checked; the label is then the hand label "
              "(docs/results/hand-check.yaml, with the cause) and `auto` is the classifier's."), "",
             "| run | id | turn | category | gold | got | score labels | label | bucket | auto | check |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    check += [f"| {x['run']} | {x['id']} | {x['turn']} | {x['category']} | {x['gold']} | {x['got']} | "
              f"{', '.join(x['score_labels'])} | {x['label']} | {x['bucket']} | {x['auto']} | "
              f"{'hand' if x['hand_checked'] else ''} |" for x in rows]  # fmt: skip
    (res / "failures-to-check.md").write_text("\n".join(check) + "\n", encoding="utf-8")
    (res / "official.json").write_text(json.dumps(
        {r: {k: v for k, v in x.items() if k != "failure_rows"} for r, x in m.items()},
        indent=1, default=dict) + "\n", encoding="utf-8")  # fmt: skip
    return text


def hand_section(hand: list[dict], m: dict) -> list[str]:
    """Plan §10.5: what was checked, and how often the classifier agrees (now, and when checked)."""
    if not hand:
        return []
    autos = {(r, x["id"], x["turn"]): x["auto"] for r in m for x in m[r]["failure_rows"]}
    now = [autos.get((h["runs"][0], h["id"], h["turn"])) for h in hand]
    agree_now = sum(a == h["hand"] for a, h in zip(now, hand, strict=True))
    agree_then = sum(h["auto"] == h["hand"] for h in hand)
    n_runs = sum(len(h["runs"]) for h in hand)
    doc = hand_doc()
    who = (f"Labels drafted by {doc.get('drafted_by')}, reviewed by {doc['reviewed_by']}."
           if doc.get("reviewed_by") else
           f"**Labels drafted by {doc.get('drafted_by')}; not yet reviewed by a person.**")  # fmt: skip
    out = ["", "## Hand-check (plan §10.5)", "",
           (f"{len(hand)} distinct failures checked by hand ({n_runs} wrong turns across the runs "
            "that gave the same answer); the taxonomy above uses the hand label. The automatic "
            f"label agreed on {agree_then}/{len(hand)} when checked; after the two classifier "
            f"fixes the check prompted (refusal misses, missing sources from unread facts) it "
            f"agrees on {agree_now}/{len(hand)}. {who} Causes: `docs/results/hand-check.yaml`."), "",
           "| id | turn | runs | automatic | hand |", "|---|---|---|---|---|"]  # fmt: skip
    out += [f"| {h['id']} | {h['turn']} | {len(h['runs'])} | {a} | {h['hand']} |"
            for a, h in zip(now, hand, strict=True)]  # fmt: skip
    return out


def repeat_section(groups: dict) -> list[str]:
    """How often repeated runs of the same agent gave a different answer (temperature 0)."""
    out = []
    for c, runs in groups.items():
        if len(runs) < 2:
            continue
        cards = [{(x["id"], t["turn"]): t["card"].get("bottom_line") for x in load(r)
                  for t in x["turns"]} for r in runs]  # fmt: skip
        keys = set.intersection(*(set(k) for k in cards))
        diff = sum(len({cc[k] for cc in cards}) > 1 for k in keys)
        out.append(f"- {c}: {diff} of {len(keys)} turns answered differently across "
                   f"{len(runs)} runs")  # fmt: skip
    if not out:
        return []
    return ["", "## Repeat runs", "",
            ("Chat runs at temperature 0, so repeat runs mostly measure determinism, not sampling "
             "variance. A different answer can also come from the endpoint (busy or failing)."),
            "", *out]  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", nargs="*", help="default: the official runs")
    ap.add_argument("--usd-per-m", type=float, help="ASSUMED price per million tokens")
    ap.add_argument("--out", type=Path, default=DOCS)
    a = ap.parse_args()
    runs = a.runs or [r for r, _, _ in RUNS]
    print(build(runs, a.usd_per_m, a.out))


if __name__ == "__main__":
    main()
