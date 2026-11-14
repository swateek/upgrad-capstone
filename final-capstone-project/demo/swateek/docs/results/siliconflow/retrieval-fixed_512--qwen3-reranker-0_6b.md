# Retrieval recall: `fixed_512` chunks

2026-11-13T04:53:50+00:00 · 38 labelled policy questions · Qwen/Qwen3-Embedding-0.6B · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-Reranker-0.6B on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.37 | 0.60 | 0.76 |
| dense | 0.53 | 0.71 | 0.84 |
| hybrid | 0.53 | 0.82 | 0.84 |
| hybrid_rerank | 0.55 | 0.82 | 0.87 |

hybrid_rerank misses at k=10: P-013, P-023, RL-003, RL-007, RL-009
