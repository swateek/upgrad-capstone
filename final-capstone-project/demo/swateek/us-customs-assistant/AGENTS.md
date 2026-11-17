# AGENTS.md

Instructions for coding agents and contributors working in `final-capstone-project/demo/swateek/us-customs-assistant/`.

## What this is

A Track B capstone: a US Customs Assistant for returning US travellers' **alcohol and tobacco** (v1), built on **Qwen3-8B** and **bge-small-en-v1.5** behind the upgrad course endpoints, with a **LangGraph** agent. It returns the allowance, a duty and excise estimate, anything prohibited, and the regulation behind each point.

- Plan, decisions and stop points: [`docs/implementation-plan.md`](docs/implementation-plan.md)
- Business case and mentor notes: `dumps/practice-capstone-project/final-capstone-project/` (repository root)

## Working rules

- **Ask, don't assume.** If a requirement, data source, rule or design choice is unclear, ask before acting.
- **Never call an upgrad endpoint (chat or embeddings) without the user's explicit OK for that step.** That includes indexing, baselines, evals, smoke tests and `docker compose up` with real keys. Log every run in `docs/quota-log.md`.
- **upgrad only.** No SiliconFlow or other model provider, in code, config or dependencies.
- **LangGraph is the only orchestrator.** No Deep Agents, CrewAI, AutoGen or a second framework.
- **Numbers and rules are code and data.** Allowances, duty and excise come from calculators and the signed-off rule and rate tables in `pack/rules/`. The model never types a dollar figure, quantity or citation id: it refers to figures (`[F1]`) and sources (`[S1]`) by handle, and code renders them.
- **Rules need sign-off.** A rule row is used, and its eval items written, only after the user signs it off (`docs/regulatory-checks.md`).
- **Eval set before agent code.** `pack/eval/queries.jsonl` and `corrections.jsonl` are frozen as `eval-v1` before agent graph code is written. Gold answers are built without access to the code. Never edit gold to make a run pass; tune on `dev.jsonl` only.
- **Respect the 8,192-token window** (input + output) on every call. Always set `max_tokens` (1–1,024). Thinking stays off.
- **Caps per question:** 10 model calls (listwise rerank calls count), 10 tool calls, 12,000 tokens. JSON: strict `json_schema`, Pydantic validation, 2 retries with the error fed back, then escalate.
- **The verifier gates every answer.** Progress may stream; answer text leaves the API only after the verifier.
- **The system informs; it never files or submits a declaration and never advises not declaring.** Every answer says it is an estimate and that the CBP officer's assessment is final.
- **Log the small model's failures** in `docs/COMPENSATIONS.md` (symptom, fix, before/after metric). It feeds a graded report section.

## Endpoints and limits

| Use | Endpoint | Limits |
|---|---|---|
| Chat | Qwen3-8B at `https://103.42.50.41:1033/v1`, CA `certs/vm05-ca.crt` | 1 active request per key across group 031–045 (a second gets 429), 60 req/min, 8,192 tokens in + out, `max_tokens` ≤ 1,024 (512 if unset) |
| Embeddings | bge-small-en-v1.5 at `https://103.42.50.41:1035/v1`, CA `certs/vm02-ca.crt` | 384 dimensions, ≤ 16 texts per request, < 512 tokens per text |

- Every request passes one process-wide gate per endpoint (`customs.llm.retry.GatedTransport`); the API runs as a single worker. Retry 429/503 at 2 s, 4 s, 8 s, then stop.
- Keep TLS verification on with each endpoint's CA file. Never disable it.
- The key is shared by the whole group: run evals when no one else is using it.
- Report a failure to the coordinator with group id, URL, error code and time. Never include the key.

## Documents

Handled as in the reference app: `pack/corpus/manifest.yaml` (hand-edited sources), `manifest.lock.yaml` (generated hashes), `exclusions.yaml`, `splitting.yaml`, `editions.md`, `synthetic/`. Downloads go to `data/` (gitignored) and are data only: never execute or import them. Ingest fails on excluded sources and on more than 2,000 documents. PII is scrubbed at ingest and in traces.

## Secrets

Secrets live in `.env` (template: `env.sample`). Never commit keys or print them in logs, traces or screenshots. The Langfuse SDK records its public key in trace metadata: blur it in screenshots.

## Repository conventions

- Branch from `main`. Pre-commit hooks (ruff, gitleaks, …) must pass. The root `.gitignore` ignores dotfiles except whitelisted ones.
- Backend: Python 3.12, `uv`, FastAPI, LangGraph. Front end: Next.js + Tailwind, pnpm.
- `cd backend && uv run pytest` runs offline; a test fails if anything connects to the course host.
- CI: `.github/workflows/us-customs-assistant.yml` (lint, offline tests, web build, image build; no secrets).
- Ports: web 3500, API 3501, Qdrant 3502.
