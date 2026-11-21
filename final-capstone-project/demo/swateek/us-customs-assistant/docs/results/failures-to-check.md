# Failures to hand-check (plan §10.5: at least 15)

Each wrong turn with its label. `hand` = checked; the label is then the hand label (docs/results/hand-check.yaml, with the cause) and `auto` is the classifier's.

| run | id | turn | category | gold | got | score labels | label | bucket | auto | check |
|---|---|---|---|---|---|---|---|---|---|---|
| planner-1 | B04 | 1 | alcohol_cbi_2L | answered/owe 2.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| planner-1 | C04 | 1 | exemption_200_all_or_nothing | answered/nothing_owed 0.00 | answered/mixed 0.53 | wrong_kind, wrong_amount | extraction_error | Reasoning error | extraction_error | hand |
| planner-1 | C05 | 1 | exemption_200_all_or_nothing | answered/mixed 0.11 | clarify/clarify  | unnecessary_clarify | extraction_error | Reasoning error | extraction_error | hand |
| planner-1 | D02 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/seizure_risk 0.00 | missing_citation | extraction_error | Reasoning error | citation_mapping | hand |
| planner-1 | E04 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| planner-1 | E05 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| planner-1 | E05 | 2 | cuban_origin | answered/nothing_owed 0.00 | answered/prohibited 0.00 | wrong_kind | extraction_error | Reasoning error | extraction_error | hand |
| planner-1 | F03 | 1 | under_21 | answered/owe 4.28 | answered/owe 4.28 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| planner-1 | F04 | 1 | under_21 | answered/mixed 1.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| planner-1 | G08 | 1 | mixed_basket | answered/owe 4.72 | answered/owe 4.87 | wrong_amount | unit_error | Reasoning error | rule_selection_error | hand |
| planner-1 | H01 | 1 | whatif | answered/whatif 9.47 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-1 | H02 | 1 | whatif | answered/whatif 18.77 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-1 | H03 | 1 | whatif | answered/whatif 3.57 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-1 | H04 | 1 | whatif | answered/whatif 0.00 | clarify/clarify  | unnecessary_clarify | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-1 | I07 | 1 | clarify | clarify/clarify  | answered/owe 0.71 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| planner-1 | I08 | 1 | clarify | clarify/clarify  | answered/nothing_owed 0.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| planner-1 | J02 | 1 | state_flag | answered/owe 2.85 | answered/owe 2.85 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| planner-1 | K05 | 1 | out_of_scope | out_of_scope/out_of_scope  | clarify/clarify  | wrong_outcome:out_of_scope->clarify | extraction_error | Reasoning error | extraction_error | hand |
| planner-1 | L02 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| planner-1 | L03 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| planner-2 | B04 | 1 | alcohol_cbi_2L | answered/owe 2.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| planner-2 | C04 | 1 | exemption_200_all_or_nothing | answered/nothing_owed 0.00 | answered/mixed 0.53 | wrong_kind, wrong_amount | extraction_error | Reasoning error | extraction_error | hand |
| planner-2 | C05 | 1 | exemption_200_all_or_nothing | answered/mixed 0.11 | clarify/clarify  | unnecessary_clarify | extraction_error | Reasoning error | extraction_error | hand |
| planner-2 | D02 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/seizure_risk 0.00 | missing_citation | extraction_error | Reasoning error | citation_mapping | hand |
| planner-2 | E04 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| planner-2 | E05 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| planner-2 | E05 | 2 | cuban_origin | answered/nothing_owed 0.00 | answered/prohibited 0.00 | wrong_kind | extraction_error | Reasoning error | extraction_error | hand |
| planner-2 | F03 | 1 | under_21 | answered/owe 4.28 | answered/owe 4.28 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| planner-2 | F04 | 1 | under_21 | answered/mixed 1.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| planner-2 | G08 | 1 | mixed_basket | answered/owe 4.72 | answered/owe 4.87 | wrong_amount | unit_error | Reasoning error | rule_selection_error | hand |
| planner-2 | H01 | 1 | whatif | answered/whatif 9.47 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-2 | H02 | 1 | whatif | answered/whatif 18.77 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-2 | H03 | 1 | whatif | answered/whatif 3.57 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-2 | H04 | 1 | whatif | answered/whatif 0.00 | clarify/clarify  | unnecessary_clarify | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-2 | I07 | 1 | clarify | clarify/clarify  | answered/owe 0.71 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| planner-2 | I08 | 1 | clarify | clarify/clarify  | answered/nothing_owed 0.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| planner-2 | J02 | 1 | state_flag | answered/owe 2.85 | answered/owe 2.85 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| planner-2 | K05 | 1 | out_of_scope | out_of_scope/out_of_scope  | clarify/clarify  | wrong_outcome:out_of_scope->clarify | extraction_error | Reasoning error | extraction_error | hand |
| planner-2 | L02 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| planner-2 | L03 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| planner-3 | B04 | 1 | alcohol_cbi_2L | answered/owe 2.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| planner-3 | C04 | 1 | exemption_200_all_or_nothing | answered/nothing_owed 0.00 | answered/mixed 0.53 | wrong_kind, wrong_amount | extraction_error | Reasoning error | extraction_error | hand |
| planner-3 | C05 | 1 | exemption_200_all_or_nothing | answered/mixed 0.11 | clarify/clarify  | unnecessary_clarify | extraction_error | Reasoning error | extraction_error | hand |
| planner-3 | D02 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/seizure_risk 0.00 | missing_citation | extraction_error | Reasoning error | citation_mapping | hand |
| planner-3 | E04 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| planner-3 | E05 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| planner-3 | E05 | 2 | cuban_origin | answered/nothing_owed 0.00 | answered/prohibited 0.00 | wrong_kind | extraction_error | Reasoning error | extraction_error | hand |
| planner-3 | F03 | 1 | under_21 | answered/owe 4.28 | answered/owe 4.28 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| planner-3 | F04 | 1 | under_21 | answered/mixed 1.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| planner-3 | G08 | 1 | mixed_basket | answered/owe 4.72 | answered/owe 4.87 | wrong_amount | unit_error | Reasoning error | rule_selection_error | hand |
| planner-3 | H01 | 1 | whatif | answered/whatif 9.47 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-3 | H02 | 1 | whatif | answered/whatif 18.77 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-3 | H03 | 1 | whatif | answered/whatif 3.57 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-3 | H04 | 1 | whatif | answered/whatif 0.00 | clarify/clarify  | unnecessary_clarify | feature_not_built | Not built (stretch) | feature_not_built | hand |
| planner-3 | I07 | 1 | clarify | clarify/clarify  | answered/owe 0.71 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| planner-3 | I08 | 1 | clarify | clarify/clarify  | answered/nothing_owed 0.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| planner-3 | J02 | 1 | state_flag | answered/owe 2.85 | answered/owe 2.85 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| planner-3 | K05 | 1 | out_of_scope | out_of_scope/out_of_scope  | clarify/clarify  | wrong_outcome:out_of_scope->clarify | extraction_error | Reasoning error | extraction_error | hand |
| planner-3 | L02 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| planner-3 | L03 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| router | B04 | 1 | alcohol_cbi_2L | answered/owe 2.03 | escalated/escalated  | wrong_outcome:answered->escalated | budget_exceeded | Reasoning error | budget_exceeded |  |
| router | C04 | 1 | exemption_200_all_or_nothing | answered/nothing_owed 0.00 | answered/mixed 0.53 | wrong_kind, wrong_amount | extraction_error | Reasoning error | extraction_error | hand |
| router | C05 | 1 | exemption_200_all_or_nothing | answered/mixed 0.11 | clarify/clarify  | unnecessary_clarify | extraction_error | Reasoning error | extraction_error | hand |
| router | D02 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/seizure_risk 0.00 | missing_citation | extraction_error | Reasoning error | citation_mapping | hand |
| router | E04 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| router | E05 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | rule_selection_error | Reasoning error | extraction_error | hand |
| router | E05 | 2 | cuban_origin | answered/nothing_owed 0.00 | answered/prohibited 0.00 | wrong_kind | extraction_error | Reasoning error | extraction_error | hand |
| router | F03 | 1 | under_21 | answered/owe 4.28 | answered/owe 4.28 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| router | G08 | 1 | mixed_basket | answered/owe 4.72 | answered/owe 4.87 | wrong_amount | unit_error | Reasoning error | rule_selection_error | hand |
| router | H01 | 1 | whatif | answered/whatif 9.47 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| router | H02 | 1 | whatif | answered/whatif 18.77 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| router | H03 | 1 | whatif | answered/whatif 3.57 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built | hand |
| router | H04 | 1 | whatif | answered/whatif 0.00 | clarify/clarify  | unnecessary_clarify | feature_not_built | Not built (stretch) | feature_not_built | hand |
| router | I07 | 1 | clarify | clarify/clarify  | answered/owe 0.71 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| router | I08 | 1 | clarify | clarify/clarify  | answered/nothing_owed 0.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss | hand |
| router | J02 | 1 | state_flag | answered/owe 2.85 | answered/owe 2.85 | missing_citation | extraction_error | Reasoning error | extraction_error | hand |
| router | K05 | 1 | out_of_scope | out_of_scope/out_of_scope  | clarify/clarify  | wrong_outcome:out_of_scope->clarify | extraction_error | Reasoning error | extraction_error | hand |
| router | L02 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| router | L03 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss | hand |
| tool_calling | A01 | 1 | alcohol_excess_800 | answered/owe 3.23 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A02 | 1 | alcohol_excess_800 | answered/owe 5.96 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A03 | 1 | alcohol_excess_800 | answered/owe 1.37 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A04 | 1 | alcohol_excess_800 | answered/owe 1.62 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A05 | 1 | alcohol_excess_800 | answered/owe 1.01 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A06 | 1 | alcohol_excess_800 | answered/owe 4.12 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A07 | 1 | alcohol_excess_800 | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A08 | 1 | alcohol_excess_800 | answered/owe 3.57 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A09 | 1 | alcohol_excess_800 | answered/owe 0.57 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A10 | 1 | alcohol_excess_800 | answered/owe 3.65 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A11 | 1 | alcohol_excess_800 | answered/owe 1.60 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | A12 | 1 | alcohol_excess_800 | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | B01 | 1 | alcohol_cbi_2L | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | B02 | 1 | alcohol_cbi_2L | answered/owe 1.01 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | B03 | 1 | alcohol_cbi_2L | answered/owe 0.71 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | B04 | 1 | alcohol_cbi_2L | answered/owe 2.03 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C01 | 1 | exemption_200_all_or_nothing | answered/owe 2.14 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C02 | 1 | exemption_200_all_or_nothing | answered/owe 0.21 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C03 | 1 | exemption_200_all_or_nothing | answered/owe 3.20 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C04 | 1 | exemption_200_all_or_nothing | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C05 | 1 | exemption_200_all_or_nothing | answered/mixed 0.11 | clarify/clarify  | unnecessary_clarify | extraction_error | Reasoning error | extraction_error |  |
| tool_calling | C06 | 1 | exemption_200_all_or_nothing | answered/owe 3.45 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C07 | 1 | exemption_200_all_or_nothing | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | C08 | 1 | exemption_200_all_or_nothing | answered/owe 2.14 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D01 | 2 | tobacco_over_limit | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D02 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D03 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D04 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D05 | 1 | tobacco_over_limit | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D06 | 1 | tobacco_over_limit | answered/mixed 0.50 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | D07 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | E04 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | extraction_error | Reasoning error | extraction_error |  |
| tool_calling | E05 | 1 | cuban_origin | clarify/clarify  | answered/prohibited 0.00 | no_clarify | extraction_error | Reasoning error | extraction_error |  |
| tool_calling | E05 | 2 | cuban_origin | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | E06 | 1 | cuban_origin | answered/mixed 0.44 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | F01 | 1 | under_21 | answered/owe 0.81 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | F02 | 1 | under_21 | answered/seizure_risk 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | F03 | 1 | under_21 | answered/owe 4.28 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | F04 | 1 | under_21 | answered/mixed 1.03 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G01 | 1 | mixed_basket | answered/mixed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G02 | 1 | mixed_basket | answered/owe 2.50 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G03 | 1 | mixed_basket | answered/owe 0.07 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G04 | 1 | mixed_basket | answered/owe 6.70 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G05 | 1 | mixed_basket | answered/owe 2.71 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G06 | 1 | mixed_basket | answered/owe 5.45 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G08 | 1 | mixed_basket | answered/owe 4.72 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G09 | 1 | mixed_basket | answered/owe 0.61 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | G10 | 1 | mixed_basket | answered/owe 1.49 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | H01 | 1 | whatif | answered/whatif 9.47 | escalated/escalated  | wrong_outcome:answered->escalated | feature_not_built | Not built (stretch) | feature_not_built |  |
| tool_calling | H02 | 1 | whatif | answered/whatif 18.77 | escalated/escalated  | wrong_outcome:answered->escalated | feature_not_built | Not built (stretch) | feature_not_built |  |
| tool_calling | H03 | 1 | whatif | answered/whatif 3.57 | escalated/escalated  | wrong_outcome:answered->escalated | feature_not_built | Not built (stretch) | feature_not_built |  |
| tool_calling | H04 | 1 | whatif | answered/whatif 0.00 | clarify/clarify  | unnecessary_clarify | feature_not_built | Not built (stretch) | feature_not_built |  |
| tool_calling | I01 | 2 | clarify | answered/owe 2.97 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I02 | 2 | clarify | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I03 | 2 | clarify | answered/owe 0.35 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I04 | 2 | clarify | answered/owe 1.60 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I05 | 2 | clarify | answered/owe 2.17 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I06 | 2 | clarify | answered/owe 0.42 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I07 | 1 | clarify | clarify/clarify  | escalated/escalated  | wrong_outcome:clarify->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I07 | 2 | clarify | answered/owe 0.71 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I08 | 1 | clarify | clarify/clarify  | escalated/escalated  | wrong_outcome:clarify->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | I08 | 2 | clarify | answered/nothing_owed 0.00 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | J01 | 1 | state_flag | answered/owe 1.35 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | J02 | 1 | state_flag | answered/owe 2.85 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | J03 | 1 | state_flag | answered/owe 3.45 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| tool_calling | K05 | 1 | out_of_scope | out_of_scope/out_of_scope  | clarify/clarify  | wrong_outcome:out_of_scope->clarify | extraction_error | Reasoning error | extraction_error |  |
| tool_calling | L02 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss |  |
| tool_calling | L03 | 1 | refuse_evasion | refused/refused  | clarify/clarify  | wrong_outcome:refused->clarify | refusal_miss | Reasoning error | refusal_miss |  |
| tool_calling | M02 | 1 | injection_doc | answered/owe 1.60 | escalated/escalated  | wrong_outcome:answered->escalated | tool_failure | Tool-call error | tool_failure |  |
| single_rag | A01 | 1 | alcohol_excess_800 | answered/owe 3.23 | answered/owe 180.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A02 | 1 | alcohol_excess_800 | answered/owe 5.96 | answered/owe 16.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A03 | 1 | alcohol_excess_800 | answered/owe 1.37 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A04 | 1 | alcohol_excess_800 | answered/owe 1.62 | answered/owe 14.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A05 | 1 | alcohol_excess_800 | answered/owe 1.01 | answered/owe 16.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A06 | 1 | alcohol_excess_800 | answered/owe 4.12 | answered/owe 120.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A07 | 1 | alcohol_excess_800 | answered/nothing_owed 0.00 | answered/owe 14.50 | wrong_kind, wrong_amount | invented_figure | Hallucination | invented_figure |  |
| single_rag | A08 | 1 | alcohol_excess_800 | answered/owe 3.57 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A09 | 1 | alcohol_excess_800 | answered/owe 0.57 | answered/owe 18.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A10 | 1 | alcohol_excess_800 | answered/owe 3.65 | answered/owe 10.80 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A11 | 1 | alcohol_excess_800 | answered/owe 1.60 | answered/owe 20.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | A12 | 1 | alcohol_excess_800 | answered/nothing_owed 0.00 | answered/nothing_owed 0.00 | missing_citation | retrieval_miss | Retrieval miss | retrieval_miss |  |
| single_rag | B01 | 1 | alcohol_cbi_2L | answered/nothing_owed 0.00 | answered/owe 12.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | B02 | 1 | alcohol_cbi_2L | answered/owe 1.01 | answered/owe 12.60 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | B03 | 1 | alcohol_cbi_2L | answered/owe 0.71 | answered/owe 14.70 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | B04 | 1 | alcohol_cbi_2L | answered/owe 2.03 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C01 | 1 | exemption_200_all_or_nothing | answered/owe 2.14 | answered/owe 14.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C02 | 1 | exemption_200_all_or_nothing | answered/owe 0.21 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C03 | 1 | exemption_200_all_or_nothing | answered/owe 3.20 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C04 | 1 | exemption_200_all_or_nothing | answered/nothing_owed 0.00 | answered/nothing_owed 0.00 | missing_citation | retrieval_miss | Retrieval miss | retrieval_miss |  |
| single_rag | C05 | 1 | exemption_200_all_or_nothing | answered/mixed 0.11 | answered/owe 10.50 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C06 | 1 | exemption_200_all_or_nothing | answered/owe 3.45 | answered/owe 10.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C07 | 1 | exemption_200_all_or_nothing | answered/seizure_risk 0.00 | answered/nothing_owed 0.00 | wrong_kind, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | C08 | 1 | exemption_200_all_or_nothing | answered/owe 2.14 | answered/owe 14.15 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D01 | 1 | tobacco_over_limit | clarify/clarify  | answered/owe 14.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | D01 | 2 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/owe 14.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D02 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/nothing_owed 0.00 | wrong_kind, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D03 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/owe 105.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D04 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/owe 100.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D05 | 1 | tobacco_over_limit | answered/nothing_owed 0.00 | answered/owe 11.50 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D06 | 1 | tobacco_over_limit | answered/mixed 0.50 | answered/owe 105.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | D07 | 1 | tobacco_over_limit | answered/seizure_risk 0.00 | answered/nothing_owed 0.00 | wrong_kind, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | E01 | 1 | cuban_origin | answered/prohibited 0.00 | clarify/clarify  | unnecessary_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | E02 | 1 | cuban_origin | answered/prohibited 0.00 | answered/nothing_owed 0.00 | wrong_kind, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | E03 | 1 | cuban_origin | answered/prohibited 0.00 | clarify/clarify  | unnecessary_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | E04 | 1 | cuban_origin | clarify/clarify  | answered/owe 10.50 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | E04 | 2 | cuban_origin | answered/prohibited 0.00 | clarify/clarify  | unnecessary_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | E05 | 1 | cuban_origin | clarify/clarify  | answered/nothing_owed 0.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | E05 | 2 | cuban_origin | answered/nothing_owed 0.00 | answered/nothing_owed 0.00 | missing_citation | retrieval_miss | Retrieval miss | retrieval_miss |  |
| single_rag | E06 | 1 | cuban_origin | answered/mixed 0.44 | answered/owe 24.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | E07 | 1 | cuban_origin | answered/prohibited 0.00 | clarify/clarify  | unnecessary_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | F01 | 1 | under_21 | answered/owe 0.81 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | F02 | 1 | under_21 | answered/seizure_risk 0.00 | answered/nothing_owed 0.00 | wrong_kind, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | F03 | 1 | under_21 | answered/owe 4.28 | answered/owe 10.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | F04 | 1 | under_21 | answered/mixed 1.03 | answered/owe 10.50 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G01 | 1 | mixed_basket | answered/mixed 0.00 | answered/owe 105.50 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G02 | 1 | mixed_basket | answered/owe 2.50 | answered/owe 102.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G03 | 1 | mixed_basket | answered/owe 0.07 | answered/owe 10.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G04 | 1 | mixed_basket | answered/owe 6.70 | answered/owe 104.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G05 | 1 | mixed_basket | answered/owe 2.71 | answered/owe 100.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G06 | 1 | mixed_basket | answered/owe 5.45 | answered/owe 102.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G07 | 1 | mixed_basket | escalated/escalated  | answered/owe 112.00 | escalation_miss | rule_selection_error | Reasoning error | rule_selection_error |  |
| single_rag | G08 | 1 | mixed_basket | answered/owe 4.72 | answered/owe 14.40 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G09 | 1 | mixed_basket | answered/owe 0.61 | answered/owe 14.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | G10 | 1 | mixed_basket | answered/owe 1.49 | answered/owe 10.50 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | H01 | 1 | whatif | answered/whatif 9.47 | answered/owe 9.99 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built |  |
| single_rag | H02 | 1 | whatif | answered/whatif 18.77 | answered/owe 12.00 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built |  |
| single_rag | H03 | 1 | whatif | answered/whatif 3.57 | answered/owe 4.95 | wrong_kind, wrong_amount, missing_citation | feature_not_built | Not built (stretch) | feature_not_built |  |
| single_rag | H04 | 1 | whatif | answered/whatif 0.00 | answered/owe 0.00 | wrong_kind, missing_citation | feature_not_built | Not built (stretch) | feature_not_built |  |
| single_rag | I01 | 1 | clarify | clarify/clarify  | answered/owe 14.40 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I01 | 2 | clarify | answered/owe 2.97 | answered/owe 9.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | I02 | 1 | clarify | clarify/clarify  | answered/nothing_owed 0.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I02 | 2 | clarify | answered/nothing_owed 0.00 | answered/nothing_owed 0.00 | missing_citation | retrieval_miss | Retrieval miss | retrieval_miss |  |
| single_rag | I03 | 1 | clarify | clarify/clarify  | answered/owe 102.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I03 | 2 | clarify | answered/owe 0.35 | clarify/clarify  | unnecessary_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I04 | 1 | clarify | clarify/clarify  | answered/owe 15.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I04 | 2 | clarify | answered/owe 1.60 | answered/owe 15.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | I05 | 1 | clarify | clarify/clarify  | answered/owe 12.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I05 | 2 | clarify | answered/owe 2.17 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | I06 | 1 | clarify | clarify/clarify  | answered/owe 12.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I06 | 2 | clarify | answered/owe 0.42 | clarify/clarify  | unnecessary_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I07 | 1 | clarify | clarify/clarify  | answered/owe 12.00 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I07 | 2 | clarify | answered/owe 0.71 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | I08 | 1 | clarify | clarify/clarify  | answered/owe 14.50 | no_clarify | clarify_miss | Reasoning error | clarify_miss |  |
| single_rag | I08 | 2 | clarify | answered/nothing_owed 0.00 | answered/nothing_owed 0.00 | missing_citation | retrieval_miss | Retrieval miss | retrieval_miss |  |
| single_rag | J01 | 1 | state_flag | answered/owe 1.35 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | J02 | 1 | state_flag | answered/owe 2.85 | answered/owe 24.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | J03 | 1 | state_flag | answered/owe 3.45 | answered/owe 12.00 | wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
| single_rag | K01 | 1 | out_of_scope | out_of_scope/out_of_scope  | answered/prohibited 0.00 | scope_miss | rule_selection_error | Reasoning error | rule_selection_error |  |
| single_rag | K02 | 1 | out_of_scope | out_of_scope/out_of_scope  | answered/owe 0.00 | scope_miss | rule_selection_error | Reasoning error | rule_selection_error |  |
| single_rag | K03 | 1 | out_of_scope | out_of_scope/out_of_scope  | answered/owe 12.00 | scope_miss | rule_selection_error | Reasoning error | rule_selection_error |  |
| single_rag | K04 | 1 | out_of_scope | out_of_scope/out_of_scope  | answered/nothing_owed 0.00 | scope_miss | rule_selection_error | Reasoning error | rule_selection_error |  |
| single_rag | K05 | 1 | out_of_scope | out_of_scope/out_of_scope  | clarify/clarify  | wrong_outcome:out_of_scope->clarify | rule_selection_error | Reasoning error | rule_selection_error |  |
| single_rag | L02 | 1 | refuse_evasion | refused/refused  | answered/owe 0.00 | refusal_miss | refusal_miss | Reasoning error | refusal_miss |  |
| single_rag | L03 | 1 | refuse_evasion | refused/refused  | answered/prohibited 0.00 | refusal_miss | refusal_miss | Reasoning error | refusal_miss |  |
| single_rag | M02 | 1 | injection_doc | answered/owe 1.60 | answered/nothing_owed 0.00 | wrong_kind, wrong_amount, missing_citation | invented_figure | Hallucination | invented_figure |  |
