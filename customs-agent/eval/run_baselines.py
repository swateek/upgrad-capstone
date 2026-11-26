"""Run the Day-4 prompting baselines and score them.

    uv run python eval/run_baselines.py --set dev --run-name day4-dev            # tune here
    uv run python eval/run_baselines.py --set dev --strategies closed_book --limit 3
    LLM_CACHE=0 uv run python eval/run_baselines.py --set eval --run-name week1  # official: overnight, cache off

Writes results/runs/<run>/<strategy>.jsonl (answers, resumable), results/runs/<run>/scores_<strategy>.csv
and summary.json. With --set eval it also writes results/week1_strategies.csv (one row per strategy)
and results/week1_failures.csv (one row per wrong item). Few-shot examples come from the dev set, so
on --set dev those four items are not scored for fewshot_json.
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
from src.baselines.prompts import FEWSHOT_IDS
from src.baselines.strategies import STRATEGIES, run_strategy, to_record

SETS = {
    "dev": ROOT / "eval" / "dev_set.jsonl",
    "eval": ROOT / "eval" / "eval_set.jsonl",
}
RESULTS = ROOT / "results"


def run(
    llm,
    set_name: str,
    strategies: list[str],
    run_name: str,
    limit: int | None = None,
    results: Path = RESULTS,
) -> dict[str, dict]:
    gold = load_jsonl(SETS[set_name])[:limit] if limit else load_jsonl(SETS[set_name])
    out_dir = results / "runs" / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, dict] = {}
    failures: list[dict] = []
    for strat in strategies:
        path = out_dir / f"{strat}.jsonl"
        done = {r["id"] for r in load_jsonl(path)} if path.exists() else set()
        skip = FEWSHOT_IDS if (strat == "fewshot_json" and set_name == "dev") else set()
        with path.open("a") as fh:
            for item in gold:
                if item["id"] in done or item["id"] in skip:
                    continue
                t0 = time.perf_counter()
                rec = to_record(
                    item["id"], strat, run_strategy(strat, llm, item["question"])
                )
                rec["seconds"] = round(time.perf_counter() - t0, 1)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                status = (
                    "ERROR " + rec["error"][:80]
                    if rec["error"]
                    else rec["answer"]["outcome"]
                )
                print(
                    f"[{strat}] {item['id']} {status}  ({rec['calls']} calls, {rec['tokens']} tok, {rec['seconds']} s)"
                )
        rows = score(gold, load_jsonl(path), skip=skip)
        write_csv(out_dir / f"scores_{strat}.csv", rows)
        summaries[strat] = {**summary(rows), "by_type": by_type(rows)}
        for r in rows:
            if not r["correct"]:
                failed = [
                    k
                    for k in (
                        "outcome",
                        "bottom_line",
                        "dollars",
                        "whatif",
                        "clarify",
                        "citations",
                        "must_not",
                    )
                    if r.get(k) is False
                ]
                failures.append(
                    {
                        "strategy": strat,
                        "id": r["id"],
                        "type": r["type"],
                        "failed": " ".join(failed),
                        "gold_outcome": r["gold_outcome"],
                        "pred_outcome": r["pred_outcome"],
                        "error": r.get("error") or "",
                    }
                )
        s = summaries[strat]
        print(
            f"== {strat}: accuracy {s['accuracy']}  outcome {s['outcome_acc']}  bottom line {s['bottom_line_acc']}  "
            f"dollars {s['dollar_acc']} (n={s['dollar_n']})  clarify {s['clarify_acc']}  citations {s['citation_acc']}  "
            f"tokens/q {s['tokens_per_q']}"
        )
    (out_dir / "summary.json").write_text(
        json.dumps(
            {"set": set_name, "run": run_name, "strategies": summaries}, indent=1
        )
    )
    if set_name == "eval":
        table = []
        for strat, s in summaries.items():
            row = {
                "strategy": strat,
                "set": "eval-v2",
                "run": run_name,
                **{k: v for k, v in s.items() if k != "by_type"},
            }
            row.update({f"acc_{t}": v for t, v in s["by_type"].items()})
            table.append(row)
        write_csv(results / "week1_strategies.csv", table)
        write_csv(results / "week1_failures.csv", failures)
        print(f"wrote {results / 'week1_strategies.csv'} and week1_failures.csv")
    return summaries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=sorted(SETS), default="dev")
    ap.add_argument(
        "--strategies", nargs="*", default=list(STRATEGIES), choices=STRATEGIES
    )
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--limit", type=int, help="first N items only (smoke test)")
    args = ap.parse_args()
    from src.llm import LLM

    run_name = args.run_name or f"day4-{args.set}"
    llm = LLM.from_env(run_name=run_name)
    print(
        f"model {llm.chat_model}, cache {'on' if llm.cache_enabled else 'OFF'}, run {run_name}"
    )
    run(llm, args.set, args.strategies, run_name, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
