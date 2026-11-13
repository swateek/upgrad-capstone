"""Procurement domain tools: screen_vendor and score_bids. Deterministic code; no model calls.

The core registers these next to its own `search_docs` (exposed here as `search_policy`).
Each tool has a Pydantic input model and returns a JSON-serialisable dict. Errors come back as
typed payloads ({"error": ..., "retryable": false}), never as exceptions into the agent graph.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from screening import match

PACK = Path(__file__).resolve().parent
SCREENING = PACK / "data" / "screening"
CASES = PACK / "data" / "bid_cases"
CASE_ID = re.compile(r"^case_\d{3}$")


# --- screen_vendor -------------------------------------------------------------------------------
class ScreenVendorInput(BaseModel):
    name: str = Field(min_length=2, max_length=200, description="Firm or brand name to screen")


@lru_cache(maxsize=1)
def _lists() -> list[tuple[dict[str, Any], list[dict[str, str]]]]:
    metas: list[dict[str, Any]] = []
    for fname in ("snapshot.yaml", "synthetic_lists.yaml"):
        metas += yaml.safe_load((SCREENING / fname).read_text(encoding="utf-8"))["lists"]
    out = []
    for m in metas:
        with (SCREENING / m["file"]).open(encoding="utf-8") as fh:
            out.append((m, list(csv.DictReader(fh))))
    return out


def screen_vendor(name: str) -> dict[str, Any]:
    """Look a firm or brand up in every loaded screening list (latest version decides)."""
    per_list = []
    present_on = []
    for meta, rows in _lists():
        r = match(name, rows)
        entry = {
            "list": meta["id"],
            "title": meta["title"],
            "synthetic": bool(meta.get("synthetic")),
            "snapshot_date": meta["snapshot_date"],
            "status": r["status"],
            "matches": [
                {
                    "supplier_name": m["supplier_name"],
                    "brand": m["brand"],
                    "category": m["category"],
                    "period": (
                        f"{m['period_from']} to {m['period_to']}" if m.get("period_from") else None
                    ),
                    "debarring_entity": m.get("debarring_entity") or None,
                }
                for m in r["matches"][:25]
            ],
            "matched_rows": len(r["matches"]),
            "history_versions": r["history_versions"],
            "possible_matches": r["possible_matches"],
            "source_url": meta.get("source_url"),
            "scope": meta.get("scope"),
            "disclaimer": meta.get("disclaimer"),
        }
        per_list.append(entry)
        if r["status"] == "present":
            present_on.append(entry)
    if present_on:
        statement = "; ".join(
            f"{name} is present on {e['title']} as of {e['snapshot_date']}" for e in present_on
        )
    else:
        snapshots = "; ".join(
            f"{e['title']}, snapshot dated {e['snapshot_date']}" for e in per_list
        )
        statement = (
            f"{name} is not present in any loaded list ({snapshots}). "
            "That is not a finding that the firm is eligible."
        )
    return {
        "query": name,
        "normalized_query": match(name, [])["normalized_query"],
        "status": "present" if present_on else "not_present",
        "statement": statement,
        "lists": per_list,
    }


# --- score_bids ----------------------------------------------------------------------------------
class ScoreBidsInput(BaseModel):
    case_id: str = Field(
        pattern=r"^case_\d{3}$", description="Preloaded bid case id, e.g. case_001"
    )


def _read_proposal(path: Path) -> tuple[dict[str, Any], str]:
    _, front, body = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(front), body


def _band_marks(value: Any, rubric: list[dict[str, Any]]) -> int:
    numeric = isinstance(value, int | float) and not isinstance(value, bool)
    for band in rubric:
        if "equals" in band and value == band["equals"]:
            return band["marks"]
        if "min" in band and numeric and value >= band["min"]:
            return band["marks"]
        if "max" in band and numeric and value <= band["max"]:
            return band["marks"]
    return 0


def _passes(value: Any, rule: Any) -> bool:
    if isinstance(rule, dict):
        if "min" in rule:
            return isinstance(value, int | float) and value >= rule["min"]
        if "in" in rule:
            return value in rule["in"]
    return value == rule


def list_cases() -> list[dict[str, Any]]:
    out = []
    for d in sorted(p for p in CASES.iterdir() if p.is_dir() and CASE_ID.match(p.name)):
        meta = yaml.safe_load((d / "case.yaml").read_text(encoding="utf-8"))
        out.append(
            {
                "case_id": meta["case_id"],
                "title": meta["title"],
                "procurement_type": meta["procurement_type"],
                "has_requirement_sheet": (d / "requirements.yaml").exists(),
            }
        )
    return out


def score_bids(case_id: str) -> dict[str, Any]:
    """Draft score sheet for a preloaded case, computed from its stored evaluation sheet."""
    case_dir = CASES / case_id
    if not CASE_ID.match(case_id) or not case_dir.is_dir():
        return {"error": f"No bid case '{case_id}' is preloaded.", "retryable": False}
    if not (case_dir / "requirements.yaml").exists():
        return {
            "error": "No requirement sheet is stored for this case, so it cannot be scored.",
            "refusal_rule": "R6_no_requirement_sheet",
            "case_id": case_id,
            "retryable": False,
        }
    req = yaml.safe_load((case_dir / "requirements.yaml").read_text(encoding="utf-8"))
    case = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    bidders: list[dict[str, Any]] = []
    for prop in sorted((case_dir / "proposals").glob("*.md")):
        front, _ = _read_proposal(prop)
        bid, resp = front["bidder_id"], front.get("responses") or {}
        failed: list[str] = []
        for m in req["mandatory"]:
            r = resp.get(m["field"])
            if r is None:
                failed.append(m["id"])
                rows.append(
                    _row(bid, m, "mandatory", None, None, "no response to a mandatory condition")
                )
                continue
            ok = _passes(r["value"], m["pass_if"])
            if not ok:
                failed.append(m["id"])
            rows.append(
                _row(bid, m, "mandatory", r.get("evidence"), "pass" if ok else "fail", None)
            )
        total = 0
        for s in req["scored"]:
            r = resp.get(s["field"])
            if failed:
                gap = f"not evaluated: non-responsive ({', '.join(failed)})"
                rows.append(_row(bid, s, "scored", None, None, gap))
            elif r is None:
                rows.append(_row(bid, s, "scored", None, None, "no response"))
            else:
                marks = _band_marks(r["value"], s["rubric"])
                total += marks
                rows.append(_row(bid, s, "scored", r.get("evidence"), marks, None))
        screening = screen_vendor(front["bidder_name"])
        hits = [e for e in screening["lists"] if e["status"] == "present"]
        price = resp.get(req["price"]["field"])
        status = "non_responsive" if failed else ("withheld_screening" if hits else "responsive")
        bidders.append(
            {
                "bidder": bid,
                "name": front["bidder_name"],
                "status": status,
                "failed_mandatory": failed,
                "technical_total": None if failed else total,
                "quoted_price_inr": price["value"] if price else None,
                "price_gap": None if price else "no price quoted",
                "screening": {
                    "status": screening["status"],
                    "statement": screening["statement"],
                    "hits": [
                        {
                            "list": e["list"],
                            "snapshot_date": e["snapshot_date"],
                            "synthetic": e["synthetic"],
                        }
                        for e in hits
                    ],
                    "history_versions": sorted(
                        {v for e in screening["lists"] for v in e["history_versions"]}, reverse=True
                    ),
                    "possible_matches": sorted(
                        {
                            p["listed_name"]
                            for e in screening["lists"]
                            for p in e["possible_matches"]
                        }
                    ),
                },
            }
        )
    eligible = sorted(
        (b for b in bidders if b["status"] == "responsive"), key=lambda b: -b["technical_total"]
    )
    return {
        "case_id": case_id,
        "title": case["title"],
        "synthetic": True,
        "is_draft": True,
        "draft_notice": "DRAFT score sheet for the evaluation committee. Not an award.",
        "weights_total": sum(s["weight"] for s in req["scored"]),
        "rows": rows,
        "bidders": bidders,
        "ranking_eligible": [b["bidder"] for b in eligible],
        "withheld_bidders": [
            {"bidder": b["bidder"], "name": b["name"], "hits": b["screening"]["hits"]}
            for b in bidders
            if b["status"] == "withheld_screening"
        ],
    }


def _row(bid: str, item: dict, kind: str, evidence: Any, score: Any, gap: str | None) -> dict:
    return {
        "bidder": bid,
        "requirement_id": item["id"],
        "requirement": item["text"],
        "kind": kind,
        "weight": item.get("weight"),
        "quoted_evidence": evidence,
        "score": score,
        "gap": gap,
    }


# --- registration ----------------------------------------------------------------------------------
TOOLS = {
    "screen_vendor": {
        "fn": screen_vendor,
        "input": ScreenVendorInput,
        "description": "Check a firm or brand name against the dated screening lists. Matching is "
        "done in code; absence is not eligibility.",
        "ui_mode": "vendor",
    },
    "score_bids": {
        "fn": score_bids,
        "input": ScoreBidsInput,
        "description": "Draft score sheet for a preloaded bid case from its stored evaluation "
        "sheet. Never an award.",
        "ui_mode": "bid",
    },
}
LISTINGS = {"bid-cases": list_cases}
