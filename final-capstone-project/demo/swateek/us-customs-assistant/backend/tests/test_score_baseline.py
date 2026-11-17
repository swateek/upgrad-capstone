"""The scorer (SPEC §10) and the baseline runner, offline (mock chat endpoint, temp output)."""

import json

import httpx
import pytest
from conftest import chat_response, mock_openai

from customs.config import PROJECT_ROOT
from customs.llm import ChatClient
from eval import baseline as bl
from eval.score import invented, keys, load_corpus, satisfies, score_extraction, score_turn

DOCS = PROJECT_ROOT / "data" / "chunks" / "documents.jsonl"
needs_corpus = pytest.mark.skipif(not DOCS.exists(), reason="corpus not built (CI)")

GOLD_OWE = {
    "outcome": "answered",
    "bottom_line": {"kind": "owe", "owe_usd": "3.23"},
    "citations": [
        {
            "claim": "R9 which_exemption",
            "acceptable": ["cfr19_p148:148.35(a)", "cfr19_p148:148.36(a)"],
        },
        {"claim": "R7 flat_rate_duty", "acceptable": ["hts_9816_rows:9816.00.20"]},
    ],
}


def test_keys_normalise_citation_forms():
    assert keys("19 C.F.R. § 148.33(d)") == {"19 cfr 148.33"}
    assert keys("HTSUS 9816.00.20") == {"9816.00.20"}
    assert keys("26 U.S.C. 5001(a)(1)") == {"26 usc 5001"}
    assert keys("OFAC FAQ 720") == {"ofac faq 720"}


@needs_corpus
def test_free_text_and_clause_id_citations_both_satisfy():
    corpus = load_corpus()
    assert satisfies(["19 CFR 148.35"], ["cfr19_p148:148.35(a)"], corpus)
    assert satisfies(["cfr19_p148:148.35(a)"], ["cfr19_p148:148.35(a)"], corpus)
    assert not satisfies(["19 CFR 148.51"], ["cfr19_p148:148.35(a)"], corpus)
    assert invented(["19 CFR 999.9", "19 CFR 148.33"], corpus) == ["19 CFR 999.9"]


@needs_corpus
def test_score_turn_correct_and_failure_labels():
    ok = score_turn(
        {
            "outcome": "answered",
            "kind": "owe",
            "owe_usd": 3.23,
            "citations": ["19 CFR 148.35", "HTSUS 9816.00.20"],
        },
        GOLD_OWE,
    )
    assert ok.correct and ok.claims_met == 2
    bad = score_turn(
        {"outcome": "answered", "kind": "owe", "owe_usd": 4.0, "citations": ["19 CFR 999.1"]},
        GOLD_OWE,
    )
    assert not bad.correct and {"wrong_amount", "missing_citation", "invented_citation"} <= set(
        bad.labels
    )
    clar = score_turn(
        {"outcome": "answered", "kind": "owe"},
        {"outcome": "clarify", "bottom_line": {"kind": "clarify"}},
    )
    assert clar.labels == ["no_clarify"]


def test_extraction_score_and_invented_fields():
    gold = {
        "profile": {"age": 34, "trip_hours": 240, "arrived_directly_from": "IT"},
        "basket": [
            {"item": "wine", "quantity": 4, "container_ml": 750, "value_usd": 120, "origin": "IT"}
        ],
    }
    pred = {
        "profile": {
            "age": 34,
            "trip_hours": ">=48",
            "arrived_directly_from": "it",
            "arrival_state": "NY",
        },
        "basket": [
            {"item": "wine", "quantity": 4, "container_ml": 750, "value_usd": 30, "origin": "IT"}
        ],
    }
    s = score_extraction(pred, gold)
    assert s == {"fields": 9, "correct": 8, "invented": 1}  # value per bottle instead of total


# --- runner ------------------------------------------------------------------------------------------

ANSWER = {"outcome": "answered", "kind": "owe", "owe_usd": 2.97, "clarify_question": None,
          "citations": ["19 CFR 148.33"], "answer": "You owe about $2.97."}  # fmt: skip


def handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    system = body["messages"][0]["content"]
    if "Step 1 of 3" in system or "Extract the traveller's facts" in system:
        content = {"profile": {"age": 34}, "basket": [{"item": "wine", "quantity": 4}]}
    elif "Step 2 of 3" in system:
        content = {"missing_fact": None, "exemption_usd": 800, "prohibited": [], "over_allowance": [],
                   "total_owed_usd": 2.97, "rules": []}  # fmt: skip
    elif "Think step by step" in system:
        content = {"reasoning": "...", **ANSWER}
    else:
        content = ANSWER
    return httpx.Response(200, json=chat_response(json.dumps(content)))


@needs_corpus
def test_runner_all_strategies_resume_and_report(tmp_path, monkeypatch, settings):
    monkeypatch.setattr(bl, "RAW", tmp_path / "raw.jsonl")
    monkeypatch.setattr(bl, "OUT", tmp_path)
    rows = [r for r in bl.load_rows("queries.jsonl") if r["id"] in ("A01", "I01")]
    runner = bl.Runner(ChatClient(settings, client=mock_openai(handler)))

    class NoTrace:
        def run(self, *a, **k):
            from contextlib import nullcontext

            return nullcontext()

        def flush(self):
            pass

    calls, _ = bl.run("tester", rows, runner, NoTrace())
    assert calls == bl.count_calls(rows) == 3 * 8 + 2 * 2  # 3 turns x 8 + 2 scenarios x 2 intakes
    again, _ = bl.run("tester", rows, runner, NoTrace())  # resume: everything already done
    assert again == 0
    bl.report()
    csv_text = (tmp_path / "week1_strategies.csv").read_text()
    assert "closed_book" in csv_text and "intake_constrained" in csv_text
    assert (tmp_path / "week1_failures.csv").exists() and (tmp_path / "week1-baselines.md").exists()


def test_frozen_call_count_is_888():
    assert bl.count_calls(bl.load_rows("queries.jsonl")) == 888
