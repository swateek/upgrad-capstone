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
uv run python data/rag-corpus/chunk_corpus.py           # corpus/chunks.jsonl (1,480 chunks, <= 350 tokens)
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

Dev-only sets for Days 8-9 (committed; rebuild after editing their YAML):

```bash
# multi-turn conversations: eval/conversations.yaml -> conversations.jsonl (dollar gold from conv_gold.xlsx formulas)
uv run python eval/build_conversations.py workbook
soffice --headless --convert-to xlsx --outdir /tmp eval/conv_gold.xlsx && cp /tmp/conv_gold.xlsx eval/conv_gold.xlsx
uv run python eval/build_conversations.py export
# red-team list: eval/redteam.yaml -> redteam.jsonl (answerable items copy the gold of a dev item)
uv run python eval/build_redteam.py
uv run python eval/run_agent.py --set redteam --run-name redteam-day8
uv run python -u eval/run_agent.py --set dev2 --run-name v2b-dev2-router         # agent v2: tune on dev-v2 (-u: live log through tee)
uv run python eval/replay.py results/runs/v1-dev2-router --set dev2              # today's code on a run's recorded readings, no model call
LLM_CACHE=0 uv run python eval/run_agent.py --set eval3 --run-name official-v2-router   # after the v2 freeze: eval-v3 (held out)
```

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

Third ablation arm, `single_rag`: the same search, then one model call answers from the 5 clauses (no guard, no tools, no verifier):

```bash
uv run python eval/run_agent.py --set dev --mode single_rag --run-name day6-single-rag
```

Writes `results/runs/<run>/router.jsonl` (answer, answer card, trace of every step), `scores_router.csv` and `summary_router.json`. Re-running the same command resumes; delete the run folder to start again. Never run `--set eval` until the Day 10 official runs.

## 11. Web app

A FastAPI backend (`app/api.py`) and a React front end (`web/`, Vite + TypeScript). Needs Node 20+.

```bash
uv add fastapi "uvicorn[standard]" langfuse      # once
uv add --dev httpx                                # once, for the API tests
cd web && npm install && cd ..                    # once
```

Development (two terminals):

```bash
uv run uvicorn app.api:app --port 8000            # API; loads the models once at the first question
cd web && npm run dev                             # http://localhost:5173 (proxies /api to :8000)
```

One process, as in the container: `cd web && npm run build && cd ..`, then `uv run uvicorn app.api:app --port 8000` serves the built app at http://localhost:8000.

Each answer carries a trace. With Langfuse settings in `.env` the trace goes to Langfuse and the answer links to it; without them it is appended to `logs/trace.jsonl`. Questions and answers are PII-masked first (emails, phone, passport and card numbers, "my name is ...").

```
LANGFUSE_HOST=https://cloud.langfuse.com         # or your self-hosted Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PROJECT_ID=...                           # optional: builds trace links without an API call
RATE_LIMIT_PER_MINUTE=10                          # optional
```

## 12. Conversations (multi-turn)

Each conversation is a LangGraph thread stored in SQLite (`logs/sessions.sqlite3` for the app). Follow-ups, corrections ("actually it was 30 hours") and fact edits on the answer card continue the same thread; a correction re-runs only the tool steps after the changed fact.

```bash
uv add langgraph langgraph-checkpoint-sqlite      # once
uv run python eval/run_conversations.py --run-name day7-conv                        # 13 dev conversations, code router
uv run python eval/run_conversations.py --mode planner --run-name day7-conv-planner
```

The web app uses the same sessions: answer a question in the box under it, or use "Correct a fact" on the card.

## 13. Docker (the app in one container)

Needs Docker Desktop (or Docker Engine with Compose). Build the corpus and the index first (steps 5 and 9): `chunks.jsonl` and `data/rag-corpus/index/` are copied into the image. `.env`, `certs/` and `logs/` are never copied in; `docker-compose.yml` mounts them at run time.

```bash
uv run python docker/fetch_wheels.py   # once, and again after uv.lock changes: Linux packages into docker/wheels/
docker compose up --build        # http://localhost:8000; first build ~5-10 minutes
docker compose logs -f app       # server log
docker compose down              # stop; sessions, cache and the reranker download are kept
```

- The build installs Python packages offline from `docker/wheels/` (git-ignored), never from PyPI: Docker Desktop reached PyPI very slowly on the owner's Mac, while the Mac itself downloads the ~400 MB in seconds. The script picks the image's CPU from your machine (`--arch x86_64` for an Intel host). PyTorch is the CPU-only build: the default Linux one pulls several GB of NVIDIA libraries.
- The first question loads the models and downloads the reranker (~2 GB) into the `hf-cache` volume: expect about a minute once. To put the reranker in the image instead (a deploy with no volume): `docker compose build --build-arg PRELOAD_RERANKER=1`.
- The container flags all 15 researched arrival states (`STATE_RULES=all`); evaluation runs outside Docker keep the SPEC's five.
- Health: `curl localhost:8000/api/live` (no models loaded) and `curl localhost:8000/api/health` (loads them, lists models, search and state flags).
- After re-chunking the corpus or rebuilding the index, rebuild the image.

## 14. Report tables and figures (Days 11–12)

Read from the official run files in `results/runs/`; nothing is re-run or re-scored. Needs the dev group (`uv sync` installs matplotlib).

```bash
uv run python -m eval.ablation              # results/ablation.csv, docs/ABLATION.md
uv run python -m eval.metrics               # results/metrics.csv, docs/METRICS.md
uv run python -m eval.recall_vs_accuracy    # results/recall_vs_accuracy.csv, docs/RECALL_VS_ACCURACY.md
uv run python -m eval.token_calls           # results/token_calls.csv, docs/TOKENS.md
uv run python -m eval.reliability           # results/reliability.csv, docs/RELIABILITY.md
uv run python -m eval.rubric_taxonomy       # results/failures_rubric.csv (the rubric's four kinds)
uv run python -m eval.report_figures        # docs/report/figures/fig1-5 (PNG)
```

Report drafts are in `docs/report/` (sections 1–7).

Red-team against the running app (Day 13; start it first with `docker compose up --build -d`): about 8 minutes, around 20 questions' worth of quota.

```bash
uv run python -u eval/redteam_live.py --run-name redteam-live-<date> 2>&1 | tee logs/redteam-live.log
```

## Coming next (add steps here as they land)

- Day 13: secrets scan on the tagged branch, assemble the 12-page report, CI, backup video.
- Day 14: final report, tag `v1.0.0`.

## Reference

| What | Where |
| --- | --- |
| Project brief and rules | `CLAUDE.md` |
| Spec (approved) | `docs/SPEC.md` |
| Architecture diagrams | `docs/ARCHITECTURE.md` |
| Rules and rates (data) | `data/rules.yaml`, `data/rates.yaml` |
| Corpus sources | `data/rag-corpus/sources.yaml`, `data/rag-corpus/README.md` |
| Eval format and gold | `eval/README.md`, `eval/gold.md` |
| Small-model compensations | `docs/COMPENSATIONS.md` |
