# Day 11 metrics

Built by `eval/metrics.py` from the official runs (`results/runs/*`: scores, records, summaries); the same arms as `docs/ABLATION.md`, where accuracy by type and each check are tabled. Planner arms: mean over 3 runs. Clarify precision = asks that gold also asks / all asks; recall = gold asks that were asked; right facts = gold asks where exactly the gold facts were asked. Completion = an outcome with no error inside the budget. Over-escalation = escalated where gold answers or asks; over-refusal = refused where gold does not refuse.

## eval-v2, gold-v1 (agent v1's held-out set)

| Arm | Accuracy | $ accuracy (n) | Citations | Clarify P / R / right facts | Completion | Over-escalation | Over-refusal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single_rag | 0.075 | 0.00 (42) | 0.05 | – / 0.00 / 0.00 | 1.00 | 0 | 1 |
| agent v1, code router | 0.750 | 0.76 (42) | 0.86 | 0.54 / 0.88 / 0.75 | 1.00 | 3 | 0 |
| agent v1, LLM planner | 0.750 | 0.76 (42) | 0.86 | 0.54 / 0.88 / 0.75 | 1.00 | 3 | 0 |

| Arm | Answered / clarify / refused / escalated | Tool steps/q | Model calls/q | Tokens/q | Tokens per run | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single_rag | 73 / 0 / 7 / 0 | 0 | 1.00 | 2,312 | 184,979 | 6.5 | 8.0 |
| agent v1, code router | 52 / 13 / 9 / 6 | 5.29 | 2.49 | 2,882 | 213,276 | 9.2 | 14.4 |
| agent v1, LLM planner | 52 / 13 / 9 / 6 | 4.97 | 3.66 | 3,528 | 261,101 | 11.6 | 17.1 |

## eval-v3 (agent v2's held-out set, SPEC v2)

| Arm | Accuracy | $ accuracy (n) | Citations | Clarify P / R / right facts | Completion | Over-escalation | Over-refusal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single_rag | 0.070 | 0.02 (51) | 0.11 | – / 0.00 / 0.00 | 1.00 | 0 | 1 |
| agent v1, code router | 0.520 | 0.57 (51) | 0.57 | 0.24 / 0.80 / 0.20 | 1.00 | 3 | 1 |
| agent v2, code router | 0.770 | 0.77 (51) | 0.79 | 0.43 / 1.00 / 0.50 | 1.00 | 2 | 0 |
| agent v2, LLM planner | 0.770 | 0.77 (51) | 0.79 | 0.43 / 1.00 / 0.50 | 1.00 | 2 | 0 |

| Arm | Answered / clarify / refused / escalated | Tool steps/q | Model calls/q | Tokens/q | Tokens per run | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single_rag | 94 / 0 / 6 / 0 | 0 | 1.00 | 2,348 | 234,764 | 6.9 | 8.3 |
| agent v1, code router | 49 / 33 / 13 / 5 | 4.61 | 2.09 | 2,374 | 215,990 | 8.2 | 13.4 |
| agent v2, code router | 59 / 23 / 13 / 5 | 4.99 | 2.33 | 2,769 | 249,234 | 9.1 | 14.4 |
| agent v2, LLM planner | 59 / 23 / 13 / 5 | 4.78 | 3.51 | 3,430 | 308,729 | 11.9 | 17.8 |

## eval-v2 re-scored under SPEC v2 (gold-v2): informed the v2 fixes

| Arm | Accuracy | $ accuracy (n) | Citations | Clarify P / R / right facts | Completion | Over-escalation | Over-refusal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent v2, code router | 1.000 | 1.00 (42) | 1.00 | 1.00 / 1.00 / 1.00 | 1.00 | 0 | 0 |
| agent v2, LLM planner | 1.000 | 1.00 (42) | 1.00 | 1.00 / 1.00 / 1.00 | 1.00 | 0 | 0 |

| Arm | Answered / clarify / refused / escalated | Tool steps/q | Model calls/q | Tokens/q | Tokens per run | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent v2, code router | 58 / 8 / 11 / 3 | 5.47 | 2.68 | 3,179 | 228,884 | 9.6 | 14.8 |
| agent v2, LLM planner | 58 / 8 / 11 / 3 | 5.15 | 3.85 | 3,810 | 274,338 | 12.1 | 17.4 |

Cost: the shared course endpoint has no price, so cost is reported in tokens; pass `--price-per-mtok` for a cost at a stated price.
