# Endpoint switch plan: `PROVIDER=siliconflow | upgrad`

**Team:** DLlamas · **Status:** **done (14 Nov 2026).** The switch is built and every result step ran on `upgrad`. The demo and the submitted report use `upgrad`; SiliconFlow stays as the fallback.

One setting in `.env` picks where the copilot's models run. `siliconflow` is today's stack. `upgrad` moves chat, embeddings and reranking to the course endpoints, with no SiliconFlow calls. Both stay usable: both indexes are kept built, and every result is saved under its provider's own directory.

**Rules:**
- No call to an upgrad endpoint (chat or embeddings) without the user's explicit go-ahead for that step.
- The SiliconFlow index and results are never overwritten or rebuilt, so switching back is a `.env` change.

## Decisions so far

| Question | Decision |
|---|---|
| Group id | **031–045**: chat on `https://103.42.50.41:1033/v1` with `vm05-ca.crt` |
| Reranker under `upgrad` (the course offers none; Track B requires one) | **`UPGRAD_RERANKER=upgrad`: Qwen3-8B on the course chat endpoint orders the fused top-20 in one listwise call.** No SiliconFlow under `upgrad`. `none` remains available (hybrid only). |
| Token quota | The full run went ahead on the user's go-ahead (14 Nov). About 2.7M chat tokens were used that day (probe, smoke test, an interrupted first attempt, two full runs, chunking, safety, preflight), plus about 1.49M on the shared embedding key for the two extra chunker indexes. |
| Demo and submission | **`upgrad`** (user's decision, 14 Nov): `.env` has `PROVIDER=upgrad`; the submitted report is `docs/report/upgrad/report.pdf`. |
| Content-check judge under `upgrad` | **Not run.** The Track B brief doesn't require an LLM judge (see below). |
| Results | **Both kept, in separate directories, labelled by provider** |

**Is the judge required?** No. In `Track-Selection.pdf`, the "LLM-as-judge rubric" is in **Track A**'s evaluation week and role table. Track B's evaluation requirement (V) is: end-to-end accuracy against the eval set, task completion rate, average tool calls per task, cost and latency per query, a failure taxonomy (retrieval miss, reasoning error, tool-call error, hallucination), and tracing. The content check came from our own plan (§11.2: "a manual or LLM-judge pass on content"). So the `upgrad` run reports the citation check, and the report says that the content check was done on the SiliconFlow runs.

## 1. What the course provides

Sources: `dumps/practice-capstone-project/final-capstone-project/Track_B_Inference_API_Learner_Guide.docx.pdf` and `embedding-endpoint/Embedding_API_Quickstart.md`.

| | Chat | Embeddings |
|---|---|---|
| Base URL | `https://103.42.50.41:1033/v1` (groups 031–045) | `https://103.42.50.41:1035/v1` |
| Route | `/chat/completions` (the base already ends in `/v1`) | `/embeddings` |
| Model | `Qwen/Qwen3-8B` | `bge-small-en-v1.5`: 384 dimensions |
| CA certificate | `vm05-ca.crt` | `vm02-ca.crt` |
| Key | group key from the coordinator; shared by the team | shared embedding key; `.shared-embedding-key.txt` in `dumps/`, git-ignored |
| Limits | **1 active request per key**, across everyone using it · 60 requests/min · 8,192 tokens in + out · `max_tokens` 512 by default, 1,024 max · 15 active requests on the whole VM05 | **≤16 texts per request · fewer than 512 tokens per text, counting [CLS]/[SEP]** · "if the server returns a capacity error, wait briefly and retry". Measured: 17 texts → 422 "batch size 17 > maximum allowed batch size 16"; a 722-token text → 422 "must have less than 512 tokens" (not truncated). |
| Supports | chat, streaming, tool calls | embeddings only |
| Errors | 429 and 503: retry after 2, 4 and 8 s, then stop. 400, 401 and 404 are never retried. | capacity error: retry the batch |
| Reranker | **none** | **none** |

**Certificates.** Both are self-signed "Caddy Local Authority – 2026 ECC Root" CAs, valid until 2036, and both are already committed under `dumps/`. TLS verification stays **on**: each client trusts its own CA file.

**Token quota.** The Track B brief mentions "an API key with a per-team token quota". The guide doesn't give a figure. A full e2e run uses about 400K chat tokens (60 × ~6.5K). Ask the coordinator for the quota before step 5.

## 2. What the switch changes

| | `siliconflow` (today) | `upgrad` |
|---|---|---|
| Chat | Qwen3-8B on SiliconFlow | Qwen3-8B on the course endpoint |
| Thinking off | body field `enable_thinking: false` | `chat_template_kwargs: {"enable_thinking": false}` (the usual vLLM form; **confirmed by the probe**, step 1) |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B`, 1,024 d, batches of 32 | `bge-small-en-v1.5`, 384 d, batches of 16 |
| Query format | `Instruct: <task>\nQuery: <q>` | `Represent this sentence for searching relevant passages: <q>` (bge's recommended query prefix) |
| Long chunks | sent whole | split into ≤500-token windows (§3.4) |
| Qdrant collection | `procurement__by_rule` (**unchanged**) | `procurement__by_rule__bge-small-en-v1-5` |
| Reranker | `Qwen3-Reranker-8B` on SiliconFlow | Qwen3-8B on the course chat endpoint, listwise (`UPGRAD_RERANKER=upgrad`), or `none` |
| Chat concurrency | 2 | **1**, the key's limit |
| Cost per token | SiliconFlow prices | $0 (course quota) |
| Content-check judge | DeepSeek-V3.2 on SiliconFlow | not run |
| Results | `docs/results/siliconflow/` | `docs/results/upgrad/` |
| SiliconFlow key | required | not used |

**Unchanged:** documents, chunks (`by_rule`), BM25, corpus hash, eval set v3 and its gold answers, prompts, the planner → executor → critic agent, tools, the 8K budget, the 10-step cap, Langfuse, Docker ports, the web UI.

## 3. Design

### 3.1 `.env`

```bash
# --- provider: siliconflow | upgrad -------------------------------------------------------
PROVIDER=siliconflow

# SiliconFlow: chat, embeddings, rerank. Also the content-check judge, which always uses it.
SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.com/v1

# upgrad course endpoints (group 031-045). Cert paths are relative to this folder.
UPGRAD_CHAT_BASE_URL=https://103.42.50.41:1033/v1
UPGRAD_CHAT_API_KEY=
UPGRAD_CHAT_CA_CERT=certs/vm05-ca.crt
UPGRAD_EMBED_BASE_URL=https://103.42.50.41:1035/v1
UPGRAD_EMBED_API_KEY=
UPGRAD_EMBED_CA_CERT=certs/vm02-ca.crt
UPGRAD_RERANKER=upgrad        # upgrad: Qwen3-8B (course chat) ranks the top-20 | none
```

- `LLM_PROVIDER` becomes `PROVIDER`, because it now switches embeddings as well as chat. The old name is still read as an alias, so an existing `.env` keeps working. The old value `course` fails with "use `upgrad`".
- Model ids aren't in `.env`. Each provider serves fixed models, so they live in the provider profile in code (§3.2). The chat model is `Qwen/Qwen3-8B` on both.
- **Fail fast at startup.** With `PROVIDER=upgrad`, a missing key or a missing certificate file stops the API with a message that names the variable. Keys are never printed.
- **Certificates:** copy both `.crt` files into `final-capstone-project/demo/swateek/certs/`. They're public CA certificates and are already in git under `dumps/`. Relative paths resolve against the project folder, so the same `.env` works on the host and in Docker. Compose mounts `./certs:/app/certs:ro`.

### 3.2 One provider profile

`copilot/llm/providers.py` returns a `ProviderProfile` with three parts. Everything else reads the profile instead of checking the provider name.

| Part | Fields |
|---|---|
| `chat` | base URL, key, model, CA path, max concurrency, requests/min, `extra_body` (thinking off) |
| `embedding` | base URL, key, model, CA path, dimensions, batch size, max tokens per text, query prefix style |
| `rerank` | SiliconFlow `Qwen/Qwen3-Reranker-8B` (`rerank_api`); under upgrad, Qwen3-8B on the course chat endpoint (`chat_listwise`, sharing the chat gate), or `None` |

**Modularity.** `domain.yaml` keeps what belongs to the domain: the query instruction and `top_k`. `embedding_model` and `reranker_model` move into the profile, because they're tied to what each provider serves. Swapping to HR policy is still "replace the documents and re-embed". Changing provider is "set `PROVIDER` and build its index once".

### 3.3 TLS and the concurrency-1 gate

- One `httpx.Client` per endpoint, with `verify=ssl.create_default_context(cafile=<CA>)`. There's no option to turn verification off.
- **Gate every chat request.** Today, agent calls go through `call_with_retry` in `BudgetMiddleware` with no `RateGate`, and the critic's model call has neither a gate nor a retry. A two-person conversation, or the critic overlapping another call, would hit 429 on the course key. Put the gate inside the HTTP transport (an `httpx` transport wrapper that holds a process-wide semaphore until the response body is closed), so every caller is covered: harness, critic, baseline, evals. Concurrency is 1 under `upgrad` and 2 under `siliconflow`.
- **Teammates share the key.** The gate covers one process. Other people using the key can still cause 429s, which the 2/4/8 s retry absorbs only if they finish quickly. Agree a window for eval runs, and keep the demo machine the key's only user during the demo.

### 3.3a The `upgrad` reranker: Qwen3-8B, listwise

The course has no reranker and Track B requires one, so `ChatReranker` (`copilot/retrieval/rerank.py`) asks Qwen3-8B on the course chat endpoint to order the fused top-20:

- **One chat call per search.** The prompt holds the question, the domain's task line and the 20 passages, numbered. The model replies with the numbers of the top 5, best first (`max_tokens` 40, thinking off).
- **It fits the 8K window.** Each passage is cut to at most 300 Qwen tokens, and less if 20 of them wouldn't fit. A test checks the worst case.
- **It never breaks retrieval.** Duplicate or out-of-range numbers are dropped, and the list is filled from the fused order. A reply with no usable number keeps the fused order, which is logged and counted (`fallbacks`).
- **It's gated with chat.** It uses the same endpoint and the same process-wide gate, so it never overlaps an agent call on the one-request key. Its tokens are recorded as rerank tokens.
- **What it costs.** Every search adds one chat call, so latency rises by one 8B call, typically a few seconds. A 20-passage prompt is roughly 5–6K tokens, which counts against the team quota.
- **Measured:** recall 0.66 / 0.95 / 0.97 at k = 1 / 5 / 10, against 0.68 / 0.97 / 0.97 for hybrid alone. It uses about 5.7K tokens per search (218K for 38) and never needed the fallback (`docs/results/upgrad/retrieval-by_rule--qwen3-8b-listwise.md`).

### 3.4 Embeddings: long chunks

Measured on `by_rule.jsonl` with the bge tokenizer:

| Chunks | bge tokens: median | p95 | max | Over 512 |
|---|---|---|---|---|
| 1,690 | 468 | 646 | 2,824 | **780 (46%)** |

The chunks were sized in Qwen tokens (max 686). bge's WordPiece counts more tokens for the same text, so nearly half exceed the endpoint's 512.

**Recommended: windows, not new chunks.** Split each chunk over 500 bge tokens into windows of up to 500 tokens with 64 tokens of overlap, using the tokenizer's offsets, and embed each window as its own Qdrant point carrying the chunk's id. Search fetches 3 × k points and keeps each chunk's best window score. That's about **2,489 vectors in 156 requests**.

What this keeps the same:
- chunk ids;
- citations;
- BM25;
- the corpus hash;
- the eval gold.

Only the dense index differs between providers, so the two runs stay comparable. The alternative, re-chunking to 512 bge tokens, would change chunk ids for both providers and invalidate the SiliconFlow retrieval numbers.

The bge tokenizer (`BAAI/bge-small-en-v1.5` `tokenizer.json`) loads the same way as the Qwen one: no PyTorch.

### 3.5 Indexes and cache

- **Collection names:** SiliconFlow keeps its original `<domain>__<chunker>`, so its existing index is used as-is. Other providers get a suffix: `<domain>__<chunker>__bge-small-en-v1-5`. Both live in the same Qdrant, so switching needs no rebuild.
- `DenseStore.check()` already refuses an index built with a different model or corpus. That guard stays.
- Index metadata: SiliconFlow keeps `by_rule.index.json`; upgrad writes `by_rule.upgrad.index.json`.
- **Retrieval cache:** the key already includes the embedding and reranker models, so cached results from the two providers never mix.

### 3.6 Results directories

```
docs/results/
  eval-freeze.md            shared (the eval set is the same for both)
  siliconflow/              the SiliconFlow results, with their own eval-report.md
  upgrad/                   probe, retrieval, e2e, safety, preflight on the course endpoints, with their own eval-report.md
```

- `e2e`, `retrieval`, `safety`, `judge` and `demo_preflight` write to `docs/results/<provider>/`. `--rescore` takes a file name in that directory.
- Every results file's header names the provider, the endpoint host (never the key), the chat, embedding and reranker models, and the collection. Langfuse traces are tagged `upgrad` or `siliconflow` (the provider tag exists today).
- Moving today's files means updating links in: `eval-report.md`, the three review sheets, `docs/report/report.md` (then rebuild the HTML and PDF), `README.md`, `AGENTS.md`, `implementation-plan.md`, `small-model-log.md`, `docs/demo/*`, `docs/report/make_figures.py` and `to-do.md`.

### 3.7 File by file

| File | Change |
|---|---|
| `config.py` | `provider` (alias `LLM_PROVIDER`), `upgrad_*` settings, `upgrad_reranker`; resolve cert paths against the project folder; remove `course` |
| `llm/providers.py` | `ProviderProfile` (§3.2); TLS clients; startup validation |
| `llm/retry.py` | gating transport (§3.3); one gate per endpoint per process |
| `agent/harness.py` | `ChatOpenAI(..., http_client=...)` from the profile; the critic shares it, so it's gated too |
| `answer.py`, `eval/baseline.py`, `eval/prompts.py` | use the profile's client. The CoT experiment (`thinking_budget`) is SiliconFlow-only and isn't re-run |
| `retrieval/embed.py` | profile-driven URL, key, TLS, batch size and query prefix; windowing (§3.4); no `dimensions` field for bge |
| `retrieval/dense.py` | collection suffix per provider (none for SiliconFlow); point id `uuid5(chunk_id#window)`; best window per chunk at search |
| `retrieval/rerank.py` | `Reranker` (SiliconFlow `/rerank`) and `ChatReranker` (Qwen3-8B listwise on the course chat endpoint); `make_reranker` picks one from the profile |
| `tools/registry.py` | models from the profile; cache key unchanged in shape |
| `ingest/index.py` | indexes the active provider into its own collection; SiliconFlow's name and metadata file are unchanged |
| `eval/e2e.py`, `eval/safety.py`, `eval/retrieval.py`, `eval/demo_preflight.py` | results under `docs/results/<provider>/`; prices per provider; provider details in the header |
| `eval/judge.py` | always on SiliconFlow (its own client, not `get_provider`); **refuses a run whose provider is `upgrad`**, with a one-line reason |
| `llm/budget.py` | re-check the per-message and tool-template overheads against the course endpoint's `usage.prompt_tokens` (probe) |
| `api/app.py` `/health` | provider, chat model, embedding model, collection and point count, reranker |
| `docker-compose.yml` | mount `./certs`; the ingest job indexes the active provider |
| `env.sample`, `README.md`, `AGENTS.md`, `implementation-plan.md` §6.2 | new variables; group 031–045 confirmed; "no embeddings" replaced by the embedding endpoint |
| New: `copilot/llm/probe.py` | step 1 |

**Tests (offline, no network):**
- the provider factory for both providers;
- verification is never off, and a missing cert fails at startup;
- `upgrad` uses concurrency 1 and gates the critic's call;
- embedding batches are ≤16 and every window is ≤500 tokens;
- dense search keeps one hit per chunk;
- SiliconFlow keeps its collection name; upgrad gets its own;
- the listwise reranker: follows the model's order, keeps the fused order on a useless reply, and its prompt fits the window;
- `upgrad` never needs a SiliconFlow key;
- cache keys differ per provider;
- the judge refuses an `upgrad` run;
- results paths are per provider.

## 4. Steps and status

| # | Step | Status |
|---|---|---|
| 0 | Keys in `.env` (embedding key copied from `dumps/`, group key added by you); certificates copied to `certs/` | done |
| 1a | Probe, embeddings half | **done** (before the no-calls rule). 384 d; 16 texts OK; 17 → 422; ≥512 tokens → 422. `docs/results/upgrad/probe.md` |
| 1b | Probe, chat half | **done** (your go-ahead). All passed: model `Qwen/Qwen3-8B`; thinking off with `chat_template_kwargs`, with `enable_thinking` and with no flag; tool call; strict `json_schema`; streamed usage; our token estimate 35 vs server 35 (178 vs 187 with a tool: errs high, safe); `max_tokens=1025` → 400; about 0.5 s per short call. No fallback needed. |
| 2 | Code and tests; today's results moved to `docs/results/siliconflow/` with links updated | **done**: 97 tests pass, offline |
| 3 | upgrad index: 1,690 chunks → 2,489 vectors (794 chunks windowed), 754K tokens, 159 s | **done** on the host (before the no-calls rule). The SiliconFlow index is untouched. |
| 4a | Retrieval eval, upgrad embeddings, with the SiliconFlow reranker as a reference point (table below) | **done** (before the no-calls rule) |
| 4b | Retrieval eval with the `upgrad` listwise reranker | **done** (your go-ahead): 0.66 / 0.95 / 0.97, slightly below hybrid alone; 218K chat tokens for 38 searches (~5.7K each); 0 fallbacks. **Kept** (your decision): it meets Track B's "a reranker", and the report states both numbers. |
| 5 | e2e (60), safety probes (7), demo preflight ×2 on `upgrad`. No judge. | **done** (your go-ahead, 14 Nov): two full runs, **55/60** each (58 of 60 answers identical); safety 7/7; preflight 9/10 twice. The first run1 attempt stopped at question 47 on a scorer bug (fixed; no outcome changes) and was repeated in full. |
| 6 | Reports | **done**: `docs/results/upgrad/eval-report.md` and the technical report `docs/report/upgrad/report.pdf`, each with SiliconFlow run 5 as the reference. The SiliconFlow reports moved under `siliconflow/` folders, content unchanged. |
| 7 | Docker: index for the stack | **done.** Image rebuilt. Both collections were copied from the host with `copilot.ingest.copy_index` (no API calls), and the chunk files were copied into the data volume. The stack serves **`upgrad`** (since 14 Nov). |
| 8 | Chunking comparison on bge (fixed_512, recursive_800) | **done** (your go-ahead): two new collections (SiliconFlow's untouched); recall@5 0.71 and 0.79 against 0.95 for by_rule |
| 9 | Langfuse screenshots of the `upgrad` runs | **done**: `docs/demo/traces/upgrad/`, in the upgrad report's Appendix E |

**Retrieval recall (38 labelled questions, eval v3 gold; k = 1 / 5 / 10):**

| Mode | SiliconFlow | upgrad embeddings |
|---|---|---|
| BM25 | 0.40 / 0.84 / 0.92 | 0.40 / 0.84 / 0.92 |
| dense | 0.60 / 0.87 / 1.00 | 0.47 / 0.90 / 0.95 |
| hybrid | 0.63 / 0.97 / 1.00 | 0.68 / 0.97 / 0.97 |
| hybrid + Qwen3-Reranker-8B (SiliconFlow) | 0.79 / 1.00 / 1.00 | 0.74 / 0.97 / 0.97 (reference only; not used under `upgrad`) |
| hybrid + Qwen3-8B listwise (course chat) | — | 0.66 / 0.95 / 0.97 |

Files:
- `docs/results/siliconflow/retrieval-by_rule--qwen3-reranker-8b--eval-v3.md`: a SiliconFlow re-run on the v3 gold. The original v1 table is unchanged.
- `docs/results/upgrad/retrieval-by_rule--qwen3-reranker-8b.md`.

## 4a. Review: other things to consider

Done in the review:
- **Rerank cost.** Under `upgrad`, rerank tokens are now priced at $0; they were left at the SiliconFlow price.
- **The listwise rerank call is visible and budgeted.** It's recorded as a `rerank` event in the agent run (tokens, seconds, fallback). Its tokens count toward the 40K per-query token cap but not the 10-step cap, per your decision: it's part of the search tool. e2e rows report them once, under `rerank_tokens`.
- **Over-long queries.** A search query too long for the embedding endpoint is now cut to fit, instead of failing with a 422 (never retried).
- **Probe labels.** The probe now marks the endpoint's documented rejections (17 texts, ≥512 tokens) as passing checks; re-run on 14 Nov, 13/13.
- **Tests.** Three new ones (100 in total).

Still to keep in mind:
- **One key, two processes.** A host eval (`uv run python -m eval.e2e` with `PROVIDER=upgrad`) and the Docker API on `upgrad` share the same course key. The gate covers one process only, so they'd collide with 429s. Run evals with the Docker API on `siliconflow`, or stopped.
- **Corpus changes rebuild both indexes.** If the chunks change, the corpus hash changes, and both collections are refused as stale until each is rebuilt: `PROVIDER=siliconflow` and `PROVIDER=upgrad` `copilot.ingest.index`. The upgrad rebuild calls the embedding endpoint, so it needs your go-ahead.
- **A domain switch needs an index per provider.** HR policy would need `hr_policy__by_rule` (SiliconFlow) and `hr_policy__by_rule__bge-small-en-v1-5` (upgrad).
- **Docker and the host have separate Qdrants.** After a host rebuild, copy it into Docker with `copilot.ingest.copy_index --replace`.
- **SiliconFlow-only experiments.** The CoT prompt experiment (`eval.prompts`, `thinking_budget`) and the judge are SiliconFlow-only, and aren't run on `upgrad`.
- **The thinking default differs.** On the course server, thinking is off even with no flag, while SiliconFlow defaults it to on. Both paths send it explicitly off.
- **bge query prefix.** It wasn't A/B-tested. bge's recommended prefix is used as published.

## 5. Demo with two providers

- **The demo runs on `upgrad`** (`PROVIDER=upgrad` in `.env`); SiliconFlow is the fallback, and both indexes are built in Docker. `docs/demo/demo-script.md` has the checklist.
- **Fallback in under a minute:** change `PROVIDER` in `.env`, run `docker compose up -d api`, then check `"provider"` in `curl localhost:3401/health`. No re-index is needed.
- **Day before:** `docker compose up -d --build`, then run the preflight twice on the demo provider and once on the fallback. Check the SiliconFlow balance, which matters for the fallback.
- **During the demo:** no one else on the team uses the course key. Demo week is when every group is presenting, and VM05 allows 15 active requests in total, so expect it to be slower than on a quiet day.

## 6. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| A teammate uses the key at the same time | 429; a slow or failed turn | the gate plus 2/4/8 s retry; agreed eval windows; one demo machine |
| The VM is busy in demo week | slow answers or 503s | preflight 30 min before; switch to SiliconFlow in under a minute |
| The thinking flag isn't honoured | long `<think>` output eats `max_tokens` and the 8K budget | **resolved by the probe**: thinking is off in every form tried |
| No strict `json_schema` | the critic's advisory call fails | **resolved by the probe**: strict `json_schema` works |
| bge-small retrieves worse than Qwen3-Embedding-0.6B (384 d, English, 512 tokens) | lower recall, more retrieval misses | measured: dense is lower at k = 1, but hybrid recall@5 is 0.97 on both providers; BM25 is unchanged |
| The listwise reranker is slower and weaker than a cross-encoder | each search takes a few seconds longer; ordering may be worse than hybrid alone | measure it (4b); fall back to `UPGRAD_RERANKER=none`, which keeps recall@5 at 0.97 |
| The embedding endpoint is shared by all groups | capacity errors while indexing | retry the batch; indexing happens once |
| Unknown team token quota | the quota runs out mid-run | measured: about 742K tokens per full e2e run (agent + rerank); results are now saved per question, so an interrupted run keeps its answers |
| A key leaks into a results file, trace or screenshot | key exposure | keys come only from `.env` as `SecretStr`; headers show the host only; the guide says to ask for a replacement if exposed |

## 7. Still open

Nothing for the switch itself. Findings from the runs that are not fixed (reported in the upgrad report §8 and §12): S-005's three-word request skips the no-tool check; B-010 screens invented bidder names; B-004 leaves out the withheld bidder; B-015 releases an empty answer at the step cap, and the scorer counts it as a refusal.
