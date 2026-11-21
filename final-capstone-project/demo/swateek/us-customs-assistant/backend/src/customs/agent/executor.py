"""The executor (plan §4.1, §4.4): runs the validated plan's steps on the Case, then finalises.

Default (`planner`, `router` modes): code. The calculators read profile and basket from the Case
(graph state), so no model types a quantity or value. After the plan, code always runs the
bookkeeping steps (caps and flags: notes, seizure risk, Cuba refs, state flag) and the citation
step (search_regulations with the fetch-by-id fallback, D20).

`audit` is the verifier's plan-level half (plan §4.7): a step error, a line left uncomputed or
a missing exemption/allowance sends the plan back to the planner once, then escalates.
"""

from __future__ import annotations

from typing import Any

from customs.agent.context import current
from customs.agent.planner import Plan
from customs.retrieval.service import RegulationSearch, Source
from customs.tools.calc import Case, finish, step_caps, step_flags
from customs.tools.models import Assessment
from customs.tools.registry import TOOLS, run_tool


def run_step(case: Case, name: str, lines: list[int]) -> dict:
    spec = TOOLS[name]
    args = {"lines": lines} if "lines" in spec["input"].model_fields else {}
    result = run_tool(case, name, args)
    current().tool_call(name, result)
    return result


def finalise(case: Case) -> Assessment:
    if "allowance" in case.done:
        step_caps(case)
    step_flags(case)
    return finish(case)


def cite(search: RegulationSearch, question: str, a: Assessment) -> tuple[list[Source], dict]:
    if a.outcome != "answered" or not a.rule_refs:
        return [], {}
    ctx = current()
    sources, stats = search.search(question, a.rule_refs)
    result = {"sources": len(sources), "recovered": stats.get("recovered", [])}
    ctx.tool_call("search_regulations", result)
    ctx.embed_requests += stats.get("embed_requests", 0)
    for ref in stats.get("recovered", []):
        ctx.event("retrieval_miss_recovered", rule=ref)
    return sources, stats


def execute(plan: Plan, case: Case) -> list[dict[str, Any]]:
    """Run the plan's calculator steps in order; search_regulations runs in `cite` after."""
    results = []
    for s in plan.steps:
        if s.step == "search_regulations":
            continue
        # check_restrictions already ran in the scope check; it is idempotent, and re-running it
        # records the step's own result for the trace
        res = run_step(case, s.step, s.lines)
        results.append({"step": s.step, "lines": s.lines, "result": res})
    return results


def audit(case: Case, results: list[dict], a: Assessment) -> list[str]:
    """Plan-level failures: [] when the results cover what the answer needs."""
    errs = [
        f"{r['step']} failed: {r['result']['error']}" for r in results if "error" in r["result"]
    ]
    if a.outcome == "escalated" or not case.admissible:
        return errs
    if "exemption" not in case.done:
        errs.append("determine_exemption did not run")
    if "allowance" not in case.done:
        errs.append("compute_allowance did not run")
    for nl in case.alcohol:
        c = case.calc.get(nl.index)
        if c is not None and c.dutiable_ml and c.excise is None:
            errs.append(f"line {nl.index} has alcohol over the allowance but was not computed")
    return errs
