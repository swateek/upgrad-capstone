# End-to-end evaluation: eval set v2

2026-11-13T08:56:29+00:00 · siliconflow `Qwen/Qwen3-8B` · by_rule + `Qwen/Qwen3-Embedding-0.6B` + `Qwen/Qwen3-Reranker-8B` · budgets {'steps': 10, 'tool_calls': 10, 'tokens': 40000} · eval commit `0e3d764 + v2 change (P-015 also_accept)` · code `351496e`

## Accuracy

| Slice | Correct |
|---|---|
| policy (factual) | 21/23 (91%) |
| screening (lookups) | 17/18 (94%) |
| bid (scoring) | 10/11 (91%) |
| refusals (all jobs) | 8/8 (100%) |
| **all 60** | 56/60 (93%) |

## Agent behaviour

| Metric | Value |
|---|---|
| Task completion (answer released within budgets, no error) | 60/60 (100%) |
| Critic passed on the released answer | 56/60 (93%) |
| Answers that needed a critic revision | 18/60 (30%) |
| Mean tool calls per task | 1.38 |
| Mean model calls (steps) per task | 4.37 |
| Runs stopped by a budget | 0 |
| Latency p50 / p95 / max (s) | 26.5 / 43.9 / 52.9 |
| Mean chat tokens per task | 5,860 |
| Mean cost per task (chat + embedding + rerank) | $0.00069 |
| Total cost of this run | $0.0412 |
| Retrieval cache (hits / misses) | 10 / 42 |

## Failure taxonomy (misses only)

| Label | Count | Questions |
|---|---|---|
| retrieval miss | 0 | – |
| tool-call error | 2 | P-023, S-005 |
| hallucination | 1 | P-021 |
| reasoning error | 1 | B-003 |

## Per question

| Id | Job | Result | Label | Steps | Tools | Notes |
|---|---|---|---|---|---|---|
| P-001 | policy | ✓ |  | 4 | 1 |  |
| P-002 | policy | ✓ |  | 7 | 2 |  |
| P-003 | policy | ✓ |  | 4 | 1 |  |
| P-004 | policy | ✓ |  | 6 | 1 |  |
| P-005 | policy | ✓ |  | 6 | 1 |  |
| P-006 | policy | ✓ |  | 4 | 1 |  |
| P-007 | policy | ✓ |  | 4 | 1 |  |
| P-008 | policy | ✓ |  | 4 | 1 |  |
| P-009 | policy | ✓ |  | 4 | 1 |  |
| P-010 | policy | ✓ |  | 4 | 1 |  |
| P-011 | policy | ✓ |  | 4 | 1 |  |
| P-012 | policy | ✓ |  | 4 | 1 |  |
| P-013 | policy | ✓ |  | 7 | 1 |  |
| P-014 | policy | ✓ |  | 7 | 2 |  |
| P-015 | policy | ✓ |  | 4 | 1 |  |
| P-016 | policy | ✓ |  | 4 | 1 |  |
| P-017 | policy | ✓ |  | 4 | 1 |  |
| P-018 | policy | ✓ |  | 4 | 1 |  |
| P-019 | policy | ✓ |  | 4 | 1 |  |
| P-020 | policy | ✓ |  | 9 | 3 |  |
| P-021 | policy | ✗ | hallucination | 4 | 1 |  |
| P-022 | policy | ✓ |  | 4 | 1 |  |
| P-023 | policy | ✗ | tool-call error | 8 | 2 |  |
| P-024 | policy (refusal) | ✓ |  | 6 | 1 |  |
| P-025 | policy (refusal) | ✓ |  | 2 | 0 |  |
| S-001 | screening | ✓ |  | 3 | 1 |  |
| S-002 | screening | ✓ |  | 3 | 1 |  |
| S-003 | screening | ✓ |  | 3 | 1 |  |
| S-004 | screening | ✓ |  | 3 | 1 |  |
| S-005 | screening | ✗ | tool-call error | 9 | 3 | screen_vendor not called |
| S-006 | screening | ✓ |  | 3 | 1 |  |
| S-007 | screening | ✓ |  | 3 | 1 |  |
| S-008 | screening | ✓ |  | 3 | 1 |  |
| S-009 | screening | ✓ |  | 3 | 1 |  |
| S-010 | screening | ✓ |  | 3 | 1 |  |
| S-011 | screening | ✓ |  | 3 | 1 |  |
| S-012 | screening | ✓ |  | 3 | 1 |  |
| S-013 | screening | ✓ |  | 3 | 1 |  |
| S-014 | screening | ✓ |  | 3 | 1 |  |
| S-015 | screening | ✓ |  | 3 | 1 |  |
| S-016 | screening | ✓ |  | 3 | 1 |  |
| S-017 | screening | ✓ |  | 3 | 1 |  |
| S-018 | screening | ✓ |  | 3 | 1 |  |
| S-019 | screening (refusal) | ✓ |  | 6 | 2 |  |
| S-020 | screening (refusal) | ✓ |  | 2 | 0 |  |
| B-001 | bid | ✓ |  | 3 | 1 |  |
| B-002 | bid | ✓ |  | 6 | 2 |  |
| B-003 | bid | ✗ | reasoning error | 9 | 3 | B2 total 90 missing; B3 total 65 missing |
| B-004 | bid | ✓ |  | 6 | 2 |  |
| B-005 | bid | ✓ |  | 6 | 2 |  |
| B-006 | bid | ✓ |  | 3 | 1 |  |
| B-007 | bid (refusal) | ✓ |  | 2 | 0 |  |
| B-008 | bid | ✓ |  | 6 | 2 |  |
| B-009 | bid | ✓ |  | 6 | 8 |  |
| B-010 | bid | ✓ |  | 6 | 6 |  |
| B-011 | bid | ✓ |  | 9 | 3 |  |
| B-012 | bid | ✓ |  | 3 | 1 |  |
| B-013 | bid (refusal) | ✓ |  | 3 | 1 |  |
| B-014 | bid (refusal) | ✓ |  | 2 | 0 |  |
| B-015 | bid (refusal) | ✓ |  | 2 | 0 |  |

Scoring and labelling rules: `backend/eval/e2e.py`. Answers, traces and tool calls for every question are in the JSON.
