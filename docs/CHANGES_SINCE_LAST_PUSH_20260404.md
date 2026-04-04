# Changes Since Last Origin Push

**Branch:** `testing/2.x`  
**Last pushed commit:** `b36849f9` — fix: alarm pipeline, PPE banner, alarm audio, PyQt6 compat, CPU model loading  
**Date:** April 4, 2026  

---

## Summary

Field-deployed bug fixes for alarm/PFDS flow, PPE false-alarm elimination, ACK_ON race condition fix, dataset class-mapping tooling, PyQt6 migration cleanup, and database manager hardening.

---

## Modified Files (23 files)

### EmberEye Field — Core

| File | Changes |
|------|---------|
| `embereye-field/fieldglass/main_window.py` | **+1928/−** — PPE alarm logic rewrite (violation-count driven, not raw fusion), ACK_ON race fix (ack-pending flag blocks stale ALARM_ON retries), ALARM_ON retry limit (max 3), effective_alarm fallback to False, auto-resolve sends ACK_ON to PFDS, superadmin enforcement on all settings, TCP port persistence on logout, alarm cooldown/scene fingerprint |
| `embereye-field/fieldglass/video_widget.py` | **+95/−** — Three-state alarm button (SECURE/SILENCE/SILENCED), explicit `_update_action_pill_visual()` on init, alarm latch fix |
| `embereye-field/main.py` | **+18/−** — UTF-8 stdout/stderr wrapper for frozen builds, import error handler |
| `embereye-field/stream_config.json` | **+48/−** — Updated stream config (camera IPs, thresholds) |
| `embereye-field/util/fusionbanner.py` | **+45/−** — Fusion banner UI updates |
| `embereye-field/vigilstream/video_worker.py` | **+302/−** — Video worker v2.0 updates |

### EmberEye Base

| File | Changes |
|------|---------|
| `embereye_base/app/ee_loginwindow.py` | **+25/−** — Dynamic import of fieldglass.main_window for EXE compat |
| `embereye_base/app/sensor_config_dialog.py` | **+2/−** — Minor fix |
| `embereye_base/core/database_manager.py` | **+73/−** — Database manager hardening |
| `embereye_base/core/detection_worker.py` | **+74/−** — Detection worker updates |
| `embereye_base/core/hybrid_detector.py` | **+216/−** — Hybrid detector refactor |

### EmberEye Studio

| File | Changes |
|------|---------|
| `embereye-studio/build_installer.py` | **+19/−** — Build installer updates |
| `embereye-studio/database_manager.py` | **+20/−** — Database manager hardening |
| `embereye-studio/external_dataset_importer.py` | **+15/−** — Dataset importer class mapping |
| `embereye-studio/qc_review_dialog.py` | **+98/−** — QC review dialog updates |
| `embereye-studio/studio_db_manager.py` | **+20/−** — Studio DB manager hardening |
| `embereye-studio/studio_main_window.py` | **+58/−** — Studio main window updates |

### Shared / Other

| File | Changes |
|------|---------|
| `embereye/core/database_manager.py` | **+20/−** — Database manager hardening |
| `scripts/build/build_installer.py` | **+11/−** — Build script updates |
| `stream_config.json` | **+82/−** — Root stream config updates |
| `tests/test_auth_user_management.py` | **+10/−** — Auth test updates |
| `windows_migration_v2/database_manager.py` | **+20/−** — Windows migration DB manager |
| `windows_migration_v2/sensor_config_dialog.py` | **+2/−** — Minor fix |

---

## New Files (7 files)

| File | Description |
|------|-------------|
| `docs/EXTERNAL_DATASET_CLASS_MAPPING_ANALYSIS.md` | Dataset class mapping analysis |
| `docs/EXTERNAL_DATASET_CLASS_MAPPING_CODE_CHANGES.md` | Dataset class mapping code changes |
| `docs/EXTERNAL_DATASET_CLASS_MAPPING_DIAGRAM.md` | Dataset class mapping diagram |
| `docs/EXTERNAL_DATASET_CLASS_MAPPING_QUICK_FIX.md` | Dataset class mapping quick fix |
| `docs/EXTERNAL_DATASET_CLASS_MAPPING_SUMMARY.md` | Dataset class mapping summary |
| `docs/FIELD_ISSUES_20260401.md` | Field issues tracker (April 1, 2026) |
| `embereye-field/models/yolo_versions/deployment_20260404_185643/metadata.json` | Model deployment metadata |

---

## Key Bug Fixes

1. **PPE false alarm** — Action card no longer turns red without actual PPE violations; alarm driven by violation counts only
2. **ACK_ON race condition** — Added `_ack_pending_by_loc_id` flag to block stale ALARM_ON retries from overriding ACK_ON
3. **ALARM_ON infinite retry** — Capped at 3 retries when no PFDS device is mapped
4. **Auto-resolve ACK_ON** — When alarm auto-resolves (person leaves), ACK_ON is now sent to PFDS device
5. **TCP port persistence** — Properly awaits async TCP server stop during logout
6. **Superadmin enforcement** — All settings gated behind superadmin role check
7. **EXE login crash** — Added fieldglass hidden imports to PyInstaller spec
