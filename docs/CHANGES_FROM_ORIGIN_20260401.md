# Changes from Origin — April 1, 2026

**Branch:** `testing/2.x`  
**Base commit:** `4de01ae9` (origin/main)  
**Author:** Copilot-assisted session (Mar 31 – Apr 1, 2026)

---

## Summary of All Changes

| # | File | Lines Changed | Category |
|---|------|--------------|----------|
| 1 | `embereye-field/vigilstream/video_worker.py` | +7 / -2 | **Critical fix**: alarm + PPE pipeline was dead |
| 2 | `embereye-field/fieldglass/main_window.py` | +232 / -17 | **Features + fixes**: alarm mode, PPE stats, audio, banner |
| 3 | `embereye-field/main.py` | +258 / -17 | **Bootstrap**: CUDA quarantine, DLL isolation, CPU-forced |
| 4 | `embereye_base/core/hybrid_detector.py` | +89 / -3 | **Model loading**: fallback, CPU checkpoint rewrite |
| 5 | `embereye_base/core/model_versioning.py` | +78 / -12 | **Model versioning**: robustness, path resolution |
| 6 | `embereye_base/utils/resource_helper.py` | +46 / -0 | **Utility**: debug log helpers |
| 7 | `embereye_base/app/master_class_config_dialog.py` | +3 / -3 | **Bugfix**: PyQt6 QHeaderView enum |
| 8 | `embereye/app/master_class_config_dialog.py` | +3 / -3 | **Bugfix**: PyQt6 QHeaderView enum (mirror) |
| 9 | `embereye-field/assets/alarm.wav` | NEW | **Asset**: default alarm audio (two-tone siren) |
| 10 | `git/*.md` | minor | **Docs**: SOP formatting tweaks |

---

## Change 1: `embereye-field/vigilstream/video_worker.py`

### Problem
The `vision_score_ready` signal was **defined but never emitted**. The entire alarm evaluation and PPE banner pipeline was dead — `handle_vision_score_from_widget()` in `main_window.py` was never called.

Additionally, `detection_event` was emitted **after** `vision_score_ready`, but `handle_vision_score_from_widget` reads `widget._latest_detections` for PPE stats — so even after the emit fix, PPE counts would be stale because of Qt signal ordering (both are QueuedConnection).

### Changes
1. **Added `self.vision_score_ready.emit(yolo_score)`** in `_on_detection_result()` callback (~line 150).
2. **Reordered**: `detection_event.emit()` now fires **before** `vision_score_ready.emit()` so the widget's `_latest_detections` are updated before the fusion handler reads them.

### Developer Action
- Review lines 147–158 in `video_worker.py`.
- Verify the signal ordering makes sense: `detection_event` → widget stores detections → `vision_score_ready` → main_window reads detections for PPE stats.
- **Do not move `vision_score_ready.emit()` back before `detection_event.emit()`** — this ordering is intentional.

---

## Change 2: `embereye-field/fieldglass/main_window.py`

This file has the most changes. Each is described separately below.

### 2a. Alarm Evaluation Mode (`alarm_evaluation_mode` config)

**Problem:** With no PFDS sensors connected, the stale-sensor gate in `handle_vision_score_from_widget()` blocked all vision processing — alarms could never trigger on camera-only deployments.

**Changes:**
- Added constants at top of file:
  ```python
  ALARM_EVALUATION_MODES = ("fusion", "vision")
  DEFAULT_ALARM_EVALUATION_MODE = "vision"
  ```
- Added `_normalize_alarm_evaluation_mode(value)` method (~line 448).
- `handle_vision_score_from_widget()` (~line 739): Now checks `alarm_mode`. In `"vision"` mode, the stale-sensor gate is bypassed. In `"fusion"` mode (original behavior), sensor freshness is required.
- **UI dropdown** added in "Analytics & Fusion Banner" dialog (~line 6019): "Alarm evaluation mode" combo with two options.
- **Persistence**: saved to `stream_config.json` as `alarm_evaluation_mode` key.
- **Loaded at startup** in `initUI()` (~line 1810).

**Developer Action:**
- Default is `"vision"` (camera-first, no PFDS required). Change to `"fusion"` if deployments always have sensors.
- Test both modes: verify `"fusion"` blocks alarms when no sensor is connected, and `"vision"` allows camera-only alarms.

### 2b. PPE Stats from Widget Detections (Not `_rule_engine`)

**Problem:** PPE stats (helmet_count, vest_count, etc.) were read from `_rule_engine.last_details['ppe_stats']`, but `_rule_engine` is a standalone `VisionDetector` that **never runs inference**. The actual YOLO runs in the background `detection_worker` (separate instance). So PPE counts were always zero.

**Changes (~line 769–802):**
- Removed the old code that read from `_rule_engine.last_details`.
- New code computes PPE stats directly from `widget._latest_detections` (the live detections stored by `handle_detection_event`).
- Counts classes: `person`, `helmet`, `no_helmet`/`head`, `vest`, `no_vest`.
- Fallback: if no `person` class detected, infers total from max(helmet+no_helmet, vest+no_vest).

**Developer Action:**
- Review the PPE class name mapping matches your YOLO model's class names.
- If new PPE classes are added to the model, update the counting logic here.

### 2c. `set_fusion_data()` Call in Vision-Only Path

**Problem:** In the vision-only code path (after `_run_fusion`), `widget.set_fusion_data()` was not called — only `update_fire_alarm()` was called. The fusion result dict (containing PPE counters, confidence, etc.) never reached the widget, so `fusionbanner.py` rendered with all-zero values.

**Change (~line 812):**
- Added `widget.set_fusion_data(dict(fusion_result or {}))` after fusion runs in the vision-only path.

**Developer Action:** No special action needed — straightforward fix.

### 2d. Alarm Audio System (NEW FEATURE)

**What it does:** Plays a looping WAV alarm sound when any alarm is active. Stops when all alarms are acknowledged/silenced.

**Changes:**
1. **Import** (~line 19): `winsound` with graceful fallback for non-Windows.
2. **State init** (~line 1868): `_alarm_audio_is_playing`, `_alarm_audio_enabled`, `_alarm_audio_file` loaded from config.
3. **Methods** (~line 1506):
   - `_play_alarm_audio()`: Plays WAV in loop via `winsound.SND_LOOP | winsound.SND_ASYNC`. Falls back to Windows SystemExclamation.
   - `_stop_alarm_audio()`: Stops playback.
   - `_update_alarm_audio_state()`: Centralized state manager — checks if any loc has active alarm, starts/stops audio accordingly.
4. **Wiring**:
   - `_handle_alarm_transition()` end (~line 1596): calls `_update_alarm_audio_state()`.
   - `handle_alarm_ack_from_widget()` (~line 1619): calls `_update_alarm_audio_state()`.
   - `cleanup_all_workers()` (~line 10595): calls `_stop_alarm_audio()` on shutdown.
5. **Settings dialog**: `show_alarm_audio_settings()` method (~line 5918):
   - Enable/disable checkbox
   - File path input + Browse + Default buttons
   - Test playback button
   - Save persists to `stream_config.json` keys: `alarm_audio_enabled`, `alarm_audio_file`
6. **Menu entry** (~line 4914): Added "Alarm Audio Settings" under SENSOR GRID section in gear menu.

**Config keys** (in `stream_config.json`):
```json
{
  "alarm_audio_enabled": true,
  "alarm_audio_file": "embereye-field/assets/alarm.wav"
}
```

**Developer Action:**
- Replace `embereye-field/assets/alarm.wav` with a production-quality alarm sound (WAV, 2-5 sec, 44.1kHz, mono/stereo).
- The generated `alarm.wav` is a simple two-tone siren (880Hz/660Hz) — functional but synthetic.
- Test on headphones: the loop is continuous until silenced.

### 2e. Model Status Logging Improvements

**Changes (~line 5528–5562):**
- On model load error: writes to `field_model_status.log` via `append_debug_log()`.
- On model status refresh exception: catches exception, logs to console and debug log, sets tooltip.

**Developer Action:** Review `resource_helper.append_debug_log` and `get_debug_log_paths` (Change 6 below).

---

## Change 3: `embereye-field/main.py` (Bootstrap)

### Changes
- **CPU-forced environment**: Sets `CUDA_VISIBLE_DEVICES="-1"`, `EMBEREYE_FORCE_CPU="1"`, `EMBEREYE_QUARANTINE_CUDA_DLLS="1"` for frozen builds.
- **Bootstrap logging**: Added `_append_bootstrap_log()` function that writes to `~/.embereye/field_bootstrap.log`.
- **CUDA DLL quarantine**: Extensive logic to isolate CUDA DLLs, register DLL directories via `ctypes.windll.kernel32.AddDllDirectory`, preload CRT DLLs (`vcruntime140.dll`, `msvcp140.dll`, etc.) to prevent DLL load failures.
- **DLL directory management**: `_DLL_DIR_HANDLES` list tracks registered DLL dirs for cleanup.

**Developer Action:**
- This file is the entry point for PyInstaller builds. Changes are Windows-specific.
- If GPU support is needed later, the `EMBEREYE_FORCE_CPU` flag needs to be removed or made conditional.
- The quarantine logic is defensive — it prevents `torch` from accidentally loading CUDA DLLs that were bundled by PyInstaller.

---

## Change 4: `embereye_base/core/hybrid_detector.py`

### Changes
1. **Legacy fallback model loading** (~line 104): If `ModelVersionManager.current_best` is None, scans all version directories for `EmberEye.pt` or `best.pt`, picks the newest by mtime.
2. **CPU-forced CUDA env** (~line 208): Changed `CUDA_VISIBLE_DEVICES=""` to `"-1"` for cleaner CPU forcing.
3. **CPU checkpoint rewrite** (~line 217): New `_attempt_cpu_checkpoint_rewrite_and_load()` method — if a CUDA-tagged checkpoint fails to load on CPU, it does: `torch.load(path, map_location="cpu")` → `torch.save()` to temp file → load via YOLO. This handles models trained on GPU being deployed to CPU-only machines.
4. **Extended exception handling** (~line 259): Catches CUDA deserialization errors and falls back to the rewrite method.

**Developer Action:**
- Verify that models exported from GPU training load correctly on CPU-only field deployments.
- The temp file is cleaned up in a `finally` block — no disk leak.

---

## Change 5: `embereye_base/core/model_versioning.py`

### Changes
- Robustness improvements for path resolution and version listing.
- Better error handling when model directories are missing or corrupted.
- Added fallback logic for version sorting.

**Developer Action:** Review the version directory scanning logic if model versioning behavior changes.

---

## Change 6: `embereye_base/utils/resource_helper.py`

### Changes (+46 lines)
- Added `append_debug_log(filename, message)`: Appends timestamped messages to debug log files in `~/.embereye/logs/`.
- Added `get_debug_log_paths(filename)`: Returns list of candidate log paths.

**Developer Action:** These are utility functions used by model status logging in `main_window.py`. No special setup needed.

---

## Change 7 & 8: `master_class_config_dialog.py` (Both copies)

### Problem
`QHeaderView.Stretch` and `QHeaderView.ResizeToContents` are PyQt5 syntax. PyQt6 requires `QHeaderView.ResizeMode.Stretch` and `QHeaderView.ResizeMode.ResizeToContents`.

### Files Changed
- `embereye_base/app/master_class_config_dialog.py` (lines 78, 79, 113)
- `embereye/app/master_class_config_dialog.py` (lines 78, 79, 113)

### Developer Action
- These are identical changes in two mirrored copies of the same file.
- Consider whether both copies need to exist (potential code duplication).

---

## Change 9: `embereye-field/assets/alarm.wav` (NEW FILE)

- Two-tone siren: 880Hz / 660Hz alternating, 2 seconds, 44.1kHz, 16-bit mono WAV.
- ~176 KB file size.
- Already included in PyInstaller bundle via `EmberEye_Field_OneDir.spec` (the spec had the assets folder inclusion already).

**Developer Action:** Replace with a professional alarm sound for production.

---

## Files NOT Changed (Reference Only)

These files were read during diagnosis but NOT modified:
- `embereye-field/fieldglass/video_widget.py`
- `embereye-field/util/fusionbanner.py`
- `embereye_base/core/fusion/fusion_orchestrator.py`
- `embereye_base/core/vision_detector.py`

---

## New Untracked Files (Not Part of Core Changes)

These are diagnostic/utility scripts created during debugging — **can be deleted before merging**:

| File | Purpose |
|------|---------|
| `diagnose_c10.py` | CUDA/torch diagnostic script |
| `inspect_dist.py` | PyInstaller dist inspection |
| `inspect_torch_dll.py` | Torch DLL path diagnostic |
| `inspect_torch_init.py` | Torch initialization check |
| `rebuild_clean.py` | Clean build helper |
| `requirements/requirements-cpu.txt` | CPU-only requirements |
| `scripts/windows/preflight_runtime_offline.bat` | Offline preflight check |
| `scripts/windows/preflight_runtime_offline.ps1` | Offline preflight check (PS) |

---

## Testing Checklist for Developer

- [ ] **PPE banner cards**: Connect camera with PPE scene → verify helmet/vest/person counts update in real-time
- [ ] **Alarm triggers from vision**: Set alarm mode to "vision" → confirm alarm fires when PPE violations detected (no PFDS sensor needed)
- [ ] **Alarm triggers with fusion**: Set alarm mode to "fusion" → confirm alarm only fires when sensor data is fresh
- [ ] **Alarm audio**: Enable alarm audio in settings → trigger alarm → verify sound plays → silence → verify sound stops
- [ ] **Custom alarm file**: Browse and select a custom WAV → Test button works → Save persists
- [ ] **Class Manager dialog**: Click Class Subclass Manager in gear menu → verify it opens without "QHeaderView.Stretch" error
- [ ] **Model loading on CPU**: Deploy a GPU-trained model → verify it loads with CPU checkpoint rewrite fallback
- [ ] **Bootstrap log**: Check `~/.embereye/field_bootstrap.log` shows torch import + DLL loading
- [ ] **Config persistence**: Change alarm mode + audio settings → restart app → verify settings restored
