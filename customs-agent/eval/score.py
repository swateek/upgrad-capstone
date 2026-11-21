"""Deterministic scorer: system answers vs gold (docs/SPEC.md 6).

    uv run python eval/score.py --gold eval/dev_set.jsonl --pred results/runs/<run>/closed_book.jsonl

A prediction file has one JSON object per line: {"id", "answer": {...} | null, "error", "calls",
"tokens", optional "retrieved_ids": [...]}. `answer` follows src/baselines/answer.py.

An item is correct when every check that applies to it passes:
  outcome      the four-way outcome matches
  bottom_line  answered items: the result type of every basket line, in order
  dollars      priced items: total, duty and excise each within $0.01
  whatif       what-if items: max units equal, owed within $0.01
  clarify      clarify items: exactly the gold facts are asked (order ignored)
  citations    every gold citation is cited (after normalising "19 CFR 148.33" -> 19cfr148.33);
               if the prediction lists retrieved_ids, every citation must be among them
  must_not     none of the forbidden strings appears in the answer
state_flag is reported but not part of correctness.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

TOL = 0.01 + 1e-9
CHECKS = (
    "outcome",
    "bottom_line",
    "dollars",
    "whatif",
    "clarify",
    "citations",
    "must_not",
)


def norm_cite(s: str) -> str:
    """Map a free-text citation to the corpus citation_id format."""
    t = s.strip().lower().replace("§", " ").replace(" ", " ")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"(\d+)\s*c\.?\s?f\.?\s?r\.?\s*(?:part\s*)?(\d+\.\d+[a-z]?)", t)
    if m:
        return f"{m.group(1)}cfr{m.group(2)}"
    m = re.search(r"(\d+)\s*u\.?\s?s\.?\s?c\.?\s*(?:section\s*)?(\d+[a-z]?)", t)
    if m:
        return f"{m.group(1)}usc{m.group(2)}"
    m = re.search(r"(\d{4}\.\d{2}\.\d{2})", t)
    if m and ("hts" in t or re.fullmatch(r"[\d.\s]+", t)):
        return f"htsus{m.group(1)}"
    m = re.search(r"ofac\s*(?:faq)?\s*#?\s*(\d{3,4})", t)
    if m:
        return f"ofac-faq-{m.group(1)}"
    if "ttb" in t and ("rate" in t or "tax" in t):
        return "ttb-tax-rates"
    return re.sub(r"[^a-z0-9.\-]+", "-", t).strip("-")


def _contains(text: str, s: str) -> bool:
    """Whole-token match, so a forbidden "$0" does not match "$0.90"."""
    return (
        re.search(rf"(?<!\w){re.escape(s.lower())}(?!\w|[.,]\d)", text.lower())
        is not None
    )


def score_item(gold_rec: dict, pred: dict | None) -> dict:
    g = gold_rec["gold"]
    a = (pred or {}).get("answer")
    row: dict = {
        "id": gold_rec["id"],
        "type": gold_rec["type"],
        "gold_outcome": g["outcome"],
        "pred_outcome": a.get("outcome") if a else None,
        "error": (pred or {}).get("error")
        or ("no prediction" if pred is None else None),
    }
    checks: dict[str, bool | None] = dict.fromkeys(CHECKS)
    if not a:
        for k in CHECKS:
            checks[k] = False
        row.update(checks, correct=False, state_flag_ok=None)
        return row

    checks["outcome"] = a.get("outcome") == g["outcome"]
    if g["outcome"] == "answered" and g.get("bottom_line"):
        got = [
            b["type"]
            for b in sorted(a.get("bottom_line") or [], key=lambda b: b.get("line", 0))
        ]
        checks["bottom_line"] = got == [b["type"] for b in g["bottom_line"]]
    if "total_usd" in g:
        checks["dollars"] = all(
            a.get(k) is not None and abs(float(a[k]) - float(g[k])) <= TOL
            for k in ("total_usd", "duty_usd", "excise_usd")
        )
    if "whatif" in g:
        w = a.get("whatif") or {}
        checks["whatif"] = (
            w.get("max_units") == g["whatif"]["max_units"]
            and w.get("owed_usd") is not None
            and abs(float(w["owed_usd"]) - float(g["whatif"]["owed_usd"])) <= TOL
        )
    if g["outcome"] == "clarify":
        checks["clarify"] = sorted(a.get("clarify_facts") or []) == sorted(
            g.get("clarify_facts") or []
        )
    if g.get("citations"):
        cited = {norm_cite(c) for c in a.get("citations") or []}
        ok = set(g["citations"]) <= cited
        retrieved = (pred or {}).get("retrieved_ids")
        if retrieved is not None:
            ok = ok and cited <= {norm_cite(r) for r in retrieved}
        checks["citations"] = ok
    if g.get("must_not_contain"):
        text = json.dumps(a, ensure_ascii=False)
        checks["must_not"] = not any(_contains(text, s) for s in g["must_not_contain"])

    row.update(checks)
    row["correct"] = all(v for v in checks.values() if v is not None)
    row["state_flag_ok"] = (
        ((a.get("state_flag") or "").upper() == g["state_flag"])
        if g.get("state_flag")
        else None
    )
    row["calls"] = (pred or {}).get("calls")
    row["tokens"] = (pred or {}).get("tokens")
    return row


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def score(
    gold: list[dict], preds: list[dict], skip: set[str] | None = None
) -> list[dict]:
    by_id = {p["id"]: p for p in preds}
    return [
        score_item(g, by_id.get(g["id"]))
        for g in gold
        if g["id"] not in (skip or set())
    ]


def summary(rows: list[dict]) -> dict:
    n = len(rows)

    def rate(key: str) -> float | None:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    def n_of(key: str) -> int:
        return sum(1 for r in rows if r.get(key) is not None)

    tok = [r["tokens"] for r in rows if r.get("tokens")]
    calls = [r["calls"] for r in rows if r.get("calls")]
    return {
        "n": n,
        "accuracy": rate("correct"),
        "outcome_acc": rate("outcome"),
        "bottom_line_acc": rate("bottom_line"),
        "bottom_line_n": n_of("bottom_line"),
        "dollar_acc": rate("dollars"),
        "dollar_n": n_of("dollars"),
        "whatif_acc": rate("whatif"),
        "clarify_acc": rate("clarify"),
        "clarify_n": n_of("clarify"),
        "citation_acc": rate("citations"),
        "must_not_acc": rate("must_not"),
        "state_flag_acc": rate("state_flag_ok"),
        "errors": sum(1 for r in rows if r.get("error")),
        "tokens_per_q": round(sum(tok) / len(tok)) if tok else None,
        "calls_per_q": round(sum(calls) / len(calls), 2) if calls else None,
    }


def by_type(rows: list[dict]) -> dict[str, float]:
    acc: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        acc[r["type"]].append(bool(r["correct"]))
    return {t: round(sum(v) / len(v), 2) for t, v in sorted(acc.items())}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--pred", required=True, type=Path)
    ap.add_argument("--out", type=Path, help="per-item CSV")
    args = ap.parse_args()
    rows = score(load_jsonl(args.gold), load_jsonl(args.pred))
    if args.out:
        write_csv(args.out, rows)
    print(json.dumps(summary(rows), indent=1))
    print(json.dumps(by_type(rows), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
