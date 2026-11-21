# Compensating for a small model: running log

Source for the report section "What did we do to compensate for a small model?".

Add a row when a model weakness changes the design, or when a fix is measured. Fill "Before" and "After" from a scored run, never from memory, and link the run file in "Evidence".

**Version** = the git tag or commit the "After" number comes from (for example `v0.1-baselines`, `v0.3-agent`, or a short commit hash). "Before" is the previous version's number for the same metric on the same set.

**Set** = which questions the metric was measured on: `dev` (20 practice scenarios), `eval-v2` (80 official; `eval-v1` was superseded before any run), `corpus` (the chunked corpus) or `probe` (a small one-off test). Only `eval-v2` numbers from official runs go in the report's main table.

## Log

| # | Version | Problem seen | Fix | Metric | Set | Before | After | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | v0.0-endpoint | Need to know which structured-output features Qwen3-8B supports before designing the planner | Checked: native tool calls 3/3, `json_schema` and `json_object` both work → planner uses the `tools` parameter; planner, writer and verifier use `json_schema`; Pydantic still validates every output | Tool-call rate | probe | — | 3/3 | `docs/endpoint_check.md` |
| 2 | corpus-v1 | Embedding endpoint (`bge-small-en-v1.5`) rejects any input over 512 tokens (HTTP 422). PDF text (HTSUS General Notes, CBP guides) has no blank lines, so whole pages became single chunks; after the first fix, text that runs words together with dots was still undercounted by our word-based token estimate | Hard chunk limit of 350 tokens, counted with the embedding model's own tokenizer; blocks over the limit are split by lines, then sentences, then words, then characters (tables repeat their header) | Chunks over the limit in real tokens; largest chunk; inputs rejected by the endpoint | corpus | 44 docs over 350 (General Note 3 as one chunk of ~6,500 tokens). After the line/sentence split, with estimated counts: 57 chunks still over, one "200-token" chunk was 1,656 real tokens and the endpoint rejected it | 0 chunks over 350; largest 344 real tokens (1,480 chunks); 0 inputs rejected in the full retrieval run | `chunk_corpus.py`, `tests/test_chunk_corpus.py` |
| 3 | v0.0-endpoint | Asked for `trip_hours` in a tool call, Qwen3-8B passed `10` for "10 days": it copies numbers instead of converting units | Tool schemas never ask the model to convert: durations and quantities are passed as stated (`{value, unit}`), and `normalise_units` converts in code | Correct tool arguments | probe | 0/1 (trip_hours=10) | 1/1 (value=10, unit=days) | `tests/test_live.py::test_native_tool_call` |
| 4 | day4-dev-v2 | Qwen3-8B mislabels outcomes when labels are loosely defined: Cuban cigars and under-21 came back "refused" (it refused the item, not the question); nicotine pouches and evasion came back "escalated" | Each outcome defined in the prompt with what belongs to it (prohibited items and under-21 are "answered"; out of scope, evasion and injection are "refused"); one refused example added to the few-shot set | Outcome accuracy (closed_book / fewshot_json / cot_sc) | dev | 0.70 / 0.75 / 0.65 | 0.90 / 0.93 / 0.80 | `results/runs/day4-dev`, `results/runs/day4-dev-v2` |
| 5 | agent-v0 (`day5-router` → `day5-router-v2`) | Intake writes countries as names ("Trinidad", "Chile", "Italy") although the schema asks for ISO codes; the tools compare codes, so the 2 L Caribbean rule and Chile's free rate were missed (and "Cuba" would miss the ban) | Names and demonyms converted to ISO codes in code after intake (`src/agent/countries.py`: pycountry + alias table, no fuzzy matching); unrecognised origin → null, so clarify asks when it matters | Dollar accuracy on the affected items (D04, D20) | dev | 0/2 | 2/2 | `results/runs/day5-router*/scores_router.csv` |
| 6 | agent-v0 (`day5-router` → `day5-router-v2`) | Intake fills facts the traveller never gave: invented a 1-day trip and arrival from Portugal for D13, so only age was asked | Prompt: never guess profile facts; code (`ground_in_question`): age must appear as a number in the question and a trip length needs a duration phrase, else null (checked on all dev questions: never drops a stated fact) | Clarify accuracy | dev | 0.50 (1/2) | 1.00 (2/2) | same |
| 7 | agent-v0 (`day5-router` → `day5-router-v2`) | The writer does its own arithmetic ("brought 1.25 L, so 0.25 L is over"; really 2.25 L and 1.25 L). The verifier caught the invented number both times, so the answer escalated instead of being wrong | Working states every intermediate number ("3 × 750 ml = 2.25 L in total; 1 L duty-free, 1.25 L over"); writer told to copy numbers, never compute; verifier feedback quotes the sentence with the bad number | Answerable dev items escalated by the verifier; wrong numbers shipped | dev | 1 escalated, 0 shipped | 0 escalated, 0 shipped | same |
| 8 | agent-v0 (`day5-router` → `day5-router-v2`) | Intake mixes up containers, volume and counts: "two 1-litre bottles" → {2 litre}; "a pack of 20" → 20 packs (400 cigarettes) | `normalise_units`: a volume that divides by the container size is that many containers; a box or pack with a piece count as its size is "box of N"; prompt examples for tobacco units | Correct result on the affected items (D02 dollars, D10 bottom line) | dev | 0/2 | 2/2 | same |
| 9 | agent-v0 (`day5-router-v2` → `day5-router-v3`) | Intake writes where an item was bought as its origin: "Cuban cigars bought in Cancún" → origin MX, so the Cuban ban was missed (it had CU in the first run: the model is not stable on this) | Origin stated with the product in the question ("Cuban cigars", "Polish vodka") overrides the model, in code, matched by product type (never contradicts dev gold); when every item is prohibited no exemption fact is asked | D08 correct | dev | wrong (asked for 30-day use) | correct (prohibited; 515.204 + 515.585 cited) | `results/runs/day5-router-v3/`, `tests/test_agent.py` |

## Planned measurements

Fill these as the runs happen; delete any that turn out not to apply.

| Planned fix | Metric | Before comes from | After comes from |
| --- | --- | --- | --- |
| Calculators do all arithmetic | Dollar accuracy (±$0.01) | **eval-v2 `week1`: closed_book 0.00, fewshot_json 0.05, cot_sc 0.07, decompose 0.07 (n=42)** | Agent run |
| Retrieval adds the regulation text | Bottom-line accuracy; citation accuracy | **eval-v2 `week1` closed_book: bottom line 0.63, citations 0.07** | Agent run |
| Few-shot JSON examples | JSON validity rate | Zero-shot prompt | `fewshot_json` baseline |
| `json_schema` constrained output | JSON validity rate; retries per question | JSON mode only | `json_schema` |
| Self-consistency (3 samples) | Bottom-line accuracy; tokens per question | **Measured (eval-v2 `week1`): closed_book 0.63 at 700 tok/q vs cot_sc 0.56 at 2,597 tok/q: no gain, 3.7× cost** | — |
| Unit normaliser ("a fifth", "carton") | Basket extraction accuracy | Intake without normaliser | Intake + normaliser |
| Missing facts decided by code: the tools return which facts change the answer, in SPEC 5.2 order; the planner only phrases one question | Clarify accuracy on the 8 clarify scenarios; spurious clarifies on answerable questions | **eval-v2 `week1`: clarify 0/8 (closed_book, fewshot, cot_sc), 1/8 decompose; decompose asked on 41 of 80 answerable questions** | Agent run |
| Citations taken from chunk metadata (`citation_id`), never written by the model | Citation validity (cited id exists and was retrieved) | `closed_book` / `single_rag` | Agent run with verifier |
| Plan validator + code-router fallback | Invalid plans reaching the executor | Planner alone | Planner + validator |
| Verifier + one writer retry | Wrong dollar figures or citations in final answers | Writer alone | Writer + verifier |
| Metadata filter before reranker | recall@3 on gold clauses | Hybrid search, no filter | Hybrid + filter + reranker |
| Smaller retrieved context (top 3 vs 5) | Accuracy; input tokens per call | Top 5 | Top 3 |
