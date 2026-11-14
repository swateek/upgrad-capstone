# Technical report: outline (12 pages)

**Team:** DLlamas · **Working title:** Procurement and vendor-review copilot: an agentic system on a hosted 8B model

Page budgets are targets. Every claim points at a file in `docs/results/` or `docs/small-model-log.md`.

| § | Section | Pages | Content | Evidence |
|---|---|---|---|---|
| 1 | Problem and scope | 0.75 | The user (one central ministry office) and the three jobs. What the system refuses. The human-in-the-loop boundary: it drafts; people award, order and debar. | `docs/spec/task-spec.md` |
| 2 | Corpus and data | 1.0 | Instruments and editions, with hashes and edition decisions. The rule-boundary splitter (footnote attachment, annexure scope, 1,690 documents vs the 500–1,200 target). The screening snapshot (five list versions; latest decides). The ten synthetic bid cases. PII handling. | `corpus/manifest*.yaml`, `editions.md`, `results/phase1-corpus-by_rule.md` |
| 3 | Evaluation set | 0.75 | 60 frozen questions (25/20/15, 8 refusals), how gold was verified mechanically, `also_accept`, retrieval labels, dev set, freeze process. | `eval/`, `results/eval-freeze.md` |
| 4 | Baseline: how the 8B model breaks | 1.0 | Closed-book vs BM25 single prompt: invented citations, wrong facts, failed refusals. | `results/siliconflow/phase1-baseline.md`, log #8–12 |
| 5 | Retrieval | 1.25 | Chunking experiment, BM25/dense/hybrid/rerank, reranker choice, recall@k measured separately from answers. | `results/siliconflow/retrieval-*.md`, log #13, #15–16 |
| 6 | Prompting strategies | 1.0 | Plain vs structured+few-shot (with/without constrained decoding) vs CoT vs decomposition. Where each breaks. | `results/siliconflow/phase3-prompts.md` |
| 7 | Agent architecture | 1.5 | Planner → executor → critic on Deep Agents. Step, tool and token budgets (with definitions). Source handles. Critic gate. Refusal pre-check. Session state. Error handling (tool failures, malformed JSON, loops, token caps). | `backend/src/copilot/agent/`, log #17–21 |
| 8 | **What we did to compensate for a small model** (graded) | 1.5 | One table: failure → evidence → compensation → measured effect. Thinking off, token budget, prompt trimming (2,889 → 471 tokens), handles instead of ids, code repairs, deterministic critic, advisory LLM critic, refusals in code, constrained decoding. | `docs/small-model-log.md` (all entries) |
| 9 | End-to-end evaluation | 1.25 | Accuracy per job, task completion, average tool calls, latency and cost per query, failure taxonomy (retrieval miss / reasoning / tool-call / hallucination). | Phase 4 `results/siliconflow/e2e-*.md` |
| 10 | Responsible AI | 0.75 | Prompt-injection tests (proposal and corpus), PII, refusals, the human-in-the-loop boundary, labelled synthetic data. | Phase 4 safety results |
| 11 | Deployment | 0.5 | Docker topology, ports, ingest job, rate limit and cache (Phase 4), tracing (Langfuse). | `docker-compose.yml`, README |
| 12 | Limitations and next steps | 0.5 | Course-endpoint switch, the 8B critic, corpus edges (Rule 194, footnote spill), MSE questions out of scope. | — |
| A | Appendix | — | Eval set sample, prompts, deviation table (plan §1.1). | — |
