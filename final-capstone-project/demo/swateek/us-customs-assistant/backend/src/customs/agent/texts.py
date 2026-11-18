"""Everything the card says that is not the writer's: figure labels and values, notes, scope and
escalation wording, the disclaimer and the as-of line (SPEC §4). The writer refers to figures and
sources by handle; code renders them from here."""

from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache

import yaml

from customs.config import get_settings
from customs.tools.models import Figure, NLine
from customs.tools.tables import Tables

DISCLAIMER = "Estimate only. The CBP officer's assessment is final. Declare everything you bring."
REFUSAL = "I can't help with that. Declare everything you bring; the CBP officer decides."

NOTES = {
    "seizure_risk": "Tobacco over the allowance may be detained or seized, and penalties can apply. "
    "Declare it; the officer decides.",
    "us_export_labelled_relinquish": "US export-labelled cigarettes over the allowance: you can "
    "give up the excess at entry with no penalty; otherwise it is forfeited and a penalty of at "
    "least $1,000 can apply.",
    "cuban_prohibited": "Cuban-origin alcohol and tobacco can't be brought in as baggage, wherever "
    "you bought them. Leave them behind or declare them.",
    "possibly_cuban_declare": "This brand is also made in Cuba and its origin is unclear, so no "
    "allowance is given for it. Declare it and tell the officer where it was made.",
    "generic_state_note": "Your arrival state may set its own limits or taxes on alcohol.",
    "large_quantity": "More than 12 litres of alcohol: CBP may treat it as commercial. Contact "
    "your port of entry before you travel.",
    "fta_caveat": "Duty-free as a trade-agreement partner's product if it qualifies as "
    "originating; the officer decides.",
    "value_unknown_duty_note": "Duty depends on the value of the alcohol over the allowance (a "
    "percentage of what you paid), so only the excise is shown.",
    "scope_note:other_goods": "Other goods (not alcohol or tobacco) share the same $800 "
    "exemption; they are not assessed here.",
    "scope_note:vapes_nicotine": "Vapes, e-cigarettes and other nicotine products are not covered "
    "by this assistant; ask CBP.",
    "scope_note:non_resident": "This assistant covers returning US residents only; "
    "non-residents have different allowances. Ask CBP.",
    "scope_note:insular": "Arrivals from US insular possessions (USVI, Guam, American Samoa, "
    "Northern Mariana Islands) have a different exemption; not covered here.",
    "scope_note:crew": "Crew members on duty have different allowances; not covered here.",
    "scope_note:shipped": "Goods shipped or mailed home follow different rules; not covered here.",
}

ESCALATIONS = {
    "large_quantity": "You have more than 12 litres of alcohol, which CBP may treat as commercial.",
    "basket_over_800": "Your alcohol and tobacco are worth more than $800, so the full tariff and "
    "the shared exemption apply, which this assistant doesn't cover.",
    "dutiable_over_1000": "More than $1,000 of alcohol is over the allowance, so the flat rate "
    "doesn't apply and the full tariff does.",
    "missing_facts": "We still don't know a fact that changes the answer.",
    "verifier_failed": "We couldn't produce an answer that passed our checks.",
    "budget": "This question needed more work than one answer allows.",
    "tool_error": "A calculation step failed.",
    "malformed_output": "The model's reply couldn't be read.",
    "plan_failed": "We couldn't plan the calculation.",
    "model_unavailable": "The model service is busy or unavailable right now.",
}
HANDOFF = (
    "Please declare everything and ask a CBP officer, or contact the CBP Information Center or "
    "your port of entry before you travel."
)


@lru_cache(maxsize=1)
def _rules_doc() -> dict:
    p = get_settings().pack_dir / "rules" / "rules.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def as_of() -> str:
    return f"Rules as of {_rules_doc()['snapshot']}"


def note_text(note: str, tables: Tables) -> str | None:
    if note == "disclaimer":
        return None
    if note.startswith("state_flag:"):
        return " ".join(tables.states[note.split(":", 1)[1]]["flag"].split())
    if note == "scope_note:russian":
        return " ".join(tables.scope_notes["russian_origin_alcohol"].split())
    if note == "scope_note:family":
        return " ".join(tables.scope_notes["family_groups"].split())
    return NOTES.get(note)


# --- figures -----------------------------------------------------------------------------------

_LINE_FIG = re.compile(
    r"^(exempt_ml|dutiable_ml|dutiable_value_usd|duty_rate|duty_usd|excise_usd|exempt_sticks"
    r"|excess_sticks)_(\d+)$"
)
_LINE_LABELS = {
    "exempt_ml": "duty-free volume",
    "dutiable_ml": "volume over the allowance",
    "dutiable_value_usd": "value over the allowance",
    "duty_rate": "duty rate",
    "duty_usd": "duty",
    "excise_usd": "federal excise",
    "exempt_sticks": "within the allowance",
    "excess_sticks": "over the allowance",
}
_LABELS = {
    "exemption_usd": "your exemption",
    "alcohol_allowance_ml": "alcohol allowance",
    "duty_total_usd": "total duty",
    "excise_total_usd": "total federal excise",
    "total_owed_usd": "total you owe",
    "max_quantity": "most you can bring",
}
ITEM_WORDS = {"sparkling_wine": "sparkling wine", "hard_cider": "hard cider"}


def figure_label(fig: Figure, lines: dict[int, NLine]) -> str:
    m = _LINE_FIG.match(fig.name)
    if m:
        i = int(m.group(2))
        item = lines[i].line.item if i in lines else "item"
        return f"line {i} ({ITEM_WORDS.get(item, item)}): {_LINE_LABELS[m.group(1)]}"
    return _LABELS.get(fig.name, fig.name.replace("_", " "))


def render_value(fig: Figure, lines: dict[int, NLine] | None = None) -> str:
    v = Decimal(fig.value)
    if fig.unit == "usd":
        return f"${v:,.2f}" if v != v.to_integral_value() or "." in fig.value else f"${int(v):,}"
    if fig.unit == "ml":
        return f"{v.normalize():,f} ml" if v != v.to_integral_value() else f"{int(v):,} ml"
    if fig.unit == "rate":
        if v == 0:
            return "free"
        pct = (v * 100).normalize()
        return f"{pct:f}%"
    if fig.unit == "sticks":
        m = _LINE_FIG.match(fig.name)
        item = (
            lines[int(m.group(2))].line.item if (m and lines and int(m.group(2)) in lines) else ""
        )
        return f"{int(v):,} {item}".strip()
    return f"{v.normalize():f}"


def number_forms(fig: Figure) -> set[str]:
    """Spellings of a figure's value the verifier accepts outside a handle (e.g. 800, 800.00)."""
    v = Decimal(fig.value)
    forms = {fig.value, f"{v:f}", f"{v:,f}", f"{v:.2f}", f"{v:,.2f}"}
    if v == v.to_integral_value():
        forms |= {str(int(v)), f"{int(v):,}"}
    if fig.unit == "rate":
        forms.add(f"{(v * 100).normalize():f}")
    if fig.unit == "ml" and v % 1000 == 0:
        forms.add(str(int(v / 1000)))  # "1 litre"
    return forms
