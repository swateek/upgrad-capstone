# Development Guide

How to clone this repository and set up local pre-commit hooks so every commit is checked before it lands.

## Prerequisites

- **Git**
- **Python 3.12+** (pre-commit installs and runs hooks in its own environments)
- The **`pre-commit`** CLI (installed in the next section)

## Clone the repository

**SSH** (preferred if you have GitHub SSH keys set up):

```bash
git clone git@github.com:swateek/upgrad-capstone.git
cd upgrad-capstone
```

**HTTPS:**

```bash
git clone https://github.com/swateek/upgrad-capstone.git
cd upgrad-capstone
```

## Install and enable pre-commit

Install the CLI once on your machine:

```bash
# macOS (Homebrew)
brew install pre-commit

# or with pip
pip install pre-commit
```

From the repository root, install the git hook so checks run on every commit:

```bash
pre-commit install
```

Optional: run all hooks against the whole tree once, to confirm the setup:

```bash
pre-commit run --all-files
```

## What the hooks check

Configured in [`.pre-commit-config.yaml`](../.pre-commit-config.yaml):

| Area | What it does |
|---|---|
| Whitespace and line endings | Trailing whitespace, end-of-file newlines, LF line endings |
| File sanity | Merge-conflict markers, YAML, JSON, large files (max 500 KB) |
| Secrets | Private keys and [gitleaks](https://github.com/gitleaks/gitleaks) |
| Shell | [shellcheck](https://www.shellcheck.net/) on shell scripts |
| Python | [Ruff](https://docs.astral.sh/ruff/) lint (with autofix) and format; `dumps/` is excluded |
| Notebooks | Strip notebook outputs ([nbstripout](https://github.com/kynan/nbstripout)); `dumps/` and `results/` are excluded |
| Branch protection | Blocks direct commits to `main`, `master`, and `develop` |

## Day-to-day use

- Hooks run automatically on `git commit`.
- To check everything without committing: `pre-commit run --all-files`.
- To refresh pinned hook versions in `.pre-commit-config.yaml`: `pre-commit autoupdate`.

For branching, commits, and pull requests, see the [Git Workflow Guide](GITFLOW.md).

## If a hook fails

Some hooks fix files in place (formatting, whitespace). Stage the changes and commit again:

```bash
git add <files>
git commit
```

Others only report a problem (for example a secret or a shellcheck warning). Fix the issue, then commit again.

A failure on `main`, `master`, or `develop` is intentional: create a feature branch and open a pull request instead.
