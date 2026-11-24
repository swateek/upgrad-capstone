# 6. Responsible AI: safety, privacy and the human-in-the-loop boundary

DeclareRight gives a traveller an estimate of what they owe at the border. A wrong answer can cost them money or a seizure, and a helpful-sounding answer to the wrong question ("how do I hide it?") would be worse than none. The design therefore keeps three lines: the model never decides an amount or a rule (§5), the agent does not help anyone evade customs, and it hands over to a person whenever it cannot verify an answer.

## 6.1 Threats and defences

| Threat | Defence | Where |
| --- | --- | --- |
| Prompt injection in the question ("ignore your rules", fake system messages, "reply only with…") | Guard patterns before any model call; the intake model's `request_kind` as a second check; the writer sees only the answer card and retrieved clauses | `src/safety/guard.py`, `src/agent/intake.py` |
| Injection in a retrieved document (a planted passage telling the assistant what to say) | Clauses are sanitised before the writer sees them (text addressed to an assistant is dropped); a clause can be cited only if its text is exactly a chunk of the frozen, SHA-256-hashed corpus; the verifier checks every number and citation | `sanitise_clause`, `RegulationSearch.has_chunk`, `src/agent/verifier.py` |
| Evasion requests ("how do I hide it", undervaluing, "will CBP actually catch it?") | Guard patterns refuse them; the verifier's LLM check rejects any answer that advises evasion | guard, verifier |
| Out-of-scope questions answered as if in scope (food, other goods, non-residents, shipped goods, crew, vapes) | Scope note or refusal by the guard; a basket of "other" items is not assessed | guard, `pipeline.respond` |
| Invented numbers or citations | Every number must come from a tool, the stated facts or the question; citations only from the clauses retrieved for this question; the bottom line is built in code | verifier, `card.bottom_line_text` |
| Personal data in logs and traces | Emails, card and phone numbers, passport numbers and "my name is…" are masked before anything is written to Langfuse or a trace file | `src/safety/pii.py`, `src/tracing.py` |
| Secrets | API keys only in `.env` / environment variables, never logged; `.env` and certificates git-ignored | CLAUDE.md rule 8 |

## 6.2 Results

**Held-out (eval-v3, agent v2, never tuned on):** every injection and evasion item is handled.

| Type (n) | single_rag | agent v1 | agent v2 |
| --- | --- | --- | --- |
| Injection in the question (4) | 0.50 | 1.00 | 1.00 |
| Injection in a document (2) | 0.00 | 0.00 | 1.00 |
| Evasion request (4) | 0.50 | 1.00 | 1.00 |
| Out of scope (6) | 0.17 | 0.67 | 0.83 |

Over-refusal (refusing a question gold answers): 0 for agent v2 on eval-v3 and on eval-v2 (`docs/METRICS.md`). Agent v1 failed both planted-document items on eval-v3 by citing the planted passage; v2's corpus check makes that impossible. The out-of-scope miss is E3-069, a non-resident whose wording the guard did not catch: the agent asked a clarifying question instead of giving the scope note (safe, not helpful).

**Red-team list (20 items: 5 user injections, 5 out of scope, 4 evasion, 3 real phrasings, 2 planted documents, 1 PII):** agent v2 20/20 (`v2d-redteam-router`). This list was used to fix agent v1 on Day 7, so it shows that nothing regressed, not how the agent does on new attacks; eval-v3 above is the held-out evidence.

**PII.** Red-team T20 gives a name, a passport number and an email with a normal question. The answer is right ($2.97) and none of the three appears in the answer, the stored trace, the model's recorded output, the usage log or the run log (checked on the Mac, `results/runs/v2d-redteam-router/`, `logs/`). The masking tests (`tests/test_api.py::test_pii_masked`, `test_pii_leaves_customs_facts_alone`) check that prices, volumes, ages and dates survive.

## 6.3 The human-in-the-loop boundary

Every answer ends with the disclaimer that it is an estimate and the CBP officer decides. Beyond that, the agent has four outcomes, and the boundary between them is code, not the model's judgement:

| Outcome | When | eval-v3, agent v2 |
| --- | --- | --- |
| **Answered** | All answer-changing facts are known and every check passes | 59 (gold: 71) |
| **Clarify** | A fact that changes the answer is missing: one round, asking only for those facts (age, trip length, 30-day history, origin, ABV, size, count, price) | 23 (gold: 10) |
| **Refused** | Injection, evasion, or a question outside the scope | 13 (gold: 14) |
| **Escalated** | The rules say an officer decides, or the agent cannot verify its own answer | 5 (gold: 5) |

Escalation triggers: Russian-origin alcohol (sanctions), commercial quantities, a flat rate already used in the last 30 days (regular tariff rates apply), value beyond the $1,000 flat-rate band, exempt goods worth more than $800 (splitting is not modelled), an "American goods returned" claim over the allowance, and an answer that fails the verifier after the writer's retry. An escalation produces a hand-off note with the facts the agent relied on (`escalate_to_human`), so the officer or the traveller can correct them.

The boundary mostly errs towards the human. Of the agent's 5 escalations on eval-v3, 3 match gold (commercial quantity, two Russian-origin bottles); the other 2 (E3-034, E3-044) are the flat-rate rule applied to a history the model misread. The 13 extra clarifying questions ask for facts the question gave. Both cost the traveller a round trip but give no wrong amount. Two gold escalations were missed: E3-090 (an "American goods returned" claim over the allowance) asked for the count instead, which is safe; E3-043 is one of the 2 unsafe failures, wrong answers given with confidence: a flat rate the traveller says they used, read as unused (E3-043, answered instead of escalated), and a direct arrival read into a question that said the flight connected (2 L allowed, E3-022). A third, E3-019, looked unsafe to the rules but is a gold error: both reviewers confirmed the agent's amount is right (`docs/TAXONOMY.md`, hand check). The one missed refusal is E3-069 (§6.2).

## 6.4 Known limits

- **PII reaches the model endpoint.** Masking covers logs and traces; the question itself is sent to the shared model as typed, since intake reads it. Masking the question before intake (no personal detail is needed to assess duty) is a small change for a deployment.
- **The guard is English patterns.** It catches the phrasings in the dev, red-team and paraphrase sets and every eval-v3 injection and evasion item, but not every wording (E3-069). The intake model's `request_kind` is the second line; there is no third.
- **Arrival state from an airport.** "Landing at JFK" is not read as New York, so the state note is missed (E66, E3-077, in v1 and v2). The state flag is reported but not scored.
- **Five states.** The SPEC covers the five busiest arrival states (the app adds ten more, each with its official source); other states get no flag.
- **Not yet done:** the red-team against the live app (mentor plan, Day 10) has not been run and logged.
