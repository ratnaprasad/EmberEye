# EmberEye Suite 2.0 — Known Issues

> Status as of 2026-03-20 · Branch: `develop/2.x`

Issues below are tracked for resolution during **Phase 0** of the 2.0 roadmap.
Where a workaround exists it is noted; otherwise the item is a blocking build concern.

---

## B-001 · Missing PyInstaller spec files for `embereye-field`

**Severity:** Build-blocking  
**Component:** `embereye-field` / `build_field_onefile.py`  
**Phase:** Phase 0 — Build infrastructure

### Description

`build_field_onefile.py` (called by `scripts/build_suite_2x.py`) looks for two spec files
that do not exist in the repository:

- `EmberEye_Field_OneDir.spec`
- `EmberEye_Field_OneFile.spec`

Running `build_suite_2x.py` will fail at the Field build step until these are created.

### Root Cause

The spec files were never committed for the field sub-app.  Only the studio spec
(`embereye-studio.spec`) and the legacy base spec (`EmberEye_win.spec`) are present.

### Acceptance Criteria

- [ ] `EmberEye_Field_OneDir.spec` created and committed — onedir build passes locally
- [ ] `EmberEye_Field_OneFile.spec` created and committed — onefile build passes locally
- [ ] `build_suite_2x.py` end-to-end build reaches the Studio step without error on the Field step

### Workaround

Skip `build_suite_2x.py` and build each app manually until specs are added.

---

## B-002 · `build_suite_2x.py` assumes Windows `.exe` artifacts

**Severity:** Build-blocking on macOS / Linux  
**Component:** `scripts/build_suite_2x.py`  
**Phase:** Phase 0 — Build infrastructure

### Description

The orchestrator script hard-codes `.exe` extensions when checking that build artifacts
exist before proceeding to the next step.  On macOS, PyInstaller produces `.app` bundles
(onedir) or bare executables without an extension (onefile); on Linux there is no `.exe`
either.  The script therefore always fails the artifact-presence check on non-Windows
platforms.

### Root Cause

`build_suite_2x.py` was written targeting Windows CI only and has no platform-conditional
artifact path logic.

### Acceptance Criteria

- [ ] Artifact path detection uses `sys.platform` / `platform.system()` to select the
  correct suffix: `.exe` (Windows), `.app` bundle path (macOS onedir), no suffix (macOS/Linux onefile)
- [ ] End-to-end `build_suite_2x.py` run completes successfully on macOS in CI

### Workaround

On macOS, build each app individually using `pyinstaller <spec>` directly.

---

## Resolved Issues

_None yet — this file was created on 2026-03-20._
