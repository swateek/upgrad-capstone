# customs-agent (DeclareRight)

**New here? Follow [SETUP.md](SETUP.md)**: install, endpoint settings, tests, building the corpus.

- What it is and the results in one page: [info.md](info.md)
- The 12-page report: [docs/report/DeclareRight_report.pdf](docs/report/DeclareRight_report.pdf)
- Hosted copy (access code from the team): https://139-59-66-138.sslip.io
- Working log and plan: [WORKLOG.md](WORKLOG.md), [CLAUDE.md](CLAUDE.md)

Python environment for the customs assistant is managed with [uv](https://docs.astral.sh/uv/).
uv is used only inside this folder; the rest of the repository is unaffected.

## Setup

Install uv once:

```bash
brew install uv
```

Then, from the repo root:

```bash
cd final-capstone-project/customs-agent
uv sync
```

`uv sync` downloads Python 3.12 if needed (pinned in `.python-version`), creates `.venv/`, and installs the exact versions in `uv.lock`, including the `dev` group (pytest).

## Everyday commands

| Task | Command |
| --- | --- |
| Run a script | `uv run python prechecks/check_endpoint.py` |
| Run tests | `uv run pytest` |
| Add a runtime dependency | `uv add langgraph` |
| Add a dev-only dependency | `uv add --dev ruff` |
| Remove a dependency | `uv remove <package>` |
| Upgrade one package | `uv lock --upgrade-package <package>` then `uv sync` |
| Re-sync after pulling | `uv sync` |

`uv run` always uses this folder's `.venv`, so there is no need to activate it. If you prefer to, run `source .venv/bin/activate`.

## Rules

- Commit `pyproject.toml`, `uv.lock` and `.python-version` together whenever dependencies change.
- Never commit `.venv/`.
- Do not `pip install` into `.venv/`; use `uv add` so the lockfile stays the source of truth.
- Secrets stay in `.env` (ignored by git); never add them to `pyproject.toml`.
