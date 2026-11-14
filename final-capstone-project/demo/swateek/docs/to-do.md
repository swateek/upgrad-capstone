# To-do

**Team:** DLlamas

## Before submission (Fri 27 Nov)

- [ ] **1. Merge the PR into main.** Plan §14 asks for phase work to show up in git history, and the branch `17-swateek---sample-design` hasn't been merged yet. Claude Code can draft the PR description; `gh` isn't logged in, so open the PR yourself.
- [ ] **2. Mentor notes.** `docs/mentor-notes/` is still empty. Write a short note for each mentor session, covering the feedback and what you did about it. This meets the "act on mentor feedback" requirement.
- [ ] **3. Release tag and submission.** Tag the final commit (name of your choice). Then submit the repo link and `docs/report/siliconflow/report.pdf`. The eval report and trace screenshots are in the repo and also in the PDF's appendices.

## When you decide

- [ ] **4. Course endpoint switch (`PROVIDER=upgrad`).** Built and tested offline; plan and status in `docs/endpoint-switch-plan.md`. Still to do:
  - [x] Chat probe: everything passed (`docs/results/upgrad/probe.md`).
  - [x] Listwise reranker recall: 0.66 / 0.95 / 0.97 vs 0.68 / 0.97 / 0.97 without it.
  - [x] `UPGRAD_RERANKER=upgrad` kept (meets "a reranker").
  - [ ] Team token quota from the coordinator.
  - [ ] Go-ahead for `eval.e2e`, `eval.safety` and the preflight on `upgrad` (no judge). Results go to `docs/results/upgrad/`.
  - [x] Docker index restored from the host (`copilot.ingest.copy_index`, no API calls).

## Demo (28 Nov – 5 Dec)

- [ ] **5.** Rehearse `docs/demo/demo-script.md` twice, timed.
- [ ] **6.** Record the fallback video.
- [ ] **7. The day before:**
  - [ ] `docker compose up -d --build`
  - [ ] Run the preflight twice: `uv run python -m eval.demo_preflight` (from `backend/`)
  - [ ] Check the SiliconFlow balance.
- [ ] **8. Thirty minutes before:**
  - [ ] Run the preflight again.
  - [ ] Open the Assistant tab (New conversation).
  - [ ] Open Langfuse, filtered to `demo-`.
