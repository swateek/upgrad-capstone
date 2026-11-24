"""Validate every synthetic bid case against the rules in data/bid_cases/README.md.

    cd backend && uv run python ../domains/procurement/pipelines/validate_bid_cases.py

Checks per case: synthetic labels, sheet shape (weights sum to 100, marks <= weight), every
evidence string appears verbatim in the proposal prose, and the hand-written gold_scores.json
matches an independent recomputation (mandatory pass/fail/gap, rubric bands, totals, screening,
withholding, ranking). Exits 1 on any mismatch.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import yaml

DOMAIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOMAIN_DIR))
from screening import match

CASES = DOMAIN_DIR / "data" / "bid_cases"
SCREENING = DOMAIN_DIR / "data" / "screening"


def load_lists() -> list[tuple[dict[str, Any], list[dict[str, str]]]]:
    metas = []
    for name in (
        "snapshot.yaml",
        "synthetic_lists.yaml",
    ):  # generated + hand-kept synthetic
        metas += yaml.safe_load((SCREENING / name).read_text(encoding="utf-8"))["lists"]
    out = []
    for lst in metas:
        with (SCREENING / lst["file"]).open(encoding="utf-8") as fh:
            out.append((lst, list(csv.DictReader(fh))))
    return out


def read_proposal(path: Path) -> tuple[dict[str, Any], str]:
    _, front, body = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(front), body


def band_marks(value: Any, rubric: list[dict[str, Any]]) -> int:
    for band in rubric:
        if "equals" in band and value == band["equals"]:
            return band["marks"]
        if (
            "min" in band
            and isinstance(value, int | float)
            and not isinstance(value, bool)
            and value >= band["min"]
        ):
            return band["marks"]
        if (
            "max" in band
            and isinstance(value, int | float)
            and not isinstance(value, bool)
            and value <= band["max"]
        ):
            return band["marks"]
    return 0


def passes(value: Any, rule: Any) -> bool:
    if isinstance(rule, dict):
        if "min" in rule:
            return isinstance(value, int | float) and value >= rule["min"]
        if "in" in rule:
            return value in rule["in"]
    return value == rule


def screen(name: str, lists) -> dict[str, Any]:
    """Combine all lists: present if present on any; keep history/possible notes."""
    result = {
        "status": "not_present",
        "lists": [],
        "history_versions": [],
        "possible_matches": [],
    }
    for meta, rows in lists:
        r = match(name, rows)
        if r["status"] == "present":
            result["status"] = "present"
            result["lists"].append({"list": meta["id"], "snapshot_date": meta["snapshot_date"]})
        result["history_versions"] += r["history_versions"]
        result["possible_matches"] += [p["listed_name"] for p in r["possible_matches"]]
    return result


def expected(case_dir: Path, lists) -> dict[str, Any]:
    req = yaml.safe_load((case_dir / "requirements.yaml").read_text(encoding="utf-8"))
    rows, bidders = [], []
    for prop in sorted((case_dir / "proposals").glob("*.md")):
        front, _ = read_proposal(prop)
        bid, resp = front["bidder_id"], front.get("responses", {})
        failed = []
        for m in req["mandatory"]:
            r = resp.get(m["field"])
            if r is None:
                rows.append((bid, m["id"], None, "gap"))
                failed.append(m["id"])
            else:
                ok = passes(r["value"], m["pass_if"])
                rows.append((bid, m["id"], "pass" if ok else "fail", None))
                if not ok:
                    failed.append(m["id"])
        total = 0
        for s in req["scored"]:
            r = resp.get(s["field"])
            if failed:
                rows.append((bid, s["id"], None, "not evaluated"))
            elif r is None:
                rows.append((bid, s["id"], None, "no response"))
            else:
                marks = band_marks(r["value"], s["rubric"])
                total += marks
                rows.append((bid, s["id"], marks, None))
        scr = screen(front["bidder_name"], lists)
        status = (
            "non_responsive"
            if failed
            else ("withheld_screening" if scr["status"] == "present" else "responsive")
        )
        price = resp.get(req["price"]["field"])
        bidders.append(
            {
                "bidder": bid,
                "status": status,
                "technical_total": None if failed else total,
                "quoted_price_inr": price["value"] if price else None,
                "screening_status": scr["status"],
                "history_versions": scr["history_versions"],
                "possible_matches": sorted(set(scr["possible_matches"])),
                "hit_lists": scr["lists"],
            }
        )
    ranking = [
        b["bidder"]
        for b in sorted(
            (b for b in bidders if b["status"] == "responsive"),
            key=lambda b: -b["technical_total"],
        )
    ]
    withheld = [b["bidder"] for b in bidders if b["status"] == "withheld_screening"]
    return {"rows": rows, "bidders": bidders, "ranking": ranking, "withheld": withheld}


def check_case(case_dir: Path, lists) -> list[str]:
    errs: list[str] = []
    case = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
    if case.get("synthetic") is not True:
        errs.append("case.yaml must say synthetic: true")
    props = sorted((case_dir / "proposals").glob("*.md"))
    if len(props) != 3:
        errs.append(f"expected 3 proposals, found {len(props)}")
    for prop in props:
        front, body = read_proposal(prop)
        if front.get("synthetic") is not True:
            errs.append(f"{prop.name}: synthetic: true missing")
        if "SYNTHETIC" not in body:
            errs.append(f"{prop.name}: prose must carry a SYNTHETIC label")
        for field, r in (front.get("responses") or {}).items():
            if r.get("evidence") and r["evidence"] not in body:
                errs.append(f"{prop.name}: evidence for {field} not verbatim in prose")

    if not (case_dir / "requirements.yaml").exists():
        if case.get("requirement_sheet") is not None:
            errs.append("no requirements.yaml but case.yaml names one")
        return errs  # the deliberate no-sheet case: nothing to score

    req = yaml.safe_load((case_dir / "requirements.yaml").read_text(encoding="utf-8"))
    weights = sum(s["weight"] for s in req["scored"])
    if weights != 100:
        errs.append(f"scored weights sum to {weights}, not 100")
    for s in req["scored"]:
        if any(b["marks"] > s["weight"] for b in s["rubric"]):
            errs.append(f"{s['id']}: a band gives more marks than the weight")

    gold = json.loads((case_dir / "gold_scores.json").read_text(encoding="utf-8"))
    exp = expected(case_dir, lists)
    got_rows = {(r["bidder"], r["requirement_id"]): r for r in gold["rows"]}
    for bid, rid, score, gap in exp["rows"]:
        g = got_rows.get((bid, rid))
        if g is None:
            errs.append(f"gold missing row {bid}/{rid}")
            continue
        if g["score"] != score:
            errs.append(f"{bid}/{rid}: gold score {g['score']!r}, expected {score!r}")
        if (gap is None) != (g["gap"] is None) or (gap and gap not in (g["gap"] or "")):
            errs.append(f"{bid}/{rid}: gold gap {g['gap']!r}, expected {gap!r}")
    if len(got_rows) != len(exp["rows"]):
        errs.append(f"gold has {len(got_rows)} rows, expected {len(exp['rows'])}")
    gb = {b["bidder"]: b for b in gold["bidders"]}
    for b in exp["bidders"]:
        g = gb.get(b["bidder"], {})
        for k in ("status", "technical_total", "quoted_price_inr"):
            if g.get(k) != b[k]:
                errs.append(f"{b['bidder']}: gold {k}={g.get(k)!r}, expected {b[k]!r}")
        gs = g.get("screening", {})
        if gs.get("status") != b["screening_status"]:
            errs.append(f"{b['bidder']}: gold screening status differs from screen()")
        if sorted(gs.get("history_versions", [])) != sorted(b["history_versions"]):
            errs.append(
                f"{b['bidder']}: history_versions {gs.get('history_versions')} != {b['history_versions']}"
            )
        if sorted(set(gs.get("possible_matches", []))) != b["possible_matches"]:
            errs.append(
                f"{b['bidder']}: possible_matches {gs.get('possible_matches')} != {b['possible_matches']}"
            )
        if b["status"] == "withheld_screening":
            w = next(
                (x for x in gold.get("withheld_bidders", []) if x["bidder"] == b["bidder"]),
                {},
            )
            hit = b["hit_lists"][0] if b["hit_lists"] else {}
            if w.get("list") != hit.get("list") or w.get("snapshot_date") != hit.get(
                "snapshot_date"
            ):
                errs.append(
                    f"{b['bidder']}: withheld list/date {w.get('list')}/{w.get('snapshot_date')} != {hit}"
                )
    if gold.get("ranking_eligible") != exp["ranking"]:
        errs.append(f"ranking {gold.get('ranking_eligible')} != expected {exp['ranking']}")
    if sorted(w["bidder"] for w in gold.get("withheld_bidders", [])) != sorted(exp["withheld"]):
        errs.append(f"withheld {gold.get('withheld_bidders')} != expected {exp['withheld']}")
    totals = [b["technical_total"] for b in exp["bidders"] if b["status"] == "responsive"]
    if len(totals) != len(set(totals)):
        errs.append("tie in technical totals; cases are designed without ties")
    return errs


def main() -> int:
    lists = load_lists()
    bad = 0
    for case_dir in sorted(p for p in CASES.iterdir() if p.is_dir()):
        errs = check_case(case_dir, lists)
        print(f"{'ok  ' if not errs else 'FAIL'} {case_dir.name}")
        for e in errs:
            print(f"     - {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
