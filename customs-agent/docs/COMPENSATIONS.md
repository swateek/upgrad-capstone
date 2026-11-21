# Compensating for a small model: running log

Source for the report section "What did we do to compensate for a small model?".

Add a row when a model weakness changes the design, or when a fix is measured. Fill "Before" and "After" from a scored run, never from memory, and link the run file in "Evidence".

**Version** = the git tag or commit the "After" number comes from (for example `v0.1-baselines`, `v0.3-agent`, or a short commit hash). "Before" is the previous version's number for the same metric on the same set.

**Set** = which questions the metric was measured on: `dev` (20 practice scenarios), `eval-v1` (80 official) or `probe` (a small one-off test). Only `eval-v1` numbers from official runs go in the report's main table.

## Log

| # | Version | Problem seen | Fix | Metric | Set | Before | After | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | v0.0-endpoint | Need to know which structured-output features Qwen3-8B supports before designing the planner | Checked: native tool calls 3/3, `json_schema` and `json_object` both work → planner uses the `tools` parameter; planner, writer and verifier use `json_schema`; Pydantic still validates every output | Tool-call rate | probe | — | 3/3 | `docs/endpoint_check.md` |
| 2 | v0.0-endpoint | Embedding model `bge-small-en-v1.5` reads at most 512 tokens per input; longer text is cut off silently | Hard chunk limit of 350 tokens, enforced in the chunker | Chunks over limit | — | — | 0 | `chunk_corpus.py` |
| 3 | v0.0-endpoint | Asked for `trip_hours` in a tool call, Qwen3-8B passed `10` for "10 days": it copies numbers instead of converting units | Tool schemas never ask the model to convert: durations and quantities are passed as stated (`{value, unit}`), and `normalise_units` converts in code | Correct tool arguments | probe | 0/1 (trip_hours=10) | 1/1 (value=10, unit=days) | `tests/test_live.py::test_native_tool_call` |

## Planned measurements

Fill these as the runs happen; delete any that turn out not to apply.

| Planned fix | Metric | Before comes from | After comes from |
| --- | --- | --- | --- |
| Calculators do all arithmetic | Dollar accuracy (±$0.01) | `closed_book` / `fewshot_json` baseline, no calculators | Agent run |
| Retrieval adds the regulation text | Bottom-line accuracy; citation accuracy | `closed_book` baseline | Agent run |
| Few-shot JSON examples | JSON validity rate | Zero-shot prompt | `fewshot_json` baseline |
| `json_schema` constrained output | JSON validity rate; retries per question | JSON mode only | `json_schema` |
| Self-consistency (3 samples) | Bottom-line accuracy; tokens per question | Single sample | `cot_sc` baseline |
| Unit normaliser ("a fifth", "carton") | Basket extraction accuracy | Intake without normaliser | Intake + normaliser |
| Plan validator + code-router fallback | Invalid plans reaching the executor | Planner alone | Planner + validator |
| Verifier + one writer retry | Wrong dollar figures or citations in final answers | Writer alone | Writer + verifier |
| Metadata filter before reranker | recall@3 on gold clauses | Hybrid search, no filter | Hybrid + filter + reranker |
| Smaller retrieved context (top 3 vs 5) | Accuracy; input tokens per call | Top 5 | Top 3 |
