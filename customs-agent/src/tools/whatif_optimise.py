"""whatif_optimise (stretch): the most bottles of one product that owe less than a target.

Runs the same tools for 1, 2, ... units and stops at the target, at the commercial-quantity
threshold (rules.yaml) or at max_units. No arithmetic of its own beyond counting.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from src.schemas import BasketLine, Profile, WhatIf
from src.tools.check_restrictions import Args as RArgs
from src.tools.check_restrictions import check_restrictions
from src.tools.common import ToolError, dec
from src.tools.compute_allowance import Args as AArgs
from src.tools.compute_allowance import compute_allowance
from src.tools.compute_duty_excise import Args as DArgs
from src.tools.compute_duty_excise import compute_duty_excise
from src.tools.determine_exemption import Args as EArgs
from src.tools.determine_exemption import determine_exemption
from src.tools.normalise_units import Args as NArgs
from src.tools.normalise_units import normalise_units


class Args(BaseModel):
    profile: Profile
    product: BasketLine = Field(
        description="One unit of the product; quantity.value is ignored"
    )
    owe_less_than_usd: float = Field(gt=0)
    max_units: int = Field(12, ge=1, le=100)


def owed_for(profile: Profile, line: BasketLine) -> Decimal:
    lines = normalise_units(NArgs(basket=[line]))
    rs = check_restrictions(RArgs(profile=profile, lines=lines))
    if rs.missing:
        raise ToolError("missing_fact", "what-if needs more facts", missing=rs.missing)
    if rs.escalate or rs.prohibited_lines:
        raise ToolError("escalate", "restriction applies", rule_id=rs.hits[0].rule_id)
    ex = determine_exemption(EArgs(profile=profile, lines=lines))
    al = compute_allowance(AArgs(exemption=ex, restrictions=rs, lines=lines))
    return compute_duty_excise(
        DArgs(profile=profile, lines=lines, allowance=al)
    ).total_usd


def whatif_optimise(args: Args) -> WhatIf:
    limit = dec(args.owe_less_than_usd)
    best: tuple[int, Decimal] | None = None
    stopped = "max_units"
    for n in range(1, args.max_units + 1):
        line = args.product.model_copy(
            update={"quantity": args.product.quantity.model_copy(update={"value": n})}
        )
        lines = normalise_units(NArgs(basket=[line]))
        if any(
            h.rule_id == "commercial_quantity"
            for h in check_restrictions(RArgs(profile=args.profile, lines=lines)).hits
        ):
            stopped = "commercial_quantity"
            break
        owed = owed_for(args.profile, line)
        if owed >= limit:
            stopped = "target"
            break
        best = (n, owed)
    if best is None:
        raise ToolError("invalid_input", "even one unit owes the target or more")
    return WhatIf(
        max_units=best[0], owed_usd=best[1], limit_usd=limit, stopped_by=stopped
    )
