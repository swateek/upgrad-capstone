# Retrieval experiment (Days 5–7)

Run on the Mac, 21 Nov 2026. 60 retrieval queries (`eval/retrieval_queries.yaml`, gold `citation_id`s fixed before any run, 3 crew-rule traps), 742 corpus documents, chunked by real `bge-small-en-v1.5` tokens. A query counts as a hit at k if any chunk in the top k carries a gold `citation_id`. Tables: `results/retrieval_experiment.csv` (24 configurations), `results/retrieval_per_query.csv`.

Retrieval is measured on its own query set, never on `eval-v2` (rule 6).

## Results at 350 tokens (1,480 chunks), hard-negative filter on

| Method | R@1 | R@3 | R@5 | R@10 | MRR@10 | Hard neg. in top 3 | Traps hit@3 | ms / query |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BM25 | 0.500 | 0.833 | 0.867 | 0.917 | 0.670 | 0.00 | 3/3 | 1.4 |
| Dense | 0.600 | 0.850 | 0.900 | 0.950 | 0.726 | 0.00 | 2/3 | 1.0 |
| **Hybrid (RRF k=60)** | **0.650** | **0.883** | **0.933** | 0.950 | **0.769** | 0.00 | **3/3** | 2.4 |
| Hybrid + MiniLM reranker | 0.583 | 0.817 | 0.900 | 0.950 | 0.712 | 0.00 | 2/3 | 66.7 |
| **Hybrid + bge-reranker-v2-m3** | **0.733** | **0.917** | **0.950** | **0.967** | **0.831** | 0.00 | **3/3** | 1,553 |

The bge row is from a separate run (`results/retrieval_experiment_bge.csv`, same chunks, same queries, cached embeddings).

Best per chunk size (hybrid, filter on): 200 tokens R@3 0.867 / R@5 0.883; **350 tokens R@3 0.883 / R@5 0.933**; 450 tokens R@3 0.850 / R@5 0.917.

## Decision 1: retriever = hybrid (BM25 + dense, RRF k=60) + `BAAI/bge-reranker-v2-m3` on the top 30

- Hybrid has the best R@1, R@3, R@5 and MRR of the three first-stage methods at every chunk size. BM25 catches exact section numbers and terms ("148.51", "Caribbean Basin"); dense catches paraphrases ("day trip to Mexico"). They miss different queries, so fusing them helps.
- The two rerankers go opposite ways. `ms-marco-MiniLM-L-6-v2` **lowers** R@1 and R@3 at 350 and 450 tokens (R@1 0.650 → 0.583 at 350): against plain hybrid it moved the first gold chunk down on 14 queries and up on 8. It was trained on web search queries (MS MARCO), not regulation text. `bge-reranker-v2-m3` **raises** every metric: R@1 0.650 → 0.733, R@3 0.883 → 0.917, MRR 0.769 → 0.831; up on 15 queries, down on 7. It fixes the Cuban-origin ban (31 CFR 515.204, rank 5 → 1), the day-trip exemption (148.35, 4 → 1) and export-labelled tobacco (26 USC 5761, 9 → 2).
- Cost: ~1.5 s per query on the Mac (CPU/MPS) and a ~2.2 GB model in the Docker image. One question makes one or two searches, and each LLM call already takes seconds, so this is acceptable.
- Caveat: 60 queries, so one query = 0.017. The R@3 gain is 2 queries; the R@1 gain (5 queries) and the three fixed rules are the stronger reasons. The reranker is a setting: plain hybrid remains the fallback if the model cannot load, and stays available as an ablation.

## Decision 2: chunk size = 350 tokens

- 350 has the best R@3 and R@5 of the three sizes with hybrid retrieval; 200 ties on R@1 but loses at R@3/R@5 (sections split into pieces too small to match); 450 loses at R@3 and misses one trap.
- 5 chunks × 350 tokens ≤ 1,750 tokens of context, inside the < 3k input target per call (CLAUDE.md).
- Retrieve **k = 5** for the writer: R@5 0.933 vs R@3 0.883.

## Decision 3: metadata filter before ranking; flat numpy index, no vector database

- Excluding `authority: hard_negative` before ranking takes hard negatives in the top 3 from 0.10–0.20 to 0.00 for every method, and never lowers recall. Kept on for every traveller query.
- The whole dense index is 1,480 × 384 floats (~2.3 MB); brute-force cosine in numpy takes ~1 ms per query. Qdrant would add a container and a service for no measurable gain at this size. The index is saved to a file with the chunk ids so official runs (cache off) do not re-embed the corpus.

## What retrieval still misses (350, filter on)

With plain hybrid, 7 of 60 queries have no gold chunk in the top 3:

| Query | Gold | Rank | What came back instead |
| --- | --- | --- | --- |
| R05 day trip to Mexico, full exemption? | 19 CFR 148.35 | 4 | CBP "types of exemptions" page (same rule, secondary source) |
| R16 can family members pool $200 exemptions? | 19 CFR 148.51 | 4 | 148.34 (family grouping for the $800 exemption: near-duplicate) |
| R21 penalty for re-importing export-labelled tobacco | 26 USC 5761 | 9 | 27 CFR 41.82–83, 26 USC 5754 (neighbouring rules) |
| R26 importer permit for wine for myself? | TTB personal importation | — | 27 CFR 27.140, state pages |
| R36 Mexican tequila free of the flat rate (USMCA) | HTSUS 9816.00.20, GN 3 | — | CBP duty page, 148.101–102 |
| R52 prohibition on Cuban-origin merchandise | 31 CFR 515.204 | 5 | OFAC FAQ, 515.569, 515.560 |
| R60 alcohol for a non-resident visitor | 19 CFR 148.43 | — | state pages (out of scope anyway) |

With the bge reranker, 5 of 60 still miss the top 3: R09 (rank 5), R16 (8: the $800 family-grouping section 148.34 still outranks 148.51), R26 (5), R36 (not in the top 10) and R60 (not in the top 10, out of scope). R05, R21 and R52 are fixed.

Implication for the agent: R36 (and R52 without the reranker) are rules the calculators and `check_restrictions` apply. Those tools already know which rule they used, because every row in `rules.yaml` / `rates.yaml` carries its citation. So `search_regulations` will take two inputs: the citation ids of the rules the tools applied (fetched by id from the index: exact, no ranking) plus free-text search for the rest. The writer still cites only clauses that were retrieved for this question (rule 2), and none of this changes the experiment numbers above, which measure free-text search alone.
