# Endpoint capability check: upgrad course endpoints

**Track B capstone · group 031–045 · run 17 Nov 2026, 08:10 UTC**

This is the Day-0 check from the mentor note *"Checking What the Capstone Endpoint Supports"*. It finds out which models the course endpoints serve and which features they support, so the design relies on facts rather than assumptions.

## Summary

The endpoints support everything the procurement copilot relies on.

- **Chat model:** `Qwen/Qwen3-8B`, with a context length of **8192 tokens** (input + output).
- **Tool calling:** works natively. The model called the tool with valid arguments in **5 of 5** runs, and a call can also be forced.
- **Structured output:** strict `json_schema` (constrained decoding) and `json_object` both work.
- **Embeddings:** **384 dimensions**, at most 16 texts per request, each under 512 tokens.
- **Token usage** comes back on every call, streamed calls included, so the cost metric can use the server's counts.

Two points remain open:

1. The embedding endpoint does not publish its model name. The vectors fit `bge-small-en-v1.5`, but only the programme office can confirm it.
2. The per-team quota, the price per token and the rate limits have to come from the programme office.

Every result matches the earlier probe of 14 Nov (13 of 13 checks unchanged). The full check used **27 requests and about 2,100 tokens**.

## Endpoints checked

| | Chat | Embeddings |
|---|---|---|
| URL | `https://103.42.50.41:1033/v1` | `https://103.42.50.41:1035/v1` |
| TLS | verified against the course CA `vm05-ca.crt` | verified against the course CA `vm02-ca.crt` |
| Key | group key (kept in `.env`, never committed) | group key (kept in `.env`, never committed) |

The mentor note assumes one URL and one key. The course gives two endpoints, each with its own key and certificate, so the check runs two clients. Requests go one at a time, because the course key allows one active request, and failed calls are not retried automatically, so the token count shows exactly what was spent.

## Answers to the note's questions

| # | Question | Answer from the check | Confidence |
|---|---|---|---|
| 1 | Which chat model, and what context length? | `Qwen/Qwen3-8B`, the only model listed; `max_model_len` = 8192 | Confirmed by the server |
| 2 | Which embedding model, and what dimension? | 384 dimensions. The model name is not published (`/v1/models` and `/info` return 404). The server accepts the name `bge-small-en-v1.5`, and the dimension and limits fit it | Dimension confirmed; name **to be confirmed** |
| 3 | Are `tools` / `tool_choice` and `response_format: json_schema` supported? | Yes, both | Confirmed |
| 4 | Per-team token quota and price per million tokens? | Not checkable from the endpoint | **Open:** programme office |
| 5 | Rate limits (requests and tokens per minute)? | Not checkable from the endpoint | **Open:** programme office |

## Results in detail

### A. The mentor's checks (the mentor's prompts)

| Check | Result | Evidence |
|---|---|---|
| Models served | ✅ one model | `Qwen/Qwen3-8B`, `max_model_len` 8192 |
| Tool calling, `tool_choice="auto"` (run 5×) | ✅ 5/5 | `get_weather({"city": "Pune"})` every time; arguments valid JSON with `city` |
| Strict `json_schema` | ✅ | `{"city": "Mumbai", "state": "Maharashtra"}`: exactly the schema's keys |
| `json_object` (plain JSON mode) | ✅ | `{"city": "Mumbai", "state": "Maharashtra"}` |
| Embeddings | ✅ | 384 dimensions; model name not published by the server |
| Token usage reported | ✅ | `prompt_tokens` 15, `completion_tokens` 3 on "Say OK." |

### B. Checks we added

| Check | Result | Evidence |
|---|---|---|
| Forced tool call, `tool_choice="required"` | ✅ | The model called `get_weather` even for "Hi there!" |
| Forced tool call, named function | ✅ | Same |
| Embedding server info (`/info`) | not available | 404: the server doesn't publish its limits or model name |

When a call is forced and the message gives no argument, the model **makes one up** ("Hi there!" became `{"city": "New York"}`). Forcing works, but force a call only when the input holds what the tool needs, and validate the arguments.

### C. Known behaviour (the 14 Nov probe, re-run unchanged): 13/13 as before

| Check | Result |
|---|---|
| Embeddings: 1 text, then 16 texts | ✅ accepted (384 dimensions) |
| Embeddings: 17 texts | ✅ refused, 422 "batch size 17 > maximum allowed batch size 16" |
| Embeddings: an 802-token text | ✅ refused, 422 "`inputs` must have less than 512 tokens" |
| Thinking mode with `chat_template_kwargs.enable_thinking=false`, with the top-level `enable_thinking=false`, and with no flag | ✅ no thinking in all three (19 completion tokens each); it is off by default |
| Our prompt-token estimate against the server's count | ✅ 35 vs 35 without tools; 187 vs 178 with a tool (we overestimate slightly, the safe side) |
| Tool call (`lookup_record`) | ✅ `{"name": "Acme Traders"}` |
| Strict `json_schema` (the critic's verdict shape) | ✅ `{"passed": true, "reason": "…"}` |
| Streamed usage (`stream_options.include_usage`) | ✅ usage arrives in the final chunk |
| `max_tokens=1025` | ✅ refused with 400: the 1024 output cap is enforced by the server |

## Limits observed

| Limit | Value | How we know |
|---|---|---|
| Context window per call (input + output) | 8192 tokens | `/v1/models` → `max_model_len` |
| Output per call | ≤ 1024 tokens | `max_tokens=1025` refused (400) |
| Embedding batch | ≤ 16 texts per request | 17 refused (422) |
| Embedding input | < 512 tokens per text | 802 refused (422) |
| Concurrency | 1 active request per group key | Track B guide; the check sends requests one at a time |
| Requests and tokens per minute; quota | unknown | **ask the programme office** |

## What this means for the design

Taken through the note's "Reading the results" table:

| Finding | What the note says to do | Where the copilot stands |
|---|---|---|
| One chat model, Qwen3-8B | Develop and test on the same family | Development ran on Qwen3-8B (same weights) throughout |
| Native tool calls work (5/5) | Use the `tools` parameter; still validate the arguments | The agent uses native tool calls; each tool's arguments are validated against a Pydantic model |
| Forcing a call works | (not in the note) | Available if a step must use a tool; it makes arguments up when they're missing, so use it with care |
| Strict `json_schema` works | Use it for the structured outputs; record "with vs. without" as an experiment | The critic's verdict uses strict `json_schema` |
| `json_object` works | The fallback if the schema fails | Not needed while strict `json_schema` works |
| 384-dimension embeddings, ≤ 16 texts, < 512 tokens | Size the vector store to match | The upgrad index is built with 384 dimensions, batches of 16 and texts split under 512 tokens |
| Usage reported, streamed too | Log prompt and completion tokens per call | Tokens are counted per call, and the prompt budget is checked before sending |
| Thinking off by default; the flag is accepted | (not in the note) | The flag is sent explicitly anyway, so behaviour doesn't depend on a server default |

These findings feed the report's graded section, *"What did we do to compensate for a small model?"*

## Open questions for the programme office

Sent through the mentor (full text in [`../questions-for-programme-office.md`](../questions-for-programme-office.md)):

1. Confirm the exact chat checkpoint (revision or quantisation) and that 8192 is the intended context length.
2. **Confirm the embedding model name and version.** The server doesn't publish it; the 384 dimensions and the limits fit `bge-small-en-v1.5`.
3. Will tool calls, `json_schema`, `json_object` and the thinking flag stay as they are through the demo week?
4. **What is the per-team token quota, and what price per million tokens should the cost metric use?**
5. **What are the requests-per-minute and tokens-per-minute limits?** Are there limits beyond one active request per key and `max_tokens` ≤ 1024?

## Cost of this check

| Requests | Chat tokens (prompt + completion) | Embedding tokens |
|---|---|---|
| 27 | 1,683 + 364 | 73 |

Recorded in [`quota-log.md`](quota-log.md).

## How to reproduce

From `final-capstone-project/demo/swateek/endpoint-capability-check/`:

```sh
cp env.sample .env            # add the two group keys
uv sync
uv run check_endpoint.py --dry-run   # checks the setup; sends nothing
uv run check_endpoint.py             # the full check, about 27 requests
```

The script reuses the demo app's own client code (the `copilot` package), so it reaches the endpoints exactly as the app does. Raw output: [`endpoint_check.txt`](endpoint_check.txt), and the same as JSON in [`endpoint_check.json`](endpoint_check.json).
