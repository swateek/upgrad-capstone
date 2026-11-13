# End-to-end evaluation: eval set v1

2026-11-13T07:50:12+00:00 · siliconflow `Qwen/Qwen3-8B` · by_rule + `Qwen/Qwen3-Embedding-0.6B` + `Qwen/Qwen3-Reranker-8B` · budgets {'steps': 10, 'tool_calls': 10, 'tokens': 40000} · eval commit `0e3d764` · code `351496e`

## Accuracy

| Slice | Correct |
|---|---|
| policy (factual) | 11/23 (48%) |
| screening (lookups) | 17/18 (94%) |
| bid (scoring) | 9/11 (82%) |
| refusals (all jobs) | 8/8 (100%) |
| **all 60** | 45/60 (75%) |

## Agent behaviour

| Metric | Value |
|---|---|
| Task completion (answer released within budgets, no error) | 59/60 (98%) |
| Critic passed on the released answer | 47/60 (78%) |
| Answers that needed a critic revision | 18/60 (30%) |
| Mean tool calls per task | 1.72 |
| Mean model calls (steps) per task | 4.35 |
| Runs stopped by a budget | 1 |
| Latency p50 / p95 / max (s) | 13.2 / 54.4 / 61.3 |
| Mean chat tokens per task | 5,533 |
| Mean cost per task (chat + embedding + rerank) | $0.00065 |
| Total cost of this run | $0.0393 |
| Retrieval cache (hits / misses) | 16 / 41 |

## Failure taxonomy (misses only)

| Label | Count | Questions |
|---|---|---|
| retrieval miss | 7 | P-002, P-006, P-010, P-011, P-014, P-016, P-022 |
| tool-call error | 6 | P-001, P-004, P-009, P-013, P-023, S-005 |
| hallucination | 0 | – |
| reasoning error | 2 | B-002, B-004 |

## Per question

| Id | Job | Result | Label | Steps | Tools | Notes |
|---|---|---|---|---|---|---|
| P-001 | policy | ✗ | tool-call error | 6 | 6 |  |
| P-002 | policy | ✗ | retrieval miss | 9 | 4 |  |
| P-003 | policy | ✓ |  | 6 | 2 |  |
| P-004 | policy | ✗ | tool-call error | 2 | 0 |  |
| P-005 | policy | ✓ |  | 9 | 5 |  |
| P-006 | policy | ✗ | retrieval miss | 9 | 4 |  |
| P-007 | policy | ✓ |  | 4 | 1 |  |
| P-008 | policy | ✓ |  | 5 | 2 |  |
| P-009 | policy | ✗ | tool-call error | 2 | 0 |  |
| P-010 | policy | ✗ | retrieval miss | 5 | 2 |  |
| P-011 | policy | ✗ | retrieval miss | 8 | 4 |  |
| P-012 | policy | ✓ |  | 7 | 2 |  |
| P-013 | policy | ✗ | tool-call error | 2 | 0 |  |
| P-014 | policy | ✗ | retrieval miss | 5 | 2 |  |
| P-015 | policy | ✓ |  | 5 | 2 |  |
| P-016 | policy | ✗ | retrieval miss | 8 | 4 |  |
| P-017 | policy | ✓ |  | 5 | 2 |  |
| P-018 | policy | ✓ |  | 8 | 4 |  |
| P-019 | policy | ✓ |  | 4 | 1 |  |
| P-020 | policy | ✓ |  | 8 | 4 |  |
| P-021 | policy | ✓ |  | 9 | 4 |  |
| P-022 | policy | ✗ | retrieval miss | 4 | 2 |  |
| P-023 | policy | ✗ | tool-call error | 2 | 0 |  |
| P-024 | policy (refusal) | ✓ |  | 5 | 1 |  |
| P-025 | policy (refusal) | ✓ |  | 2 | 0 |  |
| S-001 | screening | ✓ |  | 3 | 1 |  |
| S-002 | screening | ✓ |  | 3 | 1 |  |
| S-003 | screening | ✓ |  | 3 | 1 |  |
| S-004 | screening | ✓ |  | 3 | 1 |  |
| S-005 | screening | ✗ | tool-call error | 2 | 0 | screen_vendor not called |
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
| B-002 | bid | ✗ | reasoning error | 6 | 2 | B1 total 93 missing |
| B-003 | bid | ✓ |  | 3 | 1 |  |
| B-004 | bid | ✗ | reasoning error | 6 | 2 | B2 total 90 missing |
| B-005 | bid | ✓ |  | 3 | 1 |  |
| B-006 | bid | ✓ |  | 10 | 7 |  |
| B-007 | bid (refusal) | ✓ |  | 2 | 0 |  |
| B-008 | bid | ✓ |  | 3 | 1 |  |
| B-009 | bid | ✓ |  | 6 | 4 |  |
| B-010 | bid | ✓ |  | 6 | 4 |  |
| B-011 | bid | ✓ |  | 3 | 1 |  |
| B-012 | bid | ✓ |  | 3 | 1 |  |
| B-013 | bid (refusal) | ✓ |  | 3 | 1 |  |
| B-014 | bid (refusal) | ✓ |  | 2 | 0 |  |
| B-015 | bid (refusal) | ✓ |  | 2 | 0 |  |

Scoring and labelling rules: `backend/eval/e2e.py`. Answers, traces and tool calls for every question are in the JSON.
