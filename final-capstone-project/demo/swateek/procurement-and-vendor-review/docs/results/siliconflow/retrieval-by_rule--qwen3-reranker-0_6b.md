# Retrieval recall: `by_rule` chunks

2026-11-13T04:50:40+00:00 · 38 labelled policy questions · Qwen/Qwen3-Embedding-0.6B · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-Reranker-0.6B on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.40 | 0.79 | 0.90 |
| dense | 0.53 | 0.87 | 1.00 |
| hybrid | 0.60 | 0.92 | 0.97 |
| hybrid_rerank | 0.60 | 0.95 | 0.97 |

hybrid_rerank misses at k=10: P-011
