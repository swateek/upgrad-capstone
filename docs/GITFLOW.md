# Git Workflow Guide

This repo uses a simplified, main-based flow. There is **no `develop` branch**. Every change is made on a short-lived branch created from `main` and merged back into `main` through a Pull Request (PR).

## Branch types

| Prefix | Use for | Example |
|---|---|---|
| `feature/` | New functionality | `feature/user-login` |
| `bugfix/` | Fixing a bug | `bugfix/null-pointer-on-save` |
| `docs/` | Documentation only | `docs/update-setup-steps` |
| `refactor/` | Code cleanup with no behaviour change | `refactor/split-data-loader` |

Optionally, include the issue number: `feature/12-user-login`.

**Naming rules:** lowercase, words separated by hyphens, short and descriptive.

## Step-by-step

### 1. Start from the latest `main`
```bash
git checkout main
git pull origin main
```

### 2. Create your branch
```bash
git checkout -b feature/user-login
```

### 3. Work and commit
```bash
git add <files>
git commit -m "#12 - add login form"
```
Make small, focused commits. Reference the issue number where there is one.

### 4. Push your branch
```bash
git push -u origin feature/user-login
```

### 5. Open a Pull Request
- Base branch: `main`
- Give it a clear title and a short description of what and why.
- Request a review from a teammate.

### 6. Address review comments
Commit and push more changes to the same branch. The PR updates automatically.

### 7. Merge and clean up
Once approved, merge the PR into `main`, then delete the branch:
```bash
git checkout main
git pull origin main
git branch -d feature/user-login
```

## Keeping your branch up to date
If `main` has moved on while you work:
```bash
git checkout main
git pull origin main
git checkout feature/user-login
git merge main
```
Resolve any conflicts, commit, and push.

## Rules of thumb
- Never commit directly to `main`. Always use a branch and a PR.
- One branch = one purpose. Don't mix a feature and an unrelated bug fix.
- Keep branches short-lived. Merge often to avoid big conflicts.
- Pull `main` before creating a new branch.
- Delete branches after merging.

## Quick reference
```bash
git branch                 # list local branches
git status                 # see what changed
git checkout <branch>      # switch branch
git log --oneline -5       # recent commits
```
