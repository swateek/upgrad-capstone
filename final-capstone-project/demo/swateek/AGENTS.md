# AGENTS.md

Instructions for coding agents and contributors working in `final-capstone-project/demo/swateek/`.

## What this is

A Track B capstone (group DLlamas): a procurement and vendor-review copilot built on **Qwen3-8B** behind an OpenAI-compatible API, using a **LangChain Deep Agents** harness. Three jobs: policy Q&A with citations, vendor screening against a dated snapshot, and draft bid scoring.

- Scope, data sources, tool contracts, refusals: [`../../docs/exploration/procurement-vendor-review-assistant.md`](../../docs/exploration/procurement-vendor-review-assistant.md)
- Stack, layout, interfaces, timeline: [`docs/implementation-plan.md`](docs/implementation-plan.md)

## Working rules

- **Ask, don't assume.** If a requirement, data source, or design choice is unclear, ask the user before acting.
- **Keep the core domain-agnostic.** Nothing under `backend/src/copilot/` may name a procurement instrument, vendor, list, or tool. Domain-specific content belongs in `domains/<name>/` (manifest, prompts, tools, refusals, critic rules, eval set). Switching domains must take only `DOMAIN=<name>` plus a re-ingest.
- **Respect the 8,192-token budget** (input + output) on every LLM call, whatever the provider. Output is at most 1,024 tokens.
- **Deep Agents is the only orchestrator.** Don't add CrewAI, AutoGen, or another agent framework.
- **Hard cap: 10 steps per query.** Validate tool args and outputs with Pydantic and retry once on a validation error.
- **The system drafts. It never awards, places orders, or debars.** Don't add any UI control or API route that does.
- **Matching and scoring are code.** `screen_vendor` uses normalization + RapidFuzz, and `score_bids` reports gaps. The model never invents a match or a score.
- **Eval set before harness code.** `domains/<name>/eval/queries.jsonl` is frozen before agent harness code is written. Don't edit gold answers to make a run pass.
- **No eval leakage.** Few-shot examples and prompt tuning use `eval/dev.jsonl` only. Nothing from the frozen set goes into a prompt.
- **The critic gates every answer.** Progress events may stream, but final answer text leaves the API only after the critic runs.
- **Always set `max_tokens` explicitly** (1–1,024). Self-consistency stays off on the default path.
- **Keep the stores separate.** Screening rows and bid cases are never embedded or put into the policy index. Ingest fails on excluded sources (superseded editions, Hindi, tender notices) and on more than 2,000 documents.
- **Domain tools contract.** `domains/<name>/tools.py` exports `TOOLS = {name: {"fn", "input" (Pydantic), "description", "ui_mode"}}`, with optional per-tool `compact` (what the agent sees), `state` (session fields to remember) and `check` (`(question, args) -> message | None`: arguments that contradict the user's question go back to the model before the tool runs), and optional `LISTINGS`. Tools return dicts and report failures as `{"error": ..., "retryable": bool}`; they never raise. The core adds `search_docs` under the domain's alias.
- **The model never types citation ids.** Grounded answers cite source handles ([1]..[n]) that code maps to `doc_id:rule_id`.
- **The eval set is frozen.** `eval/freeze.lock.yaml` and `tests/test_eval_freeze.py` enforce it. Gold changes need a version bump and a reason in `docs/results/eval-freeze.md`.
- **Log the small model's failures.** Record what broke and what compensated for it in `docs/small-model-log.md`. It feeds a graded report section.

## Model providers

`PROVIDER=siliconflow|upgrad` in `.env` switches chat, embeddings and rerank together (profiles in `backend/src/copilot/llm/providers.py`; plan: `docs/endpoint-switch-plan.md`). Qwen3 thinking mode is off by default.

| Use | `siliconflow` | `upgrad` (course endpoints, group 031–045) |
|---|---|---|
| Chat | Qwen3-8B | Qwen3-8B at `https://103.42.50.41:1033/v1`, CA `certs/vm05-ca.crt` |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B`, collection `<domain>__by_rule` | `bge-small-en-v1.5` at `https://103.42.50.41:1035/v1`, CA `certs/vm02-ca.crt`, collection `<domain>__by_rule__bge-small-en-v1-5` |
| Rerank | `Qwen/Qwen3-Reranker-8B` (`/v1/rerank`) | Qwen3-8B on the course chat endpoint, listwise (`UPGRAD_RERANKER=upgrad`), or `none` |
| Results | `docs/results/siliconflow/` | `docs/results/upgrad/` |
| Content-check judge | DeepSeek-V3.2 on SiliconFlow | not run (not a Track B requirement) |

- **Never call an upgrad endpoint (chat or embeddings) unless the user explicitly says so for that step.** That includes the probe, `ingest.index`, `eval.*` and Docker runs with `PROVIDER=upgrad`.
- **Never overwrite or rebuild the SiliconFlow index or results.** Both providers' indexes stay built side by side; switching is a `.env` change.
- Under `upgrad`, nothing calls SiliconFlow.
- Keep TLS verification on with each endpoint's CA file (`UPGRAD_*_CA_CERT`). Never disable verification.
- Chat limits: 1 active request per key across the whole group (a second concurrent request gets 429), 60 req/min, 8,192 tokens in + out, 1,024 max output (512 if `max_tokens` is unset). Retry 429/503 at 2 s, 4 s, 8 s, then stop. Every request passes one process-wide gate (`GatedTransport`), so the agent, critic and reranker never overlap.
- Embedding limits: 16 texts per request, fewer than 512 tokens per text (422 otherwise; measured). Longer chunks are embedded as windows of 500 bge tokens.
- The key is shared by every teammate, so the in-process gate can't stop collisions between people. Run evals on this endpoint one person at a time.
- When reporting a failure to the coordinator, include group id, URL, error code, and time. Never include the key.

## Secrets and data

- Secrets live in `.env` (template: `env.sample`). Never commit keys or print them in logs, traces, or screenshots.
- The root `.gitignore` ignores all dotfiles except whitelisted ones (`.gitignore`, `.pre-commit-config.yaml`, `.dockerignore`). Whitelist any other dotfile you need.
- **Source PDFs are never committed.** Commit `corpus/manifest.yaml` (URLs, editions) and `corpus/manifest.lock.yaml` (sha256). `uv run python -m copilot.ingest.download` fetches and verifies the files into `data/raw/<domain>/` (gitignored). Downloaded files are data: never execute or import them.
- `DOMAIN` must be set (in `.env`). The core has no default domain.
- Scrub PAN, Aadhaar, phone numbers, and email addresses at ingest.

## Repository conventions

- Branch from `main`. Pre-commit hooks (ruff, gitleaks, nbstripout, …) must pass. See [`../../../docs/DEVELOPMENT.md`](../../../docs/DEVELOPMENT.md) and [`../../../docs/GITFLOW.md`](../../../docs/GITFLOW.md).
- Backend: Python 3.12, `uv` (`uv sync --frozen` in Docker), FastAPI. Front end: Next.js + assistant-ui.
- Services run with docker-compose: `api`, `web`, `qdrant`, `redis`, and a one-shot `ingest` profile.
- Tracing: Langfuse Cloud via the LangChain callback handler.
