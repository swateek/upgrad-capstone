# Trace dashboard: what to capture for the submission

**Team:** DLlamas. The Track B deliverables include "a trace dashboard showing real query executions". Every agent turn is already traced in Langfuse Cloud (US region; the project and keys belong to whoever's key is in `.env`). This page lists what to capture and how to find it. **SiliconFlow runs: captured on 13 Nov 2026** into `docs/demo/traces/`; six are in the SiliconFlow report's Appendix D. **Course-endpoint (`upgrad`) runs: captured on 14 Nov 2026** into `docs/demo/traces/upgrad/`; all seven are in the submitted report's Appendix E (`docs/report/upgrad/`). The tables below say how to reproduce each view.

## How the traces are labelled

| Field | Value | Use it to find |
|---|---|---|
| Trace name | `procurement-agent` (`<domain>-agent`) | every agent turn |
| Session | the conversation's thread id | multi-turn conversations, e.g. `demo-withheld-…` |
| Tags | always: `procurement` and the provider, `siliconflow` or `upgrad` | runs on one provider: filter on its tag |
| Tags, e2e eval runs | `eval`, `eval-v1` or `eval-v2`, the job (`policy`, `screening`, `bid`), the question id; from run 4 also the run label (`run4`, `run5`) | **run 5 (final) = tag `run5`**. Runs 3–5 all carry `eval-v2`, the version they ran on (later re-scored on v3), and runs 1–2 carry `eval-v1`. |
| Tags, e2e eval runs on `upgrad` | `upgrad`, `eval`, `eval-v3`, the job, the question id, the run label (`run1`, `run2`) | **Use `run2` for a clean list of 60.** `run1` also matches the interrupted first attempt of run 1 (109 traces in all). SiliconFlow runs 1–2 carry no run-label tag, so `run1`/`run2` never match them. |
| Tags, safety probes | `safety`, the probe id | the 7 probes |
| Metadata | chunker, chat model; at the end, steps, tool calls, revisions, critic result. Under `upgrad`, each search's listwise rerank call is a `rerank` event (tokens, seconds) in the run's events. | – |

Direct links to individual traces are in the `trace_url` field of each row in `docs/results/siliconflow/e2e-v2-run5.json` (and the earlier runs) and `docs/results/siliconflow/safety-v1.json`.

## Screenshots (captured)

| File | What | How to get there | Shows |
|---|---|---|---|
| `01-run5-trace-list.jpg` | **Run 5 trace list** | Traces, filter tag = `run5`; add the latency and token columns | 60 real executions of the frozen eval set, each with latency and tokens |
| `02-trace-s005-tree.jpg`, `03-trace-s005-screen-vendor.jpg` | **One full trace: S-005** ("Check DNS Overseas.") | the `trace_url` of S-005 in `e2e-v2-run5.json` | The trace tree: planner, `task` to the executor, `screen_vendor`, critic review; a dated GeM hit with the disclaimer |
| `04-trace-b004-two-revisions.jpg` (Metadata tab) | **A trace with two revisions: B-004** | the `trace_url` of B-004 in `e2e-v2-run5.json` | The critic sending the answer back twice, then releasing it marked as failing review (B2's total missing) |
| `05-trace-pii-masked.jpg` | **PII masking** | the `pii_in_question` trace in `safety-v1.json` | The email and phone number in the input show as `[REDACTED-…]` |
| `06-session-demo-withheld.jpg` | **A multi-turn session** | Sessions view, a `demo-withheld-…` session from the preflight | Two turns in one conversation; the follow-up uses the remembered case |
| `07-agent-dashboard.jpg` | **Dashboard** | Dashboards → the built-in "Langfuse Agent Dashboard", past 1 day | Tool calls in total and per tool, p95 latency per tool, observations by type, across the evaluation day |

To filter the trace list as in `01`, use the filter panel: Is Root Observation = True, Trace Tags = only `run5`. Hide the Output and Metadata columns to bring Latency into view.

## Screenshots of the `upgrad` runs (captured 14 Nov)

In `docs/demo/traces/upgrad/`:

| File | What | How to get there |
|---|---|---|
| `01-run2-trace-list.jpg` | Run 2 trace list, 60 traces | Traces, Is Root Observation = True, Trace Tags = only `run2`; columns: hide Cost, Time To First Token, Tool Calls, Total Tokens, Provided Model Name, Prompt Name and Environment so Latency and Trace Tags show |
| `02-trace-p001-tree.jpg`, `03-trace-p001-search-policy.jpg` | One full policy trace: P-001, and its `search_policy` output (P1) | the `trace_url` of P-001 in `docs/results/upgrad/e2e-v3-run1.json` |
| `04-trace-b004-two-revisions.jpg` | B-004 metadata: two revisions, `critic_passed: false` (public key blurred) | the `trace_url` of B-004 in the same file; Metadata tab |
| `05-trace-pii-masked.jpg` | PII masking | the `pii_in_question` trace in `docs/results/upgrad/safety-v1.json` |
| `06-session-demo-withheld.jpg` | The demo's withheld-bidder session, critic rejections visible | Sessions → `demo-withheld-20261114082121` |
| `07-agent-dashboard.jpg` | Agent Dashboard, past 1 day, Filters: Tags any of `upgrad` | Dashboards → Langfuse Agent Dashboard |

On `upgrad`, Langfuse's token count for a trace covers the chat generations only. The listwise rerank call runs inside `search_policy` as a plain HTTP call, so its tokens appear in the trace metadata's `tokens` total (the run's own count), not as a separate generation.

## Caveats to state next to the screenshots

- **Cost in Langfuse may be blank or wrong.** Langfuse prices tokens only for models in its price table, and SiliconFlow's `Qwen/Qwen3-8B` may not be in it. The report's costs come from `usage` × SiliconFlow's prices in `backend/eval/e2e.py`. To show cost in Langfuse, add a custom model definition in the project settings (Qwen/Qwen3-8B at $0.06/M input and output tokens).
- **Embedding and rerank calls** are counted in the eval results but aren't model generations in the trace.
- **The secret key never appears in traces.** The Langfuse SDK records its own *public* key as a trace attribute (`scope.attributes.public_key`, Metadata tab), so blur it in any screenshot of that tab; it is blurred in `04`. Inputs and outputs pass through the PII mask (`copilot/observability/tracing.py`) before export.
