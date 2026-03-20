# EmberEye 2.x Build Migration

This document defines the canonical build path for 2.x.

## Status

- Legacy per-app build entrypoints are retired for normal 2.x use:
  - `build_field_onefile.py`
  - `embereye-studio/build_installer.py`
- Canonical entrypoint for suite builds:
  - `scripts/build_suite_2x.py`

## Build EmberEye Suite 2.x

From repository root:

```bash
python scripts/build_suite_2x.py --field-mode onedir --clean
```

Optional Field installer build:

```bash
python scripts/build_suite_2x.py --field-mode onedir --field-installer --clean
```

## Outputs

Outputs are collected under:

- `dist/suite-2x/`
- `dist/suite-2x/suite-manifest.json`

The manifest includes:

- Base/Studio/Field versions
- Suite marker
- Field and Studio artifact paths

## Compatibility Mode (Temporary)

If you need to run a retired script directly:

```bash
EMBEREYE_ALLOW_LEGACY_BUILD=1 python build_field_onefile.py --mode onedir
EMBEREYE_ALLOW_LEGACY_BUILD=1 python embereye-studio/build_installer.py
```

or pass `--allow-legacy` where supported.

## Branch Policy

- Stable line: `release/1.1` (frozen/maintenance only)
- Active development: `develop/2.x`
- New feature work should target `develop/2.x`.
