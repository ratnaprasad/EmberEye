# EmberEye Naming Standard

## Purpose

This is the single source of truth for naming across development, testing, pull requests, and build/deployment artifacts.

## General Rules

1. Use lowercase only for branch names.
2. Use hyphens (`-`) as separators in branch slugs.
3. Do not use spaces in branch names, artifact names, or tags.
4. Keep names short, descriptive, and searchable.

## Branch Naming

### Development and Fixes

Pattern:

1. `<type>/<scope>-<short-topic>`

Allowed `type` values:

1. `fix`
2. `feature`
3. `chore`
4. `docs`
5. `refactor`
6. `test`

Examples:

1. `fix/studio-db-path`
2. `feature/model-results-popup`
3. `docs/git-sop-standard`
4. `refactor/training-pipeline-remap`

### Testing Machine Branches

Pattern:

1. `testing/<major>.<minor>.x`

Example:

1. `testing/2.x`

### Release Branches

Pattern:

1. `release/<major>.<minor>`

Examples:

1. `release/1.1`
2. `release/2.0`

## Commit Message Naming

Pattern:

1. `<type>: <short summary>`

Allowed `type` values:

1. `fix`
2. `feat`
3. `chore`
4. `docs`
5. `refactor`
6. `test`
7. `build`
8. `ci`

Examples:

1. `fix: handle disk full during suite copy`
2. `docs: add team git operating procedures`
3. `build: switch studio package mode to onedir`

## Pull Request Title Naming

Pattern:

1. `<type>(<scope>): <summary>`

Examples:

1. `fix(field): move runtime DB to user-writable path`
2. `docs(git): standardize team operating procedures`
3. `build(studio): align pyinstaller settings`

## Build Artifact Naming

Pattern:

1. `<product>-<stream>-<yyyymmdd>-<shortsha>.<ext>`

Examples:

1. `EmberSuite-2x-20260329-a1b2c3d.zip`
2. `EmberEyeStudio-main-20260329-4de01ae.exe`
3. `EmberEyeField-main-20260329-4de01ae.zip`

## Model Version Folder Naming

Pattern:

1. `v<yyyymmdd>_<hhmmss>`

Example:

1. `v20260329_154210`

## Tag Naming (if used)

Pattern:

1. `v<major>.<minor>.<patch>`

Examples:

1. `v2.0.0`
2. `v2.0.1`

## Names to Avoid

1. `final`
2. `new`
3. `temp`
4. `myfix`
5. `latest-fix`

## Enforcement Guidance

1. Reject PRs with non-standard branch names unless there is an approved exception.
2. Keep one topic per branch.
3. If scope changes, create a new branch with a proper name.
