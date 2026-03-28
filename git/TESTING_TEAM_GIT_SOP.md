# Testing Team Git SOP

## Purpose

This machine is a testing and validation system. The testing team should preserve test evidence and local runtime state, but should not work directly on merged development branches.

## Primary Rule

1. Perform day-to-day testing on the dedicated local branch:
   - `testing/2.x`

## What Testing Team Does On This Machine

1. Test on real devices.
2. Validate Field, Studio, and suite packaging behavior.
3. Record failures, screenshots, logs, and reproduction steps.
4. Keep local test data on this machine if needed.

## What Testing Team Should Not Do

1. Do not commit random test artifacts to `main`.
2. Do not revive old merged branches.
3. Do not open PRs from dirty testing state without isolating the actual fix.

## When No Code Change Is Needed

1. Stay on `testing/2.x`.
2. Pull latest approved code when ready:
   - `git fetch origin`
   - `git merge origin/main`
3. Run tests and record findings.

## When A Bug Is Found And A Fix Is Needed

1. Create a fresh fix branch from current approved code:
   - `git switch -c fix/<short-name> origin/main`
2. Reproduce the bug.
3. Make only the required fix.
4. Stage only relevant files.
5. Commit and push the fix branch.
6. Open PR to `main`.

## Local Testing Data Guidance

1. Local datasets, runtime DBs, screenshots, and exported packages may remain on this machine.
2. Do not stage them unless explicitly required for a reviewed change.
3. Review `git status --short` before every commit.

## Before Handing Off A Bug

Include:

1. device or environment used
2. exact steps to reproduce
3. expected result
4. actual result
5. logs or screenshots
6. build or commit hash tested

## Testing Branch Maintenance

1. Keep `testing/2.x` as the local working branch for this machine.
2. Do not delete it unless a replacement testing branch is created.
3. Use feature or fix branches only for code that will be reviewed and merged.
