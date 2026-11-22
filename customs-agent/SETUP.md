# Setup: download and run DeclareRight

Step-by-step from a fresh clone. Keep this file current: when a step is added or changes, update it in the same commit.

Run every command from `customs-agent/` unless a step says otherwise.

## 1. Prerequisites

- macOS or Linux with Git.
- [uv](https://docs.astral.sh/uv/) (`brew install uv`). It installs Python 3.12 itself (pinned in `.python-version`).
- Access to the course's chat and embedding endpoints: two URLs, two API keys, two CA certificates (`.crt`).

## 2. Clone and install

```bash
git clone <repo-url> upgrad-capstone
cd upgrad-capstone/customs-agent
uv sync                     # creates .venv/ with the exact versions in uv.lock
```

## 3. Endpoint settings (`.env`)

Create `customs-agent/.env` (git-ignored; never commit it) and put the CA certificates in `customs-agent/certs/` (also git-ignored):

```bash
CHAT_BASE_URL=https://...
CHAT_API_KEY=...
CHAT_CA_CERT=certs/<chat-ca>.crt
CHAT_MODEL=Qwen/Qwen3-8B

EMBED_BASE_URL=https://...
EMBED_API_KEY=...
EMBED_CA_CERT=certs/<embed-ca>.crt
EMBED_MODEL=bge-small-en-v1.5

# optional
# CHAT_CLIENT_CERT=... / CHAT_CLIENT_KEY=...   mutual TLS, if your endpoint needs it (same for EMBED_)
# CA_RELAX_STRICT=1                           if Python rejects the CA as "not strict X.509"
# LLM_CACHE=0                                 turn the response cache off (official runs)
# RERANKER=none                               plain hybrid search, no reranker (default BAAI/bge-reranker-v2-m3)
```

Certificates can be PEM or DER; paths are relative to `customs-agent/`.

Check the endpoints (writes `docs/endpoint_check.md`):

```bash
uv run python prechecks/check_endpoint.py
```

## 4. Tests

```bash
uv run pytest -q            # offline tests: no network, no quota
uv run pytest -m live -v    # live tests against the real endpoints (uses quota: one request at a time per key)
```

## 5. Build the RAG corpus

The corpus is not committed: it is rebuilt from the official sources. `corpus/MANIFEST.json` (committed) holds the SHA-256 of every document and download in `corpus-v1`, so you can check that your rebuild matches.

```bash
uv run python data/rag-corpus/fetch_corpus.py           # ~10 minutes: downloads, writes corpus/docs/ (742 docs)
uv run python data/rag-corpus/fetch_corpus.py --check   # compare with corpus-v1
uv run python data/rag-corpus/chunk_corpus.py           # corpus/chunks.jsonl (1,289 chunks, <= 350 tokens)
```

- Run the fetch from your own machine: some government sites refuse cloud servers.
- CFR text is fetched as of the date pinned in `data/rag-corpus/sources.yaml` (`ecfr_as_of`), so it matches `corpus-v1`. Web pages (CBP, OFAC, TTB, states) are fetched as they are today: if one changed, `--check` lists it. That is expected; for official runs use the snapshot the project owner shares.
- Two pages block scripts and are committed as hand-saved files in `corpus/raw/` (`cbp_info_cuban_cigars.html`, `eo14068.html`). If the fetch reports another bot-check page, open the URL in a browser, save it as `corpus/raw/<source id>.html`, and re-run with `--only <source id>`.
- Re-runs reuse downloads in `corpus/raw/`; `--refresh` downloads again; `--offline` never uses the network.

## 6. Evaluation sets (already built)

`eval/eval_set.jsonl` (80, tag `eval-v2`) and `eval/dev_set.jsonl` (20) are committed. Rebuild only if you change `eval/scenarios.yaml`:

```bash
uv run python eval/build_eval.py workbook
soffice --headless --convert-to xlsx --outdir /tmp eval/gold.xlsx && cp /tmp/gold.xlsx eval/gold.xlsx   # or open and save in Excel
uv run python eval/build_eval.py export
```

Never tune prompts or code against `eval_set.jsonl`; use `dev_set.jsonl`.

## 7. Prompting baselines and scoring (Day 4)

Four closed-book strategies (no retrieval, no calculators): `closed_book`, `fewshot_json`, `cot_sc` (3 samples, majority vote), `decompose` (extract -> rules -> compute). They use the chat endpoint; one request is in flight at a time.

```bash
uv run python eval/run_baselines.py --set dev --strategies closed_book --limit 3   # smoke test
uv run python eval/run_baselines.py --set dev --run-name day4-dev                 # all four on the 20 dev items
LLM_CACHE=0 uv run python eval/run_baselines.py --set eval --run-name week1       # official: 80 items, cache off, run overnight
```

- Answers go to `results/runs/<run>/<strategy>.jsonl`; re-running the same command resumes where it stopped.
- The eval run writes `results/week1_strategies.csv` (one row per strategy) and `results/week1_failures.csv` (one row per wrong item).
- Score any answers file again: `uv run python eval/score.py --gold eval/dev_set.jsonl --pred results/runs/<run>/<strategy>.jsonl`.
- Tune prompts on `--set dev` only. Run `--set eval` once the prompts are fixed.

## 8. Retrieval experiment (Days 5–7)

Compares BM25, dense (endpoint embeddings), hybrid (RRF, k=60) and hybrid + reranker, with and without the hard-negative filter, at chunk sizes 200 / 350 / 450 tokens, on 60 retrieval queries (`eval/retrieval_queries.yaml`, separate from the eval set).

```bash
uv add rank-bm25 numpy sentence-transformers      # once; sentence-transformers brings PyTorch (a few hundred MB)
uv run python eval/retrieval_experiment.py --methods bm25    # keyword only: quick, no endpoint
uv run python eval/retrieval_experiment.py                   # full grid: embeds ~4,000 chunks once (cached), downloads the reranker once
```

Writes `results/retrieval_experiment.csv` (recall@1/3/5/10, MRR, hard negatives in the top 3, per configuration) and `results/retrieval_per_query.csv`.

Decisions from these results: `docs/RETRIEVAL.md` (hybrid + `BAAI/bge-reranker-v2-m3`, 350-token chunks, hard negatives filtered, 5 chunks per question). To repeat the reranker comparison:

```bash
uv run python eval/retrieval_experiment.py --chunkings 350 --methods hybrid_rerank --reranker BAAI/bge-reranker-v2-m3 --out retrieval_experiment_bge
```

## 9. Search index

The agent searches a saved index of the 350-token chunks, so a run (even with `LLM_CACHE=0`) never re-embeds the corpus. Build it once after building the corpus, and again after re-chunking:

```bash
uv run python -m src.retrieval.index            # builds data/rag-corpus/index/ (git-ignored), or confirms it matches chunks.jsonl
uv run python -m src.retrieval.index --rebuild  # embed every chunk again
```

Try a search (the same one the agent uses):

```bash
uv run python -m src.retrieval.search "4 bottles of wine after 10 days in Italy, do I owe anything?" --ids 19cfr148.33 htsus9816.00.20
```

If `chunks.jsonl` changes, the saved index no longer matches it (fingerprint in `meta.json`) and is rebuilt automatically the next time search starts. The reranker (`BAAI/bge-reranker-v2-m3`, ~2 GB) downloads on first use; set `RERANKER=none` to run without it.

## 10. Agent (code router) on the dev set

One question end to end: guard → intake (LLM) → tools in a fixed order → `search_regulations` → writer (LLM) → verifier (code + LLM). About 3 model calls per answered question.

```bash
uv run python eval/run_agent.py --set dev --limit 3              # smoke test
uv run python eval/run_agent.py --set dev --run-name day5-router  # all 20 dev scenarios, scored
uv run python eval/run_agent.py --set dev --mode planner --run-name day6-planner   # LLM planner instead of the fixed plan
```

`--mode planner` adds one model call: the planner picks the tools and their order, a validator checks the plan (restrictions before calculations, required steps, at most 10), one repair is allowed, and otherwise the code router's plan is used (`plan fallbacks` in the summary). Every question is capped at 10 tool steps and 12,000 tokens; over either, it escalates.

Writes `results/runs/<run>/router.jsonl` (answer, answer card, trace of every step), `scores_router.csv` and `summary_router.json`. Re-running the same command resumes; delete the run folder to start again. Never run `--set eval` until the Day 10 official runs.

## Coming next (add steps here as they land)

- LLM planner + plan validator, single_rag baseline, corrections across turns, Streamlit app, Docker.

## Reference

| What | Where |
| --- | --- |
| Project brief and rules | `../CLAUDE.md` |
| Spec (approved) | `docs/SPEC.md` |
| Architecture diagrams | `docs/ARCHITECTURE.md` |
| Rules and rates (data) | `data/rules.yaml`, `data/rates.yaml` |
| Corpus sources | `data/rag-corpus/sources.yaml`, `data/rag-corpus/README.md` |
| Eval format and gold | `eval/README.md`, `eval/gold.md` |
| Small-model compensations | `docs/COMPENSATIONS.md` |
