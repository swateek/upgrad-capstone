# End-to-end evaluation: eval set v3

2026-11-14T07:54:50+00:00 · upgrad `Qwen/Qwen3-8B` · by_rule + `bge-small-en-v1.5` + `Qwen/Qwen3-8B (listwise)` · budgets {'steps': 10, 'tool_calls': 10, 'tokens': 40000} · eval commit `0e3d764 + v2 (P-015) + v3 (P-011, P-012) also_accept changes` · code `4fbf7fa`

## Accuracy

| Slice | Correct |
|---|---|
| policy (factual) | 22/23 (96%) |
| screening (lookups) | 16/18 (89%) |
| bid (scoring) | 9/11 (82%) |
| refusals (all jobs) | 8/8 (100%) |
| **all 60** | 55/60 (92%) |

## Agent behaviour

| Metric | Value |
|---|---|
| Task completion (answer released within budgets, no error) | 58/60 (97%) |
| Critic passed on the released answer | 46/60 (77%) |
| Answers that needed a critic revision | 24/60 (40%) |
| Mean tool calls per task | 1.70 |
| Mean model calls (steps) per task | 5.05 |
| Runs stopped by a budget | 2 |
| Latency p50 / p95 / max (s) | 12.8 / 32.6 / 41.5 |
| Mean chat tokens per task | 7,269 |
| Mean cost per task (chat + embedding + rerank) | $0.00000 |
| Total cost of this run | $0.0000 |
| Retrieval cache (hits / misses) | 28 / 53 |

## Failure taxonomy (misses only)

| Label | Count | Questions |
|---|---|---|
| retrieval miss | 1 | P-013 |
| tool-call error | 2 | S-005, B-010 |
| hallucination | 0 | – |
| reasoning error | 2 | S-013, B-004 |

## Per question

| Id | Job | Result | Label | Steps | Tools | Notes |
|---|---|---|---|---|---|---|
| P-001 | policy | ✓ |  | 4 | 1 |  |
| P-002 | policy | ✓ |  | 9 | 3 |  |
| P-003 | policy | ✓ |  | 9 | 3 |  |
| P-004 | policy | ✓ |  | 7 | 2 |  |
| P-005 | policy | ✓ |  | 7 | 1 |  |
| P-006 | policy | ✓ |  | 4 | 1 |  |
| P-007 | policy | ✓ |  | 4 | 1 |  |
| P-008 | policy | ✓ |  | 4 | 1 |  |
| P-009 | policy | ✓ |  | 9 | 3 |  |
| P-010 | policy | ✓ |  | 9 | 3 |  |
| P-011 | policy | ✓ |  | 7 | 2 |  |
| P-012 | policy | ✓ |  | 4 | 1 |  |
| P-013 | policy | ✗ | retrieval miss | 7 | 2 |  |
| P-014 | policy | ✓ |  | 7 | 2 |  |
| P-015 | policy | ✓ |  | 4 | 1 |  |
| P-016 | policy | ✓ |  | 4 | 1 |  |
| P-017 | policy | ✓ |  | 5 | 1 |  |
| P-018 | policy | ✓ |  | 4 | 1 |  |
| P-019 | policy | ✓ |  | 4 | 1 |  |
| P-020 | policy | ✓ |  | 5 | 1 |  |
| P-021 | policy | ✓ |  | 4 | 1 |  |
| P-022 | policy | ✓ |  | 4 | 1 |  |
| P-023 | policy | ✓ |  | 9 | 3 |  |
| P-024 | policy (refusal) | ✓ |  | 7 | 1 |  |
| P-025 | policy (refusal) | ✓ |  | 4 | 0 |  |
| S-001 | screening | ✓ |  | 3 | 1 |  |
| S-002 | screening | ✓ |  | 3 | 1 |  |
| S-003 | screening | ✓ |  | 3 | 1 |  |
| S-004 | screening | ✓ |  | 3 | 1 |  |
| S-005 | screening | ✗ | tool-call error | 1 | 0 | screen_vendor not called |
| S-006 | screening | ✓ |  | 3 | 1 |  |
| S-007 | screening | ✓ |  | 3 | 1 |  |
| S-008 | screening | ✓ |  | 3 | 1 |  |
| S-009 | screening | ✓ |  | 3 | 1 |  |
| S-010 | screening | ✓ |  | 3 | 1 |  |
| S-011 | screening | ✓ |  | 10 | 6 |  |
| S-012 | screening | ✓ |  | 3 | 1 |  |
| S-013 | screening | ✗ | reasoning error | 9 | 3 | snapshot date not stated |
| S-014 | screening | ✓ |  | 3 | 1 |  |
| S-015 | screening | ✓ |  | 9 | 6 |  |
| S-016 | screening | ✓ |  | 3 | 1 |  |
| S-017 | screening | ✓ |  | 3 | 1 |  |
| S-018 | screening | ✓ |  | 3 | 1 |  |
| S-019 | screening (refusal) | ✓ |  | 9 | 3 |  |
| S-020 | screening (refusal) | ✓ |  | 2 | 0 |  |
| B-001 | bid | ✓ |  | 3 | 1 |  |
| B-002 | bid | ✓ |  | 6 | 2 |  |
| B-003 | bid | ✓ |  | 3 | 1 |  |
| B-004 | bid | ✗ | reasoning error | 9 | 3 | B2 total 90 missing; withheld B2 not named |
| B-005 | bid | ✓ |  | 3 | 1 |  |
| B-006 | bid | ✓ |  | 3 | 1 |  |
| B-007 | bid (refusal) | ✓ |  | 6 | 0 |  |
| B-008 | bid | ✓ |  | 3 | 1 |  |
| B-009 | bid | ✓ |  | 6 | 8 |  |
| B-010 | bid | ✗ | tool-call error | 10 | 10 | B1 total 75 missing; B2 total 80 missing; B3 total 90 missing |
| B-011 | bid | ✓ |  | 6 | 2 |  |
| B-012 | bid | ✓ |  | 3 | 1 |  |
| B-013 | bid (refusal) | ✓ |  | 3 | 1 |  |
| B-014 | bid (refusal) | ✓ |  | 2 | 0 |  |
| B-015 | bid (refusal) | ✓ |  | 10 | 0 |  |

Scoring and labelling rules: `backend/eval/e2e.py`. Answers, traces and tool calls for every question are in the JSON.
