# EmberEye Analytics Package Format (.eapkg)

Version: 1.0  
Scope: EmberEye Suite 2.0 Phase 2 marketplace runtime and Studio export interoperability.

## 1. Overview

An `.eapkg` file is a ZIP archive that packages an analytics plugin for EmberEye Field.

Primary goals:

- Portable plugin delivery (USB/local import)
- Deterministic validation before load
- Stable contract between Studio export and Field runtime

## 2. Required Archive Structure

The package root must contain the following structure:

```text
<name>-<version>.eapkg
├── metadata.json
├── <module_name>/
│   ├── __init__.py
│   └── analytic.py
└── assets/                  # optional
```

Rules:

- `metadata.json` is required.
- `<module_name>/analytic.py` is required.
- `<module_name>/__init__.py` is required.
- `assets/` is optional.

## 3. metadata.json Schema

### Required fields

- `id` (string): globally unique analytic identifier, lowercase recommended
- `name` (string): display name
- `version` (string): semantic-like version, e.g. `1.0.0`
- `module` (string): Python package/module folder name at archive root
- `entry_class` (string): class name implementing AnalyticPlugin

### Optional fields

- `description` (string)
- `author` (string)
- `dependencies` (array[string])
- `execution_hints` (object)
- `required_license` (string): license key/id needed for runtime enablement
- `category` (string): e.g. `fire`, `ppe`

Example:

```json
{
  "id": "acme.fire.guard",
  "name": "Fire Guard",
  "version": "1.2.0",
  "module": "fire_guard",
  "entry_class": "FireGuardAnalytic",
  "description": "Fire and smoke heuristic fusion analytic",
  "author": "Acme Labs",
  "dependencies": [],
  "execution_hints": {
    "preferred_fps": 10
  },
  "required_license": "fire_guard",
  "category": "fire"
}
```

## 4. Runtime Contract

The class referenced by `entry_class` in `analytic.py` must conform to the Base plugin contract:

- `get_metadata()`
- `configure(config)`
- `process_frame(frame_data)`

The plugin manager validates and registers descriptors before enabling cards in Field.

## 5. Validation Outcomes

Validation is expected to produce one of the following broad states:

- valid: package can be loaded
- invalid: package structure/schema/import readiness failed

Common invalid reasons:

- missing metadata.json
- missing module folder
- missing analytic.py
- malformed metadata fields

## 6. Import and Collision Behavior

When importing from USB/local source:

- valid packages are copied to marketplace folder
- invalid packages are reported and skipped
- duplicate filenames are renamed with suffixes (`_1`, `_2`, ...)

## 7. Compatibility Notes

- Keep `id` stable across versions to preserve runtime identity.
- Change `version` for every new package build.
- Maintain backward-compatible metadata keys where possible.

## 8. Security and Licensing Notes

- Package validation checks structure and metadata only.
- Runtime card enablement is license-aware and determined by LicenseManager.
- Unlicensed analytics must not be force-enabled through manual card visibility.
