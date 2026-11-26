"""Structured-output reliability in the official runs: JSON repairs, plan repairs, writer retries.

    uv run python -m eval.reliability      # -> results/reliability.csv, docs/RELIABILITY.md

The rubric calls constrained decoding, JSON schema validation and retry logic the core of Track B.
Every model call that must return JSON uses `json_schema` output and Pydantic validation, with up
to 2 repairs (the validation error fed back; src/agent/llm_json.py). Read from each record:

- `steps`: one entry per model call; `attempt` > 0 is a JSON repair of that stage.
- `trace` planner entries: the validator's errors on each proposed plan; a second entry is the
  repair; `fallback` means the code router's plan was used.
- `trace` verifier entries: more than one means the writer was retried with the verifier's
  problems; an entry with attempt "pruned" means unsupported sentences were removed.
- `error` with "invalid JSON": a stage still invalid after 2 repairs.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from eval.ablation import ARMS, RUNS, SETS

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "results" / "reliability.csv"
OUT_MD = ROOT / "docs" / "RELIABILITY.md"
STAGES = ("intake", "planner", "writer", "verifier")


def arm_reliability(mode: str, dirs: list[str]) -> dict:
    calls: Counter = Counter()
    repairs: Counter = Counter()
    plan_errors: Counter = Counter()
    out = Counter()
    for d in dirs:
        for line in (RUNS / d / f"{mode}.jsonl").read_text().splitlines():
            r = json.loads(line)
            out["questions"] += 1
            for s in r.get("steps") or []:
                st = str(s.get("stage", "?")).removesuffix("_repair")
                calls[st] += 1
                if str(s.get("attempt")) not in ("0", "None"):
                    repairs[st] += 1
            if r.get("error") and "invalid JSON" in str(r["error"]):
                out["json_unrecovered"] += 1
            trace = r.get("trace") or []
            plans = [
                t for t in trace if t.get("step") == "planner" and "fallback" not in t
            ]
            if plans:
                out["planned"] += 1
                bad = plans[0].get("errors") or plans[0].get("error")
                if bad:
                    out["first_plan_invalid"] += 1
                    for e in plans[0].get("errors") or [plans[0].get("error")]:
                        plan_errors[str(e).split(":")[0].split(" [")[0][:70]] += 1
                    last = plans[-1]
                    if len(plans) > 1 and not (last.get("errors") or last.get("error")):
                        out["plan_fixed_by_repair"] += 1
            if any(t.get("step") == "planner" and t.get("fallback") for t in trace):
                out["plan_fallback"] += 1
            ver = [t for t in trace if t.get("step") == "verifier"]
            if sum(1 for t in ver if t.get("attempt") != "pruned") > 1:
                out["writer_retried"] += 1
            if any(t.get("attempt") == "pruned" for t in trace):
                out["pruned"] += 1
            if r.get("reason") == "verifier_failed":
                out["verifier_escalated"] += 1
    row = dict(out)
    for st in STAGES:
        if calls[st]:
            row[f"{st}_calls"] = calls[st]
            row[f"{st}_json_repairs"] = repairs[st]
    row["json_calls"] = sum(calls.values())
    row["json_repairs"] = sum(repairs.values())
    row["top_plan_errors"] = "; ".join(
        f"{n} × {e}" for e, n in plan_errors.most_common(3)
    )
    return row


def build() -> list[dict]:
    rows = []
    for set_, arm, _agent, mode, dirs in ARMS:
        if mode == "single_rag" or not all(
            (RUNS / d / f"{mode}.jsonl").exists() for d in dirs
        ):
            continue
        rows.append(
            {"set": set_, "arm": arm, "runs": len(dirs), **arm_reliability(mode, dirs)}
        )
    return rows


def write(rows: list[dict]) -> None:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    g = lambda r, k: r.get(k, 0)
    lines = [
        "# Structured-output reliability",
        "",
        (
            "Built by `eval/reliability.py` from the official runs (planner arms pool their three "
            "runs). JSON stages use `json_schema` output, Pydantic validation and up to 2 repairs; "
            "plans are checked by the validator, repaired once, else replaced by the router's plan."
        ),
        "",
    ]
    for set_, title in SETS.items():
        sub = [r for r in rows if r["set"] == set_]
        if not sub:
            continue
        lines += [
            f"## {title}",
            "",
            "| Arm | Questions | Model calls | JSON repairs | Still invalid | Planned | First plan invalid | Fixed by one repair | Fallbacks | Writer retried | Sentences pruned | Verifier escalations |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in sub:
            planned = g(r, "planned")
            lines.append(
                f"| {r['arm']} | {r['questions']} | {r['json_calls']} | {r['json_repairs']} | "
                f"{g(r, 'json_unrecovered')} | {planned or '–'} | "
                f"{g(r, 'first_plan_invalid') if planned else '–'} | "
                f"{g(r, 'plan_fixed_by_repair') if planned else '–'} | "
                f"{g(r, 'plan_fallback') if planned else '–'} | {g(r, 'writer_retried')} | "
                f"{g(r, 'pruned')} | {g(r, 'verifier_escalated')} |"
            )
        tops = [
            f"- {r['arm']}: {r['top_plan_errors']}"
            for r in sub
            if r.get("top_plan_errors")
        ]
        if tops:
            lines += ["", "Most common reasons a first plan was invalid:", "", *tops]
        lines.append("")
    OUT_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    rows = build()
    write(rows)
    print(
        f"{len(rows)} arms -> {OUT_CSV.relative_to(ROOT)}, {OUT_MD.relative_to(ROOT)}"
    )
