# Implementation plan: US Customs Assistant (alcohol and tobacco, v1)

A Track B capstone built end to end on the upgrad course endpoints. Inputs:

- Business case: `dumps/practice-capstone-project/final-capstone-project/US Customs Assistant — Business Case.pdf` (15 Nov 2026)
- Mentor's proposal and corrections: `dumps/practice-capstone-project/final-capstone-project/mentor-notes/01_US_Customs_Assistant.docx` ("DeclareRight", approved with required changes)
- Track B template: `dumps/practice-capstone-project/final-capstone-project/Track-Selection.pdf` (items I–VI, deliverables, guardrails, grading)
- Endpoint guides: `Track_B_Inference_API_Learner_Guide.docx.pdf` (chat) and `embedding-endpoint/Embedding_API_Quickstart.md` (embeddings), same folder
- Lessons and code from `../procurement-and-vendor-review/` (the reference app), especially `docs/small-model-log.md`

Status: **draft for review**, revised after the critical review of 17 Nov. Nothing here has called an upgrad endpoint.

---

## 1. Decisions

| # | Decision | Source |
|---|---|---|
| D1 | Full Track B deliverable: items I–VI and all five deliverables (§15). | You, 17 Nov |
| D2 | **LangGraph `StateGraph`** with explicit nodes and the SQLite checkpointer. No Deep Agents. The validated plan is run by a code executor by default; an LLM tool-calling executor is kept as a measured mode (D19). No second framework. | You, 17 Nov (switched from Deep Agents) |
| D3 | **Standalone copy** of the reference core modules. No dependency on `procurement-and-vendor-review`. | You |
| D4 | **upgrad only.** Chat: Qwen3-8B at `:1033` (CA `vm05-ca.crt`). Embeddings: bge-small-en-v1.5 at `:1035` (CA `vm02-ca.crt`, 384 dims). No SiliconFlow code, no `PROVIDER` switch, no LLM judge from another provider. | You |
| D5 | **Separate Langfuse project** with its own keys in this app's `.env`, and its own dashboards. | You |
| D6 | Reranker: **measure none vs Qwen3-8B listwise (upgrad chat) vs local `ms-marco-MiniLM-L-6-v2`**, ship the winner. The local model runs in the container (pinned weights baked in at build); it is not an API. *Measured 18 Nov: **none** ships; the cross-encoder lost on every metric, listwise is switchable (`RERANKER=listwise`). The cross-encoder's dependency (fastembed) stays in the `experiment` group, out of the image.* | You |
| D7 | Regulatory checks: **I research the official texts and write each finding with its citation; you sign off each one** before eval items are written. | You |
| D8 | Eval scenarios: **I draft 80 frozen + 20 dev + ~6 corrections scenarios.** Gold answers: see D18. | You |
| D9 | Front end: **Next.js + Tailwind**, own container, clean minimal design in the spirit of Anthropic's site (§9). | You |
| D10 | Folder: `final-capstone-project/demo/swateek/us-customs-assistant/`. | You |
| D11 | State-rule table: **CA, NY, FL, TX, IL** (flag + source only). | You |
| D12 | `whatif_optimise` is a **stretch** item; its 4 items are otherwise reported as a known gap. | You |
| D13 | The report lives in this folder (`docs/report/`). Which project is submitted is decided separately. | You |
| D14 | Documents are handled **exactly as in the reference** (manifest, lock, exclusions, splitting, editions, synthetic, gitignored raw data, never executed, PII scrub, fail on excluded sources or > 2,000 documents). | Your brief |
| D15 | Packaging: Docker + docker-compose. | Your brief |
| D16 | **No upgrad call without your explicit OK for that step.** Every such step is marked **STOP (upgrad OK)** with an estimate. | Standing rule |
| D17 | **Corrections suite**: about 6 scripted multi-turn correction scenarios, frozen with `eval-v1`, scored and reported separately. The mentor's 80 stay as designed. | You, 17 Nov |
| D18 | **Gold by a fresh subagent** that sees only the signed-off rule table and the scenarios, never the code. You hand-check 20; the subagent's gold is the second, independent computation the mentor's two-person rule asks for. | You, 17 Nov |
| D19 | **Fourth mode `tool_calling`**: the model executes the validated plan through native tool calls. Run once on the 80. Evidence for the code executor and for the template's "tool-call error" bucket. | You, 17 Nov |
| D20 | **Citations: retrieve first; on a miss, fetch the clause by its id** and log `retrieval_miss_recovered`. Answers stay correct; misses are still counted. | You, 17 Nov |
| D21 | **Demo deployment: Docker on your laptop** (needs network access to `103.42.50.41` during the demo). | You, 17 Nov |
| D22 | **You do all the work** (with Claude). The report's role table uses the labels Person A–F (§16). No programme-office questions are sent. | You, 17 Nov |
| D23 | **GitHub Actions CI** for this app: lint, offline tests, web build, image build. No secrets, no upgrad calls (§13.1). | You, 17 Nov |

---

## 2. Coverage

### 2.1 Mentor comments

| Mentor comment | How the plan handles it | Section |
|---|---|---|
| Code router is a workflow, not a planner (item IV) | LLM planner returns the plan as strict JSON from a fixed step vocabulary; code validates it against an allowed-step graph; the code router is the fallback and an ablation. | §4.2, §4.3 |
| Corrections across turns | Profile and basket in graph state; a correction becomes a field delta; only dependent steps are replanned; editable "facts relied on" in the UI; scored corrections suite (D17). | §4.5, §9, §10.1 |
| ≥3 tools; error handling for malformed JSON, loops, token caps | 8 tools + 1 stretch; JSON retries ×2 then escalate; repeated steps rejected; step and token caps; 429 back-off through one gate; tool-argument guard in `tool_calling` mode. | §4.4, §4.6 |
| Tool error goes back to the planner | Plan-level failures (tool error, missing step) go back to the planner once; wording failures go back to the writer once. | §4.7 |
| RAG over 500–2,000 documents, hybrid + reranker, recall@k | ~500–650 regulatory documents with hard negatives; BM25 + bge-small + RRF; reranker study; recall@1/3/5/10; three written decisions. | §5, §6 |
| Prompting baseline with 3+ strategies | closed_book, fewshot_json, cot_sc, decompose; dollar items without calculators; constrained decoding with vs without. Gate before agent code. | §10.3 |
| Tracing, taxonomy, cost, latency | Langfuse project, scores per answer, custom dashboard; taxonomy rolled up to the template's four buckets; tokens + labelled price assumption. | §8, §10 |
| Injection, PII, refusals, HITL | Guard before any model call; planted-line fixtures; PII masking; session time-to-live; evasion refusals; escalation note. | §7 |
| Regulatory facts (0.3, items 1–8) | R1–R8 researched, cited, signed off; R9–R12 added. Examples 3 and 4 corrected. | §3 |
| Mixed baskets, what-if, state lookup | Mixed baskets must-have; brand → origin handling (the mentor's "6 Cohibas"); state lookup tool; what-if stretch. | §3, §4.4 |
| Calls under ~3k input tokens; 8,192 cap | Small node prompts; budget checked before each call. | §4.6 |
| Store raw source, text, URL, date, hash; freeze | Manifest/lock pattern extended for HTML/XML. | §5 |
| 80 frozen + 20 dev; independent gold; 20 hand-checked | D8, D18; freeze lock + test. | §10.1, §10.2 |
| Official runs: 3× agent, 1× router, 1× single_rag | Plus 1× `tool_calling` (D19) and the corrections suite. | §10.4 |
| Constrained decoding "with vs without" (B1.3) | Measured on intake and the fewshot_json baseline. | §10.3 |
| An 8B judge is unreliable; report agreement on 30+ items (B1.3) | Scoring is code; the advisory LLM reviewer's agreement with human labels is reported on 30 items. | §10.6 |
| Metadata filter first; metadata header in every chunk | Topic filter set by code; header inside each chunk. | §5.2, §6 |
| Develop locally on the same family (B1.1) | Not adopted: upgrad only (D4). Development uses scripted fakes offline; live runs need your OK. | §4.6 |
| Compare embeddings with bge-small locally (B1.2) | Optional: local bge-small vectors vs the endpoint's, which would also confirm the endpoint's model (it publishes no model name). | §6 |
| Docker + GitHub Actions CI (B1.3); green CI (B2) | Workflow for lint, offline tests, web build, image build. | §13.1 |
| Instructor library | Not needed: the endpoint supports strict `json_schema`; Pydantic validates. | §4.6 |
| Quota log from Day 1 | `docs/quota-log.md`, one line per upgrad run. | §8 |
| Mentor check-in on gate evidence | A stop point after the gate. | §14 |
| Must-have vs stretch; slip rules | §14.2. | §14 |
| Each owner writes their report section when their part freezes | Report sections are steps inside §14, not one step at the end. | §14 |
| Role split | §16. | §16 |
| COMPENSATIONS.md from Day 1 | §11. | §11 |

### 2.2 Track B template and endpoint guides

| Requirement | Where |
|---|---|
| I. Spec of what it does, **what it must refuse**, what a correct answer looks like; 60–100 queries with gold before agent code | SPEC (§14 step 4) includes the refusal policy and the answer-changing facts table; eval §10 |
| II. Single-prompt baseline, ≥3 strategies, document how the model breaks | §10.3, `week1_failures.csv`, `COMPENSATIONS.md` |
| III. 500–2,000 docs, chunking experiments, hybrid, reranker, citation-grounded answers, recall@k separate from end-to-end | §5, §6; recall@k reported next to end-to-end accuracy |
| IV. ≥3 tools, explicit planner → executor → critic **loop**, persistent state, error handling (tool failures, malformed JSON, infinite loops, token caps) | §4 (the verifier can send work back to the planner, closing the loop) |
| V. End-to-end accuracy, task completion rate, average tool calls, cost and latency per query, taxonomy (retrieval miss, reasoning error, tool-call error, hallucination), tracing | §8, §10.4, §10.5 |
| VI. React front end, containerised, rate limiting, caching; injection tests against the corpus, PII, refusals, HITL boundary | §7, §9, §13 |
| Guardrails: corpus ≤ 2,000 docs; ≤ 10 steps per query; Week-1 gate; "What did we do to compensate for a small model?" | §5, §4.6, §14, §11 |
| Deliverables: repo, trace dashboard, evaluation report with taxonomy, 12-page report, 10-minute live demo | §15 |
| Chat limits: 1 active request per key (group-wide), 60 req/min, 8,192 tokens in + out, output 512 default / 1,024 max | §4.6 |
| Errors: retry 429/503 at 2, 4, 8 s then stop; 400 → check max_tokens/context; keep TLS verification on | §4.6 |
| Report failures with group id, URL, error code, time; never the key | §8 |
| Embeddings: ≤16 texts per request, < 512 tokens per text, same model for index and query, retry on capacity errors | §6 |

---

## 3. Regulatory checks (before SPEC is approved)

I read the official text from the downloaded corpus and write the finding, exact citation and as-of date into `docs/regulatory-checks.md` and the rule table; you sign off each row. Until a row is signed off, its eval items are not written.

| # | Claim | What to establish | Status |
|---|---|---|---|
| R1 | $200 exemption: 150 ml / 50 cigarettes / 10 cigars | The **all-or-nothing** rule of 19 CFR 148.51(b). Correct example 4 (whole 750 ml dutiable; excise ≈ 0.198 gal × 0.80 × $13.50 ≈ $2.14, plus duty). | Mentor: confirmed wrong in business case |
| R2 | 1 litre of alcohol | Add the **CBI 2-litre** rule of 19 CFR 148.33(d); pin the beneficiary-country list as data. | Mentor: confirmed incomplete |
| R3 | Under 21: no alcohol in the exemption | Keep; clarify trigger. | Mentor: confirmed |
| R4 | Cuban alcohol and tobacco banned "wherever bought" | Cite the right provision for **third-country purchases** (31 CFR 515.204, the 2020 removal of the earlier authorisation), FAQ 719 for goods acquired in Cuba. | Mentor: verify |
| R5 | "Extra tobacco is not taxed, it is seized" | Whether excess tobacco is **taxed or seized**, and when. Both paths as data-driven rules. Decides whether the duty step runs for tobacco. | Mentor: verify (central) |
| R6 | "US cigarettes exported can come back" | 26 USC 5754 / 5761(d) limits on re-importing US export-labelled tobacco. Probably the reverse of the business case. | Mentor: verify |
| R7 | Flat 3% duty (HTSUS 9816.00.20) | First $1,000 over the exemption; origin exceptions (USMCA, insular possessions); what v1 does above $1,000 (likely escalate). | Mentor: verify |
| R8 | TTB rates | Full rate table with as-of date (wine bands, sparkling, beer, spirits, small and large cigars, cigarettes); **which rate applies to a traveller's import** (full vs reduced craft rates). | Mentor: consistent; verify extra rows |
| R9 | 30-day and 48-hour rules | Exact conditions for $800 vs $200; land-border differences. | Added |
| R10 | Personal use vs commercial quantity | Published threshold or not; if not, flag and escalate. | Added |
| R11 | Allocation of the exemption | In a mixed alcohol basket, **which litre is exempt** (wine vs spirits changes excise a lot), and how value is allocated for the 3% duty. | Added (review) |
| R12 | Origin from brand names | Brands made both in Cuba and elsewhere (e.g. Cohiba, Havana Club): origin can't be inferred from the brand, so it is a clarify trigger; sanctions answers stay conservative. | Added (review; the mentor's "6 Cohibas" example) |

**Answer-changing facts table (goes into SPEC, signed off with it).** For each fact: when it changes the answer, and what happens if it is still missing after the one clarifying exchange.

| Fact | Ask when | If still missing |
|---|---|---|
| Age (21+) | Any alcohol or tobacco in the basket | Escalate (no allowance can be given) |
| Trip length / exemption used in the last 30 days | Always for an allowance | Escalate |
| Origin of a line | A brand or place made in Cuba and elsewhere (R12); CBI claim (R2) | Treat as possibly Cuban: advise declaring, no allowance for that line |
| Value of a dutiable line | Only when the line is over the allowance | Show excise only; duty "depends on value", stated |
| ABV | Never asked by default | Assume a stated default by product class (proposed: wine ≤16%, spirits 40%), shown in "facts relied on" |
| Arrival state | Alcohol in the basket | No state flag; generic note that states may set limits |
| US resident | Never asked; only acted on when the traveller says otherwise | Out of scope (non-resident) |

Several missing facts are asked in **one** short question (as in the business case's example 1).

**Done and signed off (17 Nov):** findings, citations and decisions A–G are in `docs/regulatory-checks.md`; the tables (rules, rates, units, countries, brands, states, facts) are in `pack/rules/`. Two corrections beyond the mentor's: arrivals directly from **Mexico** get the $800 exemption regardless of time away (19 CFR 148.35(a)), so the Tijuana example is not a $200 case; and 9816.00.20 is duty-free for trade-agreement partners' products (Decision C). The $200 all-or-nothing eval items therefore use non-Mexico short trips and repeat trips within 30 days.

---

## 4. Agent design (LangGraph)

### 4.1 Flow

One `StateGraph`; every node is a span in the trace. Typical question: 4 model calls (intake, planner, writer, advisory review).

```
Traveller question
  ▼ guard (code, no model call)       injection patterns, evasion ("how do I hide…") → refuse → END
  ▼ intake (1 LLM call, strict JSON)  profile {age, trip_hours, exemption_used_30d, countries[], arrival_state,
  │                                            us_resident, from_insular_possession, crew, shipped}
  │                                   basket [{item, qty, unit, abv, value_usd, origin, brand, bought_where, category}]
  ▼ normalise (code)                  units ("a fifth"→750 ml, "carton"→200, "box of 25"→25), ABV→proof,
  │                                   brand→origin table (ambiguous brands flagged, R12)
  ▼ scope (code)                      out-of-scope profile → scope note → END; out-of-scope lines (vapes, food…)
  │                                   noted ("shares the $800 exemption, not assessed"); in-scope lines continue
  ▼ clarify (code)                    answer-changing facts missing (§3 table) → ONE short question → END (turn)
  ▼ planner (1 LLM call, strict JSON) ordered steps from a fixed vocabulary
  ▼ validate_plan (code)              allowed-step graph + inputs + no repeats + ≤10 steps
  │                                   invalid → planner once with the error → else router's plan
  ▼ executor (code; or LLM in tool_calling mode)
  │                                   check_restrictions → determine_exemption → compute_allowance
  │                                   → compute_duty_excise → lookup_state_rule → citations (D20)
  ▼ writer (1 LLM call, strict JSON)  bottom line + working, figures and sources by handle only
  ▼ verifier (code; + 1 advisory LLM call)
  │   plan-level failure (line not computed, step error, missing lookup) → planner once
  │   wording failure (unknown handle, typed number, bottom line ≠ tool outcome) → writer once
  │   still failing → escalate
  ▼ answered | clarify | refused | out_of_scope | escalated
```

The business case's five agents map as: **intake**, **duty** and **restrictions** (tool groups run by the executor), **writer**, **verifier**; the mentor's **planner** is added. By default the executor is code: the plan is already validated and the calculators read their inputs from state, so an executor model would only re-call the steps in the order given, at 1–3 s per call on a one-request-at-a-time endpoint (small-model log #5, #19, #20, #38). `tool_calling` mode measures that choice (D19).

Carried over from the reference: SQLite checkpointer, client and gate, budget logic (a wrapper around each node's LLM call), deterministic critic checks, Langfuse callback.

### 4.2 Planner and plan validation (item IV)

- The planner sees the normalised profile and basket and returns `{steps: [{step, lines, reason}]}` in strict JSON. The schema enforces the vocabulary: `check_restrictions, determine_exemption, compute_allowance, compute_duty_excise, lookup_state_rule, search_regulations, escalate_to_human` (+ `whatif_optimise`).
- `validate_plan`: `check_restrictions` first; `determine_exemption` → `compute_allowance` → `compute_duty_excise`; inputs exist in state; `lookup_state_rule` only with alcohol and a known state; no repeated step; ≤10 steps. A prohibited line (Cuba, under-21 alcohol) gets no downstream calculation.
- Invalid plan: error back once; then the **code router's** plan, tagged `plan_fallback`.
- The planner can skip `compute_duty_excise` (tobacco-only, if R5 says seizure) or request the what-if loop. On a correction it plans only the stale steps (§4.5).
- LangGraph `recursion_limit` backs up the caps.

### 4.3 Modes (the ablations)

`AGENT_MODE` (env, and per request for evals):

| Mode | What runs | Answers |
|---|---|---|
| `planner` (default) | Everything in §4.1 | Does an LLM planner help? |
| `router` | Planner node replaced by the deterministic router | Baseline for the planner |
| `tool_calling` | Planner + validator as above; the executor is an LLM that calls the tools natively (`tools`, `tool_choice`), with Pydantic argument validation, one retry per bad call, repeated-call block (`ToolArgGuard`) | Code executor vs model executor; fills the "tool-call error" bucket |
| `single_rag` | Guard → hybrid retrieval top-5 → one answer call; no tools | Agent vs plain RAG |

### 4.4 Tools

Reference contract: Pydantic input, dicts out, failures as `{"error", "retryable"}`, never raise. **Calculators read the profile and basket from graph state**; no model retypes quantities or values (except in `tool_calling` mode, where that is what is measured).

| Tool | Type | Purpose |
|---|---|---|
| `normalise_units` | code | Units, ABV → proof, brand → origin (runs in the pipeline; also exposed for tests) |
| `check_restrictions` | code (rule table) | Cuban origin (R4, R12), under-21 (R3), commercial quantity (R10), US export-labelled tobacco (R6) |
| `determine_exemption` | code | $800 vs $200 (R9), CBI 2 L (R2), insular-possession scope-out |
| `compute_allowance` | code | Exempt vs excess per line; allocation (R11); $200 all-or-nothing (R1) |
| `compute_duty_excise` | code (rate table, as-of date) | 3% flat duty (R7); TTB excise by class (R8) |
| `lookup_state_rule` | code (5-state table) | Flag + source for CA, NY, FL, TX, IL |
| `search_regulations` | hybrid RAG | Query built by code (user's question + the rules used); topic filter from the step; no model-written queries or filters (small-model log #27, #30) |
| `escalate_to_human` | code | Hand-off note with the facts relied on |
| `whatif_optimise` | code (stretch) | Loops the calculators |

**Citations (D20).** Each calculator result carries `rule_refs`; each rule maps to a clause id (`doc_id:section`), independent of the chunker. The executor retrieves; for any rule whose clause is not in the results, it fetches the clause by id and logs `retrieval_miss_recovered`. The writer cites only handles from this set.

### 4.5 State and corrections

- SQLite checkpointer keyed by thread id; state: `profile`, `basket`, `plan`, `results`, `as_of`. Sessions expire after a set time and are purged (§7).
- A clarify reply or correction is parsed by intake (which sees the current profile) into a **field delta**. A dependency map marks stale results (`age → restrictions, allowance`; `trip_hours / exemption_used_30d → exemption → allowance → duty`; `origin → restrictions, CBI`; `arrival_state → state rule`; a basket line → that line's chain); the planner replans only those.
- At most one clarifying exchange per question; the follow-up rate is tracked.

### 4.6 Reliability and budgets

- **One global gate.** The API runs as a single worker; every chat and embedding request goes through the copied `GatedTransport` (one active request), plus a client-side limiter under 60 requests per minute. 429/503 retried at 2, 4, 8 s, then stop. Embedding batches retried on capacity errors. The UI shows "queued" while waiting.
- `max_tokens` always explicit (≤1,024); thinking off; token estimator calibrated (+7 per message, +85 with tools); target under ~3k input tokens per call; 8K window guard.
- Strict `json_schema` for intake, planner, writer, verifier; Pydantic validation; malformed JSON → 2 retries with the error fed back → escalate.
- **Steps (template: 10 per query)**: at most 10 model calls (listwise rerank calls count) and at most 10 tool calls per question, as in the reference. Token budget per question: the mentor's 12,000. Prompt sizes measured offline first; any cap change is logged in `COMPENSATIONS.md`.
- Offline development uses scripted fake models (as in the reference); no local model.

### 4.7 Writer and verifier

- **The model never types a number or a citation id.** The writer produces only the bottom line and the working, referring to figures (`[F1]`: dollars, litres, quantities, all from calculators) and sources (`[S1]`…) by handle. Code renders the figures and adds the facts relied on (from the profile), the sources with as-of date, the disclaimer and the "declare it" note.
- Verifier, deterministic (blocking): every handle exists in this run; no literal number outside a handle unless it equals a known figure; every claim sentence has a source handle; bottom line agrees with the tool outcomes (prohibited ⇒ "No"; owe ⇒ the total figure); no evasion advice (banned phrases).
- Routing: plan-level failures → planner once; wording failures → writer once; still failing → `escalated` with the hand-off note.
- Verifier, LLM (advisory, recorded in the trace): is each cited sentence supported by its clause? It does not block (small-model log #17); its agreement with human labels is measured (§10.6).

---

### 4.8 Build notes (18 Nov)

Decisions taken while building, within the plan; each is easy to reverse.
- **The plan-level half of the verifier runs right after the executor** (`executor.audit`), before the writer, so a broken plan never reaches wording. Routing is as planned: plan-level failure → planner once → escalate; wording failure → writer once → escalate.
- **Caps, flags and citations always run in code after the plan.** They are bookkeeping (notes, seizure risk, Cuba refs, state flag) and the D20 citation step, not choices. So the planner's real choices are which calculators to run (e.g. skipping duty for tobacco only) and on which lines.
- **`escalate_to_human` is not in the planner's vocabulary.** Escalation is decided by the calculators (caps), the audit, the verifier, missing facts and the budget; the tool builds the hand-off note.
- **Corrections reuse the last plan when it is still valid** for the corrected facts: no planner call, the calculators re-run, and the delta and stale steps are recorded. The planner is called (with the stale steps) only when the old plan no longer fits, e.g. a new alcohol line into a flagged state.
- **Numbers outside handles:** the verifier also accepts the traveller's own facts ("your 3 bottles at $22 each") and signed-off rule constants (48 hours, 21, $800), besides figure values. Any other typed number, or any typed regulation number, fails.
- **Budgets are per turn.** A clarify exchange is two turns (the first uses only the intake).
- **Search:** one query per rule the answer relies on, embedded in one request per question. Only passages that hold a rule's own clause ids reach the writer, so planted lines elsewhere in the corpus never do.
- **`tool_calling` mode:** the model types the facts into the tool arguments, and those typed facts drive the calculators. Differences from the intake's facts are counted (`transcription_diffs`). Bad arguments get one retry per tool; repeated identical calls are blocked.
- **Not built yet:** `whatif_optimise` (stretch). The 4 `whatif` eval items will fail until it exists.

## 5. Documents and corpus (same handling as the reference)

### 5.1 Files

```
pack/corpus/
  manifest.yaml        hand-edited: id, store, topic, title, url, source_page, format (html|xml|pdf|json),
                       edition, edition_date, index_scope, language
  manifest.lock.yaml   generated by `download --freeze`: sha256 (raw and normalised text), bytes, retrieved_at
  exclusions.yaml      URL patterns that must never be indexed (+ reasons)
  splitting.yaml       per-source split rules (CFR section/paragraph, FAQ item, article)
  editions.md          which edition/date of each source and why
  synthetic/           injection fixtures (planted lines in several documents), marked synthetic
data/raw/customs/      downloaded files (gitignored), never executed or imported
```

### 5.2 What changes from the reference

- The downloader checks each source's declared `format` instead of PDF only.
- eCFR from the **versioner API at a fixed date**; USITC/HTSUS and US Code from versioned release points where available, so hashes hold.
- For HTML pages with volatile markup (CBP, TTB, OFAC, state sites), the lock also stores the hash of the **normalised extracted text**, and verification uses it.
- Parsers: `ecfr_xml`, `html_article`, `faq_items`, `htsus`. A metadata header goes inside every chunk; each chunk lists the clause ids it covers.
- PII scrub at ingest (emails, phone numbers, US SSN).

### 5.3 Candidate sources (target ~500–650 documents; exact URLs pinned in `manifest.yaml`)

| Source | Unit | ≈ Count | Role |
|---|---|---|---|
| 19 CFR Part 148 | section / paragraph | 120–180 | core |
| HTSUS Ch. 98 Subchapter IV + general notes (CBI, USMCA) | heading / note | 30–50 | core |
| TTB rate tables + 27 CFR rate provisions | provision / row group | 40–60 | core, as-of date |
| 26 USC 5001, 5041, 5051, 5701, 5754, 5761 | subsection | 20–30 | core |
| 31 CFR Part 515 + OFAC Cuba FAQs | section / FAQ | 100–150 | core + hard negatives |
| CBP traveller guidance + CBP Info Center articles | article | 100–200 | core + hard negatives |
| State personal-import pages (CA, NY, FL, TX, IL) | page | 5–10 | flag only |
| Hard negatives: food, medication, currency, Form 6059B, vapes | article | 80–150 | precision and scope |

Snapshot frozen once counts are in; answers show the snapshot's as-of date. Downloading public government pages is not an upgrad call.

**Built (17 Nov):** 41 sources, **1,261 documents**, snapshot frozen in `manifest.lock.yaml`. Deviations from the table above, with reasons in `pack/corpus/editions.md`: the CBP Info Center is not fetchable (rendered in the browser), so 19 static cbp.gov pages replace it (73 documents); 27 CFR Parts 27 and 41 are indexed whole (they hold the import rate provisions); Illinois uses the ILCC import form because ilga.gov could not be reached. Counts per source: `docs/results/corpus-counts.md`.

---

## 6. Retrieval

- Copied from the reference: BM25 + dense (bge-small via the course endpoint: ≤16 texts per request, < 512 tokens per text, longer chunks embedded as 500-token windows; same model for index and query) + RRF (k=60), Qdrant, Redis cache.
- Experiments (`eval/retrieval.py` → `docs/results/retrieval_experiment.{md,json}`, recall@1/3/5/10):
  - Chunking: paragraph-with-header, whole section, 200-token window.
  - Embedding: bge query instruction prefix on vs off (a real choice with a single embedding model). Optional: local bge-small vectors vs the endpoint's, to confirm the endpoint's model, which it doesn't publish.
  - Reranker (D6): none, Qwen3-8B listwise, local MiniLM.
  - Topic filter on/off.
- **Choices are made on dev labels and reported on eval labels.** Labels are clause ids from the gold, so they don't depend on the chunker.
- Three written decisions (chunking, embedding, reranker) in `docs/results/retrieval-decisions.md`. Recall@k is reported next to end-to-end accuracy.
- **Done 18 Nov.** Also measured: the query form (question alone vs question + rule names) and recall within a 1,500-token passage budget (R@1.5k), because recall at a fixed k favours whole sections (5 sections ≈ 3,600 tokens). Shipped: `window200`, hybrid, prefix on, question + rule names, topic filter, **no reranker** (the cross-encoder was worse; listwise improved ordering but not R@1.5k, at +1 call and ~4k tokens per search). Dev R@1.5k 0.84 (frozen 0.77). Listwise ran on dev only (`COMPENSATIONS.md` #8).

---

## 7. Safety and responsible AI

- **Guard** (code, before any model call): injection patterns and evasion requests only. Scope is decided after intake (§4.1), so a mixed basket isn't refused for one out-of-scope item.
- Retrieved text is data: planted lines in several `synthetic/` documents must be ignored.
- Safety suite (`eval/safety.py`) beyond the 4 injection items in the eval: planted-line probes, user injections, PII in the question, evasion phrasings. Results in `docs/results/safety.md`.
- Every answer: estimate, as-of date, "the CBP officer's assessment is final", recommend declaring. Sanctions answers conservative (§3 table).
- PII: masked in traces and logs. Session state expires and is purged; nothing else is stored.
- **HITL boundary**: the system informs; it never fills in or submits a declaration, and never advises not declaring. Escalation produces a hand-off note.
- Red-team list (15+) against the live app, logged in `docs/results/red-team.md`.

---

## 8. Observability (Langfuse, separate project)

- Keys only in this app's `.env`.
- One turn = one trace `customs-agent`; session = thread id; tags: `customs`, `upgrad`, mode, and for evals `eval`, `eval-v1`, category, question id, run label. Baselines are traced too. PII mask as in the reference.
- Scores per answer: `verifier_passed`, `revisions`, `outcome`, `plan_fallback`, `retrieval_miss_recovered`, and for evals `correct`, `dollar_ok`, `citation_ok`.
- Custom dashboard: outcomes, verifier pass rate, plan-fallback rate, tool calls per tool, p50/p95 latency per node, tokens per call, clarify rate. Screenshots to `docs/demo/traces/`.
- **Cost**: upgrad publishes no price. Report tokens per query plus cost at a clearly labelled assumed price per million tokens; set the same price as a custom model in the Langfuse project.
- **Quota log** `docs/quota-log.md`: one line per upgrad run (date, who, what, requests, tokens).
- Endpoint failures are reported to the coordinator with group id, URL, error code and time, never the key.

---

## 9. Front end (Next.js)

- Next.js 15 + Tailwind 4 + TypeScript in `web/`, own container, API route proxy as in the reference.
- Look: warm off-white background, near-black ink, one muted clay accent, generous whitespace, single centred column, serif display headings with a clean sans body (open fonts self-hosted via `next/font`; no Anthropic fonts, logo or name). Light and dark themes.
- Screens: **Ask** (composer, four example questions as chips); **Clarify** (one short question with quick replies); **Answer card** (bottom line first; working table; **editable facts relied on** that trigger a replan; sources with as-of date; officer-decides note; status mark); progress and a "queued" state while waiting; final text only after the verifier.
- Rate limit (10 questions/min per conversation) and answer cache (off for official runs). A **demo cache** of the demo script's answers, used only if the endpoint is down during the live demo, clearly labelled as cached.

---

## 10. Evaluation

### 10.1 Sets (all frozen as `eval-v1` except dev)

- `queries.jsonl`: 80, the mentor's categories (alcohol_excess_800 12, alcohol_cbi_2L 4, exemption_200_all_or_nothing 8, tobacco_over_limit 7, cuban_origin 7, under_21 4, mixed_basket 10, whatif 4, clarify 8, state_flag 3, out_of_scope 5, refuse_evasion 4, injection_doc 2, injection_user 2).
- `corrections.jsonl`: ~6 multi-turn correction scenarios (D17), scored separately.
- `dev.jsonl`: 20, for all tuning and few-shots.
- `retrieval_labels.jsonl`: gold clause ids per question (dev and eval).
- **Scenario schema**: `id, category, turns[{user, expect: clarify|answer|refuse|scope}]` (scripted replies for clarify and correction turns), and gold: `outcome, bottom_line, figures{name: value}, citations[clause ids], profile, basket, clarify_fields`.

### 10.2 Gold and freeze

- Gold built by a **fresh subagent** given only the signed-off rule table, rate table and scenarios, never the code (D18), as a spreadsheet with formulas (`pack/eval/gold/gold.xlsx`, exported to CSV).
- You hand-check 20; disagreements settled against the regulation text.
- `freeze.lock.yaml` + `tests/test_eval_freeze.py`; gold changes need a version bump and a reason in `docs/results/eval-freeze.md`.

### 10.3 Baselines (the gate, before agent code)

- closed_book, fewshot_json (few-shots from dev), cot_sc (CoT in the prompt, thinking off, 3 sequential samples at temperature > 0, majority vote), decompose. Dollar items also run without calculators.
- **Constrained decoding with vs without**: fewshot_json and intake each run once with strict `json_schema` and once with prompted JSON; schema-valid rate and accuracy.
- Output: `docs/results/week1_strategies.csv`, `week1_failures.csv` (how the model breaks).

### 10.4 Scoring and official runs

- `eval/score.py`, code only: outcome and bottom line equal gold; each figure within $0.01; each claim cites a gold clause; clarify asked exactly when gold says, for the right fields; extraction accuracy per profile and basket field; refusals and scope notes. A multi-turn runner plays the scripted turns.
- Official runs, cache off, one request at a time: **3× `planner`, 1× `router`, 1× `tool_calling`, 1× `single_rag`**, and the corrections suite with each `planner` run.
- Metrics: accuracy per category, dollar accuracy, citation accuracy, extraction accuracy, clarify precision/recall, task completion rate, average tool calls, tokens and cost per query, p50/p95 latency, plan-fallback rate, retrieval-miss-recovered rate; recall@k alongside.
- Results: `docs/results/` (JSON + markdown per run) and the **evaluation report** `docs/eval-report.md`.

### 10.5 Failure taxonomy

Every wrong answer gets a fine label that rolls up into the template's four buckets; at least 15 hand-checked.

| Template bucket | Fine labels |
|---|---|
| Retrieval miss | retrieval_miss, retrieval_miss_recovered (counted, not wrong) |
| Reasoning error | extraction_error, unit_error, rule_selection_error, plan_invalid, clarify_miss, refusal_miss |
| Tool-call error | tool_arg_error, wrong_tool, repeated_call, tool_failure (mostly `tool_calling` mode) |
| Hallucination | invented_figure, invented_citation, unsupported_claim |

### 10.6 Advisory reviewer agreement

The advisory LLM reviewer's verdicts are compared with human labels on 30 answers (mentor B1.3). If agreement is poor, it is reported and the reviewer stays advisory or is removed.

---

## 11. Compensating for a small model (graded section)

`docs/COMPENSATIONS.md` from the first step: symptom, fix, before/after metric. Carried over from the reference: thinking off, token estimator calibration, opaque handles, query anchoring, no model-set filters, deterministic critic. New: numbers by handle; schema-constrained intake + unit and brand tables (extraction accuracy before/after); constrained decoding with vs without; policy-constrained planning with router fallback; code executor vs `tool_calling` (calls, latency, tool-call errors); replan-by-dependency; citation fallback by id.

---

## 12. Repository layout

```
us-customs-assistant/
  AGENTS.md  README.md  env.sample  docker-compose.yml  ruff.toml
  certs/                       vm05-ca.crt (chat), vm02-ca.crt (embeddings)
  pack/
    corpus/                    manifest, lock, exclusions, splitting, editions.md, synthetic/
    rules/                     rules.yaml, rates.yaml, units.yaml, brands.yaml, states.yaml,
                               countries.yaml (CBI, USMCA, insular), facts.yaml (answer-changing facts)
    prompts/                   intake, planner, executor (tool_calling), writer, reviewer, baselines
    refusals.yaml  refusal_patterns.yaml
    eval/                      queries.jsonl, corrections.jsonl, dev.jsonl, retrieval_labels.jsonl,
                               gold/, freeze.lock.yaml
  backend/
    pyproject.toml  uv.lock  Dockerfile
    src/customs/
      llm/                     client, GatedTransport, limiter, retry, budget, probe
      ingest/                  download, parsers, build_chunks, index, pii
      retrieval/               bm25, dense, embed, hybrid, rerank (listwise + cross-encoder)
      tools/                   calculators, restrictions, state rules, search, escalate, whatif
      agent/                   graph.py, state, nodes/ (guard, intake, normalise, scope, clarify, planner,
                               validate_plan, router, executor, tool_executor, writer, verifier), budget
      safety/                  guard, masking, session expiry
      observability/           tracing, scores
      api/                     FastAPI app
    eval/                      baseline.py, retrieval.py, e2e.py, multiturn.py, safety.py, score.py
    tests/                     unit tests per rule, graph offline tests with scripted fakes
  web/                         Next.js app
  docs/                        SPEC.md, implementation-plan.md, regulatory-checks.md, COMPENSATIONS.md,
                               quota-log.md, eval-report.md, results/, report/, demo/
  data/                        gitignored: raw/, chunks/
```

## 13. Docker (laptop, D21)

Services: `api` (FastAPI, single worker), `web` (Next.js), `qdrant`, `redis`, one-shot `ingest` profile (download → build_chunks → index). Ports 3500 (web), 3501 (api), 3502 (qdrant), beside the reference's 3400–3402. Certs mounted read-only; secrets only from `.env`; healthchecks; the SQLite checkpointer on a volume. If the local cross-encoder wins, its pinned weights are fetched at image build. `ingest` (index) and `api` call upgrad, so running them is **STOP (upgrad OK)**.

### 13.1 GitHub Actions CI (D23)

- File: `.github/workflows/us-customs-assistant.yml` at the **repository root** (GitHub reads workflows only from there). The root `.gitignore` ignores all dotfiles, so `!.github/` is added to its whitelist.
- Triggers: push and pull request, filtered to `final-capstone-project/demo/swateek/us-customs-assistant/**` and the workflow file.
- Jobs:
  - **backend**: `uv sync --frozen`; `ruff check` and `ruff format --check`; `pytest` (rule unit tests, graph tests with scripted fakes, eval-freeze test).
  - **web**: `pnpm install --frozen-lockfile`; `lint`; `build`.
  - **images**: `docker build` of the backend and web images (no push).
- No secrets in CI and nothing reaches `103.42.50.41`: tests use fakes, and a test fails if an upgrad URL is called. Actions pinned to versions.
- Pre-commit hooks (ruff, gitleaks, …) still run locally as for the rest of the repository.

---

## 14. Execution order and stop points

### 14.1 Steps

No calendar. "STOP (sign-off)" waits for your approval; "STOP (upgrad OK)" waits for an explicit yes before any request to `103.42.50.41`. Steps in the same group can run in parallel.

1. **Scaffold (offline).** Folder, `AGENTS.md`, `env.sample`, core modules copied and stripped, compose file, offline test harness with fakes, GitHub Actions workflow + `.gitignore` whitelist (§13.1), `COMPENSATIONS.md`, `quota-log.md`.
   **STOP (you):** new Langfuse project; its keys and the upgrad keys in `.env`.
2. **Corpus (offline, public sites).** Manifest, exclusions, parsers, `download --freeze`, `build_chunks`, counts per source, `editions.md`. *Done 17 Nov: 1,261 documents.*
3. **Regulatory checks R1–R12** → `docs/regulatory-checks.md`, rule, rate, brand and facts tables. *Done and signed off 17 Nov (decisions A–G).*
   **STOP (sign-off):** each row.
4. **SPEC.md**: scope, refusal policy, answer-changing facts, the corpus document unit, tool contracts, what counts as correct, metrics, HITL boundary.
   **STOP (sign-off):** SPEC APPROVED. *Approved 17 Nov (v1.0).*
5. In parallel:
   - **Eval scenarios** (80 + ~6 corrections + 20 dev) and retrieval labels; **gold** by the fresh subagent (D18).
     **STOP (sign-off):** your hand-check of 20 → freeze `eval-v1`. *Done 17 Nov: `eval-v1` frozen (80 + 6 corrections, 20 dev); gold built independently; the hand-check of 20 was done by the main session at the user's request (20/20 OK, finding F1 fixed). See `docs/results/eval-freeze.md`.*
   - **Calculators and tools (offline)**, unit tests per rule, the four corrected business-case examples. *Done 17 Nov: `customs/tools/` (tables, models, calc, facts, registry); 151 offline tests green; the calculators match the independent dev gold exactly on all 18 dev scenarios they decide. Note: in v1 the $1,000 flat-rate cap (R7) is never reached first, because any basket over $800 already escalates (R11).*
   - **UI mock-up** of the answer card (offline).
6. **Index.** **STOP (upgrad OK):** 3 chunking variants (~600 docs → ~1,500–2,500 chunks, ≈100–160 embedding requests per variant; ×2 for the prefix experiment). *Done 17 Nov with the user's OK: 3,528 distinct texts embedded in 221 requests (logged in `docs/quota-log.md`); three collections built (paragraph 1,413, section 920, window200 1,601 points, 384 dims); vectors cached in `data/embeddings/` so rebuilds, including Docker, need no upgrad calls.*
7. **Baselines (the gate).** **STOP (upgrad OK):** ≈850 chat calls (4 strategies, dollar items without calculators, constrained-decoding comparison). → `week1_strategies.csv`, `week1_failures.csv`. *Done 17 Nov with the user's OK: 924 chat calls in all (smoke 20 + stopped run 15 + resumed run 889, incl. 36 JSON retries), 64 min, no API errors. Turn accuracy 1–13% (few-shot best); amount right on 12–22% of answered turns; see `docs/results/week1-baselines.md` and `docs/COMPENSATIONS.md` #3–7.* Report §1–2 (problem, spec, eval design) and §3 (prompting) drafted.
   **STOP (mentor):** share the gate evidence. *Done 17 Nov: `docs/mentor-check-01.md`.*
8. **Retrieval experiment.** **STOP (upgrad OK):** listwise rerank ≈ 1 chat call per labelled question per variant (a few hundred). → recall@k, three decisions; report §4 (retrieval) drafted. *Done 18 Nov with the user's OK: 44 embedding requests (query vectors, cached) + 45 listwise chat calls on dev; 63 local variants + listwise; decisions in `docs/results/retrieval-decisions.md` (window200, hybrid, prefix on, question + rule names, topic filter, no reranker). Report §4 not drafted yet.*
9. **Agent graph (offline first).** All nodes, the four modes, state and corrections, error handling; offline tests; prompt-size measurement. *Done 18 Nov, offline (no upgrad call): `customs/agent/` (graph, guard, intake, planner + validator + router, code and tool-calling executors, writer, verifier, single_rag), `customs/retrieval/service.py` (search_regulations with fetch-by-id fallback), prompts in `pack/prompts/`, guard policy in `pack/policy/guard.yaml`. 27 new offline tests (195 in all). Prompt sizes: `docs/results/prompt-sizes.md` (worst answered question 5,519 of 12,000 tokens). Oracle run on dev (perfect scripted replies, sources by id): 23/23 turns correct. Build notes and deviations: §4.8.*
10. **Dev-set runs.** **STOP (upgrad OK):** 20 questions × ~4 calls per iteration (+ a few corrections). Tune on dev only → **prompt freeze**. *Done 18 Nov with the user's OK for each run: 5 dev runs (379 chat calls, 82 embedding requests, ~342k tokens in all), 14/23 → 19 → 16 → 22 → **23/23** turns; agent frozen as v1 (`pack/agent.lock.yaml`, 27 files) on dev-05. Changes per run and the freeze: `docs/results/dev-runs.md`; COMPENSATIONS #9–13. The corrections suite was not run (it is eval-v1, measured in step 13).*
11. **API, UI, Docker** (offline build); live smoke test **STOP (upgrad OK)**. *Built 18 Nov, offline:*
    - *API (`customs/api/`): streams progress as server-sent events; one question at a time, with `queued`; rate limits; a first-turn answer cache that seeds the thread state; sessions purged after 6 h; fact edits sent as a correction message.*
    - *The frozen agent is untouched. Progress comes from a tracer callback.*
    - *UI: Ask / Clarify (quick replies) / Answer card (figures, notes, editable facts, sources, as-of).*
    - *Docker: the ingest copies the host's verified snapshot (`download --from-snapshot`), because cbp.gov and abc.ca.gov refuse container downloads with HTTP 403. The corpus hash is identical; 0 upgrad calls.*
    - *Checked in the browser against a scripted offline model, including clarify and a fact edit replan (the queued state is covered by a test), and through Docker with a guard refusal.*
    - *218 tests.*
    - *Live smoke tests (with the user's OK): smoke 1 found 2 wrong answers (a Mexico day trip; a false sentence in the working). Fixed as agent freeze v2 and v3, each confirmed by a full dev run (23/23) and live: 46 smoke chat calls and 10 embedding requests in all. See `docs/results/dev-runs.md` and COMPENSATIONS #14–15.*
12. **Hardening, safety suite, red-team.** **STOP (upgrad OK)** for the live runs. → CI green → **code freeze** (`v1.0.0-rc`). Report §5 (agent design) and §6 (responsible AI) drafted. *Done 18 Nov with the user's OK for each live run:*
    - *Safety suite `eval/safety.py`: offline checks in CI; live probes `docs/results/safety.md`.*
    - *Red-team `eval/red_team.py`: 22 attacks, 22/22 (`docs/results/red-team.md`).*
    - *Hardening: no API docs exposed; questions with personal data are never cached, and the cache never outlives a session; web security headers and CSP; the API serves only planner and router.*
    - *Agent freeze v4: guard, banned patterns, scope-flag evidence, unsourced-sentence handling. Confirmed by dev-08 at 23/23.*
    - *CI-equivalent run green without the corpus (259 passed, 7 skipped).*
    - *Not done: the `v1.0.0-rc` tag (the user tags), and drafting report §5–6.*
13. **Official runs.** **STOP (upgrad OK):** ≈2,100 chat calls (3 × planner, router, tool_calling, single_rag, corrections), one request at a time, when no one else in group 031–045 is using the shared key.
14. **Metrics, taxonomy, reviewer agreement, Langfuse dashboard screenshots, evaluation report.** Report §7 (compensations).
15. **Stretch (if green):** what-if + its 4 items, then the other stretch items (§14.2).
16. **Report (12 pages) and demo**: demo script (four corrected example conversations, one refusal, one correction), demo cache, recorded backup video, rehearsal; final check for keys in Git and masked logs; tag `v1.0.0`.

### 14.2 Must-have vs stretch, and slip rules

| Must-have | Stretch (drop first) |
|---|---|
| SPEC, frozen eval + corrections suite, 4-strategy baseline | `whatif_optimise` and its 4 items |
| Corpus ≥ 500, hybrid + reranker, recall@k, citations | State table beyond 5 states |
| Planner + validator + executor + verifier, 4 modes, state and corrections, error handling | Extra router runs (1 is enough) |
| Official runs, taxonomy, tracing, eval report | Embedded regulation viewer in the UI |
| UI in a container, rate limit, cache, safety suite, HITL, red-team, green CI | PDF export of a declaration checklist |
| 12-page report, live demo, backup video | Extra dev tuning rounds |

Slip rules (mentor): if the gate slips, cut what-if and reduce the corpus to the 500 minimum; prompts freeze before code; nothing is tuned against `eval-v1`; each owner writes their report section when their part freezes.

---

## 15. Deliverables (Track B)

| Deliverable | Where |
|---|---|
| Git repository with the full agent stack | this folder |
| Trace dashboard showing real query executions | the Langfuse project's dashboard; screenshots in `docs/demo/traces/` |
| Evaluation report including the failure taxonomy | `docs/eval-report.md` |
| 12-page technical report | `docs/report/` (body kept to 12 pages) |
| 10-minute live demo | `docs/demo/demo-script.md`, laptop Docker, demo cache, backup video |

## 16. Roles

You do all the work (D22); the report uses these labels for the template's role split.

| Role (template) | Owns in this plan | Label |
|---|---|---|
| Domain spec & eval design | R1–R12 sign-off, SPEC, scenarios review, hand-check of 20 | Person A |
| Prompt engineering | Baselines, constrained-decoding comparison, node prompts | Person B |
| RAG / retrieval | Corpus, chunking, embedding and reranker experiments, citations | Person C |
| Agent orchestration & tools | Graph, modes, calculators, state, error handling | Person D |
| Observability & safety | Langfuse, taxonomy, safety suite, red-team, PII | Person E |
| Front-end & deployment | UI, Docker, CI, rate limit, cache, demo | Person F |

## 17. Risks

| Risk | Mitigation |
|---|---|
| A regulatory claim is wrong | Rules are data with citations and sign-off; a fix is a data change plus a re-run |
| Some sources can't be fetched with plain HTTP (e.g. a JavaScript-rendered CBP Info Center) | Prefer versioned APIs; replace with other official pages and OFAC FAQs; record in `editions.md` |
| Corpus under 500 documents | More CBP articles and OFAC FAQs. The document unit (one CFR section or paragraph, one FAQ, one article) is defined in SPEC and `editions.md` |
| A grader reads the code executor as "not agentic enough" | The planner chooses, skips and loops steps; the verifier can send work back to it; `tool_calling` and `router` ablations are the evidence |
| The LLM planner underperforms the router | A valid result: ship the router as default and report it |
| Shared key, one request at a time, quota unknown | Global gate and limiter; quota log; official runs only when the key is free; cache in development |
| Endpoint down during the live demo | Demo cache (labelled) and backup video |
| Scope vs time | If this becomes the submission (27 Nov), the mentor's plan assumed ~200 person-hours across six people; apply the slip rules early |
| Rates or sanctions change | Frozen snapshot with as-of date |
