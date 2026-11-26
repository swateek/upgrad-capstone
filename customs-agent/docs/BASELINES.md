# Week 1 prompting baselines (Day 4)

Official run `week1` on `eval-v2` (80 scenarios), cache off, Qwen/Qwen3-8B. Closed book: the model gets the task and the answer format, but no rules, no retrieval and no calculators. Prompts were tuned on the dev set only (runs `day4-dev`, `day4-dev-v2`) and frozen before this run. Raw answers: `results/runs/week1/`; tables: `results/week1_strategies.csv`, `results/week1_failures.csv`.

## Headline

| Strategy | Calls / q | Tokens / q | Accuracy | Outcome | Bottom line | Dollars (n=42) | Clarify (n=8) | Citations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| closed_book | 1 | 700 | 0.100 | 0.825 | 0.63 | 0.000 | 0.000 | 0.068 |
| fewshot_json | 1 | 1,665 | **0.175** | 0.812 | 0.63 | 0.048 | 0.000 | **0.61** |
| cot_sc | 3 | 2,597 | 0.113 | 0.800 | 0.56 | 0.071 | 0.000 | 0.068 |
| decompose | 2.15 | 1,423 | 0.113 | 0.388 | 0.07 | 0.071 | 0.125 | 0.000 |

Accuracy = every applicable check passes (docs/SPEC.md 6). **No strategy fully answers a single question that has a dollar amount, a prohibition with a citation (except few-shot on Cuba), or a missing fact.** Correct answers come almost only from refusals (evasion 4/4 and user injection in every strategy; out of scope 2–4 of 5).

## What fails, and what it means for the agent

| Finding | Evidence | Design answer |
| --- | --- | --- |
| The model cannot do customs arithmetic | Dollar accuracy 0–7%. Median dollar error: closed_book $11.43, cot_sc $6.29, fewshot_json $1.53, decompose $0.57 (when it answers) | Calculators compute every amount; the model never does arithmetic (CLAUDE.md rule 1) |
| It does not know the regulations | Citation accuracy 7% without examples; it cites tariff chapters 22 (not 9816) and invents sections ("21 CFR 10.115", 63 times in decompose). Few-shot examples lift it to 61%, but only for the patterns shown | Retrieval puts the regulation text in the prompt; the writer cites only retrieved `citation_id`s; the verifier checks them |
| It never asks for missing facts | Clarify 0/8 in three strategies: it guesses and answers (8 of 8 clarify scenarios answered) | Code decides which facts are missing (SPEC 5.2); the planner only phrases one question |
| When asked to decide missing facts, it contradicts its own extraction | decompose: 41 of 80 answerable questions turned into clarify, flagging facts its first step had filled in | Same: missing facts come from the tools, not the model |
| It does not escalate | Russian vodka, over-band and commercial quantity answered in every strategy except decompose (once) | check_restrictions and compute_duty_excise escalate by rule |
| Rules it gets wrong | Tobacco over the limit taxed instead of "declare" (best 1/7); $200 all-or-nothing and the 2 L rule never right; under-21 never right | Rules live in `rules.yaml`, applied by code |
| What it does well | Recognises evasion and prompt injection (100%); outcome type right ~80% | Keep the code guard anyway (cheap, deterministic) |
| More sampling is not a fix | cot_sc costs 3.7× the tokens of closed_book for +1 point of accuracy and lower bottom-line accuracy | Spend calls on tools and verification, not repeated sampling |

## Caveats

- Few-shot examples (D01, D05, D08, D13, D16) come from the dev set, so few-shot results reflect what those five patterns teach (Cuba 5/6 correct, citations 61%).
- Injection-in-document scenarios have no retrieval here, so the planted text never reaches these baselines; they fail on dollars.
- State flag is reported, not scored: 1 of 3 for three strategies.
