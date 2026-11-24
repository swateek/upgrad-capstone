# Retrieval recall: `by_rule` chunks (upgrad)

2026-11-13T19:29:27+00:00 · provider upgrad · 38 labelled questions · bge-small-en-v1.5 · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-Reranker-8B on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.40 | 0.84 | 0.92 |
| dense | 0.47 | 0.90 | 0.95 |
| hybrid | 0.68 | 0.97 | 0.97 |
| hybrid_rerank | 0.74 | 0.97 | 0.97 |

hybrid_rerank misses at k=10: P-013
