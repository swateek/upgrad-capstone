"""Replay a run's intake outputs through today's code, with no model call.

    uv run python eval/replay.py results/runs/v1-dev2-router --set dev2

For each question, the model's raw intake JSON recorded in the run (`steps`, stage "intake") is
put through today's guard, clean-up (src/agent/pipeline.clean) and code router, and the outcome,
bottom line, dollars, what-if and clarify facts are compared with gold, as eval/score.py does.
Citations and the writer are not replayed (they need the model).

It answers one question: had the model read the questions exactly as it did in that run, would
today's code get them right? A cheap check of a code change before a full run; it never replaces
one (a prompt change, or the cache, changes what the model reads). Never use it on a held-out set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.run_agent import HELD_OUT, SETS
from eval.score import load_jsonl

TOL = 0.01


def replay_item(rec: dict, gold: dict) -> dict:
    from src.agent.intake import IntakeResult
    from src.agent.pipeline import clean
    from src.agent.router import route
    from src.safety.guard import check_question
    from src.tools.common import ToolError

    g = gold["gold"]
    q = gold["question"]
    out: dict = {"id": gold["id"], "type": gold["type"], "gold_outcome": g["outcome"]}
    guard = check_question(q)
    raw = [s for s in rec.get("steps") or [] if s.get("stage") == "intake"]
    if guard.action == "refuse":
        got = {"outcome": "refused"}
    elif not raw:
        got = {"outcome": (rec.get("answer") or {}).get("outcome", "none")}
    else:
        try:
            facts = IntakeResult.model_validate_json(raw[-1]["content"])
        except Exception:  # noqa: BLE001 - the run repaired it; replay cannot
            got = {"outcome": (rec.get("answer") or {}).get("outcome", "none")}
        else:
            facts, _, _ = clean(facts, q)
            basket = [
                b for b in facts.basket if b.category != "other" and b.type != "other"
            ]
            if facts.request_kind != "assess":
                got = {"outcome": "refused"}
            elif not basket:  # as pipeline.respond: other goods only -> refused
                other = len(basket) < len(facts.basket) or guard.other_goods
                got = (
                    {"outcome": "refused"}
                    if other
                    else {"outcome": "clarify", "missing": ["count"]}
                )
            else:
                try:
                    r = route(facts.profile, basket, facts.owe_less_than_usd)
                    got = {
                        "outcome": r.outcome,
                        "lines": r.line_types,
                        "total": float(r.duty.total_usd) if r.duty else None,
                        "missing": r.missing,
                        "whatif": (r.whatif.max_units, float(r.whatif.owed_usd))
                        if r.whatif
                        else None,
                    }
                except ToolError as e:
                    got = {
                        "outcome": "clarify"
                        if e.code == "missing_fact"
                        else "escalated",
                        "missing": list(e.missing or []),
                    }
    out["pred_outcome"] = got["outcome"]
    checks = {"outcome": got["outcome"] == g["outcome"]}
    if g["outcome"] == "answered" and g.get("bottom_line"):
        checks["bottom_line"] = got.get("lines") == [
            b["type"] for b in g["bottom_line"]
        ]
    if g["outcome"] == "answered" and g.get("total_usd") is not None:
        checks["dollars"] = (
            got.get("total") is not None and abs(got["total"] - g["total_usd"]) <= TOL
        )
    if g.get("whatif"):
        w = got.get("whatif")
        checks["whatif"] = (
            bool(w)
            and w[0] == g["whatif"]["max_units"]
            and abs(w[1] - g["whatif"]["owed_usd"]) <= TOL
        )
    if g["outcome"] == "clarify":
        checks["clarify"] = sorted(got.get("missing") or []) == sorted(
            g.get("clarify_facts") or []
        )
    out.update(checks)
    out["correct"] = all(checks.values())
    out["got"] = got
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--set", required=True, choices=sorted(SETS))
    ap.add_argument("--mode", default="router")
    ap.add_argument(
        "--before", help="scores_<mode>.csv of the run, to list what changed"
    )
    args = ap.parse_args()
    if args.set in HELD_OUT:
        print(f"Refusing to replay on {HELD_OUT[args.set]}: held out")
        return 1
    gold = {g["id"]: g for g in load_jsonl(SETS[args.set])}
    recs = load_jsonl(Path(args.run_dir) / f"{args.mode}.jsonl")
    rows = [replay_item(r, gold[r["id"]]) for r in recs if r["id"] in gold]
    before = {}
    path = Path(args.before or Path(args.run_dir) / f"scores_{args.mode}.csv")
    if path.exists():
        import csv

        before = {r["id"]: r["correct"] == "True" for r in csv.DictReader(path.open())}
    n = len(rows)
    ok = sum(r["correct"] for r in rows)
    print(
        f"replay of {args.run_dir} on {args.set}: {ok}/{n} = {ok / n:.3f} (outcome, bottom line, dollars, what-if, clarify; no citations)"
    )
    if before:
        print(
            f"the run itself (all checks incl. citations): {sum(before.values())}/{len(before)}"
        )
    for r in rows:
        if not r["correct"]:
            failed = [
                k
                for k in ("outcome", "bottom_line", "dollars", "whatif", "clarify")
                if r.get(k) is False
            ]
            print(
                f"   wrong: {r['id']} {r['type']}: {' '.join(failed)}  got {r['got']}"
            )
    fixed = [r["id"] for r in rows if r["correct"] and before.get(r["id"]) is False]
    broken = [r["id"] for r in rows if not r["correct"] and before.get(r["id"]) is True]
    if before:
        print(f"now right, wrong in the run: {len(fixed)} {fixed}")
        print(f"now wrong, right in the run: {len(broken)} {broken}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
