"""The full planner -> executor -> critic flow, offline, with a scripted model (no API calls)."""

import pytest
from fakes import ScriptedChatModel, call
from langchain_core.messages import AIMessage

from copilot.agent.harness import Harness
from copilot.config import Settings
from copilot.domains.loader import load_domain
from copilot.tools.registry import Toolbox

GOOD_BID = (
    "Draft for the evaluation committee, not an award: B1 scores 93, B2 75 and B3 35. "
    "The draft ranking of eligible bidders is B1, B2, B3."
)


def plan_and_delegate(cid: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            call(
                "write_todos",
                {"todos": [{"content": "Score case_001", "status": "in_progress"}]},
                f"{cid}a",
            ),
            call(
                "task",
                {"description": "Draft the score sheet for case_001.", "subagent_type": "executor"},
                f"{cid}b",
            ),
        ],
    )


def score(cid: str, case_id: str = "case_001") -> AIMessage:
    return AIMessage(content="", tool_calls=[call("score_bids", {"case_id": case_id}, cid)])


@pytest.fixture
def make(tmp_path):
    def _make(script):
        settings = Settings(
            _env_file=None,
            domain="procurement",
            data_dir=tmp_path,
            siliconflow_api_key="test-key",
            agent_step_limit=10,
        )
        domain = load_domain(settings.domain_dir)
        model = ScriptedChatModel(script=script)
        return Harness(settings, domain, Toolbox(settings, domain), llm=model), model

    return _make


def test_bid_flow_planner_executor_critic(make):
    h, _ = make([plan_and_delegate("p1"), score("e1"), AIMessage(content=GOOD_BID)])
    r = h.run("Draft the score sheet for case_001.", "t1")
    assert r["answer"] == GOOD_BID and r["critic_passed"] and r["complete"]
    assert (r["steps"], r["tool_calls"], r["revisions"]) == (3, 1, 0)  # planner, executor x2
    assert [t["content"] for t in r["todos"]] == ["Score case_001"]
    assert r["session"]["active_case_id"] == "case_001"
    assert h.history("t1")["turns"][0]["answer"] == GOOD_BID


def test_critic_rejects_then_revision_passes(make):
    vague = "Draft for the committee: the score sheet is ready and B1 is ranked first."
    h, _ = make(
        [
            plan_and_delegate("p1"),
            score("e1"),
            AIMessage(content=vague),
            AIMessage(
                content="",
                tool_calls=[
                    call(
                        "task",
                        {"description": "Fix: report totals", "subagent_type": "executor"},
                        "p2",
                    )
                ],
            ),
            score("e2"),
            AIMessage(content=GOOD_BID),
        ]
    )
    r = h.run("Draft the score sheet for case_001.", "t2")
    assert r["revisions"] == 1 and r["critic_passed"]
    assert not r["critic"][0]["passed"] and "technical total" in r["critic"][0]["problems"][0]
    assert r["answer"] == GOOD_BID


def test_malformed_args_get_one_retry_then_refused(make):
    h, model = make(
        [
            plan_and_delegate("p1"),
            score("e1", "case 1"),
            score("e2", "case-1"),
            AIMessage(content="I could not load the case because its id was invalid."),
        ]
    )
    r = h.run("Draft the score sheet for case one.", "t3")
    errors = [e for e in r["events"] if e["type"] == "tool_arg_error"]
    assert [e["attempt"] for e in errors] == [1, 2]
    last_tool_msg = [m for m in model.calls[-1] if getattr(m, "type", "") == "tool"][-1]
    assert "no more retries" in last_tool_msg.content
    assert r["tool_calls"] == 2  # malformed calls still count against the tool budget


def test_step_cap_releases_latest_reviewed_draft(make):
    vague = "Draft for the committee: everything looks fine."
    loop = [
        AIMessage(
            content="",
            tool_calls=[
                call("task", {"description": "again", "subagent_type": "executor"}, f"p{i}")
            ],
        )
        for i in range(3)
    ]
    script = [
        plan_and_delegate("p0"),
        score("e1"),
        AIMessage(content=vague),
        *loop,
        score("e2"),
        score("e3"),
        score("e4"),
        score("e5"),
        score("e6"),
        score("e7"),
    ]
    h, _ = make(script)
    r = h.run("Draft the score sheet for case_001.", "t4")
    assert r["steps"] == 10 and "step limit" in r["stopped"]
    assert r["partial"] and r["answer"] == vague and not r["complete"]


def test_refusal_rule_detected_in_code(make):
    decline = (
        "I can't debar firms; that decision belongs to the competent authority. "
        "I can point to the rule that governs debarment."
    )
    h, _ = make([AIMessage(content=decline)])
    r = h.run("Debar Orbit Systems & Services LLP from all our tenders.", "t5")
    assert r["refusal_rules"] == ["R1_consequential_action"]
    assert r["critic_passed"] and r["steps"] == 1 and r["tool_calls"] == 0


def test_refs_without_search_are_repaired(make):
    h, _ = make(
        [plan_and_delegate("p1"), score("e1"), AIMessage(content=GOOD_BID + " [P1] [score_bids]")]
    )
    r = h.run("Draft the score sheet for case_001.", "t6")
    assert r["answer"] == GOOD_BID and r["critic_passed"]
    assert {e.get("what") for e in r["events"] if e["type"] == "repaired"} >= {
        "removed refs from an answer with no search results",
        "removed tool names written as citations",
    }


def test_answering_without_tools_is_sent_back(make):
    h, _ = make(
        [
            plan_and_delegate("p1"),
            AIMessage(content="I cannot find this in the indexed rules."),  # executor skips tools
            AIMessage(
                content="",
                tool_calls=[
                    call(
                        "task", {"description": "use the tools", "subagent_type": "executor"}, "p2"
                    )
                ],
            ),
            score("e1"),
            AIMessage(content=GOOD_BID),
        ]
    )
    r = h.run("Draft the score sheet for case_001 please.", "t7")
    assert not r["critic"][0]["passed"] and "No tool was used" in r["critic"][0]["problems"][0]
    assert r["revisions"] == 1 and r["answer"] == GOOD_BID and r["critic_passed"]


def test_two_revisions_then_pass(make):
    vague = "Draft for the committee: the score sheet is ready."
    again = [
        AIMessage(
            content="",
            tool_calls=[call("task", {"description": "fix", "subagent_type": "executor"}, f"p{i}")],
        )
        for i in (2, 3)
    ]
    h, _ = make(
        [
            plan_and_delegate("p1"),
            score("e1"),
            AIMessage(content=vague),
            again[0],
            score("e2"),
            AIMessage(content=vague),
            again[1],
            score("e3"),
            AIMessage(content=GOOD_BID),
        ]
    )
    r = h.run("Draft the score sheet for case_001.", "t8")
    assert r["revisions"] == 2 and r["critic_passed"] and r["answer"] == GOOD_BID
    assert [c["passed"] for c in r["critic"]] == [False, False, True]
