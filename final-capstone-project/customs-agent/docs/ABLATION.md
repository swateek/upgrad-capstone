# Ablation: every arm on the same questions

Built by `eval/ablation.py` from the run files (`results/runs/*/summary_*.json`, `*.jsonl`) and `results/week1_strategies.csv`; see `results/ablation.csv` for every column. Accuracy is the share of questions where every applicable check passes (eval/score.py). The LLM planner arms are three runs each (mean, with the range); latency pools all questions of an arm. Cache off for every official run; all v2 runs matched the v2 freeze (`v2.0.0-rc`).

## eval-v2, gold-v1 (agent v1's held-out set)

| Arm | Runs | Accuracy | Outcome | Bottom line | Dollars | Clarify | Citations | Must not | State flag | Tokens/q | Calls/q | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prompting: closed_book | 1 | 0.100 | 0.82 | 0.63 | 0.00 | 0.00 | 0.07 | 1.00 | 0.33 | 700 | 1.00 | – | – |
| prompting: fewshot_json | 1 | 0.175 | 0.81 | 0.63 | 0.05 | 0.00 | 0.61 | 1.00 | 0.33 | 1,665 | 1.00 | – | – |
| prompting: cot_sc | 1 | 0.113 | 0.80 | 0.56 | 0.07 | 0.00 | 0.07 | 1.00 | 0.33 | 2,597 | 3.00 | – | – |
| prompting: decompose | 1 | 0.113 | 0.39 | 0.07 | 0.07 | 0.12 | 0.00 | 1.00 | 0.00 | 1,423 | 2.15 | – | – |
| single_rag | 1 | 0.075 | 0.79 | 0.59 | 0.00 | 0.00 | 0.05 | 0.75 | 0.33 | 2,312 | 1.00 | 6.5 | 8.0 |
| agent v1, code router | 1 | 0.750 | 0.88 | 0.85 | 0.76 | 0.75 | 0.86 | 0.75 | 0.67 | 2,882 | 2.49 | 9.2 | 14.4 |
| agent v1, LLM planner | 3 | 0.750 (0.75–0.75) | 0.88 | 0.85 | 0.76 | 0.75 | 0.86 | 0.75 | 0.67 | 3,528 | 3.66 | 11.6 | 17.1 |

Accuracy by question type:

| Type | prompting: closed_book | prompting: fewshot_json | prompting: cot_sc | prompting: decompose | single_rag | agent v1, code router | agent v1, LLM planner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| alcohol_excess_800 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.75 | 0.75 |
| alcohol_cbi_2L | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| exemption_200_all_or_nothing | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.75 | 0.75 |
| tobacco_over_limit | 0.00 | 0.00 | 0.14 | 0.00 | 0.00 | 0.71 | 0.71 |
| cuban_origin | 0.00 | 0.83 | 0.00 | 0.00 | 0.00 | 0.83 | 0.83 |
| under_21 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| mixed_basket | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.40 | 0.40 |
| whatif | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.75 | 0.75 |
| clarify | 0.00 | 0.00 | 0.00 | 0.12 | 0.00 | 0.75 | 0.75 |
| state_flag | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| sanctions_escalate | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| out_of_scope | 0.40 | 0.80 | 0.40 | 0.40 | 0.20 | 0.60 | 0.60 |
| refuse_evasion | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| injection_doc | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.50 | 0.50 |
| injection_user | 1.00 | 0.50 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 |

## eval-v3 (agent v2's held-out set, SPEC v2)

| Arm | Runs | Accuracy | Outcome | Bottom line | Dollars | Clarify | Citations | Must not | State flag | Tokens/q | Calls/q | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single_rag | 1 | 0.070 | 0.75 | 0.49 | 0.02 | 0.00 | 0.11 | 0.00 | 0.17 | 2,348 | 1.00 | 6.9 | 8.3 |
| agent v1, code router | 1 | 0.520 | 0.69 | 0.64 | 0.57 | 0.20 | 0.57 | 0.00 | 0.33 | 2,374 | 2.09 | 8.2 | 13.4 |
| agent v2, code router | 1 | 0.770 | 0.84 | 0.81 | 0.77 | 0.50 | 0.79 | 1.00 | 0.83 | 2,769 | 2.33 | 9.1 | 14.4 |
| agent v2, LLM planner | 3 | 0.770 (0.77–0.77) | 0.84 | 0.81 | 0.77 | 0.50 | 0.79 | 1.00 | 0.83 | 3,430 | 3.51 | 11.9 | 17.8 |

Accuracy by question type:

| Type | single_rag | agent v1, code router | agent v2, code router | agent v2, LLM planner |
| --- | --- | --- | --- | --- |
| alcohol_excess_800 | 0.00 | 0.41 | 0.65 | 0.65 |
| alcohol_cbi_2L | 0.00 | 1.00 | 1.00 | 1.00 |
| exemption_200_all_or_nothing | 0.00 | 0.33 | 0.67 | 0.67 |
| tobacco_over_limit | 0.20 | 0.50 | 0.70 | 0.70 |
| cuban_origin | 0.00 | 0.67 | 0.83 | 0.83 |
| under_21 | 0.00 | 0.83 | 1.00 | 1.00 |
| mixed_basket | 0.00 | 0.30 | 0.70 | 0.70 |
| whatif | 0.00 | 0.50 | 0.75 | 0.75 |
| clarify | 0.00 | 0.20 | 0.50 | 0.50 |
| state_flag | 0.00 | 0.25 | 1.00 | 1.00 |
| sanctions_escalate | 0.00 | 1.00 | 1.00 | 1.00 |
| out_of_scope | 0.17 | 0.67 | 0.83 | 0.83 |
| refuse_evasion | 0.50 | 1.00 | 1.00 | 1.00 |
| injection_doc | 0.00 | 0.00 | 1.00 | 1.00 |
| injection_user | 0.50 | 1.00 | 1.00 | 1.00 |

## eval-v2 re-scored under SPEC v2 (gold-v2): informed the v2 fixes

| Arm | Runs | Accuracy | Outcome | Bottom line | Dollars | Clarify | Citations | Must not | State flag | Tokens/q | Calls/q | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent v2, code router | 1 | 1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 3,179 | 2.68 | 9.6 | 14.8 |
| agent v2, LLM planner | 1 | 1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 3,810 | 3.85 | 12.1 | 17.4 |

Accuracy by question type:

| Type | agent v2, code router | agent v2, LLM planner |
| --- | --- | --- |
| alcohol_excess_800 | 1.00 | 1.00 |
| alcohol_cbi_2L | 1.00 | 1.00 |
| exemption_200_all_or_nothing | 1.00 | 1.00 |
| tobacco_over_limit | 1.00 | 1.00 |
| cuban_origin | 1.00 | 1.00 |
| under_21 | 1.00 | 1.00 |
| mixed_basket | 1.00 | 1.00 |
| whatif | 1.00 | 1.00 |
| clarify | 1.00 | 1.00 |
| state_flag | 1.00 | 1.00 |
| sanctions_escalate | 1.00 | 1.00 |
| out_of_scope | 1.00 | 1.00 |
| refuse_evasion | 1.00 | 1.00 |
| injection_doc | 1.00 | 1.00 |
| injection_user | 1.00 | 1.00 |

## Reading it

- **Tools beat prompting.** On eval-v2 the four Day 4 prompting strategies reach 0.10–0.18 and single_rag 0.075; the agent with calculators, rules as data and the verifier reaches 0.75. Dollars are where prompting fails: no strategy gets more than a few amounts right without the calculators.
- **Planner vs router.** On every set the LLM planner and the code router give the same answers; the planner costs more tokens and model calls. A valid, reportable result (mentor plan): the fixed plan is enough for this task.
- **Agent v1 vs v2 on the same new questions (eval-v3):** 0.52 → 0.77. Part of the gain is SPEC v2 rules that v1 never had (sake as beer, the origin question, ABV timing), part is reading.
- **Generalisation gap.** Agent v2 scores 0.991 on dev-v2 (tuned on) and 1.00 on eval-v2 under gold-v2 (its failures shaped the fixes), but 0.77 on eval-v3 (never seen). eval-v3 is the honest number.
- **State flag is reported, not scored** (eval/score.py). Every miss in the official runs is the same gap, in v1 and v2 alike: an arrival airport ("landing at JFK") is not read as the arrival state, so the New York note is left out (E66, E3-077). A known gap for the report; not fixed on a spent set.
