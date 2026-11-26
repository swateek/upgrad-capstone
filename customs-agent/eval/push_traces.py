"""Send the official runs to Langfuse as traces, tagged so the dashboard can show them alone.

    uv run python -m eval.push_traces --dry-run              # count and show one trace, send nothing
    uv run python -m eval.push_traces                        # the headline arms (about 700 traces)
    uv run python -m eval.push_traces --all                  # every official run (about 1,200)

The official runs were made with tracing off (cache off, one request at a time); every model call,
plan, tool output and verifier check was saved in results/runs/<run>/<mode>.jsonl. This script
rebuilds one trace per question from those records with the same layout the app uses
(src/tracing.py `spans`, PII-masked), and makes NO model calls. Each trace lasts as long as the
question did in the run and each step its recorded duration, but the traces are placed at upload
time, not at the run: each one carries the run's freeze date and `replayed` in its metadata and tags.

Tags on every trace, for the Langfuse filter (Traces > Tags):
  official-run · <set> (eval-v2, eval-v3, gold-v2) · <agent> (agent-v1, agent-v2, single-rag)
  · <mode> (router, planner, single_rag) · <correct | wrong> · replayed
Session = the run directory (official-v2-eval3-router, …), so a session is one whole run.
Needs LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST in .env (as the app does).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

from eval.ablation import ARMS, RUNS

ROOT = Path(__file__).resolve().parents[1]
SET_FILES = {
    "eval-v2": ROOT / "eval" / "eval_set.jsonl",
    "eval-v3": ROOT / "eval" / "eval_set_v3.jsonl",
    "eval-v2/gold-v2": ROOT / "eval" / "eval_set_gold_v2.jsonl",
}
SET_TAG = {"eval-v2": "eval-v2", "eval-v3": "eval-v3", "eval-v2/gold-v2": "gold-v2"}
# the arms the report's headline rests on; --all adds the other planner runs, v1 on eval-v3 and gold-v2
HEADLINE = {
    "official-router",
    "official-planner-1",
    "official-single-rag",
    "official-v2-eval3-router",
    "official-v2-eval3-planner-1",
    "official-v2-eval3-single_rag",
    "official-v1-eval3-router",
}


class _Answer:
    """What src/tracing.spans needs from a pydantic answer: model_dump_json()."""

    def __init__(self, d: dict) -> None:
        self._d = d

    def model_dump_json(self) -> str:
        return json.dumps(self._d)


def as_run(rec: dict) -> SimpleNamespace:
    """A recorded answer, shaped like the AgentRun that src/tracing.spans reads."""
    return SimpleNamespace(
        answer=_Answer(rec["answer"]) if rec.get("answer") else None,
        trace=rec.get("trace") or [],
        usage=SimpleNamespace(
            steps=list(rec.get("steps") or []),
            calls=rec.get("calls"),
            tokens=rec.get("tokens"),
        ),
        reason=rec.get("reason"),
        error=rec.get("error"),
        tool_steps=rec.get("tool_steps"),
        plan_fallback=rec.get("plan_fallback"),
        retrieved_ids=rec.get("retrieved_ids") or [],
    )


def agent_tag(agent: str, mode: str) -> str:
    return "single-rag" if mode == "single_rag" else f"agent-{agent}"


def items(include_all: bool):
    """(run dir, mode, set label, agent tag, record, question, score row, freeze date)."""
    for set_, _arm, agent, mode, dirs in ARMS:
        if set_ not in SET_FILES:
            continue
        questions = {
            q["id"]: q["question"]
            for q in map(json.loads, SET_FILES[set_].read_text().splitlines())
        }
        for d in dirs:
            if not include_all and d not in HEADLINE:
                continue
            path = RUNS / d / f"{mode}.jsonl"
            if not path.exists():
                continue
            scores = {
                r["id"]: r
                for r in csv.DictReader((RUNS / d / f"scores_{mode}.csv").open())
            }
            summ = json.loads((RUNS / d / f"summary_{mode}.json").read_text())
            frozen = (summ.get("freeze") or {}).get("at")
            for line in path.read_text().splitlines():
                rec = json.loads(line)
                yield (
                    d,
                    mode,
                    set_,
                    agent_tag(agent, mode),
                    rec,
                    questions.get(rec["id"], ""),
                    scores.get(rec["id"], {}),
                    frozen,
                )


def tags_for(d: str, mode: str, set_: str, agent: str, score: dict) -> list[str]:
    ok = score.get("correct") == "True"
    return [
        "official-run",
        SET_TAG[set_],
        agent,
        mode,
        "correct" if ok else "wrong",
        "replayed",
    ]


def send(tracer, d, mode, set_, agent, rec, question, score, frozen) -> str:
    from langfuse import propagate_attributes

    from src.tracing import spans

    data = spans(question, as_run(rec), mode)
    meta = {
        **data["metadata"],
        "question_id": rec["id"],
        "question_type": score.get("type"),
        "gold_outcome": score.get("gold_outcome"),
        "correct": score.get("correct") == "True",
        "seconds_in_run": rec.get("seconds"),
        "run": d,
        "set": SET_TAG[set_],
        "freeze_at": frozen,
        "replayed": f"rebuilt from results/runs/{d}/{mode}.jsonl; durations from the run (seconds, step ms), placed at upload time",
    }
    with (
        propagate_attributes(
            session_id=d,
            trace_name=f"official · {d} · {rec['id']}",
            tags=tags_for(d, mode, set_, agent, score),
        ),
        tracer.client.start_as_current_observation(
            name=f"declare-right {rec['id']}",
            as_type="agent",
            input=data["input"],
            metadata=meta,
        ) as root,
    ):
        tracer.lay_out(root, data["children"], rec.get("seconds"))
        root.update(output=data["output"])
        return root.trace_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all",
        action="store_true",
        help="every official run, not only the headline arms",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="count and print one trace; send nothing"
    )
    ap.add_argument("--limit", type=int, help="send at most this many (a first test)")
    a = ap.parse_args()
    todo = list(items(a.all))
    runs = sorted({t[0] for t in todo})
    print(f"{len(todo)} traces from {len(runs)} runs: {', '.join(runs)}")
    if a.limit:
        todo = todo[: a.limit]
    if a.dry_run:
        from src.tracing import spans

        d, mode, set_, agent, rec, q, score, _frozen = todo[0]
        print("tags:", tags_for(d, mode, set_, agent, score))
        print(json.dumps(spans(q, as_run(rec), mode), indent=1, default=str)[:3000])
        return
    from src.endpoints import load_env
    from src.tracing import LangfuseTracer

    load_env()
    tracer = LangfuseTracer()
    for i, t in enumerate(todo, 1):
        send(tracer, *t)
        if i % 50 == 0:
            tracer.flush()
            print(f"  {i}/{len(todo)}", flush=True)
    tracer.flush()
    print(
        f"sent {len(todo)} traces. In Langfuse: Traces, filter Tags = official-run (and eval-v3, agent-v2, …)."
    )


if __name__ == "__main__":
    main()
