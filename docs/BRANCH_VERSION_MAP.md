# EmberEye Branch And Version Map

This document defines which Git tag or branch should be used for each release line.

## Canonical References

### Exact Released Stable Baseline

- Reference: `v1.1.0`
- Commit: `c64d7cd6`
- Use when you need the exact code that was published as stable release 1.1.0.

### Current Stable Maintenance Line

- Reference: `release/1.1`
- Commit at time of writing: `64ce292a`
- Use when you need post-release fixes for the 1.1 line.
- This branch is ahead of `v1.1.0` by 1 commit.

### Current Next Development Line

- Reference: `develop/2.x`
- Commit at time of writing: `2a6b5c03`
- Use when you need ongoing 2.x development.
- This branch is ahead of `v1.1.0` by 22 commits.

## Practical Team Guidance

### Use `v1.1.0` when

- You need the exact production release baseline.
- You need a rollback point.
- You need to answer "what was shipped?"

### Use `release/1.1` when

- You are fixing bugs in the stable 1.1 line.
- You are validating 1.1 maintenance changes.
- You are preparing 1.1.x hotfix releases.

### Use `develop/2.x` when

- You are building new features.
- You are making breaking or architectural changes.
- You are doing work that should not go into the 1.1 line.

## Local Workspace Mapping

- Main local coordination workspace: `D:\EE\EmberEye`
- Stable maintenance workspace: `D:\EE\EmberEye-stable-1.1`
- 2.x development workspace: `D:\EE\EmberEye-develop-2.x`

## Recommended Workflow

1. Treat `v1.1.0` as immutable release history.
2. Treat `release/1.1` as the stable maintenance branch.
3. Treat `develop/2.x` as the future-development branch.
4. Cherry-pick selected 1.1 fixes into `develop/2.x` when needed.
5. Do not use a single dirty worktree for switching between stable and development lines.

## Related Documents

- [VERSIONING_POLICY.md](d:/EE/EmberEye/docs/VERSIONING_POLICY.md)
- [releases/README.md](d:/EE/EmberEye/docs/releases/README.md)
- [releases/RELEASE_NOTES_2026-03-19.md](d:/EE/EmberEye/docs/releases/RELEASE_NOTES_2026-03-19.md)

---

Status: Active
Owner: EmberEye Engineering
Last updated: 2026-03-26