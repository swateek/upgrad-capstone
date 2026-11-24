# Tokens per model call

Built by `eval/token_calls.py` from the official runs (`results/runs/*/<mode>.jsonl`, the `steps` of each record). Tokens are the endpoint's `total_tokens` for the call, input plus output. Limits: 8,192 per call (endpoint), 12,000 per question (design budget); target under 3,000 input per call. Planner arms pool their three runs.

## eval-v2, gold-v1 (agent v1's held-out set)

| Arm | Stage | Calls | p50 | p95 | Max | Calls over 3,000 | Over the call limit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent v1, code router | intake | 74 | 933 | 1,182 | 1,186 | 0 | 0 |
| agent v1, code router | writer | 58 | 2,321 | 2,549 | 2,662 | 0 | 0 |
| agent v1, code router | verifier | 52 | 168 | 197 | 204 | 0 | 0 |
| agent v1, code router | all calls | 184 | 934 | 2,446 | 2,662 | 0 | 0 |
| agent v1, LLM planner | intake | 222 | 933 | 1,182 | 1,186 | 0 | 0 |
| agent v1, LLM planner | planner | 261 | 539 | 609 | 671 | 0 | 0 |
| agent v1, LLM planner | writer | 174 | 2,321 | 2,549 | 2,662 | 0 | 0 |
| agent v1, LLM planner | verifier | 156 | 168 | 197 | 206 | 0 | 0 |
| agent v1, LLM planner | all calls | 813 | 653 | 2,427 | 2,662 | 0 | 0 |

Largest question (all calls together):

- agent v1, code router: 6,319 tokens; 0 questions over 12,000.
- agent v1, LLM planner: 6,903 tokens; 0 questions over 12,000.

## eval-v3 (agent v2's held-out set, SPEC v2)

| Arm | Stage | Calls | p50 | p95 | Max | Calls over 3,000 | Over the call limit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent v1, code router | intake | 91 | 954 | 1,211 | 1,246 | 0 | 0 |
| agent v1, code router | writer | 50 | 2,384 | 2,702 | 2,805 | 0 | 0 |
| agent v1, code router | verifier | 49 | 165 | 213 | 226 | 0 | 0 |
| agent v1, code router | all calls | 190 | 954 | 2,515 | 2,805 | 0 | 0 |
| agent v2, code router | intake | 90 | 1,007 | 1,263 | 1,296 | 0 | 0 |
| agent v2, code router | writer | 61 | 2,390 | 2,724 | 2,988 | 0 | 0 |
| agent v2, code router | verifier | 59 | 172 | 227 | 241 | 0 | 0 |
| agent v2, code router | all calls | 210 | 1,010 | 2,521 | 2,988 | 0 | 0 |
| agent v2, LLM planner | intake | 270 | 1,007 | 1,263 | 1,296 | 0 | 0 |
| agent v2, LLM planner | planner | 319 | 552 | 617 | 668 | 0 | 0 |
| agent v2, LLM planner | writer | 183 | 2,390 | 2,734 | 2,988 | 0 | 0 |
| agent v2, LLM planner | verifier | 177 | 172 | 221 | 241 | 0 | 0 |
| agent v2, LLM planner | all calls | 949 | 613 | 2,477 | 2,988 | 0 | 0 |

Largest question (all calls together):

- agent v1, code router: 6,105 tokens; 0 questions over 12,000.
- agent v2, code router: 6,999 tokens; 0 questions over 12,000.
- agent v2, LLM planner: 7,558 tokens; 0 questions over 12,000.

## eval-v2 re-scored under SPEC v2 (gold-v2): informed the v2 fixes

| Arm | Stage | Calls | p50 | p95 | Max | Calls over 3,000 | Over the call limit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent v2, code router | intake | 72 | 987 | 1,236 | 1,240 | 0 | 0 |
| agent v2, code router | writer | 63 | 2,356 | 2,579 | 2,645 | 0 | 0 |
| agent v2, code router | verifier | 58 | 174 | 199 | 211 | 0 | 0 |
| agent v2, code router | all calls | 193 | 989 | 2,471 | 2,645 | 0 | 0 |
| agent v2, LLM planner | intake | 72 | 987 | 1,236 | 1,240 | 0 | 0 |
| agent v2, LLM planner | planner | 85 | 547 | 615 | 678 | 0 | 0 |
| agent v2, LLM planner | writer | 62 | 2,350 | 2,579 | 2,647 | 0 | 0 |
| agent v2, LLM planner | verifier | 58 | 174 | 199 | 211 | 0 | 0 |
| agent v2, LLM planner | all calls | 277 | 615 | 2,446 | 2,647 | 0 | 0 |

Largest question (all calls together):

- agent v2, code router: 6,596 tokens; 0 questions over 12,000.
- agent v2, LLM planner: 7,261 tokens; 0 questions over 12,000.
