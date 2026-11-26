"""Baseline strategies with a scripted fake model (no network, no quota)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.baselines import prompts
from src.baselines.strategies import cot_sc, decompose, run_strategy

DEV = {
    json.loads(x)["id"]: json.loads(x)
    for x in (Path(__file__).parents[1] / "eval" / "dev_set.jsonl")
    .read_text()
    .splitlines()
}
OWE = {
    "outcome": "answered",
    "bottom_line": [{"line": 1, "item": "wine", "type": "owe"}],
    "duty_usd": 1.0,
    "excise_usd": 0.5,
    "total_usd": 1.5,
}


@dataclass
class U:
    total_tokens: int = 100


@dataclass
class R:
    content: str
    usage: U = field(default_factory=U)


class Fake:
    def __init__(self, replies: list) -> None:
        self.replies, self.calls = list(replies), []

    def chat(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        reply = self.replies.pop(0)
        return R(reply if isinstance(reply, str) else json.dumps(reply))


def test_closed_book_parses_answer_and_counts_tokens() -> None:
    llm = Fake([OWE])
    run = run_strategy("closed_book", llm, "q")
    assert run.answer.total_usd == 1.5 and run.calls == 1 and run.tokens == 100
    assert (
        llm.calls[0]["response_format"]["type"] == "json_schema"
        and llm.calls[0]["temperature"] == 0.0
    )


def test_invalid_json_is_an_error_not_a_crash() -> None:
    run = run_strategy("closed_book", Fake(["not json"]), "q")
    assert run.answer is None and "invalid JSON" in run.error


def test_endpoint_exception_is_recorded() -> None:
    class Boom:
        def chat(self, *a, **k):
            raise RuntimeError("429")

    run = run_strategy("fewshot_json", Boom(), "q")
    assert run.answer is None and "429" in run.error


def test_fewshot_sends_five_examples_before_the_question() -> None:
    llm = Fake([OWE])
    run_strategy("fewshot_json", llm, "my question")
    msgs = llm.calls[0]["messages"]
    assert len(msgs) == 1 + 10 + 1 and msgs[-1]["content"] == "my question"


def test_cot_sc_majority_vote_over_three_samples() -> None:
    nothing = {
        **OWE,
        "bottom_line": [{"line": 1, "item": "wine", "type": "nothing_to_pay"}],
        "total_usd": 0,
    }
    llm = Fake(
        [
            {"reasoning": "a", "answer": nothing},
            {"reasoning": "b", "answer": OWE},
            {"reasoning": "c", "answer": OWE},
        ]
    )
    run = cot_sc(llm, "q")
    assert run.answer.bottom_line[0].type == "owe" and run.calls == 3
    assert [c["sample"] for c in llm.calls] == [0, 1, 2] and all(
        c["temperature"] == 0.7 for c in llm.calls
    )


def test_decompose_stops_early_for_refusal_and_clarify() -> None:
    refused = decompose(
        Fake([{"request_kind": "evasion", "profile": {}, "basket": []}]), "hide it?"
    )
    assert refused.answer.outcome == "refused" and refused.calls == 1
    facts = {"request_kind": "assess", "profile": {}, "basket": []}
    clar = decompose(
        Fake([facts, {"missing_facts": ["age"], "exemption": "none"}]), "q"
    )
    assert (
        clar.answer.outcome == "clarify"
        and clar.answer.clarify_facts == ["age"]
        and clar.calls == 2
    )


def test_decompose_runs_three_steps() -> None:
    facts = {"request_kind": "assess", "profile": {"age": 40}, "basket": []}
    rules = {
        "exemption": "800",
        "lines": [
            {"line": 1, "item": "wine", "status": "partly_exempt", "excess_liters": 2}
        ],
    }
    run = decompose(Fake([facts, rules, OWE]), "q")
    assert run.answer.total_usd == 1.5 and run.calls == 3


def test_fewshot_examples_match_dev_gold() -> None:
    for item_id, question, ans in prompts.FEWSHOT:
        g = DEV[item_id]
        assert question == g["question"]
        assert ans["outcome"] == g["gold"]["outcome"]
        assert [b["type"] for b in ans["bottom_line"]] == [
            b["type"] for b in g["gold"]["bottom_line"]
        ]
        for k in ("total_usd", "duty_usd", "excise_usd"):
            if k in g["gold"]:
                assert abs(ans[k] - g["gold"][k]) < 0.005
        if g["gold"]["outcome"] == "clarify":
            assert ans["clarify_facts"] == g["gold"]["clarify_facts"]


def test_runner_writes_answers_scores_and_resumes(tmp_path) -> None:
    from eval.run_baselines import run

    class Always:
        calls = 0

        def chat(self, messages, **kw):
            Always.calls += 1
            return R(json.dumps(OWE))

    s = run(Always(), "dev", ["closed_book"], "t", limit=3, results=tmp_path)
    out = tmp_path / "runs" / "t"
    assert len((out / "closed_book.jsonl").read_text().splitlines()) == 3
    assert (out / "scores_closed_book.csv").exists() and s["closed_book"]["n"] == 3
    run(
        Always(), "dev", ["closed_book"], "t", limit=3, results=tmp_path
    )  # resume: nothing re-asked
    assert Always.calls == 3


def test_decompose_extract_treats_zero_as_unknown() -> None:
    from src.baselines.answer import Extracted

    e = Extracted.model_validate(
        {
            "request_kind": "out_of_scope",
            "profile": {"trip": {"value": 0, "unit": "days"}},
            "basket": [
                {
                    "item": "x",
                    "category": "other",
                    "type": "other",
                    "quantity": {"value": 0, "unit": "can"},
                }
            ],
        }
    )
    assert e.profile.trip is None and e.basket == []


def test_citations_are_capped_and_deduplicated() -> None:
    from src.baselines.answer import MAX_CITATIONS, Answer

    a = Answer(
        outcome="answered",
        citations=[f"21 CFR 10.115(a)({i})" for i in range(40)]
        + ["21 CFR 10.115(a)(0)"],
    )
    assert len(a.citations) == MAX_CITATIONS
    assert (
        Answer.model_json_schema()["properties"]["citations"]["maxItems"]
        == MAX_CITATIONS
    )
