"""Run the agent on a scenario set and score it (eval/score.py).

    uv run python eval/run_agent.py --set dev --run-name day5-router            # agent v0, code router
    uv run python eval/run_agent.py --set dev --mode planner --run-name day6-planner   # LLM planner
    uv run python eval/run_agent.py --set dev --mode single_rag --run-name day6-single-rag   # search + 1 call
    uv run python eval/run_agent.py --set dev --limit 3                          # smoke test
    uv run python eval/run_agent.py --set paraphrase --run-name para-router      # generalisation check (once)
    LLM_CACHE=0 uv run python eval/run_agent.py --set eval --run-name official-router-1   # Day 10 only

Writes results/runs/<run>/<mode>.jsonl (one record per item: answer, retrieved_ids, card, trace;
resumable), scores_<mode>.csv and summary_<mode>.json. Never tune on --set eval (CLAUDE.md rule 6).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.score import by_type, load_jsonl, score, summary, write_csv

SETS = {
    "dev": ROOT / "eval" / "dev_set.jsonl",
    # one-shot check: PARAPHRASE_BRIEF.md
    "paraphrase": ROOT / "eval" / "paraphrase_set.jsonl",
    "redteam": ROOT / "eval" / "redteam.jsonl",  # eval/redteam.yaml
    "eval": ROOT / "eval" / "eval_set.jsonl",
}
MODES = ("router", "planner", "single_rag")
CHECKS = (
    "outcome",
    "bottom_line",
    "dollars",
    "whatif",
    "clarify",
    "citations",
    "must_not",
)


def run(
    llm,
    search,
    set_name: str,
    mode: str,
    run_name: str,
    limit: int | None = None,
    only: list[str] | None = None,
    verify_with_llm: bool = True,
    results: Path = ROOT / "results",
) -> dict:
    from src.agent.pipeline import answer_question

    gold = load_jsonl(SETS[set_name])
    if only:
        gold = [g for g in gold if g["id"] in only]
    if limit:
        gold = gold[:limit]
    out_dir = results / "runs" / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{mode}.jsonl"
    done = {r["id"] for r in load_jsonl(path)} if path.exists() else set()
    with path.open("a") as fh:
        for item in gold:
            if item["id"] in done:
                continue
            t0 = time.perf_counter()
            if mode == "single_rag":
                res = _single_rag(llm, search, item)
            else:
                res = answer_question(
                    item["question"],
                    llm=llm,
                    search=search,
                    inject=item.get("inject_into_retrieval"),
                    verify_with_llm=verify_with_llm,
                    mode=mode,
                )
            rec = res.record(item["id"], mode)
            rec["seconds"] = round(time.perf_counter() - t0, 1)
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            fh.flush()
            got = rec["answer"]["outcome"] if rec["answer"] else "none"
            flag = (
                ""
                if got == item["gold"]["outcome"]
                else f"  (gold {item['gold']['outcome']})"
            )
            err = f"  ERROR {rec['error'][:90]}" if rec["error"] else ""
            fb = {True: "  plan=FALLBACK", False: "  plan=ok"}.get(
                rec.get("plan_fallback"), ""
            )
            print(
                f"[{mode}] {item['id']} {got}{flag}  reason={rec['reason']}  "
                f"({rec['tool_steps']} steps, {rec['calls']} calls, {rec['tokens']} tok, {rec['seconds']} s){fb}{err}"
            )
    rows = score(
        gold, [r for r in load_jsonl(path) if r["id"] in {g["id"] for g in gold}]
    )
    write_csv(out_dir / f"scores_{mode}.csv", rows)
    recs = [r for r in load_jsonl(path) if r["id"] in {g["id"] for g in gold}]
    planned = [r for r in recs if r.get("plan_fallback") is not None]
    s = {**summary(rows), "by_type": by_type(rows)}
    s["max_tool_steps"] = max((r.get("tool_steps") or 0) for r in recs) if recs else 0
    if planned:
        s["plan_fallbacks"] = sum(1 for r in planned if r["plan_fallback"])
        s["planned_n"] = len(planned)
    from eval.freeze import status as freeze_status

    s["freeze"] = freeze_status()
    (out_dir / f"summary_{mode}.json").write_text(
        json.dumps({"set": set_name, "run": run_name, **s}, indent=1)
    )
    print(
        f"== {mode}: accuracy {s['accuracy']}  outcome {s['outcome_acc']}  bottom line {s['bottom_line_acc']}  "
        f"dollars {s['dollar_acc']} (n={s['dollar_n']})  clarify {s['clarify_acc']}  citations {s['citation_acc']}  "
        f"tokens/q {s['tokens_per_q']}  calls/q {s['calls_per_q']}  max steps {s['max_tool_steps']}"
        + (
            f"  plan fallbacks {s['plan_fallbacks']}/{s['planned_n']}"
            if planned
            else ""
        )
    )
    for r in rows:
        if not r["correct"]:
            failed = [k for k in CHECKS if r.get(k) is False]
            print(
                f"   wrong: {r['id']} {r['type']}: {' '.join(failed)}  {r.get('error') or ''}"
            )
    return s


def _single_rag(llm, search, item):
    """Wrap the single_rag baseline in the agent's record format."""
    from src.agent.pipeline import AgentRun
    from src.baselines.single_rag import single_rag

    base, ids, trace = single_rag(
        llm, search, item["question"], item.get("inject_into_retrieval")
    )
    res = AgentRun(
        answer=base.answer, error=base.error, retrieved_ids=ids, trace=[trace]
    )
    res.usage.calls, res.usage.tokens, res.usage.steps = (
        base.calls,
        base.tokens,
        base.steps,
    )
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=sorted(SETS), default="dev")
    ap.add_argument("--mode", choices=MODES, default="router")
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--limit", type=int, help="first N items only (smoke test)")
    ap.add_argument("--only", nargs="*", help="item ids, e.g. D01 D12")
    ap.add_argument(
        "--no-verify-llm",
        action="store_true",
        help="skip the verifier's LLM evasion check",
    )
    ap.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="run the eval set although the code does not match eval/freeze.json",
    )
    args = ap.parse_args()
    if args.set == "eval":
        from eval.freeze import status as freeze_status

        fz = freeze_status()
        if not (fz["frozen"] and fz["matches"]) and not args.allow_unfrozen:
            print(
                "Refusing to run eval-v2: "
                + (
                    "no freeze yet (eval/freeze.py --write)"
                    if not fz["frozen"]
                    else "the code drifted from the freeze:"
                )
            )
            for line in fz.get("drift") or []:
                print(f"  {line}")
            return 1
        print(
            "Running on eval-v2: official runs only (Day 10). Nothing may be tuned on this result."
        )

    from src.llm import LLM
    from src.tools.search_regulations import RegulationSearch

    run_name = args.run_name or f"agent-{args.set}"
    llm = LLM.from_env(run_name=run_name)
    print(f"chat: {llm.chat_model}  cache {'on' if llm.cache_enabled else 'OFF'}")
    if args.set == "eval" and llm.cache_enabled and not args.allow_unfrozen:
        print("Refusing to run eval-v2 with the response cache on: set LLM_CACHE=0")
        return 1
    search = RegulationSearch.from_env(llm)
    print(f"search: {search.method}")
    run(
        llm,
        search,
        args.set,
        args.mode,
        run_name,
        args.limit,
        args.only,
        not args.no_verify_llm,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
