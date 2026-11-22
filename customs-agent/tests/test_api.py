"""HTTP API with a scripted model, fake search and a file tracer (no network, no models)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api import RateLimiter, Service, create_app, pretty_citation
from src.safety.pii import mask_text
from src.tracing import FileTracer
from tests.test_agent import DEV, GOOD_D01, ScriptedLLM, fake_search, intake_for

CHUNKS = [
    {
        "citation_id": "19cfr148.33",
        "authority": "primary_regulation",
        "heading_path": "§ 148.33 Articles acquired abroad.",
        "text": "(a) Articles acquired abroad ...",
        "metadata": {
            "title": "19 CFR Part 148",
            "source_url": "https://www.ecfr.gov/x",
            "as_of": "2026-11-19",
        },
    },
    {
        "citation_id": "19cfr148.64",
        "authority": "hard_negative",
        "heading_path": "§ 148.64 Crewmembers",
        "text": "crew",
        "metadata": {},
    },
]


def client(tmp_path, llm=None) -> tuple[TestClient, FileTracer]:
    tracer = FileTracer(tmp_path / "trace.jsonl")
    llm = llm or ScriptedLLM(
        intake=[intake_for("D01")],
        planner=[
            {
                "steps": [
                    "normalise_units",
                    "check_restrictions",
                    "determine_exemption",
                    "compute_allowance",
                    "compute_duty_excise",
                    "search_regulations",
                ],
                "reason": "x",
            }
        ],
        writer=[GOOD_D01],
        verifier=[{"advises_evasion": False}],
    )
    return TestClient(create_app(Service(llm, fake_search, tracer, CHUNKS))), tracer


def test_ask_returns_answer_card_trace_and_cost(tmp_path) -> None:
    c, tracer = client(tmp_path)
    r = c.post(
        "/api/ask",
        json={"question": DEV["D01"]["question"] + " Email me: me@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "answered" and body["answer"]["total_usd"] == 2.97
    assert body["card"]["working"] and body["card"]["facts_relied_on"]
    assert {x["label"] for x in body["card"]["citations"]} >= {"19 CFR 148.33"}
    assert (
        body["cost"]["model_calls"] == 4 and body["trace"]["id"] and body["session_id"]
    )
    line = json.loads(tracer.path.read_text().splitlines()[0])
    assert (
        "me@example.com" not in json.dumps(line)
        and "[email]" in line["input"]["question"]
    )


def test_router_mode_and_refusal(tmp_path) -> None:
    c, _ = client(tmp_path, ScriptedLLM())
    r = c.post("/api/ask", json={"question": DEV["D19"]["question"], "mode": "router"})
    assert r.json()["outcome"] == "refused" and r.json()["cost"]["model_calls"] == 0


def test_rate_limit(tmp_path) -> None:
    lim = RateLimiter(2)
    assert lim.retry_after("a", 0) == 0 and lim.retry_after("a", 1) == 0
    assert lim.retry_after("a", 2) > 0
    assert lim.retry_after("b", 2) == 0  # per client
    assert lim.retry_after("a", 61) == 0  # window moved on


def test_rate_limit_returns_429(tmp_path, monkeypatch) -> None:
    from app import api

    monkeypatch.setattr(api, "RATE_LIMIT", 1)
    c, _ = client(tmp_path, ScriptedLLM())
    q = {"question": DEV["D19"]["question"]}
    assert c.post("/api/ask", json=q).status_code == 200
    r = c.post("/api/ask", json=q)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_clause_viewer_hides_hard_negatives(tmp_path) -> None:
    c, _ = client(tmp_path)
    r = c.get("/api/clause/19cfr148.33")
    assert (
        r.status_code == 200
        and r.json()["label"] == "19 CFR 148.33"
        and r.json()["sections"]
    )
    assert c.get("/api/clause/19cfr148.64").status_code == 404


def test_empty_question_is_rejected(tmp_path) -> None:
    c, _ = client(tmp_path)
    assert c.post("/api/ask", json={"question": ""}).status_code == 422


@pytest.mark.parametrize(
    "cid,title,label",
    [
        ("19cfr148.33", None, "19 CFR 148.33"),
        ("26usc5761", None, "26 USC § 5761"),
        ("htsus9816.00.20", None, "HTSUS 9816.00.20"),
        ("htsus-gn-3", None, "HTSUS General Note 3"),
        ("ofac-faq-720", None, "OFAC FAQ 720"),
        (
            "cbp-duty-info",
            "CBP - Customs Duty Information",
            "CBP: Customs Duty Information",
        ),
    ],
)
def test_citation_labels(cid, title, label) -> None:
    assert pretty_citation(cid, title) == label


@pytest.mark.parametrize(
    "text,kept",
    [
        ("call +1 415-555-0134", "[phone]"),
        ("passport no. X1234567", "[passport]"),
        ("My name is Ana Ruiz, I'm 34", "[name]"),
        ("card 4111 1111 1111 1111", "[card]"),
    ],
)
def test_pii_masked(text, kept) -> None:
    assert kept in mask_text(text)


def test_pii_leaves_customs_facts_alone() -> None:
    t = "4 bottles, 750 ml, $30 each, $1,000 band, back 2026-11-21, 10 days, I'm 34, HTSUS 9816.00.20"
    assert mask_text(t) == t
