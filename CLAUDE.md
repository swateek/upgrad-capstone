# DeclareRight: US customs assistant for alcohol & tobacco

Track B capstone (API-side, ≤8B hosted model), group DLlamas. Working solo with AI assistance.
Programme brief, deadlines and grading: repo-root `README.md` (final submission 27 Nov 2026, presentation 5 Dec 2026).

**All project code and docs live in `customs-agent/`.** Paths in this file are relative to it unless they start with the repo root.

- Mentor proposal (source of truth for scope and plan): `docs/01_US_Customs_Assistant.docx`.
- Day-0 endpoint test guide: `docs/Endpoint_Capability_Check.docx`; results in `docs/endpoint_check.md`.
- Architecture and request flow (Mermaid diagrams + component table): `docs/ARCHITECTURE.md`.

## Repo conventions

- **Setup guide:** `customs-agent/SETUP.md` is how someone else installs and runs the project. When a step is added or changes (new dependency, new build step, new command), update it in the same change.
- **Work log:** `customs-agent/WORKLOG.md` (committed since `198cdb1`). After each piece of work, append an entry under the current day: what, files, found / decided, open.

- **Python env: uv, inside `customs-agent/` only.** `uv sync` to install; `uv run python …` / `uv run pytest` to run; `uv add <pkg>` (or `uv add --dev`) to add dependencies. Never `pip install` into `.venv/`. Commit `pyproject.toml`, `uv.lock` and `.python-version` together.
- **Git flow** (repo-root `docs/GITFLOW.md`): never commit to `main`; short-lived branches `feature/…`, `bugfix/…`, `docs/…`, `refactor/…`; merge through a PR. Commit messages `#<issue> - <what>` when there is an issue.
- **Pre-commit** (repo-root `docs/DEVELOPMENT.md`): Ruff lint + format, gitleaks secret scan, YAML/JSON checks, 500 KB file limit, notebook outputs stripped (except `results/`). Keep generated data under 500 KB per file or keep it out of git.
- Git-ignored: every dotfile at the root (so `.env`), `certs/`, `.venv/`. Never commit keys or certificates.

## What we are building

A multi-agent assistant that answers a returning US resident's question about alcohol and tobacco they carry home, for example "4 bottles of wine after 10 days in Italy, do I owe anything?". It returns:

- the bottom line: amount owed, allowed, or prohibited;
- the working: exemption, allowance, excess, duty, excise;
- the facts it relied on (age, trip length, origin…), so the traveller can correct them;
- citations to the regulation for every claim, with an as-of date;
- a disclaimer that this is an estimate and the CBP officer decides.

It asks one clarifying question only when a missing fact changes the answer, refuses evasion requests, and escalates when it can't verify.

**In scope:** returning US residents; wine, beer, spirits, cigarettes, cigars; $800 and $200 exemptions; age; 1 L / 2 L (Caribbean Basin) alcohol; 200 cigarettes / 100 cigars; flat-rate duty; TTB excise; Cuban-origin ban; arrival-state flag (5 states).
**Out of scope (scope note, no assessment):** other goods, vapes/nicotine pouches, food, cash, non-residents, crew, US insular-possession arrivals ($1,600), commercial quantities, shipped goods.

## Course rubric (upGrad, Track B)

### Deliverables

- Git repository with the full agent stack
- Trace dashboard showing real query executions
- Evaluation report including the failure taxonomy
- 12-page technical report
- 10-minute live demo

### Guardrails that keep it doable in four weeks

- The endpoint, an API key with a per-team token quota, and a starter agent skeleton will be provided.
- Corpus capped at 2,000 documents; agent capped at 10 steps per query.
- Evaluation set frozen and baseline numbers recorded before any agent code is written. This is the single most common failure mode: teams that build first and evaluate later have nothing to report.
- The weakness of the 8B model is an explicit learning objective, not a complaint. "What did we do to compensate for a small model?" is a graded section.

### Where each item stands

| Rubric item | How we meet it | Status |
| --- | --- | --- |
| Git repository, full agent stack | `customs-agent/` on branch `customs-agent-main`; `SETUP.md` rebuilds everything | In progress |
| Trace dashboard | Langfuse (Docker), one trace per question; fallback `trace.jsonl` | Not started (agent records a step trace per item already) |
| Evaluation report + failure taxonomy | `eval/score.py`, official runs Day 10, failure taxonomy Days 11–14 | Baselines done (`docs/BASELINES.md`) |
| 12-page technical report | Days 11–14 | Not started |
| 10-minute live demo | Streamlit in Docker + backup video, Days 11–14 | Not started |
| Corpus ≤ 2,000 documents | 742 documents (`corpus-v1`) | Met |
| ≤ 10 steps per query | Enforced in `src/agent/pipeline.py`: at most 10 tool steps and 12,000 tokens per question, else escalate; the plan validator also caps plans at 10. Router plan: 7 steps (8 for what-if) | Met |
| Eval frozen and baselines recorded before agent code | `eval-v2` tagged, `results/week1_*.csv` committed, gate `gate-day4` before any `src/agent/` code | Met |
| Small-model compensations (graded) | `docs/COMPENSATIONS.md`: symptom, fix, before/after metric per row | Ongoing |

## Non-negotiable rules for any code in this repo

1. **The model never does arithmetic.** Every dollar, volume and count comes from a calculator in `src/tools/`. The verifier rejects any number not present in tool outputs.
2. **Citations only from retrieved clause ids.** The writer may cite only chunks returned by `search_regulations` for this question. The corpus holds official text only (no summaries written by us).
3. **Rules and rates are data, not code.** `data/rules.yaml` and `data/rates.yaml`, each row with citation + as-of date. A regulatory fix is a data change plus a re-run.
4. **Restriction check runs before any calculation** (Cuban origin, under-21, commercial quantity). The plan validator enforces this.
5. **Gold answers are never generated by the code under test.** Gold lives in an independent spreadsheet built from the regulation text; 20 scenarios hand-checked.
6. **Nothing is tuned against `eval-v1`.** Tune on the 20-scenario dev set only.
7. **No agent code before the gate** (end of Day 4: SPEC approved, `eval-v1` tagged, baselines committed). Calculators, corpus and UI skeleton may be built before it.
8. **Secrets:** API key only in `.env` / environment variables. `.env` is in `.gitignore`. Never print or log it.
9. **Log every compensation** for the small model in `docs/COMPENSATIONS.md`: problem, fix, metric, set (`dev` / `eval-v1` / `probe`), before/after from a scored run, evidence file. Rows are keyed by version (git tag or commit), not date. This feeds a graded report section.
10. **Every model call goes through `src/llm.py`**, including the corpus pipeline's embedding calls and eval scripts. Nothing creates its own OpenAI client.

## Endpoints (checked Day 0, see `docs/endpoint_check.md`)

Two separate OpenAI-compatible endpoints, each with its own URL, API key and CA certificate (`.crt`, PEM or DER).

| | Chat | Embeddings |
| --- | --- | --- |
| Model | `Qwen/Qwen3-8B` | `bge-small-en-v1.5` (set via `EMBED_MODEL`: the server has no `/v1/models`, returns 404) |
| Settings (`.env`) | `CHAT_BASE_URL`, `CHAT_API_KEY`, `CHAT_CA_CERT`, `CHAT_MODEL` | `EMBED_BASE_URL`, `EMBED_API_KEY`, `EMBED_CA_CERT`, `EMBED_MODEL` |
| Verified | Native tool calls 3/3; `response_format` `json_schema` and `json_object` both work; `usage` reported | `POST /v1/embeddings` works; **384 dimensions**; **max 512 tokens per input**; **max 16 inputs per call** (422 above; `src/llm.py` batches by 16) |
| Limits | 8,192 tokens per call total, max 1,024 output; 1 request in flight | 1 request in flight |

- Certificates live in `certs/` (git-ignored). TLS setup lives in `src/endpoints.py` (`Endpoint`, `resolve_file()`, `load_ca()`, `make_client()`); application code imports from there, never from `prechecks/`. `CA_RELAX_STRICT=1` only if Python 3.13+ rejects a CA for missing key-usage extensions.
- Design consequences: planner uses native `tools`; planner, writer and verifier use `json_schema`; Pydantic still validates every output. Tool schemas take quantities and durations **as stated** (`{value, unit}`), never pre-converted: asked for `trip_hours`, the model passed `10` for "10 days" (COMPENSATIONS.md row 3). Chunks ≤ 350 tokens (hard limit, below the embedder's 512).
- No thinking mode on this endpoint: replies contain no `<think>` text or `reasoning_content`, so no switch is needed.

## `src/llm.py` (single client for both endpoints; built, 21 tests in `tests/test_llm.py`)

Use: `llm = LLM.from_env(run_name=...)`, then `llm.chat(messages, stage=..., tools=..., response_format=..., max_tokens=...)` → `ChatResult` (content, tool_calls, usage, cached) and `llm.embed(texts, stage=...)` → vectors. Smoke test against the real endpoints: `uv run python -m src.llm`. Live tests (11, about 8 real calls, marker `live`, excluded from the default run): `uv run pytest -m live -v`. Requires `CHAT_MODEL` and `EMBED_MODEL` in `.env`.


- One FIFO queue per endpoint, one request in flight, across threads and across processes on this machine (lock file in `logs/`); exponential back-off with jitter on 429/5xx and connection errors, honouring `Retry-After`; other 4xx fail at once with `LLMError`.
- Refuses before sending (`BudgetError`) any call with `max_tokens` > 1,024 or an estimated total over 8,192 tokens.
- SQLite response cache (`logs/llm_cache.sqlite3`) keyed by model + messages + params; calls with temperature > 0 are cached only with a `sample` id (self-consistency samples 0, 1, 2). **Cache OFF for official runs**: `LLM_CACHE=0` or `cache_enabled=False`.
- Writes one line per call to `logs/usage.jsonl`: timestamp, run name, stage, endpoint, model, prompt/completion tokens, latency, cached flag. This is the source of truth for cost and quota (no manual quota log).
- Budget: target < 3k input tokens per call; retrieval returns 3–5 clauses of ≤ 350 tokens; 12,000 tokens per question.
- Long runs (baselines, official evaluation) run overnight.

## Architecture (mentor design)

```
question
 → guard (code): injection, evasion requests, out-of-scope goods → refuse / scope note
 → intake (LLM, JSON): profile{age, trip_hours, exemption_used_30d, countries[], arrival_state}
                       basket[{item, qty, unit, abv, value_usd, origin, bought_where}]
 → normalise_units (code): "a fifth"→750 ml, "carton"→200 cigarettes, "box of 25"→25 cigars
 → planner (LLM, JSON plan) → plan validator (code: allowed-step graph, inputs present, ≤10 steps)
      missing answer-changing fact → CLARIFY (one question); invalid plan → code router fallback
 → executor: check_restrictions → determine_exemption → compute_allowance → compute_duty_excise
             → lookup_state_rule → search_regulations
 → writer (LLM, JSON): bottom_line, working[], facts_relied_on, citations[], as_of, disclaimer
 → verifier (code + 1 LLM call): $ match tools; citations in retrieved set; facts match profile; no evasion advice
      fail → writer retries once → ESCALATE
 → answered | clarify | refused | escalated
```

- State: LangGraph StateGraph + SqliteSaver; on a correction ("actually it was 3 days") replan only steps depending on the changed field.
- Spec: `docs/SPEC.md`, **APPROVED Day 1**. Project decisions in 5.4; data used from CBP guidance without checking the HTSUS in 5.5 (status `accepted`).
- Ablation: LLM planner vs code router vs `single_rag`. A planner that loses to the router is still a valid, reportable result.
- Error handling: malformed JSON → 2 retries with validation error fed back → escalate; ToolError back to planner; identical repeated call blocked; 10-step cap.
- Tracing: Langfuse, one trace per question (every step's input, output, tokens, latency) for debugging and failure labelling; mask personal data before sending. Fallback `trace.jsonl`. Token cost comes from `logs/usage.jsonl`, not Langfuse.

### Tools (9)

| Tool | Type | Purpose |
| --- | --- | --- |
| `normalise_units` | code | ml/L/fifth/carton/pack/box; ABV → proof |
| `check_restrictions` | code + citation | Cuban origin, under-21, commercial quantity |
| `determine_exemption` | code | $800 vs $200 (48 h, 30-day rule), CBI 2 L, insular scope-out |
| `compute_allowance` | code | exempt vs excess; $200 all-or-nothing |
| `compute_duty_excise` | code + `rates.yaml` | 3% flat duty on excess value; TTB excise by class |
| `lookup_state_rule` | code (5 states) + citation | flag + source link, no amounts |
| `search_regulations` | hybrid RAG | BM25 + dense + reranker, metadata filters |
| `whatif_optimise` | code (stretch) | "most I can bring and owe under $X" |
| `escalate_to_human` | code | hand-off note with facts relied on |

## Regulatory facts: status

Confirmed = checked against the regulation text. VERIFY = must be confirmed from the official source before the eval set is frozen. Day 1 resolutions, with quotes and links: `docs/regulatory_checks.md` ("Checked" = researched there, awaiting human read before `eval-v1`).

| Rule | Status | Source |
| --- | --- | --- |
| $800 exemption: ≥ 48 h abroad (waived for a **direct arrival from Mexico**), not used in previous 30 days | Confirmed | 19 CFR 148.33, 148.35(a), 148.36; HTSUS 9804.00.65 |
| $200 exemption otherwise: 50 cigarettes, 10 cigars, 150 ml alcohol; no family pooling | Confirmed | 19 CFR 148.51 |
| $200 is **all-or-nothing**: if any article exceeds a limit or the $200 value, nothing is exempt | Confirmed | 19 CFR 148.51(b) |
| 1 L alcohol in the $800 exemption, age 21+, personal use, legal in arrival state | Confirmed | 19 CFR 148.33 |
| 2 L if arriving directly from a Caribbean Basin (CBI) country, ≥ 1 L produced there | Confirmed | 19 CFR 148.33(d) |
| Under 21: no alcohol in the exemption | Confirmed | 19 CFR 148.33 |
| Excess alcohol: flat 3% on next $1,000 + federal excise, even if total < $800 | Confirmed | HTSUS 9816.00.20; 19 CFR 148.101+ |
| Flat rate by **origin**: 3% general; **Free** for listed FTA partners incl. Mexico/Canada (USMCA `S`); **4%** Column 2 (Belarus, Cuba, North Korea, Russia). Excise still due. Flat rate has its own 30-day rule. No 2026 surcharge on Chapter 98 entries | Checked | HTSUS 9816.00.20; USITC Pub. 5060 |
| TTB excise: still wine ≤ 16% $1.07/gal; spirits $13.50/proof gal; small cigarettes $50.33/1,000; large cigars 52.75% capped $402.60/1,000; beer $18/bbl | Confirmed (store as-of date) | TTB rate tables |
| 200 cigarettes + 100 cigars in the $800 exemption | Confirmed | 19 CFR 148.33; CBP |
| Tobacco over the allowance: **not a duty calculation**; declare, excess subject to detention/seizure/abandonment; no dollar figure | Checked | CBP customs duty information; 19 USC 1681a |
| US-made export-labelled (duty-free) cigarettes: allowed only up to the exemption; **relinquish the excess** at entry (no penalty), else forfeiture + penalty. No AGR route for excess (escalate if claimed) | Checked | 26 USC 5754, 5761(c)-(d) |
| Cuban alcohol/tobacco: acquired in Cuba barred since 24 Sep 2020 | Confirmed | OFAC FAQ 719 |
| Cuban alcohol/tobacco bought in a third country (e.g. Cancún): prohibited as baggage | Checked | 31 CFR 515.204(a), 515.585(d); CBP Info Center 1389 |
| CBP enforces stricter arrival-state alcohol limits | Confirmed | CBP customs duty information |
| Russian-origin alcohol (EO 14068) in personal baggage: unresolved (IEEPA travel exemption may apply); **v1 escalates** | Open | E.O. 14068; OFAC FAQs 1024, 1182 |

**Retrieval trap:** 19 CFR 148 Subpart G (crew members, incl. 148.64) has the same 50 / 10 / 150 ml limits as 148.51. Keep it in the corpus as a hard negative, tag it `crew`, and never cite it for a traveller.

### Worked examples (gold candidates)

- 4 × 750 ml wine, 13% ABV, $30 each; 10 days in Italy; age 34; exemption unused. 3 L, 1 L exempt, 2 L excess ($80). Duty 3% = $2.40; excise 0.528 gal × $1.07 = $0.57. **Total $2.97.**
- Day trip to Tijuana, one 750 ml bottle of tequila, age 21+, exemption unused: direct arrival from Mexico gets the **$800** exemption whatever the trip length (148.35(a)); 750 ml is within the 1 L allowance. **Total $0.**
- Day trip to Canada, one 750 ml bottle of 40% Canadian whisky: $200 exemption; 750 ml > 150 ml, so **nothing is exempt** (all-or-nothing): the whole bottle goes to the flat rate. Canadian origin (USMCA) → duty **$0**; excise 0.198 gal × 0.8 × $13.50 ≈ **$2.14**. **Total ≈ $2.14** + state tax.
- Cuban cigars bought in Cancún: prohibited; cite 31 CFR 515.204(a) and 515.585(d).

## Corpus (target 500–840 documents; freeze on Day 3)

Unit = one CFR paragraph/section, one HTSUS heading or note, one FAQ, one article. Store raw HTML, extracted text, URL, retrieval date, SHA-256.

| Source | ~Count |
| --- | --- |
| 19 CFR Part 148 (by section/paragraph, incl. Subpart G as hard negative) | 120–180 |
| HTSUS ch. 98 Subchapter IV (9804, 9816) + U.S. notes | 30–50 |
| 27 CFR TTB rate provisions + TTB rate tables | 40–60 |
| 26 USC 5001, 5041, 5051, 5701, 5754, 5761 | 20–30 |
| 31 CFR Part 515 + OFAC Cuba FAQs | 100–150 |
| CBP traveller guidance + CBP Info Center articles | 100–200 |
| State alcohol personal-import rules (5 states) | 5–10 |
| Hard negatives: food, medication, cash reporting, Form 6059B, vapes | 80–150 |

Starting point: `data/rag-corpus/` (fetch script, `sources.yaml`, chunker). 14 official sources (one is the Subpart G hard negative, authority `hard_negative`); must be extended. Official text only: the curated plain-English summary was removed on Day 1.

Chunks carry a metadata header (source, section path, authority, tags, as-of). Filter on metadata before reranking: rerankers can pick the wrong near-duplicate CFR section. Chunks stay ≤ 350 tokens: `bge-small-en-v1.5` silently truncates input beyond 512.

## Evaluation

- `eval/eval_set.jsonl`: 80 scenarios, frozen as git tag `eval-v1` at end of Day 3. Dev set: 20 separate scenarios.
- Types (n): alcohol_excess_800 (12), alcohol_cbi_2L (4), exemption_200_all_or_nothing (8), tobacco_over_limit (7), cuban_origin (7), under_21 (4), mixed_basket (10), whatif (4), clarify (8), state_flag (3), out_of_scope (5), refuse_evasion (4), injection_doc (2), injection_user (2).
- Correct = bottom line equals gold; every $ within $0.01; each claim cites the gold regulation; clarify asked exactly when gold says a fact is missing and answer-changing.
- `eval/score.py` scores deterministically. An LLM judge only for secondary metrics, with agreement vs human labels on ≥ 30 items.
- Baselines (Day 4): closed_book, fewshot_json, cot_sc (3 sequential samples), decompose; dollar items also without calculators → `results/week1_strategies.csv`, `results/week1_failures.csv`.
- Retrieval (Days 5–7): BM25 / dense / hybrid RRF (k=60) / hybrid + reranker × topic filter × 3 chunkings → `results/retrieval_experiment.csv` (recall@1/3/5/10) + three written decisions.
- Official runs (Day 10, overnight, cache off): 3 × agent, 1 × code router, 1 × single_rag.

## Stack

LangGraph · Pydantic v2 · numpy flat index + rank_bm25 (no Qdrant: docs/RETRIEVAL.md) · reranker `cross-encoder/ms-marco-MiniLM-L-6-v2` (compare `BAAI/bge-reranker-v2-m3`) · embeddings: `bge-small-en-v1.5` from the provided endpoint (384-d) · Langfuse (fallback `logs/trace.jsonl`) · **web app: FastAPI (`app/api.py`) + React/Vite/TypeScript (`web/`) instead of Streamlit** (decision Day 6: Streamlit could not give the answer card, editable facts and regulation viewer a demo needs; one container serves both) · Docker + docker-compose (app + Langfuse) · GitHub Actions. Local dev on the same model family as the endpoint via Ollama/vLLM.

## Repo layout

```
# all paths relative to customs-agent/
pyproject.toml, uv.lock      # uv-managed dependencies
docs/SPEC.md                 # item I, marked APPROVED
docs/ARCHITECTURE.md         # component + request-flow diagrams (Mermaid)
docs/COMPENSATIONS.md        # running log for the graded section, keyed by version
docs/endpoint_check.md       # Day-0 endpoint report
prechecks/check_endpoint.py  # endpoint check; source of Endpoint/make_client TLS helpers
certs/                       # CA certificates, git-ignored
.env                         # endpoint URLs, keys, cert paths, model names; git-ignored
data/                        # rules.yaml, rates.yaml, rag-corpus/, raw snapshot + hashes
logs/                        # git-ignored: usage.jsonl (one line per model call), llm_cache.sqlite3, queue locks
eval/eval_set.jsonl          # frozen, tag eval-v1
eval/dev_set.jsonl
eval/score.py
src/endpoints.py             # endpoint settings, TLS (CA certs), OpenAI client factory
src/llm.py                   # chat + embeddings clients: queue, retries, cache, usage log
src/schemas.py               # Pydantic models for every agent output
src/retrieval/               # chunkers, bm25, dense, hybrid (RRF k=60), reranker
src/tools/                   # each tool: pydantic args, ToolError on failure
src/agent/graph.py           # guard → intake → planner → validator → executor → writer → verifier
src/safety/                  # guard rules, sanitiser, PII masking
app/streamlit_app.py
results/                     # week1_strategies.csv, retrieval_experiment.csv, runs/
tests/
```

## Plan and gates (14 days)

From the mentor proposal's day-by-day table (`docs/01_US_Customs_Assistant.docx`, section 5). ✅ done, ⏳ open, ⚠️ open and behind the mentor's day.

| Days | Work (mentor plan) | Exit criterion | Status |
| --- | --- | --- | --- |
| 0 | Endpoint check; repo skeleton; `src/llm.py`; COMPENSATIONS.md | `docs/endpoint_check.md` committed | ✅ |
| 1–2 | Resolve VERIFY rows; rules.yaml + rates.yaml; SPEC.md; calculators + unit tests | SPEC APPROVED; rule tests green | ✅ |
| 1–3 | Corpus fetch, clean, dedupe, metadata; freeze snapshot | ≥ 500 docs, hashes stored | ✅ 742 docs, `corpus-v1` |
| 2–3 | 80 + 20 scenarios; independent gold spreadsheet | tag `eval-v1` | ✅ `eval-v2` |
| 4 | Four prompting baselines | **GATE**: week1 CSVs committed | ✅ `gate-day4` |
| 5–7 | Retrieval experiment + three decisions; citation grounding; agent v0 end to end on dev; code router | recall@k table; three decisions | ✅ (+ LLM planner, single_rag, hard budget, paraphrase check) |
| 5–7 | Writer and verifier prompts; failure notes for the report | | ✅ |
| 5–7 | UI connected to agent v0; trace link per answer; PII masking in logs; taxonomy labelling rules | **Day 7 checkpoint:** "the web app shows real answers" (React + FastAPI replaces Streamlit) | ✅ app, traces, PII masking (Day 6); ⏳ taxonomy labelling rules |
| 8 | Error handling: JSON retries ✅, ToolError back to the planner ⏳, loop block ✅, 10-step cap ✅, token budget ✅ | error-handling tests pass | ⏳ |
| 8 | Corrections across turns: LangGraph StateGraph + SqliteSaver; replan only steps that depend on the changed field | | ✅ built (Day 7); 13 dev conversations to run |
| 8 | Rate limit (10 questions per minute); answer cache (off for official runs) | | ✅ |
| 8 | Error-handling tests | | ⏳ |
| 9 | Dry-run scoring on dev; prompt freeze at end of day; freeze the retrieval configuration | prompts frozen | ⏳ |
| 9 | Verifier rules final; red-team prompt list (15+) | | ✅ red-team list (20, eval/redteam.yaml) |
| 9 | Editable "facts relied on" in the UI that triggers a replan | | ✅ ("Correct a fact" → /api/edit) |
| 9 | **Checkpoint:** must-have vs. stretch (section 5.4) | | ⏳ |
| 10 | Official runs overnight, cache off: 3 × LLM-planner agent, 1 × code router, 1 × single_rag (≈ 3–4 h); code freeze, tag `v1.0.0-rc`; red-team against the live app, logged; CI green, image builds, health check; report §3 (prompting, small-model failures) and §4 (retrieval) | tag `v1.0.0-rc` | ⏳ |
| 11 | Metrics: accuracy per type, $ accuracy, citation accuracy, clarify precision/recall, completion, tool calls, tokens and cost, p50/p95 latency; failure taxonomy (label every wrong answer, hand-check ≥ 15); recall@k next to end-to-end accuracy; report §5 (agent design, planner vs. router), §6 (responsible AI, injection and PII results, HITL boundary); deploy the container | | ⏳ |
| 12 | Report §7 from COMPENSATIONS.md; figures; blocking bugs only; security notes, model limits, as-of dates; demo script (four conversations + one refusal + one correction) | | ⏳ |
| 13 | Assemble the 12-page report; optional 2 more router runs; final check: no keys in Git, masked logs; backup demo video; full rehearsal | | ⏳ |
| 14 | Final report, tag `v1.0.0`; live demo dry-run; submission | tag `v1.0.0` | ⏳ |

### Must-have vs. stretch (mentor 5.4): we are doing all of it

| Must-have (graded) | Stretch |
| --- | --- |
| SPEC, 80-question frozen set, 4-strategy baseline ✅ | `whatif_optimise` and its 4 items ✅ (built; D12 passes) |
| Corpus ≥ 500, hybrid + reranker, recall@k, citations ✅ | State-rule table beyond 5 states ⏳ |
| LLM planner + validator + executor + verifier, ≥ 3 tools ✅; memory and corrections ⏳; error handling (partly) | 3 code-router runs (1 is enough for the ablation) ⏳ |
| Official runs (3 × agent, 1 × router, 1 × single_rag), taxonomy, tracing ⏳ | Embedded regulation viewer in the UI ⏳ |
| Web app (React + FastAPI) in a container ⏳, rate limit ✅, cache ✅, injection/PII/refusal tests (partly), HITL boundary, red-team log ⏳ | PDF export of the declaration checklist ⏳ |
| 12-page report, 10-minute demo, backup video ⏳ | Extra dev-set tuning rounds (partly: stop at the prompt freeze) |

Rules that still hold: prompts freeze on Day 9 and code on Day 10; nothing is tuned against the eval set; if the schedule slips, stretch items go first, then UI extras. Never drop the eval set, baselines, retrieval table, planner + verifier, or official runs.

### Next, in order

1. Day 7 catch-up: ✅ web app (React + FastAPI) on agent v0 with answer card and regulation viewer; ✅ Langfuse tracing with a trace link per answer (= rubric "trace dashboard"; needs Langfuse keys); ✅ PII masking; ⏳ taxonomy labelling rules.
2. Days 8–9: multi-turn dev conversations (written before the code, independent gold) → LangGraph StateGraph + SqliteSaver, clarify → answer → continue, corrections replan only dependent steps, defaults after two unanswered rounds (SPEC 5.2); ToolError back to the planner; rate limit; error-handling tests; editable facts in the UI; red-team list (15+); also the rule-4 gap (Cuban item with an unreadable count asks before it prohibits).
3. Stretch, alongside: state rules beyond 5 states; regulation viewer; PDF checklist export.
4. Day 9 checkpoint and prompt freeze, then Day 10 official runs.

## Current status

**Day 0: done.**

- [x] Endpoint check run; `docs/endpoint_check.md` committed (results in "Endpoints" above).
- [x] `prechecks/check_endpoint.py`: separate chat/embeddings settings, `.crt` CA certs (PEM or DER), path resolution.
- [x] `docs/ARCHITECTURE.md`: component and request-flow diagrams.
- [x] `docs/COMPENSATIONS.md` started: 2 rows + planned measurements.
- [x] `data/rag-corpus/` starter kit in place: sources list, fetch script, chunker; official text only (curated summary removed Day 1). Must grow to 500+.
- [x] `src/endpoints.py` + `src/llm.py` with 21 tests (mock API, no quota).
- [x] Day 1: first corpus fetch (14 sources, incl. CBP Info Center saved from the browser).
- [x] Day 1: `docs/regulatory_checks.md` drafted: 4 of 5 VERIFY rows researched (Russian alcohol → escalate). **Needs your read of the cited text.**
- [x] Day 1: `data/rules.yaml` (exemptions, 9 restrictions, flags, out-of-scope) and `data/rates.yaml` (flat rate by origin, programme codes, Column 2, TTB excise, conversions) written from the regulation text; both worked examples reproduce ($2.97, $2.14).
- [x] 2 L beneficiary-country list (27 countries, from CBP; status checked) in `rates.yaml`; 5 states (NY, FL, CA, TX, NJ) with official sources and the commercial-quantity threshold (> 9 L or > 12 units, project decision) in `rules.yaml`.
- [x] `docs/SPEC.md` **APPROVED (Day 1)**: commercial threshold and 5 states adopted (5.4); 2 L list (now 30, incl. Curaçao, Sint Maarten, Caribbean Netherlands) and programme codes used from CBP without HTSUS check, status `accepted` (5.5); eval table has 6 `cuban_origin` + 1 `sanctions_escalate`.
- [ ] Not blocking: check SPEC 5.5 data against HTSUS General Notes 3, 7, 11 if time allows.
- [x] Eval sets written: `eval/scenarios.yaml` → `eval/gold.xlsx` (formula gold, independent of `src/tools`; readable working in `eval/gold.md`) → `eval/eval_set.jsonl` (80, SPEC 7 counts) and `eval/dev_set.jsonl` (20). Cross-checked with a separate decimal calculation: 61 priced lines and 5 what-ifs agree. Format and gaps in `eval/README.md`.
- [x] Hand check of the eval gold done by the project owner: all match.
- [x] `eval-v1` tagged locally on `customs-agent-main` (not pushed); superseded by `eval-v2` (Day 3: 2 L country list corrected from the HTSUS, E15 and E48 changed).
- [x] Calculators: `src/schemas.py` and `src/tools/` (normalise_units, check_restrictions, determine_exemption, compute_allowance, compute_duty_excise, lookup_state_rule, whatif_optimise, escalate_to_human), reading `rules.yaml` / `rates.yaml`. Tests: `tests/test_tools.py` (rule tests with clause references) and `tests/test_dev_set.py` (all calculable dev scenarios match gold). All 94 tests pass on the Mac (73 tool + 21 llm).
- [x] Corpus v2 built (Day 3): 742 docs in `data/rag-corpus/corpus/docs/` (one per CFR section, USC section, HTSUS line/note, OFAC FAQ, page section), `MANIFEST.json` with SHA-256s, raw snapshots in `corpus/raw/` (3 PDFs over 500 KB git-ignored). Every citation in the eval gold and the YAML files exists as a `citation_id`. EO 14068 saved by hand (`corpus/raw/eo14068.html`).
- [x] Chunks: 1,289 (≤ 350 tokens each). The corpus itself is not committed: `corpus/docs/`, `corpus/raw/` and `chunks.jsonl` are rebuilt from `SETUP.md` step 5; committed are `MANIFEST.json` (hashes), `raw/INDEX.json` and the two hand-saved pages. eCFR date pinned (`ecfr_as_of` in `sources.yaml`).
- [x] Corpus committed as manifest + hand-saved pages; tag `corpus-v1`.
- [x] Day 4 code: `eval/score.py` (deterministic scorer, SPEC 6), `src/baselines/` (closed_book, fewshot_json with 4 dev examples, cot_sc 3 samples, decompose 3 steps; closed book, model does all arithmetic), `eval/run_baselines.py` (resumable; writes `results/week1_*.csv` for the eval set). 124 offline tests.
- [x] Baselines run: dev v1/v2 (prompt fixes logged), official `week1` on eval-v2 -> `results/week1_strategies.csv`, `results/week1_failures.csv`; write-up `docs/BASELINES.md`. Best accuracy 0.175 (fewshot_json); dollars ≤ 0.07; clarify ≤ 1/8.
- [x] **Gate passed (end of Day 4):** SPEC approved, `eval-v2` tagged, baselines committed (commit 5615aa7, tag `gate-day4`). Agent code now allowed.
- [x] Days 5–7 retrieval: `results/retrieval_experiment.csv` (+ `_bge`), decisions in `customs-agent/docs/RETRIEVAL.md` (hybrid RRF + `BAAI/bge-reranker-v2-m3`, 350-token chunks, hard negatives filtered, k = 5, numpy index instead of Qdrant). `search_regulations` built (by citation id + search; saved index in `data/rag-corpus/index/`).
- [x] Days 5–7: agent v0 (code router) and LLM planner + validator end to end on dev; single_rag arm; hard budget (10 steps, 12k tokens). Dev ablation in WORKLOG (Day 6). Paraphrase check 0.883 before fixes.
- [ ] `uv add --dev pyyaml openpyxl` (needed by `eval/build_eval.py`).
- [ ] Add the newly cited sources to the corpus: 19 USC 1681a, 26 USC 5754/5761, HTSUS General Note 3 and ch. 98 U.S. Note 4, OFAC Russia FAQs.

- Business case and first technical design exist (pre-mentor review): Business Case https://claude.ai/artifact/3EmBYyxpiwUn4LhgD2xKvJ · Technical Design https://claude.ai/artifact/AAoYfA26TQhgigAvZfzQoc. The mentor proposal supersedes them where they differ (planner, 9 tools, corpus size, corrected facts).

Update this section as work lands.
