# DeclareRight: summary

**What we built:** a multi-agent assistant where the 8B model only reads the question and writes the explanation. Code does everything else: it checks each fact against the question, applies the rules (stored as data with citations), computes every amount, fetches the regulation text (hybrid search + bge reranker over 742 documents) and verifies the answer. It includes an LLM planner with a validator, multi-turn corrections, a guard and a human-in-the-loop escalation path.

**How we evaluated it:** we froze the spec, the eval set and the prompting baselines before any agent code, kept a separate held-out set for each agent version, and scored everything in code.

## Key results

- 0.77 fully correct on 100 unseen questions
- every injection and evasion item handled, 0 fair questions refused
- the main remaining limit is reading the question (20 of the 23 failures)

## Ablations

- prompting alone 0.10 to 0.18, single-call RAG 0.07, agent 0.77
- LLM planner vs fixed code router: identical answers; the planner costs 24% more tokens
- retrieval: hybrid beat BM25 and dense alone; the bge reranker raised recall@1 from 0.65 to 0.73, while MiniLM lowered it

## Compensating for the small model

- calculators do all the arithmetic: dollar accuracy from 0 to 7% to 0.77
- rules are data, applied by code; citations come only from retrieved clauses
- schema-constrained JSON with repairs: 4 repairs in 1,159 calls, none left invalid
- every fact checked against the question in code, which fixed most invented and missed facts

## Live red-team

24 new attacks against the running app. They found one critical path-traversal bug, now fixed, and it passes 24 of 24.
