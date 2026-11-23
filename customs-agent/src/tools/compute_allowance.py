"""compute_allowance: which part of each line is inside the exemption.

$200 (19 CFR 148.51(b)): all-or-nothing. If any limit (150 ml alcohol, 50 cigarettes,
10 cigars, $200 value) is exceeded, nothing is exempt.

$800 (19 CFR 148.33): alcohol up to the litre allowance, taken from the line with the
highest duty + excise per litre first (148.33(b); ranking basis per litre, SPEC 5.4);
for the 2 L beneficiary allowance at least 1 L must be made in a beneficiary country,
otherwise the allowance is 1 L. Tobacco up to 200 cigarettes and 100 cigars.

Tobacco over the allowance is never priced: the over-allowance rules in rules.yaml
decide the line's status (relinquish, escalate, or declare with detention risk).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from src.schemas import (
    Allowance,
    Exemption,
    LineAllowance,
    NormalisedLine,
    Restrictions,
)
from src.tools.common import ToolError, dec, litres, match, rates, rules
from src.tools.compute_duty_excise import duty_rate, excise_per_litre


class Args(BaseModel):
    exemption: Exemption
    restrictions: Restrictions
    lines: list[NormalisedLine]


def _over_allowance_status(ln: NormalisedLine) -> tuple[str, str | None, str | None]:
    """First over-allowance tobacco rule in rules.yaml order that matches this line."""
    ctx = {
        "category": ln.line.category,
        "export_labelled_us": ln.line.export_labelled_us,
        "claims_american_goods_returned": ln.line.claims_american_goods_returned,
        "over_allowance": True,
    }
    for r in rules()["restrictions"]:
        if match(r["when"], ctx) == "yes":
            return (
                {
                    "relinquish_excess": "relinquish_excess",
                    "escalate": "escalate",
                    "declare_detention_risk": "declare_detention_risk",
                }[r["outcome"]],
                r["id"],
                r.get("message"),
            )
    raise ToolError("invalid_input", f"no over-allowance rule matches line {ln.index}")


def _rank_key(ln: NormalisedLine) -> Decimal:
    """Duty + excise per litre of this line (higher is exempted first)."""
    missing = [
        n
        for n, v in (
            ("origin", ln.line.origin),
            ("unit_price", ln.line.unit_price_usd),
            ("abv", ln.excise_class),
        )
        if v is None
    ]
    if missing:
        raise ToolError(
            "missing_fact",
            f"{ln.line.item}: needed to decide which litre is duty-free",
            missing=missing,
        )
    per_litre_value = (
        dec(ln.line.unit_price_usd)
        * dec(rates()["conversions"]["ml_per_liter"])
        / ln.unit_ml
    )
    rate, _ = duty_rate(ln.line.origin)
    return rate * per_litre_value + excise_per_litre(ln)


def compute_allowance(args: Args) -> Allowance:
    ex, rs = args.exemption, args.restrictions
    if ex.kind is None:
        raise ToolError("missing_fact", "exemption not decided", missing=ex.missing)
    if rs.missing:
        raise ToolError(
            "missing_fact", "restriction check needs more facts", missing=rs.missing
        )

    blocked = {
        h.line: h
        for h in rs.hits
        if h.line is not None and h.outcome in ("prohibited", "escalate")
    }
    out: dict[int, LineAllowance] = {}
    for idx, h in blocked.items():
        out[idx] = LineAllowance(
            line=idx,
            status="prohibited" if h.outcome == "prohibited" else "escalate",
            rule_id=h.rule_id,
            message=h.message,
        )
    live = [
        ln
        for ln in args.lines
        if ln.index not in blocked and ln.line.category in ("alcohol", "tobacco")
    ]
    alcohol = [ln for ln in live if ln.line.category == "alcohol"]
    tobacco = [ln for ln in live if ln.line.category == "tobacco"]
    reasons: list[str] = []
    citations = list(ex.citations)
    failed = False
    allowance_l = Decimal(0)

    if ex.kind == "short_trip_200":
        alc_ml = sum((ln.units * ln.unit_ml for ln in alcohol), Decimal(0))
        cigs = sum(ln.count or 0 for ln in tobacco if ln.line.type == "cigarettes")
        cigars = sum(ln.count or 0 for ln in tobacco if ln.line.type == "cigars")
        if any(ln.line.unit_price_usd is None for ln in live):
            raise ToolError(
                "missing_fact",
                "the $200 exemption needs the value of every item",
                missing=["unit_price"],
            )
        value = sum((dec(ln.line.unit_price_usd) * ln.units for ln in live), Decimal(0))
        tests = [
            (
                alc_ml > ex.max_alcohol_ml,
                f"alcohol {alc_ml:g} ml is over {ex.max_alcohol_ml:g} ml",
            ),
            (
                cigs > ex.max_cigarettes,
                f"{cigs} cigarettes is over {ex.max_cigarettes}",
            ),
            (cigars > ex.max_cigars, f"{cigars} cigars is over {ex.max_cigars}"),
            (value > ex.value_usd, f"value ${value:g} is over ${ex.value_usd:g}"),
            (rs.alcohol_excluded and bool(alcohol), "alcohol is not exempt under 21"),
            (rs.tobacco_excluded and bool(tobacco), "tobacco is not exempt under 21"),
        ]
        broken = [why for bad, why in tests if bad]
        failed = bool(broken)
        if failed:
            reasons.append(
                "$200 exemption lost (all-or-nothing, 19 CFR 148.51(b)): "
                + "; ".join(broken)
                + "."
            )
        for ln in alcohol:
            out[ln.index] = (
                LineAllowance(
                    line=ln.index,
                    status="dutiable",
                    exempt_l=Decimal(0),
                    excess_l=ln.total_l,
                )
                if failed
                else LineAllowance(
                    line=ln.index,
                    status="exempt",
                    exempt_l=ln.total_l,
                    excess_l=Decimal(0),
                )
            )
        for ln in tobacco:
            if failed:
                status, rid, msg = _over_allowance_status(ln)
                out[ln.index] = LineAllowance(
                    line=ln.index,
                    status=status,
                    exempt_count=0,
                    excess_count=ln.count,
                    rule_id=rid,
                    message=msg,
                )
            else:
                out[ln.index] = LineAllowance(
                    line=ln.index,
                    status="exempt",
                    exempt_count=ln.count,
                    excess_count=0,
                )
        exempt_value = Decimal(0) if failed else value
    else:
        # ---- alcohol
        allowance_l = Decimal(0) if rs.alcohol_excluded else ex.alcohol_l
        cap_other = None
        if ex.beneficiary_2l and allowance_l > 0:
            bc = rates()["beneficiary_countries_2l"]["countries"]
            made_there = sum(
                (ln.total_l for ln in alcohol if ln.line.origin in bc), Decimal(0)
            )
            need = dec(
                rules()["exemptions"]["standard_800"]["alcohol"][
                    "beneficiary_country_direct_arrival"
                ]["min_liters_produced_in_beneficiary_countries"]
            )
            if made_there < need:
                allowance_l = dec(
                    rules()["exemptions"]["standard_800"]["alcohol"]["max_liters"]
                )
                reasons.append(
                    f"Only {made_there:g} L made in beneficiary countries (need {need:g} L): 1 L allowance."
                )
            else:
                cap_other = allowance_l - need  # at most 1 L from elsewhere
        if rs.alcohol_excluded and alcohol:
            reasons.append(
                "Under 21: no alcohol in the exemption (19 CFR 148.33(d)(2))."
            )
        total = sum((ln.total_l for ln in alcohol), Decimal(0))
        order = (
            alcohol
            if total <= allowance_l or len(alcohol) <= 1
            else sorted(alcohol, key=_rank_key, reverse=True)
        )
        remaining, other_used = allowance_l, Decimal(0)
        exempt_value = Decimal(0)
        for ln in order:
            take = min(ln.total_l, remaining)
            if (
                cap_other is not None
                and ln.line.origin
                not in rates()["beneficiary_countries_2l"]["countries"]
            ):
                take = min(take, cap_other - other_used)
                other_used += take
            take = litres(max(take, Decimal(0)))
            remaining -= take
            excess = litres(ln.total_l - take)
            status = (
                "exempt"
                if excess == 0
                else ("dutiable" if take == 0 else "partly_exempt")
            )
            out[ln.index] = LineAllowance(
                line=ln.index, status=status, exempt_l=take, excess_l=excess
            )
            if take and ln.line.unit_price_usd is not None:
                exempt_value += dec(ln.line.unit_price_usd) * take * 1000 / ln.unit_ml
        # ---- tobacco
        for kind, limit in (
            ("cigarettes", ex.max_cigarettes),
            ("cigars", ex.max_cigars),
        ):
            group = [ln for ln in tobacco if ln.line.type == kind]
            if not group:
                continue
            pieces = sum(ln.count or 0 for ln in group)
            over = rs.tobacco_excluded or pieces > limit
            for ln in group:
                if over:
                    status, rid, msg = _over_allowance_status(ln)
                    exempt = 0 if rs.tobacco_excluded else None
                    out[ln.index] = LineAllowance(
                        line=ln.index,
                        status=status,
                        exempt_count=exempt,
                        excess_count=None,
                        rule_id=rid,
                        message=msg,
                    )
                    citations += next(
                        r for r in rules()["restrictions"] if r["id"] == rid
                    ).get("citations", [])
                else:
                    out[ln.index] = LineAllowance(
                        line=ln.index,
                        status="exempt",
                        exempt_count=ln.count,
                        excess_count=0,
                    )
                    if ln.line.unit_price_usd is not None:
                        exempt_value += dec(ln.line.unit_price_usd) * ln.units
            if over:
                reasons.append(
                    # the excess stated here, so the writer copies it (Day 10 E27: it subtracted)
                    f"{pieces} {kind} is {pieces - limit} over the {limit} allowance."
                    if not rs.tobacco_excluded
                    else "Under 21: no tobacco in the exemption."
                )
        if exempt_value > ex.value_usd:
            raise ToolError(
                "escalate",
                f"Exempt goods are worth ${exempt_value:.2f}, over the $800 exemption: "
                "splitting the value is not modelled in v1.",
                rule_id=None,
                # the part beyond the exemption is dutiable under the flat-rate band (agent v2, D2-010)
                citations=["19cfr148.33", "htsus9816.00.20"],
            )

    for ln in args.lines:  # other goods: noted, not assessed
        if ln.index not in out and ln.line.category == "other":
            reasons.append(
                f"{ln.line.item}: not assessed (out of scope); it shares the same exemption."
            )
    lines = [out[i] for i in sorted(out)]
    return Allowance(
        exemption=ex.kind,
        lines=lines,
        all_or_nothing_failed=failed,
        alcohol_allowance_l=allowance_l,
        exempt_value_usd=exempt_value.quantize(Decimal("0.01")),
        reasons=reasons,
        citations=list(dict.fromkeys(citations)),
    )
