# Phase 3: prompt-strategy comparison (policy questions)

2026-11-13T05:40:24+00:00 · siliconflow `Qwen/Qwen3-8B` · temperature 0 · retrieval by_rule + hybrid + `Qwen/Qwen3-Reranker-8B` top-5 (same sources for every strategy except decompose, which retrieves per planned lookup)

| Metric | plain | structured | structured_strict | cot | decompose |
|---|---|---|---|---|---|
| Cites an acceptable gold source (factual) | 21/23 | 20/23 | 21/23 | 23/23 | 14/23 |
| Refusal handled correctly (all 25) | 22/25 | 23/25 | 24/25 | 22/25 | 20/25 |
| Answers with an uncited sentence | 4/25 | 0/25 | 4/25 | 10/25 | 2/25 |
| Answers with an invalid source handle | 0/25 | 0/25 | 1/25 | 1/25 | 0/25 |
| Schema-valid first try | – | 24/25 | 25/25 | – | – |
| Schema-valid after one retry | – | 24/25 | 25/25 | – | – |
| Mean model calls | 1.0 | 1.0 | 1.0 | 1.0 | 5.0 |
| Mean tokens per question | 2972 | 3448 | 3337 | 3437 | 3113 |
| Mean latency (s) | 3.6 | 4.9 | 5.5 | 18.8 | 6.6 |

Auto metrics only. Where each strategy breaks is written up by hand in `docs/small-model-log.md`.
