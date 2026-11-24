"""Test helper: run the calculator tools in order on a scenario's facts.

This is not the code router (agent code waits for the Day 4 gate); it only chains the
tools so tests can compare their outputs with the gold in eval/dev_set.jsonl.
"""

from __future__ import annotations

from decimal import Decimal

from src.schemas import Amount, BasketLine, Profile
from src.tools import (
    ToolError,
    check_restrictions,
    compute_allowance,
    compute_duty_excise,
    determine_exemption,
    normalise_units,
)
from src.tools.check_restrictions import Args as RArgs
from src.tools.common import order_missing
from src.tools.compute_allowance import Args as AArgs
from src.tools.compute_duty_excise import Args as DArgs
from src.tools.determine_exemption import Args as EArgs
from src.tools.normalise_units import Args as NArgs

STATUS_TO_BOTTOM_LINE = {
    "prohibited": "prohibited",
    "declare_detention_risk": "declare_detention_risk",
    "relinquish_excess": "relinquish_excess",
    "exempt": "nothing_to_pay",
}


def line_from_fact(f: dict) -> BasketLine:
    t = f["type"]
    t = "sparkling_wine" if "sparkling" in t else t
    return BasketLine(
        item=f["item"],
        category=f["category"],
        type=t,
        quantity=Amount(**f["quantity"]),
        size=Amount(value=f["unit_ml"], unit="ml") if f.get("unit_ml") else None,
        abv=f.get("abv"),
        unit_price_usd=f.get("unit_price_usd"),
        origin=f.get("origin"),
        bought_where=f.get("bought_where"),
        export_labelled_us=f.get("export_labelled_us", False),
    )


def profile_from_fact(p: dict) -> Profile:
    return Profile(**{k: v for k, v in p.items() if v is not None})


def run(profile: Profile, basket: list[BasketLine]) -> dict:
    """Return {outcome, missing?, bottom_line?, total_usd?, duty?, allowance?}."""
    try:
        lines = normalise_units(NArgs(basket=basket))
        rs = check_restrictions(RArgs(profile=profile, lines=lines))
        ex = determine_exemption(EArgs(profile=profile, lines=lines))
        missing = order_missing(rs.missing + ex.missing)
        if missing:
            return {"outcome": "clarify", "missing": missing}
        if rs.escalate:
            return {
                "outcome": "escalated",
                "rule_id": next(h.rule_id for h in rs.hits if h.outcome == "escalate"),
            }
        al = compute_allowance(AArgs(exemption=ex, restrictions=rs, lines=lines))
        if any(a.status == "escalate" for a in al.lines):
            return {
                "outcome": "escalated",
                "rule_id": next(a.rule_id for a in al.lines if a.status == "escalate"),
            }
        de = compute_duty_excise(DArgs(profile=profile, lines=lines, allowance=al))
    except ToolError as e:
        if e.code == "missing_fact":
            return {"outcome": "clarify", "missing": e.missing}
        return {
            "outcome": "escalated" if e.code == "escalate" else e.code,
            "rule_id": e.rule_id,
            "message": e.message,
        }
    owed = {d.line: d.total_usd for d in de.lines}
    bottom = []
    for a in al.lines:
        if a.status in ("partly_exempt", "dutiable"):
            bottom.append(
                "owe" if owed.get(a.line, Decimal(0)) > 0 else "nothing_to_pay"
            )
        else:
            bottom.append(STATUS_TO_BOTTOM_LINE[a.status])
    return {
        "outcome": "answered",
        "bottom_line": bottom,
        "total_usd": de.total_usd,
        "duty": de,
        "allowance": al,
        "exemption": ex,
        "restrictions": rs,
    }
