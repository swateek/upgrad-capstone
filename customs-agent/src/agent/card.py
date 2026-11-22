"""The answer card, built in code from the tool outputs (SPEC 4): bottom line per item, working,
facts relied on, citations with as-of dates, state flag, disclaimer. The writer only explains it."""

from __future__ import annotations

from decimal import Decimal

from src.agent.router import RouteResult
from src.schemas import Clauses, Profile

EXEMPTION_LABEL = {
    "standard_800": "$800 personal exemption (abroad 48 hours or more, not used in the last 30 days)",
    "short_trip_200": "$200 short-trip exemption (all-or-nothing)",
}
LINE_TEXT = {
    "owe": "you owe duty and tax on the part over your allowance",
    "nothing_to_pay": "nothing to pay",
    "prohibited": "prohibited: you cannot bring it in",
    "declare_detention_risk": "over the tobacco allowance: declare it; the excess may be detained or seized",
    "relinquish_excess": "over the allowance: hand the excess to CBP at entry",
}
DUTY_BASIS = {"general": "flat rate", "column_2": "Column 2 flat rate"}


def money(x: Decimal | float) -> str:
    return f"${Decimal(str(x)):,.2f}"


def litres(x: Decimal | float) -> str:
    return f"{Decimal(str(x)).normalize():f} L"


def plural(unit: str, n: float) -> str:
    """ "bottle" x 4 -> "bottles"; units that already carry a count ("box of 10") stay as stated."""
    if (
        n == 1
        or " of " in unit
        or unit.endswith("s")
        or unit in ("ml", "cl", "l", "fl oz")
    ):
        return unit
    return unit + ("es" if unit.endswith(("x", "ch", "sh")) else "s")


def country(code: str | None) -> str | None:
    """ISO code -> name for the traveller ("IT" -> "Italy"); the code itself if unknown."""
    if not code:
        return code
    try:
        import pycountry

        c = pycountry.countries.get(alpha_2=code)
    except ImportError:  # pragma: no cover
        return code
    return (getattr(c, "common_name", None) or c.name) if c else code


def facts_relied_on(profile: Profile, lines, *, age_21_plus: bool = False) -> list[str]:
    p = profile
    out = []
    if age_21_plus:
        out.append("Age: 21 or over")
    else:
        out.append(f"Age: {p.age}" if p.age is not None else "Age: not stated")
    out.append(
        f"Time abroad: {p.trip.value:g} {p.trip.unit}"
        if p.trip
        else "Time abroad: not stated"
    )
    if p.direct_arrival_from:
        out.append(f"Arriving directly from: {country(p.direct_arrival_from)}")
    if p.exemption_used_last_30_days is not None:
        out.append(
            "Exemption used in the last 30 days: "
            + ("yes" if p.exemption_used_last_30_days else "no")
        )
    if p.arrival_state:
        out.append(f"Arrival state: {p.arrival_state}")
    for n in lines:
        b = n.line
        bits = [
            f"{b.quantity.value:g} {plural(b.quantity.unit, b.quantity.value)}",
            b.item,
        ]
        if n.unit_ml:
            bits.append(f"{Decimal(n.unit_ml).normalize():f} ml each")
        if b.abv:
            bits.append(f"{b.abv:g}% ABV")
        if b.unit_price_usd is not None:
            bits.append(f"{money(b.unit_price_usd)} each")
        if b.origin:
            bits.append(f"made in {country(b.origin)}")
        out.append(f"Item {n.index}: " + ", ".join(bits))
    return out


def working(r: RouteResult) -> list[str]:
    steps: list[str] = []
    ex, al, de = r.exemption, r.allowance, r.duty
    if r.restrictions:
        for h in r.restrictions.hits:
            if h.outcome in ("prohibited", "escalate") and h.message:
                steps.append(f"Item {h.line}: {h.message}" if h.line else h.message)
    if ex and ex.kind:
        s = EXEMPTION_LABEL[ex.kind]
        has_alcohol = any(n.line.category == "alcohol" for n in r.lines)
        if r.restrictions and r.restrictions.alcohol_excluded:
            s += "; alcohol allowance 0 L: under 21, no alcohol is duty-free"
        elif ex.kind == "standard_800" and has_alcohol:
            s += f"; alcohol allowance {litres(ex.alcohol_l or 0)}"
        steps.append("Exemption: " + s + ". " + " ".join(ex.reasons))
    if al:
        steps += al.reasons
        by_index = {n.index: n for n in r.lines}
        for a in al.lines:
            n = by_index.get(a.line)
            if (
                a.exempt_l is not None
                and a.excess_l is not None
                and (a.excess_l or a.exempt_l)
            ):
                brought = (
                    f"{n.units.normalize():f} x {Decimal(n.unit_ml).normalize():f} ml"
                    f" = {litres(n.total_l)} in total; "
                    if n is not None and n.unit_ml and n.total_l is not None
                    else ""
                )
                steps.append(
                    f"Item {a.line}: {brought}{litres(a.exempt_l)} duty-free, "
                    f"{litres(a.excess_l)} over the allowance."
                )
            elif n is not None and n.count is not None and ex is not None:
                # tobacco: state the count and the allowance, so the writer never has to
                kind = n.line.type  # cigarettes | cigars
                limit = ex.max_cigarettes if kind == "cigarettes" else ex.max_cigars
                verdict = "within" if a.status == "exempt" else "over"
                steps.append(
                    f"Item {a.line}: {n.count} {kind}; your allowance is {limit} {kind}: {verdict} it."
                    + (f" {a.message}" if a.message else "")
                )
            elif a.message:
                steps.append(f"Item {a.line}: {a.message}")
    if de:
        for d in de.lines:
            rate = f"{(d.duty_rate * 100).normalize():f}%"
            basis = DUTY_BASIS.get(
                d.duty_basis,
                d.duty_basis.replace("free_program:", "free under trade programme "),
            )
            gal = (d.proof_gallons or d.gallons).quantize(Decimal("0.001"))
            unit = "proof gallons" if d.proof_gallons is not None else "gallons"
            steps.append(
                f"Item {d.line}: dutiable value {money(d.dutiable_value_usd)}; duty {rate} ({basis}) = {money(d.duty_usd)}; "
                f"federal excise {gal} {unit} at {money(d.excise_rate)} {d.excise_basis} = {money(d.excise_usd)}; "
                f"item total {money(d.total_usd)}."
            )
        if de.lines:
            steps.append(
                f"Total: duty {money(de.duty_usd)} + excise {money(de.excise_usd)} = {money(de.total_usd)}."
            )
    if r.whatif:
        steps.append(
            f"What-if: up to {r.whatif.max_units} bottles owe {money(r.whatif.owed_usd)}, "
            f"under your {money(r.whatif.limit_usd)} limit."
        )
    # The arrival-state note is not a step of the calculation: the card shows it in its own
    # section (state_flag), and it is kept away from the writer, which converted its gallons
    # into litres and failed the verifier (COMPENSATIONS row 18).
    return steps


def bottom_line_items(r: RouteResult) -> list[str]:
    out = []
    owed = {d.line: d.total_usd for d in (r.duty.lines if r.duty else [])}
    for n, t in zip(r.lines, r.line_types, strict=False):
        text = LINE_TEXT[t]
        if t == "owe":
            text = f"owe {money(owed[n.index])}"
        out.append(f"Item {n.index} ({n.line.item}): {text}")
    if r.whatif:
        out.append(
            f"Up to {r.whatif.max_units} bottles keep what you owe under {money(r.whatif.limit_usd)} "
            f"(you would owe {money(r.whatif.owed_usd)})."
        )
    return out


def as_of(clauses: Clauses | None) -> str | None:
    dates = [c.as_of for c in (clauses.clauses if clauses else []) if c.as_of]
    return max(dates) if dates else None


def disclaimer(date: str | None) -> str:
    when = f", as of {date}" if date else ""
    return f"Estimate only{when}. The CBP officer decides. Declare everything."
