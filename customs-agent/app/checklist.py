"""Declaration checklist as a PDF (stretch, mentor plan): what to declare, what was worked out, and
what it relies on, to carry to the border.

Built only from one answer the API already returned (the answer card, its facts and citations):
it adds no number, rule or claim of its own. Every figure on it is a tool output that the
verifier checked. Only answered and escalated turns get a checklist: a clarify or refused turn
has nothing settled to declare.
"""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

CHECKLIST_OUTCOMES = ("answered", "escalated")

# same words as the web app's answer slip (web/src/format.ts LINE_TEXT)
LINE_TEXT = {
    "owe": "Over your allowance",
    "nothing_to_pay": "Within your allowance",
    "prohibited": "Prohibited",
    "declare_detention_risk": "Over the tobacco allowance: may be detained",
    "relinquish_excess": "Over the allowance: hand the excess to CBP",
}

INK = colors.HexColor("#14213d")
SOFT = colors.HexColor("#4a5672")
RULE = colors.HexColor("#d3d9e3")
STAMP = colors.HexColor("#2457a6")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    s = {
        "body": ParagraphStyle(
            "body",
            parent=base,
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=INK,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base,
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=SOFT,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=INK,
        ),
        "h": ParagraphStyle(
            "h",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            spaceBefore=12,
            spaceAfter=4,
            textColor=INK,
        ),
        "bottom": ParagraphStyle(
            "bottom",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=STAMP,
            alignment=TA_LEFT,
        ),
    }
    s["cell"] = ParagraphStyle("cell", parent=s["body"], fontSize=9, leading=12)
    s["num"] = ParagraphStyle("num", parent=s["cell"], alignment=TA_RIGHT)
    return s


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text), style)


def _money(x: float | None) -> str:
    return f"${x:,.2f}" if x is not None else ""


def item_lines(card: dict) -> dict[int, str]:
    """'Item 1: 4 bottles, wine, ...' from the facts relied on, by line number."""
    out: dict[int, str] = {}
    for f in card.get("facts_relied_on") or []:
        if m := re.match(r"Item (\d+): (.+)", f):
            out[int(m.group(1))] = m.group(2)
    return out


def basket_lines(resp: dict) -> dict[int, str]:
    """Fallback when the card lists no facts (an escalated turn): the items as stated."""
    out: dict[int, str] = {}
    for n, b in enumerate((resp.get("facts") or {}).get("basket") or [], 1):
        q = b.get("quantity") or {}
        qty = f"{q.get('value', '')} {q.get('unit', '')}".strip()
        qty = re.sub(r"^(\d+)\.0\b", r"\1", qty)
        out[n] = f"{qty} {b.get('item', '')}".strip()
    return out


class TickBox(Flowable):
    """An empty square to tick by hand (the built-in PDF fonts have no box glyph)."""

    def __init__(self, size: float = 9) -> None:
        super().__init__()
        self.size = size

    def wrap(self, *_):
        return self.size, self.size + 3

    def draw(self) -> None:
        self.canv.setStrokeColor(INK)
        self.canv.setLineWidth(0.8)
        self.canv.rect(0, 0, self.size, self.size)


def _checkbox_table(rows: list[str], st: dict) -> Table:
    data = [[TickBox(), _p(r, st["body"])] for r in rows]
    t = Table(data, colWidths=[0.25 * inch, 6.5 * inch])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (0, -1), 4),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def to_do(resp: dict) -> list[str]:
    """What the traveller does at the border, from the outcome and the line results only."""
    card, outcome = resp.get("card") or {}, resp.get("outcome")
    types = {i.get("type") for i in card.get("items") or []}
    rows = [
        "Declare every item on this list to the CBP officer, on your declaration or at the kiosk."
    ]
    if outcome == "escalated":
        rows.append(
            "This estimate could not be checked: the officer will assess everything."
        )
    if "prohibited" in types:
        rows.append(
            "An item is prohibited: declare it; the officer decides what happens to it."
        )
    if "declare_detention_risk" in types or "relinquish_excess" in types:
        rows.append(
            "An item is over its allowance: expect the officer to hold or take the excess."
        )
    if "owe" in types:
        rows.append("Have a way to pay the estimated duty and excise at the port.")
    rows.append("Keep receipts for what you bought abroad where you can reach them.")
    rows.append("Check the facts below: if one is wrong, this estimate is wrong too.")
    if card.get("state_flag"):
        rows.append(
            f"Read the {card['state_flag']['name']} note: state rules apply as well."
        )
    return rows


def build_pdf(resp: dict, *, generated: datetime | None = None) -> bytes:
    """resp: one /api/ask or /api/edit response (answered or escalated)."""
    if resp.get("outcome") not in CHECKLIST_OUTCOMES:
        raise ValueError(f"no checklist for a {resp.get('outcome')} turn")
    st = _styles()
    card = resp.get("card") or {}
    answer = resp.get("answer") or {}
    when = (generated or datetime.now(UTC)).strftime("%d %B %Y")
    story: list = [
        _p("Declaration checklist", st["title"]),
        _p(
            f"DeclareRight estimate, made {when}. Bring this with you; the CBP officer decides.",
            st["small"],
        ),
        Spacer(1, 10),
    ]
    bottom = card.get("bottom_line") or answer.get("message") or ""
    if bottom:
        story.append(_p(bottom, st["bottom"]))

    # the items to declare
    lines = item_lines(card) or basket_lines(resp)
    items = card.get("items") or [
        {"line": n, "item": "", "type": None} for n in sorted(lines)
    ]
    if items:
        story.append(_p("Items to declare", st["h"]))
        data = [
            [
                _p(h, st["cell"])
                for h in ("#", "What you are bringing", "Result", "Estimated")
            ]
        ]
        for i in items:
            n = i.get("line")
            owed = i.get("owed_usd")
            if owed is None and i.get("type") == "nothing_to_pay":
                owed = 0.0
            data.append(
                [
                    _p(str(n), st["cell"]),
                    _p(lines.get(n) or i.get("item") or "", st["cell"]),
                    _p(
                        LINE_TEXT.get(i.get("type"), "To be assessed by the officer"),
                        st["cell"],
                    ),
                    _p(_money(owed), st["num"]),
                ]
            )
        if answer.get("total_usd"):
            data.append(
                [
                    "",
                    _p(
                        f"Duty {_money(answer.get('duty_usd') or 0)}, federal excise "
                        f"{_money(answer.get('excise_usd') or 0)}",
                        st["small"],
                    ),
                    _p("Total", st["cell"]),
                    _p(_money(answer["total_usd"]), st["num"]),
                ]
            )
        t = Table(
            data,
            colWidths=[0.35 * inch, 3.6 * inch, 1.85 * inch, 0.95 * inch],
            repeatRows=1,
        )
        t.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ]
            )
        )
        story.append(t)

    story += [_p("At the border", st["h"]), _checkbox_table(to_do(resp), st)]

    if card.get("working"):
        story.append(_p("How it was worked out", st["h"]))
        story += [_p(w, st["body"]) for w in card["working"]]
    if card.get("facts_relied_on"):
        story.append(_p("Facts this relies on", st["h"]))
        story += [_p(f, st["body"]) for f in card["facts_relied_on"]]
    if card.get("assumptions"):
        story.append(_p("Assumed because it was not answered", st["h"]))
        story += [_p(a, st["body"]) for a in card["assumptions"]]
    if sf := card.get("state_flag"):
        block = [
            _p(f"Arriving in {sf['name']}", st["h"]),
            _p(sf["note"], st["body"]),
        ]
        if sf.get("general_note"):
            block.append(_p(sf["general_note"], st["small"]))
        block.append(_p(f"Source: {sf['source']}", st["small"]))
        story.append(KeepTogether(block))
    if card.get("citations"):
        story.append(_p("Rules behind this answer", st["h"]))
        for c in card["citations"]:
            label = c.get("label") or c.get("id")
            bits = [label]
            if c.get("as_of"):
                bits.append(f"as of {c['as_of']}")
            if c.get("url"):
                bits.append(c["url"])
            story.append(_p("; ".join(bits), st["small"]))
    story += [
        Spacer(1, 14),
        _p(
            card.get("disclaimer")
            or "Estimate only. The CBP officer decides. Declare everything.",
            st["body"],
        ),
    ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Declaration checklist",
        author="DeclareRight",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SOFT)
    canvas.drawString(
        doc.leftMargin,
        0.5 * inch,
        "Estimate only, not legal advice. Rules can change: check the sources listed.",
    )
    canvas.drawRightString(LETTER[0] - doc.rightMargin, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()
