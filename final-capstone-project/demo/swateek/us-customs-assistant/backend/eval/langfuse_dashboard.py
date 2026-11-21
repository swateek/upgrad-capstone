"""The plan §8 Langfuse dashboards, built through Langfuse's (unstable) dashboard API.

    uv run python -m eval.langfuse_dashboard            # create or rebuild both dashboards

1. "Customs agent: official planner runs (eval-v1)": outcomes (clarify rate), correct / dollar /
   citation / verifier-passed / plan-fallback rates, p50 and p95 latency per graph node, tokens
   per model call, model calls per node, model and tool calls per question.
2. "Customs agent: modes compared (eval-v1)": correct, model calls per question and p95 latency
   for planner, router, tool_calling and single_rag.

Runs are picked by trace tags (`frozen` + the mode). The eval scores come from
eval.langfuse_scores. Rebuilding deletes the dashboards and widgets this script made before
(matched by name) and creates them again. Sends nothing to upgrad.
"""

from __future__ import annotations

from typing import Any

from customs.config import get_settings

PREFIX = "customs · "
NODES = ["guard", "intake", "prepare", "clarify", "plan", "execute", "audit", "write", "verify"]
MODES = ["planner", "router", "tool_calling", "single_rag"]
RATES = ["correct", "dollar_ok", "citation_ok", "verifier_passed", "plan_fallback"]


def tags(*t: str) -> dict:
    return {"column": "tags", "operator": "all of", "value": list(t), "type": "arrayOptions"}


def eq(col: str, v: str) -> dict:
    return {"column": col, "operator": "=", "value": v, "type": "string"}


def any_of(col: str, v: list[str]) -> dict:
    return {"column": col, "operator": "any of", "value": v, "type": "stringOptions"}


def w(name, view, dims, metrics, filters, chart, desc="", **cfg) -> dict:
    return {"name": PREFIX + name, "view": view, "dimensions": [{"field": d} for d in dims],
            "metrics": [{"measure": m, "agg": a} for m, a in metrics], "filters": filters,
            "chart_type": chart, "description": desc,
            "chart_config": {"type": chart, **cfg}}  # fmt: skip


def planner_widgets() -> list[tuple[dict, int, int, int, int]]:
    p = tags("frozen", "planner")
    nodes = [p, any_of("name", NODES), eq("type", "CHAIN")]
    return [
        (w("Outcomes", "scores-categorical", ["stringValue"], [("count", "count")],
           [p, eq("name", "outcome")], "HORIZONTAL_BAR",
           "Turns per outcome (clarify rate = clarify / all).", show_value_labels=True),
         0, 0, 6, 6),
        (w("Correct, dollar, citation, verifier, plan fallback", "scores-boolean", ["name"],
           [("value", "avg")], [p, any_of("name", RATES)], "HORIZONTAL_BAR",
           "Mean of each boolean score (eval scores from the run records).",
           show_value_labels=True), 6, 0, 6, 6),
        (w("Latency p50 per node", "observations", ["name"], [("latency", "p50")], nodes,
           "HORIZONTAL_BAR", "LangGraph node spans.", show_value_labels=True), 0, 6, 6, 6),
        (w("Latency p95 per node", "observations", ["name"], [("latency", "p95")], nodes,
           "HORIZONTAL_BAR", "LangGraph node spans.", show_value_labels=True), 6, 6, 6, 6),
        (w("Tokens per model call", "observations", ["name"], [("totalTokens", "avg")],
           [p, eq("type", "GENERATION")], "HORIZONTAL_BAR",
           "Mean input + output tokens per Qwen3-8B call, by caller.", show_value_labels=True),
         0, 12, 6, 6),
        (w("Model calls by caller", "observations", ["name"], [("count", "count")],
           [p, eq("type", "GENERATION")], "HORIZONTAL_BAR",
           "intake, planner, writer and the advisory review.", show_value_labels=True), 6, 12, 6, 6),
        (w("Per question: model calls, tool calls, rewrites, sources recovered", "scores-numeric",
           ["name"], [("value", "avg")],
           [p, any_of("name", ["model_calls", "tool_calls", "revisions",
                               "retrieval_miss_recovered"])],
           "HORIZONTAL_BAR", "Model and tool calls: mean over all turns (tools are code calculators). Rewrites and sources recovered: mean over turns that reached the verifier.",
           show_value_labels=True), 0, 18, 12, 5),
    ]  # fmt: skip


def mode_widgets() -> list[tuple[dict, int, int, int, int]]:
    out = []
    for i, m in enumerate(MODES):
        f = tags("frozen", m)
        out += [
            (w(f"Correct · {m}", "scores-boolean", [], [("value", "avg")],
               [f, eq("name", "correct")], "NUMBER", "Share of turns correct (eval-v1)."),
             3 * i, 0, 3, 3),
            (w(f"Model calls/turn · {m}", "scores-numeric", [], [("value", "avg")],
               [f, eq("name", "model_calls")], "NUMBER"), 3 * i, 3, 3, 3),
            (w(f"Latency p95 · {m}", "observations", [], [("latency", "p95")],
               [f, any_of("name", ["customs-agent"])], "NUMBER", "Whole turn, from the trace."), 3 * i, 6, 3, 3),
        ]  # fmt: skip
    return out


DASHBOARDS = [
    ("Customs agent: official planner runs (eval-v1)",
     "Frozen agent v4 on the frozen eval set, planner-1..3. See docs/eval-report.md.",
     planner_widgets),
    ("Customs agent: modes compared (eval-v1)",
     "planner (3 runs), router, tool_calling, single_rag on the frozen eval set.", mode_widgets),
]  # fmt: skip


def _items(page: Any) -> list[Any]:
    return list(page.data or [])


def main() -> None:
    from langfuse import Langfuse

    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        raise SystemExit("FAIL Langfuse keys not set")
    lf = Langfuse(public_key=s.langfuse_public_key,
                  secret_key=s.langfuse_secret_key.get_secret_value(),
                  base_url=s.langfuse_base_url)  # fmt: skip
    api = lf.api.unstable
    project = lf.api.projects.get().data[0].id
    names = {n for n, _, _ in DASHBOARDS}
    for d in _items(api.dashboards.list(limit=100)):
        if d.name in names:
            api.dashboards.delete(d.id)
    for x in _items(api.dashboard_widgets.list(limit=100)):
        if x.name.startswith(PREFIX):
            api.dashboard_widgets.delete(x.id)
    for name, desc, widgets in DASHBOARDS:
        d = api.dashboards.create(name=name, description=desc)
        for spec, x, y, width, height in widgets():
            widget = api.dashboard_widgets.create(**spec)
            api.dashboards.add_placement(d.id, request={"type": "widget", "widget_id": widget.id,
                                                        "x": x, "y": y, "width": width,
                                                        "height": height})  # fmt: skip
        print(f"{name}: {s.langfuse_base_url}/project/{project}/dashboards/{d.id}")


if __name__ == "__main__":
    main()
