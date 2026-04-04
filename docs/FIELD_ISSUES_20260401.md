# EmberEye 2.x – Reported Field Issues & Requirements

**Date:** April 1, 2026  
**Branch:** `testing/2.x`  
**Status:** In Progress

---

## Issue Tracker

| # | Issue | Priority | Status | Assignee |
|---|-------|----------|--------|----------|
| 1 | False Positives on Static Objects | High | **Fixed** | — |
| 2.1 | Continuous Alarm Loop (Single Camera) | Critical | **Fixed** | — |
| 2.2 | Multi-Camera Failure | Critical | **Fixed** | — |
| 3 | Alarm-to-Display Card Mapping | Medium | **Fixed** | — |
| 4 | Rule-Based Conditional Alarms (PPE + Vehicle) | High | **Fixed** | — |
| 5 | Performance & Stability | Critical | **Fixed** | — |

---

## 1. False Positives on Static Objects

**Severity:** High  
**Category:** Detection Logic

### Current Behavior
The analytics engine flags static, non-human objects as violations. Pre-existing, stable objects in the scene (e.g., a red fire extinguisher or a static pillar) are identified as "Vest" or "Helmet" violations because the object's color matches the required PPE color.

### Expected Behavior
Detection must be scoped strictly to **humans**. The logic should be:

$$\text{Detect Human} \rightarrow \text{Check if Human is wearing Vest/Helmet}$$

The system must not classify inanimate objects as violations.

### Root Cause
PPE count logic in `handle_vision_score_from_widget()` counted class names directly without checking spatial location. Any YOLO detection classified as `helmet`, `vest`, etc. was counted regardless of whether a person was present.

### Fix Applied
- Added `_ppe_overlaps_person(ppe_bbox, person_bboxes, min_containment=0.3)` helper function
- PPE stats computation now separates person bboxes from PPE detections
- Each PPE detection is checked for containment overlap (≥30%) with a person bbox
- PPE detections with no person association are discarded
- `total_persons` is now computed from actual person detections only (removed fallback inference from PPE counts)

---

## 2. Alarm Generation & System Stability

### 2.1 Continuous Alarm Loop (Single Camera)

**Severity:** Critical  
**Category:** Alarm Pipeline / Resource Management

#### Current Behavior
When a human without PPE enters the scene, the alarm triggers. Even if the alarm is "silenced" (acknowledged/muted), the system continues to generate alarm events in the background. This causes a resource loop, leading to **system lag and eventual hanging** until the person leaves the scene.

#### Expected Behavior
Once an alarm is silenced or acknowledged for a specific object/person, the system must suppress further alarms for that same incident during a cooldown period. The system must remain responsive regardless of the alarm state.

#### Root Cause
1. **No cooldown after ACK**: Operator acknowledges alarm → next frame (33ms later) fusion re-evaluates → alarm immediately re-triggers
2. **No early return for unchanged state**: `_handle_alarm_transition()` called 30+ times/sec even when alarm state hadn't changed — full method body executed every time
3. **Widget UI thrash**: `update_fire_alarm()` ran expensive UI updates (highlight, button sync, position) every frame even when alarm state was unchanged
4. **Re-latch without debounce**: When fusion clears but alarm isn't ACKed, state is re-latched to True — correct behavior but combined with 30fps processing caused CPU waste

#### Fix Applied
- Added `_alarm_ack_cooldown_ts_by_loc_id` dict and `alarm_ack_cooldown_s` config (default 30s)
- Post-ACK cooldown: after operator ACKs, new alarm triggers suppressed for N seconds
- Added early return in `_handle_alarm_transition()` when `active → active` (no state change)
- Added early return in `update_fire_alarm()` when `effective_alarm == was_alarm_active`
- Config key: `alarm_ack_cooldown_s` (default: 30.0)

### 2.2 Multi-Camera Failure

**Severity:** Critical  
**Category:** Concurrency / Resource Management

#### Current Behavior
When processing feeds from multiple cameras simultaneously:
- Vision analytics stop functioning correctly
- Alarms fail to trigger for violations
- The system becomes unresponsive (hangs) shortly after adding multiple streams

#### Expected Behavior
The system must handle concurrent streams efficiently. Analytics and alarm generation must work independently per camera without degrading overall system performance.

#### Root Cause
1. **Main thread overload**: `handle_vision_score_from_widget()` called 30+ times/sec per camera → N cameras × 30 = main thread saturated with fusion calculations
2. **Single-threaded detection**: All cameras share one `DetectionWorker` with one YOLO model — 4 cameras @ 10fps = 40 frames/sec queued but only 2-3/sec processed
3. **No per-camera throttle**: Every vision_score_ready signal triggered full fusion pipeline on main thread

#### Fix Applied
- Added per-camera fusion throttle: `_vision_fusion_last_ts_by_loc` and `_vision_fusion_interval_s` (default 1.0s)
- `handle_vision_score_from_widget()` now returns immediately if called within interval for same camera
- With 4 cameras: main thread processes 4 fusion evals/sec instead of 120
- Config key: `vision_fusion_interval_s` (default: 1.0)
- Note: Detection queue already has per-stream backpressure (`per_stream_max: 4`) and round-robin scheduling

---

## 3. Alarm-to-Display Card Mapping

**Severity:** Medium  
**Category:** UI / Alarm Configuration

### Description
The current alarm logic is global. Alarms are triggered regardless of which display cards are selected in the UI banner.

### Requirement
If a specific camera or rule is **not** selected in the UI banner (display card), it must not generate alarms. The alarm trigger logic must be explicitly tied to the UI selection state.

### Implementation Applied
- Added `_is_alarm_card_active()` method: checks if 'action' card is selected for active analytics category
- In 'auto' banner mode: all cards active → alarms always allowed
- In 'manual' banner mode: alarms only trigger when 'action' card is toggled on
- Gate applied in `handle_vision_score_from_widget()` before `_handle_alarm_transition()` call

---

## 4. Rule-Based Conditional Alarms (PPE + Vehicle)

**Severity:** High  
**Category:** Rule Engine

### Description
PPE violations currently trigger regardless of context.

### Requirement
Implement conditional rules. Example:

> **"Trigger PPE (Helmet/Vest) alarm ONLY IF a Vehicle is also present in the scene."**

The system needs a rule engine where users can define dependencies between object classes (e.g., Person + Vehicle, Person + Heavy Equipment) before an alarm is raised.

### Implementation Applied
- Rule schema: `{ "name": str, "enabled": bool, "trigger_classes": [...], "require_classes": [...] }`
- Interpretation: if any `trigger_classes` detected AND no `require_classes` present → suppress alarm
- Added `_evaluate_conditional_alarm_rules(detections)` method — returns True (allow) or False (suppress)
- Added `show_conditional_alarm_rules()` UI dialog with table editor (add/edit/delete rules)
- Added "Conditional Alarm Rules" menu entry under Settings
- Rules stored in `stream_config.json` under `conditional_alarm_rules`
- Default: empty rules list (no suppression — backward compatible)

---

## 5. Performance & Stability

**Severity:** Critical  
**Category:** Resource Management / Architecture

### Current Behavior
The system experiences severe performance degradation and hangs when scaling.

### Symptoms
- High CPU / Memory leak
- UI freezing
- System crashes

### Triggers
- Multi-camera streaming (see 2.2)
- Persistent alarm states (see 2.1)

### Requirement
- Fix resource management to ensure stability with multiple cameras
- Optimize the alarm handling thread to prevent blocking the main analytics pipeline

### Fixes Applied
- **CPU waste eliminated**: Alarm loop fix (2.1) + fusion throttle (2.2) + widget early return reduce main thread load by ~95%
- **Memory cleanup**: Added `_cleanup_loc_state()` method to clean per-location dicts when widgets are removed
- **Shutdown cleanup**: `cleanup_all_workers()` now clears all 12 per-location tracking dicts
- **Widget removal cleanup**: `cleanup_old_widgets()` calls `_cleanup_loc_state()` before deleting each widget
- **Thermal matrix leak**: `_last_thermal_matrix_by_loc_id` (stores large numpy arrays) now cleaned on widget removal

---

## Files Changed

| File | Change Description |
|------|--------------------|
| `embereye-field/fieldglass/main_window.py` | Added `_ppe_overlaps_person()` for person-associated PPE filtering (Issue 1). Added alarm ACK cooldown with `_alarm_ack_cooldown_ts_by_loc_id` and `DEFAULT_ALARM_ACK_COOLDOWN_S` (Issue 2.1). Added early returns in `_handle_alarm_transition()` for unchanged state (Issue 2.1). Added per-camera vision fusion throttle `_vision_fusion_interval_s` (Issue 2.2). Added `_is_alarm_card_active()` display-card alarm gate (Issue 3). Added conditional alarm rules system with `_evaluate_conditional_alarm_rules()`, `show_conditional_alarm_rules()` dialog, menu entry, and `DEFAULT_CONDITIONAL_ALARM_RULES` (Issue 4). Added `_cleanup_loc_state()` and per-location dict cleanup in `cleanup_all_workers()` and `cleanup_old_widgets()` (Issue 5). |
| `embereye-field/fieldglass/video_widget.py` | Added early return in `update_fire_alarm()` when effective alarm state is unchanged — prevents UI thrash at 30 fps (Issues 2.1, 5). |
| `docs/FIELD_ISSUES_20260401.md` | This issues document. |

---

## Notes
- Priority order: Performance (5) → Alarm Loop (2.1) → Rule Engine (4) → Object Scoping (1)
- Issues 2.1 and 5 are likely related (alarm loop causes performance degradation)
- Issue 2.2 may share root cause with 5
