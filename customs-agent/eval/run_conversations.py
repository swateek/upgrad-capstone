"""Run the multi-turn dev conversations through the session graph and score every turn.

    uv run python eval/run_conversations.py --run-name day7-conv                 # code router
    uv run python eval/run_conversations.py --mode planner --run-name day7-conv-planner
    uv run python eval/run_conversations.py --only C03 C08                       # a few

A turn is scored like a single question (eval/score.py: outcome, bottom line, dollars, clarify
facts, citations, must-not-contain) plus its assumptions (the SPEC 5.2 defaults used must equal the
gold's). A conversation is correct when every turn is. Writes results/runs/<run>/conversations.jsonl
(one record per turn), scores_conversations.csv and summary_conversations.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.score import load_jsonl, score_item, summary, write_csv

CONVS = ROOT / "eval" / "conversations.jsonl"


def score_turn(conv: dict, turn: dict, rec: dict) -> dict:
    gold_rec = {
        "id": f"{conv['id']}-t{turn['turn']}",
        "type": conv["type"],
        "gold": turn["gold"],
    }
    row = score_item(gold_rec, rec)
    want = sorted(turn["gold"].get("assumptions") or [])
    got = sorted(rec.get("assumptions") or [])
    row["assumptions"] = want == got
    row["correct"] = bool(row["correct"]) and row["assumptions"]
    return row


def run(
    sessions,
    mode: str,
    run_name: str,
    only: list[str] | None = None,
    results: Path = ROOT / "results",
) -> dict:
    convs = load_jsonl(CONVS)
    if only:
        convs = [c for c in convs if c["id"] in only]
    out_dir = results / "runs" / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "conversations.jsonl"
    rows, records = [], []
    for c in convs:
        sid = f"{run_name}-{c['id']}-{uuid.uuid4().hex[:6]}"
        for t in c["turns"]:
            t0 = time.perf_counter()
            if "edit" in t:
                res = sessions.turn(sid, edit=t["edit"], mode=mode)
            else:
                res = sessions.turn(sid, message=t["user"], mode=mode)
            rec = res.record(f"{c['id']}-t{t['turn']}", mode)
            rec["seconds"] = round(time.perf_counter() - t0, 1)
            records.append(rec)
            row = score_turn(c, t, rec)
            rows.append(row)
            got = rec["answer"]["outcome"] if rec["answer"] else "none"
            mark = "ok " if row["correct"] else "BAD"
            extra = (
                ""
                if row["correct"]
                else f"  (gold {t['gold']['outcome']} {t['gold'].get('clarify_facts') or ''} {t['gold'].get('total_usd') or ''})"
            )
            print(
                f"[{mode}] {mark} {c['id']} t{t['turn']} {got} {rec['answer'].get('clarify_facts') or ''} "
                f"{rec['answer'].get('total_usd') if rec['answer'] else ''}{extra}  ({rec['calls']} calls, {rec['tokens']} tok, {rec['seconds']} s)"
            )
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records)
    )
    write_csv(out_dir / "scores_conversations.csv", rows)
    conv_ok = {}
    for r in rows:
        cid = r["id"].split("-t")[0]
        conv_ok[cid] = conv_ok.get(cid, True) and bool(r["correct"])
    s = {
        **summary(rows),
        "turns": len(rows),
        "turn_accuracy": round(sum(r["correct"] for r in rows) / len(rows), 3)
        if rows
        else None,
        "conversations": len(conv_ok),
        "conversation_accuracy": round(sum(conv_ok.values()) / len(conv_ok), 3)
        if conv_ok
        else None,
        "assumptions_acc": round(sum(r["assumptions"] for r in rows) / len(rows), 3)
        if rows
        else None,
    }
    (out_dir / "summary_conversations.json").write_text(
        json.dumps({"run": run_name, "mode": mode, **s}, indent=1)
    )
    print(
        f"== conversations ({mode}): {sum(conv_ok.values())}/{len(conv_ok)} conversations, turn accuracy {s['turn_accuracy']} "
        f"({len(rows)} turns)  dollars {s['dollar_acc']}  clarify {s['clarify_acc']}  citations {s['citation_acc']}  "
        f"assumptions {s['assumptions_acc']}  tokens/turn {s['tokens_per_q']}"
    )
    for cid, ok in conv_ok.items():
        if not ok:
            print(f"   wrong: {cid}")
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("router", "planner"), default="router")
    ap.add_argument("--run-name", default="conversations")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    from src.agent.session import Sessions
    from src.llm import LLM
    from src.tools.search_regulations import RegulationSearch

    llm = LLM.from_env(run_name=args.run_name)
    print(f"chat: {llm.chat_model}  cache {'on' if llm.cache_enabled else 'OFF'}")
    search = RegulationSearch.from_env(llm)
    db = ROOT / "results" / "runs" / args.run_name / "sessions.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    run(Sessions(llm, search, db=db), args.mode, args.run_name, args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
