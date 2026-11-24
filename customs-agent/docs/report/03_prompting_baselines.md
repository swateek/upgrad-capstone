# 3. Prompting baselines and the small model's failures

## 3.1 What the endpoint can do (Day 0)

Before any design, `prechecks/check_endpoint.py` tested the course endpoint: Qwen3-8B made a structured tool call in 3 of 3 tries, and both `json_schema` (constrained decoding) and `json_object` output worked; the embedding endpoint serves `bge-small-en-v1.5` (384 dimensions, 512-token inputs). So the planner uses native tool calls and every other model output is constrained by a JSON schema and validated with Pydantic (COMPENSATIONS row 1).

## 3.2 Four strategies, no tools (Day 4 gate)

Before any agent code, four prompting strategies were run on eval-v2 with no retrieval and no calculators: the model does all the reasoning and arithmetic. Prompts were tuned on the dev set only and frozen before the official run (`week1`, cache off).

- **closed_book:** one call, the task and the answer format.
- **fewshot_json:** one call with five worked dev examples (D01, D05, D08, D13, D16).
- **cot_sc:** three sampled reasoning calls, majority vote on the outcome and bottom line.
- **decompose:** three calls: extract the facts, decide the rules, compute and answer.

| Strategy | Calls/q | Tokens/q | Accuracy | Outcome | Bottom line | Dollars (n = 42) | Clarify (n = 8) | Citations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| closed_book | 1 | 700 | 0.100 | 0.825 | 0.63 | 0.000 | 0.000 | 0.068 |
| fewshot_json | 1 | 1,665 | **0.175** | 0.812 | 0.63 | 0.048 | 0.000 | **0.61** |
| cot_sc | 3 | 2,597 | 0.113 | 0.800 | 0.56 | 0.071 | 0.000 | 0.068 |
| decompose | 2.15 | 1,423 | 0.113 | 0.388 | 0.07 | 0.071 | 0.125 | 0.000 |

Source: `results/week1_strategies.csv`, `docs/BASELINES.md`.

No strategy fully answers a single question that has a dollar amount, a missing fact, or a prohibition with its citation (except few-shot on Cuba, whose pattern is in the examples). Almost every correct answer is a refusal: evasion 4 of 4 and user injection in every strategy.

## 3.3 What the failures say

| Finding | Evidence (eval-v2) | Design answer |
| --- | --- | --- |
| It cannot do customs arithmetic | Dollar accuracy 0–7%; median dollar error $11.43 closed book, $0.57 decompose (when it answers) | Calculators compute every amount (rule 1) |
| It does not know the regulations | Citations 7% without examples; tariff chapter 22 cited instead of 9816; "21 CFR 10.115" invented 63 times in decompose. Few-shot lifts citations to 61%, only for the patterns shown | Retrieval brings the regulation text; citations only from retrieved clauses (rule 2) |
| It never asks for a missing fact | Clarify 0 of 8 in three strategies: it guesses and answers | Code decides which facts are missing (SPEC 5.2); the model only phrases the question |
| Asked to decide, it contradicts itself | decompose turned 41 of 80 answerable questions into a clarifying question, about facts its own first step had filled in | Same |
| It does not escalate | Russian vodka, over the $1,000 band and commercial quantity answered by every strategy except decompose (once) | Escalation rules in `rules.yaml`, applied by code |
| It gets the rule interactions wrong | $200 all-or-nothing, the 2 L rule and under 21: never right; tobacco over the limit taxed instead of "declare" (best 1 of 7) | Rules as data, applied by code (rule 3) |
| More sampling does not help | cot_sc: 3.7 times the tokens of closed book for 1 point of accuracy, and a lower bottom-line score | Spend calls on tools and checking, not sampling |
| What it does well | Recognises evasion and injection (100%); outcome type right about 80% of the time | Keep the code guard anyway: cheap and deterministic |

## 3.4 The agent's first failures (Days 5–9)

Once the agent existed, its failures on the dev, paraphrase, red-team and conversation sets were fixed one by one, each with its cause found by hand (`eval/taxonomy_check.csv`, 29 failures). The rules-based labeller later gave the same cause for 28 of them (§5.4):

| Cause | n |
| --- | --- |
| Reading the question: a stated fact missed | 7 |
| Reading the question: a fact invented | 7 |
| Reading the question: a wrong value (a country name for a code, the shop's country as the origin, "a pack of 20" as 20 packs) | 4 |
| Unit conversion (two 1-litre bottles read as one 2-litre bottle; a box of 10 cigars not read) | 2 |
| Guard missed an injection, an evasion or an out-of-scope item | 5 |
| Intake called a fair question evasion | 2 |
| Writer did its own arithmetic | 1 |
| Verifier rejected a right number the card had not stated | 1 |

18 of 29 are in reading the question, and none is in a calculation or a rule. That set the pattern for everything after: the 8B model's weak point is turning free text into facts, so most of the compensation work (§7) is code that checks each fact against the question.
