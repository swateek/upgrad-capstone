# 5. Agent design and the planner vs. router ablation

## 5.1 The request flow

DeclareRight answers one question with a fixed pipeline. The 8B model reads and writes; code decides. Every dollar, volume, count and allowance comes from a calculator in `src/tools/`, and every rule and rate is a row in `data/rules.yaml` or `data/rates.yaml` with its citation and as-of date (CLAUDE.md rules 1–3).

| Stage | Who | What it does |
| --- | --- | --- |
| Guard | code | Refuses injection, evasion and out-of-scope requests (other goods, non-residents, shipped goods, crew, vapes) before any model call; a scope note when alcohol or tobacco is also asked about |
| Intake | LLM (JSON schema) | Reads the traveller's profile (age, trip, 30-day history, arrival) and basket (item, quantity, size, ABV, price, origin) |
| Clean-up | code | Checks every fact against the question: drops values the question does not state, fills sizes, counts, origins and history the model missed, fixes product types by name (`pipeline.clean`, COMPENSATIONS rows 5–31) |
| Plan | LLM planner + code validator, or code router | The order of tools; the validator enforces the allowed-step graph (below) |
| Tools | code | `normalise_units` → `check_restrictions` → `determine_exemption` → `compute_allowance` → `compute_duty_excise` → `lookup_state_rule` → `search_regulations`; `whatif_optimise` and `escalate_to_human` when needed |
| Answer card | code | The bottom line and the working, from the tool outputs only |
| Writer | LLM | A plain explanation of the card, citing only the clauses retrieved for this question |
| Verifier | code + 1 LLM call | Every number must come from a tool, the facts or the question; citations only from the retrieved, frozen-corpus clauses; an LLM check for evasion advice. One retry with the problems fed back, then unsupported sentences are removed, else escalate |

The outcome is one of four: **answered**, **clarify** (one round asking only for facts that change the answer), **refused** or **escalated** (§6.3). A conversation keeps its state in LangGraph with a SQLite checkpointer; a correction ("actually it was 30 hours") re-runs only the tools that depend on the changed fact (`tests/test_session.py::test_correction_replans_only_dependent_steps`). All 13 scripted conversations, 30 turns, are answered correctly by agent v2 (`v2d-conversations`).

Error handling: malformed JSON gets two retries with the validation error fed back; a tool error goes back to the plan; an identical repeated call is blocked; a hard budget of 10 tool steps and 12,000 tokens per question. No official run hit the budget (at most 8 tool steps; completion 1.00 on every arm, `docs/METRICS.md`).

## 5.2 What the model does, and what it does not

The model has three jobs: read the question into a schema, write the explanation, and (in planner mode) choose the order of tools. It never computes an amount, chooses a rule or picks a citation outside the retrieved set. From agent v2 the bottom-line sentence is also built in code: on dev-v2 the writer had copied the prompt's example amount ("You owe $2.97 on the wine" for cigarettes) or added two excesses itself, and the verifier escalated correct answers; with the bottom line in code no writer retry or pruning was needed on any of the 112 dev-v2 questions (COMPENSATIONS row 31).

## 5.3 Planner vs. router

The mentor design has an LLM planner choosing the tools, checked by a validator: only known tools, each once, at most 10 steps, `search_regulations` last; restrictions before any calculation (rule 4); `whatif_optimise` first and only for a what-if question; `lookup_state_rule` when an arrival state is known; `escalate_to_human` only after `check_restrictions`. An invalid plan gets one repair; a second failure falls back to the code router's plan. The code router is the same tool order written as code, the ablation baseline.

| Set | Arm | Accuracy | Tokens/q | Model calls/q | p50 / p95 s | Plan fallbacks |
| --- | --- | --- | --- | --- | --- | --- |
| eval-v2 | agent v1, router | 0.750 | 2,882 | 2.49 | 9.2 / 14.4 | – |
| eval-v2 | agent v1, planner (3 runs) | 0.750 (0.75–0.75) | 3,528 | 3.66 | 11.6 / 17.1 | 0 / 71 per run |
| eval-v3 | agent v2, router | 0.770 | 2,769 | 2.33 | 9.1 / 14.4 | – |
| eval-v3 | agent v2, planner (3 runs) | 0.770 (0.77–0.77) | 3,430 | 3.51 | 11.9 / 17.8 | 0 / 87 per run |

Source: `docs/ABLATION.md`, `docs/METRICS.md`.

On both held-out sets the planner and the router give **the same answer on every question**, in every run. The planner's plan differs from the router's on 41 of 87 planned questions on eval-v3 (38 of 71 on eval-v2), and in all but one case the only difference is that it skips `lookup_state_rule` when no arrival state was given, which changes nothing. Planning costs about 24% more tokens, one more model call and 2.8 s more at the median per question. The validator never had to fall back.

**Decision.** For this task a fixed tool order is enough: the questions differ in their facts, not in the steps needed to answer them. The planner is kept because the mentor design asks for it and the ablation shows it is safe (validated, never worse); a deployment on cost would use the router. This is a valid, reportable result: a planner that does not beat the router is evidence about the task, not a failure.

## 5.4 Agent v1 and v2

Agent v1 was frozen (`v1.0.0-rc`) and run on eval-v2: 0.75. Its 20 failures were mostly reading (item types such as Champagne and sake, missed facts, demonyms), 3 guard misses and 2 citation-slot misses (`docs/TAXONOMY.md`, WORKLOG Day 10). Agent v2 (`v2.0.0-rc`) adds SPEC v2 (sake taxed as beer, the origin asked when it changes the duty, the ABV asked in the first round) and code fixes for those failure classes, tuned on a new dev set only (dev-v2, 112 questions: 0.607 → 0.991). Two prompt lines changed; everything else is code and data.

| eval-v3 (100 new questions) | Accuracy | $ accuracy | Citations | Clarify P / R |
| --- | --- | --- | --- | --- |
| single_rag (one call with retrieval) | 0.07 | 0.02 | 0.11 | – / 0.00 |
| agent v1, router | 0.52 | 0.57 | 0.57 | 0.24 / 0.80 |
| agent v2, router | 0.77 | 0.77 | 0.79 | 0.43 / 1.00 |

Like for like, v2 fixes 27 of v1's 48 failures and breaks 2. Part of the gain is SPEC v2 rules that v1 never had; part is reading. The gap between dev-v2 (0.991) and eval-v3 (0.77) is the honest measure of how far the code rules generalise: they cover the phrasings they were written from, and new writers say the same facts in other words. 20 of v2's 23 eval-v3 failures start in reading the question (11 missed facts, 5 wrong, 4 invented); the clearest symptom is clarify precision 0.43: v2 asks for every fact it should (recall 1.00) but also asks for facts the question gave. Retrieval is not the bottleneck: where the agent reached search, every gold citation was in front of the writer on 93% of questions, and each of the other 4 began with a misread fact (`docs/RECALL_VS_ACCURACY.md`).

One gold error was found in eval-v3 while labelling and confirmed by both reviewers of the failure labels (E3-019: a 15.5% wine taxed at the over-16% rate; the agent's $1.10 is right). Accuracy is reported as scored, 0.77, and with E3-019 corrected, 0.78. The failure labels themselves agree with two independent reviewers on 27 and 26 of 28 checked items (κ 0.95 and 0.90; the reviewers agree with each other on 27, κ 0.95), with the caveat that the reviewers saw the proposed label (`docs/TAXONOMY.md`).
