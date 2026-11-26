"""single_rag baseline: one call over the retrieved clauses, recorded in the agent's format."""

from __future__ import annotations

import json

from eval.run_agent import run
from src.baselines.single_rag import single_rag
from tests.test_agent import DEV, ScriptedLLM, fake_search

ANSWER = {
    "outcome": "answered",
    "bottom_line": [{"line": 1, "item": "wine", "type": "owe"}],
    "duty_usd": 2.4,
    "excise_usd": 0.57,
    "total_usd": 2.97,
    "whatif": None,
    "clarify_facts": [],
    "citations": ["cbp-duty-info"],
    "state_flag": None,
    "message": "You owe about $2.97.",
}


def test_one_call_over_search_results_only() -> None:
    seen = {}

    class Spy(ScriptedLLM):
        def chat(self, messages, *, stage, **kw):
            seen["prompt"] = messages[-1]["content"]
            return super().chat(messages, stage=stage, **kw)

    llm = Spy(baseline_single_rag=[ANSWER])
    r, ids, _trace = single_rag(llm, fake_search, DEV["D01"]["question"])
    assert llm.calls == ["baseline_single_rag"] and r.answer.total_usd == 2.97
    assert ids == ["cbp-duty-info"]  # no tools, so nothing is fetched by id
    assert "[cbp-duty-info]" in seen["prompt"]


def test_planted_document_reaches_the_model_unfiltered() -> None:
    seen = {}

    class Spy(ScriptedLLM):
        def chat(self, messages, *, stage, **kw):
            seen["prompt"] = messages[-1]["content"]
            return super().chat(messages, stage=stage, **kw)

    inject = DEV["D20"]["inject_into_retrieval"]
    _, ids, _ = single_rag(
        Spy(baseline_single_rag=[ANSWER]), fake_search, DEV["D20"]["question"], inject
    )
    assert ids[0] == inject["doc_id"] and inject["text"][:30] in seen["prompt"]


def test_run_agent_single_rag_mode(tmp_path) -> None:
    s = run(
        ScriptedLLM(baseline_single_rag=[ANSWER]),
        fake_search,
        "dev",
        "single_rag",
        "t",
        only=["D01"],
        results=tmp_path,
    )
    rec = json.loads((tmp_path / "runs" / "t" / "single_rag.jsonl").read_text())
    assert (
        rec["strategy"] == "single_rag"
        and rec["calls"] == 1
        and rec["retrieved_ids"] == ["cbp-duty-info"]
    )
    assert s["n"] == 1
