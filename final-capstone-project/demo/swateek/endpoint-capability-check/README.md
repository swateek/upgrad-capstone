# Endpoint capability check

The mentor note's Day-0 check ("Checking What the Capstone Endpoint Supports") for the upgrad course endpoints, as a uv script built on the demo's `copilot` package. The plan and the reasoning behind it are in [PLAN.md](PLAN.md).

## Setup

```sh
cp env.sample .env      # then fill in UPGRAD_CHAT_API_KEY and UPGRAD_EMBED_API_KEY
uv sync                 # installs ../procurement-and-vendor-review/backend (copilot), editable
```

`certs/` holds copies of the course CAs (`vm05-ca.crt` for chat, `vm02-ca.crt` for embeddings). `.env` is never committed. The script reads only this folder's `.env` and `certs/`, never the demo project's.

## Run

```sh
uv run check_endpoint.py --dry-run   # settings, certs, clients, tokenizers; nothing sent to upgrad
uv run check_endpoint.py             # the full check: ~27 requests, a few thousand tokens
```

Flags: `--skip-chat`, `--skip-embed`, `--skip-probe` (leaves out section C), `--tool-repeats N` (default 5), `--who NAME` (for the quota log).

The script calls the course endpoints. Run it only when the team agrees, and keep the quota log.

## Output

- `results/endpoint_check.txt`: section A in the mentor script's format, B and C as check lines, then a **Verdict** that applies the note's "Reading the results" table to each finding.
- `results/endpoint_check.json`: the same, machine-readable.
- `results/quota-log.md`: one line per run, with date, who, flags, requests and tokens.

| Section | What |
|---|---|
| A | The mentor's checks with the mentor's prompts: `/models` (+ `max_model_len`), tools ×5, strict json_schema, json_object, embeddings model + dimension, usage |
| B | Forced tool calls (`required`, named) and the embedding server's `/info` limits |
| C | `copilot.llm.probe`'s chat and embedding checks, unchanged (13/13 on 14 Nov) |

Exit code 0 means every check ran; an unsupported feature counts as a finding, not a failure. Exit code 1 means a setup problem: a missing key or cert, TLS, or 401/403.
