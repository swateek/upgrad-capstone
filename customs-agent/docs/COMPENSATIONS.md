# Compensating for a small model: running log

Source for the report section "What did we do to compensate for a small model?".

Add a row when a model weakness changes the design, or when a fix is measured. Fill "Before" and "After" from a scored run, never from memory, and link the run file in "Evidence".

**Version** = the git tag or commit the "After" number comes from (for example `v0.1-baselines`, `v0.3-agent`, or a short commit hash). "Before" is the previous version's number for the same metric on the same set.

**Set** = which questions the metric was measured on: `dev` (20 practice scenarios), `eval-v2` (80 official; `eval-v1` was superseded before any run), `corpus` (the chunked corpus) or `probe` (a small one-off test). Only `eval-v2` numbers from official runs go in the report's main table.

## Log

| # | Version | Problem seen | Fix | Metric | Set | Before | After | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | v0.0-endpoint | Need to know which structured-output features Qwen3-8B supports before designing the planner | Checked: native tool calls 3/3, `json_schema` and `json_object` both work → planner uses the `tools` parameter; planner, writer and verifier use `json_schema`; Pydantic still validates every output | Tool-call rate | probe | — | 3/3 | `docs/endpoint_check.md` |
| 2 | corpus-v1 | Embedding model `bge-small-en-v1.5` reads at most 512 tokens per input; longer text is cut off silently. PDF text (HTSUS General Notes, CBP spirits guide) has no blank lines, so whole pages became single chunks | Hard chunk limit of 350 tokens; blocks over the limit are split by lines, then sentences, then words (tables repeat their header) | Docs with a chunk over 350 tokens; largest chunk | corpus | 44 docs; General Note 3 as one chunk of ~6,500 tokens | 0 docs; largest 346 tokens (1,289 chunks) | `chunk_corpus.py`, `tests/test_chunk_corpus.py` |
| 3 | v0.0-endpoint | Asked for `trip_hours` in a tool call, Qwen3-8B passed `10` for "10 days": it copies numbers instead of converting units | Tool schemas never ask the model to convert: durations and quantities are passed as stated (`{value, unit}`), and `normalise_units` converts in code | Correct tool arguments | probe | 0/1 (trip_hours=10) | 1/1 (value=10, unit=days) | `tests/test_live.py::test_native_tool_call` |
| 4 | day4-dev-v2 | Qwen3-8B mislabels outcomes when labels are loosely defined: Cuban cigars and under-21 came back "refused" (it refused the item, not the question); nicotine pouches and evasion came back "escalated" | Each outcome defined in the prompt with what belongs to it (prohibited items and under-21 are "answered"; out of scope, evasion and injection are "refused"); one refused example added to the few-shot set | Outcome accuracy (closed_book / fewshot_json / cot_sc) | dev | 0.70 / 0.75 / 0.65 | 0.90 / 0.93 / 0.80 | `results/runs/day4-dev`, `results/runs/day4-dev-v2` |

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
