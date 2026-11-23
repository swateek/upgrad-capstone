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
| 2026-11-18 05:31 | swateek | red-team against the live app (Docker) | 9 | 0 | 0 | 22 attacks; tokens not tracked per item; 1 min |
| 2026-11-18 05:33 | swateek | safety suite live probes | 18 | 7 | 18479 | 8 probes; 1 min |
| 2026-11-18 05:45 | swateek | agent run dev-08 (dev, planner) | 71 | 17 | 73123 | run took 6 min |
| 2026-11-18 05:49 | swateek | red-team against the live app (Docker) | 7 | 0 | 0 | 22 attacks; tokens not tracked per item; 1 min |
| 2026-11-18 05:50 | swateek | safety suite live probes | 21 | 8 | 21773 | 8 probes; 1 min |
| 2026-11-18 07:07 | swateek | agent run planner-1 (frozen, planner), PARTIAL: paused by the user | 263 | 66 | 280917 | 65 of 80 scenarios saved; the scenario in flight at the pause was not saved (its calls are not counted); resumable |
| 2026-11-18 10:28 | swateek | agent run planner-1 (frozen, planner) | 21 | 4 | 20907 | run took 2 min |
| 2026-11-18 10:28 | swateek | agent run planner-1-corr, CRASHED (harness bug: second Qdrant client) | 2 | 0 | 0 | estimated: intake + planner of CR01 turn 1 before the crash; tokens unknown; scenario not saved |
| 2026-11-18 10:33 | swateek | agent run planner-1-corr (corrections, planner) | 40 | 12 | 45731 | run took 4 min |
| 2026-11-18 10:56 | swateek | agent run planner-2 (frozen, planner) | 284 | 70 | 301685 | run took 23 min |
| 2026-11-18 10:59 | swateek | agent run planner-2-corr (corrections, planner) | 40 | 0 | 45731 | run took 4 min |
| 2026-11-18 11:22 | swateek | agent run planner-3 (frozen, planner) | 284 | 0 | 301685 | run took 22 min |
| 2026-11-18 12:03 | swateek | agent run planner-3-corr (corrections, planner) | 38 | 0 | 42664 | run took 41 min |
| 2026-11-18 12:20 | swateek | agent run router (frozen, router) | 213 | 0 | 258244 | run took 17 min |
| 2026-11-18 12:41 | swateek | agent run tool_calling (frozen, tool_calling) | 542 | 0 | 903750 | run took 21 min |
| 2026-11-18 12:47 | swateek | agent run single_rag (frozen, single_rag) | 87 | 87 | 138414 | run took 6 min |
| 2026-11-20 ~01:30 (start time approximate) | swateek | live demo-script run for screenshots (docs/demo/screens): 6 questions, 2 clarify replies, 1 correction edit, 9 turns | not counted | not counted | not counted | app does not count per run; no cached answers (fresh Redis); refusal turn expected to make no model call; see Langfuse customs-agent traces for 20 Nov. Explicit OK given by the user to call the endpoints for this run.
| 2026-11-20 ~02:00 (start time approximate) | swateek | retrieval option A, dev: listwise rerank of top 10, 120-token passages (docs/results/retrieval/rerank_a.json) | 45 | 0 | ~60,300 | 45 calls, 0 fallbacks, 0 errors; per-call mean 1,341 tokens. Approved by the user ("do option A"). |
| 2026-11-20 ~02:05 (start time approximate) | swateek | retrieval option A, frozen: same configuration (docs/results/retrieval/rerank_a.json) | 220 | 0 | ~296,000 | 220 calls, 0 fallbacks, 0 errors; per-call mean 1,346 tokens. Approved by the user ("do option A"). Some 429s were retried by the client. |
| 2026-11-20 18:26 | swateek | agent run dev-09 (dev, planner) | 113 | 17 | 129939 | run took 7 min |
| 2026-11-20 18:57 | swateek | agent run planner-1 (frozen, planner) | 490 | 70 | 577781 | run took 26 min |
| 2026-11-20 19:01 | swateek | agent run planner-1-corr (corrections, planner) | 83 | 12 | 101179 | run took 4 min |
| 2026-11-21 00:30 (IST) | swateek | agent run planner-2 (frozen, planner), PARTIAL: stopped by the user | not counted | not counted | not counted | 3 of 80 scenarios saved; the scenario in flight at the stop was not saved; resumable. Remaining official runs (planner-2 onward) wait for the user's next OK.
| 2026-11-21 03:21 | swateek | agent run planner-2 (frozen, planner) | 469 | 67 | 552848 | run took 26 min |
| 2026-11-21 03:24 | swateek | agent run planner-2-corr (corrections, planner) | 83 | 12 | 101160 | run took 4 min |
| 2026-11-21 03:52 | swateek | agent run planner-3 (frozen, planner) | 490 | 3 | 577704 | run took 27 min |
| 2026-11-21 03:55 | swateek | agent run planner-3-corr (corrections, planner) | 83 | 0 | 101160 | run took 4 min |
| 2026-11-21 04:17 | swateek | agent run router (frozen, router) | 424 | 0 | 541276 | run took 21 min |
| 2026-11-21 04:39 | swateek | agent run tool_calling (frozen, tool_calling) | 553 | 0 | 918576 | run took 22 min |
| 2026-11-21 04:45 | swateek | agent run single_rag (frozen, single_rag) | 87 | 87 | 138414 | run took 6 min |
| 2026-11-21 ~10:40 (start time approximate) | swateek | live re-run of the Dubai demo questions after freeze v5 (2 turns: clarify, then reply; docs/demo/screens/06, 07) | not counted | not counted | not counted | counts not recorded by the UI run; card checked: no duty or excise line on the tobacco |
| 2026-11-23 ~13:35 (start time approximate) | swateek | live recording of the demo walkthrough for the backup video (docs/demo/demo-video.mp4): 8 questions, 2 clarify replies, 1 correction edit, 1 refusal | not counted | not counted | not counted | counts not recorded by the recording run; Langfuse not shown on screen |
