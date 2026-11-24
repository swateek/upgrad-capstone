"""Declaration checklist PDF (app/checklist.py): built only from what the answer already says."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

from app.checklist import build_pdf, item_lines, to_do

ANSWER = {
    "outcome": "answered",
    "answer": {
        "outcome": "answered",
        "total_usd": 2.97,
        "duty_usd": 2.4,
        "excise_usd": 0.57,
    },
    "card": {
        "bottom_line": "You owe $2.97 on the wine.",
        "items": [{"line": 1, "item": "wine", "type": "owe", "owed_usd": 2.97}],
        "working": [
            "Item 1: 4 x 750 ml = 3 L in total; 1 L duty-free, 2 L over the allowance."
        ],
        "facts_relied_on": [
            "Age: 34",
            "Item 1: 4 bottles, wine, 750 ml each, 13% ABV, $30.00 each, made in Italy",
        ],
        "citations": [
            {
                "id": "19cfr148.33",
                "label": "19 CFR 148.33",
                "as_of": "2026-11-19",
                "url": "https://www.ecfr.gov/x",
            }
        ],
        "state_flag": {
            "state": "HI",
            "name": "Hawaii",
            "note": "Arriving in Hawaii, up to 1 gallon of liquor ...",
            "source": "https://data.capitol.hawaii.gov/x",
            "general_note": "CBP: most state limits apply to residents.",
        },
        "disclaimer": "Estimate only, as of 2026-11-19. The CBP officer decides. Declare everything.",
    },
    "facts": {"profile": {}, "basket": []},
}


def text_of(pdf: bytes) -> str:
    pdfplumber = pytest.importorskip("pdfplumber")
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(p.extract_text() or "" for p in doc.pages)


def test_pdf_carries_the_answer_and_nothing_new():
    pdf = build_pdf(ANSWER, generated=datetime(2026, 11, 22, tzinfo=UTC))
    assert pdf.startswith(b"%PDF")
    t = text_of(pdf)
    for want in (
        "Declaration checklist",
        "You owe $2.97 on the wine.",
        "4 bottles, wine, 750 ml each",
        "Over your allowance",
        "$2.97",
        "Duty $2.40, federal excise $0.57",
        "19 CFR 148.33",
        "Arriving in Hawaii",
        "The CBP officer decides",
        "22 November 2026",
    ):
        assert want in t, want
    # every dollar figure on the checklist is one the answer already gave
    import re

    assert set(re.findall(r"\$[\d,]+\.\d\d", t)) <= {
        "$2.97",
        "$2.40",
        "$0.57",
        "$30.00",
    }


def test_border_steps_follow_the_results():
    rows = to_do(ANSWER)
    assert rows[0].startswith("Declare every item")
    assert any("pay the estimated duty" in r for r in rows)
    assert any("Hawaii note" in r for r in rows)
    banned = dict(
        ANSWER, card=dict(ANSWER["card"], items=[{"line": 1, "type": "prohibited"}])
    )
    assert any("prohibited: declare it" in r for r in to_do(banned))


def test_escalated_lists_the_items_as_stated():
    esc = {
        "outcome": "escalated",
        "answer": {
            "outcome": "escalated",
            "message": "Declare everything; an officer decides.",
        },
        "card": {},
        "facts": {
            "basket": [{"item": "vodka", "quantity": {"value": 2.0, "unit": "bottle"}}]
        },
    }
    t = text_of(build_pdf(esc))
    assert "2 bottle vodka" in t and "To be assessed by the officer" in t
    assert "could not be checked" in t


def test_no_checklist_for_clarify_or_refused():
    for outcome in ("clarify", "refused"):
        with pytest.raises(ValueError):
            build_pdf({"outcome": outcome, "card": {}})


def test_item_lines():
    assert item_lines(ANSWER["card"]) == {
        1: "4 bottles, wine, 750 ml each, 13% ABV, $30.00 each, made in Italy"
    }
