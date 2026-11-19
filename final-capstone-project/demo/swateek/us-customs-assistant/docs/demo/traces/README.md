# Langfuse traces and dashboards (plan §8)

Screenshots from this app's own Langfuse project, taken 18 Nov 2026 after the official runs.

| file | what it shows |
|---|---|
| `01-planner-outcomes-latency.jpg` | Dashboard "Customs agent: official planner runs (eval-v1)": outcomes (clarify rate), correct / dollar / citation / verifier-passed / plan-fallback rates, p50 and p95 latency per LangGraph node |
| `02-planner-tokens-calls.jpg` | Same dashboard: tokens per Qwen3-8B call, model calls by caller, model and tool calls per question, rewrites, sources recovered by id |
| `03-modes-compared.jpg` | Dashboard "Customs agent: modes compared (eval-v1)": correct, model calls per turn and p95 latency for planner, router, tool_calling, single_rag |
| `04-one-trace-A01.jpg` | One real question (frozen eval A01, planner-3): the node tree with each model call's time and tokens, the card, and the scores on the trace |

How they were made:

- Traces: every official turn is one `customs-agent` trace, tagged with the run, set, mode, category and question id.
- Scores: the frozen agent records only `outcome`. `eval/langfuse_scores.py` attached the rest (correct, dollar_ok, citation_ok, verifier_passed, revisions, plan_fallback, retrieval_miss_recovered, model_calls, tool_calls) to the same traces from the run records: 3,994 scores on 582 traces.
- Dashboards: `eval/langfuse_dashboard.py` builds both through Langfuse's (unstable) dashboard API; rerunning rebuilds them. Runs are selected by trace tags (`frozen` + mode), so dev, smoke and safety traces are left out.

Reading them:

- Langfuse's dashboard date range defaults to the past day; set it to cover 18 Nov 2026 to see these runs later.
- Latency here is the trace's own span; `docs/eval-report.md` uses the agent's timer and a nearest-rank percentile, so p95s differ a little (router 24.3 s here, 29.0 s in the report). Accuracy, calls and tokens match the report.
- Tool calls are code calculators run inside the `execute` node, not separate spans, so Langfuse has calls per question but not calls per tool; `docs/eval-report.md` has the per-run tool-call means.
- The advisory review is about 5 s of the `verify` node's time (p50) and one of four model calls per answer; see `docs/results/reviewer-agreement.md` for how much it is worth.
- No keys appear in these screenshots (the trace is shown on its Preview tab, not Metadata, which holds the SDK's public key).
