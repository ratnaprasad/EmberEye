# EmberEye Product Versioning Policy

This document defines how we version and tag:
- EmberEye Base
- EmberEye Studio
- EmberEye Field

It is intended for engineering, QA, release, and operations.

## 1. Goals

- Keep each product independently releasable.
- Make release impact obvious from version number.
- Keep tags easy to search and automate in CI/CD.
- Support desktop installers while staying compatible with Android/macOS style metadata.

## 2. Versioning Model

We use independent Semantic Versioning (SemVer) per product:

`MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`

Examples:
- `1.8.0`
- `1.8.1`
- `1.9.0-rc.1`

### 2.1 What to bump

- MAJOR: Breaking behavior/protocol/config changes.
- MINOR: Backward-compatible feature additions.
- PATCH: Backward-compatible bug fixes.

### 2.2 Product version streams

Each app has its own stream:
- Base: `embereye-base/vX.Y.Z`
- Studio: `embereye-studio/vX.Y.Z`
- Field: `embereye-field/vX.Y.Z`

Do not force all apps to the same version if only one app changed.

## 3. Git Tagging Standard

Use annotated tags only.

Tag formats:
- `embereye-base/vX.Y.Z`
- `embereye-studio/vX.Y.Z`
- `embereye-field/vX.Y.Z`

Optional suite tag (only when all three are jointly validated):
- `embereye-suite/YYYY.MM.DD-rN`
- Example: `embereye-suite/2026.03.19-r1`

### 3.1 Tag commands

```bash
git tag -a embereye-base/v1.8.0 -m "Base v1.8.0"
git tag -a embereye-studio/v1.5.0 -m "Studio v1.5.0"
git tag -a embereye-field/v1.6.0 -m "Field v1.6.0"

git push origin embereye-base/v1.8.0 embereye-studio/v1.5.0 embereye-field/v1.6.0
```

## 4. Pre-release and Hotfix Rules

- Release candidate tags: `-rc.N` (example: `v1.6.0-rc.2`).
- Hotfix after release: increment PATCH (example: `1.6.0` -> `1.6.1`).
- Never reuse or move an existing release tag.

## 5. Android/macOS Styled Versioning: Should We Use It?

Short answer: yes, as secondary metadata, not as the primary source of truth.

### 5.1 Android style

Android normally uses:
- versionName (human-readable), for example `1.6.0`
- versionCode (monotonic integer), for example `1060003`

This is useful for update ordering and store/distribution systems.

### 5.2 macOS style

macOS typically uses:
- CFBundleShortVersionString (marketing version), for example `1.6.0`
- CFBundleVersion (build number), for example `20260319.3`

This is useful for installer/updater comparison.

### 5.3 Recommendation for EmberEye

Use a hybrid approach:
- Primary release version for all docs/tags: SemVer (`X.Y.Z`).
- Secondary build metadata for packaging/updaters:
  - buildNumber: monotonic integer or date-based sequence.
  - Example mapping:
    - releaseVersion: `1.6.0`
    - buildNumber: `20260319.3`

This gives clear engineering meaning (SemVer) and robust installer/update ordering (Android/macOS style build number).

## 6. Release Checklist

1. Confirm branch is synced with `origin/main`.
2. Confirm tests/builds pass for affected product(s).
3. Choose bump type (MAJOR/MINOR/PATCH).
4. Create annotated product tag(s).
5. Push tag(s) to origin.
6. Record release notes.
7. If all three are validated together, add optional suite tag.

## 7. Version Ownership

- Base team owns Base version bumps.
- Studio team owns Studio version bumps.
- Field team owns Field version bumps.
- Release manager verifies tag naming and uniqueness.

## 8. Examples

- Only Field bugfix:
  - `embereye-field/v1.6.1`
- Studio feature + Base unchanged:
  - `embereye-studio/v1.6.0`
- Breaking change in TCP protocol shared by Base and Field:
  - `embereye-base/v2.0.0`
  - `embereye-field/v2.0.0`

---

Policy status: Active
Owner: EmberEye Engineering
Last updated: 2026-03-19
