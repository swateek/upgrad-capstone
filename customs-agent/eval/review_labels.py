"""The owner's hand check of the failure labels (Day 11; docs/TAXONOMY.md).

    uv run python eval/review_labels.py          # -> eval/REVIEW_LABELS.md
    uv run python eval/review_labels.py --apply eval/label_verdicts.yaml

Part 1: every wrong answer of agent v2 on eval-v3 (the headline; the router run, whose 23 are
the same as each planner run's). Part 2: every unsafe wrong answer of agent v1 on eval-v2
(planner run 1). For each: the question, gold, what the agent did, and the proposed label.

The verdicts go in eval/label_verdicts.yaml (one block per reviewer: id -> agree, or the right
label, with a note); --apply writes them into the failures CSVs (human_label/_note for reviewer 1,
human_label_2/_note_2 for reviewer 2, label_reviewed = the rules' label they saw), after which
`eval/label_failures.py <csv> --agreement` gives rules vs each reviewer and reviewer vs reviewer.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "REVIEW_LABELS.md"
# found while building the sheet: the owner decides
NOTES = {
    "E3-019": (
        "Possible GOLD_ERROR: the gold taxes this 15.5% wine at the over-16% rate ($1.57/gal, the "
        "generator's excise class, taken as given by build_v3.py). Still wine of not more than 16% "
        "is $1.07/gal (TTB), which gives the agent's $1.10 (duty $0.96 + excise $0.14). The only "
        "excise class in eval-v3 and dev-v2 that disagrees with its ABV."
    ),
}
PARTS = [
    (
        "Part 1: agent v2 on eval-v3 (every wrong answer)",
        ROOT / "results/runs/official-v2-eval3-router",
        "router",
        ROOT / "eval/eval_set_v3.jsonl",
        None,
    ),
    (
        "Part 2: agent v1 on eval-v2 (every unsafe wrong answer)",
        ROOT / "results/runs/official-planner-1",
        "planner",
        ROOT / "eval/eval_set.jsonl",
        "unsafe",
    ),
]


def gold_text(g: dict) -> str:
    out = [g["outcome"]]
    if g.get("reason"):
        out.append(f"({g['reason']})")
    if g.get("bottom_line"):
        out.append(str([b["type"] for b in g["bottom_line"]]))
    if g.get("total_usd") is not None:
        out.append(f"${g['total_usd']:.2f}")
    if g.get("clarify_facts"):
        out.append(f"asks {g['clarify_facts']}")
    if g.get("whatif"):
        out.append(f"what-if {g['whatif']}")
    return " ".join(out)


def got_text(rec: dict) -> str:
    a = rec.get("answer") or {}
    out = [a.get("outcome") or "none"]
    if rec.get("reason"):
        out.append(f"({rec['reason']})")
    if a.get("bottom_line"):
        out.append(str([b["type"] for b in a["bottom_line"]]))
    if a.get("total_usd") is not None:
        out.append(f"${a['total_usd']:.2f}")
    if a.get("clarify_facts"):
        out.append(f"asks {a['clarify_facts']}")
    if a.get("whatif"):
        out.append(f"what-if {a['whatif']}")
    return " ".join(out)


def build() -> None:
    doc = [
        "# Failure labels: the owner's hand check (Day 11)",
        "",
        (
            "Each wrong answer has one proposed label: the first pipeline stage that went wrong "
            "(`docs/TAXONOMY.md`). Read the question, the gold and what the agent did, and say whether "
            "the label is the root cause. For a wrong label, give the right one (labels below) and a "
            "few words. Only GOLD_ERROR, SCORER and VERIFIER_FALSE_ALARM are set by hand."
        ),
        "",
        (
            "Labels: GUARD_MISS, INTENT, EXTRACT_MISSED, EXTRACT_INVENTED, EXTRACT_WRONG, UNITS, "
            "CLARIFY_LOGIC, PLAN, RULES, RETRIEVAL_MISS, CITATION_SELECTION, WRITER, VERIFIER_FALSE_ALARM, "
            "GOLD_ERROR, SCORER, UNEXPLAINED."
        ),
        "",
    ]
    for title, run, mode, gold_path, only in PARTS:
        gold = {r["id"]: r for r in map(json.loads, gold_path.read_text().splitlines())}
        recs = {
            r["id"]: r
            for r in map(json.loads, (run / f"{mode}.jsonl").read_text().splitlines())
        }
        rows = list(csv.DictReader((run / f"failures_{mode}.csv").open()))
        if only:
            rows = [r for r in rows if r["severity"] == only]
        doc += [
            f"## {title}",
            "",
            f"Run `{run.relative_to(ROOT)}`, {len(rows)} items.",
            "",
        ]
        for r in rows:
            g = gold[r["id"]]
            doc += [
                f"### {r['id']} ({r['type']}){'  ⚠️ unsafe' if r['severity'] == 'unsafe' else ''}",
                "",
                f"> {g['question']}",
                "",
                f"- **Gold:** {gold_text(g['gold'])}",
                f"- **Agent:** {got_text(recs[r['id']])}",
                f"- **Proposed label:** `{r['label']}`: {r['detail']}",
                f"- **Evidence:** {r['evidence'][:400]}",
                *([f"- **Note:** {NOTES[r['id']]}"] if r["id"] in NOTES else []),
                "- **Your verdict:** ☐ agree ☐ disagree → label: ______  note: ______",
                "",
            ]
    OUT.write_text("\n".join(doc))
    print(f"wrote {OUT.relative_to(ROOT)}")


def apply(path: Path) -> None:
    """verdicts YAML: {reviewer_1: {part1: {id: {agree: true, note} | {label, note}}, part2: ...},
    reviewer_2: ...}. Writes human_label/_note (reviewer 1) and human_label_2/_note_2 (reviewer 2),
    and label_reviewed = the rules' label the reviewers saw (so agreement survives a rule change)."""
    v = yaml.safe_load(path.read_text())
    cols = {
        "reviewer_1": ("human_label", "human_note"),
        "reviewer_2": ("human_label_2", "human_note_2"),
    }
    for key, (_t, run, mode, _g, _o) in zip(("part1", "part2"), PARTS, strict=True):
        f = run / f"failures_{mode}.csv"
        rows = list(csv.DictReader(f.open()))
        for rev, (lc, nc) in cols.items():
            given = (v.get(rev) or {}).get(key) or {}
            for r in rows:
                x = given.get(r["id"])
                if x is None:
                    continue
                r.setdefault("label_reviewed", "")
                r["label_reviewed"] = r["label_reviewed"] or r["label"]
                r[lc] = r["label_reviewed"] if x.get("agree") else x["label"]
                r[nc] = x.get("note", "")
        fields = list(rows[0])
        for c in ("human_label_2", "human_note_2", "label_reviewed"):
            if c not in fields:
                fields.append(c)
        with f.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fields})
        print(
            f"{f.relative_to(ROOT)}: {sum(1 for r in rows if r.get('human_label'))} items checked by reviewer 1, "
            f"{sum(1 for r in rows if r.get('human_label_2'))} by reviewer 2"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", type=Path)
    args = ap.parse_args()
    apply(args.apply) if args.apply else build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
