# To-do

**Team:** DLlamas

## Before submission (Fri 27 Nov)

- [ ] **1. Merge the PR into main.** Plan §14 asks for phase work to show up in git history, and the branch `17-swateek---sample-design` hasn't been merged yet. Claude Code can draft the PR description; `gh` isn't logged in, so open the PR yourself.
- [ ] **2. Mentor notes.** `docs/mentor-notes/` is still empty. Write a short note for each mentor session, covering the feedback and what you did about it. This meets the "act on mentor feedback" requirement.
- [ ] **3. Release tag and submission.** Tag the final commit (name of your choice). Then submit the repo link and **`docs/report/upgrad/report.pdf`** (the course-endpoint report). Its eval report is `docs/results/upgrad/eval-report.md`; the trace screenshots are in `docs/demo/traces/upgrad/` and in the PDF's Appendix E.

## Course endpoint switch

- [x] **4. Switched to `PROVIDER=upgrad` (14 Nov).** Plan and status in `docs/endpoint-switch-plan.md`. The demo and the submitted report use `upgrad`; SiliconFlow is the fallback.
  - [x] Chat probe: 13/13 (`docs/results/upgrad/probe.md`).
  - [x] Listwise reranker recall: 0.66 / 0.95 / 0.97 vs 0.68 / 0.97 / 0.97 without it; kept (meets "a reranker").
  - [x] Two full e2e runs: 55/60 each. Safety probes 7/7. Demo preflight 9/10 twice.
  - [x] Chunking comparison on bge; Langfuse screenshots; eval report and technical report.
  - [x] Docker serves `upgrad`.
  - [ ] Team token quota from the coordinator (useful for demo week; the runs went ahead without it).

## Demo (28 Nov – 5 Dec)

- [ ] **5.** Rehearse `docs/demo/demo-script.md` twice, timed.
- [ ] **6.** Record the fallback video.
- [ ] **7. The day before:**
  - [ ] `docker compose up -d --build`
  - [ ] Check `/health` says `"provider":"upgrad"`.
  - [ ] Run the preflight twice: `uv run python -m eval.demo_preflight` (from `backend/`). Expect 9/10 on `upgrad`: the case_002 recommendation turn is critic-flagged.
  - [ ] Ask the team to stay off the course key.
  - [ ] Check the SiliconFlow balance (the fallback).
- [ ] **8. Thirty minutes before:**
  - [ ] Run the preflight again.
  - [ ] Open the Assistant tab (New conversation).
  - [ ] Open Langfuse, filtered to `demo-`.
