"""Independent gold builder for the US Customs Assistant eval sets (plan D18).

Reads ONLY:
  pack/rules/*.yaml                      signed-off rule, rate, unit, country, brand, state tables
  pack/eval/src/{frozen,corrections,dev}.yaml   the 106 scenarios
  pack/eval/gold/judgement.yaml          the judgement layer (outcome, clarify, rules cited, notes)

Shares no code with backend/ or web/. All money arithmetic uses decimal.Decimal; each duty line and
each excise line is rounded half-up to the cent, then summed (SPEC section 5 step 7).

Writes (into pack/eval/gold/): gold.jsonl, workings.md, gold.xlsx.

Run from the app root:
  uv run --no-project --with pyyaml --with openpyxl python pack/eval/gold/build_gold.py
"""

from __future__ import annotations

import copy
import json
import sys
from decimal import ROUND_HALF_UP, getcontext
from decimal import Decimal as D
from pathlib import Path

import yaml

getcontext().prec = 60

HERE = Path(__file__).resolve().parent
APP = HERE.parents[2]
RULES_DIR = APP / "pack" / "rules"
SRC_DIR = APP / "pack" / "eval" / "src"

SETS = [("frozen", "frozen.yaml"), ("corrections", "corrections.yaml"), ("dev", "dev.yaml")]
HAND_CHECK = {
    "A01",
    "A04",
    "A07",
    "A10",
    "B01",
    "B03",
    "C01",
    "C05",
    "C08",
    "D01",
    "D02",
    "E04",
    "F01",
    "G02",
    "G04",
    "G07",
    "G08",
    "G10",
    "I02",
    "I06",
}


def load(p: Path):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dec(x) -> D:
    return D(str(x))


# ----------------------------------------------------------------------------------------------
# Rule tables
# ----------------------------------------------------------------------------------------------
RULES_Y = load(RULES_DIR / "rules.yaml")
RATES_Y = load(RULES_DIR / "rates.yaml")
UNITS_Y = load(RULES_DIR / "units.yaml")
COUNTRIES_Y = load(RULES_DIR / "countries.yaml")
STATES_Y = load(RULES_DIR / "states.yaml")
BRANDS_Y = load(RULES_DIR / "brands.yaml")
JUDGE = load(HERE / "judgement.yaml")["scenarios"]

RULE = {r["id"]: r for r in RULES_Y["rules"]}

L_PER_GAL = dec(UNITS_Y["litres_per_us_gallon"])
GAL_PER_BBL = dec(UNITS_Y["gallons_per_barrel"])
PROOF_PER_ABV = dec(UNITS_Y["proof_per_abv_percent"])
VOL = {k: dec(v) for k, v in UNITS_Y["volumes_ml"].items()}
COUNTS = UNITS_Y["counts"]
DEFAULT_ABV = {k: dec(v) for k, v in UNITS_Y["default_abv"].items()}

DUTY_RATE = dec(RATES_Y["duty"]["flat_rate"]["rate"])
DUTY_RATE_COL2 = dec(RATES_Y["duty"]["column2_flat_rate"]["rate"])
DUTY_CAP = dec(RATES_Y["duty"]["flat_rate"]["cap_usd"])
EXCISE = {row["class"]: row for row in RATES_Y["excise_alcohol"]}

MEXICO = set(COUNTRIES_Y["mexico"])
INSULAR = set(COUNTRIES_Y["insular_possessions"]["codes"])
CBI_KEY = COUNTRIES_Y["caribbean_basin"]["used_by_R2"]  # Decision A
CBI = set(COUNTRIES_Y["caribbean_basin"][CBI_KEY]["codes"])
COLUMN2 = set(COUNTRIES_Y["column2"]["codes"])
FTA = {}
for sym, prog in COUNTRIES_Y["trade_agreement_programs"]["programs"].items():
    for c in prog["codes"]:
        FTA[c] = f"{prog['name']} ({sym})"

AMBIGUOUS_BRANDS = {b.lower() for lst in BRANDS_Y["ambiguous_brands"].values() for b in lst}

P_R1 = RULE["R1"]["params"]
P_R2 = RULE["R2"]["params"]
P_R3 = RULE["R3"]["params"]
P_R5 = RULE["R5"]["params"]
P_R9 = RULE["R9"]["params"]
P_R10 = RULE["R10"]["params"]
P_R11 = RULE["R11"]["params"]

EX_800 = 800
EX_200 = int(P_R1["value_limit_usd"])
ALC_ALLOW_800_ML = dec(P_R9["alcohol_litres"]) * 1000
ALC_ALLOW_CBI_ML = dec(P_R2["litres"]) * 1000
CBI_MIN_ML = dec(P_R2["min_beneficiary_product_litres"]) * 1000
ALC_LIMIT_200_ML = dec(P_R1["limits"]["alcohol_ml"])
CIG_LIMIT_200 = int(P_R1["limits"]["cigarettes"])
CIGAR_LIMIT_200 = int(P_R1["limits"]["cigars"])
CIG_ALLOW = int(P_R5["allowance"]["cigarettes"])
CIGAR_ALLOW = int(P_R5["allowance"]["cigars"])
MIN_AGE = int(P_R3["alcohol_min_age"])
MIN_HOURS = dec(P_R9["min_hours"])
FLAG_ML = dec(P_R10["flag_litres_per_traveller"]) * 1000
BASKET_CAP = dec(P_R11["escalate_if_basket_value_over_usd"])

ALCOHOL = {"wine", "sparkling_wine", "beer", "spirits", "liqueur", "hard_cider"}
TOBACCO = {"cigarettes", "cigars"}
CENT = D("0.01")


def cents(x: D) -> D:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


TIES: list[str] = []  # exact half-cent ties met while rounding (audit)
SENSITIVITY: list[str] = []  # places where a defensible alternative reading changes a figure


def rnd(x: D, where: str) -> D:
    frac = (x * 100) - (x * 100).to_integral_value(rounding="ROUND_FLOOR")
    if frac == D("0.5"):
        TIES.append(f"{where}: {x} is an exact half cent")
    return cents(x)


def fmt(x) -> str:
    """Plain decimal string without exponent or trailing zeros (for ml, counts, rates)."""
    if isinstance(x, int):
        return str(x)
    x = dec(x)
    if x == x.to_integral_value():
        return str(int(x))
    s = format(x.normalize(), "f")
    return s


def usd(x: D) -> str:
    return str(cents(x))


# ----------------------------------------------------------------------------------------------
# Citations
# ----------------------------------------------------------------------------------------------
def acceptable(token: str) -> tuple[str, list[str]]:
    if token.startswith("STATE:"):
        st = token.split(":", 1)[1]
        return f"{st} arrival-state flag", list(STATES_Y["states"][st]["cites"])
    if token.startswith("R4."):
        sub = token.split(".", 1)[1]
        label = {
            "third_country": "R4 Cuban-origin alcohol/tobacco bought in a third country is prohibited",
            "acquired_in_cuba": "R4 alcohol/tobacco acquired in Cuba cannot be brought back",
        }[sub]
        return label, list(RULE["R4"]["cites"][sub])
    r = RULE[token]
    return f"{token} {r['name']}", list(r["cites"])


# ----------------------------------------------------------------------------------------------
# Normalisation
# ----------------------------------------------------------------------------------------------
def container_ml(line) -> tuple[D, str | None]:
    if line.get("container_ml") is not None:
        return dec(line["container_ml"]), None
    unit, item = line.get("unit"), line["item"]
    if unit == "fifth":
        return VOL["fifth"], "fifth = 750 ml (units.yaml)"
    if unit == "magnum":
        return VOL["magnum"], "magnum = 1500 ml (units.yaml)"
    if unit in ("l", "litre"):
        return VOL["litre"], None
    if unit == "ml":
        return D(1), None
    if unit == "can":
        return VOL["can_12oz"], "can = 12 oz (units.yaml)"
    if unit == "bottle" or unit is None:
        if item in ("spirits", "liqueur"):
            return VOL[
                "bottle_spirits"
            ], "bottle size not stated: 750 ml assumed (units.yaml bottle_spirits)"
        if item in ("wine", "sparkling_wine"):
            return VOL[
                "bottle_wine"
            ], "bottle size not stated: 750 ml assumed (units.yaml bottle_wine)"
    raise ValueError(f"cannot size line {line}")


def sticks_of(line) -> int:
    q = line["quantity"]
    unit = line.get("unit")
    if unit == "pack":
        return int(q) * int(COUNTS["cigarettes_per_pack"])
    if unit == "carton":
        return int(q) * int(COUNTS["cigarettes_per_carton"])
    if unit in ("stick", "each", None):
        return int(q)
    raise ValueError(f"cannot count line {line}")


def excise_class(item: str, abv: D) -> str:
    if item in ("spirits", "liqueur"):
        return "distilled_spirits"
    if item == "wine":
        if abv > dec(EXCISE["still_wine_21_24"]["max_abv"]):
            return "distilled_spirits"  # 26 USC 5001(a)(3)
        if abv <= dec(EXCISE["still_wine_le_16"]["max_abv"]):
            return "still_wine_le_16"
        if abv <= dec(EXCISE["still_wine_16_21"]["max_abv"]):
            return "still_wine_16_21"
        return "still_wine_21_24"
    if item == "sparkling_wine":
        return "sparkling_wine"
    if item == "hard_cider":
        return "hard_cider"
    if item == "beer":
        return "beer"
    raise ValueError(item)


def excise_exact(cls: str, ml: D, abv: D) -> D:
    row = EXCISE[cls]
    rate = dec(row["rate"])
    gallons = ml / 1000 / L_PER_GAL
    if row["per"] == "proof_gallon":
        return gallons * (PROOF_PER_ABV * abv) / 100 * rate
    if row["per"] == "wine_gallon":
        return gallons * rate
    if row["per"] == "barrel":
        return gallons / GAL_PER_BBL * rate
    raise ValueError(row)


def normalise(basket):
    out = []
    for i, line in enumerate(basket, start=1):
        item = line["item"]
        L = {
            "i": i,
            "item": item,
            "src": line,
            "defaults": [],
            "origin": line.get("origin"),
            "bought_in": line.get("bought_in"),
            "brand": line.get("brand"),
            "value": dec(line["value_usd"]) if line.get("value_usd") is not None else None,
            "us_export": bool(line.get("us_made_export_labelled")),
        }
        if item in ALCOHOL:
            L["kind"] = "alcohol"
            cml, note = container_ml(line)
            if note:
                L["defaults"].append(note)
            L["ml"] = cml * dec(line["quantity"])
            if line.get("abv") is not None:
                L["abv"] = dec(line["abv"])
            else:
                L["abv"] = DEFAULT_ABV[item]
                L["defaults"].append(
                    f"ABV not stated: {fmt(L['abv'])}% default for {item} (units.yaml)"
                )
            L["cls"] = excise_class(item, L["abv"])
        elif item in TOBACCO:
            L["kind"] = "tobacco"
            L["sticks"] = sticks_of(line)
        else:
            L["kind"] = "other"
        # restriction status (SPEC 5 step 1)
        if L["kind"] in ("alcohol", "tobacco") and L["origin"] == "CU":
            L["status"] = "prohibited"
        elif (
            L["kind"] in ("alcohol", "tobacco")
            and L["origin"] in (None, "unknown")
            and L["brand"]
            and L["brand"].lower() in AMBIGUOUS_BRANDS
        ):
            L["status"] = "possibly_cuban"  # Decision E (after the one question)
        elif L["kind"] == "other":
            L["status"] = "out_of_scope"
        else:
            L["status"] = "ok"
        out.append(L)
    return out


# ----------------------------------------------------------------------------------------------
# Calculators (SPEC section 5, in order)
# ----------------------------------------------------------------------------------------------
class Missing(Exception):
    pass


def long_trip(profile) -> bool | None:
    th = profile.get("trip_hours")
    if th is None:
        return None
    if isinstance(th, str):
        return {">=48": True, "<48": False}[th]
    return dec(th) >= MIN_HOURS


def determine_exemption(profile, log):
    used = profile.get("exemption_used_last_30_days")
    mx = profile.get("arrived_directly_from") in MEXICO
    lt = long_trip(profile)
    if used is None:
        raise Missing("exemption_used_last_30_days")
    if lt is None and not mx:
        raise Missing("trip_hours")
    th = profile.get("trip_hours")
    if (lt or mx) and not used:
        why = (
            "arrived directly from Mexico (no 48-hour minimum)"
            if mx and not lt
            else f"trip {th} h >= 48 h"
            if not isinstance(th, str)
            else f"trip {th} h"
        )
        log.append(f"Exemption $800 (R9): {why}; not used in the last 30 days.")
        return EX_800
    if used:
        log.append("Exemption $200 (R9 -> R1): the $800 exemption was used in the last 30 days.")
    else:
        tdesc = "under 48 h" if th == "<48" else f"{th} h < 48 h"
        log.append(f"Exemption $200 (R9 -> R1): trip {tdesc} and not arriving from Mexico.")
    return EX_200


def per_litre_cost(L) -> D:
    """R11 ranking key: 3% of value per litre + excise per litre (rule-literal 3%)."""
    v = (L["value"] / L["ml"] * 1000) if L["value"] is not None else D(0)
    return DUTY_RATE * v + excise_exact(L["cls"], D(1000), L["abv"])


def duty_rate_for(L) -> tuple[D, bool, str]:
    o = L["origin"]
    if o in COLUMN2:
        return DUTY_RATE_COL2, False, f"4% Column 2 ({o})"
    if o in FTA:
        return D(0), True, f"free: product of {FTA[o]} partner, if it qualifies as originating"
    return DUTY_RATE, False, "3% flat rate"


def compute(profile, basket, *, basket_total_usd=None, sid=""):
    log: list[str] = []
    lines = normalise(basket)
    R = {
        "lines": lines,
        "log": log,
        "exemption": None,
        "under21": False,
        "alc_allow_ml": None,
        "cbi": False,
        "aon_triggered": False,
        "escalate": [],
        "rank": [],
    }

    for L in lines:
        for d in L["defaults"]:
            log.append(f"Line {L['i']}: {d}.")
        if L["status"] == "prohibited":
            where = (
                "acquired in Cuba"
                if L["bought_in"] == "CU"
                else f"bought in {L['bought_in']} (third country)"
            )
            log.append(
                f"Line {L['i']} ({L['item']}): Cuban origin, {where} -> prohibited, removed from all counts (R4)."
            )
        elif L["status"] == "possibly_cuban":
            log.append(
                f"Line {L['i']} ({L['item']}, brand {L['brand']}): origin still unknown after one question "
                f"-> treated as possibly Cuban: no allowance, declare (R12, Decision E)."
            )

    adm = [L for L in lines if L["status"] == "ok"]
    alc = [L for L in adm if L["kind"] == "alcohol"]
    tob = [L for L in adm if L["kind"] == "tobacco"]
    for L in lines:
        L.setdefault("exempt_ml", None)
        L.setdefault("dutiable_ml", D(0))
        L.setdefault("duty", None)
        L.setdefault("excise", None)
        L.setdefault("exempt_sticks", None)
        L.setdefault("excess_sticks", 0)
    if not adm:
        R["totals"] = {"duty": D(0), "excise": D(0), "total": D(0)}
        return R

    age = profile.get("age")
    if age is None:
        raise Missing("age")
    R["under21"] = int(age) < MIN_AGE
    if R["under21"]:
        log.append(f"Age {age} < 21: no alcohol and no tobacco allowance (R3, Decision B).")

    ex = determine_exemption(profile, log)
    R["exemption"] = ex

    # Large-quantity and basket-value caps (R10, R11)
    total_ml = sum((L["ml"] for L in alc), D(0))
    R["total_alcohol_ml"] = total_ml
    if total_ml > FLAG_ML:
        R["escalate"].append(
            f"total alcohol {fmt(total_ml)} ml > {fmt(FLAG_ML)} ml (R10, Decision D)"
        )
    known_vals = [L["value"] for L in adm if L["value"] is not None]
    if sum(known_vals, D(0)) > BASKET_CAP:
        R["escalate"].append("in-scope basket value > $800 (R11)")

    if ex == EX_800:
        if R["under21"]:
            allow = D(0)
        else:
            arrived = profile.get("arrived_directly_from")
            cbi_ml = sum((L["ml"] for L in alc if L["origin"] in CBI), D(0))
            if arrived in CBI and alc:
                if cbi_ml >= CBI_MIN_ML:
                    R["cbi"] = True
                    allow = ALC_ALLOW_CBI_ML
                    log.append(
                        f"Arrived directly from {arrived} (CBP Caribbean Basin list, Decision A) and "
                        f"{fmt(cbi_ml)} ml is a beneficiary-country product (>= 1 L): 2 L allowance (R2)."
                    )
                else:
                    allow = ALC_ALLOW_800_ML
                    log.append(
                        f"Arrived directly from {arrived} (on CBP's list) but only {fmt(cbi_ml)} ml is a "
                        f"beneficiary-country product (< 1 L): 1 L allowance (R2)."
                    )
            else:
                allow = ALC_ALLOW_800_ML
        R["alc_allow_ml"] = allow if alc else None
        if alc:
            if not R["under21"]:
                log.append(f"Alcohol allowance {fmt(allow)} ml.")
            ranked = sorted(alc, key=lambda L: (-per_litre_cost(L), L["i"]))
            R["rank"] = [(L["i"], per_litre_cost(L)) for L in ranked]
            if total_ml > allow > 0 and len(alc) > 1:
                log.append(
                    "R11 ranking (3% of value per litre + excise per litre): "
                    + "; ".join(
                        f"line {L['i']} {L['item']} ${per_litre_cost(L):.4f}/L" for L in ranked
                    )
                )
            left = allow
            for L in ranked:
                take = min(left, L["ml"])
                L["exempt_ml"] = take
                L["dutiable_ml"] = L["ml"] - take
                left -= take
            # does using the real duty rate (FTA 0 / Column 2 4%) change the allocation? (audit)
            alt = sorted(
                alc,
                key=lambda L: (
                    -(
                        duty_rate_for(L)[0] * ((L["value"] or 0) / L["ml"] * 1000)
                        + excise_exact(L["cls"], D(1000), L["abv"])
                    ),
                    L["i"],
                ),
            )
            if [L["i"] for L in alt] != [L["i"] for L in ranked] and total_ml > allow > 0:
                SENSITIVITY.append(
                    f"{sid}: ranking by the line's actual duty rate would change the R11 order "
                    f"{[L['i'] for L in ranked]} -> {[L['i'] for L in alt]}"
                )
        tob_allow = {
            "cigarettes": 0 if R["under21"] else CIG_ALLOW,
            "cigars": 0 if R["under21"] else CIGAR_ALLOW,
        }
        for L in tob:
            take = min(tob_allow[L["item"]], L["sticks"])
            L["exempt_sticks"] = take
            L["excess_sticks"] = L["sticks"] - take
            tob_allow[L["item"]] -= take
    else:  # $200, all-or-nothing (R1)
        cig = sum((L["sticks"] for L in tob if L["item"] == "cigarettes"), 0)
        cgr = sum((L["sticks"] for L in tob if L["item"] == "cigars"), 0)
        aml = sum((L["ml"] for L in alc), D(0))
        if all(L["value"] is not None for L in adm):
            tot = sum((L["value"] for L in adm), D(0))
        elif basket_total_usd is not None:
            tot = dec(basket_total_usd)
        else:
            raise Missing("value for the $200 test")
        alc_limit = D(0) if R["under21"] else ALC_LIMIT_200_ML
        reasons = []
        if cig > CIG_LIMIT_200:
            reasons.append(f"{cig} cigarettes > {CIG_LIMIT_200}")
        if cgr > CIGAR_LIMIT_200:
            reasons.append(f"{cgr} cigars > {CIGAR_LIMIT_200}")
        if aml > alc_limit:
            reasons.append(f"{fmt(aml)} ml alcohol > {fmt(alc_limit)} ml")
        if tot > EX_200:
            reasons.append(f"value ${tot} > $200")
        R["alc_allow_ml"] = alc_limit if alc else None
        R["aon_triggered"] = bool(reasons)
        if reasons:
            log.append(
                "R1 all-or-nothing triggered (" + "; ".join(reasons) + "): NOTHING is exempt."
            )
        else:
            log.append(f"R1: within every $200 limit (value ${tot}): everything is exempt.")
        for L in alc:
            L["exempt_ml"] = D(0) if reasons else L["ml"]
            L["dutiable_ml"] = L["ml"] if reasons else D(0)
        for L in tob:
            L["exempt_sticks"] = 0 if reasons else L["sticks"]
            L["excess_sticks"] = L["sticks"] if reasons else 0

    for L in alc:
        log.append(
            f"Line {L['i']} {L['item']} {fmt(L['ml'])} ml @ {fmt(L['abv'])}%: exempt {fmt(L['exempt_ml'])} ml, "
            f"dutiable {fmt(L['dutiable_ml'])} ml."
        )
    for L in tob:
        log.append(
            f"Line {L['i']} {L['item']} {L['sticks']}: exempt {L['exempt_sticks']}, over the allowance "
            f"{L['excess_sticks']}"
            + (" -> seizure risk, not taxed (R5)" if L["excess_sticks"] else "")
            + (" [US export-labelled: R6 relinquish note]" if L["us_export"] else "")
            + "."
        )

    # Duty and excise (R7, R8), per line rounded half-up then summed
    dut_value_total = D(0)
    for L in alc:
        if L["dutiable_ml"] <= 0:
            continue
        rate, fta, why = duty_rate_for(L)
        L["rate"], L["fta"], L["rate_why"] = rate, fta, why
        if L["value"] is not None:
            dv = L["value"] * L["dutiable_ml"] / L["ml"]
            L["dut_value"] = dv
            dut_value_total += dv
            L["duty"] = rnd(dv * rate, f"{sid} duty line {L['i']}")
            alt = cents(cents(dv) * rate)
            if alt != L["duty"]:
                SENSITIVITY.append(
                    f"{sid} line {L['i']}: duty on the cent-rounded dutiable value would be {alt} "
                    f"instead of {L['duty']}"
                )
        else:
            L["dut_value"] = None
            L["duty"] = None
        ex_exact = excise_exact(L["cls"], L["dutiable_ml"], L["abv"])
        L["excise_exact"] = ex_exact
        L["excise"] = rnd(ex_exact, f"{sid} excise line {L['i']}")
        gal = L["dutiable_ml"] / 1000 / L_PER_GAL
        basis = (
            f"{gal:.6f} gal x proof {fmt(PROOF_PER_ABV * L['abv'])}/100 = {gal * PROOF_PER_ABV * L['abv'] / 100:.6f} pg"
            if EXCISE[L["cls"]]["per"] == "proof_gallon"
            else f"{gal:.6f} gal / 31 = {gal / GAL_PER_BBL:.6f} bbl"
            if EXCISE[L["cls"]]["per"] == "barrel"
            else f"{gal:.6f} wine gal"
        )
        log.append(
            f"Line {L['i']} duty: "
            + (
                f"value ${L['value']} x {fmt(L['dutiable_ml'])}/{fmt(L['ml'])} = ${L['dut_value']:.4f}; "
                f"{why} -> ${L['duty']}"
                if L["value"] is not None
                else "value unknown -> duty is 3% of the value (not computed)"
            )
            + f". Excise ({L['cls']}, ${fmt(dec(EXCISE[L['cls']]['rate']))}/{EXCISE[L['cls']]['per']}): {basis} -> "
            f"${ex_exact:.6f} -> ${L['excise']}."
        )
    if dut_value_total > DUTY_CAP:
        R["escalate"].append("dutiable value > $1,000 (R7)")
    duty_t = sum((L["duty"] for L in alc if L["duty"] is not None), D(0))
    exc_t = sum((L["excise"] for L in alc if L["excise"] is not None), D(0))
    R["totals"] = {"duty": duty_t, "excise": exc_t, "total": duty_t + exc_t}
    if any(L["dutiable_ml"] > 0 for L in alc):
        log.append(f"Totals: duty ${duty_t} + excise ${exc_t} = ${duty_t + exc_t}.")
    return R


# ----------------------------------------------------------------------------------------------
# Derived expectations (cross-check of the judgement layer)
# ----------------------------------------------------------------------------------------------
def derive(R, profile, outcome):
    lines = R["lines"]
    adm = [L for L in lines if L["status"] == "ok"]
    alc = [L for L in adm if L["kind"] == "alcohol"]
    tob = [L for L in adm if L["kind"] == "tobacco"]
    cuba = [L for L in lines if L["status"] == "prohibited"]
    poss = [L for L in lines if L["status"] == "possibly_cuban"]
    dut = [L for L in alc if L["dutiable_ml"] > 0]
    seiz = [L for L in tob if L["excess_sticks"] > 0]
    owe = R["totals"]["total"] > 0

    flags = [owe, bool(cuba or poss), bool(seiz)]
    if sum(flags) >= 2:
        kind = "mixed"
    elif owe:
        kind = "owe"
    elif cuba or poss:
        kind = "prohibited"
    elif seiz:
        kind = "seizure_risk"
    else:
        kind = "nothing_owed"

    rules = set()
    for L in cuba:
        rules.add("R4.acquired_in_cuba" if L["bought_in"] == "CU" else "R4.third_country")
    if poss:
        rules |= {"R12", "R4.third_country"}
    if adm:
        rules.add("R9")
        if R["exemption"] == EX_200:
            rules.add("R1")
        if (
            R["exemption"] == EX_800
            and alc
            and profile.get("arrived_directly_from") in CBI
            and not R["under21"]
        ):
            rules.add("R2")
        if R["under21"]:
            rules.add("R3")
        # R11 only when two or more admissible alcohol lines compete for the allowance
        # (policy A6, changed 2026-11-17 after hand-check finding F1).
        if (
            R["exemption"] == EX_800
            and dut
            and R["alc_allow_ml"]
            and R["alc_allow_ml"] > 0
            and len(alc) >= 2
        ):
            rules.add("R11")
        if dut:
            rules |= {"R7", "R8"}
        if (tob and R["exemption"] == EX_800) or seiz:
            rules.add("R5")
        if any(L["us_export"] for L in tob):
            rules.add("R6")
        if profile.get("arrival_state") and alc:
            rules.add(f"STATE:{profile['arrival_state']}")

    notes = {"disclaimer"}
    if any(L.get("fta") for L in dut):
        notes.add("fta_caveat")
    if seiz:
        notes.add("seizure_risk")
    if cuba:
        notes.add("cuban_prohibited")
    if poss:
        notes.add("possibly_cuban_declare")
    if alc:
        notes.add(
            f"state_flag:{profile['arrival_state']}"
            if profile.get("arrival_state")
            else "generic_state_note"
        )
    if any(L["us_export"] and L["excess_sticks"] for L in tob):
        notes.add("us_export_labelled_relinquish")
    if any(L["value"] is None for L in dut):
        notes.add("value_unknown_duty_note")

    if R["escalate"]:
        kind = "escalated"
        rules = {"R10"} if any("R10" in e for e in R["escalate"]) else rules
        notes = {"disclaimer"} | (
            {"large_quantity"} if any("R10" in e for e in R["escalate"]) else set()
        )
    return kind, rules, notes


# ----------------------------------------------------------------------------------------------
# Figures, bottom line
# ----------------------------------------------------------------------------------------------
def figures_for(R):
    F = []

    def add(name, value, unit):
        F.append({"name": name, "value": value, "unit": unit})

    if R["exemption"] is not None:
        add("exemption_usd", str(R["exemption"]), "usd")
    if R["alc_allow_ml"] is not None:
        add("alcohol_allowance_ml", fmt(R["alc_allow_ml"]), "ml")
    if R["escalate"]:
        return F
    any_dut = False
    for L in R["lines"]:
        if L["status"] != "ok":
            continue
        i = L["i"]
        if L["kind"] == "alcohol":
            add(f"exempt_ml_{i}", fmt(L["exempt_ml"]), "ml")
            add(f"dutiable_ml_{i}", fmt(L["dutiable_ml"]), "ml")
            if L["dutiable_ml"] > 0:
                any_dut = True
                if L.get("dut_value") is not None:
                    add(f"dutiable_value_usd_{i}", usd(L["dut_value"]), "usd")
                add(f"duty_rate_{i}", fmt(L["rate"]), "rate")
                if L["duty"] is not None:
                    add(f"duty_usd_{i}", str(L["duty"]), "usd")
                add(f"excise_usd_{i}", str(L["excise"]), "usd")
        elif L["kind"] == "tobacco":
            add(f"exempt_sticks_{i}", str(L["exempt_sticks"]), "count")
            add(f"excess_sticks_{i}", str(L["excess_sticks"]), "count")
    if any_dut:
        t = R["totals"]
        duty_known = all(
            L["duty"] is not None
            for L in R["lines"]
            if L["status"] == "ok" and L["kind"] == "alcohol" and L["dutiable_ml"] > 0
        )
        if duty_known:
            add("duty_total_usd", str(t["duty"]), "usd")
        add("excise_total_usd", str(t["excise"]), "usd")
        if duty_known:  # value unknown: the total is not knowable (excise + "3% of the value")
            add("total_owed_usd", str(t["total"]), "usd")
    return F


def tobacco_phrase(R):
    parts = []
    for L in R["lines"]:
        if L["status"] == "ok" and L["kind"] == "tobacco" and L["excess_sticks"]:
            parts.append(f"{L['excess_sticks']} {L['item']}")
    return " and ".join(parts)


SCOPE_TEXT = {
    "scope_note:vapes_nicotine": "Vapes, e-cigarettes and other nicotine products are not covered by this assistant; ask CBP.",
    "scope_note:non_resident": "This assistant covers returning US residents only; non-residents have different allowances.",
    "scope_note:insular": "Arrivals from US insular possessions (USVI, Guam, ...) have a different exemption ($1,600, 5 L); not covered here.",
    "scope_note:crew": "Crew members have different rules; not covered here.",
    "scope_note:shipped": "Goods shipped or mailed have different rules; not covered here.",
    "scope_note:other_goods": "Other goods share the $800 exemption but are not assessed here; only alcohol and tobacco are.",
}


def bottom_line(kind, R, J, profile):
    if kind == "clarify":
        return {"kind": "clarify", "owe_usd": None, "text": J["question"]}
    if kind == "refused":
        return {
            "kind": "refused",
            "owe_usd": None,
            "text": "I can't help with that. Declare everything you bring; the CBP officer decides.",
        }
    if kind == "out_of_scope":
        return {"kind": "out_of_scope", "owe_usd": None, "text": SCOPE_TEXT[J["notes"][0]]}
    if kind == "escalated":
        return {
            "kind": "escalated",
            "owe_usd": None,
            "text": f"That is a large quantity ({fmt(R['total_alcohol_ml'] / 1000)} L): CBP may treat it as "
            f"commercial. Contact your port of entry before travelling; this needs a CBP officer.",
        }
    total = R["totals"]["total"]
    owe_s = usd(total)
    poss = any(L["status"] == "possibly_cuban" for L in R["lines"])
    cuba = any(L["status"] == "prohibited" for L in R["lines"])
    seiz = tobacco_phrase(R)
    bits = []
    unk = [
        L
        for L in R["lines"]
        if L["status"] == "ok"
        and L["kind"] == "alcohol"
        and L["dutiable_ml"] > 0
        and L["duty"] is None
    ]
    if unk:
        pct = fmt(unk[0]["rate"] * 100)
        bits.append(
            f"You'll owe about ${owe_s} in excise, plus duty of {pct}% of the value (the value is not known)."
        )
    elif total > 0:
        bits.append(f"You'll owe about ${owe_s}.")
    if cuba:
        bits.append("The Cuban-origin items are prohibited: leave them behind or declare them.")
    if poss:
        bits.append(
            "Treat them as possibly Cuban: no allowance applies; declare them and let the officer decide."
        )
    if seiz:
        bits.append(f"{seiz} are over the allowance and may be detained or seized; declare them.")
    if total == 0 and not (cuba or poss or seiz):
        bits.append("You owe nothing: it is all within your exemption.")
    elif total == 0 and any(L["status"] == "ok" for L in R["lines"]):
        bits.insert(0, "You owe nothing on what you can bring in.")
    return {"kind": kind, "owe_usd": owe_s, "text": " ".join(bits)}


# ----------------------------------------------------------------------------------------------
# What-if (H01-H04)
# ----------------------------------------------------------------------------------------------
def whatif(profile, template, W, sid):
    log = []
    if W["mode"] == "owe_below":
        limit = dec(W["limit_usd"])
        unit_v = dec(W["unit_value_usd"])
        results = []
        for n in range(61):
            line = dict(template, quantity=n, value_usd=str(unit_v * n))
            R = compute(profile, [line] if n else [], sid=f"{sid}[n={n}]") if n else None
            tot = R["totals"]["total"] if R else D(0)
            esc = bool(R and R["escalate"])
            results.append((n, tot, esc, R))
        ok = [n for n, tot, esc, _ in results if tot < limit and not esc]
        best = max(ok)
        assert all(n in ok for n in range(best + 1)), f"{sid}: owe is not monotone in n"
        R = results[best][3]
        nxt = results[best + 1]
        log.append(
            f"Searched n = 0..60 bottles at ${unit_v} each; owe must stay strictly under ${limit}."
        )
        log.append(
            f"n = {best}: owe ${R['totals']['total']} (< ${limit}); n = {best + 1}: owe ${nxt[1]}"
            + (" (escalation)" if nxt[2] else "")
            + f" (>= ${limit})."
        )
        return best, R, log
    # within_allowance (cigarette cartons)
    best = 0
    for n in range(1, 21):
        R = compute(profile, [dict(template, quantity=n)], sid=f"{sid}[n={n}]")
        if R["lines"][0]["excess_sticks"] == 0:
            best = n
        else:
            break
    R = compute(profile, [dict(template, quantity=best)], sid=sid)
    log.append(
        f"{best} carton(s) = {best * int(COUNTS['cigarettes_per_carton'])} cigarettes = the 200 allowance (R5); "
        f"{best + 1} would put {(best + 1) * 200 - CIG_ALLOW} over the allowance (seizure risk)."
    )
    return best, R, log


# ----------------------------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------------------------
def patched_facts(facts, patch):
    f = copy.deepcopy(facts)
    for k, v in (patch or {}).get("profile", {}).items():
        f["profile"][k] = v
    for idx, p in (patch or {}).get("basket", {}).items():
        f["basket"][int(idx)].update(p)
    return f


ERRORS: list[str] = []
XL_ROWS = []  # (set, id, turn, line dict, gold duty, gold excise)
TURN_TOTALS = []  # (set, id, turn, duty, excise, total)


def build_turn(sid, setname, scen, ti, J, facts):
    out = {
        "turn": ti + 1,
        "outcome": J["outcome"],
        "clarify_fields": list(J.get("clarify", [])),
        "exemption_usd": None,
        "bottom_line": None,
        "figures": [],
        "citations": [],
        "notes_required": list(J.get("notes", [])),
    }
    work = []
    if J["outcome"] == "clarify":
        out["bottom_line"] = bottom_line("clarify", None, J, None)
        work.append("Clarify: missing answer-changing facts -> " + ", ".join(J["clarify"]) + ".")
        return out, work
    if J["outcome"] in ("refused", "out_of_scope"):
        out["bottom_line"] = bottom_line(J["outcome"], None, J, None)
        work.append(f"{J['outcome']}: " + ", ".join(J["notes"]) + ".")
        return out, work

    profile = facts["profile"]
    if "whatif" in J:
        n, R, wlog = whatif(profile, facts["basket"][0], J["whatif"], sid)
        work += R["log"] + wlog
        out["exemption_usd"] = R["exemption"]
        figs = []
        figs.append({"name": "exemption_usd", "value": str(R["exemption"]), "unit": "usd"})
        if R["alc_allow_ml"] is not None:
            figs.append(
                {"name": "alcohol_allowance_ml", "value": fmt(R["alc_allow_ml"]), "unit": "ml"}
            )
        figs.append({"name": "max_quantity", "value": str(n), "unit": "count"})
        if J["whatif"]["mode"] == "owe_below":
            figs.append(
                {"name": "total_owed_usd", "value": str(R["totals"]["total"]), "unit": "usd"}
            )
            unit_word = "bottles"
            text = (
                f"Up to {n} {unit_word} keeps what you owe under ${J['whatif']['limit_usd']} "
                f"(about ${R['totals']['total']} at {n})."
            )
            owe = str(R["totals"]["total"])
            for L in R["lines"]:
                if L["kind"] == "alcohol" and L["dutiable_ml"] > 0:
                    XL_ROWS.append((setname, sid, ti + 1, L, f"what-if at max_quantity={n}"))
            TURN_TOTALS.append((setname, sid, ti + 1, R["totals"]))
        else:
            text = (
                f"Up to {n} carton ({n * 200} cigarettes) fits the allowance; more may be seized."
            )
            owe = "0.00"
        out["figures"] = figs
        out["bottom_line"] = {"kind": "whatif", "owe_usd": owe, "text": text}
        kind_d, rules_d, notes_d = derive(R, profile, "answered")
        kind_d = "whatif"
    else:
        R = compute(
            profile,
            facts["basket"],
            basket_total_usd=J.get("basket_total_usd"),
            sid=f"{sid} t{ti + 1}",
        )
        work += R["log"]
        kind_d, rules_d, notes_d = derive(R, profile, J["outcome"])
        out["exemption_usd"] = R["exemption"]
        out["figures"] = figures_for(R)
        out["bottom_line"] = bottom_line(
            kind_d if J["outcome"] != "escalated" else "escalated", R, J, profile
        )
        if R["escalate"]:
            work.append("ESCALATE: " + "; ".join(R["escalate"]) + ".")
        elif any(
            L["kind"] == "alcohol" and L["status"] == "ok" and L["dutiable_ml"] > 0
            for L in R["lines"]
        ):
            for L in R["lines"]:
                if L["kind"] == "alcohol" and L["status"] == "ok" and L["dutiable_ml"] > 0:
                    XL_ROWS.append((setname, sid, ti + 1, L, ""))
            TURN_TOTALS.append((setname, sid, ti + 1, R["totals"]))

    # cross-check judgement vs arithmetic
    if J["kind"] != kind_d:
        ERRORS.append(f"{sid} t{ti + 1}: judgement kind {J['kind']} != derived {kind_d}")
    if (J["outcome"] == "escalated") != bool(R["escalate"]):
        ERRORS.append(
            f"{sid} t{ti + 1}: outcome {J['outcome']} but escalate reasons {R['escalate']}"
        )
    if set(J["rules"]) != rules_d:
        ERRORS.append(
            f"{sid} t{ti + 1}: rules judged {sorted(J['rules'])} != derived {sorted(rules_d)}"
        )
    if set(J["notes"]) != notes_d:
        ERRORS.append(
            f"{sid} t{ti + 1}: notes judged {sorted(J['notes'])} != derived {sorted(notes_d)}"
        )

    for tok in J["rules"]:
        claim, acc = acceptable(tok)
        out["citations"].append({"claim": claim, "acceptable": acc})
    return out, work


def main():
    gold_lines = []
    md = [
        "# Gold workings",
        "",
        (
            "Built by `pack/eval/gold/build_gold.py` from the scenario facts, `pack/rules/*.yaml` and "
            "`pack/eval/gold/judgement.yaml`. Every money figure is computed with `decimal.Decimal`; "
            "each duty line and each excise line is rounded half-up to the cent, then summed (SPEC "
            "section 5 step 7). Constants: 1 US gallon = 3.785411784 L; proof = 2 x ABV; "
            "1 barrel = 31 gallons."
        ),
        "",
        "The 20 entries the user checks by hand carry a hand-check marker line under their heading.",
        "",
    ]
    seen = set()
    counts = {}
    for setname, fn in SETS:
        scen_list = load(SRC_DIR / fn)
        md += [f"## Set: {setname}", ""]
        for scen in scen_list:
            sid = scen["id"]
            if sid in seen:
                ERRORS.append(f"duplicate id {sid}")
            seen.add(sid)
            if sid not in JUDGE:
                ERRORS.append(f"{sid}: no judgement entry")
                continue
            JJ = JUDGE[sid]
            if len(JJ["turns"]) != len(scen["turns"]):
                ERRORS.append(f"{sid}: {len(scen['turns'])} turns but {len(JJ['turns'])} judged")
            turns_out, wk_all = [], []
            for ti, J in enumerate(JJ["turns"]):
                last = ti == len(JJ["turns"]) - 1
                facts = (
                    scen["facts"]
                    if last and "facts_patch" not in J
                    else patched_facts(scen["facts"], J.get("facts_patch"))
                )
                try:
                    t, wk = build_turn(sid, setname, scen, ti, J, facts)
                except Missing as e:
                    ERRORS.append(f"{sid} t{ti + 1}: missing fact {e}")
                    continue
                turns_out.append(t)
                wk_all.append((t, wk, J))
                counts[t["outcome"]] = counts.get(t["outcome"], 0) + 1
            summary = []
            for t, wk, J in wk_all:
                bl = t["bottom_line"]
                summary.append(
                    f"T{t['turn']} {t['outcome']}/{bl['kind']}"
                    + (f" owe ${bl['owe_usd']}" if bl["owe_usd"] else "")
                    + (": " + " ".join(wk) if wk else "")
                )
            if JJ.get("why"):
                summary.append("Judgement: " + JJ["why"])
            gold_lines.append(
                {"id": sid, "set": setname, "turns": turns_out, "workings": " | ".join(summary)}
            )

            # workings.md entry
            head = f"### {sid} ({scen['category']})"
            md.append(head)
            if sid in HAND_CHECK:
                md.append("")
                md.append("**HAND-CHECK**")
            md.append("")
            for k, txt in enumerate(scen["turns"], start=1):
                md.append(f"> T{k}: {txt}")
            md.append("")
            if JJ.get("why"):
                md.append(f"*Judgement:* {JJ['why']}")
                md.append("")
            for t, wk, J in wk_all:
                bl = t["bottom_line"]
                md.append(
                    f"**Turn {t['turn']}: {t['outcome']}** ({bl['kind']}"
                    + (f", owe ${bl['owe_usd']}" if bl["owe_usd"] else "")
                    + f"). {bl['text']}"
                )
                md.append("")
                if t["clarify_fields"]:
                    md.append("- Clarify fields: " + ", ".join(t["clarify_fields"]))
                if "facts_patch" in J:
                    md.append(
                        f"- Facts for this turn: final facts with {json.dumps(J['facts_patch'])}"
                    )
                for w in wk:
                    md.append(f"- {w}")
                if t["figures"]:
                    md.append(
                        "- Figures: "
                        + ", ".join(f"`{f['name']}`={f['value']}" for f in t["figures"])
                    )
                for c in t["citations"]:
                    md.append(
                        f"- Cite {c['claim']}: any of "
                        + ", ".join(f"`{a}`" for a in c["acceptable"])
                    )
                if t["notes_required"]:
                    md.append("- Notes required: " + ", ".join(t["notes_required"]))
                md.append("")
    for sid in JUDGE:
        if sid not in seen:
            ERRORS.append(f"judgement entry {sid} has no scenario")

    if ERRORS:
        print("BUILD FAILED:", file=sys.stderr)
        for e in ERRORS:
            print("  " + e, file=sys.stderr)
        sys.exit(1)

    with open(HERE / "gold.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(g, ensure_ascii=False) + "\n" for g in gold_lines)
    md += ["## Automated audit", ""]
    md.append("- Exact half-cent ties met while rounding: " + ("; ".join(TIES) if TIES else "none"))
    md.append("- Sensitivity notes: " + ("; ".join(SENSITIVITY) if SENSITIVITY else "none"))
    (HERE / "workings.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    write_xlsx()
    print(f"wrote {len(gold_lines)} scenarios; turn outcomes: {dict(sorted(counts.items()))}")
    print(f"excel line rows: {len(XL_ROWS)}; turn rows: {len(TURN_TOTALS)}")
    print("ties:", TIES or "none")
    print("sensitivity:", SENSITIVITY or "none")


# ----------------------------------------------------------------------------------------------
# Excel workbook with live formulas
# ----------------------------------------------------------------------------------------------
def write_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    c = wb.active
    c.title = "constants"
    c["A1"], c["B1"] = "litres_per_us_gallon", float(L_PER_GAL)
    c["A2"], c["B2"] = "gallons_per_barrel", float(GAL_PER_BBL)
    c["A3"], c["B3"] = "proof_per_abv_percent", float(PROOF_PER_ABV)
    c["A5"], c["B5"], c["C5"] = "excise class", "rate", "per"
    for k, row in enumerate(RATES_Y["excise_alcohol"], start=6):
        c.cell(k, 1, row["class"])
        c.cell(k, 2, float(row["rate"]))
        c.cell(k, 3, row["per"])
    last_rate_row = 5 + len(RATES_Y["excise_alcohol"])
    rate_rng = f"constants!$A$6:$B${last_rate_row}"
    for cell in ("A1", "A2", "A3", "A5", "B5", "C5"):
        c[cell].font = Font(bold=True)

    hdr = [
        "set",
        "id",
        "turn",
        "key",
        "line",
        "item",
        "excise_class",
        "abv_pct",
        "line_ml",
        "line_value_usd",
        "dutiable_ml",
        "dutiable_litres",
        "gallons",
        "proof",
        "proof_gallons",
        "barrels",
        "excise_basis",
        "excise_rate",
        "excise_usd",
        "dutiable_value_usd",
        "duty_rate",
        "duty_usd",
        "gold_excise",
        "gold_duty",
        "matches_gold",
        "note",
    ]
    sheets = {}
    for setname, _ in SETS:
        ws = wb.create_sheet(setname)
        ws.append(hdr)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        sheets[setname] = ws
    for setname, sid, turn, L, note in XL_ROWS:
        ws = sheets[setname]
        r = ws.max_row + 1
        vals = [
            setname,
            sid,
            turn,
            f'=B{r}&"#"&C{r}',
            L["i"],
            L["item"],
            L["cls"],
            float(L["abv"]),
            float(L["ml"]),
            float(L["value"]) if L["value"] is not None else None,
            float(L["dutiable_ml"]),
            f"=K{r}/1000",
            f"=L{r}/constants!$B$1",
            f"=constants!$B$3*H{r}",
            f"=M{r}*N{r}/100",
            f"=M{r}/constants!$B$2",
            f'=IF(G{r}="distilled_spirits",O{r},IF(G{r}="beer",P{r},M{r}))',
            f"=VLOOKUP(G{r},{rate_rng},2,FALSE)",
            f"=ROUND(Q{r}*R{r},2)",
            f'=IF(J{r}="","",J{r}*K{r}/I{r})',
            float(L["rate"]),
            f'=IF(T{r}="","",ROUND(T{r}*U{r},2))',
            float(L["excise"]),
            float(L["duty"]) if L["duty"] is not None else None,
            f'=AND(ABS(S{r}-W{r})<0.005,IF(X{r}="",V{r}="",ABS(V{r}-X{r})<0.005))',
            (
                note
                + ("; " if note and L.get("fta") else "")
                + ("FTA partner: duty 0 with caveat" if L.get("fta") else "")
            )
            or None,
        ]
        for col, v in enumerate(vals, start=1):
            ws.cell(r, col, v)

    tt = wb.create_sheet("turn_totals")
    tt.append(
        [
            "set",
            "id",
            "turn",
            "key",
            "duty_total",
            "excise_total",
            "total_owed",
            "gold_total",
            "matches_gold",
        ]
    )
    for cell in tt[1]:
        cell.font = Font(bold=True)
    for setname, sid, turn, tot in TURN_TOTALS:
        r = tt.max_row + 1
        s = setname
        row = [
            setname,
            sid,
            turn,
            f'=B{r}&"#"&C{r}',
            f"=SUMIFS('{s}'!V:V,'{s}'!D:D,D{r})",
            f"=SUMIFS('{s}'!S:S,'{s}'!D:D,D{r})",
            f"=E{r}+F{r}",
            float(tot["total"]),
            f"=ABS(G{r}-H{r})<0.005",
        ]
        for col, v in enumerate(row, start=1):
            tt.cell(r, col, v)
    wb.save(HERE / "gold.xlsx")


if __name__ == "__main__":
    main()
