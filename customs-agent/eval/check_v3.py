"""Independent rule check for AI-generated scenarios (eval-v3 / dev-v2, SPEC v2).

    uv run python eval/check_v3.py                    # report on eval/generated/*.yaml

For each scenario it re-derives, from the facts the scenario states, what SPEC v2 says the answer
must be (outcome, exemption, bottom line per line, clarify facts, state flag) and lists every
place the generator's labels disagree, plus facts that do not appear in the question text.

It is written separately from the agent and imports nothing from src/ (CLAUDE.md rule 5): it
only flags scenarios for review. A disagreement is settled by reading the rule, never by
running the agent. Rates and country lists are typed in here from SPEC v2 and rates.yaml.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "eval" / "generated"

TYPES = {
    "alcohol_excess_800",
    "alcohol_cbi_2L",
    "exemption_200_all_or_nothing",
    "tobacco_over_limit",
    "cuban_origin",
    "sanctions_escalate",
    "under_21",
    "mixed_basket",
    "whatif",
    "clarify",
    "state_flag",
    "out_of_scope",
    "refuse_evasion",
    "injection_doc",
    "injection_user",
}
OUTCOMES = {"answered", "clarify", "refused", "escalated"}
EXCISE = {  # $ per litre (TTB): wine per wine gallon, spirits per proof gallon, beer per barrel
    "wine_still_le16": lambda abv: 1.07 / 3.785411784,
    "wine_still_16_21": lambda abv: 1.57 / 3.785411784,
    "sparkling": lambda abv: 3.40 / 3.785411784,
    "beer": lambda abv: 18.0 / 117.347765,
    "spirits": lambda abv: 13.5 * (abv or 40) * 2 / 100 / 3.785411784,
}
FACTS = {
    "age",
    "trip_length",
    "exemption_used_last_30_days",
    "origin",
    "abv",
    "size",
    "unit_price",
    "count",
}
BOTTOM = {
    "owe",
    "nothing_to_pay",
    "prohibited",
    "declare_detention_risk",
    "relinquish_excess",
}
CBI = {
    "AG",
    "AW",
    "BS",
    "BB",
    "BZ",
    "CW",
    "DM",
    "GD",
    "GY",
    "HT",
    "JM",
    "MS",
    "KN",
    "LC",
    "VC",
    "TT",
    "VG",
}
FREE = {
    "MX",
    "CA",
    "CR",
    "DO",
    "SV",
    "GT",
    "HN",
    "NI",
    "BH",
    "CL",
    "CO",
    "IL",
    "JO",
    "KR",
    "MA",
    "OM",
    "PA",
    "PE",
    "SG",
}
COLUMN2 = {"BY", "KP", "RU", "CU"}
STATES = {"NY", "FL", "CA", "TX", "NJ"}
# airports and cities in the five SPEC states: a mention with no arrival_state in the facts is a
# note to read (it can be a departure, or San José in Costa Rica), not an issue
CITIES = re.compile(
    r"\b(JFK|LaGuardia|Newark|EWR|Miami|Fort Lauderdale|Orlando|Tampa|LAX|Los Angeles|"
    r"San Francisco|SFO|San Diego|Houston|Dallas|DFW|Austin|El Paso|New York|New Jersey|"
    r"Florida|California|Texas)\b",
    re.IGNORECASE,
)
RISKY_WORDS = re.compile(r"\b(rum|ron|cigars?|habanos?|vodka)\b", re.IGNORECASE)


@dataclass
class Report:
    sid: str
    source: str
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def hours(trip: dict | None) -> float | None:
    if not trip or trip.get("value") is None:
        return None
    return float(trip["value"]) * {"hours": 1, "days": 24, "weeks": 168}.get(
        trip.get("unit"), 0
    )


def containers(b: dict) -> float:
    return float((b.get("quantity") or {}).get("value") or 0)


def litres(b: dict) -> float:
    return containers(b) * float(b.get("unit_ml") or 0) / 1000


def sticks(b: dict, kind: str) -> int:
    return int(b.get("count") or 0) if b.get("type") == kind else 0


def charge_per_l(b: dict) -> float:
    o = b.get("origin")
    rate = 0.0 if o in FREE else 0.04 if o in COLUMN2 else 0.03
    value_per_l = float(b.get("unit_price_usd") or 0) / (
        float(b.get("unit_ml") or 750) / 1000
    )
    return rate * value_per_l + EXCISE.get(b.get("excise_class"), EXCISE["spirits"])(
        b.get("abv")
    )


def expected(s: dict) -> dict:
    """SPEC v2 answer for a fully stated scenario."""
    p, basket = s.get("profile") or {}, s.get("basket") or []
    alc = [b for b in basket if b.get("category") == "alcohol"]
    tob = [b for b in basket if b.get("category") == "tobacco"]
    age = p.get("age")
    if any(b.get("origin") == "RU" for b in alc):
        return {"outcome": "escalated", "reason": "russian_origin_alcohol"}
    total_l = sum(litres(b) for b in alc if b.get("origin") != "CU")
    if total_l > 9 or any(containers(b) > 12 for b in alc):
        return {"outcome": "escalated", "reason": "commercial_quantity"}
    used = p.get("exemption_used_last_30_days")
    h = hours(p.get("trip"))
    from_mx = p.get("direct_arrival_from") == "MX"
    use_800 = not used and ((h is not None and h >= 48) or from_mx)
    lines: list[str | None] = [None] * len(basket)
    for i, b in enumerate(basket):
        if b.get("origin") == "CU":
            lines[i] = "prohibited"
    live = [i for i, b in enumerate(basket) if lines[i] is None]
    out: dict = {"outcome": "answered"}

    if not use_800:
        value = sum(
            containers(basket[i]) * float(basket[i].get("unit_price_usd") or 0)
            for i in live
        )
        ml = sum(
            litres(basket[i]) * 1000 for i in live if basket[i]["category"] == "alcohol"
        )
        cig = sum(sticks(basket[i], "cigarettes") for i in live)
        cgr = sum(sticks(basket[i], "cigars") for i in live)
        fits = value <= 200 and ml <= 150 and cig <= 50 and cgr <= 10
        if (
            age is not None
            and age < 21
            and any(basket[i]["category"] == "alcohol" for i in live)
        ):
            fits = False
        out["exemption"] = "short_trip_200" if fits else "none_200_failed"
        for i in live:
            if fits:
                lines[i] = "nothing_to_pay"
            elif basket[i]["category"] == "alcohol":
                lines[i] = "owe"
            else:
                lines[i] = tobacco_line(basket[i], over=True)
        dutiable = (
            0.0
            if fits
            else value_of(
                basket, [i for i in live if basket[i]["category"] == "alcohol"], {}
            )
        )
    else:
        under21 = age is not None and age < 21
        alc_live = [i for i in live if basket[i]["category"] == "alcohol"]
        tob_live = [i for i in live if basket[i]["category"] == "tobacco"]
        allowance = 0.0 if under21 else 1.0
        if not under21 and p.get("direct_arrival_from") in CBI:
            cbi_l = sum(
                litres(basket[i]) for i in alc_live if basket[i].get("origin") in CBI
            )
            if cbi_l >= 1.0:
                allowance = 2.0
        exempt: dict[int, float] = {}
        left = allowance
        for i in sorted(alc_live, key=lambda i: -charge_per_l(basket[i])):
            take = min(left, litres(basket[i]))
            exempt[i], left = take, left - take
        for i in alc_live:
            lines[i] = (
                "nothing_to_pay"
                if exempt.get(i, 0) >= litres(basket[i]) - 1e-9
                else "owe"
            )
        cig = sum(sticks(basket[i], "cigarettes") for i in tob_live)
        cgr = sum(sticks(basket[i], "cigars") for i in tob_live)
        for i in tob_live:
            b = basket[i]
            over = (
                under21
                or (b["type"] == "cigarettes" and cig > 200)
                or (b["type"] == "cigars" and cgr > 100)
            )
            lines[i] = tobacco_line(b, over=over) if over else "nothing_to_pay"
        if under21 and alc:
            out["exemption"] = "standard_800_no_alcohol_under_21"
        elif under21 and tob:
            out["exemption"] = "standard_800_no_tobacco_under_21"
        elif allowance == 2.0:
            out["exemption"] = "standard_800_beneficiary_2l"
        else:
            out["exemption"] = "standard_800"
        dutiable = value_of(basket, alc_live, exempt)
    if "escalate_agr" in lines:
        return {"outcome": "escalated", "reason": "agr_claim_over_allowance"}
    owes = any(x == "owe" for x in lines)
    if owes and p.get("flat_rate_used_last_30_days") is True:
        return {"outcome": "escalated", "reason": "flat_rate_used"}
    if dutiable > 1000:
        return {"outcome": "escalated", "reason": "over_flat_rate_band"}
    out["bottom_line"] = lines
    if p.get("arrival_state") in STATES:
        out["state_flag"] = p["arrival_state"]
    return out


def tobacco_line(b: dict, *, over: bool) -> str:
    if not over:
        return "nothing_to_pay"
    if b.get("claims_american_goods_returned"):
        return "escalate_agr"
    if b.get("export_labelled_us"):
        return "relinquish_excess"
    return "declare_detention_risk"


def value_of(basket: list[dict], idx: list[int], exempt: dict[int, float]) -> float:
    v = 0.0
    for i in idx:
        b, total = basket[i], litres(basket[i])
        if total:
            v += (
                (total - exempt.get(i, 0))
                / total
                * containers(b)
                * float(b.get("unit_price_usd") or 0)
            )
    return v


def expected_clarify(s: dict) -> list[str]:
    """SPEC v2 5.2 + 9b: the facts the first clarifying message asks for."""
    p, basket = s.get("profile") or {}, s.get("basket") or []
    alc = [b for b in basket if b.get("category") == "alcohol"]
    h = hours(p.get("trip"))
    from_mx = p.get("direct_arrival_from") == "MX"
    value = sum(containers(b) * float(b.get("unit_price_usd") or 0) for b in basket)
    ml = sum(litres(b) * 1000 for b in alc)
    cig = sum(int(b.get("count") or 0) for b in basket if b.get("type") == "cigarettes")
    cgr = sum(int(b.get("count") or 0) for b in basket if b.get("type") == "cigars")
    sizes_known = all(b.get("unit_ml") for b in alc)
    fits200 = (
        sizes_known
        and all(b.get("unit_price_usd") for b in basket)
        and value <= 200
        and ml <= 150
        and cig <= 50
        and cgr <= 10
    )
    ask: list[str] = []
    if p.get("age") is None:
        ask.append("age")
    if h is None and not from_mx and not fits200:
        ask.append("trip_length")
    if p.get("exemption_used_last_30_days") is None and not fits200:
        ask.append("exemption_used_last_30_days")
    if any(
        b.get("origin") is None
        and RISKY_WORDS.search(f"{b.get('item', '')} {b.get('type', '')}")
        for b in basket
    ):
        ask.append("origin")
    cbi = p.get("direct_arrival_from") in CBI
    if (
        sizes_known
        and any(b.get("abv") is None for b in alc)
        and ml / 1000 > (2.0 if cbi else 1.0)
    ):
        ask.append("abv")
    if not sizes_known:
        ask.append("size")
    if any(
        b.get("category") == "tobacco" and not b.get("count") for b in basket
    ) or any(not containers(b) for b in basket):
        ask.append("count")
    if any(b.get("unit_price_usd") is None for b in basket) and not fits200:
        ask.append("unit_price")
    if ask:
        return ask
    # stage 2: only when something is owed
    if expected(s).get("bottom_line") and "owe" in expected(s)["bottom_line"]:
        if any(b.get("origin") is None and b.get("bought_where") in FREE for b in alc):
            ask.append("origin")
        if any(b.get("abv") is None for b in alc):
            ask.append("abv")
    return ask


def stated(question: str, value) -> bool:
    """Is a number from the facts written in the question (digits, or a few common words)?"""
    if value is None or isinstance(value, bool):
        return True
    q = question.lower().replace(",", "")
    v = float(value)
    forms = {f"{v:g}", f"{v:.2f}", f"{v:.1f}", str(int(v)) if v == int(v) else f"{v:g}"}
    if any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", q) for f in forms):
        return True
    words = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
        20: "twenty",
        30: "thirty",
        40: "forty",
        50: "fifty",
        60: "sixty",
        70: "seventy",
    }
    return v in words and re.search(rf"\b{words[int(v)]}", q) is not None


def check(s: dict, source: str) -> Report:
    r = Report(str(s.get("id")), source)
    g = s.get("gold") or {}
    t = s.get("type")
    if t not in TYPES:
        r.issues.append(f"unknown type {t!r}")
    if g.get("outcome") not in OUTCOMES:
        r.issues.append(f"bad outcome {g.get('outcome')!r}")
        return r
    for b in s.get("basket") or []:
        if b.get("category") == "alcohol" and b.get("excise_class") not in EXCISE:
            r.issues.append(f"{b.get('item')}: excise_class {b.get('excise_class')!r}")
        abv, xc = b.get("abv"), b.get("excise_class")
        if (
            b.get("type") == "wine"
            and abv is not None
            and str(xc).startswith("wine_still")
        ):
            # the band follows the ABV (TTB): found on Day 11, E3-019 15.5% labelled over 16%
            band = (
                "wine_still_le16"
                if abv <= 16
                else "wine_still_16_21"
                if abv <= 21
                else "wine_still_21_24"
            )
            if xc != band:
                r.issues.append(f"{b.get('item')}: {abv}% is {band}, not {xc}")
        if b.get("category") == "tobacco" and not b.get("count") and t != "clarify":
            r.issues.append(f"{b.get('item')}: no count")
        if (
            re.search(r"\bsake\b", str(b.get("item")), re.IGNORECASE)
            and b.get("excise_class") != "beer"
        ):
            r.issues.append("sake not in the beer class (SPEC v2 10)")
        if (
            re.search(
                r"champagne|prosecco|cava|cr[ée]mant|sekt|spumante|sparkling",
                str(b.get("item")),
                re.IGNORECASE,
            )
            and b.get("excise_class") != "sparkling"
        ):
            r.issues.append(
                f"{b.get('item')}: sparkling wine not in the sparkling class"
            )
        if (
            re.search(
                r"liqueur|cr[eè]me de|\bamaro\b|schnapps",
                str(b.get("item")),
                re.IGNORECASE,
            )
            and b.get("excise_class") != "spirits"
        ):
            r.issues.append(f"{b.get('item')}: liqueur not in the spirits class")
    q = str(s.get("question") or "")
    p = s.get("profile") or {}
    if (
        (m := CITIES.search(q))
        and not p.get("arrival_state")
        and g.get("outcome") == "answered"
    ):
        r.notes.append(
            f"names {m.group(0)!r} but the facts give no arrival state: arrival or not?"
        )
    for k in ("age",):
        if not stated(q, p.get(k)):
            r.notes.append(f"{k} {p.get(k)} not found in the question")
    for b in s.get("basket") or []:
        for k in ("abv", "unit_price_usd"):
            if not stated(q, b.get(k)):
                r.notes.append(
                    f"{b.get('item')}: {k} {b.get(k)} not found in the question"
                )

    if g["outcome"] == "refused":
        if not g.get("reason"):
            r.issues.append("refused without a reason")
        return r
    if t == "injection_doc":
        inj = s.get("inject_into_retrieval") or {}
        if (
            not inj.get("doc_id")
            or not inj.get("text")
            or not g.get("must_not_contain")
        ):
            r.issues.append(
                "injection_doc without a planted document or forbidden phrases"
            )
    if t == "whatif":
        if not s.get("whatif", {}).get("owe_less_than_usd"):
            r.issues.append("whatif without a target")
        return r
    if g["outcome"] == "clarify":
        want = expected_clarify(s)
        got = g.get("clarify_facts") or []
        if bad := set(got) - FACTS:
            r.issues.append(f"unknown clarify facts {sorted(bad)}")
        if set(got) != set(want):
            r.issues.append(f"clarify facts {sorted(got)} / rules say {sorted(want)}")
        return r
    want_clarify = expected_clarify(s)
    if want_clarify:
        r.issues.append(
            f"answered/escalated, but a fact is missing: rules would ask {want_clarify}"
        )
        return r
    e = expected(s)
    if e["outcome"] != g["outcome"]:
        r.issues.append(
            f"outcome {g['outcome']} / rules say {e['outcome']} ({e.get('reason')})"
        )
        return r
    if e["outcome"] == "escalated":
        if g.get("reason") != e.get("reason"):
            r.notes.append(f"reason {g.get('reason')} / rules say {e.get('reason')}")
        return r
    if g.get("exemption") != e.get("exemption"):
        r.issues.append(
            f"exemption {g.get('exemption')} / rules say {e.get('exemption')}"
        )
    gb = list(g.get("bottom_line") or [])
    if bad := set(gb) - BOTTOM:
        r.issues.append(f"unknown bottom line {sorted(bad)}")
    if gb != e.get("bottom_line"):
        r.issues.append(f"bottom line {gb} / rules say {e.get('bottom_line')}")
    if g.get("state_flag") != e.get("state_flag"):
        r.issues.append(
            f"state flag {g.get('state_flag')} / rules say {e.get('state_flag')}"
        )
    return r


def load_generated() -> list[tuple[str, dict]]:
    out = []
    for f in sorted(GENERATED.glob("*.yaml")):
        if f.name == "corrections.yaml":  # fixes applied by build_v3.py, not scenarios
            continue
        for s in yaml.safe_load(f.read_text()) or []:
            out.append((f.stem, s))
    return out


def main() -> int:
    items = load_generated()
    reports = [check(s, src) for src, s in items]
    bad = [r for r in reports if r.issues]
    by_src: dict[str, list[int]] = {}
    for r in reports:
        by_src.setdefault(r.source, [0, 0])
        by_src[r.source][0] += 1
        by_src[r.source][1] += bool(r.issues)
    print(f"{len(items)} scenarios, {len(bad)} with issues")
    for src, (n, b) in sorted(by_src.items()):
        print(f"  {src:10s} {n:3d} scenarios, {b:3d} with issues")
    for r in reports:
        if r.issues or r.notes:
            print(f"\n{r.source}:{r.sid}")
            for i in r.issues:
                print(f"  ISSUE {i}")
            for n in r.notes:
                print(f"  note  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
