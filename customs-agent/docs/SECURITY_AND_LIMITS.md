# Security notes, model limits and as-of dates (Day 12)

Source for the report's limits paragraph and the demo's closing slide. Checked 2026-11-24.

## Secrets

| Check | Result |
| --- | --- |
| API keys | Only in `customs-agent/.env` or environment variables (CLAUDE.md rule 8); `src/llm.py` never logs them, and its usage log holds no prompts or keys |
| `.env`, certificates, logs | Git-ignored (`.env` by the repo-root `.*` rule; `certs/`, `logs/` in `customs-agent/.gitignore`). Docker mounts `.env` and `certs/` read-only at run time; they are never copied into the image |
| Tracked files on `customs-agent-main` | No `.env`, certificate or key file tracked; no API key, Langfuse key or private key in any tracked file (`git grep`, 2026-11-24) |
| History of `customs-agent-main` | No key or certificate ever committed on this branch |
| Other branches | `origin/main` (a teammate's demo folders and the `dumps/` folder) tracks the course endpoints' **CA certificates** (`vm02-ca.crt`, `vm05-ca.crt`). These are public CA certificates, not private keys or API keys, so nothing secret is exposed; they are still outside the "certificates git-ignored" rule. Not changed from this branch; to raise with the teammate |
| Final check | Day 13: repeat the scan on the branch to be tagged `v1.0.0` |

## Web server

- **Path traversal (fixed Day 13).** The static-file route served any file in the container for `../` in the URL, `/app/.env` included; the port was published on every interface. Fixed in `app/api.py` (the path must resolve inside `web/dist`) and `docker-compose.yml` (`127.0.0.1:8000`); regression test in `tests/test_api.py`; re-tested on the live container (`docs/REDTEAM_LIVE.md`). Rotate the API keys if the container ever ran on a shared network.
- **Card edits** (`POST /api/edit`, fixed Day 13 for hosting): text values go through the guard and the clause sanitiser, numbers are range-checked; refused with HTTP 422 (hosted red-team L12 to L14).
- **Hosted copy** (https://139-59-66-138.sslip.io, DigitalOcean, Caddy): access code (HttpOnly cookie with a token derived from the code), rate limit per visitor from the address Caddy appends (`TRUST_PROXY=1`), app port not published, firewall 22/80/443. Hosted red-team 24 of 24 (`docs/REDTEAM_LIVE.md`). Destroy the droplet when the course ends.

## Personal data

- **Masked:** emails, card, phone and passport numbers and "my name is …" are masked before anything is written to Langfuse or `logs/trace.jsonl` (`src/safety/pii.py`, `src/tracing.py`). Red-team T20 (name, passport, email) left no trace of them in the answer, trace, recorded model output, usage log or run log (§6.2).
- **Not masked:**
  - the question is sent to the shared model endpoint as typed (intake reads it);
  - the web app's conversation store (`logs/sessions.sqlite3`, local, git-ignored) keeps each conversation's messages as typed, so a correction can be re-read in context. Sessions are not deleted automatically.
- **Fix for a deployment:** mask the question before intake (no personal detail is needed to assess duty), which also covers the session store; expire sessions after a set time.

## Abuse and cost controls

- **Rate limit:** 10 questions per minute per client in the web app (`RATE_LIMIT_PER_MINUTE`), 429 with `Retry-After` beyond it.
- **One request in flight** to the endpoint (FIFO queue in `src/llm.py`), back-off with jitter on 429 and 5xx, honouring `Retry-After`.
- **Budgets:** 10 tool steps and 12,000 tokens per question; every call is refused before sending if it could exceed 8,192 tokens or 1,024 output. No official run came near either (largest call 2,988 tokens, largest question 7,558: `docs/TOKENS.md`).
- **Guard before any model call** for injection, evasion and out-of-scope requests; retrieved text is sanitised and must match the frozen corpus to be cited (§6).
- **Live red-team** (Day 13): 24 new attacks against the running container, 24/24 after the traversal fix (`docs/REDTEAM_LIVE.md`).

## Model limits

- **Reading is the weak point.** Qwen3-8B misreads, drops or invents facts; code checks each fact against the question, but those checks cover the phrasings they were written from. On eval-v3, 20 of agent v2's 23 failures start there, mostly as a needless clarifying question (§5.4, §7.4).
- **Same input, slightly different output.** Calls run at temperature 0, yet between eval-v2 planner runs 1 and 2 the intake JSON differed on 5 of 80 questions and the writer's text on 9 of 80; the final answers were identical in all three runs because code grounding, tools and the verifier absorb the variation.
- **English only.** The guard's patterns and the grounding rules are English phrasings; "Hecho en Cuba" is the one non-English phrase handled.
- **No knowledge from the model.** Rules, rates and country lists come from the data tables, so the model's training cut-off does not matter, but the tables do: an answer is only as current as the as-of dates below.
- **Not handled:** arrival airports ("landing at JFK") are not read as the arrival state; a region is not read as its country ("made in Jalisco"); a price range or a "3 or 5 boxes" is resolved rather than asked; regular tariff rates above the $1,000 flat-rate band, family pooling and splitting the $800 between alcohol and other goods are escalated, not calculated.

## As-of dates

| Data | As of | Where |
| --- | --- | --- |
| Rules (exemptions, allowances, restrictions, escalations, five state notes) | 2026-11-21 | `data/rules.yaml` meta |
| Rates (flat rate, programme and 2 L country lists, TTB excise) | 2026-11-21 (TTB rate page fetched that day) | `data/rates.yaml` meta |
| Product-name tax classes (sake, sparkling, liqueurs, fortified wine) and names made only in one country (tequila, mezcal, pisco) | 2026-11-23 | `rates.yaml` `excise.classes_by_name`, `flat_rate.origin_by_name` |
| Ten extra state notes (web app only) | 2026-11-22 | `rules.yaml` `extended_states` |
| CFR text in the corpus | eCFR as of 2026-11-19 | `data/rag-corpus/sources.yaml` `ecfr_as_of` |
| Web pages in the corpus (CBP, OFAC, TTB, HTSUS 2026 Revision 23, states) | fetched 2026-11-21 | chunk metadata `fetched_at`, `corpus/MANIFEST.json` |
| Open question | Russian-origin alcohol in personal baggage (E.O. 14068 vs the IEEPA travel exemption): escalated, not answered | `docs/regulatory_checks.md` check 5 |

Every answer shows its as-of date and says the CBP officer decides. A change in a rate or rule is a data change and a re-run (CLAUDE.md rule 3); the regression sets (dev, dev-v2, paraphrase, red-team, conversations) and `eval/replay.py` show what it changes.
