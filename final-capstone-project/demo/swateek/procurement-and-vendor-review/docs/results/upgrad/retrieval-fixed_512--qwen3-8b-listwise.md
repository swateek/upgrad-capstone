# Retrieval recall: `fixed_512` chunks (upgrad)

2026-11-14T08:15:18+00:00 · provider upgrad · 38 labelled questions · bge-small-en-v1.5 · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-8B (listwise) on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.40 | 0.66 | 0.82 |
| dense | 0.42 | 0.63 | 0.79 |
| hybrid | 0.50 | 0.71 | 0.79 |
| hybrid_rerank | 0.47 | 0.71 | 0.76 |

hybrid_rerank misses at k=10: P-009, P-013, P-019, P-023, RL-001, RL-002, RL-007, RL-009, RL-015
