# Retrieval recall next to end-to-end accuracy

Built by `eval/recall_vs_accuracy.py`.

## Search alone (Day 5–7 experiment, 60 retrieval queries)

Chosen retriever (docs/RETRIEVAL.md): hybrid BM25 + dense (RRF k=60), `BAAI/bge-reranker-v2-m3` on the top 30, hard negatives filtered, 350-token chunks.

| recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 |
| --- | --- | --- | --- | --- |
| 0.733 | 0.917 | 0.95 | 0.967 | 0.831 |

## In the official runs

Questions whose gold cites regulations and that reached search. The agent fetches each applied rule's citation by id first (docs/RETRIEVAL.md), then fills the 5-clause budget by search, so this is the recall of the clauses the writer actually saw. Citation recall: gold citations retrieved / all gold citations. Full recall: every gold citation retrieved.

| Set | Arm | Questions | Citation recall | Full recall | Accuracy if full | Accuracy if not (n) | Wrong despite full recall | Citation check |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eval-v3 | agent v2, code router | 61 | 0.967 | 0.934 | 0.982 | 0.0 (4) | 1 | 0.934 |
| eval-v3 | agent v1, code router | 50 | 0.913 | 0.820 | 0.878 | 0.0 (9) | 5 | 0.820 |
| eval-v2 | agent v1, code router | 55 | 0.965 | 0.927 | 0.843 | 0.0 (4) | 8 | 0.927 |
| eval-v2/gold-v2 | agent v2, code router | 59 | 1.000 | 1.000 | 1.0 | – (0) | 0 | 1.000 |

## Reading it

- On eval-v3, agent v2 had every gold citation in front of the writer on 93% of the questions that reached search; 1 of those was still wrong (E3-019 is the eval-v3 gold error). Retrieval is not the bottleneck: the wrong answers start earlier (reading the question, docs/METRICS.md and the failure labels).
- "Accuracy if not" is 0 by construction: the citation check needs every gold citation. On eval-v3 agent v2's 4 questions without full recall (E3-022, E3-034, E3-043, E3-044) all began with a misread fact (failure labels: EXTRACT_WRONG): the agent applied a different rule, so a different source was fetched. Search itself missed no needed clause in that run.
- Search alone finds the right clause in the top 5 for 95% of the retrieval queries; fetching each applied rule's citation by id makes the clauses the writer sees close to complete.
- Questions that end in a clarifying question or a refusal never reach search, so they are not in this table.
