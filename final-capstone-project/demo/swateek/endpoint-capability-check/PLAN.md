# Endpoint capability check: plan

Source: mentor note `dumps/practice-capstone-project/final-capstone-project/mentor-notes/Endpoint_Capability_Check.docx` ("Day 0: Checking What the Capstone Endpoint Supports").

The note's Colab/`check_endpoint.py` becomes a small uv app in this folder. It is built on the demo's own `copilot` package (`../procurement-and-vendor-review/backend`), so it reaches upgrad exactly the way the demo does: the same settings, clients, TLS, thinking flag, one-request gate and token counting.

## Decisions (agreed 17 Nov)

| Topic | Decision |
|---|---|
| Packages | Import `copilot` itself, as a uv path dependency on `../procurement-and-vendor-review/backend`. |
| Keys and certs | Its own `.env` (gitignored by the repo's `.*` rule) and its own `certs/`. Both are copied from the upgrad setup in `../procurement-and-vendor-review` (`.env` → `UPGRAD_*`, `certs/vm05-ca.crt`, `certs/vm02-ca.crt`). The check hands them to `copilot`'s `Settings`; the project's `.env` is never read. |
| Scope | The mentor's checks, adapted to our two endpoints, plus the things we learnt building the demo (below). |
| Runtime | `uv run check_endpoint.py` from this folder. |
| Output | `results/endpoint_check.txt` (readable, in the mentor's format) and `results/endpoint_check.json`. Nothing is written into the demo's `docs/`. |

## What we already know (from the demo project)

Our setup differs from what the mentor note assumes:

| Mentor note assumes | Our upgrad setup (group 031–045) |
|---|---|
| One `OPENAI_BASE_URL` and one key | Two endpoints, each with its own key and CA: chat `https://103.42.50.41:1033/v1` (`vm05-ca.crt`) and embeddings `https://103.42.50.41:1035/v1` (`vm02-ca.crt`) |
| Public TLS | Self-signed course CAs; verification stays **on**, trusted through the CA file only |
| The embedding model is guessed from the chat `/models` list | The embedding endpoint is a separate server; ask its own `/models` |
| Default generation settings | Qwen3-8B: thinking must be off via `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` (vLLM style) |
| No limits | 1 active request per key; `max_tokens` ≤ 1024 (1025 → 400); 8192-token context; embeddings ≤ 16 texts per request and < 512 tokens per text (→ 422) |

All of this is already in `copilot`. `copilot.llm.probe` ran 13/13 against upgrad on 14 Nov (`../procurement-and-vendor-review/docs/results/upgrad/probe.md`): the model is `Qwen/Qwen3-8B`, tool calls and strict json_schema work, embeddings have 384 dimensions (bge-small-en-v1.5), and usage is reported (streamed too). This check runs the mentor's checks, with the mentor's own prompts, beside that probe, and adds what the probe didn't cover: the context length, `json_object`, repeated and forced tool calls, and the embedding server's own model name.

## What is reused from `copilot`

| From | Used for |
|---|---|
| `copilot.config.Settings` | Built with `Settings(_env_file=<this folder>/.env, provider="upgrad", domain="procurement", upgrad_chat_ca_cert=<abs>, upgrad_embed_ca_cert=<abs>)`. Cert paths are made absolute against this folder first, because `Settings.resolve` would otherwise resolve them against the demo project. `domain` is required by `Settings` but nothing here uses it. |
| `copilot.llm.providers.get_provider` / `get_embedding` | The chat and embedding endpoint configs: base URL, key, CA, model (`CHAT_MODEL`, default `Qwen/Qwen3-8B`; `bge-small-en-v1.5`) and the thinking-off `extra_body`. They raise `ProviderNotConfigured` when a key or cert is missing. |
| `copilot.llm.providers.make_openai_client` | `OpenAI` clients that verify TLS against the course CA, use `max_retries=0` (no hidden extra calls) and pass every request through the process-wide gate (one active request per key). |
| `copilot.llm.budget.get_tokenizer` / `count_message_tokens` | Our prompt-token estimate against the server's `usage.prompt_tokens`, and sizing a text past bge's 512-token limit. Downloads `tokenizer.json` from Hugging Face on first use (already cached from the demo). |
| `copilot.llm.probe.attempt`, `probe_chat`, `probe_embeddings` | `attempt` times each check and records `APIStatusError`s. `probe_chat` / `probe_embeddings` are run unchanged as the "known behaviour" section (their `main()`, which writes into the demo's `docs/results/`, is **not** called). |

## Folder layout

```
endpoint-capability-check/
  PLAN.md                 this file
  README.md               setup, run, how to read the output
  pyproject.toml          uv project; requires-python ">=3.12,<3.13" (matches copilot)
                          dependencies = ["copilot", "openai"]
                          [tool.uv.sources] copilot = { path = "../procurement-and-vendor-review/backend", editable = true }
  uv.lock
  env.sample              variable names, no values (committed)
  .env                    real keys (gitignored by the root .* rule; never committed)
  certs/vm05-ca.crt       chat CA (copied)
  certs/vm02-ca.crt       embeddings CA (copied)
  check_endpoint.py       the check
  results/
    endpoint_check.txt    readable output, in the mentor's format plus a "what this means" verdict
    endpoint_check.json   the same rows, machine-readable
    quota-log.md          one line per run: date, who, what ran, tokens used
  questions-for-programme-office.md   Option 1 of the note, for the mentor to forward
```

`env.sample` uses the names `copilot.config` already reads:

```
CHAT_MODEL=Qwen/Qwen3-8B
UPGRAD_CHAT_BASE_URL=https://103.42.50.41:1033/v1
UPGRAD_CHAT_API_KEY=
UPGRAD_CHAT_CA_CERT=certs/vm05-ca.crt      # relative to this folder
UPGRAD_EMBED_BASE_URL=https://103.42.50.41:1035/v1
UPGRAD_EMBED_API_KEY=
UPGRAD_EMBED_CA_CERT=certs/vm02-ca.crt     # relative to this folder
ENABLE_THINKING=false
```

## Script design (`check_endpoint.py`)

- **Config:** `Settings` as above; real environment variables still override the `.env`. A missing key or cert stops the script (`ProviderNotConfigured`) before any network call.
- **Pacing:** strictly sequential; the gate in `make_openai_client` enforces one active request per key anyway.
- **Chat defaults:** `temperature=0`, thinking off through the provider's `extra_body`, `max_tokens` ≤ 200 except where the cap itself is being tested.
- **Recording:** every check goes through `probe.attempt` (ok/fail, seconds, detail). The script also adds up `usage` for the token total.
- **Keys** are never printed or written. The output header shows only the hosts.
- **Flags:** `--dry-run` (builds `Settings` and both clients, loads the certs into SSL contexts and makes **no** calls to upgrad), `--skip-chat`, `--skip-embed`, `--skip-probe` (leaves out the reused `probe_chat`/`probe_embeddings` section), `--tool-repeats N` (default 5).
- **Exit code:** 0 when every check ran, even if a feature turns out to be unsupported (that is a finding, not a failure). 1 for a setup error (missing key or cert, TLS failure, 401).

### Checks

**Section A: the mentor's checks** (the mentor's prompts, through our clients):

| # | Check | Answers |
|---|---|---|
| A1 | Chat `GET /models`: ids, plus `max_model_len` if vLLM reports it; the served id is compared with `CHAT_MODEL` | Q1 model and context length |
| A2 | Tools, `tool_choice="auto"`, `get_weather` "What is the weather in Pune?", run N times: number of calls, arguments parse and have `city` | Q3 tools (+ the note's "run it 3–5 times") |
| A3 | `response_format` json_schema, the mentor's city/state schema, sent strict (`strict: true`, `additionalProperties: false`, as our critic uses it) | Q3 constrained decoding |
| A4 | `response_format` json_object | the weaker fallback |
| A5 | Embedding endpoint `GET /models`, compared with `bge-small-en-v1.5`; embed 1 text for the dimension | Q2 model and dimension |
| A6 | `usage` on a "Say OK." call (`max_tokens=5`) | cost metric |

**Section B: what we add:**

| # | Check | Why |
|---|---|---|
| B1 | Tool call forced: `tool_choice="required"` and a named function | can the planner force a call |
| B2 | TEI `GET /info` on the embedding host (outside `/v1`; recorded as "not available" on a 404): `max_input_length`, `max_client_batch_size` | the embedding limits, as the server states them |

**Section C: known behaviour** (`probe_embeddings` + `probe_chat` reused unchanged): embedding batches of 16 accepted and 17 refused; a text over 512 tokens refused; thinking on/off three ways; prompt-token estimate against the server's count; `lookup_record` tool call; strict json_schema verdict; streamed usage; `max_tokens=1025` refused. It also shows whether anything changed since 14 Nov.

Not checked here: Q4 (quota and price) and Q5 (rate limits), which only the programme office can answer, and an 8k-token prompt, which would spend about 8k tokens to prove a number `copilot` already enforces.

**Expected cost:** about 15 chat calls in sections A and B plus 9 in section C, each under ~300 tokens in plus out, so roughly 5–7k tokens in all; the embedding calls are negligible. The script totals the tokens actually used and writes that to `quota-log.md`.

### Output

`endpoint_check.txt` has a header (timestamp UTC, hosts, model ids, total tokens), then section A in the mentor's line format (`tools: OK -> get_weather({"city": "Pune"})`), sections B and C as tables, then a **Verdict** section that applies the note's "Reading the results" table to each finding. For example: `json_schema: OK → use it for the planner, writer and critic outputs; the with/without experiment applies`, or `tools: auto called 5/5 → native tool calling, still validated with Pydantic`.

## Status (17 Nov)

All steps are done. The run (08:10 UTC) made 27 requests and used 1683 + 364 chat tokens and 73 embedding tokens. Every check matches the 14 Nov probe. One new finding: the embedding endpoint publishes no model name (`/v1/models` and `/info` return 404), so Q2's model name is left for the programme office. Decision for step 7: the findings stay in this folder, and neither report changes.

## Steps

1. **Scaffold.** Create `pyproject.toml`, `env.sample` and `README.md`; create `.env` by copying the `UPGRAD_*` values from `../procurement-and-vendor-review/.env`, and `certs/` by copying `vm05-ca.crt` and `vm02-ca.crt`. Run `uv sync`, which installs `copilot` editable with its dependencies into this folder's `.venv`. Makes no calls to upgrad.
2. **Write `check_endpoint.py`** as designed above.
3. **Verify offline.** `uv run ruff check`, then `uv run check_endpoint.py --dry-run`: `Settings` loads from this folder's `.env`, the cert paths point here rather than at the demo project, both clients build, and nothing is sent.
4. **Stop: ask for an explicit OK to call upgrad.** Then run `uv run check_endpoint.py` once.
5. **Read the results** against the 14 Nov probe and note any difference (model, tool behaviour, a new limit). Append the run to `results/quota-log.md`.
6. **Draft `questions-for-programme-office.md`:** the note's five questions, with Q1–3 pre-filled from the run and Q4/Q5 left open for the office.
7. **Stop: decide with the user** whether and where the findings go in the upgrad report (§8 "What we did to compensate for a small model") or in `docs/results/upgrad/eval-report.md`. The SiliconFlow reports stay untouched.
