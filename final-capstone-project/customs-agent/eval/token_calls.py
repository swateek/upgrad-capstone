"""Tokens per model call, by stage, from the official runs (mentor plan section 6: "tokens per
call distribution").

    uv run python eval/token_calls.py      # -> results/token_calls.csv, docs/TOKENS.md

Each record's `steps` holds one entry per model call with the endpoint's `total_tokens`
(input + output). The endpoint allows 8,192 tokens per call; the design targets under 3,000
input per call and 12,000 tokens per question (CLAUDE.md). Same arms as eval/ablation.py.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from eval.ablation import ARMS, RUNS, SETS

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "results" / "token_calls.csv"
OUT_MD = ROOT / "docs" / "TOKENS.md"
CALL_LIMIT = 8192
QUESTION_BUDGET = 12000
STAGE_ORDER = ("intake", "planner", "writer", "verifier", "single_rag")


def quantile(values: list[int], q: float) -> int:
    """Nearest-rank quantile (no interpolation), so every value is a real call."""
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, -(-int(q * 100) * len(s) // 100) - 1))
    return s[k]


def stage_of(name: str) -> str:
    return name.removesuffix("_repair")


def arm_tokens(mode: str, dirs: list[str]) -> tuple[dict[str, list[int]], list[int]]:
    by_stage: dict[str, list[int]] = defaultdict(list)
    per_q: list[int] = []
    for d in dirs:
        for line in (RUNS / d / f"{mode}.jsonl").read_text().splitlines():
            r = json.loads(line)
            per_q.append(int(r.get("tokens") or 0))
            for s in r.get("steps") or []:
                if s.get("tokens") is not None:
                    by_stage[stage_of(s.get("stage", "?"))].append(int(s["tokens"]))
    return by_stage, per_q


def build() -> list[dict]:
    rows = []
    for set_, arm, _agent, mode, dirs in ARMS:
        if not all((RUNS / d / f"{mode}.jsonl").exists() for d in dirs):
            continue
        by_stage, per_q = arm_tokens(mode, dirs)
        stages = sorted(by_stage, key=lambda s: (STAGE_ORDER + (s,)).index(s))
        every = [t for s in stages for t in by_stage[s]]
        for st in [*stages, "all calls"]:
            v = every if st == "all calls" else by_stage[st]
            if not v:
                continue
            rows.append(
                {
                    "set": set_,
                    "arm": arm,
                    "runs": len(dirs),
                    "stage": st,
                    "calls": len(v),
                    "p50": quantile(v, 0.50),
                    "p95": quantile(v, 0.95),
                    "max": max(v),
                    "over_3000": sum(1 for t in v if t > 3000),
                    "over_limit": sum(1 for t in v if t > CALL_LIMIT),
                    "question_max": max(per_q) if per_q else 0,
                    "questions_over_budget": sum(
                        1 for t in per_q if t > QUESTION_BUDGET
                    ),
                }
            )
    return rows


def write(rows: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [
        "# Tokens per model call",
        "",
        (
            "Built by `eval/token_calls.py` from the official runs (`results/runs/*/<mode>.jsonl`, the "
            "`steps` of each record). Tokens are the endpoint's `total_tokens` for the call, input plus "
            f"output. Limits: {CALL_LIMIT:,} per call (endpoint), {QUESTION_BUDGET:,} per question "
            "(design budget); target under 3,000 input per call. Planner arms pool their three runs."
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
            "| Arm | Stage | Calls | p50 | p95 | Max | Calls over 3,000 | Over the call limit |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in sub:
            lines.append(
                f"| {r['arm']} | {r['stage']} | {r['calls']} | {r['p50']:,} | {r['p95']:,} | "
                f"{r['max']:,} | {r['over_3000']} | {r['over_limit']} |"
            )
        seen = []
        lines += ["", "Largest question (all calls together):", ""]
        for r in sub:
            if r["arm"] in seen:
                continue
            seen.append(r["arm"])
            lines.append(
                f"- {r['arm']}: {r['question_max']:,} tokens; "
                f"{r['questions_over_budget']} questions over {QUESTION_BUDGET:,}."
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    rows = build()
    write(rows)
    print(
        f"{len(rows)} rows -> {OUT_CSV.relative_to(ROOT)}, {OUT_MD.relative_to(ROOT)}"
    )
