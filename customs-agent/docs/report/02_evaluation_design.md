# 2. Evaluation design

No public question set exists for this domain, so every set was built for the project, with its gold computed independently of the code under test (CLAUDE.md rule 5).

## 2.1 The sets

| Set | n | Written by | Used for |
| --- | --- | --- | --- |
| dev | 20 | Project owner, from the regulation text | Tuning agent v1 |
| **eval-v2** (gold-v1) | 80 | Project owner, same way | **Held out for agent v1**; the Day 4 prompting baselines |
| paraphrase | 60 | A separate session that had not seen the agent's code, from a brief: 3 rewordings of each dev question, same facts and gold | Generalisation check for v1 (first run 0.883) |
| red-team | 20 | Project owner: 5 user injections, 2 planted documents, 4 evasion, 5 out of scope, 3 real phrasings, 1 with personal data | Safety regression (§6) |
| conversations | 13 (30 turns) | Project owner | Clarify answers and corrections across turns |
| dev-v2 | 112 | Five AI generators (Claude, ChatGPT, Gemini, Groq-hosted, Mistral), from one SPEC v2 prompt | Tuning agent v2 |
| **eval-v3** | 100 | Same generation, split from dev-v2 at random within each type | **Held out for agent v2** |
| gold-v2 | 80 | eval-v2's questions re-scored under SPEC v2 (6 gold changes, each with its rule) | Agent v2 on eval-v2, labelled as such: those questions shaped the v2 fixes |

eval-v2 follows the mentor's type mix (15 types: $800 excess 12, $200 all-or-nothing 8, mixed baskets 10, clarify 8, tobacco over the limit 7, Cuban origin 6, Russian origin 1, 2 L 4, under 21 4, what-if 4, state flag 3, out of scope 5, evasion 4, injection 2 + 2). eval-v3 keeps the same types with 100 items (for example $800 excess 17, tobacco 10, clarify 10, under 21 6, injection in the question 4).

**eval-v1 → eval-v2.** On Day 3 the HTSUS text corrected the 2 L country list (SPEC 5.5), which changed two gold answers (E15, E48). No run had used eval-v1, so the set was re-tagged `eval-v2` before any result existed.

**Why eval-v3.** eval-v2 was spent once agent v1 ran on it: its failures shaped agent v2, so v2's score on it (1.00 under gold-v2) measures fitting, not generalisation. eval-v3 was generated, checked and frozen before any v2 fix was written. The generation prompt carried the SPEC v2 rules and the type mix, and no hint of v1's failures; the generators labelled only the judgement parts (outcome, bottom line, clarify facts, state flag, forbidden phrases), never dollars or citations.

## 2.2 Gold

- **Dollars by spreadsheet formulas**, with the rates typed in from TTB and HTSUS 9816.00.20 (`eval/gold.xlsx`, `gold_v3.xlsx`), never by `src/tools/`. Each workbook was checked against a separate decimal calculation outside the repository: 61 priced lines and 5 what-if answers for eval-v2 and dev, 135 priced lines for eval-v3 and dev-v2, 0 differences.
- **Allocation and citations by fixed rules** in the build scripts (highest duty plus excise per litre first, SPEC 5.4), with the regulation ids from `rules.yaml`.
- **Hand checks.** eval-v2: 20 scenarios re-checked by hand the next day (solo protocol). eval-v3: an independent rule checker (`eval/check_v3.py`, imports nothing from `src/`) flagged 8 of 217 generated scenarios. In all 9 were corrected with the rule cited (including arrival states added after the owner's first findings) and 5 dropped (a cut-off reply, three duplicates and one close copy of an eval-v2 item), leaving 212. The owner checked 15 random eval-v3 items and every corrected one: 24, all right.
- **Errata, not edited after tagging.** E3-019 (eval-v3): a 15.5% wine taxed at the over-16% rate; the right total is $1.10, not $1.17. Found while labelling failures and confirmed by both reviewers (§5.4). D2-055 (dev-v2): gold answers a case SPEC 3 escalates. Results are reported as scored, with the erratum noted.

## 2.3 What counts as correct

A scenario is correct only when every applicable check passes (SPEC 6):

1. the outcome and every bottom-line type match gold;
2. every dollar figure is within $0.01 of gold;
3. every gold citation is cited, and nothing is cited outside the clauses retrieved for this question;
4. a clarifying question is asked exactly when gold asks, in one message asking for all the gold facts and nothing outside the current stage;
5. no forbidden phrase (`must_not_contain`) appears, for example "nothing is owed" in a planted-document item.

`eval/score.py` scores all of this in code; no LLM judge is used for any reported number. The state note is reported but not scored. The failure labels (§5, §6) come from rules in code, hand-checked by two independent reviewers on 28 items (κ 0.95 between them).

## 2.4 Keeping the held-out sets honest

- **Freeze.** Before an official run, `eval/freeze.py` records the prompt hashes, retrieval settings, token budget, the corpus fingerprint and (from v2) a hash of every source file and both data tables. `run_agent.py` refuses a held-out set unless the code matches the freeze, the response cache is off and the state notes are the SPEC's five. `eval/replay.py`, which re-runs recorded model readings through new code at no cost, refuses held-out sets.
- **No tuning on held-out sets.** Nothing was fixed and re-run on eval-v2 after agent v1's run, or on eval-v3 after agent v2's. Fixes found on a held-out set are future work.
- **Official runs** (overnight, cache off, one request at a time): for each agent version, three LLM-planner runs, one code-router run and one single_rag run on its held-out set. Agent v1 was also run once on eval-v3 (router), from its frozen tag in a separate worktree, so the two versions are compared on the same new questions.
