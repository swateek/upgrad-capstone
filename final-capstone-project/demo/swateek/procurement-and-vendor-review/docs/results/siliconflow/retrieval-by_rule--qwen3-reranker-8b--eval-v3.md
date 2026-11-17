# Retrieval recall: `by_rule` chunks (siliconflow, eval v3 gold; re-run for the provider comparison)

2026-11-13T19:31:14+00:00 · provider siliconflow · 38 labelled questions · Qwen/Qwen3-Embedding-0.6B · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-Reranker-8B on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.40 | 0.84 | 0.92 |
| dense | 0.60 | 0.87 | 1.00 |
| hybrid | 0.63 | 0.97 | 1.00 |
| hybrid_rerank | 0.79 | 1.00 | 1.00 |

hybrid_rerank misses at k=10: none
