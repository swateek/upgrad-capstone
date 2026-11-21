"""The tool contract (SPEC §8): validated arguments, prerequisites, dict results, never raises,
and the steps run through tools give the same answer as assess()."""

from customs.tools.calc import assess, finish, new_case
from customs.tools.models import Line, Profile
from customs.tools.registry import TOOLS, run_tool

PROFILE = Profile(
    age=40,
    trip_hours=240,
    arrived_directly_from="ES",
    exemption_used_last_30_days=False,
    arrival_state="NY",
)
BASKET = [
    Line(item="wine", quantity=2, unit="bottle", container_ml=750, value_usd=40, origin="ES"),
    Line(
        item="spirits",
        quantity=1,
        unit="bottle",
        container_ml=1000,
        abv=40,
        value_usd=35,
        origin="ES",
    ),
    Line(item="cigarettes", quantity=2, unit="carton"),
]
PLAN = [
    "normalise_units",
    "check_restrictions",
    "determine_exemption",
    "compute_allowance",
    "compute_duty_excise",
    "lookup_state_rule",
]


def test_tools_in_plan_order_equal_assess():
    case = new_case(PROFILE, BASKET)
    results = {name: run_tool(case, name) for name in PLAN}
    assert all("error" not in r for r in results.values()), results
    via_tools = finish(case)
    direct = assess(PROFILE, BASKET)
    assert via_tools.model_dump() == direct.model_dump()
    assert results["compute_duty_excise"]["figures"]  # money appears only as figures
    assert results["lookup_state_rule"]["rule_refs"] == ["state:NY"]


def test_out_of_order_call_is_a_non_retryable_error():
    case = new_case(PROFILE, BASKET)
    r = run_tool(case, "compute_duty_excise")
    assert r == {"error": "compute_duty_excise needs ['allowance'] first", "retryable": False}


def test_bad_arguments_are_retryable_errors():
    case = new_case(PROFILE, BASKET)
    run_tool(case, "normalise_units")
    r = run_tool(case, "check_restrictions", {"lines": "all"})
    assert r["retryable"] is True and "invalid arguments" in r["error"]
    r = run_tool(case, "normalise_units", {"anything": 1})
    assert r["retryable"] is True


def test_unknown_tool_and_internal_failure_do_not_raise():
    case = new_case(PROFILE, BASKET)
    assert "unknown tool" in run_tool(case, "award_contract")["error"]
    broken = new_case(PROFILE, [Line(item="wine", quantity=1, unit="bottle", abv=99)])
    for name in PLAN[:4]:
        run_tool(broken, name)
    assert "error" not in run_tool(broken, "compute_duty_excise")  # 99% wine taxed as spirits


def test_escalation_note_carries_the_facts():
    case = new_case(PROFILE, BASKET)
    run_tool(case, "normalise_units")
    r = run_tool(case, "escalate_to_human", {"reason": "basket over $800"})
    assert "CBP" in r["handoff"] and r["facts_relied_on"]["arrival_state"] == "NY"


def test_every_tool_declares_input_and_description():
    for name, spec in TOOLS.items():
        assert {"fn", "input", "requires", "description"} <= set(spec), name
