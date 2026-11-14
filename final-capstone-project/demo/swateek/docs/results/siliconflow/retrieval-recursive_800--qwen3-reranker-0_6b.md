# Retrieval recall: `recursive_800` chunks

2026-11-13T04:57:02+00:00 · 38 labelled policy questions · Qwen/Qwen3-Embedding-0.6B · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-Reranker-0.6B on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.29 | 0.63 | 0.76 |
| dense | 0.42 | 0.71 | 0.82 |
| hybrid | 0.50 | 0.82 | 0.87 |
| hybrid_rerank | 0.53 | 0.84 | 0.84 |

hybrid_rerank misses at k=10: P-007, P-009, P-011, P-023, RL-007, RL-009
