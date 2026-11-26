"""check_restrictions: rules that apply before any calculation (CLAUDE.md rule 4).

Evaluates every rules.yaml restriction whose `when` keys are known before allocation:
origin bans (Cuba), sanctions escalation (Russia), under-21 exclusions and the
commercial-quantity threshold. Rules that need the allowance (tobacco over the
allowance, export-labelled cigarettes) or the duty (flat-rate band) are evaluated by
compute_allowance and compute_duty_excise.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from src.schemas import NormalisedLine, Profile, Restrictions, RuleHit
from src.tools.common import dec, match, order_missing, rules, words


class Args(BaseModel):
    profile: Profile
    lines: list[NormalisedLine]


def _may_need_origin(rule: dict, ln: NormalisedLine) -> bool:
    ask = rule.get("ask_origin_when")
    if not ask or ln.line.origin is not None:
        return False
    if ln.line.category not in rule["when"].get("category", [ln.line.category]):
        return False
    return ln.line.type in ask.get("types", []) or bool(
        words(ln.line.item) & set(ask.get("item_keywords", []))
    )


def check_restrictions(args: Args) -> Restrictions:
    profile, lines = args.profile, args.lines
    hits: list[RuleHit] = []
    missing: list[str] = []
    prohibited: set[int] = set()
    out = Restrictions()

    # commercial quantity: a basket-level fact
    threshold = next(
        r for r in rules()["restrictions"] if r["id"] == "commercial_quantity"
    )["threshold"]
    alcohol = [
        ln for ln in lines if ln.line.category == "alcohol" and ln.total_l is not None
    ]
    total_l = sum((ln.total_l for ln in alcohol), Decimal(0))
    biggest = max(
        (ln.units for ln in alcohol), default=Decimal(0)
    )  # bottles of one product
    commercial = total_l > dec(threshold["alcohol_total_liters_gt"]) or biggest > dec(
        threshold["same_product_units_gt"]
    )

    for r in rules()["restrictions"]:
        when = r["when"]
        if "commercial_quantity" in when:
            if match(when, {"commercial_quantity": commercial}) == "yes":
                hits.append(
                    RuleHit(
                        rule_id=r["id"],
                        outcome=r["outcome"],
                        message=r.get("message"),
                        citations=r.get("citations", []),
                    )
                )
            continue
        for ln in lines:
            if ln.index in prohibited:
                continue
            ctx = {
                "category": ln.line.category,
                "origin": ln.line.origin,
                "max_age": profile.age,
            }
            result = match(when, ctx)
            if result == "n/a":
                break  # rule belongs to a later stage
            if result == "unknown":
                if (
                    "max_age" in when
                    and profile.age is None
                    and ln.line.category in when.get("category", [])
                ):
                    missing.append("age")
                if "origin" in when and _may_need_origin(r, ln):
                    missing.append("origin")
                continue
            if result != "yes":
                continue
            hits.append(
                RuleHit(
                    rule_id=r["id"],
                    outcome=r["outcome"],
                    line=ln.index,
                    message=r.get("message"),
                    citations=r.get("citations", []),
                )
            )
            if r["outcome"] == "prohibited":
                prohibited.add(ln.index)
            elif r["outcome"] == "exclude_from_exemption":
                if ln.line.category == "alcohol":
                    out.alcohol_excluded = True
                else:
                    out.tobacco_excluded = True

    out.hits = hits
    out.prohibited_lines = sorted(prohibited)
    out.escalate = any(h.outcome == "escalate" for h in hits)
    out.missing = order_missing(missing)
    out.citations = list(dict.fromkeys(c for h in hits for c in h.citations))
    return out
