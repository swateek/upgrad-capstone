# upgrad quota log

One line per run that reaches the course endpoints (group 031–045), made only with the user's explicit OK. Never record the key.

| Date (UTC) | Who | What | Chat requests | Embedding requests | Tokens | Notes |
|---|---|---|---|---|---|---|
| 2026-11-17 15:18 | swateek | index embeddings (paragraph, section, window200) | 0 | 221 | 738302 | 3528 new texts; cache now 3528 |
| 2026-11-17 15:28 | swateek | baselines (eval-v1, 4 strategies + intake comparison) | 20 | 0 | 14198 | run took 1 min |
| 2026-11-17 15:30 | swateek | baselines (eval-v1), partial: stopped by the user, resumable | 15 | 0 | 11391 | 1 scenarios complete; the item in flight at the stop was not saved (its calls are not counted) |
| 2026-11-17 18:07 | swateek | baselines (eval-v1, 4 strategies + intake comparison) | 889 | 0 | 639401 | run took 64 min |
| 2026-11-18 00:09 | swateek | retrieval experiment: query embeddings | 0 | 44 | 39966 | 702 query texts (prefix on + off) |
| 2026-11-18 00:49 | swateek | retrieval experiment: listwise rerank (dev) | 45 | 0 | 179851 | base window200 / hybrid / on / qr / topic; run took 1 min |
