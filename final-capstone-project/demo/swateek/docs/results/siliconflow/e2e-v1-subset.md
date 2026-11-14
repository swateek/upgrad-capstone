# End-to-end evaluation: eval set v1

2026-11-13T07:25:58+00:00 · siliconflow `Qwen/Qwen3-8B` · by_rule + `Qwen/Qwen3-Embedding-0.6B` + `Qwen/Qwen3-Reranker-8B` · budgets {'steps': 10, 'tool_calls': 10, 'tokens': 40000} · eval commit `0e3d764` · code `351496e` · **SUBSET, not a reportable run**

## Accuracy

| Slice | Correct |
|---|---|
| policy (factual) | 0/1 (0%) |
| screening (lookups) | 1/1 (100%) |
| bid (scoring) | 1/1 (100%) |
| refusals (all jobs) | 1/1 (100%) |
| **all 60** | 3/4 (75%) |

## Agent behaviour

| Metric | Value |
|---|---|
| Task completion (answer released within budgets, no error) | 4/4 (100%) |
| Critic passed on the released answer | 3/4 (75%) |
| Answers that needed a critic revision | 1/4 (25%) |
| Mean tool calls per task | 1.50 |
| Mean model calls (steps) per task | 4.00 |
| Runs stopped by a budget | 0 |
| Latency p50 / p95 / max (s) | 12.6 / 13.6 / 36.3 |
| Mean chat tokens per task | 4,727 |
| Mean cost per task (chat + embedding + rerank) | $0.00039 |
| Total cost of this run | $0.0016 |
| Retrieval cache (hits / misses) | 1 / 1 |

## Failure taxonomy (misses only)

| Label | Count | Questions |
|---|---|---|
| retrieval miss | 1 | P-016 |
| tool-call error | 0 | – |
| hallucination | 0 | – |
| reasoning error | 0 | – |

## Per question

| Id | Job | Result | Label | Steps | Tools | Notes |
|---|---|---|---|---|---|---|
| P-016 | policy | ✗ | retrieval miss | 8 | 4 |  |
| S-008 | screening | ✓ |  | 3 | 1 |  |
| B-003 | bid | ✓ |  | 3 | 1 |  |
| B-007 | bid (refusal) | ✓ |  | 2 | 0 |  |

Scoring and labelling rules: `backend/eval/e2e.py`. Answers, traces and tool calls for every question are in the JSON.
