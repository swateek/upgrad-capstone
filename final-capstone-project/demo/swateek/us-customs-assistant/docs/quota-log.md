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
| 2026-11-18 01:52 | swateek | agent run dev-01 (dev, planner) | 87 | 17 | 73773 | run took 7 min |
| 2026-11-18 03:38 | swateek | agent run dev-02 (dev, planner) | 84 | 18 | 74828 | run took 9 min |
| 2026-11-18 03:52 | swateek | agent run dev-03 (dev, planner) | 63 | 13 | 57464 | run took 6 min |
| 2026-11-18 04:02 | swateek | agent run dev-04 (dev, planner) | 77 | 17 | 70946 | run took 7 min |
| 2026-11-18 04:11 | swateek | agent run dev-05 (dev, planner) | 68 | 17 | 64742 | run took 6 min |
| 2026-11-18 04:52 | swateek | live smoke test via UI proxy (Docker, 6 turns) | 18 | 5 | 18901 | Italy clarify+answer+fact edit, Cuban, Dubai, Tijuana; 2 wrong (see dev-runs.md) |
| 2026-11-18 05:01 | swateek | agent run dev-06 (dev, planner) | 72 | 17 | 74509 | run took 6 min |
| 2026-11-18 05:06 | swateek | live smoke test 2 via UI proxy (Docker, agent v2) | 18 | 4 | 20400 | 6 turns + 2 Tijuana probes; last probe tokens estimated (~960); all answers right; Tijuana still asks (fixed after, offline) |
| 2026-11-18 05:13 | swateek | agent run dev-07 (dev, planner) | 71 | 17 | 73100 | run took 6 min |
| 2026-11-18 05:14 | swateek | live smoke: Tijuana question (Docker, agent v3) | 4 | 1 | 3587 | Mexico land crossing: $800, nothing owed (correct) |
