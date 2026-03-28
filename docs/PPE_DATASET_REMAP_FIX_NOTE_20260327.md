# PPE Dataset Remap Fix Note for 2.x

## Purpose

This note documents the code and data-handling changes made during investigation of incorrect PPE inference and missing dataset statistics in EmberEye Studio on the 2.x code line. It is intended to be shared with developers before any merge, cherry-pick, or manual porting of these changes.

## User-Visible Problems Observed

1. A trained PPE model was over-predicting `HELMET` and incorrectly classifying `NO_HELMET` or other PPE states as helmet-related detections.
2. After moving/importing data for training, the Studio dataset panel did not display the expected dataset statistics.
3. External dataset import and dataset preparation were not deterministic enough when label metadata was missing or incomplete.

## Root Cause Summary

### 1. Silent class corruption during training dataset preparation

The main defect was in the dataset remapping flow inside DatasetManager. When a source label ID could not be resolved via metadata, the code could fall back incorrectly and ultimately default to target class index `0`.

For PPE datasets, that meant multiple unresolved labels were silently rewritten as `HELMET`, which directly contaminated the training set and caused biased inference behavior.

### 2. Imported datasets can carry global class IDs

Some imported annotation files were using global taxonomy IDs rather than category-local PPE IDs. The pipeline needed to understand both:

1. explicit per-dataset/per-folder mapping metadata
2. full flattened taxonomy order
3. active analytics category order

Before this fix, the remapper did not consistently prioritize those sources.

### 3. Dataset stats UI was reading the wrong folder

The Studio UI was looking for the dataset under `training_data/yolo_dataset`, while the current training pipeline writes the prepared dataset under `training_data/dataset`.

That mismatch caused the UI to show missing or stale dataset information even when the training dataset had been prepared correctly.

## Code Changes Applied

### A. Deterministic remapping during dataset preparation

File: [embereye-studio/forgelab/training_pipeline.py](embereye-studio/forgelab/training_pipeline.py#L466)

Changes:

1. Added support for folder-level `_id_map.json` files as the highest-priority explicit mapping source.
2. Added full flattened taxonomy fallback via `_get_all_leaf_classes()`.
3. Kept active-category leaf-class fallback as a secondary mapping source.
4. Removed the unsafe behavior of defaulting unresolved labels to class index `0`.
5. Changed the behavior so unresolved labels are skipped instead of being silently corrupted.

Relevant sections:

1. [embereye-studio/forgelab/training_pipeline.py](embereye-studio/forgelab/training_pipeline.py#L466)
2. [embereye-studio/forgelab/training_pipeline.py](embereye-studio/forgelab/training_pipeline.py#L624)
3. [embereye-studio/forgelab/training_pipeline.py](embereye-studio/forgelab/training_pipeline.py#L689)

### B. Explicit mapping persisted at import time

File: [embereye-studio/external_dataset_importer.py](embereye-studio/external_dataset_importer.py#L522)

Changes:

1. Added generation of `_id_map.json` for imported datasets.
2. Wrote `_id_map.json` into both imported dataset storage and QC storage.
3. Stored mappings as `global_id -> target_class_name` so later dataset preparation can remap deterministically even if original sidecar files are incomplete.

This reduces ambiguity for future external imports.

### C. Dataset stats UI fixed to read the active dataset location

File: [embereye-studio/studio_main_window.py](embereye-studio/studio_main_window.py#L1352)

Changes:

1. Dataset stats now read `training_data/dataset` first.
2. Backward compatibility remains for older `training_data/yolo_dataset` layout.
3. The stats panel now counts `train`, `val`, and `test` images.
4. The UI now handles both list-style and dict-style `names` entries in `dataset.yaml`.

## Taxonomy State Observed During Fix

The active PPE taxonomy in [embereye/config/master_classes.json](embereye/config/master_classes.json#L76) is:

1. `HELMET`
2. `NO_HELMET`
3. `SAFETY_VEST`
4. `NO_VEST`
5. `HEAD_NO_HELMET`
6. `PERSON`

This matters because imported datasets may contain source classes such as `helmet`, `No helmet`, `No vest`, `Person`, or `vest`, and those must be mapped intentionally into the PPE taxonomy.

## Verification Performed

The dataset was rebuilt after the code changes and verified before retraining.

Observed prepared dataset output:

1. Final classes: `HELMET`, `NO_HELMET`, `NO_VEST`, `PERSON`
2. Final class counts: `0: 2057`, `1: 983`, `2: 1708`, `3: 3107`
3. Unknown class IDs in the prepared dataset: none

This confirmed that the previous `all roads lead to HELMET` corruption path was fixed.

## Important Scope Clarification

### Permanent vs temporary

These are source-code changes, not a temporary runtime workaround. If merged properly, the main defect will not recur from the same root cause.

### Internal annotation flow

Internal annotation flow should be safe with this fix because the training pipeline no longer silently rewrites unresolved IDs to class `0`.

### External import flow

External import flow is much safer after this change because `_id_map.json` is now persisted and consumed by dataset preparation.

However, semantic correctness still depends on the import mapping itself being correct. If a source class is intentionally or accidentally mapped to the wrong EmberEye target class, the training result will still reflect that semantic choice.

Example:

If an external `vest` class is mapped to `PERSON WITH PPE` instead of `SAFETY_VEST`, the pipeline will preserve that mapping deterministically, but the semantic choice itself may still be wrong for PPE-only training.

## Files Changed in This Work

### Code files intended for developer review

1. [embereye-studio/forgelab/training_pipeline.py](embereye-studio/forgelab/training_pipeline.py)
2. [embereye-studio/external_dataset_importer.py](embereye-studio/external_dataset_importer.py)
3. [embereye-studio/studio_main_window.py](embereye-studio/studio_main_window.py)

### Taxonomy file that should be reviewed carefully before merge

1. [embereye/config/master_classes.json](embereye/config/master_classes.json)

### Generated/local files that should generally NOT be committed as part of the fix

1. [training_data/dataset/dataset.yaml](training_data/dataset/dataset.yaml)
2. Files under `training_data/dataset/images/...`
3. Files under `training_data/dataset/labels/...`
4. Local imported dataset artifacts under analytics data folders unless intentionally versioned

## Conflict Risk on 2.x

Because 2.x is active and other roadmap work is in progress, the following files are likely to be merge-sensitive:

1. [embereye-studio/forgelab/training_pipeline.py](embereye-studio/forgelab/training_pipeline.py)
2. [embereye-studio/studio_main_window.py](embereye-studio/studio_main_window.py)
3. [embereye-studio/external_dataset_importer.py](embereye-studio/external_dataset_importer.py)
4. [embereye/config/master_classes.json](embereye/config/master_classes.json)

Particular caution points:

1. `training_pipeline.py` is central training logic and may be concurrently edited for roadmap changes.
2. `studio_main_window.py` is a large, high-churn UI file and should be merged carefully.
3. `external_dataset_importer.py` may conflict with other import/taxonomy work.
4. `master_classes.json` is effectively shared taxonomy state and should never be auto-merged without review.

## Recommended Merge Strategy

1. Cherry-pick or manually port only the code changes in the three Python files first.
2. Treat [embereye/config/master_classes.json](embereye/config/master_classes.json) as a manual review item, not a blind overwrite.
3. Do not merge generated `training_data/dataset` contents as part of the fix.
4. Rebuild the dataset after merge and verify class distribution before any production retrain.

## Recommendations for Developers

1. Keep `_id_map.json` as a supported contract for imported datasets.
2. Preserve the rule that unresolved labels must be skipped, never coerced to class `0`.
3. Add automated regression tests for:
   - external dataset import with global IDs
   - internal annotation dataset preparation
   - Studio dataset stats against both `dataset` and legacy `yolo_dataset`
4. Add a validation step that prints class histogram before training starts.
5. Add a warning in the UI or logs when source labels are skipped during remap.
6. Review PPE semantic mapping rules, especially around `vest`, `SAFETY_VEST`, `PERSON`, and any broader human/PPE hybrid classes.
7. If taxonomy evolves, update import mapping rules and tests together in the same change.

## Suggested Follow-Up Work

1. Add unit tests around `_discover_used_class_names()` and `_copy_split()` covering `_id_map.json`, metadata JSON, labels.txt, global IDs, and category-local IDs.
2. Add import-time validation that flags suspicious mappings such as `vest -> PERSON WITH PPE` when the active domain is `ppe`.
3. Consider writing a small developer utility to inspect imported datasets and print:
   - source IDs
   - resolved class names
   - target dataset IDs
   - skipped labels
4. Consider isolating taxonomy config changes from training-pipeline fixes in separate pull requests to reduce merge conflicts.

## Bottom Line

The primary defect fixed here is permanent if the source changes are merged correctly: unresolved labels are no longer silently turned into `HELMET`, and the dataset stats UI now reflects the actual prepared dataset.

The remaining risk is no longer silent class corruption. The remaining risk is semantic mapping quality for external datasets, which should be addressed with explicit import rules, `_id_map.json`, and regression tests.

## Additional Critical Fixes Applied (2026-03-28)

### Issue: PPE Violation Counter Stuck at Zero in Field Despite Visible Detections

**Problem Statement**: EmberEye Field was displaying PPE detections (NO_VEST, NO_HELMET boxes) in the video tile overlay, but the VIOLATIONS card on the analytics dashboard remained at 0, regardless of how many violations were detected.

**Root Cause Analysis** (in discovery order):

1. **Vision-only PPE gate blocking fusion**: Field's `_handle_incoming_sensor()` method had a guard that would block PPE analytics fusion when sensor packets were stale, even though PPE detection is primarily vision-based. This prevented the fusion orchestrator from processing detection data.

2. **Sensor packet overwrites without PPE carry-through**: When sensor fusion packets were created, they did not preserve the PPE statistics extracted from YOLO detections, allowing sensor-only sensors to overwrite detection-based PPE counts with zero/stale values.

3. **Class name normalization gap**: PPE class names from the YOLO model could contain variations (dots, slashes, spaces, dashes) such as `NO.HELMET`, `NO/HELMET`, `NO-HELMET`, but the PPE counter extraction logic only handled basic space and dash normalization, causing class name mismatches and failed counts.

4. **Detection events bypassed statistics extraction**: The direct detection callback path from the video widget did not immediately extract and store PPE statistics, relying instead on async score callbacks that could race with sensor events, leading to missed or overwritten counts.

#### Code Changes Applied (Field App):

**File: [embereye-field/fieldglass/main_window.py](embereye-field/fieldglass/main_window.py)**

Changes:

1. **Removed vision-only PPE gate** (Line ~744):
   - Changed: `if not has_recent_sensor: ... break`
   - To: `if not has_recent_sensor and not ppe_mode: ... break`
   - Effect: PPE mode now continues fusion orchestration even without recent sensor packets, allowing vision-only PPE analytics to work correctly.

2. **Added sensor packet PPE carry-through** (Lines ~2150-2177):
   - Sensor fusion packets now read and merge live PPE statistics before calling the fusion orchestrator.
   - Uses `max()` to preserve non-zero counts across sensor/vision overwrites.
   - Reads from `_ppe_stats_by_loc_id` which is updated by both direct detection events and score callbacks.
   - Effect: PPE counts extracted from vision are now carried forward through sensor packets instead of being overwritten with zero.

3. **Robust PPE class name normalization** (Helper methods ~1669-1676, ~1701-1708):
   - Added `_norm_class_name()` helper that normalizes class names by:
     - Converting to lowercase
     - Replacing dots, slashes, spaces, dashes with underscores
     - Removing consecutive underscores
   - Updated PPE count extraction to use this normalization.
   - Supports class name variants: `NO.HELMET`, `NO_HELMET`, `NO-HELMET`, `no_helmet`, etc.
   - Effect: YOLO model output with various naming conventions is now correctly matched to PPE taxonomy entries.

4. **Added direct detection event integration** (Lines ~823-866):
   - New method: `handle_detection_event_from_widget(loc_id, status, yolo_score, detections, frame_size)`
   - Purpose: Callback triggered immediately when YOLO returns detections, before score thresholding delays.
   - Behavior:
     - Extracts PPE counts from raw detections
     - Updates `_ppe_stats_by_loc_id[loc_key]` with live counts
     - Updates `_fusion_by_loc_id[loc_key]` fusion payload
     - Pushes updated fusion data to widget via `set_fusion_data()` immediately
   - Effect: PPE statistics are now stored and available synchronously, preventing race conditions.

5. **Modified video widget detection callback** (File: [embereye-field/fieldglass/video_widget.py](embereye-field/fieldglass/video_widget.py), Line ~1346-1350):
   - `handle_detection_event()` now forwards detections to main window's `handle_detection_event_from_widget()`
   - Effect: Video tile now triggers direct PPE statistics extraction as soon as detections are available.

**Testing/Verification**: 
- PPE violation counters now increment correctly when NO_VEST and NO_HELMET detections appear in the video.
- Class name normalization tested with model outputs containing dots, slashes, dashes.
- Sensor packets no longer overwrite detection-extracted PPE counts.

---

### Feature: Alarm Audio Playback on Incident Raise/Silence

**Feature Request**: Play an audio alarm file when an incident alarm is raised, stop playing when the alarm is silenced or acknowledged, and resume playing if the alarm is raised again due to new violations.

**Implementation Summary**:

Integrated `winsound` (Windows audio) into the alarm state machine with centralized audio state management.

#### Code Changes Applied (Field App):

**File: [embereye-field/fieldglass/main_window.py](embereye-field/fieldglass/main_window.py)**

Changes:

1. **Alarm audio import and fallback** (Lines ~18-19):
   ```python
   try:
       import winsound
   except (ImportError, OSError):
       winsound = None
   ```
   - Gracefully handles environments where winsound is not available (non-Windows).

2. **Alarm audio state initialization** (Lines ~1910-1922):
   ```python
   self._alarm_audio_is_playing = False
   self._alarm_audio_enabled = bool(self.config.get('alarm_audio_enabled', True))
   field_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   self._alarm_audio_file = str(self.config.get('alarm_audio_file', 
       os.path.join(field_root, 'assets', 'alarm.wav')))
   ```
   - Initializes audio playback state, enabled flag, and file path.
   - Default alarm path: `embereye-field/assets/alarm.wav`
   - Configuration is read from `stream_config.json`.

3. **Alarm audio playback methods** (Lines ~1548-1587):
   - `_play_alarm_audio()`: 
     - Plays the configured alarm file in a loop using `winsound.SND_LOOP | winsound.SND_ASYNC`.
     - Fallback: If file not found or winsound unavailable, uses Windows SystemExclamation beep.
     - Sets `_alarm_audio_is_playing = True`.
   
   - `_stop_alarm_audio()`:
     - Stops playback by calling `winsound.PlaySound(None, 0)`.
     - Sets `_alarm_audio_is_playing = False`.
   
   - `_update_alarm_audio_state()` (centralized audio state manager):
     - Checks if ANY location currently has an active alarm (`_alarm_state_by_loc_id`).
     - If any alarm is active AND audio is enabled AND no audio is currently playing: PLAY.
     - If no alarms are active AND audio is currently playing: STOP.
     - Effect: Single audio stream for entire application, with smart management to avoid multiple simultaneous sounds.

4. **Wiring into alarm state transitions** (File: [embereye-field/fieldglass/main_window.py](embereye-field/fieldglass/main_window.py), method `_handle_alarm_transition()`):
   - **Alarm raise** (Line ~1618): When an alarm becomes active, `_update_alarm_audio_state()` starts playback if enabled.
   - **Alarm silence** (Lines ~1607, ~1614): When alarm is cleared/silenced, `_update_alarm_audio_state()` stops playback.
   - **Alarm re-raise** (Line ~1618): If violation persists and alarm transitions from inactive to active again, audio restarts automatically.

5. **Wiring into alarm acknowledgment** (File: [embereye-field/fieldglass/main_window.py](embereye-field/fieldglass/main_window.py), method `handle_alarm_ack_from_widget()`):
   - When user acknowledges alarm (Line ~1661), `_update_alarm_audio_state()` is called to stop audio.

6. **Cleanup integration** (File: [embereye-field/fieldglass/main_window.py](embereye-field/fieldglass/main_window.py), method `cleanup_all_workers()`):
   - Early `_stop_alarm_audio()` call (Lines ~10572-10576) ensures audio is stopped before application shutdown.

**Alarm Audio Lifecycle**:
```
NO ALARM (audio silent)
       ↓
VIOLATION DETECTED → Alarm RAISED → Audio PLAYS (looping)
       ↓
User ACKNOWLEDGES → Alarm SILENCED → Audio STOPS
       ↓
NO ALARM (audio silent)

OR (if violation persists):

ALARM SILENCED (audio stops)
       ↓
NEW DETECTION → Alarm RAISED AGAIN → Audio PLAYS (restarts)
```

---

### Feature: Alarm Audio Configuration UI

**Feature Request**: Add user-accessible settings for enabling/disabling alarm audio, selecting custom alarm file, and testing audio playback.

**Implementation Summary**:

Added "Alarm Audio Settings" dialog accessible from the Field gear menu (⚙ icon).

#### Code Changes Applied (Field App):

**File: [embereye-field/fieldglass/main_window.py](embereye-field/fieldglass/main_window.py)**

Changes:

1. **Alarm Audio Settings Dialog** (Lines ~6025-6111):
   - Method: `show_alarm_audio_settings()`
   - UI Elements:
     - **Enable Checkbox**: Toggle `alarm_audio_enabled` setting.
     - **File Path Input**: Display currently selected alarm file path. Editable.
     - **Browse Button**: Open QFileDialog to select custom WAV file.
     - **Default Button**: Reset to `embereye-field/assets/alarm.wav`.
     - **Test Button**: Play selected file immediately via `_play_alarm_audio()` (respects `winsound` availability).
     - **Save Button**: Persist settings to `stream_config.json` and apply at runtime.
   
   - User Workflow:
     1. Click gear menu → "Alarm Audio Settings"
     2. Check/uncheck "Enable Alarm Audio"
     3. Click "Browse..." to select custom WAV file OR "Default" to use built-in
     4. Click "Test" to hear selected file
     5. Click "Save" to persist settings

2. **Settings Menu Integration** (Lines ~5042, ~5330):
   - Gear menu (SENSOR GRID section): Added menu action "Alarm Audio Settings"
   - Alt menu (not tied to specific location): Added menu action "Alarm Audio Settings..."
   - Both actions trigger `show_alarm_audio_settings()`.

3. **Configuration Persistence** (Lines ~6107-6111 in dialog):
   - Reads and writes to `stream_config.json` using `StreamConfig.save_config()`.
   - Config keys:
     - `alarm_audio_enabled`: Boolean (default: `True`)
     - `alarm_audio_file`: String file path (default: `embereye-field/assets/alarm.wav`)
   - Settings are saved when user clicks Save button and applied immediately to runtime state.

**Settings Storage**:
```json
{
  "alarm_audio_enabled": true,
  "alarm_audio_file": "d:\\EE\\EmberEye-develop-2.x\\embereye-field\\assets\\alarm.wav"
}
```

---

### Asset Folder: Alarm Audio Files

**New Directory**: [embereye-field/assets/](embereye-field/assets/)

Purpose: Centralized location for alert/alarm audio files and future asset resources.

**Contents**:
- `README.md`: Instructions for users and developers on placing alarm WAV files.
- `alarm.wav` (user-provided): Custom alarm audio file (format: WAV, mono/stereo, recommended 2-5 seconds looping content).

**Default Behavior**: 
- Field app looks for `embereye-field/assets/alarm.wav` at startup.
- If not found, falls back to Windows SystemExclamation beep (built-in Windows sound).
- User can select alternative WAV file via Alarm Audio Settings dialog.

**Asset File Format**:
- Recommended: WAV format (lossless, compatible with winsound).
- Duration: 2-5 seconds (will loop until alarm is silenced).
- Channels: Mono or stereo, 16-bit, 44.1 kHz or 48 kHz sample rate recommended.
- Content: Distinct, non-jarring alert sound (e.g., electronic beep, siren, buzzer).

---

## Impact on Developers

### PPE Counter Fix Impact

1. **Detection processing**: Developers working on YOLO integration or detection callbacks should be aware that class names are now normalized uniformly. Custom class name variants should be added to the normalization helper, not handled ad-hoc elsewhere.

2. **Sensor fusion**: Sensor-based analytics now expect PPE statistics to be carried through fusion payloads. If adding new sensor types or analytics categories, ensure `_ppe_stats_by_loc_id` is populated before fusing.

3. **Analytics categories**: The vision-only PPE gate removal means PPE mode will now attempt fusion even without sensors. This is correct behavior but may expose other missing logic (e.g., tile banner layout for sensor-less tiles).

### Alarm Audio Impact

1. **Audio playback state**: The `_alarm_audio_is_playing` flag and `_update_alarm_audio_state()` method are now the single source of truth for alarm audio state. Do not call `_play_alarm_audio()` or `_stop_alarm_audio()` directly; always go through `_update_alarm_audio_state()` to ensure consistency.

2. **Configuration keys**: `alarm_audio_enabled` and `alarm_audio_file` are now persistent config keys in `stream_config.json`. These should be treated as first-class settings, not temporary state.

3. **Multi-location alarms**: The alarm audio system is application-level (one speaker for multiple location tiles). If alarms are active on multiple tiles simultaneously, the audio will be a single continuous stream. This is intentional (avoid audio cacophony), but developers should document this behavior if adding multi-location alarm features.

4. **Fallback audio**: The Windows SystemExclamation fallback ensures that even if the alarm file is missing, users still get *some* audio notification. Do not remove this fallback without testing on headless/server environments.

### File Modification Summary

**Core files changed**:
1. `embereye-field/fieldglass/main_window.py` (~11,600 lines, multiple sections)
2. `embereye-field/fieldglass/video_widget.py` (minimal change, single callback forward)

**New files**:
1. `embereye-field/assets/README.md` (instructions)
2. `embereye-field/assets/alarm.wav` (user-provided, not committed to git)

**Configuration impact**:
- `stream_config.json` now supports `alarm_audio_enabled` and `alarm_audio_file` keys.
- Existing configs without these keys will use defaults (audio enabled, built-in alarm file).
- Backward compatible; no breaking changes to existing config structure.

---

## Regression Testing Recommendations

1. **PPE counter display**:
   - Open Field with PPE analytics active.
   - Trigger NO_HELMET and NO_VEST detections.
   - Verify VIOLATIONS counter increments.
   - Test with various class name formatting (dots, slashes, etc.) if available in model.

2. **Alarm audio playback**:
   - Open Alarm Audio Settings.
   - Test "Default" button and verify alarm.wav location is set correctly.
   - Click "Test" button and verify audio plays (or SystemExclamation beep if file missing).
   - Trigger alarm condition, verify audio plays continuously until alarm is silenced.
   - Silence alarm, verify audio stops immediately.
   - Re-trigger alarm (if violation persists), verify audio resumes.

3. **Configuration persistence**:
   - Toggle "Enable Alarm Audio" and save; restart Field app.
   - Verify setting persisted to `stream_config.json`.
   - Select custom alarm file, save, restart.
   - Verify custom file is used.

4. **Sensor fusion with PPE**:
   - Open Field with both PPE analytics and sensor streams active.
   - Trigger detections, verify PPE counts are preserved through sensor packets.
   - Stop sensor stream, verify PPE analytics continue working via vision-only.

5. **Multi-tile alarms**:
   - If available, test PPE analytics on 2+ tiles simultaneously.
   - Trigger violations on both tiles, verify single audio stream (not cacophony).
   - Silence one tile, verify audio continues (because other tile still alarmed).

---

## Files Ready for Git Commit

### Include in PR/commit:
- `embereye-field/fieldglass/main_window.py` (all PPE counter fixes + alarm audio + settings UI)
- `embereye-field/fieldglass/video_widget.py` (detection callback forward)
- `embereye-field/assets/README.md` (instructions for alarm file placement)

### Do NOT include in PR/commit:
- `embereye-field/assets/alarm.wav` (user-provided, added to `.gitignore` so can be local)
- `stream_config.json` (runtime config, should not be version-controlled)
- Test artifacts, logs, or debug data

### Suggested `.gitignore` update:
```
embereye-field/assets/alarm.wav
embereye-field/assets/*.wav
```
(Developers can place their own alarm.wav in assets/ without committing it.)

---

## Change Log Update (2026-03-28)

Requested by user: expose validation results in Studio UI after training so end users can identify class mismatch and wrong mapping directly without terminal commands.

Implemented in [embereye-studio/studio_main_window.py](embereye-studio/studio_main_window.py):

1. Added `Results` button in Training tab under Model Versions, next to Export/Delete.
2. Button is disabled by default and enabled only when a model version is selected.
3. On click, Studio validates the selected model against `training_data/dataset/dataset.yaml` (`val` split).
4. Results popup now shows:
   - `mAP50`
   - `mAP50-95`
   - mean precision/recall
   - per-class AP50/precision/recall
   - dataset class list used for validation

### User verification status

Confirmed by user in session:

1. Results page is visible and working.
2. Existing model export is working.

### Operational impact

This improvement reduces dependency on command-line validation and makes model quality checks accessible to non-technical users before deployment/export.

### Merge caution update

Because this update modifies the same high-churn UI file, additional merge/conflict attention is required for:

1. [embereye-studio/studio_main_window.py](embereye-studio/studio_main_window.py)

---

## Build and Runtime Reliability Update (2026-03-28)

### Summary

During suite packaging and runtime verification, three production blockers were addressed:

1. Field login flow failed after auth with database open errors when the install drive was full.
2. Suite package field runtime failed with missing python DLLs due to a partial copy.
3. Studio startup failed due to database write path and oversized onefile packaging behavior.

### Code and Packaging Changes Applied

#### 1) Field PFDS database path moved to user-writable home storage

File: [embereye-field/hawkcore/emberhawk_manager.py](embereye-field/hawkcore/emberhawk_manager.py)

Changes:

1. Added `_default_db_path()` and switched `DB_PATH` to use it.
2. Path now resolves to `~/.embereye/pfds_devices.db` for both source and packaged execution.
3. Added one-time migration logic from install/project location to home storage when present.

Impact:

1. Prevents SQLite WAL/journal failures when install directory is on a full or constrained drive.
2. Keeps runtime device DB in a stable writable location.

#### 2) Studio user database path moved to user-writable home storage

File: [embereye-studio/database_manager.py](embereye-studio/database_manager.py)

Changes:

1. Added `_default_studio_db_path()`.
2. Studio now stores `studio_users.db` in `~/.embereye/studio_users.db` for both source and packaged execution.

Impact:

1. Avoids startup failures caused by non-writable or full install locations.
2. Keeps auth DB in a persistent user-owned location.

#### 3) Studio packaging mode switched from onefile to onedir

File: [embereye-studio/build_installer.py](embereye-studio/build_installer.py)

Changes:

1. Replaced `--onefile` with `--onedir` to avoid heavy per-launch extraction overhead.
2. Updated hidden import collection from `PyQt5` to `PyQt6` alignment in build args.

Impact:

1. Reduces startup friction for large studio bundles.
2. Keeps packaging aligned with active UI runtime stack.

#### 4) Suite artifact copy fallback retained for low-disk environments

File: [scripts/build_suite_2x.py](scripts/build_suite_2x.py)

Changes:

1. `copy_artifact()` now handles both `shutil.Error` and `OSError` disk-full cases.
2. For disk-full copy failures, manifest falls back to original artifact path instead of aborting the entire suite process.

Impact:

1. Suite manifest generation remains usable even under constrained disk conditions.

### Runtime Repair Action Performed in Dist Output

Local runtime repair completed for existing suite output:

1. Removed incomplete `dist/suite-2x/field-EmberEye-Field-GPU` copy (missing DLLs).
2. Replaced with a directory junction pointing to `dist/EmberEye-Field-GPU`.

Result:

1. `python312.dll` and full runtime dependency set are resolved from the complete field dist folder.

### Notes for Developers

1. Existing built executables do not auto-include source changes; rebuild is required for binaries to embed these updates.
2. Large `build/studio_pyinstaller` contents can be cleaned between builds when disk space is constrained.