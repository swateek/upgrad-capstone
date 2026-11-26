"""determine_exemption: $800 (19 CFR 148.33) or $200 (148.51), and the 2 L beneficiary allowance.

- $800 needs at least 48 hours abroad (waived for a direct arrival from Mexico, 148.35(a))
  and no use of the exemption in the previous 30 days (148.36).
- Otherwise $200, which is all-or-nothing (148.51(b)).
- 2 L of alcohol instead of 1 L for a direct arrival from a beneficiary country
  (148.33(d)(3)(ii); country list in rates.yaml).
- Arrivals from a US insular possession ($1,600) are out of scope.

Missing facts are reported in `missing` only when they change which exemption applies.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from src.schemas import Exemption, NormalisedLine, Profile
from src.tools.common import ToolError, dec, order_missing, rates, rules

HOURS = {"hours": 1, "days": 24, "weeks": 168}


class Args(BaseModel):
    profile: Profile
    lines: list[NormalisedLine] = []


def trip_hours(profile: Profile) -> Decimal | None:
    if profile.trip is None:
        return None
    return dec(profile.trip.value) * HOURS[profile.trip.unit]


def fits_200(lines: list[NormalisedLine]) -> bool | None:
    """Would the basket pass every $200 limit? None if a price needed for the value test is missing."""
    r = rules()["exemptions"]["short_trip_200"]
    alcohol_ml = sum(
        (
            ln.units * ln.unit_ml
            for ln in lines
            if ln.line.category == "alcohol" and ln.unit_ml
        ),
        Decimal(0),
    )
    cigarettes = sum(ln.count or 0 for ln in lines if ln.line.type == "cigarettes")
    cigars = sum(ln.count or 0 for ln in lines if ln.line.type == "cigars")
    if (
        alcohol_ml > dec(r["max_alcohol_ml"])
        or cigarettes > r["max_cigarettes"]
        or cigars > r["max_cigars"]
    ):
        return False
    if any(ln.line.unit_price_usd is None for ln in lines):
        return None
    value = sum((dec(ln.line.unit_price_usd) * ln.units for ln in lines), Decimal(0))
    return value <= dec(r["max_aggregate_value_usd"])


def determine_exemption(args: Args) -> Exemption:
    p = args.profile
    ex = rules()["exemptions"]
    std, short = ex["standard_800"], ex["short_trip_200"]
    when = std["applies_when"]

    if p.direct_arrival_from in std.get("insular_possessions", []):
        raise ToolError(
            "out_of_scope",
            "Arrivals from a US insular possession use the $1,600 exemption (out of scope).",
            citations=["19cfr148.33"],
        )

    reasons: list[str] = []
    missing: list[str] = []
    waived = p.direct_arrival_from in when["min_hours_waived_for_direct_arrival_from"]
    hours = trip_hours(p)
    long_enough: bool | None
    if waived:
        long_enough = True
        reasons.append(
            f"Direct arrival from {p.direct_arrival_from}: the 48-hour rule does not apply (19 CFR 148.35(a))."
        )
    elif hours is None:
        long_enough = None
    else:
        long_enough = hours >= when["min_hours_abroad"]
        reasons.append(
            f"Trip of {hours} hours: {'at least' if long_enough else 'under'} {when['min_hours_abroad']} hours."
        )

    used = p.exemption_used_last_30_days
    if long_enough is False or used is True:
        kind = "short_trip_200"
        if used:
            reasons.append(
                "Exemption already used in the last 30 days (19 CFR 148.36)."
            )
    elif long_enough is True and used is False:
        kind = "standard_800"
    else:
        fits = fits_200(args.lines) if args.lines else None
        if (
            fits
        ):  # same answer either way: nothing in the basket exceeds the $200 limits
            kind = "short_trip_200"
            reasons.append(
                "Basket is within the $200 limits, so trip length and earlier use do not change the answer."
            )
        else:
            kind = None
            if long_enough is None:
                missing.append("trip_length")
            if used is None:
                missing.append("exemption_used_last_30_days")

    if kind is None:
        return Exemption(kind=None, reasons=reasons, missing=order_missing(missing))

    if kind == "short_trip_200":
        return Exemption(
            kind=kind,
            value_usd=dec(short["max_aggregate_value_usd"]),
            max_cigarettes=short["max_cigarettes"],
            max_cigars=short["max_cigars"],
            max_alcohol_ml=dec(short["max_alcohol_ml"]),
            all_or_nothing=True,
            reasons=reasons,
            citations=short["citations"],
        )

    alc, tob = std["alcohol"], std["tobacco"]
    beneficiary = (
        p.direct_arrival_from in rates()["beneficiary_countries_2l"]["countries"]
    )
    litres = dec(
        alc["beneficiary_country_direct_arrival"]["max_liters"]
        if beneficiary
        else alc["max_liters"]
    )
    if beneficiary:
        reasons.append(
            f"Direct arrival from beneficiary country {p.direct_arrival_from}: up to 2 L, at least 1 L made there (19 CFR 148.33(d)(3)(ii))."
        )
    return Exemption(
        kind=kind,
        value_usd=dec(std["value_usd"]),
        alcohol_l=litres,
        beneficiary_2l=beneficiary,
        max_cigarettes=tob["max_cigarettes"],
        max_cigars=tob["max_cigars"],
        reasons=reasons,
        citations=std["citations"],
    )
