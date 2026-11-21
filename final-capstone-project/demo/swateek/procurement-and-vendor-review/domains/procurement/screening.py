"""Firm-name normalization for vendor screening (procurement domain).

Screening is a table lookup done in code. The model never decides whether two names match.
`normalize` is used both when the snapshot is built and when `screen_vendor` runs, so both
sides of a comparison go through the same function.
"""

from __future__ import annotations

import re
import unicodedata

# Legal-form words carry no identity. Longest first so "PRIVATE LIMITED" wins over "LIMITED".
LEGAL_SUFFIXES = [
    "PRIVATELIMITED",
    "PVTLTD",
    "PRIVATE LIMITED",
    "PVT LIMITED",
    "PRIVATE LTD",
    "PVT LTD",
    "LIMITED",
    "LTD",
    "LLP",
    "INCORPORATED",
    "INC",
    "CORPORATION",
    "CORP",
    "COMPANY",
    "CO",
]
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize(name: str) -> str:
    """'Prama Hikvision India Pvt. Ltd.' -> 'PRAMA HIKVISION INDIA'."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.upper().replace("&", " AND ")
    text = _PUNCT.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if text.endswith(" " + suffix) or text == suffix:
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def compact(name: str) -> str:
    """Space-free form, for sources that lost word spacing ('PRAMAHIKVISIONINDIA')."""
    return normalize(name).replace(" ", "")


# --- matching (decided 12 Nov 2026) ------------------------------------------------------------
# present        exact normalized match on a supplier or brand in the LATEST list version
# history        exact match only in older versions -> status stays not_present
# possible match token_sort_ratio >= POSSIBLE_MATCH_MIN, or a listed brand (>= 4 chars) appears
#                as a whole word sequence in the name -> status stays not_present; human verifies
POSSIBLE_MATCH_MIN = 88


def match(name: str, rows: list[dict[str, str]]) -> dict[str, object]:
    """Screen one name against snapshot rows (dicts as in the screening CSV)."""
    from rapidfuzz import fuzz

    query = normalize(name)
    latest = [r for r in rows if r.get("in_latest_version", "true") == "true"]
    older = [r for r in rows if r.get("in_latest_version", "true") != "true"]

    def exact(pool: list[dict[str, str]]) -> list[dict[str, str]]:
        return [r for r in pool if query in (r["normalized_supplier"], r["normalized_brand"])]

    hits = exact(latest)
    history = [] if hits else exact(older)
    possible: dict[str, str] = {}
    if not hits:
        padded = f" {query} "
        for r in latest:
            for field in ("normalized_supplier", "normalized_brand"):
                listed = r[field]
                if not listed or listed == query:
                    continue
                if fuzz.token_sort_ratio(query, listed) >= POSSIBLE_MATCH_MIN:
                    possible[listed] = "similar name"
                elif field == "normalized_brand" and len(listed) >= 4 and f" {listed} " in padded:
                    possible[listed] = "name contains a listed brand"
    return {
        "query": name,
        "normalized_query": query,
        "status": "present" if hits else "not_present",
        "matches": hits,
        "history_versions": sorted({r["list_section_date"] for r in history}, reverse=True),
        "possible_matches": [{"listed_name": k, "reason": v} for k, v in sorted(possible.items())],
    }
