"""Build eval/conversations.jsonl from eval/conversations.yaml (multi-turn dev set, Days 8-9).

Dollar gold for every answered turn comes from the same spreadsheet formulas as the eval set
(eval/build_eval.py), in a separate workbook eval/conv_gold.xlsx, never from src/tools (rule 5).

    uv run python eval/build_conversations.py workbook   # conversations.yaml -> conv_gold.xlsx (formulas)
    #   recalculate: soffice --headless --convert-to xlsx --outdir /tmp eval/conv_gold.xlsx && cp /tmp/conv_gold.xlsx eval/
    uv run python eval/build_conversations.py export     # conv_gold.xlsx values -> conversations.jsonl
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from eval import build_eval as B

SOURCE = HERE / "conversations.yaml"
WORKBOOK = HERE / "conv_gold.xlsx"
OUT = HERE / "conversations.jsonl"
OUTCOMES = {"answered", "clarify", "refused", "escalated"}


def load() -> list[dict]:
    convs = yaml.safe_load(SOURCE.read_text())["conversations"]
    seen = set()
    for c in convs:
        if c["id"] in seen:
            raise SystemExit(f"duplicate id {c['id']}")
        seen.add(c["id"])
        for n, t in enumerate(c["turns"], 1):
            if ("user" in t) == ("edit" in t):
                raise SystemExit(f"{c['id']} turn {n}: give exactly one of user / edit")
            g = t["gold"]
            if g["outcome"] not in OUTCOMES:
                raise SystemExit(f"{c['id']} turn {n}: unknown outcome {g['outcome']}")
            if g["outcome"] == "answered" and "state" not in t:
                raise SystemExit(f"{c['id']} turn {n}: an answered turn needs a state")
            if g["outcome"] == "clarify" and not g.get("clarify_facts"):
                raise SystemExit(
                    f"{c['id']} turn {n}: a clarify turn needs clarify_facts"
                )
    return convs


def text(t: dict) -> str:
    return (
        t["user"]
        if "user" in t
        else f"[edit] {t['edit']['field']} = {t['edit']['value']}"
    )


def scenarios(convs: list[dict]) -> list[dict]:
    """One build_eval scenario per answered turn (state + gold), for the gold workbook."""
    out = []
    for c in convs:
        history: list[str] = []
        for n, t in enumerate(c["turns"], 1):
            history.append(text(t))
            if "state" not in t:
                continue
            gold = {k: v for k, v in t["gold"].items() if k != "assumptions"}
            out.append(
                {
                    "id": f"{c['id']}-t{n}",
                    "set": "dev",  # build_eval's internal set name; written to conversations.jsonl only
                    "type": c["type"],
                    "question": " / ".join(history),
                    "profile": t["state"].get("profile", {}),
                    "basket": t["state"].get("basket", []),
                    "gold": gold,
                }
            )
    return out


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("workbook", "export"):
        raise SystemExit(__doc__)
    convs = load()
    items = scenarios(convs)
    B.WORKBOOK = WORKBOOK
    if sys.argv[1] == "workbook":
        B.build_workbook(items)
        print(
            f"wrote {WORKBOOK.name}: {len(items)} answered turns; recalculate it, then export"
        )
        return
    with tempfile.TemporaryDirectory() as tmp:
        B.OUT = {"dev": Path(tmp) / "turns.jsonl"}
        B.write_markdown = lambda *a, **k: None
        B.export(items)
        golds = {
            r["id"]: r
            for r in (json.loads(x) for x in B.OUT["dev"].read_text().splitlines())
        }
    recs = []
    for c in convs:
        turns = []
        for n, t in enumerate(c["turns"], 1):
            g = dict(t["gold"])
            rec = {"turn": n, "gold": g}
            if "user" in t:
                rec["user"] = t["user"]
            else:
                rec["edit"] = t["edit"]
            if "state" in t:
                computed = golds[f"{c['id']}-t{n}"]
                rec["gold"] = {
                    **computed["gold"],
                    "assumptions": g.get("assumptions", []),
                }
                rec["facts"] = computed["facts"]
            else:
                rec["gold"] = {
                    "outcome": g["outcome"],
                    "reason": g.get("reason"),
                    "clarify_facts": g.get("clarify_facts"),
                    "assumptions": g.get("assumptions", []),
                    "citations": g.get("citations", []),
                    "bottom_line": [],
                    "must_not_contain": g.get("must_not_contain", []),
                }
            turns.append(rec)
        recs.append(
            {
                "id": c["id"],
                "set": "conversation",
                "type": c["type"],
                "note": c.get("note"),
                "turns": turns,
            }
        )
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
    print(
        f"wrote {OUT.name}: {len(recs)} conversations, {sum(len(r['turns']) for r in recs)} turns"
    )


if __name__ == "__main__":
    main()
