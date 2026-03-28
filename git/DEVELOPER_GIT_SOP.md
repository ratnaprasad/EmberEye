# Developer Git SOP

## Purpose

This document defines the required Git workflow for developers working on EmberEye source code.

## Branch Rules

1. Do not develop directly on `main`.
2. Do not reuse old merged branches.
3. Create a fresh branch for every task.
4. Use branch names like:
   - `fix/<short-name>`
   - `feature/<short-name>`
   - `chore/<short-name>`

## Start of Work

1. Update local refs:
   - `git fetch origin`
2. Start from latest `origin/main`:
   - `git switch -c fix/<short-name> origin/main`
3. Confirm branch and state:
   - `git branch --show-current`
   - `git status --short`

## Recommended Local Git Settings (Developer Machine)

Apply once per local clone:

1. Auto-prune stale remote refs:
   - `git config --local fetch.prune true`
2. Prevent unintended merge commits on pull:
   - `git config --local pull.ff only`
3. Reuse recorded conflict resolutions when possible:
   - `git config --local rerere.enabled true`

## During Work

1. Commit only source changes related to the task.
2. Do not commit generated datasets, local runtime databases, logs, or build output unless explicitly required.
3. Keep commits small and focused.
4. Before each commit, review staged files:
   - `git diff --cached --name-only`

## Commit Standard

Use concise commit messages:

1. `fix: resolve studio dataset import conflict`
2. `feature: add model validation results dialog`
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
   - if `rg` is unavailable: `grep -R "<<<<<<<\|=======\|>>>>>>>" .`
4. Stage resolved files.
5. Continue merge or rebase.

## Scenario Playbook: Detached HEAD Recovery + Mainline Sync

**Scenario name:** `detached-head-local-work-recovery`

Use this when all are true:

1. You are on `HEAD (no branch)`.
2. You have local tracked/untracked work you must keep.
3. `origin/main` moved and you need SOP-compliant continuation.

Steps:

1. Preserve work safely:
   - `git status -sb`
   - `git stash push -u -m "wip-detached-recovery-<date>"`
2. Create fresh task branch from latest main:
   - `git fetch origin --prune`
   - `git switch -c chore/<task-name> origin/main`
3. Reapply preserved work:
   - `git stash pop`
4. Resolve overlaps/conflicts (if any), then verify no conflict markers remain.
5. Re-run build/test checks required for the task.
6. Keep runtime/local artifacts out of commits (`stream_config.json`, local DBs, logs, generated datasets).

Notes:

1. This scenario is the approved recovery path instead of forcing commits on detached HEAD.
2. If stash pop produces conflicts, resolve in editor and continue with normal conflict resolution steps above.

## Developer Do Not Do

1. Do not force-push shared branches unless approved.
2. Do not commit directly to `main`.
3. Do not mix unrelated work in one PR.
4. Do not commit local testing artifacts.

## End of Work

1. Ensure PR is merged.
2. Delete the remote feature/fix branch.
3. Delete the local branch after switching away from it.
