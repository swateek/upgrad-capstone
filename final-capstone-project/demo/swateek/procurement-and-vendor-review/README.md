# Procurement and vendor-review copilot (Track B)

**Team DLlamas** · IIT Kharagpur / upGrad Executive PG capstone, Track B (API-side).

A Deep Agents copilot on Qwen3-8B for policy Q&A, vendor screening, and draft bid scoring. Everything domain-specific lives in a swappable domain pack under `domains/`.

- Plan: [`docs/implementation-plan.md`](docs/implementation-plan.md)
- Spec: [`docs/spec/task-spec.md`](docs/spec/task-spec.md)
- Rules for contributors and coding agents: [`AGENTS.md`](AGENTS.md)

## Status

**Phases 0–4 are done.** **Phase 5** is in progress: the reports are in [`docs/report/siliconflow/report.md`](docs/report/siliconflow/report.md) and [`docs/report/upgrad/report.md`](docs/report/upgrad/report.md) (build steps in [`docs/report/README.md`](docs/report/README.md)). The final evaluation and demo prep follow.

| Phase | Delivered |
|---|---|
| 0. Spec and scaffold | Config and LLM provider layer (token budget, Track B retry policy, rate/concurrency gate), domain-pack loader, corpus manifest with hashes, spec and refusal policy |
| 1. Eval gate | Corpus (1,690 by_rule chunks), screening snapshot, 10 synthetic bid cases, a frozen 60-question eval set (now v2), single-prompt baseline |
| 2. Demo floor | Hybrid retrieval, domain tools, API, web UI, Docker |
| 3. Depth | Chunking and reranker experiments (by_rule wins), five prompting strategies, the planner/executor/critic agent, the Assistant chat tab |
| 4. Hardening | Langfuse tracing, Redis cache and rate limits, e2e and safety runners. Latest result: **56/60** on eval v2 (run 3), with safety probes passing 7/7 |

**The system now runs on the course endpoints (`PROVIDER=upgrad`, switched 14 Nov):** 55/60 in two full runs on eval v3. This is the submitted and demo configuration; SiliconFlow, where it was developed (57/60), is the fallback. See [Providers](#providers).

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
cd final-capstone-project/demo/swateek/procurement-and-vendor-review
cp env.sample .env          # then fill SILICONFLOW_API_KEY; never commit .env
cd backend
uv sync
uv run pytest -q
```

## Download the corpus

The source PDFs are not committed. `domains/<domain>/corpus/manifest.yaml` lists them (URL, edition, edition date), and `manifest.lock.yaml` pins their sha256.

```bash
cd backend
uv run python -m copilot.ingest.download            # download into ../data/raw/<domain>/ and verify hashes
uv run python -m copilot.ingest.download --freeze   # re-pin hashes after a deliberate edition change
```

A hash mismatch fails the run. If an official file changed upstream, record the decision in `corpus/editions.md` before freezing again.

## Providers

One setting in `.env`, `PROVIDER=siliconflow|upgrad`, picks where every model call goes; **`.env` has `upgrad`**. Plan and status (done): [`docs/endpoint-switch-plan.md`](docs/endpoint-switch-plan.md).

| | `siliconflow` | `upgrad` |
|---|---|---|
| Chat | Qwen3-8B on SiliconFlow | Qwen3-8B on the course endpoint (group 031–045) |
| Embeddings | `Qwen3-Embedding-0.6B` | `bge-small-en-v1.5` on the course embedding endpoint |
| Rerank | `Qwen3-Reranker-8B` | Qwen3-8B on the course chat endpoint, listwise (`UPGRAD_RERANKER=upgrad`) |
| Qdrant collection | `procurement__by_rule` | `procurement__by_rule__bge-small-en-v1-5` |
| Results | `docs/results/siliconflow/` | `docs/results/upgrad/` |

Each provider keeps its own index, so switching never rebuilds one: edit `.env`, then restart the API (`docker compose up -d api`). `GET /health` shows the provider, models and collection in use. The course CA certificates are in `certs/` (public CAs, mounted read-only in Docker); TLS verification stays on.

```bash
uv run python -m copilot.llm.probe              # check the course endpoints' behaviour (calls them)
PROVIDER=upgrad uv run python -m copilot.ingest.index   # build the upgrad index once (calls the embedding endpoint)
uv run python -m copilot.ingest.copy_index --to http://localhost:3402 --only procurement__by_rule procurement__by_rule__bge-small-en-v1-5
                                                # fill Docker's Qdrant from the host index (no API calls)
```

## Phase 0 spike (SiliconFlow)

```bash
cd backend
uv run python spikes/siliconflow_spike.py
```

The spike makes seven small calls (thinking on/off, tool round trip, JSON modes, long history, streaming) and writes `docs/results/siliconflow/phase0-spike-siliconflow.json`. To rerun only some checks and merge them into the existing file: `--only 5,6,7`.

The Deep Agents prompt-size measurement is offline (a stub model, no API calls):

```bash
uv run python spikes/deepagents_prompt_size.py
```

Findings so far are in [`docs/small-model-log.md`](docs/small-model-log.md).

## Phase 1: corpus, screening data, bid cases, eval set, baseline

Run from `backend/`, after downloading the corpus:

```bash
uv run python -m copilot.ingest.build_chunks                          # by_rule chunks -> data/processed/<domain>/chunks/
uv run python ../domains/procurement/pipelines/build_screening.py     # GeM delist PDF -> data/screening/*.csv
uv run python ../domains/procurement/pipelines/validate_bid_cases.py  # checks all 10 synthetic cases against their gold
uv run python -m eval.baseline                                        # single-prompt baseline (~50 small API calls)
uv run python -m eval.baseline --rescore                              # re-score saved answers, no API calls
uv run pytest -q
```

| Output | Where |
|---|---|
| Corpus counts | [`docs/results/phase1-corpus-by_rule.md`](docs/results/phase1-corpus-by_rule.md) |
| Eval set (60), dev set (8), retrieval labels (15) | `domains/procurement/eval/` |
| Synthetic bid cases (10) | `domains/procurement/data/bid_cases/` |
| Screening snapshot | `domains/procurement/data/screening/` |
| Baseline results | [`docs/results/siliconflow/phase1-baseline.md`](docs/results/siliconflow/phase1-baseline.md) |

## Phase 2: demo floor (hybrid retrieval, tools, API, web, Docker)

### With Docker

```bash
cp env.sample .env      # fill SILICONFLOW_API_KEY (ports default to 3400 web, 3401 api, 3402 qdrant)
docker compose --profile ingest run --rm ingest   # once: verify sources, chunk, embed into Qdrant (~1 min)
docker compose up -d --build                      # qdrant + api + web
open http://localhost:3400
```

The ingest job downloads the source PDFs into the `copilot-data` volume and checks each one against `manifest.lock.yaml`. Rerunning it is cheap: an up-to-date index isn't re-embedded.

### Without Docker (development)

```bash
cd backend
uv run python -m copilot.ingest.index                         # embed by_rule chunks into data/qdrant (embedded Qdrant)
uv run python -m eval.retrieval                               # recall@1/5/10 for bm25, dense, hybrid
uv run uvicorn copilot.api.app:app --reload --port 3401
cd ../web && pnpm install && pnpm dev                         # http://localhost:3400 (API_URL defaults to :3401)
```

### API

| Route | What it does |
|---|---|
| `GET /health` | Index status (points, staleness) and provider |
| `GET /domain` | Display name, UI modes, tools with input schemas, instruments |
| `GET /listings/bid-cases` | Preloaded cases for the bid picker |
| `POST /tools/{name}` | Calls one domain tool directly (`search_policy`, `screen_vendor`, `score_bids`). Returns a draft. |
| `POST /answer` | Hybrid retrieval plus one grounded model call. Citations are mapped from source handles in code. |

No route awards, orders, debars or approves. The web proxy forwards only these routes.

## Phase 3: experiments and the agent

```bash
cd backend
uv run python -m copilot.ingest.rechunk                    # fixed_512 + recursive_800 chunk sets
uv run python -m copilot.ingest.index --chunker fixed_512  # (and recursive_800) embed into Qdrant
uv run python -m eval.retrieval --chunker by_rule --reranker Qwen/Qwen3-Reranker-8B
uv run python -m eval.prompts                              # 5 prompting strategies on the policy questions
```

| Result | File |
|---|---|
| Chunking and reranker matrix | `docs/results/siliconflow/retrieval-<chunker>--<reranker>.md` |
| Prompt strategies | `docs/results/siliconflow/phase3-prompts.md` |
| What broke and what compensates | `docs/small-model-log.md` |

The agent (`backend/src/copilot/agent/`):
- **Planner:** the main agent writes todos, then delegates.
- **Executor:** a Deep Agents subagent with the tools.
- **Critic:** enforced in code on every answer.
- **Budgets per query:** 10 model calls (steps), 10 tool calls, 40,000 tokens.
- **API:** `POST /chat` streams progress over SSE and sends the answer only after the critic. `GET /threads/{id}` returns history.
- **Web:** the **Assistant** tab is the chat, with a live agent trace.

## Phase 4: evaluation, tracing, safety, cache and rate limits

```bash
cd backend
uv run python -m eval.e2e --label run5     # 60 frozen questions through the full agent (~30 min, ~$0.04)
uv run python -m eval.e2e --rescore e2e-v1-run2.json   # re-score a saved run (in docs/results/) on the current gold, no API calls
uv run python -m eval.judge e2e-v3-run5-rescored.json # content check of policy answers by a larger judge model (~90K tokens)
uv run python -m eval.safety               # 7 injection / refusal / PII probes
```

- **Results, course endpoints (`upgrad`, the submitted configuration):** [`docs/results/upgrad/eval-report.md`](docs/results/upgrad/eval-report.md)
  - two runs on eval v3: 55/60 each, 22/23 factual policy, 8/8 refusals; 58 of 60 answers identical between the runs;
  - safety probes 7/7; demo preflight 9/10 twice.
- **Results, SiliconFlow:** [`docs/results/siliconflow/eval-report.md`](docs/results/siliconflow/eval-report.md)
  - final, run 5 on eval v3: 57/60 overall, 22/23 factual policy, 0 retrieval misses, 0 tool-call errors;
  - with the content check on policy answers: 55/60 overall, 20/23 policy (verdicts confirmed by the team: `docs/results/siliconflow/judge-v3-run5-review.md`);
  - safety probes 7/7.
- **Tracing:** Langfuse Cloud, one trace per agent turn, PII-masked. It's on when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are in `.env`.
- **Docker:** Redis now holds the retrieval cache and the rate-limit counters:
  - 60 requests/min per client;
  - 10 agent turns/min per conversation;
  - 429 with `Retry-After` when exceeded.

## Phase 5: report, content check, demo

```bash
cd backend
uv run python -m eval.judge e2e-v3-run5-rescored.json   # content check of policy answers (larger judge model)
uv run --with matplotlib python ../docs/report/siliconflow/make_figures.py   # report figures from docs/results/siliconflow/*.json
uv run --with matplotlib python ../docs/report/upgrad/make_figures.py        # upgrad report figures from docs/results/upgrad/*.json
uv run python -m eval.demo_preflight                    # run the scripted demo against the live API (stack must be up)
```

- **Reports:** [`docs/report/upgrad/report.md`](docs/report/upgrad/report.md) (**submitted**) and [`docs/report/siliconflow/report.md`](docs/report/siliconflow/report.md), each with HTML and PDF beside it (build steps in [`docs/report/README.md`](docs/report/README.md)).
- **Content check:** review sheets `docs/results/siliconflow/judge-*-review.md` (final: [`judge-v3-run5-review.md`](docs/results/siliconflow/judge-v3-run5-review.md)). The judge finds the problems, and a person confirms the verdicts.
- **Demo:**
  - talk track in [`docs/demo/demo-script.md`](docs/demo/demo-script.md);
  - questions and checks in `domains/procurement/demo.yaml`;
  - latest preflights: `docs/results/upgrad/demo-preflight-1.md` and `-2.md` (the demo provider), `docs/results/siliconflow/demo-preflight.md` (the fallback).
- **Trace dashboard:**
  - screenshots of the `upgrad` runs in `docs/demo/traces/upgrad/` (upgrad report Appendix E), and of the SiliconFlow runs in `docs/demo/traces/` (SiliconFlow report Appendix D);
  - how to reproduce each view: [`docs/demo/trace-dashboard.md`](docs/demo/trace-dashboard.md).
