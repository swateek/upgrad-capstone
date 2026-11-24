"""The answer card (SPEC §4) and its builders. Code owns every field except the writer's bottom
line and working, which arrive with handles ([F1], [S1]) and are rendered here."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from customs.agent import texts
from customs.retrieval.service import Source
from customs.tools.models import Assessment, Figure, NLine, Profile
from customs.tools.tables import Tables

HANDLE = re.compile(r"\[(F|S)(\d+)\]")


class Card(BaseModel):
    outcome: str
    kind: str
    bottom_line: str
    working: list[str] = Field(default_factory=list)
    facts_relied_on: list[dict[str, str]] = Field(default_factory=list)
    notes: list[dict[str, str]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    figures: list[dict[str, str]] = Field(default_factory=list)
    owe_usd: str | None = None
    exemption_usd: int | None = None
    clarify_question: str | None = None
    clarify_fields: list[str] = Field(default_factory=list)
    handoff: dict[str, Any] | None = None
    citations: list[str] = Field(default_factory=list)  # clause ids (what the scorer reads)
    as_of: str = Field(default_factory=texts.as_of)
    disclaimer: str = texts.DISCLAIMER
    meta: dict[str, Any] = Field(default_factory=dict)


# --- facts relied on ---------------------------------------------------------------------------


def facts_relied_on(profile: Profile, lines: list[NLine], defaults: list[str]) -> list[dict]:
    p = profile
    out = []

    def add(label: str, value: Any) -> None:
        if value is not None and value != "":
            out.append({"label": label, "value": str(value)})

    add("Age", p.age)
    if p.trip_hours is not None:
        th = p.trip_hours
        add("Time away", th if isinstance(th, str) else f"{th:g} hours")
    add("Arrived directly from", p.arrived_directly_from)
    if p.exemption_used_last_30_days is not None:
        add("Exemption used in the last 30 days", "yes" if p.exemption_used_last_30_days else "no")
    add("Arrival state", p.arrival_state)
    for nl in lines:
        ln = nl.line
        bits = [texts.ITEM_WORDS.get(ln.item, ln.item)]
        if nl.volume_ml is not None:
            bits.append(f"{nl.volume_ml.normalize():f} ml")
        if nl.sticks is not None:
            bits.append(f"{nl.sticks} sticks")
        if nl.abv is not None:
            bits.append(f"{nl.abv.normalize():f}% ABV" + (" (default)" if nl.abv_defaulted else ""))
        if ln.value_usd is not None:
            bits.append(f"${ln.value_usd:,.2f}")
        if ln.origin:
            bits.append(f"made in {ln.origin}")
        add(f"Line {nl.index}", ", ".join(bits))
    for d in defaults:
        add("Default used", d)
    return out


def figure_rows(figs: list[Figure], lines: list[NLine]) -> list[dict]:
    by_index = {nl.index: nl for nl in lines}
    return [
        {
            "handle": f"F{i}",
            "name": f.name,
            "label": texts.figure_label(f, by_index),
            "value": f.value,
            "unit": f.unit,
            "display": texts.render_value(f, by_index),
        }
        for i, f in enumerate(figs, start=1)
    ]


def render(text: str, figures: list[dict], sources: list[Source]) -> str:
    figs = {r["handle"]: r["display"] for r in figures}
    srcs = {s.handle: s.citation for s in sources}

    def sub(m: re.Match) -> str:
        h = f"{m.group(1)}{m.group(2)}"
        if m.group(1) == "F":
            return figs.get(h, m.group(0))
        return f"({srcs[h]})" if h in srcs else m.group(0)

    return re.sub(r"\s+\(", " (", HANDLE.sub(sub, text)).strip()


def note_rows(notes: list[str], tables: Tables) -> list[dict]:
    out = []
    for n in notes:
        t = texts.note_text(n, tables)
        if t:
            out.append({"id": n, "text": t})
    return out


# --- builders ----------------------------------------------------------------------------------


def refused(wording: str, rule: str) -> Card:
    return Card(
        outcome="refused",
        kind="refused",
        bottom_line=wording,
        notes=[{"id": "declare_everything", "text": "Declare everything you bring."}],
        meta={"guard": rule},
    )


def clarify(question: str, fields: list[str]) -> Card:
    return Card(
        outcome="clarify",
        kind="clarify",
        bottom_line=question,
        clarify_question=question,
        clarify_fields=fields,
    )


def out_of_scope(notes: list[str], tables: Tables) -> Card:
    rows = note_rows(notes, tables) or note_rows(["scope_note:other_goods"], tables)
    return Card(
        outcome="out_of_scope",
        kind="out_of_scope",
        bottom_line=rows[0]["text"],
        notes=rows,
    )


def escalated(
    reason: str,
    detail: str | None = None,
    handoff: dict | None = None,
    assessment: Assessment | None = None,
    tables: Tables | None = None,
    profile: Profile | None = None,
) -> Card:
    head = texts.ESCALATIONS.get(reason, texts.ESCALATIONS["tool_error"])
    card = Card(
        outcome="escalated",
        kind="escalated",
        bottom_line=f"{head} {texts.HANDOFF}",
        handoff=handoff or {"reason": reason},
        meta={"escalation": reason, **({"detail": detail} if detail else {})},
    )
    if assessment is not None and tables is not None:
        card.notes = note_rows([n for n in assessment.notes if n != "disclaimer"], tables)
        card.exemption_usd = assessment.exemption_usd
        if profile is not None:
            card.facts_relied_on = facts_relied_on(
                profile, assessment.lines, assessment.defaults_used
            )
    return card


def answered(
    a: Assessment,
    bottom_line: str,
    working: list[str],
    sources: list[Source],
    profile: Profile,
    tables: Tables,
) -> Card:
    figs = figure_rows(a.figures, a.lines)
    return Card(
        outcome=a.outcome,
        kind=a.kind,
        bottom_line=render(bottom_line, figs, sources),
        working=[render(w, figs, sources) for w in working],
        facts_relied_on=facts_relied_on(profile, a.lines, a.defaults_used),
        notes=note_rows(a.notes, tables),
        sources=[s.as_dict() | {"citation": s.citation} for s in sources],
        figures=figs,
        owe_usd=None if a.owe_usd is None else str(a.owe_usd),
        exemption_usd=a.exemption_usd,
        citations=[s.clause_id for s in sources],
    )
