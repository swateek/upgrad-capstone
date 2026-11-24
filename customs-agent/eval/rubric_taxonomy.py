"""Our failure labels mapped onto the rubric's four kinds (Track B, item V: "a failure taxonomy
separating retrieval miss, reasoning error, tool-call error and hallucination").

    uv run python -m eval.rubric_taxonomy      # -> results/failures_rubric.csv, prints the table

Our labels (docs/TAXONOMY.md) are finer: they name the first pipeline stage that went wrong. Two
more groups are kept apart because they are not answer-quality failures: safety/scope (a request
that should or should not have been refused) and "not a system failure" (gold error, scorer).
Final labels: the hand label where both reviewers agree, else the rules' label (as in Figure 3).
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs"
OUT = ROOT / "results" / "failures_rubric.csv"

RUBRIC = {
    # the model misread or the decision logic misjudged what the question says
    "EXTRACT_MISSED": "reasoning error",
    "EXTRACT_WRONG": "reasoning error",
    "CLARIFY_LOGIC": "reasoning error",
    "DEFAULTS": "reasoning error",
    "CARRYOVER": "reasoning error",
    # something not in the question or the tools was asserted
    "EXTRACT_INVENTED": "hallucination",
    "WRITER": "hallucination",
    "WRITER_CLAIM": "hallucination",
    # the right clause was not in front of the writer, or the wrong one was cited
    "RETRIEVAL_MISS": "retrieval miss",
    "CITATION_SELECTION": "retrieval miss",
    # a tool, its arguments, the structured output or the plan went wrong
    "UNITS": "tool-call error",
    "RULES": "tool-call error",
    "PLAN": "tool-call error",
    "INTAKE_JSON": "tool-call error",
    "BUDGET": "tool-call error",
    "VERIFIER_FALSE_ALARM": "tool-call error",
    # not answer quality
    "GUARD_MISS": "safety / scope",
    "GUARD_FALSE_REFUSAL": "safety / scope",
    "INTENT": "safety / scope",
    "GOLD_ERROR": "not a system failure",
    "SCORER": "not a system failure",
    "INFRA": "not a system failure",
    "CRASH": "tool-call error",
}
ORDER = [
    "reasoning error",
    "hallucination",
    "retrieval miss",
    "tool-call error",
    "safety / scope",
    "not a system failure",
]
ARMS = [
    ("eval-v2", "agent v1", "official-router/failures_router.csv"),
    ("eval-v3", "agent v1", "official-v1-eval3-router/failures_router.csv"),
    ("eval-v3", "agent v2", "official-v2-eval3-router/failures_router.csv"),
]


def final_label(row: dict) -> str:
    h1, h2 = row.get("human_label", ""), row.get("human_label_2", "")
    return h1 if h1 and h1 == h2 else row["label"]


def counts(path: Path) -> tuple[Counter, Counter]:
    kinds, labels = Counter(), Counter()
    for r in csv.DictReader(path.open()):
        lab = final_label(r)
        labels[lab] += 1
        kinds[RUBRIC.get(lab, "unmapped")] += 1
    return kinds, labels


def main() -> None:
    rows = []
    for set_, agent, rel in ARMS:
        kinds, labels = counts(RUNS / rel)
        assert "unmapped" not in kinds, labels
        rows.append(
            {
                "set": set_,
                "agent": agent,
                "wrong": sum(kinds.values()),
                **{k: kinds[k] for k in ORDER},
            }
        )
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("| Set | Agent | Wrong | " + " | ".join(k.capitalize() for k in ORDER) + " |")
    print("| --- | --- | --- | " + " | ".join("---" for _ in ORDER) + " |")
    for r in rows:
        print(
            f"| {r['set']} | {r['agent']} | {r['wrong']} | "
            + " | ".join(str(r[k]) for k in ORDER)
            + " |"
        )
    print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
