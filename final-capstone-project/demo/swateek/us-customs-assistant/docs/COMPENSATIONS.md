# What we did to compensate for a small model

The graded Track B section. One row per finding, from the first step: what broke, what fixed it, and the metric before and after. Carried-over lessons from the reference app (`../procurement-and-vendor-review/docs/small-model-log.md`) are marked "reference" until they are measured here.

| # | Date | Symptom | Compensation | Before → after | Evidence |
|---|---|---|---|---|---|
| 1 | 17 Nov | Reference: Qwen3 thinking mode multiplies output tokens (~14×) | Thinking off on every call (`chat_template_kwargs.enable_thinking=false`) | reference | `backend/src/customs/llm/endpoints.py` |
| 2 | 17 Nov | Reference: the token estimator under-counted tool prompts by ~40% | Calibrated estimator (+7 per message, +85 with tools), checked before every call | reference | `tests/test_token_estimate.py` |
| 3 | 17 Nov | Reference: malformed JSON from the 8B model | Strict `json_schema` + Pydantic validation + 2 retries with the error fed back, then escalate | to measure (constrained decoding with vs without) | `tests/test_chat.py` |
