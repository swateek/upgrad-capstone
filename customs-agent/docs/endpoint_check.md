# Endpoint capability check

- **Run at:** 2026-11-21 11:12 IST
- **openai library:** 3.57.0

| Endpoint | Host | Model | TLS |
| --- | --- | --- | --- |
| Chat (LLM) | `103.42.50.41:1033` | `Qwen/Qwen3-8B` | custom CA: vm05-ca.crt |
| Embeddings | `103.42.50.41:1035` | `bge-small-en-v1.5` | custom CA: vm02-ca.crt |

## Summary

| Check | Result | Detail | Latency |
| --- | --- | --- | --- |
| chat: TLS | **INFO** | custom CA: vm05-ca.crt |  |
| chat: models | **OK** | Qwen/Qwen3-8B | 50 ms |
| chat: model used | **INFO** | Qwen/Qwen3-8B |  |
| chat: tools | **OK** | structured tool call in 3/3 tries |  |
| chat: json_schema | **OK** | {"city": "Mumbai", "state": "Maharashtra"} | 465 ms |
| chat: json_object | **OK** | {"city": "Mumbai", "state": "Maharashtra"} | 461 ms |
| chat: usage reported | **OK** | prompt=15, completion=3, total=18 | 94 ms |
| embeddings: TLS | **INFO** | custom CA: vm02-ca.crt |  |
| embeddings: models | **FAILED** | NotFoundError: Error code: 404 |  |
| embeddings | **OK** | model=bge-small-en-v1.5, dimension=384 | 22 ms |

## What to do next

1. Develop locally on the same model family as `Qwen/Qwen3-8B` (Ollama or vLLM) and write the name in `../docs/SPEC.md`.
2. Tools: native tool calling works. Use the `tools` parameter in the planner; still validate arguments with Pydantic.
3. JSON: constrained decoding works. Use `json_schema` for planner, writer and verifier outputs; record "with vs. without" as an experiment.
4. Embeddings: configure the vector store with 384 dimensions (model=bge-small-en-v1.5).
5. Usage: log `prompt_tokens` and `completion_tokens` per call in `src/llm.py` for the cost metric and quota log.
6. `src/llm.py`: keep two clients built with `Endpoint` + `make_client()` from this script: one for chat, one for embeddings, each with its own key and certificate.
7. Copy every finding into `../docs/COMPENSATIONS.md`; they feed the graded section "What did we do to compensate for a small model?".

## Token usage (for the quota log)

| Call | Prompt | Completion | Total |
| --- | --- | --- | --- |
| tools #1 | 158 | 21 | 179 |
| tools #2 | 158 | 21 | 179 |
| tools #3 | 158 | 21 | 179 |
| json_schema | 20 | 20 | 40 |
| json_object | 25 | 20 | 45 |
| usage | 15 | 3 | 18 |
| embeddings | 8 | 0 | 8 |
| **All calls** | | | **648** |

## Raw responses

<details><summary>chat: tools</summary>

```
try 1 (495 ms): get_weather({"city": "Pune"})
try 2 (485 ms): get_weather({"city": "Pune"})
try 3 (486 ms): get_weather({"city": "Pune"})
```

</details>

<details><summary>chat: json_schema</summary>

```
{
  "city": "Mumbai",
  "state": "Maharashtra"
}
```

</details>

<details><summary>chat: json_object</summary>

```
{
  "city": "Mumbai",
  "state": "Maharashtra"
}
```

</details>


## Still to confirm with the programme office

- Per-team token quota and price per million tokens, for chat and for embeddings (cost metric).
- Rate limits (requests and tokens per minute) for each endpoint.
- Chat context length (expected 8,192 tokens per call, 1,024 max output) and the embeddings input limit.
