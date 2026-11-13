"""Offline tests for the harness pieces: budgets, refusals, critic checks, repair, resolution."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from copilot.agent.context import BudgetExceeded, RunContext, activate, deactivate
from copilot.agent.critic import Critic
from copilot.agent.harness import _resolve, _this_turn_todos
from copilot.agent.middleware import CriticGate
from copilot.agent.refusals import RefusalPolicy
from copilot.config import get_settings
from copilot.domains.loader import load_domain


@pytest.fixture(scope="module")
def domain():
    return load_domain(get_settings().domain_dir)


@pytest.fixture
def ctx():
    c = RunContext(step_limit=3, tool_limit=2, token_limit=1000)
    token = activate(c)
    yield c
    deactivate(token)


@pytest.fixture
def critic(domain):
    c = Critic(domain, RefusalPolicy(domain), llm=None, prompt="")
    c.mode_of_tool = {"search_policy": "__search__", "screen_vendor": "vendor", "score_bids": "bid"}
    return c


HIT = {
    "chunk_id": "gfr_2017:R154#1",
    "citation": "gfr_2017:R154",
    "title": "Rule 154",
    "instrument": "gfr",
    "edition_date": "2026-01-31",
    "synthetic": False,
    "text": "...",
}


def test_step_and_tool_budgets(ctx):
    for _ in range(3):
        ctx.take_step()
    with pytest.raises(BudgetExceeded):
        ctx.take_step()
    ctx.take_tool_call()
    ctx.take_tool_call()
    with pytest.raises(BudgetExceeded):
        ctx.take_tool_call()
    assert "step limit" in ctx.stopped


def test_refs_are_deduplicated(ctx):
    assert ctx.register(HIT) == "P1"
    assert ctx.register(dict(HIT)) == "P1"
    assert ctx.register({**HIT, "chunk_id": "x#1"}) == "P2"


def test_refusal_patterns(domain):
    pol = RefusalPolicy(domain)
    assert [h.rule_id for h in pol.check("Place the purchase order with Northwind today.")] == [
        "R1_consequential_action"
    ]
    assert pol.check("When can a firm be debarred under the rules?") == []
    assert pol.check("Who may award a contract under the GFR?") == []


def test_critic_flags_unknown_refs_and_uncited_facts(ctx, critic):
    ctx.register(HIT)
    ctx.tool_payloads.append({"tool": "search_policy", "args": {}, "result": {"hits": []}})
    problems = critic.deterministic(
        "The limit is Rs 50,000 per occasion [P1]. It rises to Rs 2 lakh "
        "for scientific departments [P7]. Bid security is two to five percent."
    )
    joined = " ".join(problems)
    assert "P7" in joined and "without a [P#] ref" in joined


def test_critic_requires_decline_when_refusal_rule_matched(ctx, critic, domain):
    ctx.refusal_hits = RefusalPolicy(domain).check("Debar Orbit Systems now.")
    assert critic.deterministic("Sure, Orbit Systems is now debarred from all tenders.")
    assert critic.deterministic("I can't debar firms; that is for the competent authority.") == []


def test_critic_requires_tools_for_long_unaided_answers(ctx, critic):
    long = "Purchases of goods are governed by many rules that set thresholds and committees " * 3
    assert any("without using any tool" in p for p in critic.deterministic(long))
    assert critic.deterministic("Hello! How can I help you today?") == []


SHEET = {
    "bidders": [
        {"bidder": "B1", "technical_total": 75},
        {"bidder": "B2", "technical_total": 90},
        {"bidder": "B3", "technical_total": 65},
    ],
    "withheld_bidders": [{"bidder": "B2", "name": "Prama Hikvision India Pvt. Ltd."}],
}


def test_domain_checks_for_bids(ctx, critic):
    ctx.tool_payloads.append({"tool": "score_bids", "args": {}, "result": SHEET})
    bad = critic.deterministic(
        "Draft for the committee: B1 75, B3 65. We recommend B2 as the best bid."
    )
    assert any("technical total" in p for p in bad) and any("withheld" in p for p in bad)
    good = "Draft for the committee, not an award: B1 75, B2 90 (withheld, not ranked), B3 65."
    assert critic.deterministic(good) == []


def test_domain_check_requires_snapshot_date(ctx, critic):
    result = {"status": "present", "lists": [{"snapshot_date": "2024-09-03"}]}
    ctx.tool_payloads.append({"tool": "screen_vendor", "args": {}, "result": result})
    assert critic.deterministic("DNS Overseas is on the GeM delist.")
    assert (
        critic.deterministic("DNS Overseas is present on the GeM delist as of 03-Sep-2024.") == []
    )


def test_gate_repairs_refs_and_tool_names_without_search(ctx):
    gate = CriticGate(
        lambda q, d: {"passed": True, "problems": []},
        search_tools=frozenset({"search_policy"}),
        tool_names=frozenset({"search_policy", "score_bids"}),
    )
    ctx.tool_payloads.append({"tool": "score_bids", "args": {}, "result": SHEET})
    assert gate._repair("B1 scores 75 [P1] [score_bids].") == "B1 scores 75."
    ctx.tool_payloads.append({"tool": "search_policy", "args": {}, "result": {"hits": []}})
    assert gate._repair("Limit is Rs 50,000 [P1].") == "Limit is Rs 50,000 [P1]."  # left for critic


def test_resolve_maps_refs_to_citations():
    text, cites, unknown = _resolve("Rs 50,000 [P1]. Other [P9].", {"P1": HIT})
    assert text == "Rs 50,000 [gfr_2017:R154]. Other ."
    assert cites == ["gfr_2017:R154"] and unknown == ["P9"]


def test_todos_are_per_turn():
    old = AIMessage(
        content="",
        tool_calls=[{"name": "write_todos", "args": {"todos": [{"content": "old"}]}, "id": "1"}],
    )
    msgs = [HumanMessage(content="q1"), old, HumanMessage(content="q2"), AIMessage(content="hi")]
    assert _this_turn_todos(msgs, "q2") == []
    assert _this_turn_todos(msgs, "q1") == [{"content": "old"}]
