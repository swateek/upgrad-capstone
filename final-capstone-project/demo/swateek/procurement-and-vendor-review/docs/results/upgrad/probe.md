# upgrad endpoint probe

2026-11-14T07:26:26+00:00 · chat `103.42.50.41:1033` · embeddings `103.42.50.41:1035` · chat: probed

| Check | OK | Seconds | Detail |
|---|---|---|---|
| embed: 1 text | yes | 0.35 | {"vectors": 1, "dimensions": 384, "usage": {"prompt_tokens": 5, "total_tokens": 5}} |
| embed: 16 texts | yes | 0.11 | {"vectors": 16, "dimensions": 384, "usage": {"prompt_tokens": 64, "total_tokens": 64}} |
| embed: 17 texts (limit 16) is refused | yes | 0.03 | {"expected": "rejected", "status": 422, "error": "{'message': 'batch size 17 > maximum allowed batch size 16', 'code': 422, 'type': 'Validation'}"} |
| embed: 802-token text (limit 512) is refused | yes | 0.04 | {"expected": "rejected", "status": 422, "error": "{'message': 'Input validation error: `inputs` must have less than 512 tokens. Given: 802', 'code': 422, 'type': 'Validation'}", "bge_tokens": 802} |
| chat: list models | yes | 0.12 | {"models": ["Qwen/Qwen3-8B"]} |
| chat: thinking off (chat_template_kwargs) | yes | 0.5 | {"thinking_seen": false, "completion_tokens": 19, "finish": "stop", "answer": "A reranker reorders or prioritizes items in a list based on relevance or importance."} |
| chat: thinking off (enable_thinking) | yes | 0.46 | {"thinking_seen": false, "completion_tokens": 19, "finish": "stop", "answer": "A reranker reorders or prioritizes items in a list based on relevance or importance."} |
| chat: no thinking flag (default) | yes | 0.47 | {"thinking_seen": false, "completion_tokens": 19, "finish": "stop", "answer": "A reranker reorders or prioritizes items in a list based on relevance or importance."} |
| chat: prompt-token estimate | yes | 1.13 | {"server_prompt_tokens": 35, "our_estimate": 35, "server_with_tool": 178, "our_estimate_with_tool": 187} |
| chat: tool call | yes | 0.55 | {"tool_calls": ["lookup_record"], "arguments": {"name": "Acme Traders"}} |
| chat: strict json_schema | yes | 0.97 | {"parsed": {"passed": true, "reason": "The draft is clear and concise. It effectively communicates the rule allowing purchases up to Rs 50,000 without quotations."}} |
| chat: streamed usage | yes | 0.47 | {"chunks": 21, "usage": {"completion_tokens": 19, "prompt_tokens": 24, "total_tokens": 43, "completion_tokens_details": null, "prompt_tokens_details": null}} |
| chat: max_tokens=1025 refused | yes | 0.1 | {"status": 400} |
