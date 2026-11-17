# End-to-end evaluation: eval set v3

2026-11-14T07:27:09+00:00 · upgrad `Qwen/Qwen3-8B` · by_rule + `bge-small-en-v1.5` + `Qwen/Qwen3-8B (listwise)` · budgets {'steps': 10, 'tool_calls': 10, 'tokens': 40000} · eval commit `0e3d764 + v2 (P-015) + v3 (P-011, P-012) also_accept changes` · code `4fbf7fa` · **SUBSET, not a reportable run**

## Accuracy

| Slice | Correct |
|---|---|
| policy (factual) | 1/1 (100%) |
| screening (lookups) | 1/1 (100%) |
| bid (scoring) | 1/1 (100%) |
| refusals (all jobs) | – |
| **all 60** | 3/3 (100%) |

## Agent behaviour

| Metric | Value |
|---|---|
| Task completion (answer released within budgets, no error) | 3/3 (100%) |
| Critic passed on the released answer | 3/3 (100%) |
| Answers that needed a critic revision | 0/3 (0%) |
| Mean tool calls per task | 1.00 |
| Mean model calls (steps) per task | 3.33 |
| Runs stopped by a budget | 0 |
| Latency p50 / p95 / max (s) | 9.4 / 9.4 / 14.6 |
| Mean chat tokens per task | 4,682 |
| Mean cost per task (chat + embedding + rerank) | $0.00000 |
| Total cost of this run | $0.0000 |
| Retrieval cache (hits / misses) | 0 / 2 |

## Failure taxonomy (misses only)

| Label | Count | Questions |
|---|---|---|
| retrieval miss | 0 | – |
| tool-call error | 0 | – |
| hallucination | 0 | – |
| reasoning error | 0 | – |

## Per question

| Id | Job | Result | Label | Steps | Tools | Notes |
|---|---|---|---|---|---|---|
| P-001 | policy | ✓ |  | 4 | 1 |  |
| S-001 | screening | ✓ |  | 3 | 1 |  |
| B-001 | bid | ✓ |  | 3 | 1 |  |

Scoring and labelling rules: `backend/eval/e2e.py`. Answers, traces and tool calls for every question are in the JSON.
