# Retrieval recall: `recursive_800` chunks (upgrad)

2026-11-14T08:16:09+00:00 · provider upgrad · 38 labelled questions · bge-small-en-v1.5 · BM25 and dense top-20, RRF k=60 · reranker Qwen/Qwen3-8B (listwise) on the fused top-20

| Mode | recall@1 | recall@5 | recall@10 |
|---|---|---|---|
| bm25 | 0.29 | 0.68 | 0.79 |
| dense | 0.47 | 0.58 | 0.76 |
| hybrid | 0.45 | 0.76 | 0.84 |
| hybrid_rerank | 0.53 | 0.79 | 0.82 |

hybrid_rerank misses at k=10: P-007, P-009, P-013, P-023, RL-007, RL-009, RL-015
