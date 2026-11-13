# Procurement and vendor-review copilot (Track B)

A Deep Agents copilot on Qwen3-8B for policy Q&A, vendor screening, and draft bid scoring. Everything domain-specific lives in a swappable domain pack under `domains/`.

- Plan: [`docs/implementation-plan.md`](docs/implementation-plan.md)
- Spec: [`docs/spec/task-spec.md`](docs/spec/task-spec.md)
- Rules for contributors and coding agents: [`AGENTS.md`](AGENTS.md)

## Status

**Phase 0** (spec + scaffold) is done. **Phase 1** (eval gate) is drafted; the eval set awaits team review before freezing. Phase 0 delivered:
- Config and LLM provider layer: token budget, Track B retry policy, rate/concurrency gate
- Domain-pack loader
- Corpus manifest with hashes
- SiliconFlow spike script
- Spec and refusal policy drafts

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
cd final-capstone-project/demo/swateek
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

## Phase 0 spike (SiliconFlow)

```bash
cd backend
uv run python spikes/siliconflow_spike.py
```

The spike makes seven small calls (thinking on/off, tool round trip, JSON modes, long history, streaming) and writes `docs/results/phase0-spike-siliconflow.json`. To rerun only some checks and merge them into the existing file: `--only 5,6,7`.

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
| Baseline results | [`docs/results/phase1-baseline.md`](docs/results/phase1-baseline.md) |

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
