# Developer Git SOP

## Purpose

This document defines the required Git workflow for developers working on EmberEye source code.

## Naming Standard

1. Follow [git/NAMING_STANDARD.md](git/NAMING_STANDARD.md) for branch, commit, PR, and artifact naming.

## Branch Rules

1. Do not develop directly on `main`.
2. Do not reuse old merged branches.
3. Create a fresh branch for every task.
4. Use branch names like:
   - `fix/<scope>-<short-topic>`
   - `feature/<scope>-<short-topic>`
   - `chore/<scope>-<short-topic>`

## Start of Work

1. Update local refs:
   - `git fetch origin`
2. Start from latest `origin/main`:
   - `git switch -c fix/<short-name> origin/main`
3. Confirm branch and state:
   - `git branch --show-current`
   - `git status --short`

## During Work

1. Commit only source changes related to the task.
2. Do not commit generated datasets, local runtime databases, logs, or build output unless explicitly required.
3. Keep commits small and focused.
4. Before each commit, review staged files:
   - `git diff --cached --name-only`

## Commit Standard

Use concise commit messages:

1. `fix: resolve studio dataset import conflict`
2. `feat: add model validation results dialog`
3. `chore: document build handoff procedure`

## Push and PR

1. Push branch:
   - `git push origin <branch-name>`
2. Open PR into `main` unless told otherwise.
3. PR description must include:
   - what changed
   - why it changed
   - how it was verified
   - known risks

## Conflict Resolution

1. Resolve conflicts in editor.
2. Remove all markers:
   - `<<<<<<<`
   - `=======`
   - `>>>>>>>`
3. Verify with:
   - `rg "<<<<<<<|=======|>>>>>>>"`
4. Stage resolved files.
5. Continue merge or rebase.

## Developer Do Not Do

1. Do not force-push shared branches unless approved.
2. Do not commit directly to `main`.
3. Do not mix unrelated work in one PR.
4. Do not commit local testing artifacts.

## End of Work

1. Ensure PR is merged.
2. Delete the remote feature/fix branch.
3. Delete the local branch after switching away from it.
