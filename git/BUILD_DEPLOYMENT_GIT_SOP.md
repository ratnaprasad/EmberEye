# Build and Deployment Git SOP

## Purpose

This document defines how the build and deployment team should generate trusted artifacts such as Field builds, Studio builds, and `.embersuite 2.x` packages.

## Branch Source Rule

1. Build only from an approved branch.
2. Preferred source is:
   - `origin/main`
3. If a release branch is introduced, build only from the approved release branch.

## Clean Build Rule

Before building:

1. Fetch latest refs:
   - `git fetch origin`
2. Create a clean build branch or use approved branch head.
3. Confirm exact commit:
   - `git rev-parse HEAD`
4. Confirm no unintended staged changes:
   - `git status --short`

## Build Machine Rules

1. Do not build from a developer scratch branch unless explicitly approved.
2. Do not build from a dirty working tree.
3. Do not commit generated artifacts into source branches unless that is a deliberate release process.

## Build Record Requirements

Each build handoff must record:

1. branch name
2. commit hash
3. build date/time
4. builder name or machine
5. artifact names produced
6. test status

## Packaging Procedure

1. Pull latest approved branch.
2. Verify runtime configuration needed for the build.
3. Run build scripts from the approved branch state.
4. Store produced artifacts outside source-controlled directories when possible.
5. If artifacts are copied into repo folders temporarily, do not commit them unless approved.

## If Build Fails

1. Record exact command used.
2. Save console output.
3. Report whether failure is:
   - environment issue
   - missing dependency
   - code regression
   - packaging issue

## If Build Team Needs A Fix

1. Do not patch directly on `main`.
2. Create a fix branch from `origin/main`.
3. Commit only the build-related fix.
4. Push branch and open PR.
5. Rebuild only after the fix is approved or explicitly authorized.

## Artifact Naming Guidance

Use names that allow traceability:

1. product name
2. version or branch
3. commit hash or build timestamp

Example:

1. `EmberSuite-2x-20260329-<shortsha>.zip`

## Release Closeout

1. Archive build log and commit hash.
2. Confirm deployed artifact came from the approved commit.
3. Close the build ticket only after verification is complete.
