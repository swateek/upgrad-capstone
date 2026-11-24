"""compute_duty_excise: flat-rate duty and federal excise on the alcohol outside the exemption.

Duty (HTSUS 9816.00.20): on the next $1,000 of dutiable value, at a rate set by where the
goods were made: 3% general, Free for listed trade programmes, 4% for Column 2 countries.
Over $1,000, or with the flat rate already used in the last 30 days, regular tariff rates
apply: out of scope, so the tool escalates.

Excise (TTB): wine and beer per gallon, spirits per proof gallon; due on every excess
litre whatever the duty rate.

Rounding per line (SPEC 5.1): dutiable value to the dollar; duty and excise to the cent,
half-up; totals are sums of the rounded line amounts.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from src.schemas import Allowance, DutyExcise, LineDuty, NormalisedLine, Profile
from src.tools.common import ToolError, cents, dec, dollars, match, rates, rules


class Args(BaseModel):
    profile: Profile
    lines: list[NormalisedLine]
    allowance: Allowance


def duty_rate(origin: str) -> tuple[Decimal, str]:
    r = rates()
    by = r["flat_rate"]["rate_by_origin"]
    for code, prog in r["free_programs"].items():
        if origin in prog["countries"]:
            return dec(by["free_program"]), f"free_program:{code}"
    if origin in r["column2_countries"]:
        return dec(by["column2"]), "column2"
    return dec(by["general"]), "general"


def _excise(ln: NormalisedLine) -> tuple[Decimal, str, bool]:
    """(rate, basis, per proof gallon?) for the line's excise class."""
    ex = rates()["excise"]
    cls = ln.excise_class
    if cls is None:
        raise ToolError(
            "missing_fact",
            f"{ln.line.item}: ABV needed for the excise class",
            missing=["abv"],
        )
    if cls == "spirits":
        if ln.proof is None:
            raise ToolError(
                "missing_fact",
                f"{ln.line.item}: ABV needed for spirits excise",
                missing=["abv"],
            )
        return dec(ex["spirits_per_proof_gallon"]), "per proof gallon", True
    if cls == "beer":
        per_bbl = dec(ex["beer_per_barrel"])
        return (
            per_bbl / dec(rates()["conversions"]["us_gallons_per_beer_barrel"]),
            "per gallon (barrel / 31)",
            False,
        )
    return dec(ex["wine_per_wine_gallon"][cls]), "per wine gallon", False


def excise_per_litre(ln: NormalisedLine) -> Decimal:
    rate, _, proof = _excise(ln)
    per_gal = rate * (ln.proof / 100 if proof else 1)
    return per_gal / dec(rates()["conversions"]["liters_per_us_gallon"])


def compute_duty_excise(args: Args) -> DutyExcise:
    conv = rates()["conversions"]
    lpg = dec(conv["liters_per_us_gallon"])
    by_index = {ln.index: ln for ln in args.lines}
    priced = [a for a in args.allowance.lines if a.excess_l and a.excess_l > 0]
    if priced and args.profile.flat_rate_used is None:
        raise ToolError(
            "missing_fact",
            "flat-rate 30-day use unknown",
            missing=["exemption_used_last_30_days"],
        )
    if priced and args.profile.flat_rate_used:
        raise ToolError(
            "escalate",
            "The flat rate was already used in the last 30 days: regular tariff rates apply "
            "(out of scope).",
            citations=["htsus9816.00.20"],
        )
    out: list[LineDuty] = []
    for a in priced:
        ln = by_index[a.line]
        missing = [
            n
            for n, v in (
                ("origin", ln.line.origin),
                ("unit_price", ln.line.unit_price_usd),
            )
            if v is None
        ]
        if missing:
            raise ToolError(
                "missing_fact", f"{ln.line.item}: needed for the duty", missing=missing
            )
        value = dollars(
            dec(ln.line.unit_price_usd)
            * a.excess_l
            * dec(conv["ml_per_liter"])
            / ln.unit_ml
        )
        rate, basis = duty_rate(ln.line.origin)
        duty = cents(value * rate)
        ex_rate, ex_basis, per_proof = _excise(ln)
        gallons = a.excess_l / lpg
        proof_gal = gallons * ln.proof / 100 if per_proof else None
        excise = cents((proof_gal if per_proof else gallons) * ex_rate)
        out.append(
            LineDuty(
                line=a.line,
                excess_l=a.excess_l,
                dutiable_value_usd=value,
                duty_rate=rate,
                duty_basis=basis,
                duty_usd=duty,
                excise_class=ln.excise_class,
                excise_rate=ex_rate,
                excise_basis=ex_basis,
                gallons=gallons.quantize(Decimal("0.000001")),
                proof_gallons=proof_gal.quantize(Decimal("0.000001"))
                if proof_gal is not None
                else None,
                excise_usd=excise,
                total_usd=duty + excise,
            )
        )
    dutiable = sum((x.dutiable_value_usd for x in out), Decimal(0))
    band = next(r for r in rules()["restrictions"] if r["id"] == "over_flat_rate_band")
    if match(band["when"], {"dutiable_value_over_exemption_usd_gt": dutiable}) == "yes":
        raise ToolError(
            "escalate",
            f"Dutiable value ${dutiable} is over the ${rates()['flat_rate']['band_usd']} "
            "flat-rate band: regular tariff rates apply (out of scope).",
            rule_id=band["id"],
            citations=band.get("citations", []),
        )
    duty = sum((x.duty_usd for x in out), Decimal(0))
    excise = sum((x.excise_usd for x in out), Decimal(0))
    citations = (
        list(rates()["flat_rate"]["citations"][:1]) + ["ttb-tax-rates"] if out else []
    )
    return DutyExcise(
        lines=out,
        dutiable_value_usd=dutiable,
        duty_usd=duty,
        excise_usd=excise,
        total_usd=duty + excise,
        citations=citations,
    )
