# Work log

Local record of what was done, decided and found, written as the work happens. **Not committed** (git-ignored); the committed record is `CLAUDE.md` (status) and `docs/COMPENSATIONS.md` (graded evidence).

How to add an entry: append under the current day, newest at the bottom. One entry per piece of work:

- **What:** what was done, in one line
- **Files:** created or changed
- **Found / decided:** results, decisions and why
- **Open:** anything left to do because of it

---

## Before Day 0: planning

- **What:** Defined the system (intake → duty and restrictions specialists → writer → verifier) and wrote a business case and technical design.
  - **Files:** claude.ai docs: [Business case](https://claude.ai/artifact/3EmBYyxpiwUn4LhgD2xKvJ), [Technical design](https://claude.ai/artifact/AAoYfA26TQhgigAvZfzQoc)
  - **Found / decided:** Numbers come from code, not the model; a verifier checks every number and citation.
- **What:** Narrowed scope to alcohol and tobacco only.
  - **Found / decided:** API limits (1 request in flight, 8,192 tokens per call) favour one small category with a compact corpus and precise eval answers.
- **What:** Built a corpus kit (fetch script, sources list, chunker, curated reference) when asked for RAG documents.
  - **Found / decided:** Government sites were unreachable from the cloud workspace, so the kit downloads on the local machine instead. Caught a mis-citation: 19 CFR 148.64 is the crew exemption; the $200 resident rule is 148.51.
- **What:** Mentor review received (`docs/01_US_Customs_Assistant.docx`).
  - **Found / decided:** Approved with changes: LLM planner + plan validator (code router as fallback and ablation), 9 tools, corpus of 500–840 documents with hard negatives, 80-scenario eval set, Day 4 gate before any agent code. Corrections: $200 exemption is all-or-nothing (day-trip example was wrong: whole bottle dutiable, about $2.14 excise); Caribbean Basin 2 L rule in scope; excess tobacco and US-cigarettes-returning claims to verify; cite 31 CFR 515.204 for Cuban goods bought elsewhere.
- **What:** Created `CLAUDE.md` as the project brief for Claude Code sessions.

## Day 0

- **What:** Endpoint check script adapted from the mentor's version.
  - **Files:** `prechecks/check_endpoint.py`, `docs/endpoint_check.md`
  - **Found / decided:** Report written as markdown. Separate URL, key and CA certificate per endpoint; `.crt` files read as PEM or DER; relative cert paths resolved with a clear error. Results: chat `Qwen/Qwen3-8B` — native tool calls 3/3, `json_schema` and `json_object` work, usage reported. Embeddings `bge-small-en-v1.5` — 384 dimensions, 512-token input limit, no `/v1/models` route (so `EMBED_MODEL` must be set).
- **What:** Process decisions.
  - **Found / decided:** No manual quota log: `src/llm.py` writes `logs/usage.jsonl`. Langfuse for per-question traces (graded tracing + failure labelling). `COMPENSATIONS.md` rows keyed by version, not date. No thinking mode on this endpoint, so no switch or test.
- **What:** Design docs.
  - **Files:** `docs/COMPENSATIONS.md`, `docs/ARCHITECTURE.md` (component and request-flow diagrams in Mermaid, parser-checked)
  - **Found / decided:** Ablations on Day 10: agent vs code router vs single_rag on the same 80 scenarios.
- **What:** Repo set-up and `CLAUDE.md` refresh.
  - **Files:** `CLAUDE.md`, root `.gitignore`
  - **Found / decided:** Project lives in `customs-agent/` (uv). Conventions: `uv add`, never pip; no commits to `main`; pre-commit runs Ruff and gitleaks. `CLAUDE.md` un-ignored so it is committed.
- **What:** LLM client.
  - **Files:** `src/endpoints.py`, `src/llm.py`, `tests/test_llm.py` (21 offline tests), `tests/test_live.py` (11 live tests, marker `live`), `pyproject.toml` (marker, default run excludes live)
  - **Found / decided:** One request in flight per endpoint (threads and processes), retries with `Retry-After`, SQLite cache (off for official runs), size check before sending, usage log without prompts or keys. All 11 live tests pass against the real endpoints.
- **What:** First small-model finding.
  - **Files:** `tests/test_live.py`, `docs/COMPENSATIONS.md` row 3, `CLAUDE.md`
  - **Found / decided:** Asked for `trip_hours`, Qwen passed `10` for "10 days". Tool schemas now take quantities and durations as stated (`{value, unit}`); `normalise_units` converts in code. Re-test: 1/1.
- **What:** Incidents.
  - **Found / decided:** Editor auto-save overwrote an updated `tests/test_live.py` with the old copy; rewritten, and the file closed in the editor. A git dry run from the cloud side left `.git/index.lock`; moved to `.git/stale-index-lock-from-claude`.
  - **Open:** delete `.git/stale-index-lock-from-claude`.
- **What:** Corpus kit placed in the repo.
  - **Files:** `data/rag-corpus/` (README, `sources.yaml`, `fetch_corpus.py`, `chunk_corpus.py`, curated reference)
  - **Found / decided:** Curated reference corrected ($200 all-or-nothing, day-trip $2.14) and unverified tobacco claims marked UNVERIFIED. Subpart G (crew) added as a `hard_negative` source: 15 sources. pip replaced with uv. Lint fixes and a chunker crash fixed. Nothing downloaded yet.
  - **Open:** `uv add requests pyyaml beautifulsoup4 lxml markdownify`, then run the fetch. Grow to 500+ documents.

### Open at end of Day 0

- [ ] Commit Day 0 on the branch: `src/`, `tests/`, `data/rag-corpus/`, `CLAUDE.md`, `.gitignore` files, `docs/COMPENSATIONS.md`, `pyproject.toml`.
- [ ] Day 1: regulatory checks → `docs/regulatory_checks.md` → `data/rules.yaml`, `data/rates.yaml`.
- [ ] Day 1: add corpus dependencies and run the first fetch.

## Day 1

- **What:** First corpus fetch (run locally): 13 of 15 sources downloaded.
  - **Files:** `data/rag-corpus/corpus/primary/*.md` (13 files), `corpus/fetch_report.json`; `data/rag-corpus/sources.yaml`, `fetch_corpus.py`, `README.md`
  - **Found / decided:** Content checked: 19 CFR 148.51 limits (50 / 10 / 150 ml), crew sections 148.61-148.67, 31 CFR 515.204/.560/.585, HTSUS 9804 and 9816 lines, CBP duty page (incl. tobacco and AGR text), OFAC FAQs 719/769, TTB rates. The TTB rates page already includes tobacco, so the separate TTB tobacco source (404) was dropped: 14 sources. CBP Info Center returns 401 to scripts. Fetch script no longer retries permanent errors (401/404). HTSUS 9816.00.20 special-rate column lists programme codes where the flat rate is Free; check which codes cover Mexico/Canada during the regulatory checks.
  - **Open:** The old CBP Info Center address redirects to a login; the article moved to https://www.help.cbp.gov/s/article/Article-1389?language=en_US (`sources.yaml` updated). It is JavaScript-rendered, so it must be saved from a browser (Chrome: Save Page As → Webpage, Complete) to `data/rag-corpus/corpus/raw/cbp_info_cuban_cigars.html`, then re-run with `--only cbp_info_cuban_cigars`. Corpus is 13 documents, one per source: needs splitting into one document per section/FAQ/article and many more sources to reach 500+.

- **What:** CBP Info Center Cuban-cigars article saved from the browser and converted: corpus complete at 14 of 14 sources.
  - **Files:** `data/rag-corpus/corpus/raw/cbp_info_cuban_cigars.html`, `corpus/primary/cbp_info_cuban_cigars.md`
- **What:** Regulatory checks drafted for the five open rules.
  - **Files:** `docs/regulatory_checks.md` (new); `CLAUDE.md` (facts table, worked examples, status); `data/rag-corpus/corpus/curated/alcohol_tobacco_rules_reference.md`
  - **Found / decided:**
    1. Tobacco over the allowance: not a duty calculation; declare, excess subject to detention/seizure/abandonment (CBP; 19 USC 1681a for cigarettes).
    2. US-made export-labelled (duty-free) cigarettes: only up to the exemption; relinquish the excess at entry without penalty, else forfeiture and penalty (26 USC 5754, 5761(c)-(d)). No AGR route for excess.
    3. Cuban alcohol/tobacco bought in a third country: prohibited (31 CFR 515.204(a); 515.585(d) excludes alcohol and tobacco).
    4. Flat rate by origin: 3% general, Free for listed FTA partners incl. USMCA (Mexico/Canada), 4% Column 2; excise always due; flat rate has its own 30-day rule; 2026 Section 122 surcharge not applied to Chapter 98 entries. Tijuana tequila example is now $0 duty + about $2.14 excise.
    5. Russian-origin alcohol: unresolved; v1 escalates.
  - **Open:** Human read of the cited text for checks 1–4. Confirm General Note 3(c)(i) codes (e.g. `P` = CAFTA-DR). Write `data/rules.yaml` and `data/rates.yaml`. Add 19 USC 1681a, 26 USC 5754/5761, HTSUS General Note 3 and OFAC Russia FAQs to the corpus.

- **What:** Removed the curated plain-English summary from the corpus.
  - **Files:** deleted `data/rag-corpus/corpus/curated/`; updated `data/rag-corpus/README.md`, `CLAUDE.md` (rule 2, corpus section, status), `docs/regulatory_checks.md`
  - **Found / decided:** The corpus holds official text only. The summary was written by us, had needed two corrections, and is not in the mentor's corpus plan. If plain-English questions retrieve poorly later, a summary can be tested as a retrieval experiment.

- **What:** Wrote the rule and rate data files from the regulation text.
  - **Files:** `data/rules.yaml`, `data/rates.yaml` (new); `docs/regulatory_checks.md` (check 6, examples); `CLAUDE.md` (facts table, worked examples, status)
  - **Found / decided:** Read 19 CFR 148.33–148.36 and 148.51 in full. New finding: **148.35(a) waives the 48-hour rule for a direct arrival from Mexico**, so a Tijuana day trip gets the $800 exemption (one bottle of tequila: $0 owed). The all-or-nothing $200 example now uses a day trip to Canada (still about $2.14 excise, duty Free under USMCA). Also from the text: the $800 exemption is applied to the highest-rate articles first (148.33(b)); the 30-day period excludes the arrival day (148.36(b)); tobacco has no age in 148.33 (age 21 comes from CBP guidance). All rates taken from the downloaded TTB page (general rates, not producer credits). Both worked examples reproduce from the files ($2.97 wine, $2.14 whisky).
  - **Open:** beneficiary-country list for the 2 L rule (HTSUS ch. 98 U.S. Note 4); confirm programme codes (GN 3(c)(i)); commercial-quantity threshold and the 5 states (decide in SPEC); add 19 USC 1681a, 26 USC 5754/5761, GN 3, ch. 98 U.S. Note 4 and OFAC Russia FAQs to the corpus.

- **What:** Filled the open data and drafted the spec.
  - **Files:** `data/rates.yaml` (2 L beneficiary countries), `data/rules.yaml` (5 states, commercial threshold), `docs/SPEC.md` (new), `CLAUDE.md`
  - **Found / decided:** 2 L list: 27 Caribbean Basin and Andean countries from the CBP page already in the corpus; "Netherlands Antilles" (dissolved 2010) kept as to-confirm (Curaçao, Sint Maarten, Caribbean Netherlands); 5 ineligible islands listed. States: NY, FL, CA, TX, NJ with official sources (NY Tax Dept, Florida statute 562.16, California ABC, Texas TABC, NJ Treasury); notes only, no state amounts. Of note: California limits alcohol from Mexico to the federal duty-free quantity, and Texas collects state tax at ports of entry. Commercial threshold (project decision): escalate above 9 L total or 12 units of one product. Spec adds calculation conventions (highest-rate litre exempt first, rounding), clarify/refusal/escalation tables, and moves one Cuba scenario to a Russian-alcohol escalate scenario.
  - **Open:** Mentor approval of `docs/SPEC.md`; confirm programme codes and the 2 L list from the HTSUS Chapter 98 PDF.

- **What:** SPEC approved by the project owner, with the open items decided rather than verified.
  - **Files:** `docs/SPEC.md` (status APPROVED; new 5.5 and 9; 5.4 and 7 marked adopted), `data/rates.yaml`, `data/rules.yaml`, `CLAUDE.md`
  - **Found / decided:** 2 L country list and trade-programme codes used as published by CBP, not checked against the HTSUS; new status `accepted` in the legend. Netherlands Antilles read as Curaçao, Sint Maarten and Caribbean Netherlands, so the 2 L list is now 30. Known risks recorded in SPEC 5.5: ATPA expired 2013 (Bolivia, Ecuador); FTA countries are "former beneficiary countries" in the HTSUS. Commercial threshold (> 9 L or > 12 units) and the five states adopted; federal law sets no personal-use limit (TTB: CBP port director decides). Eval table change adopted: 6 `cuban_origin` + 1 `sanctions_escalate`.
  - **Open:** Not blocking: HTSUS check of SPEC 5.5. Next: eval scenarios + gold spreadsheet, calculators.

- **What:** Wrote the evaluation sets and the independent gold.
  - **Files:** `eval/scenarios.yaml`, `eval/gold.xlsx`, `eval/build_eval.py`, `eval/eval_set.jsonl` (80), `eval/dev_set.jsonl` (20), `eval/README.md` (new); `docs/SPEC.md` (3, 5.1, 7); `CLAUDE.md`
  - **Found / decided:** Dollar gold is spreadsheet formulas with rates typed in from TTB and HTSUS 9816.00.20, not read from rates.yaml; per-line exempt litres are hand allocations (highest duty + excise per litre first), with the per-litre charge shown for checking. A separate decimal script outside the repo agrees on all 61 priced lines and 5 what-ifs. Every answered question states age, trip length, 30-day use, origin, ABV and price, so only the 8 clarify scenarios have a missing fact. SPEC changes: new profile field `flat_rate_used_last_30_days` (the flat rate has its own 30-day rule; E20 and E24 test it); rounding stated as per line. Citations are scored at regulation level (`19cfr148.33`), mapped from chunk metadata.
  - **Open:** Hand re-check of 20 scenarios tomorrow, then tag `eval-v1`. Spec gaps kept out of the eval (README): tobacco losing the exemption when $200 fails on another item; tobacco using up the $800 value; two-turn clarify. Corpus still lacks 26 USC 5754 (cited by E27). `uv add --dev pyyaml openpyxl`.

- **What:** Added `eval/gold.md`: a readable copy of the gold with the working for every priced line and what-if.
  - **Files:** `eval/build_eval.py` (export writes gold.md; workbook gains unrounded value and excise columns), `eval/gold.md` (new), `eval/README.md`
  - **Found / decided:** Keep both: `gold.xlsx` calculates (formulas), `gold.md` is for reading, the hand re-check and git diffs. Every number in gold.md is a spreadsheet value; the script only formats. Gold unchanged (cross-check still 0 problems).

- **What:** First-pass review of the 20 hand-check scenarios by a separate Claude session (AI review, not the human hand check).
  - **Files:** `docs/SPEC.md` (5.1, 5.4), `eval/build_eval.py`, `eval/gold.xlsx`, `eval/gold.md`, `eval/README.md`
  - **Found / decided:** No disagreements. Three notes: (1) "highest rate" ranking basis is not in 148.33(b); per litre kept and recorded as a project decision in SPEC 5.4 (per dollar would give E44 $3.84, E46 $2.16). (2) E48 depends on Peru being on the accepted 2 L list (SPEC 5.5); E15 (Dominican Republic) has the same risk. Both listed in eval/README "Answers that rest on a project choice". (3) E53 what-if showed 12 bottles as "within limits: no"; the column mixed the target and the quantity threshold. Split into `under_target` and `within_commercial_threshold`. Gold unchanged; cross-check 0 problems.
  - **Open:** Human spot-check still to do (the review is AI, so it can share the original's blind spots), then tag `eval-v1`.

- **What:** Clarify policy for several missing facts, and the eval updated to test it.
  - **Files:** `docs/SPEC.md` (5.2 rewritten, 6 item 4), `eval/scenarios.yaml` (E57, D13 rewritten; `clarify_fact` → `clarify_facts` list), `eval/build_eval.py`, `eval/README.md`, exports regenerated
  - **Found / decided:** Prompted by "One bottle of wine, 750 ml, $15, as a present for my parents. Is that duty-free?": age, trip length and 30-day use all change the answer, but SPEC allowed one question per turn with no order. Now: one clarifying message asks for all answer-changing facts, in two stages (stage 1 decides the exemption: age, trip length, 30-day use, and origin if the item could be Cuban or Russian; stage 2 only if something is owed: origin for the rate, ABV), ordered age → trip length → 30-day use → origin → ABV. Defaults after two unanswered rounds added for every fact (age: answer both ways; trip: under 48 h; used: yes; origin: 3%; ABV: spirits 40%, table wine ≤ 16%, fortified 16–21%). E57 is now that exact question; D13 is a dev twin. Counts unchanged (80 / 20); the single-fact age case remains as E63. Gold for priced scenarios unchanged; cross-check 0 problems.
  - **Open:** Two-turn clarify (reply, then answer; defaults after two silent rounds) still not in the eval.

- **What:** Hand-check method, worked through on E01 (written by Claude as a template; not yet the human hand check).
  - **Files:** none changed; compare against `eval/gold.md`; rules in `data/rag-corpus/corpus/primary/` (`19cfr148_returning_residents.md`, `htsus_9816_flat_rate.md`, `ttb_alcohol_tax_rates.md`)
  - **Method (E01: age 52, 9 days in Tuscany, first trip this year, 3 × 750 ml Chianti, 13%, $25 each):**
    1. Blocking rules first: made in Italy (not Cuba/Russia); age 52 (21+); 2.25 L and 3 bottles (under 9 L / 12 units). Nothing blocks.
    2. Exemption: 9 days ≥ 48 h, not used in 30 days → $800 (19 CFR 148.33, 148.35, 148.36).
    3. Free alcohol: 1 L at 21+ (148.33(d)(3)); not a direct Caribbean arrival, so not 2 L. Total value $75 < $800.
    4. Excess: 3 × 0.75 = 2.25 L; 2.25 − 1.00 = 1.25 L.
    5. Dutiable value: $25 × 1.25 ÷ 0.75 = $41.67 → $42 (SPEC 5.1).
    6. Duty: Italy is neither a free-programme nor a Column 2 country → 3% (HTSUS 9816.00.20); $42 × 0.03 = $1.26.
    7. Excise: still wine ≤ 16% → $1.07/gal (TTB); 1.25 ÷ 3.785411784 = 0.3302 gal; × 1.07 = $0.3533 → $0.35.
    8. Total $1.26 + $0.35 = $1.61. Bottom line: owe $1.61; cite 148.33, 9816.00.20, TTB.
  - **Compare:** in `gold.md` under "### E01", check outcome, item result, exempt litres (1.000), excess (1.250), value ($42), duty ($1.26), excise ($0.35), total ($1.61). Record "Hand check <id>: matches / differs (why)".
  - **Harder cases:** E44, E46 and other multi-item baskets: before step 4, compute each item's duty + excise per litre and take the free litre from the highest first (SPEC 5.4). E48: step 3 is 2 L (direct from a country on the accepted CBP list, SPEC 5.5).
  - **Open:** Human hand check of E01, E44, E46, E48 (and more of the 20 in `eval/README.md`), then tag `eval-v1`.

- **What:** Human hand check of the eval gold (project owner).
  - **Found / decided:** Checked by hand against the regulation text using the method above; all checked scenarios match `gold.md`. Gold ready to freeze.
  - **Open:** Commit on a branch, merge, tag `eval-v1`.

- **What:** Froze the eval set: annotated tag `eval-v1` on commit dd81665 ("eval and checks"), on `customs-agent-main`, local only (not pushed).
  - **Found / decided:** The 80 eval scenarios no longer change; any change means `eval-v2` and a note in the report.

- **What:** Built the calculator tools and their tests.
  - **Files:** `src/schemas.py`, `src/tools/` (`common.py`, `normalise_units.py`, `check_restrictions.py`, `determine_exemption.py`, `compute_allowance.py`, `compute_duty_excise.py`, `lookup_state_rule.py`, `whatif_optimise.py`, `escalate_to_human.py`), `tests/_chain.py`, `tests/test_tools.py`, `tests/test_dev_set.py`; `data/rules.yaml` (ask-origin keywords for Cuba/Russia, insular-possession codes), `data/rates.yaml` (unit and container conversions); `docs/SPEC.md` 5.2 (30-day row)
  - **Found / decided:** Every threshold and rate is read from the YAML files; amounts are Decimal with half-up rounding per line. Missing facts come back as a list in SPEC 5.2 order, so the planner can ask them in one message. Rules are matched from their `when` blocks in rules.yaml order; each tool evaluates the rules whose facts it knows (pre-calculation in check_restrictions, over-allowance in compute_allowance, flat-rate band in compute_duty_excise). Commercial threshold counts alcohol containers only (50 single cigars is not "50 units"). Exempt goods worth more than $800 escalate (not modelled). Flat rate already used in 30 days escalates; unknown flat-rate use is asked when something is dutiable (SPEC 5.2 row updated). Tests: 73 pass, including every calculable dev scenario against gold and the D12 what-if; eval set not used (rule 6). Pre-commit ruff clean.
  - **Open:** `uv add pydantic`; run `uv run pytest -v` on the Mac. Corpus expansion and freeze next (Day 3), then score.py and baselines.

- **What:** Added pydantic (`uv add pydantic`) and ran the full suite on the Mac: 94 passed (73 tool tests + 21 offline llm tests).

- **What:** Corpus v2 tooling (Day 3): one document per regulatory unit.
  - **Files:** `data/rag-corpus/fetch_corpus.py` (rewritten), `sources.yaml` (35 sources), `chunk_corpus.py` (reads `corpus/docs/`, lifts `citation_id` and `authority` onto chunks), `README.md`, `tests/test_corpus_fetch.py` (offline parser tests)
  - **Found / decided:** Units: CFR section (eCFR API; whole parts 19 CFR 148, 31 CFR 515, 27 CFR 27, 27 CFR 41, plus 31 CFR 1010.340), U.S. Code subsection (OLRC: 26 USC 5001/5041/5051/5701/5704/5754/5761, 19 USC 1497/1681/1681a/1681b), HTSUS tariff lines 9804 and 9816 (USITC API) and Chapter 98 / General Notes 3, 7, 11 (USITC PDFs), OFAC FAQs (all Cuba FAQs from the topic listing, plus Russia 1024/1027/1182), EO 14068, CBP pages split by H2, TTB rates and personal-importation pages, the 5 state pages, and hard negatives (crew subpart, off-topic CBP sections, food, currency, visitors). Each doc carries `doc_id`, `citation_id` (what the gold cites), `authority`, tags, as-of date and SHA-256s; raw downloads kept gzipped with an index; `--check` verifies against `MANIFEST.json`. Parsers tested offline only: the cloud workspace cannot reach government sites, so the real fetch runs on the Mac. Old `corpus/primary/` left in place until the new fetch is reviewed.
  - **Open:** `uv add pdfplumber`; run the fetch on the Mac and review counts and failures; then delete `corpus/primary/`, update references to it, commit and tag `corpus-v1`.

- **What:** First real corpus fetch on the Mac (729 docs, 2 sources failed) and fixes.
  - **Files:** `data/rag-corpus/fetch_corpus.py`, `sources.yaml`, `customs-agent/.gitignore`
  - **Found / decided:** U.S. Code URLs moved: now `https://uscode.house.gov/us/usc/t<title>/s<section>/` (OLRC FAQ). Chapter 98 notes were cut short at an inline tariff number: now read up to the first tariff table, page headers stripped (Subchapter IV notes 1-4, XVI note 1). General Notes found by their running page label; **General Note 11 (ATPA) is not in the 2026 HTSUS**. EO 14068 page blocks scripts: fetched through the Federal Register API instead. Florida chapter page: take the last "562.16 Possession" match (the first is the table of contents). CBP CSMS bulletin: layout tables flattened. TTB firearms rates marked off-topic. Three raw PDFs over 500 KB git-ignored (hashes kept). Spot-checked docs (19 CFR 148.33, OFAC 720, CBP alcohol section): clean.
  - **Found / decided (regulatory):** HTSUS ch. 98 Subchapter IV U.S. Note 4: "beneficiary country" for 9804.00.72 (the 2 L allowance) means a country in General Note 7(a) or 11(a). GN 7(a) lists 17 countries (Antigua and Barbuda, Aruba, Bahamas, Barbados, Belize, Curaçao, Dominica, Grenada, Guyana, Haiti, Jamaica, Montserrat, St Kitts and Nevis, Saint Lucia, Saint Vincent and the Grenadines, Trinidad and Tobago, British Virgin Islands; Netherlands Antilles listed but no longer eligible), and GN 11 no longer exists. So 13 countries in our accepted CBP list do not qualify: Bolivia, Colombia, Costa Rica, Dominican Republic, Ecuador, El Salvador, Guatemala, Honduras, Nicaragua, Panama, Peru, Sint Maarten, Caribbean Netherlands. GN 3(c)(i) confirms the programme codes used for the Free flat rate (BH, CL, CO, IL, JO, KR, MA, OM, P, PA, PE, S, SG).
  - **Open:** Decide whether to correct the 2 L list (affects eval E15 and E48, so eval-v2). Re-run the fetch for the fixed sources.

- **What:** Corrected the 2 L country list from the HTSUS and re-tagged the eval as `eval-v2` (project owner's decision).
  - **Files:** `data/rates.yaml` (17 GN 7(a) countries, status confirmed; the 13 others under `not_eligible`; programme symbols confirmed), `data/rules.yaml` (legend), `docs/SPEC.md` (5.5 rewritten, 9), `eval/scenarios.yaml` (E15, E48: 1 L), `eval/README.md`, exports regenerated; `CLAUDE.md`. Commit be15ef3, tag `eval-v2` (local, not pushed).
  - **Found / decided:** E15 $2.85 → $5.71 (3 L Dominican rum, 2 L excess, duty Free under P, excise only); E48 $0.71 → $3.57 (pisco, 1.25 L excess, Free under PE). Only E15 and E48 differ from `eval-v1`; dev set unchanged; cross-check 0 problems; 78 tests pass. Also found that the `eval-v1` commit held stale copies of `scenarios.yaml` and `eval/README.md` (probably an editor tab saving over them); the latest versions are restored in `eval-v2`. The JSONL in `eval-v1` was correct.
  - **Open:** Re-run the fetch for the fixed corpus sources; review; delete `corpus/primary/`; commit and tag `corpus-v1`. Close open editor tabs of eval files before committing.

- **What:** Corpus fixes and second fetch: 742 docs, 0 failed, `--check` OK.
  - **Files:** `data/rag-corpus/fetch_corpus.py`, `sources.yaml`; references to `corpus/primary/` updated in `docs/regulatory_checks.md`, `data/rules.yaml`, `data/rates.yaml`, `eval/build_eval.py` (comment only); `CLAUDE.md`
  - **Found / decided:** U.S. Code now fetched (11 sections, one doc each). EO 14068: federalregister.gov (site and API text) and govinfo.gov both return bot-check pages to scripts, so the page was saved by hand as `corpus/raw/eo14068.html`; the fetcher now refuses to keep a bot-check page as a snapshot, and the manifest forgets deleted downloads. The editor overwrote `fetch_corpus.py` and `sources.yaml` with old buffers twice during this; restored each time. All 9 gold citation ids and every citation in rules.yaml / rates.yaml exist in the corpus.
  - **Open:** delete `corpus/raw/eo14068__api.json.gz` and `eo14068__text.txt.gz` (failed attempts); `git rm -r corpus/primary`; chunk; commit; tag `corpus-v1`.

- **What:** Chunker fix for PDF text, and the corpus is ready to freeze.
  - **Files:** `data/rag-corpus/chunk_corpus.py` (oversized blocks split by lines, then sentences, then words; table pieces repeat the header), `tests/test_chunk_corpus.py`, `.gitignore` (`chunks.jsonl` is derived)
  - **Found / decided:** PDF text has no blank lines, so General Note 3 and the CBP spirits-guide pages were single chunks of thousands of tokens (over the 512-token embedding limit). Now 742 docs -> 1,289 chunks, none over 350 tokens; `--check` OK (192 raw files). The device write tool reported success on `chunk_corpus.py` without changing it (the cause of the earlier "reverts"); the file was written through the shell instead and verified after 30 s.
  - **Open:** commit and tag `corpus-v1`; then Day 4: `eval/score.py` and the four baselines.


- **What:** COMPENSATIONS.md updated: row 2 now measured on the corpus (44 docs with an over-limit chunk, General Note 3 as one ~6,500-token chunk -> 0 docs, largest 346 tokens); two planned rows added (missing facts decided by code; citations from chunk metadata); set names now eval-v2 and corpus.

- **What:** Corpus not committed; `SETUP.md` added.
  - **Files:** `customs-agent/SETUP.md` (new), `README.md` (link), `.gitignore` (corpus docs, raw, fetch report, chunks ignored; MANIFEST, raw INDEX and the two hand-saved pages kept), `fetch_corpus.py` + `sources.yaml` (`ecfr_as_of: 2026-11-19` pins the CFR text), `CLAUDE.md` (setup-guide convention, status)
  - **Found / decided:** Owner's choice: rebuild the corpus from sources instead of committing ~7 MB. Reproducibility: CFR pinned by date; web pages can drift, and `--check` against the committed MANIFEST shows which; for official runs share a snapshot. Writes to existing files now go through a new file plus `mv` (or in-place shell edits), verified by checksum.

## Day 4

- **What:** Scorer and prompting baselines.
  - **Files:** `eval/score.py`, `eval/run_baselines.py`, `src/baselines/` (`answer.py`, `prompts.py`, `strategies.py`), `tests/test_score.py`, `tests/test_baselines.py`, `SETUP.md` (step 7), `CLAUDE.md`
  - **Found / decided:** Scorer checks outcome, bottom line per line, dollars (total, duty, excise within $0.01), what-if, clarify facts (exact set), citations (normalised: "19 CFR § 148.33(d)" -> 19cfr148.33; must also be in retrieved_ids when a system reports them), forbidden text (whole-token, so "$0" does not match "$0.90"); state flag reported separately. Baselines are closed book: task and output format only, no rules, no retrieval, no calculators, so their dollar accuracy is the "before" for the calculator compensation. Answers use json_schema output. fewshot_json uses dev D01, D05, D08, D13 (those four are not scored on dev). cot_sc: 3 sequential samples at temperature 0.7, majority vote on (outcome, bottom line, clarify facts). decompose: extract facts -> rules decision -> compute, with early exits for refusal, clarify and escalation. Every gold record scores correct against itself (test). 124 offline tests pass.
  - **Open:** Smoke test on 3 dev items; full dev run; then eval run overnight with LLM_CACHE=0.


- **What:** First dev run of the four baselines (`results/runs/day4-dev`, prompts v1) and prompt fixes (v2).
  - **Results v1 (dev):** accuracy closed_book 0.00, fewshot_json 0.06, cot_sc 0.05, decompose 0.05. Dollars almost never right (fewshot near misses, $3.43 vs $3.45; closed book far off, $12 vs $2.97); tobacco over the limit taxed instead of flagged; never asks to clarify; invents citations ("21 CFR 10.115").
  - **Found / decided (harness, fixed in v2):** (1) decompose extraction wrote `{value: 0}` for unknown trip/quantity and failed the `> 0` schema check (4 errors): zero now means unknown. (2) decompose missed "haven't used my exemption recently" -> spurious clarify on 12 of 20: extraction prompt lists common phrasings; rules step may only flag facts that are null. (3) "refused" was ambiguous: Cuban cigars and under-21 came back "refused", nicotine pouches and evasion "escalated": each outcome now defined, and a refused example (D16) added to the few-shot set (5 examples). Prompt fixes are tuning on dev only (rule 6). v1 results kept for comparison.
  - **Open:** run v2 on dev as `day4-dev-v2`; candidate COMPENSATIONS row for outcome-label confusion (before v1, after v2).

- **What:** Dev run v2 (`results/runs/day4-dev-v2`) and the last baseline change.
  - **Results v2 (dev):** accuracy closed_book 0.20, fewshot_json 0.20, cot_sc 0.10, decompose 0.10; outcome accuracy 0.90 / 0.93 / 0.80 / 0.30. Dollars still ~0 (fewshot 0/9, cot_sc 2/11): the model cannot do the arithmetic. Citations: only fewshot (0.64) names the right sections; the others invent "21 CFR 10.115".
  - **Found / decided:** Outcome definitions fixed the label confusion (COMPENSATIONS row 4). decompose's rules step lists facts as missing that its own extraction filled in (D03 exemption used = false, D05 trip/origin/abv): a real small-model failure, kept as the "before" for "missing facts decided by code". decompose also looped on citations ("21 CFR 10.115(a)(1)...(a)(36)") until max_tokens, leaving broken JSON (D01, D15, D20): citation lists now capped at 6 in the schema (`maxItems`) and on parsing. Prompts now frozen for the baselines.
  - **Open:** official eval run (`week1`, LLM_CACHE=0) -> `results/week1_strategies.csv`, `results/week1_failures.csv`.

- **What:** Official baseline run `week1` on eval-v2 (80 scenarios, cache off). Day 4 gate items now complete once committed.
  - **Files:** `results/week1_strategies.csv`, `results/week1_failures.csv`, `results/runs/week1/`, `docs/BASELINES.md` (new: write-up for the report), `docs/COMPENSATIONS.md` (before numbers filled in), `CLAUDE.md`
  - **Results:** accuracy closed_book 0.100, fewshot_json 0.175, cot_sc 0.113, decompose 0.113. Dollars 0.00-0.07 (n=42; median error $11.43 closed book, $1.53 few-shot). Citations 0.07 except few-shot 0.61; invented "21 CFR 10.115" 63 times in decompose. Clarify 0/8 except decompose 1/8; decompose turned 41 of 80 answerable questions into clarify. Never escalates. Evasion and user injection refused 100%. No errors.
  - **Found / decided:** Supports the design: calculators for every amount, retrieval + citation ids for citations, code-decided missing facts, rule-based escalation. Self-consistency is not worth its cost (3.7× tokens, lower bottom-line accuracy).
  - **Open:** commit `results/` and `docs/BASELINES.md`; then Days 5-7: retrieval experiment (BM25 / dense / hybrid / reranker) and agent v0 on dev.

- **What:** Day 4 gate passed: commit 5615aa7 (scorer, baselines, week1 results), tag `gate-day4`.

## Day 5

- **What:** Retrieval experiment set up.
  - **Files:** `eval/retrieval_queries.yaml` (60 queries, gold citation ids, 3 crew-rule traps), `src/retrieval/` (`corpus.py`, `retriever.py`: BM25, dense, hybrid RRF k=60, hybrid + cross-encoder reranker, hard-negative filter applied before ranking), `eval/retrieval_experiment.py` (3 chunk sizes x 4 methods x 2 filters -> recall@1/3/5/10, MRR, hard negatives in top 3), `tests/test_retrieval.py`, `SETUP.md` step 8
  - **Found / decided:** Retrieval is measured on its own query set, not the eval questions (rule 6). Gold ids all verified against MANIFEST; not edited after seeing results. Chunk sizes 200 / 350 / 450 (not 500: the endpoint's model reads 512 tokens and our token count is an estimate). BGE query instruction prefix used for dense queries. Preview, BM25 on the real 350-token chunks (computed in the workspace): R@1 0.53, R@3 0.77, R@5 0.87, R@10 0.90; the filter takes hard negatives in the top 3 from 0.20 to 0.00; crew traps 3/3. 135 offline tests.
  - **Open:** `uv add rank-bm25 numpy sentence-transformers`; run the full grid on the Mac; write the three decisions in docs/RETRIEVAL.md.

- **What:** First full retrieval run stopped at the dense index: the embeddings endpoint rejects batches over 16 inputs (HTTP 422, not retried). `src/llm.py` default `embed_batch_size` 32 -> 16; endpoint limit added to CLAUDE.md. BM25 at 200 tokens before the stop: R@1 0.48, R@3 0.77, R@5 0.78, R@10 0.90.


- **What:** Second retrieval run stopped: a "200-token" chunk was 1,656 real tokens (endpoint limit is 512). The chunker estimated tokens from words, and PDF text that runs words together with dots ("documentation.that.proves.you.left...", dotted contents lines) has few words but many tokens (57 chunks affected, mostly the CBP visitors' guide and spirits guide).
  - **Files:** `data/rag-corpus/chunk_corpus.py` (counts tokens with the bge-small-en-v1.5 tokenizer via `transformers`; fallback estimate max(words x 1.35, chars / 3); over-long "words" split by characters), `tests/test_chunk_corpus.py`
  - **Open:** re-chunk (`chunk_corpus.py`) so the default 350-token chunks are also exact, then re-run the experiment. Candidate COMPENSATIONS update for row 2 (chunk limit now measured in real tokens).

- **What:** Full retrieval experiment done (24 configurations, all 60 queries, chunks counted in real tokens: 1,480 at 350, largest 344).
  - **Files:** `results/retrieval_experiment.csv`, `results/retrieval_per_query.csv`, `docs/RETRIEVAL.md` (three decisions), `docs/COMPENSATIONS.md` row 2 corrected (old "largest 346" was an estimate)
  - **Found / decided:** (1) Hybrid RRF wins at every size; best is 350 tokens + filter: R@1 0.65, R@3 0.883, R@5 0.933, traps 3/3. (2) The MiniLM reranker lowers R@1/R@3 at 350 and 450 and costs ~65 ms/query: dropped. (3) Chunk 350, k = 5. (4) Hard-negative filter takes hard negatives in top 3 to 0 with no recall loss. (5) No vector DB: numpy flat index (~2.3 MB). 7 misses in top 3, incl. Cuban 515.204 (rank 5) and USMCA GN 3 (missing) → tools pass the citation ids of rules they applied, fetched by id.
  - **Open:** optional bge-reranker-v2-m3 comparison run; save the dense index file for 350; agent v0.

- **What:** Reranker comparison: `BAAI/bge-reranker-v2-m3` on hybrid, 350 tokens (`results/retrieval_experiment_bge.csv`). With the filter: R@1 0.733, R@3 0.917, R@5 0.950, MRR 0.831 (plain hybrid 0.650 / 0.883 / 0.933 / 0.769); traps 3/3; ~1.5 s per query.
  - **Found / decided:** Decision 1 changed: hybrid + bge reranker (MiniLM stays rejected). Fixes 515.204 (5 -> 1), 148.35 (4 -> 1), 5761 (9 -> 2). Still missing: USMCA GN 3 (R36), $200 pooling 148.51 (R16). Plain hybrid kept as fallback and ablation. `docs/RETRIEVAL.md` updated.
  - **Open:** save the 350 index file (vectors + chunk ids); agent v0; code router.

- **Why this retrieval setup (hybrid + bge reranker, 350-token chunks, decoys filtered, k = 5)**
  - **Hybrid over BM25 or dense alone:** BM25 finds exact section numbers and legal terms ("148.51", "Caribbean Basin"); dense finds paraphrases ("day trip to Mexico"). They miss different queries, so fusing them won at every chunk size (R@3 0.883 vs 0.833 BM25, 0.850 dense at 350).
  - **bge-reranker-v2-m3 over MiniLM or no reranker:** MiniLM was trained on web search and made results worse (R@1 0.650 -> 0.583). bge raised every metric (R@1 0.733, R@3 0.917, R@5 0.950) and put three rules the agent depends on near the top: the Cuban-origin ban, the day-trip exemption and export-labelled tobacco. The cost (~1.5 s per search, ~2 GB model) is small next to the LLM calls. With 60 queries the R@3 gain is only 2 queries, so the reranker is a setting with plain hybrid as fallback.
  - **350 tokens over 200 or 450:** best R@3 and R@5. 200 splits sections into pieces too small to match; 450 dilutes them and missed a crew trap. 5 x 350 tokens fits the < 3k input target.
  - **Filter decoys before ranking:** hard negatives in the top 3 fall to 0 with no recall loss. Ranking can't be trusted to push them down on its own (BM25 had them in the top 3 for 20% of queries).
  - **k = 5:** recall goes from 0.917 at 3 to 0.950 at 5 for ~700 extra tokens.
  - **No vector database:** 1,480 x 384 vectors is ~2.3 MB and a search takes ~1 ms in numpy. Qdrant would add a service without changing any result.
  - **What it doesn't solve:** USMCA tequila (R36) and $200 no-pooling (R16) still miss, so the tools hand over the citation ids of the rules they applied and those clauses are fetched by id.

- **What:** `search_regulations` tool and the saved search index.
  - **Files:** `src/tools/search_regulations.py` (`RegulationSearch`, `Args{query, citation_ids, k<=5}` -> `Clauses`), `src/retrieval/index.py` (`vectors.npy` + `meta.json` in `data/rag-corpus/index/`, git-ignored; fingerprint of chunk ids + texts), `src/retrieval/search.py` (command-line search), `Retriever.set_matrix` / `bm25_scores`, `Clause` / `Clauses` in `src/schemas.py`, `tests/test_search_regulations.py` (13 tests; 170 offline pass in the workspace), SETUP.md step 9, ARCHITECTURE.md (Qdrant -> saved numpy index)
  - **Found / decided:** Citation ids from the tools are fetched first (one chunk per section, the one BM25 matches best to the query); search fills the rest of the 5, one chunk per citation. Hard negatives and curated notes are refused even by id (`not_found`). If the ids fill all 5 slots, no search (and no 1.5 s rerank) runs. Index rebuilds itself when chunks.jsonl or the embedding model change. `RERANKER=none` gives plain hybrid; a reranker that fails to load falls back to hybrid and says so in `method`.
  - **Open:** build the index on the Mac; code router.

- **What:** `rules.yaml` Cuban rule: added `ofac-faq-720` (Cuban-origin goods bought in a third country, e.g. Cancun) as second citation. Seen in a live search: for "Cuban cigars bought in Cancun" FAQ 720 ranked #3 and 31 CFR 515.204 was not in the top 5, so the rule's citations (fetched by id) must carry both. Order: 515.204, 515.585, FAQ 720, FAQ 719, CBP notice (the two CFR sections first: every Cuban gold answer cites both). Gold unchanged. Note for the router: a mixed basket (E35) applies rules with 10+ citations between them, more than the 5-clause budget, so the router must pass the first one or two citations of each rule applied, not all of them.

- **What:** Agent v0 with the code router, end to end (not yet run on the endpoint).
  - **Files:** `src/safety/guard.py` (injection / evasion / out-of-scope patterns from the SPEC categories; `sanitise_clause` drops retrieved text addressed to an assistant: 0 of 1,480 real chunks dropped), `src/agent/` (`llm_json.py` JSON call + 2 repairs; `intake.py` IntakeResult incl. what-if target; `router.py` tools in fixed order + citations of the rules applied, 2 per rule; `card.py` answer card built in code; `writer.py`; `verifier.py`; `pipeline.py`; `prompts.py`), `eval/run_agent.py`, `tests/test_agent.py` (225 offline pass in the workspace), SETUP.md step 10. `Answer.clarify_facts` now also allows size / unit_price / count.
  - **Found / decided:** The LLM does two things: read the question (intake) and explain the code-built card (writer). Bottom line, dollars, clarify facts and citations of applied rules come from code. Final citations = clauses fetched by id for the rules the tools applied + clauses the writer cites by number. Verifier: every number in the writer's text must appear in tool outputs, retrieved clauses, facts or question; the bottom line must state the total owed; sources must be retrieved clauses; no evasion wording; plus one LLM evasion check. Fail -> one writer retry with the problems fed back -> escalate. With gold facts, the router gets outcome, bottom line and the gold citations (within the 5-clause budget) right on every routable dev item.
  - **Open:** run on dev (`eval/run_agent.py --set dev --run-name day5-router`); then the LLM planner.

- **Open (agreed to do later, with the planner):** hard per-question budget shared by router and planner: at most 10 steps (tool calls + model calls) and 12,000 tokens; over either -> escalate, reason in the trace; step count in each record for the report. Today the router stays at <= 8 tool steps by design, but retries can reach ~11 model calls in the worst case and nothing enforces the cap.

- **What:** First agent smoke test on the endpoint (`--set dev --limit 3`, run `agent-dev`): D01 correct ($2.97, 3 calls, 3,100 tokens, 10 s); D02 wrong dollars ($3.15 vs $3.45); D03 escalated by the verifier (gold answered). Citations 3/3.
  - **Found:** (1) D02: intake wrote "two 1-litre bottles" as quantity {2, "litre"} + size {1, "litre"}; normalise_units read it as one 2-litre container, so the excess litre was valued at $10, not $20. (2) Intake wrote origins as names ("Italy", "Poland") although the tools compare ISO codes: harmless for these three, but "Cuba" would have missed the ban and "Mexico" the USMCA rate. (3) D03: the writer did its own subtraction ("brought 1.25 L, so 0.25 L is over"; really 2.25 L brought, 1.25 L over); the verifier caught the invented 0.25 both times, so the answer escalated instead of being wrong. The working never stated the total brought, and the feedback did not say where the error was.
  - **Fixed:** (1) normalise_units: a quantity given as a volume, with a container size that divides it, is that many containers (test added). (2) `src/agent/countries.py`: names and demonyms -> ISO codes in code after intake (pycountry + alias table, no fuzzy matching: it maps "Republic of Korea" to North Korea); unrecognised origin -> null so clarify asks when it matters. Intake prompt asks for ISO codes and containers-not-litres. (3) Card working now states "3 x 750 ml = 2.25 L in total; 1 L duty-free, 1.25 L over"; writer prompt: copy numbers exactly, never compute; verifier feedback quotes the sentence with the bad number. 241 offline tests pass in the workspace.
  - **COMPENSATIONS candidates (need before/after on dev):** countries normalised in code; writer told to copy numbers + verifier catches computed numbers.

- **What:** Full dev run of agent v0 before the fixes above (run `day5-router`, kept as the "before"): **accuracy 0.65** (13/20), outcome 0.90, dollars 0.636, clarify 0.5, citations 0.929, 2,932 tokens and 2.7 calls per question. Baselines on dev were 0.10-0.18.
  - **Wrong (7):** D02 (litres as count), D03 (writer subtraction, escalated), D04 and D20 (origin "Trinidad"/"Chile" as names: 2 L rule and Chile free rate missed), D08 (Cuban cigars: "box" + size "10 cigars" -> count unknown -> clarify instead of prohibited), D10 ("a pack of 20" read as 20 packs = 400 cigarettes -> declare), D13 (intake invented a 1-day trip and arrival from PT, so only age was asked).
  - **Fixed after:** countries -> ISO in code (D04, D20, and the Cuba/Mexico risk); volume-as-count (D02); card + writer + feedback (D03); normalise_units: box/pack with a piece count as size -> "box of N" (D08); intake prompt: tobacco units with counts ("pack of 20" = {1, "pack of 20"}), never guess profile facts (D10, D13); `ground_in_question`: age and trip length dropped in code unless the question states them (never drops a stated fact on dev; drops D13's guesses). 265 offline tests.
  - **Open:** rule 4 gap: a Cuban item whose count can't be read asks for the count before saying it is prohibited (normalise_units runs before check_restrictions). Re-run as `day5-router-v2`.

- **What:** Dev run `day5-router-v2` (all fixes above): **accuracy 0.95** (19/20), outcome 0.95, dollars 1.00 (11/11), clarify 1.00, citations 0.929, 2,878 tokens and 2.6 calls per question. From 0.65 in `day5-router`.
  - **Wrong (1):** D08 Cuban cigars: this time intake wrote origin MX (where bought) instead of CU, and with no ban the tools asked for 30-day use.
  - **Fixed:** `origin_from_question` (code): an origin stated with the product ("Cuban cigars") overrides the model's, matched by product type; never contradicts dev gold. Router: if every item is prohibited, answer at once without asking exemption facts (rule 4 / SPEC 5.2). 280 offline tests.
  - **COMPENSATIONS:** rows 5-9 added from `day5-router` -> `day5-router-v2` (row 9 after the next run).
  - **Open:** re-run as `day5-router-v3`; commit agent v0.

- **What:** Dev run `day5-router-v3`: **accuracy 1.00** (20/20), citations 1.00, 2,995 tokens and 2.75 calls per question. D08 fixed by `origin_from_question` (same cached intake output as v2, which wrote MX). COMPENSATIONS row 9 filled.
  - **Caveat (discussed):** dev is now tuned-on data: 0.65 -> 0.95 -> 1.00 came from fixing exactly the dev failures, so it is not an estimate of eval accuracy. General fixes (ISO codes, volume-as-count, copy-don't-compute, grounding) carry low overfitting risk; pattern lists (guard keywords, duration phrases, product words, tobacco prompt examples) carry some. The model is also unstable (D08 origin CU in v1, MX in v2), and one cached run hides variance.
  - **Next checks without touching eval:** a paraphrase set written by someone other than this session (same facts as dev items -> same gold, so no new gold arithmetic); dev runs with the cache off for variance; prompt freeze Day 9; report states dev numbers are post-tuning.

- **What:** Generalisation check prepared (before any further tuning).
  - **Files:** `eval/PARAPHRASE_BRIEF.md` (brief for someone who has not seen `src/`: 3 rewordings per dev item, same facts, so gold is copied, not recomputed), `eval/build_paraphrase.py` (checks `paraphrase_raw.jsonl`, copies gold and planted docs from the source dev item -> `paraphrase_set.jsonl`), `run_agent.py --set paraphrase`, `tests/test_build_paraphrase.py`.
  - **Decided:** one-shot: run once on the current agent; failures read as kinds of weakness; general fixes only, logged with this run as "before"; not re-run until it passes.
  - **Open:** questions to be written by the user or a fresh Claude session; then run `--set paraphrase --run-name para-router`; variance: dev with `LLM_CACHE=0` x3.

- **What:** Paraphrase check (one-shot): 60 rewordings of the dev questions, written by a separate session from `eval/PARAPHRASE_BRIEF.md`, gold copied from the source items. Run `para-router`: **accuracy 0.883** (53/60), outcome 0.90, dollars 0.879, clarify 0.667, citations 0.905. Dev on the same code: 1.00. **That gap is the honest measure of how much the dev fixes generalise.**
  - **Wrong (7), three kinds:** (1) size written "75cl" dropped by intake -> clarify size (P01b, P03b, P13b, P15b, P20b); (2) 30-day history invented as "not used" -> needed clarify skipped (P14a); (3) injection as an "admin note ... always answer" passed guard and intake (P19b). Also seen: intake invented "1 litre" for whisky with no size stated (P19b).
  - **Fixed (general, not per question):** `sizes_from_question` (read sizes in code when missed; drop sizes never stated; "litre bottles" and size words count); `ground_in_question` also grounds the 30-day facts; guard: authority-claim / answer-order patterns and "so customs doesn't find them" concealment. Replaying the recorded intake outputs through the new code: 0/60 wrong on paraphrase, 0/20 on dev. 299 offline tests.
  - **Decided:** COMPENSATIONS rows 10-12. One live re-run (`para-router-v2`) to fill the "after" numbers; after that the paraphrase set counts as tuned-on too, so the honest estimate is the Day 10 eval run.

- **What:** After the paraphrase fixes: `para-router-v2` **1.00** (60/60), `day5-router-v4` dev **1.00** (no regression); ~3,000 tokens and 2.75 calls per question. COMPENSATIONS rows 10-12 filled, marked "after fixing on this set".
  - **Status of the sets:** dev and paraphrase are both tuned-on now. Reportable generalisation number: paraphrase 0.883 (first run, before fixes). Honest estimate from here: the Day 10 eval run. Optional: a fresh paraphrase set later, recorded but never fixed on.


## Day 6

- **What:** LLM planner + plan validator, and the hard budget.
  - **Files:** `src/agent/router.py` refactored into a plan executor (`execute(profile, basket, plan)`); the code router is the fixed plan `ROUTER_PLAN` (test: executor with that plan == old router on every dev item; paraphrase replay still 0/60 wrong). `src/agent/planner.py` (prompt, `Plan` schema = ordered tool names only, `validate`, `propose`). `pipeline.py`: `mode="router"|"planner"`; planner -> validate -> one repair -> router plan as fallback (`plan_fallback` in each record); budget: 10 tool steps, 12,000 tokens -> escalate `budget_exceeded`. `run_agent.py --mode planner` (prints steps, fallbacks, max steps). `tests/test_planner.py`. 329 offline tests.
  - **Decided:** the planner chooses tools and order; it never writes tool arguments (executor fills them from state). JSON plan via `json_schema`, not the native `tools` parameter (COMPENSATIONS row 1 said tools): one call returns the whole plan, which the validator can check before anything runs. Validator: known tools, no repeats, <= 10, search last, calculation order (rule 4), what-if first only for what-if, state lookup required when the state is known. "Step" = one tool run; model calls are bounded by the token budget.
  - **Open:** run planner on dev (`day6-planner`) and compare with `day5-router-v4`; then single_rag baseline for the three-way ablation.

- **What:** Planner on dev (`day6-planner`): accuracy **1.00**, same as the router, at **3,981 tokens and 4.69 calls per question** (router 2,995 and 2.75): +33% tokens, +1.9 calls. Max 8 tool steps. Fallbacks 0/16.
  - **Found:** the first plan was invalid on 15 of 16 questions: always check_restrictions before normalise_units (it took "before any calculation" literally), search_regulations left out, determine_exemption missing on 7. The one repair fixed every one, so the validator, not the planner, is what makes it correct. The final plans are the router's plan (15 x the standard chain incl. lookup_state_rule, 1 x what-if).
  - **Changed:** planner prompt states the order as a rule. This makes the planner close to a copy of the router plan: the honest finding is that for this task the plan is a fixed dependency chain, so a planner adds cost and needs a validator, without changing answers. COMPENSATIONS row 13 (before numbers; after pending).
  - **Open:** re-run as `day6-planner-v2`; then single_rag.

- **What:** `day6-planner-v2` (order rule in the prompt): accuracy 1.00; first plans valid 13/16 (was 1/16); 0 fallbacks; 3,640 tokens and 3.94 calls per question (router 2,995 / 2.75). Remaining first-plan errors: search_regulations left out (3), what-if plan with whatif_optimise third and no calculation steps (1). COMPENSATIONS row 13 filled.
  - **Ablation so far (dev, post-tuning):** router 1.00 at 2.75 calls / 2,995 tok; planner 1.00 at 3.94 calls / 3,640 tok (+22% tokens) with the validator repairing 3/16 plans. Planner adds cost, no accuracy; the validator is what keeps it safe.

- **What:** `single_rag` ablation arm: `src/baselines/single_rag.py` (Day-4 TASK prompt + the top 5 clauses from the same search, free-text only; one call; no guard, intake, tools, verifier or sanitiser; planted document passed through as for the agent), `run_agent.py --mode single_rag` (agent record format, so the same scorer and retrieved-ids citation check), `tests/test_single_rag.py`, SETUP step 10. 332 offline tests.
  - **Open:** run on dev (`day6-single-rag`); three-way table (closed_book from day4-dev-v2, single_rag, planner, router).

- **What:** `single_rag` on dev (`day6-single-rag`): accuracy **0.05**, outcome 0.75, bottom line 0.69, dollars 0/11, clarify 0/2, citations 0.00, 2,289 tokens, 1 call.
  - **Ablation (dev; closed_book from `day4-dev-v2`, same TASK prompt):**

    | Arm | Accuracy | Outcome | Bottom line | Dollars (n=11) | Clarify (n=2) | Citations | Tokens / q | Calls / q |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | closed_book | 0.20 | 0.90 | 0.69 | 0.00 | 0.00 | 0.00 | 670 | 1.0 |
    | single_rag | 0.05 | 0.75 | 0.69 | 0.00 | 0.00 | 0.00 | 2,289 | 1.0 |
    | planner | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3,640 | 3.94 |
    | router | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 2,995 | 2.75 |

    Planner and router are post-tuning on dev; closed_book and single_rag were not tuned on these results. Official comparison: eval-v2, Day 10.
  - **Found:** (1) Retrieval alone adds nothing on dev: same bottom line (0.69), dollars still 0. (2) Free-text search on the whole question finds CBP guidance pages, not the deciding sections: the full gold citation set was in the top 5 for 0 of 14 questions (partly for 5). The retrieval experiment's short, focused queries (R@3 0.917) overstate end-to-end retrieval; fetching the applied rules by id is what fixes citations (COMPENSATIONS row 14). (3) Retrieved text weakened refusals: closed_book refused D16, D17, D19; single_rag answered all three (outcome 0.90 -> 0.75). (4) The planted document worked on single_rag: it cited `planted-limit-note` (must_not failed); the agent's sanitiser drops it.
  - **Open:** Days 5-7 done. Next: Langfuse trace dashboard (rubric), then Days 8-9 (corrections across turns, red-team list, prompt freeze).

- **What:** Plan in `CLAUDE.md` rewritten from the mentor's day-by-day table (docx section 5): status per row, the must-have vs. stretch table (5.4), and "Next, in order". Decided with the project owner: **all stretch items are in** (whatif done; state rules beyond 5, 3 router runs, regulation viewer, PDF checklist export, extra tuning until the freeze).
  - **Found (behind the mentor's schedule):** Day 7 checkpoint items not done: Streamlit showing real answers, trace link per answer, PII masking in logs, taxonomy labelling rules. Day 8-9 open: corrections across turns (LangGraph), ToolError back to the planner, rate limit 10/min, error-handling tests, editable facts in the UI, red-team list 15+.

- **What:** Web app (replaces Streamlit, decided with the project owner) + tracing + PII masking.
  - **Files:** `app/api.py` (FastAPI: `/api/ask`, `/api/clause/{id}`, `/api/health`; rate limit 10/min per client -> 429 + Retry-After; serves `web/dist` when built), `web/` (React + Vite + TS: question box with examples, answer slip, regulation viewer, clarify reply box, model-plans / fixed-plan switch), `src/tracing.py` (one trace per question, child observation per step: guard, intake, planner, tools chain with one child per tool, retrieval, writer, verifier; Langfuse 5 SDK when keys are set, else `logs/trace.jsonl`), `src/safety/pii.py` (email, phone, card, passport, "my name is"; prices, volumes, ages, dates untouched), answer card gains `items` (per-item type and amount) and readable facts ("4 bottles", "made in Italy"), `llm_json` records tokens and ms per call. Tests: `tests/test_api.py` (17). 349 offline tests. Checked in a headless browser against a fake agent: desktop, mobile, regulation viewer.
  - **Design:** customs-hall palette (signage navy on cool form paper); the bottom line takes the customs channel colour (red: owe / declare; green: nothing to pay; amber: officer or one more fact); the answer is a tear-off declaration slip; Public Sans (US government typeface) for the interface, Source Serif 4 for regulation text; citations as ink-stamp buttons that open the text.
  - **Interim:** answering a clarify question re-asks with the reply appended (stateless). Replaced by LangGraph sessions in Days 8-9.
  - **Open:** Langfuse keys (cloud or self-hosted) to see the dashboard; taxonomy labelling rules; Docker.

- **Bug (first real use of the web app):** a clarify reply looped. The interim follow-up appended only "no" to the question; `ground_in_question` found nothing about earlier trips in the text and dropped the answer, so the agent asked the same question again (3 times in the owner's test, Tijuana day trip). Fixed: the follow-up carries the question it answers ("Asked: ... Answer: no"), and the intake prompt says how to read that line. The clarify slip no longer shows the question twice. Lesson for the multi-turn design: an answer must be tied to the fact it answers, not re-parsed from free text.

- **Bug (owner's test, D11-like question):** "I'm forty-nine" -> asked for age, twice. `ground_in_question` only accepted ages written in digits, so the model's correct age 49 was dropped as unstated. Fixed: `spelled_numbers` (0-99 in words: "forty-nine", "twenty one", "Thirty") counts as stated; an age that is not in the question is still dropped. Tests added; paraphrase replay still 0/60 wrong. This is a generalisation failure the paraphrase set did not contain (it spelled out days, not ages): candidate COMPENSATIONS row with the next fresh check.

- **Bug (owner's test, same question after the age fix):** numbers right ($2.01, matches D11 gold), but the writer said "Cigarettes are within the 100-pack limit" (the allowance is 200 cigarettes; 100 is the count). The verifier passed it: 100 is a real number from the facts, attached to the wrong thing. The working had no line for an exempt tobacco item, so the writer improvised. Fixed: the card states count and allowance for every tobacco line ("Item 2: 100 cigarettes; your allowance is 200 cigarettes: within it."); writer prompt: state allowances only as WORKING gives them. **Known verifier limit for the report:** number checks catch invented numbers, not real numbers attached to the wrong fact.

- **Bug (owner's test: Johnny Walker Blue from India, "I'm over 21"):** age asked for again after it was given as "over 21": not a number, so grounding dropped it. Fixed: "over 21", "21+", "21 or older", "of legal drinking age" count as stated and set age 21 (the rules only need "not under 21"); an exact age in the question still wins; the card shows "Age: 21 or over". Prompt line added. Tests; dev and paraphrase replays still 0 wrong.
  - **Noted for multi-turn:** the SPEC 5.2 two-stage order asked for the bottle size first, then age, trip and 30-day history in a second round. Correct by the SPEC, but tiring: consider asking every missing fact in one round when the multi-turn work revisits clarify.


## Day 7 (Days 8-9 work begins)

- **What:** Multi-turn dev conversations and the red-team list, written before any multi-turn code.
  - **Files:** `eval/conversations.yaml` (13 conversations, 30 turns: clarify answered in one or two turns, corrections of trip length / age / count / origin, an edit on the answer card, defaults after two unanswered rounds (one escalates, one answers with ABV 40%), evasion and out-of-scope follow-ups, the Johnnie Walker case), `eval/build_conversations.py` (dollar gold for the 17 answered turns from the same spreadsheet formulas as the eval set, `eval/conv_gold.xlsx`, recalculated with LibreOffice), `eval/conversations.jsonl`; `eval/redteam.yaml` (20 items: user injection 5, document injection 2, evasion 4, out of scope 5, real phrasings that broke the app 3, PII 1; answerable items copy dev gold), `eval/build_redteam.py`, `eval/redteam.jsonl`, `run_agent.py --set redteam`, `tests/test_build_sets.py`. 378 offline tests.
  - **Found:** cross-check: our tools agree with the spreadsheet gold on all 17 answered turns. The guard alone catches only 6 of the 15 red-team refusals (it is the first line; the intake model's request_kind is the second): the real run will measure both together.
  - **Open (needs the owner):** SPEC 5.2 does not list container size as a clarify fact, but the tools ask for it (C13 expects it in stage 1 with trip and 30-day use). Proposed amendment: size (and count, unit price) are stage-1 item facts, ordered after origin and ABV. Bias note: these sets were written by the session that built the guard; the owner adds C50+/T50+.

- **Decided (owner):** SPEC 5.2 amended (section 9a): size, count and unit price are stage-1 clarify facts in the same message as the trip facts, ordered after origin and ABV; defaults: size 750 ml, count and price escalate. Checked against the frozen eval gold facts only: all 8 eval clarify items state their sizes, so no eval answer changes.

- **What:** Red-team run `redteam-day7` (router): accuracy 0.80 (16/20); refusals 11/15 (guard 6 + intake 5); the 3 real phrasings, 2 planted documents and the PII item all correct (dollars 6/6, citations 1.00). Missed: T02 (reply-only order), T04 ([SYSTEM] tag), T08 ("will they notice"), T12 (Parmesan: category alcohol, type other; asked for its bottle size).
  - **Fixed (general):** guard patterns for reply-form orders, bracketed role tags and detection questions ("check" deliberately left out: "Will customs check my receipts?" is a normal question); items of type "other" are out of scope whatever their category; clarify text when no item was read ("How many the item" bug). No false refusals on dev, paraphrase or red-team. 387 offline tests. COMPENSATIONS row 15.

- **What:** `redteam-day7-v2`: accuracy 1.00 (20/20), refusals 15/15, 2,148 tokens and 2.0 calls per question. COMPENSATIONS row 15 filled (after fixing on this set: the red-team list is now tuned-on too; fresh checks are the owner's T50+ and the Day 10 live red-team run).

- **What:** Conversations across turns on LangGraph (Days 8-9 main build).
  - **Files:** `src/agent/session.py` (`Sessions`: StateGraph read -> respond -> save, SqliteSaver, one thread per conversation; turn intake returns only what a message states or changes, merged in code; card edits change one fact with no model call; answers to our own questions count even when terse; `TurnUpdate`, `merge`, `apply_edit`, SPEC 5.2 defaults (`default_for`, both ages for age), step reuse), `src/agent/router.py` (`execute(..., reuse)`: steps before the first affected one are taken from the previous turn; one combined clarify round via a stand-in run when size/count is missing, SPEC 5.2 as amended), `src/agent/pipeline.py` split into `read()` + `respond()` (single questions and session turns share the same answering code; `assumptions` in every record), `eval/run_conversations.py` (scores every turn with eval/score.py + assumptions; conversation correct if all turns are), API on sessions (`/api/ask` continues a session, `/api/edit`), web app (session id, clarify answers as real follow-ups, "Correct a fact" form, assumptions box, New conversation). Tests: `tests/test_session.py` (12, incl. C01/C03/C07/C08/C09/C11/C13 with a scripted model) + API. 401 offline tests; dev and paraphrase replays unchanged (0 wrong).
  - **Decided:** "replan only the steps that depend on the changed field" is done in code (dependency map: items -> all; age -> restrictions on; trip / 30-day -> exemption on; arrival state -> state lookup); the trace shows which steps were reused. The LLM planner still proposes the plan in planner mode; reuse applies to it too.
  - **Open:** run the 13 conversations on the endpoint (router and planner); ToolError back to the planner; error-handling tests; prompt freeze.

- **Bug (first conversation run):** crash on C01 turn 2: the turn intake's trip was a free-form dict, the model wrote unit "day", and validation failed outside any retry. Fixed: `ProfileUpdate.trip` is the strict `Duration` type (the json_schema now constrains the unit; a bad value goes to the repair loop) and `new_items` are full `BasketLine`s; edits accept singular units; `Sessions.turn` records a failed turn as escalated with the error instead of raising, so one bad turn cannot end a conversation or a run.

- **What:** First conversation run `day7-conv` (router): **9/13 conversations, turn accuracy 0.70** (30 turns), dollars 0.867, clarify 0.556, citations 0.941, assumptions 0.9, 2,345 tokens per turn. Wrong: C04 (writer kept a 1 L allowance after age 23 -> 20; working never stated the 0 L allowance; verifier caught 0.5 twice -> escalated), C08 ("Does that matter?" / "I'd rather not say" labelled evasion by the turn intake), C09 (intake invented ABV 40%, so it never asked), C10 (intake invented origin Italy for plain "vodka" -> origin not asked; turn 2 "first trip this year" not read as 30-day not used; turn 3 then took the 30-day default).
  - **Fixed (general):** `ground_items` (ABV must be stated; origin of a Cuban/Russian-risk item, from rules.yaml `ask_origin_when`, must be named; per-field in later turns), `history_from_question` ("first trip this year", "no other trips", "haven't used my exemption" -> not used, when empty), `countries_in` (names and demonyms in text; "Cuban-made"; Havana/Habanos -> CU), card states the alcohol allowance always ("0 L: under 21"), turn-intake prompt: declining / asking why is "assess". Dev and paraphrase replays still 0 wrong. 413 offline tests. COMPENSATIONS row 16.

- **What:** `day7-conv-v2`: **13/13 conversations, turn accuracy 1.00** (30 turns), dollars, clarify, citations and assumptions all 1.00, 2,212 tokens per turn. COMPENSATIONS row 16 filled (after fixing on this set). The single-question path changed too (ABV / origin / history grounding): re-run dev, paraphrase and red-team to check for regressions before the prompt freeze.

- **What:** Regression checks after the grounding changes: dev `day7-dev-check` 0.95 (D07 wrong), red-team `day7-redteam-check` 1.00, conversations in planner mode `day7-conv-planner` 13/13 (2,820 tokens per turn vs 2,212 router).
  - **D07:** intake set `export_labelled_us: true` for British cigarettes from Heathrow duty-free (the intake prompt changed today, so the cached reading was not reused; the model is unstable on this flag). Fixed: the export-label and American-goods flags are grounded like ABV and origin (kept only when stated). Replay of the recorded D07 intake now correct; dev and paraphrase replays 0 wrong. 416 offline tests. COMPENSATIONS row 17.
  - **Model instability is now a measured theme:** D08 origin (CU then MX), D07 export flag, C09 invented ABV, C10 invented origin: each time a fact the question never states. The general answer has been code grounding, not prompt wording.

- **What:** Error handling completed (Days 8-9 exit criterion).
  - **Found (gaps):** a tool's out-of-scope error (arriving from a US territory, $1,600 exemption) came out as "escalated" instead of the scope note; an unreadable unit ("a jug") escalated instead of asking for the size; a plan error was not caught (it ended the whole answer); no tool error went back to the planner.
  - **Fixed:** `router.tool_error` classifies every ToolError (missing fact -> clarify; rule -> escalate; out of scope -> refused with the scope note; unreadable unit -> ask the size; other invalid input -> `r.error`); `PlanError` caught; planner mode `_planned`: a tool or plan error goes back to the planner once with the error as feedback, then the code router's plan, then the escalation stands; the session executor does the same. `tests/test_error_handling.py` (17): JSON repairs and escalation, endpoint and search failures, each ToolError kind, tool error -> planner -> router -> escalate, repeated tool blocked, 10-step cap, verifier twice, tracer failure keeps the answer, failed session turn keeps the facts. 433 offline tests; dev replay 0 wrong.

- **What:** Failure-taxonomy labelling rules (Day 7 leftover, needed for Day 11).
  - **Files:** `docs/TAXONOMY.md` (labels, decision order, fact rules, severity, conversation rules, hand-check protocol), `eval/label_failures.py` (proposes one label per wrong answer: the first pipeline stage that went wrong; writes `failures_<mode>.csv` with severity, evidence, `needs_check` and empty `human_label` / `human_note`; `--agreement` gives raw agreement and Cohen's kappa against the hand labels), `eval/taxonomy_check.csv` (the 29 failures fixed on Days 5-7 with the cause found by hand), `tests/test_label_failures.py` (17). The pipeline now logs a `facts` trace step (the merged facts each answer used) so turns in a conversation can be compared with gold; no prompt or answer changes. 450 offline tests.
  - **Decided:** a fact difference counts only if it can change the answer (origin only for rate-changing or banned countries, from rates.yaml; arrival country only for the 2 L countries; ages 21+ equal). Stated fields are compared before derived quantities, so a model that wrote the right facts in an awkward shape is `UNITS` (the conversion), not extraction. Severity is what the traveller would do with the answer: unsafe / over / safe_fail / minor. Changing the labeller after seeing eval failures is allowed (analysis code, not the system) but logged, with the agreement measured before the change.
  - **Found:** the rules give the hand-found cause for 28 of 29 known failures. The exception, C04-t2, is "writer wrong" vs "verifier's number list incomplete", which needs a person: every `WRITER` row is marked for checking. Of the 29: 14 extraction (7 missed, 7 invented), 4 wrong values, 2 units, 5 guard misses, 2 intent, 1 writer, 1 verifier false alarm: reading the question, not reasoning, is where the small model fails.

- **What:** Day 9 freeze tooling, ready for the checkpoint.
  - **Files:** `eval/freeze.py` (short hashes of the five prompts the model sees: intake, writer, evasion check, planner, turn intake; the retrieval settings: reranker, RRF k, candidate pools, k, uncitable tags, citations per rule, chunk size; the budget; the saved index's corpus fingerprint when present; `--write` records `eval/freeze.json`, no flag checks and lists any drift), `tests/test_freeze.py`. `run_agent.py --set eval` now refuses to start when there is no freeze, the code drifted from it, or the response cache is on (`--allow-unfrozen` overrides, on purpose only). Every run summary records the freeze status. 454 offline tests.
  - **Next (owner):** dry-run dev in router and planner mode on the endpoint; if both are clean, `eval/freeze.py --write --note "Day 9 checkpoint"` and commit `eval/freeze.json`.
