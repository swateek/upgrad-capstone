# Questions for the programme office (via the mentor)

Option 1 of the mentor note. Answers to Q1–3 are pre-filled from our own check (`results/endpoint_check.txt`, run 2026-11-17 08:10 UTC). Each one asks the office only to confirm, or to fill a gap. Q4 and Q5 only the office can answer.

---

For the Track B capstone endpoints (group 031–045: chat `103.42.50.41:1033`, embeddings `103.42.50.41:1035`):

1. **Chat model and context length.** `/v1/models` lists one model, `Qwen/Qwen3-8B`, with `max_model_len` 8192. Is that the exact checkpoint served (which revision or quantisation)? Is 8192 the intended context length (input + output)?
2. **Embeddings model and dimension.** The embedding endpoint publishes no model name (`/v1/models` and `/info` both return 404). It returns 384-dimensional vectors, accepts at most 16 texts per request, and refuses texts of 512 tokens or more. That matches `bge-small-en-v1.5`. Please confirm the model name and version.
3. **Tools and JSON output.** Confirmed on our side: native tool calls (`tool_choice` auto 5/5, plus `required` and named), `response_format` with strict `json_schema`, and `json_object`. Thinking is off by default; `chat_template_kwargs.enable_thinking=false` is also accepted. Should we expect these settings to stay the same through the demo week?
4. **Quota and price.** What is the per-team token quota, and what price per million tokens (input and output) should we use for the cost metric?
5. **Rate limits.** What are the requests-per-minute and tokens-per-minute limits? We work to one active request per group key (from the Track B guide) and `max_tokens` ≤ 1024 (the server refuses 1025 with a 400). Are there any other limits?
