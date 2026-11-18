# US Customs Assistant (alcohol and tobacco, v1)

Returning US travellers ask one plain-language question and get back how much alcohol and tobacco they can bring, an estimate of what they owe on the rest, what is prohibited, and the regulation behind each point. Dollar figures come from calculators; a verifier checks every figure and citation before the answer is shown. Built for Track B on the upgrad course endpoints (Qwen3-8B, bge-small-en-v1.5) with a LangGraph agent.

Estimates only: the CBP officer's assessment is final.

- Plan: [`docs/implementation-plan.md`](docs/implementation-plan.md)
- Rules for contributors and coding agents: [`AGENTS.md`](AGENTS.md)

## Status

- Step 1, scaffold: endpoint layer (gate, retry, token budget, chat call with strict JSON), tracing, retrieval core, health API, web skeleton, Docker, CI.
- Step 2, corpus: 41 public sources, 1,261 documents, three chunk sets (`docs/results/corpus-counts.md`, `pack/corpus/editions.md`).

- Step 3, regulatory checks: R1–R12 researched and signed off (`docs/regulatory-checks.md`, `pack/rules/`).
- Step 4, SPEC v1.0 approved (`docs/SPEC.md`).
- Step 5, eval set: `eval-v1` frozen: 80 scenarios + 6 corrections, 20 dev, independent gold (`docs/results/eval-freeze.md`).

- Step 6, calculators and tools (`backend/src/customs/tools/`): every rule as code over the signed-off tables; matches the dev gold exactly.

- Step 7, index: three Qdrant collections from cached embeddings (221 requests, once).
- Step 8, baselines (the gate): four prompting strategies on eval-v1 (`docs/results/week1-baselines.md`); mentor check-in `docs/mentor-check-01.md`.
- Step 9, retrieval experiment: 63 variants + listwise; shipped window200, hybrid, question + rule names, topic filter, no reranker (`docs/results/retrieval-decisions.md`).

- Step 10, agent graph (offline): LangGraph guard → intake → prepare → clarify → plan → execute → audit → write → verify; modes planner / router / tool_calling / single_rag; prompt sizes in `docs/results/prompt-sizes.md`; oracle on dev 23/23 (`uv run python -m eval.oracle_dev`).

- Step 11, dev-set runs: 5 runs on dev only, 14/23 → 23/23 turns; agent frozen as v1 (`pack/agent.lock.yaml`); see `docs/results/dev-runs.md`.

Next: API, UI and Docker (offline build), then a live smoke test.

## Run

```sh
cp env.sample .env                    # upgrad keys + this app's Langfuse project keys

# backend (offline tests never reach the course endpoints)
cd backend && uv sync && uv run pytest

# corpus: download public sources (verified against the lock), then chunk
uv run python -m customs.ingest.download && uv run python -m customs.ingest.build_chunks
uv run uvicorn customs.api.app:app --port 3501

# web
cd web && pnpm install && pnpm dev    # http://localhost:3500

# or everything in Docker
docker compose up -d                  # http://localhost:3500
```

Running the stack with real keys reaches the course endpoints once questions are asked; agree it with the group first (one active request per key).

## Layout

| Path | What |
|---|---|
| `backend/src/customs/` | `llm/` endpoints, gate, budget, chat call · `retrieval/` BM25, dense, hybrid, rerank · `observability/` Langfuse · `ingest/` PII scrub · `api/` FastAPI |
| `backend/tests/` | Offline tests (mock endpoints) |
| `pack/` | Corpus manifest, rule and rate tables, prompts, eval sets |
| `web/` | Next.js front end |
| `docs/` | Plan, SPEC, regulatory checks, compensations, quota log, results, report |
| `certs/` | Course CA certificates (public) |
