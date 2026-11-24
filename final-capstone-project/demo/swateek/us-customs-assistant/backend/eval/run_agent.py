"""Run the agent over an eval set and score every turn (plan step 10 dev runs; step 13 official).

    uv run python -m eval.run_agent --set dev --mode planner --run dev-01 --dry-run
    uv run python -m eval.run_agent --set dev --mode planner --run dev-01 --who swateek   # upgrad!
    uv run python -m eval.run_agent --run dev-01 --report-only

Each scenario plays its turns in one thread (clarify replies and corrections in order). A turn
is scored with eval.score (SPEC §10): outcome, kind, amount to the cent, citation claims; plus
clarify fields, and fact extraction on the last turn. Raw cards go to
docs/results/runs/<run>/raw.jsonl one scenario per line, so an interrupted run resumes; the
summary is docs/results/runs/<run>/summary.md. Calls to upgrad (chat + embeddings) are appended to
docs/quota-log.md. Tune on `dev` only; `frozen` and `corrections` are measured, never tuned on.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict

from customs.config import PROJECT_ROOT, get_settings
from customs.ingest.index import append_quota_log
from eval.score import score_extraction, score_turn

EVAL = PROJECT_ROOT / "pack" / "eval"
RUNS = PROJECT_ROOT / "docs" / "results" / "runs"
SETS = {"dev": "dev.jsonl", "frozen": "queries.jsonl", "corrections": "corrections.jsonl"}
# expected chat calls / embedding requests for a turn that goes the normal way, by gold outcome
NOMINAL = {"answered": (4, 1), "clarify": (1, 0), "refused": (0, 0), "out_of_scope": (1, 0),
           "escalated": (2, 0)}  # fmt: skip
SINGLE_RAG = {"refused": (0, 0)}  # every other turn: 1 chat call + 1 embedding request


def load(set_name: str) -> list[dict]:
    path = EVAL / SETS[set_name]
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def raw_path(run: str):
    return RUNS / run / "raw.jsonl"


def done_ids(run: str) -> set[str]:
    p = raw_path(run)
    if not p.exists():
        return set()
    return {json.loads(x)["id"] for x in p.read_text(encoding="utf-8").splitlines() if x}


def expected_calls(rows: list[dict], mode: str) -> tuple[int, int, int]:
    """(chat calls, embedding requests) when every turn goes the normal way, and the cap."""
    s = get_settings()
    chat = emb = turns = 0
    for r in rows:
        for g in r["gold"]:
            turns += 1
            if mode == "single_rag":
                c, e = SINGLE_RAG.get(g["outcome"], (1, 1))
            else:
                c, e = NOMINAL[g["outcome"]]
                if mode == "router" and g["outcome"] in ("answered", "escalated"):
                    c -= 1
                if mode == "tool_calling" and g["outcome"] == "answered":
                    c += 2  # executor rounds: tools in one round + the closing reply
            chat += c
            emb += e
    return chat, emb, turns * s.agent_step_limit


def pred_of(card: dict) -> dict:
    return {k: card.get(k) for k in ("outcome", "kind", "owe_usd", "citations")}


def run(run_name: str, set_name: str, mode: str, rows: list[dict], agent, who: str | None) -> dict:
    out = raw_path(run_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = done_ids(run_name)
    totals = Counter()
    t0 = time.time()
    with out.open("a", encoding="utf-8") as fh:
        for row in rows:
            if row["id"] in done:
                continue
            thread = f"{run_name}-{row['id']}"
            turns = []
            for i, text in enumerate(row["turns"]):
                gold = row["gold"][i]
                card = agent.ask(thread, text, mode=mode,
                                 tags=["eval", run_name, set_name, row["category"], row["id"]])  # fmt: skip
                sc = score_turn(pred_of(card), gold)
                m = card.get("meta", {})
                totals["chat"] += m.get("model_calls", 0)
                totals["embed"] += m.get("embed_requests", 0)
                totals["tokens"] += m.get("tokens", 0)
                turns.append({
                    "turn": i + 1, "gold_outcome": gold["outcome"],
                    "gold_kind": gold["bottom_line"]["kind"],
                    "gold_owe": gold["bottom_line"].get("owe_usd"),
                    "gold_clarify_fields": gold.get("clarify_fields", []),
                    "correct": sc.correct, "labels": sc.labels, "score": sc.__dict__,
                    "facts": (agent.state(thread) or {}).get("facts"), "card": card,
                })  # fmt: skip
            facts = (agent.state(thread) or {}).get("facts") or {}
            rec = {"id": row["id"], "category": row["category"], "set": set_name, "mode": mode,
                   "turns": turns, "extraction": score_extraction(facts, row["facts"])
                   if mode != "single_rag" else None}  # fmt: skip
            fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
            ok = all(t["correct"] for t in turns)
            print(f"{'ok ' if ok else 'BAD'} {row['id']} {row['category']}", flush=True)
    if who and (totals["chat"] or totals["embed"]):
        append_quota_log(
            who, f"agent run {run_name} ({set_name}, {mode})", totals["chat"], totals["embed"],
            totals["tokens"], f"run took {round((time.time() - t0) / 60)} min",
        )  # fmt: skip
    return dict(totals)


# --- report -----------------------------------------------------------------------------------


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"


def p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, round(q * (len(v) - 1)))]


def report(run_name: str) -> str:
    recs = [json.loads(x) for x in raw_path(run_name).read_text(encoding="utf-8").splitlines() if x]
    turns = [(r, t) for r in recs for t in r["turns"]]
    by_cat: dict[str, list[bool]] = defaultdict(list)
    labels = Counter()
    for r, t in turns:
        by_cat[r["category"]].append(t["correct"])
        labels.update(t["labels"])
    metas = [t["card"].get("meta", {}) for _, t in turns]
    calls = [m.get("model_calls", 0) for m in metas]
    tools = [m.get("tool_calls", 0) for m in metas]
    toks = [m.get("tokens", 0) for m in metas]
    secs = [m.get("seconds", 0) for m in metas]
    answered = [(r, t) for r, t in turns if t["gold_outcome"] == "answered"]
    amount_ok = sum(bool(t["score"]["owe_ok"]) for _, t in answered)
    cite_ok = sum(bool(t["score"]["cite_ok"]) for _, t in answered)
    claims = sum(t["score"]["claims"] for _, t in answered)
    claims_met = sum(t["score"]["claims_met"] for _, t in answered)
    clar_gold = [(r, t) for r, t in turns if t["gold_outcome"] == "clarify"]
    clar_pred = [(r, t) for r, t in turns if t["card"]["outcome"] == "clarify"]
    clar_tp = sum(t["card"]["outcome"] == "clarify" for _, t in clar_gold)
    events = Counter(e["event"] for m in metas for e in m.get("events", []))
    esc = Counter(m.get("escalation") for m in metas if m.get("escalation"))
    plan_src = Counter(m.get("plan_source") for m in metas if m.get("plan_source"))
    ext = [r["extraction"] for r in recs if r.get("extraction")]
    ext_f = sum(e["fields"] for e in ext)
    ext_c = sum(e["correct"] for e in ext)
    ext_i = sum(e["invented"] for e in ext)
    mode = recs[0]["mode"] if recs else "?"
    lines = [
        f"# Agent run `{run_name}` ({recs[0]['set'] if recs else '?'}, mode `{mode}`)",
        "",
        "Generated by `eval/run_agent.py`. Scored with `eval/score.py` (SPEC §10).",
        "",
        (
            f"- **Turns correct: {pct(sum(t['correct'] for _, t in turns), len(turns))}**; "
            f"scenarios fully correct: {pct(sum(all(t['correct'] for t in r['turns']) for r in recs), len(recs))}"
        ),
        (
            f"- Answered turns: amount right {pct(amount_ok, len(answered))}; all citation claims met "
            f"{pct(cite_ok, len(answered))}; claims met {pct(claims_met, claims)}"
        ),
        f"- Clarify: recall {pct(clar_tp, len(clar_gold))}, precision {pct(clar_tp, len(clar_pred))}",
        f"- Fact extraction (last turn): {pct(ext_c, ext_f)} fields right; {ext_i} invented",
        (
            f"- Model calls per turn: mean {statistics.mean(calls):.1f}, max {max(calls)}; tool calls "
            f"mean {statistics.mean(tools):.1f}; tokens per turn mean {statistics.mean(toks):,.0f}, max "
            f"{max(toks):,}"
        ),
        f"- Latency per turn: p50 {p(secs, 0.5):.1f} s, p95 {p(secs, 0.95):.1f} s",
        f"- Plan source: {dict(plan_src)}; escalations: {dict(esc)}",
        f"- Events: {dict(events)}",
        "",
        "## By category",
        "",
        "| category | turns correct |",
        "|---|---|",
        *[f"| {c} | {pct(sum(v), len(v))} |" for c, v in sorted(by_cat.items())],
        "",
        "## Failure labels (turn level)",
        "",
        *(f"- {k}: {v}" for k, v in labels.most_common()),
        "",
        "## Failed turns",
        "",
        "| id | turn | gold | got | labels | escalation / events |",
        "|---|---|---|---|---|---|",
    ]
    for r, t in turns:
        if t["correct"]:
            continue
        c = t["card"]
        m = c.get("meta", {})
        ev = ", ".join(sorted({e["event"] for e in m.get("events", [])} - {"model_call",
                                                                            "tool_call"}))  # fmt: skip
        lines.append(
            f"| {r['id']} | {t['turn']} | {t['gold_outcome']}/{t['gold_kind']} {t['gold_owe'] or ''} "
            f"| {c['outcome']}/{c['kind']} {c.get('owe_usd') or ''} | {', '.join(t['labels'])} "
            f"| {m.get('escalation') or ''} {m.get('detail', '')[:80]} {ev} |"
        )
    text = "\n".join(lines) + "\n"
    (RUNS / run_name / "summary.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", choices=list(SETS), default="dev")
    ap.add_argument("--mode", choices=["planner", "router", "tool_calling", "single_rag"],
                    default="planner")  # fmt: skip
    ap.add_argument("--run", required=True, help="run name, e.g. dev-01")
    ap.add_argument("--ids", nargs="*", help="only these scenario ids")
    ap.add_argument("--dry-run", action="store_true", help="expected call counts; sends nothing")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--who", help="who ran it (quota log); required to call the endpoints")
    a = ap.parse_args()
    if a.report_only:
        print(report(a.run))
        return
    rows = load(a.set)
    if a.ids:
        rows = [r for r in rows if r["id"] in set(a.ids)]
    todo = [r for r in rows if r["id"] not in done_ids(a.run)]
    chat, emb, cap = expected_calls(todo, a.mode)
    print(f"{a.set}/{a.mode}: {len(todo)} scenarios to run ({sum(len(r['turns']) for r in todo)} "
          f"turns); expected ~{chat} chat calls + ~{emb} embedding requests if every turn goes "
          f"the normal way; hard cap {cap} chat calls (10 per turn)")  # fmt: skip
    if a.dry_run:
        print("dry run: nothing sent")
        return
    if not a.who:
        print("FAIL calling the upgrad endpoints needs --who (quota log)", file=sys.stderr)
        sys.exit(1)
    from langgraph.checkpoint.memory import InMemorySaver

    from customs.agent.graph import CustomsAgent

    agent = CustomsAgent(get_settings(), checkpointer=InMemorySaver())
    totals = run(a.run, a.set, a.mode, todo, agent, a.who)
    print(f"sent: {totals}")
    print(report(a.run))


if __name__ == "__main__":
    main()
