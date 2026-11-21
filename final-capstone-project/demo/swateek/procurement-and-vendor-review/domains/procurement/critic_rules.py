"""Procurement-specific critic checks. Called by the core critic with the draft and every
tool payload of the run; returns a list of problems (empty = pass). Deterministic only."""

from __future__ import annotations

import re
from typing import Any

RECOMMEND = re.compile(
    r"\b(recommend|recommended|award|select|rank(?:s|ed)? first|top[- ]ranked|preferred)\b",
    re.IGNORECASE,
)
NEGATED = re.compile(r"\b(not|cannot|can't|never|withheld|excluded|no)\b", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
# How an answer may name each screening list (any one is enough). Lives here because the list
# metadata files are frozen with the eval set.
LIST_MENTIONS = {
    "gem_delisted_sellers": ["GeM"],
    "synthetic_buyer_debarment": ["buyer-specific", "Directorate of Estates"],
}


def _names_list(draft: str, list_id: str) -> bool:
    words = LIST_MENTIONS.get(list_id, [list_id])
    return any(w.lower() in draft.lower() for w in words)


def _date_forms(iso: str) -> list[str]:
    y, m, d = iso.split("-")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    full = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    mi = int(m) - 1
    return [
        iso,
        f"{d}-{months[mi]}-{y}",
        f"{int(d)} {full[mi]} {y}",
        f"{int(d)} {months[mi]} {y}",
        f"{full[mi]} {int(d)}, {y}",
        f"{d}.{m}.{y}",
        f"{d}/{m}/{y}",
    ]


def check(draft: str, payloads: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    low = draft.lower()
    for p in payloads:
        result = p["result"]
        if "error" in result:
            continue
        if p["tool"] == "screen_vendor":
            dates = {e["snapshot_date"] for e in result["lists"]}
            if not any(form.lower() in low for d in dates for form in _date_forms(d)):
                problems.append(
                    "A screening answer must state the snapshot date of the list "
                    f"({', '.join(sorted(dates))})."
                )
            for e in result["lists"]:
                if e.get("status") == "present" and not _names_list(draft, e.get("list", "")):
                    problems.append(
                        f"Name the list the firm is on ({e.get('title', e.get('list'))})."
                    )
            if result["status"] == "not_present" and re.search(r"\b(is|are) eligible\b", low):
                problems.append(
                    "Absence from a snapshot is not eligibility; do not say the firm is eligible."
                )
        if p["tool"] == "score_bids":
            if "draft" not in low:
                problems.append(
                    "A bid score answer must say it is a draft for the committee, not an award."
                )
            missing = [
                f"{b['bidder']} ({b['technical_total']})"
                for b in result["bidders"]
                if b["technical_total"] is not None
                and not re.search(rf"\b{b['technical_total']}\b", draft)
            ]
            if missing:
                problems.append(
                    "Report each bidder's technical total from the score sheet; missing: "
                    + ", ".join(missing)
                    + "."
                )
            for w in result["withheld_bidders"]:
                for hit in w.get("hits", []):
                    if not _names_list(draft, hit["list"]):
                        problems.append(
                            f"Say which list {w['bidder']} is on ({hit['list']}, "
                            f"as of {hit['snapshot_date']})."
                        )
                names = [w["bidder"], w["name"]]
                for sent in SENTENCE.split(draft):
                    if (
                        any(n.lower() in sent.lower() for n in names)
                        and RECOMMEND.search(sent)
                        and not NEGATED.search(sent)
                    ):
                        problems.append(
                            f"{w['bidder']} ({w['name']}) is withheld after screening "
                            "and must not be recommended or ranked."
                        )
                        break
    return problems
