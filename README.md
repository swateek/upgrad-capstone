# upGrad Capstone Project

Team-based, structured practical project for the **Executive Post Graduate Programme in Generative AI and Agentic AI**. This repository is for Capstone group **DLlamas**.

## Overview

| | |
|---|---|
| Programme | Executive Post Graduate Programme in Generative AI and Agentic AI |
| Group | **DLlamas** |
| Track | **Track B — API-Side** (hosted ≤8B endpoint, no GPU) |
| Weightage | **20%** of the overall programme grade |
| Team size | **6–7** learners per group (the brief assigns **6 roles**) |
| Duration | **4 weeks** of build, from **30 Oct 2026** |
| Effort | **~8–10** focused hours per person per week |
| Curriculum | Modules 1–5: transformers, prompting, RAG, PEFT, multimodal, agents, serving, responsible AI |
| Schedule | Mentorship from **30 Oct 2026**; final submission **27 Nov 2026**; presentation **5 Dec 2026** |
| Graduation | Required — not participating fails the programme and blocks certification |

Groups are randomly formed (communicated **5 Oct 2026**). This team's group is **DLlamas**. Group changes are not allowed. All members receive the same grade.

Both tracks put the difficulty in design and evaluation. Starter repositories, notebooks, and containers are supplied beforehand.

## Selected track

Group **DLlamas** has selected **Track B — API-Side**.

**Title:** Multi-Agent Operations Copilot — an agentic system built entirely on a hosted ≤8B inference API.

The team receives an OpenAI-compatible chat-completions endpoint backed by a single shared ≤8B instruct model, plus an embeddings endpoint. Weights stay fixed, logits are not available, and a frontier model cannot be swapped in. The work is prompting, retrieval, tool design, orchestration, and evaluation.

Suggested domains: procurement and vendor-review assistant, travel-and-expense policy agent, competitive-research analyst, incident postmortem drafter, financial-report question-answering agent, HR policy navigator.

The nominated representative still submits this choice on the LMS form by **17 Oct 2026**.

### What the team must build

1. **Week 1 — Task decomposition.** A written specification of what the copilot does, what it must refuse, and what a correct answer looks like. An evaluation set of **60–100** realistic queries with gold answers, written before any code.
2. **Week 1 — Prompt engineering baseline.** A single-agent, single-prompt attempt. Compare at least three strategies: structured output with few-shot, chain-of-thought or self-consistency, and decomposition prompting. Document how the small model breaks.
3. **Week 2 — RAG over a real corpus.** **500–2,000** documents. Required: chunking experiments, hybrid retrieval (BM25 plus dense), a reranker, and citation-grounded answers. Measure retrieval recall@k separately from end-to-end answer quality.
4. **Week 3 — Agentic layer.** A multi-agent or tool-using system (LangGraph, CrewAI, AutoGen, or hand-rolled) with at least three tools, an explicit planner → executor → critic loop, persistent state across turns, and handling for tool failures, malformed JSON, infinite loops, and token budget caps. Constrained decoding, JSON schema validation, and retry logic are the core engineering work, because small models fumble tool calls.
5. **Weeks 3–4 — Evaluation and observability.** End-to-end accuracy against the Week 1 evaluation set, task completion rate, average tool calls per task, cost and latency per query, and a failure taxonomy (retrieval miss, reasoning error, tool-call error, hallucination). Tracing via LangSmith, Langfuse, or OpenTelemetry.
6. **Week 4 — Ship it.** Streamlit or React front-end, containerised, with rate limiting and caching. Responsible AI: prompt-injection tests against the document corpus, PII handling, refusal behaviour, and a stated human-in-the-loop boundary for consequential actions.

### Role split

| Role | Responsibility |
|---|---|
| Domain spec & eval design | Scope definition, gold-answer evaluation set, refusal policy |
| Prompt engineering | Strategy comparison, structured output, failure characterisation |
| RAG / retrieval | Chunking, hybrid search, reranking, citation grounding |
| Agent orchestration & tools | Planner/executor/critic loop, tool interfaces, state and memory |
| Observability & safety | Tracing, failure taxonomy, prompt-injection and PII testing |
| Front-end & deployment | UI, containerisation, rate limiting, caching, demo |

### Deliverables

- Git repository with the full agent stack
- Trace dashboard showing real query executions
- Evaluation report including the failure taxonomy
- 12-page technical report
- 10-minute live demo

### Guardrails

- The endpoint, an API key with a per-team token quota, and a starter agent skeleton will be provided
- Corpus capped at **2,000** documents; agent capped at **10** steps per query
- **Week 1 gate:** evaluation set frozen and baseline numbers recorded before any agent code is written
- Compensating for the ≤8B model is a graded section: what the team did to make a small model reliable

### Track A, for contrast

Track A is model-side: direct GPU access to fine-tune and serve a domain-adapted ≤8B open LLM. This group is on Track B.

| | Track A (GPU) | Track B (API) |
|---|---|---|
| Modules emphasised | 1, 3, 5 (and 2) | 2, 4, 5 |
| Core skill | Model adaptation and serving | Orchestration and evaluation |
| Hardest week | Week 2 (training instability) | Week 3 (agent reliability) |

## Journey

1. **Practice assignment** — Meet the team and the problem (optional, non-gradable; strongly recommended). Deadline **12 Oct 2026**
2. **Track selection** — Review the Capstone document, then the nominated representative submits the team's collective choice on the LMS form by **17 Oct 2026**
3. **Build + mentorship** — Work begins **30 Oct 2026**. One dedicated mentor; four weekly sessions. Recordings are on the LMS
4. **Submission** — Deliver by **27 Nov 2026**. No extensions
5. **Presentation** — **5 Dec 2026**

## Key dates (2026)

Revised calendar, approved to leave more time for project work alongside programme activities and proctored examinations.

| Date | Milestone |
|------|-----------|
| **5 Oct** | Group info + practice assignment live |
| **9 Oct** | Problem statement and track selection form live on the LMS |
| **12 Oct** | Practice assignment deadline |
| **17 Oct** | Track selection form deadline |
| **23–25 Oct** | Mentorship slots communicated |
| **30 Oct** | Capstone and mentorship begin |
| **27 Nov** | Final submission — **no extensions** |
| **5 Dec** | Capstone project presentation |

### Practice assignment

- Opens: **5 Oct** · Deadline: **12 Oct**
- Optional and non-gradable; use it to collaborate before graded work begins

### Track selection

- The form is on the LMS. The team's collective decision is **Track B — API-Side**
- Only the officially nominated team representative can submit
- The representative submits that decision on behalf of the group
- Submissions by other members are not considered
- Representative details will be shared separately. Deadline: **17 Oct**

### Mentorship

- One dedicated mentor per group, for four weekly sessions, starting **30 Oct**
- Slots are communicated **23–25 Oct**
- Session recordings are available on the LMS
- Session length, how slots are booked, and the submission format will be shared separately

### Grading

| Component | Weight |
|---|---|
| Technical depth and rigour | **30%** |
| Punctuality and consistent progress | **25%** |
| Working deployed system | **20%** |
| Report and demo | **25%** |

## Working rules

- Connect early. Communicate regularly, divide work clearly, and keep moving even if a member is inactive
- Come to mentor sessions prepared; act on feedback
- External tools and datasets are allowed
- The team owns execution and the final submission
- Capstone issues → programme coordinator

## Checklist

**Before you start**

- [X] Know your assigned group: **DLlamas**
- [X] Team decision: **Track B — API-Side**
- [ ] Complete the practice assignment if possible (deadline **12 Oct**)
- [ ] Nominated representative submits **Track B** on the LMS track selection form by **17 Oct**
- [ ] Note the mentorship slot when it is communicated (**23–25 Oct**)

**Throughout**

- [ ] Attend or catch up on each of the four weekly sessions (recordings on the LMS)
- [ ] Work consistently with the team between sessions, from **30 Oct**
- [ ] Submit the Capstone by **27 Nov** — no extensions
- [ ] Present on **5 Dec**

## Documents

- [Git Workflow Guide](docs/GITFLOW.md)
