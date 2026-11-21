"""Code router: the tools in a fixed order (CLAUDE.md architecture; ablation baseline for the planner).

    normalise_units -> check_restrictions -> determine_exemption -> (clarify?) -> (escalate?)
      -> compute_allowance -> compute_duty_excise -> lookup_state_rule
    what-if questions: whatif_optimise, then the same chain at the answer's quantity

Restrictions run before any calculation (rule 4). Missing facts come from the tools, in the SPEC 5.2
order, never from the model. The router also collects the citations of the rules each tool applied,
for search_regulations to fetch by id (docs/RETRIEVAL.md): the first two per rule, because a mixed
basket can apply more rules than the 5-clause budget holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from src.schemas import (
    Allowance,
    BasketLine,
    DutyExcise,
    Exemption,
    NormalisedLine,
    Profile,
    Restrictions,
    StateFlag,
    WhatIf,
)
from src.tools import (
    ToolError,
    check_restrictions,
    compute_allowance,
    compute_duty_excise,
    determine_exemption,
    lookup_state_rule,
    normalise_units,
    whatif_optimise,
)
from src.tools.check_restrictions import Args as RArgs
from src.tools.common import order_missing, rules
from src.tools.compute_allowance import Args as AArgs
from src.tools.compute_duty_excise import Args as DArgs
from src.tools.determine_exemption import Args as EArgs
from src.tools.lookup_state_rule import Args as SArgs
from src.tools.normalise_units import Args as NArgs
from src.tools.whatif_optimise import Args as WArgs

PER_RULE = 2  # citations passed per applied rule
STATUS_TO_LINE_TYPE = {
    "prohibited": "prohibited",
    "declare_detention_risk": "declare_detention_risk",
    "relinquish_excess": "relinquish_excess",
    "exempt": "nothing_to_pay",
}


@dataclass
class RouteResult:
    outcome: Literal["answered", "clarify", "escalated"]
    missing: list[str] = field(default_factory=list)
    rule_id: str | None = None
    message: str | None = None
    lines: list[NormalisedLine] = field(default_factory=list)
    restrictions: Restrictions | None = None
    exemption: Exemption | None = None
    allowance: Allowance | None = None
    duty: DutyExcise | None = None
    state_flag: StateFlag | None = None
    whatif: WhatIf | None = None
    line_types: list[str] = field(default_factory=list)  # bottom line per basket line
    citations: list[str] = field(default_factory=list)  # rules applied, in order
    trace: list[dict] = field(default_factory=list)  # tool name + compact output

    def tool_outputs(self) -> list[object]:
        return [
            x
            for x in (
                self.restrictions,
                self.exemption,
                self.allowance,
                self.duty,
                self.state_flag,
                self.whatif,
            )
            if x is not None
        ]


def _cite(out: list[str], ids: list[str], n: int = PER_RULE) -> None:
    added = 0
    for c in ids:
        if added >= n:
            break
        if c not in out:
            out.append(c)
            added += 1


def _rule_citations(rule_id: str) -> list[str]:
    return next(
        (x.get("citations", []) for x in rules()["restrictions"] if x["id"] == rule_id),
        [],
    )


def _log(r: RouteResult, tool: str, output: object) -> None:
    dump = (
        output.model_dump(mode="json", exclude_none=True)
        if hasattr(output, "model_dump")
        else output
    )
    r.trace.append({"tool": tool, "output": dump})


def _chain(profile: Profile, basket: list[BasketLine], r: RouteResult) -> RouteResult:
    lines = normalise_units(NArgs(basket=basket))
    r.lines = lines
    _log(
        r,
        "normalise_units",
        [ln.model_dump(mode="json", exclude_none=True) for ln in lines],
    )
    rs = check_restrictions(RArgs(profile=profile, lines=lines))
    r.restrictions = rs
    _log(r, "check_restrictions", rs)
    for h in rs.hits:
        _cite(r.citations, h.citations)
    if lines and set(rs.prohibited_lines) >= {ln.index for ln in lines}:
        # everything is prohibited: no exemption fact can change the answer (SPEC 5.2), so none
        # is asked for (rule 4: restrictions before any calculation)
        r.line_types = ["prohibited"] * len(lines)
        r.outcome = "answered"
        return r
    ex = determine_exemption(EArgs(profile=profile, lines=lines))
    r.exemption = ex
    _log(r, "determine_exemption", ex)
    missing = order_missing(rs.missing + ex.missing)
    if missing:
        r.outcome, r.missing = "clarify", missing
        return r
    if rs.escalate:
        hit = next(h for h in rs.hits if h.outcome == "escalate")
        r.outcome, r.rule_id, r.message = "escalated", hit.rule_id, hit.message
        return r
    _cite(r.citations, ex.citations)
    al = compute_allowance(AArgs(exemption=ex, restrictions=rs, lines=lines))
    r.allowance = al
    _log(r, "compute_allowance", al)
    for rid in dict.fromkeys(a.rule_id for a in al.lines if a.rule_id):
        _cite(
            r.citations, _rule_citations(rid)
        )  # rules applied per line (tobacco over allowance...)
    esc = next((a for a in al.lines if a.status == "escalate"), None)
    if esc:
        r.outcome, r.rule_id, r.message = "escalated", esc.rule_id, esc.message
        return r
    de = compute_duty_excise(DArgs(profile=profile, lines=lines, allowance=al))
    r.duty = de
    _log(r, "compute_duty_excise", de)
    _cite(r.citations, de.citations)
    sf = lookup_state_rule(SArgs(arrival_state=profile.arrival_state))
    if sf:
        r.state_flag = sf
        _log(r, "lookup_state_rule", sf)
        _cite(r.citations, sf.citations, 1)
    owed = {d.line: d.total_usd for d in de.lines}
    for a in al.lines:
        if a.status in ("partly_exempt", "dutiable"):
            r.line_types.append(
                "owe" if owed.get(a.line, Decimal(0)) > 0 else "nothing_to_pay"
            )
        else:
            r.line_types.append(STATUS_TO_LINE_TYPE[a.status])
    r.outcome = "answered"
    return r


def route(
    profile: Profile,
    basket: list[BasketLine],
    owe_less_than_usd: float | None = None,
) -> RouteResult:
    r = RouteResult(outcome="answered")
    try:
        if owe_less_than_usd:
            product = basket[0]
            w = whatif_optimise(
                WArgs(
                    profile=profile,
                    product=product,
                    owe_less_than_usd=owe_less_than_usd,
                )
            )
            _log(r, "whatif_optimise", w)
            at = product.model_copy(
                update={
                    "quantity": product.quantity.model_copy(
                        update={"value": w.max_units}
                    )
                }
            )
            _chain(profile, [at], r)
            r.whatif = w
            r.line_types = []  # a what-if has no bottom line per item
            return r
        return _chain(profile, basket, r)
    except ToolError as e:
        if e.code == "missing_fact":
            r.outcome, r.missing = "clarify", order_missing(e.missing)
        else:
            r.outcome, r.rule_id, r.message = (
                "escalated",
                e.rule_id or e.code,
                e.message,
            )
            _cite(r.citations, e.citations)
        return r
