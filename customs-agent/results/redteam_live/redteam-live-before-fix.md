# Red-team against the live app (Day 13)

Run `redteam-live-before-fix`, 2026-11-24 10:17 IST, against `http://localhost:8000` (the app as `docker compose up` serves it: LLM planner, 15 state notes, rate limit 10 a minute). Built by `eval/redteam_live.py`; every request and response in `results/redteam_live/redteam-live-before-fix.jsonl`. Fresh attacks: none is from the Day 7 red-team list or an eval set.

**0 of 1 passed.**

| # | Area | Attack | Expected | Result | Pass |
| --- | --- | --- | --- | --- | --- |
| L20 | Web server | Path traversal on the static-file route (5 encodings), asking for data/rules.yaml | No file outside web/dist served | a file outside the web folder was served for /../../data/rules.yaml, /..%2f..%2fdata%2frules.yaml, /%2e%2e/%2e%2e/data/rules.yaml, /%2e%2e%2f%2e%2e%2fdata%2frules.yaml: the same route would serve /app/.env (API keys) | **no** |
