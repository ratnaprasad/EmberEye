# EmberEye Stable Release Notes

Release date: 2026-03-19
Release commit: `c64d7cd6`
Branch: `main`

## Stable Tags

- `embereye-base/v1.1.0`
- `embereye-studio/v1.1.0`
- `embereye-field/v1.1.0`
- `embereye-suite/2026.03.19-r1`

## Latest Versions (Per Versioning Policy)

- Base latest stable: `1.1.0`
- Studio latest stable: `1.1.0`
- Field latest stable: `1.1.0`
- Suite stable marker: `2026.03.19-r1`

## Included Change Highlights

### Base

- Detection and fusion flow improvements.
- Hybrid and vision detector updates.
- Thermal detector and TCP async server refinements.
- Master class and runtime configuration alignment.

### Studio

- Versioning governance added through `VERSIONING_POLICY.md`.
- Dataset refresh and training-data indexing cleanup.
- Binary/cache artifact tracking tightened via `.gitignore` updates.

### Field

- Fieldglass UI updates (`main_window`, `video_widget`, fusion banner).
- Single-instance guard and startup/stop script updates.
- Stream configuration and runtime behavior tuning.

## Stability and Release Governance

- Product-level versioning follows independent SemVer streams:
  - Base: `embereye-base/vX.Y.Z`
  - Studio: `embereye-studio/vX.Y.Z`
  - Field: `embereye-field/vX.Y.Z`
- Suite-wide validated release marker uses:
  - `embereye-suite/YYYY.MM.DD-rN`

## Android/macOS Style Compatibility

The release keeps SemVer as the primary version and supports Android/macOS style metadata as secondary build numbering:

- Android-style mapping:
  - `versionName = 1.1.0`
  - `versionCode = <monotonic integer>`
- macOS-style mapping:
  - `CFBundleShortVersionString = 1.1.0`
  - `CFBundleVersion = <monotonic build number>`

Recommended for all packaging pipelines:
- Keep SemVer tags as source of truth.
- Generate monotonic build numbers per build job for updater/installers.

## Notes

- These product tags currently point to the same validated commit (`c64d7cd6`).
- Future releases may diverge per product stream when only one product changes.
