# Structured-output reliability

Built by `eval/reliability.py` from the official runs (planner arms pool their three runs). JSON stages use `json_schema` output, Pydantic validation and up to 2 repairs; plans are checked by the validator, repaired once, else replaced by the router's plan.

## eval-v2, gold-v1 (agent v1's held-out set)

| Arm | Questions | Model calls | JSON repairs | Still invalid | Planned | First plan invalid | Fixed by one repair | Fallbacks | Writer retried | Sentences pruned | Verifier escalations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent v1, code router | 80 | 184 | 0 | 0 | – | – | – | – | 5 | 0 | 1 |
| agent v1, LLM planner | 240 | 813 | 0 | 0 | 213 | 48 | 48 | 0 | 15 | 0 | 3 |

Most common reasons a first plan was invalid:

- agent v1, LLM planner: 48 × search_regulations must be the last step; 12 × a what-if question starts with whatif_optimise; 12 × missing steps

## eval-v3 (agent v2's held-out set, SPEC v2)

| Arm | Questions | Model calls | JSON repairs | Still invalid | Planned | First plan invalid | Fixed by one repair | Fallbacks | Writer retried | Sentences pruned | Verifier escalations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent v1, code router | 100 | 190 | 0 | 0 | – | – | – | – | 1 | 0 | 0 |
| agent v2, code router | 100 | 210 | 1 | 0 | – | – | – | – | 1 | 1 | 0 |
| agent v2, LLM planner | 300 | 949 | 3 | 0 | 261 | 58 | 58 | 0 | 3 | 3 | 0 |

Most common reasons a first plan was invalid:

- agent v2, LLM planner: 58 × search_regulations must be the last step; 15 × a what-if question starts with whatif_optimise; 15 × missing steps

## eval-v2 re-scored under SPEC v2 (gold-v2): informed the v2 fixes

| Arm | Questions | Model calls | JSON repairs | Still invalid | Planned | First plan invalid | Fixed by one repair | Fallbacks | Writer retried | Sentences pruned | Verifier escalations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent v2, code router | 80 | 193 | 0 | 0 | – | – | – | – | 5 | 3 | 0 |
| agent v2, LLM planner | 80 | 277 | 0 | 0 | 69 | 16 | 16 | 0 | 4 | 3 | 0 |

Most common reasons a first plan was invalid:

- agent v2, LLM planner: 16 × search_regulations must be the last step; 4 × a what-if question starts with whatif_optimise; 4 × missing steps
