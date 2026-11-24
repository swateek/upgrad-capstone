# Week-1 baselines (eval-v1, bare model)

Generated 2026-11-17 18:07 UTC by `eval.baseline`. Qwen3-8B on the upgrad endpoint, single prompts, no tools, no calculators, no retrieval. Scored by `eval/score.py`. *Invented cites* = cited regulation sections that are not in the corpus snapshot (fabricated, or real but outside the snapshot). Amount % is over answered turns where the gold has an amount; citation cover % is gold citation claims met.

| Strategy | Turns | Turn acc % | Scenario acc % | Outcome % | Amount % | Citation cover % | Invented cites % | Valid JSON 1st try % | Tokens/turn | s/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| closed_book | 91 | 2.2 | 2.5 | 68.1 | 11.8 | 45.7 | 5.3 | 100.0 | 583 | 3.11 |
| fewshot_json | 91 | 13.2 | 12.5 | 82.4 | 13.2 | 74.0 | 4.8 | 100.0 | 1012 | 2.9 |
| cot_sc | 91 | 3.3 | 3.8 | 71.4 | 22.1 | 41.6 | 21.1 | 100.0 | 2441 | 19.81 |
| decompose | 91 | 1.1 | 1.2 | 75.8 | 22.1 | 53.4 | 16.0 | 100.0 | 2125 | 9.93 |

| Intake | Scenarios | Field accuracy % | Invented fields | Valid JSON 1st try % | Invalid |
|---|---|---|---|---|---|
| intake_constrained | 80 | 86.1 | 33 | 100.0 | 0 |
| intake_prompted | 80 | 85.8 | 36 | 55.0 | 0 |

## Failure labels per strategy

- **closed_book**: missing_citation 60, wrong_amount 52, wrong_kind 23, no_clarify 11, unnecessary_clarify 8, wrong_outcome 6, invented_citation 4, scope_miss 3, escalation_miss 1
- **fewshot_json**: wrong_amount 59, missing_citation 42, wrong_kind 24, no_clarify 10, invented_citation 8, scope_miss 3, escalation_miss 1, wrong_outcome 1, refusal_miss 1
- **cot_sc**: missing_citation 62, wrong_amount 47, invented_citation 42, wrong_kind 24, no_clarify 11, wrong_outcome 7, unnecessary_clarify 5, scope_miss 2, escalation_miss 1
- **decompose**: missing_citation 68, wrong_amount 53, wrong_kind 29, invented_citation 24, no_clarify 11, refusal_miss 4, scope_miss 3, wrong_outcome 3, escalation_miss 1
