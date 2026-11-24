# Mentor check-in 1: the Week-1 gate

**Project:** US Customs Assistant ("DeclareRight"): alcohol and tobacco, v1. Track B on the upgrad course endpoints.
**Date:** 2026-11-17.
**Status:** plan steps 1–8 done. The Track B gate is met: the spec is approved, the evaluation set is frozen, and the baseline numbers are recorded, **all before any agent code**.

This note collects the gate evidence and the observations so far. Every number links to the file it comes from.

---

## 1. Gate evidence

| Gate item | Evidence | Where |
|---|---|---|
| Spec: what it does, what it refuses, what correct means | SPEC **v1.1, approved** 17 Nov | `docs/SPEC.md` |
| Rules researched against the official text | R1–R12 signed off with clause-level citations; decisions A–G recorded | `docs/regulatory-checks.md`, `pack/rules/` |
| Evaluation set, gold written before agent code | **`eval-v1` frozen**: 80 scenarios (your categories and counts) + 6 correction scenarios; 20 dev scenarios kept separate for tuning | `pack/eval/`, `pack/eval/freeze.lock.yaml`, `docs/results/eval-freeze.md` |
| Baseline with at least 3 prompting strategies | 4 strategies + constrained-decoding comparison on all 80 | `docs/results/week1_strategies.csv`, `week1_failures.csv`, `week1-baselines.md` |
| How the small model breaks | Five measured findings (below) | `docs/COMPENSATIONS.md` #3–7 |

---

## 2. What changed from your proposal, and why

| Your proposal | What we did | Why |
|---|---|---|
| LangGraph, planner → executor → critic | LangGraph `StateGraph`. The **LLM planner** proposes the steps; code validates the plan; a **code executor** runs the calculators; writer and verifier follow. The verifier can send work back to the planner (plan problems) or the writer (wording). | The calculators read their inputs from state, so a model executor would only add calls on a one-request-at-a-time endpoint. To keep this honest, a fourth mode, **`tool_calling`** (the model calls the tools itself), is measured against it. |
| Official runs: 3× agent, 1× router, 1× single_rag | Same, **plus 1× `tool_calling`** and a **6-scenario corrections suite** (your "actually it was 3 days") | Evidence for the executor choice, and a scored test of corrections, which your 80 don't cover |
| Day-trip-to-Tijuana example: $200, whole bottle dutiable | **$800 exemption, nothing owed** (unless the exemption was used in the last 30 days) | 19 CFR 148.35(a): arrivals directly from **Mexico** get the $800 exemption whatever the time away. The HTS 9804.00.65 heading and CBP's "What to Expect" page agree. Your all-or-nothing correction is right, but only for a repeat trip within 30 days, or a short trip from anywhere other than Mexico. The $200 eval items use Canada day trips and repeat trips. |
| Third-country Cuban goods: verify the provision | **31 CFR 515.585(d)** allows Cuban-origin goods bought in a third country as baggage, but "does not apply to … Cuban-origin alcohol or tobacco". With 515.204(a) and OFAC FAQ 720. | Found in the frozen corpus |
| Extra tobacco: taxed or seized? | **Seized, not taxed**: CBP's current guidance says excess tobacco is "subject to detention, seizure, penalties, abandonment, and destruction" (with 27 CFR 41.190). Kept as a data-driven rule. | Your doubt resolved in favour of the business case |
| US export-labelled cigarettes "can come back" | **Reversed**: 26 USC 5761(c)–(d) allow only the duty-free personal quantity; the excess can be given up at entry without penalty, otherwise it is forfeited (penalty ≥ $1,000) | Statute |
| Flat 3% on the first $1,000 | 3%; **free for products of trade-agreement partners** (USMCA, CAFTA-DR, Peru, Colombia, Chile, Korea…); **4% for Column 2** origins (Russia, Belarus, North Korea, Cuba) | HTSUS 9816.00.20 Special and Column 2 rates, General Notes 3(b)–(c) and 11(a) |
| Which excise rate | The general rates: the reduced craft-beverage (CBMA) rates and credits only apply to producers and to importers a foreign producer has assigned them to | TTB rate tables; 26 USC 5001, 5041, 5051 |
| Added by us | R11: in a mixed basket the allowance goes to the **highest duty + tax first** (19 CFR 148.33(b)); R12: a brand does not prove origin (Cohiba, Havana Club are made in and outside Cuba) | Needed for mixed baskets; your "6 Cohibas" example |
| Corpus ≈ 500–840 docs incl. CBP Info Center | **1,261 documents** from 41 public sources. The CBP Info Center is rendered by JavaScript and can't be downloaded; 19 static cbp.gov pages replace it. The Illinois rule (ilga.gov) was unreachable; the ILCC import form is used. | `pack/corpus/editions.md`, `docs/results/corpus-counts.md` |

### Decisions taken by the team (17 Nov)

| # | Decision |
|---|---|
| A | The 2-litre rule uses **CBP's country list** (wider than HTS General Note 7(a)); four scenarios depend on it |
| B | Tobacco under 21: **no exemption** (CBP guidance; the regulation is silent) |
| C | Trade-agreement partner products: **duty free**, with "if it qualifies as originating; the officer decides" |
| D | More than **12 litres** per traveller: flag "contact your port of entry" and escalate (a UX threshold, not law) |
| E | Ambiguous brand, origin unknown after one question: **treat as possibly Cuban** (no allowance, declare) |
| F | Family groups: answered **per traveller**, with a scope note |
| G | Russian-origin alcohol: **scope note only** |

---

## 3. The evaluation set

- **80 frozen scenarios** in your categories and counts.
  - The business case's examples appear in corrected form.
  - The decisions above each have a test: the Dominican Republic 2 L case, under-21 tobacco, partner-origin duty, ambiguous brands, the 12 L flag, the 4% Column 2 rate (A11) and an unknown price (I03).
  - 11 of the 91 turns are clarifying turns, with scripted replies.
- **Gold built independently.** A separate agent with no access to any application code read only the SPEC, the rules and the scenarios, and computed the gold with its own script.
  - It produced a formula workbook (127 formula rows reproduce the gold) and an issues log, which the team decided.
- **Hand-check of 20.** Every figure was recomputed with a second, separate script; citations were checked against the corpus and outcomes against the regulation text. **20/20 OK.**
  - One finding fixed: the "highest-rate first" citation is required only when two or more alcohol lines compete. The fix changed 37 turns, each losing exactly one citation requirement; nothing else changed (diffed).
  - One limitation recorded: the thin Illinois evidence.
  - *Note:* the plan had a team member doing this hand-check; it was done by the AI coding session at the team's request, on top of the independent gold builder.
- **Calculators** (plan step 6, code only) match the **dev** gold exactly on all 18 dev scenarios they decide: outcome, amount, every figure, every note, every cited rule. The frozen gold is kept for the official runs.

---

## 4. Baselines: how the bare 8B model breaks

Qwen3-8B on the course endpoint, single prompts, **no tools, no calculators, no retrieval**, on the 80 frozen scenarios (91 turns). Scored in code (`backend/eval/score.py`).

| Strategy | Turn accuracy | Amount right | Gold citations met | Invented citations | Tokens / turn | Seconds / turn |
|---|---|---|---|---|---|---|
| Closed-book | 2.2% | 11.8% | 45.7% | 5.3% | 583 | 3.1 |
| **Few-shot JSON** (strict schema) | **13.2%** | 13.2% | **74.0%** | 4.8% | 1,012 | 2.9 |
| Chain-of-thought, 3-sample vote | 3.3% | 22.1% | 41.6% | 21.1% | 2,441 | 19.8 |
| Decomposition (facts → working → answer) | 1.1% | 22.1% | 53.4% | 16.0% | 2,125 | 9.9 |

*Invented citations* = cited sections that aren't in the corpus snapshot (fabricated, or real but outside it).

**Observations**

1. **The money is almost never right.** At best 22% of answered turns, even with step-by-step reasoning. Even the best strategy (few-shot) scores **0%** on every money category: excess alcohol, the 2-litre rule, the $200 rule, mixed baskets, under 21, states. For the cognac question (gold $3.23) the four strategies answered $108, $13.50, $22 and $315. → All figures come from calculators; the model never types a number.
2. **Thinking harder invents more citations.** Chain-of-thought cites sections not in the corpus 21% of the time; few-shot 5%. Few-shot also meets the most gold citations (74%). → Citations only from clauses retrieved in the run, enforced by the verifier.
3. **Clarifying is unreliable.** Every strategy missed 10–11 of the 11 turns that needed a clarifying question, and closed-book asked 8 unnecessary ones. → The clarify decision is made in code from the answer-changing-facts table.
4. **Scope and injection fail without code.** Out-of-scope cases recognised: 0–1 of 5. Direct prompt injection ("ignore your rules…") refused: at most 1 of 2. Evasion requests were refused better: few-shot 4/4, decomposition 1/4. → Guard and scope checks run in code before and after the model.
5. **Few-shot is the best prompting strategy, and still far from usable** (13% of turns). Chain-of-thought costs 4× the tokens and 7× the latency of few-shot for less accuracy. → Few-shot (dev examples only) for the intake and writer; no chain-of-thought on the default path.
6. **Constrained decoding fixes the format, not the content.** Without a schema, the intake produced valid JSON on the first try **55%** of the time; with strict `json_schema`, **100%**. Retries with the error fed back recovered every prompted case. Extraction accuracy was the same either way (about 86%). → Strict schema on every model output, with retries as the safety net.

---

## 5. Endpoint usage so far (all with the team's explicit OK; `docs/quota-log.md`)

| Run | Endpoint | Requests | Tokens |
|---|---|---|---|
| Index build (3 chunk sets, 3,528 distinct texts, cached so never re-sent) | embeddings | 221 | ~738k |
| Baselines (smoke 20 + stopped run 15 + resumed run 889, incl. 36 JSON retries) | chat | 924 | ~665k |

---

## 6. Points for your review

1. **The executor is code, the planner is the LLM.** Does this satisfy "explicit planner → executor → critic loop" for item IV, given the `tool_calling` and `router` ablations as evidence?
2. **The Mexico finding (19 CFR 148.35(a)).** It changes your Tijuana correction; please confirm.
3. **Decision A** uses CBP's 2-litre country list rather than the narrower HTS General Note 7(a). Is that acceptable, given it is recorded as a known difference?
4. **Hand-check.** Done by the AI session with independent recomputation, not by a second team member. Is that acceptable for the gold protocol?
5. **Document unit.** One CFR paragraph, US Code subsection, OFAC FAQ, HTS subheading or note subdivision, or web-page heading block per document (1,261 total). Does this count towards the 500–2,000 rule?

---

## 7. Next

1. **Retrieval experiment** (needs an endpoint OK): chunking (paragraph-with-header vs whole section vs 200-token window), bge query prefix on/off, reranker none vs Qwen3-8B listwise vs a local cross-encoder, and the topic filter. Recall@1/3/5/10, plus three written decisions.
2. **Agent graph** (offline first): guard, intake, clarify, planner + validator, executor, writer, verifier; corrections; the four modes.
3. Dev-set tuning, then the API, UI and Docker, the red-team, and the official runs.
