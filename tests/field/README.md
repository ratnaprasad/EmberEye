# EmberEye Field App Test Suite

**Last Updated:** February 13, 2026  
**Test Coverage:** ~60% → Target: 85%+

## 📁 Test Structure

```
tests/field/
├── _test_utils.py                      # Logging & assertion helpers
├── run_all_field_tests.py              # Master test runner
├── run_smoke_test.py                   # ✅ Basic app launch
├── run_rtsp_pipeline_test.py           # ✅ RTSP camera simulation
├── run_ui_toggle_test.py               # ✅ Display modes & fusion overlay
├── run_hybrid_alarm_test.py            # ✅ Rule evaluation logic
├── run_threshold_config_test.py        # 🆕 Threshold configuration
├── run_multi_camera_grid_test.py       # 🆕 2x2 camera grid
├── run_pfds_integration_test.py        # 🆕 PFDS device integration
├── run_tcp_server_test.py              # 🆕 Embedded TCP server
├── logs/                                # Test execution logs
└── TEST_COVERAGE_ANALYSIS.md           # Detailed gap analysis
```

---

## 🚀 Quick Start

### Run All Tests
```powershell
cd D:\EE\EmberEye\tests\field
python run_all_field_tests.py
```

### Run Individual Test
```powershell
python run_smoke_test.py
python run_multi_camera_grid_test.py
python run_pfds_integration_test.py
```

### View Test Logs
```powershell
cat logs\*_<timestamp>.log
```

---

## 📋 Test Coverage Matrix

| Your Question | Test Coverage | Status |
|---------------|---------------|--------|
| **1. 2x2 RTSP Camera Grid** | `run_multi_camera_grid_test.py` | 🟢 **NEW** |
| **2. YOLO Model Import/Usage** | `run_hybrid_alarm_test.py` | 🟡 Partial (no actual model) |
| **3. Real PFDS Device** | `run_pfds_integration_test.py` | 🟢 **NEW** |
| **4. Fusion + Rules + Alarm** | `run_hybrid_alarm_test.py` + `run_threshold_config_test.py` | 🟢 **ENHANCED** |
| **5. Thermal/Grid/Fusion/Toggles** | `run_ui_toggle_test.py` | 🟢 Covered |
| **6. PFDS Config, RTSP Config, Model Import** | `run_pfds_integration_test.py` | 🟡 Partial (config dialogs not tested) |
| **7. Threshold Configuration** | `run_threshold_config_test.py` | 🟢 **NEW** |
| **8. Embedded TCP Server** | `run_tcp_server_test.py` | 🟢 **NEW** |

---

## 🎯 Test Descriptions

### 1. **run_smoke_test.py**
**Purpose:** Validate that Field app launches without crashing  
**Duration:** 8 seconds  
**Validates:**
- ✅ App starts successfully
- ✅ No immediate crashes
- ✅ Process terminates cleanly

**Run:**
```powershell
python run_smoke_test.py
```

---

### 2. **run_rtsp_pipeline_test.py**
**Purpose:** End-to-end RTSP video pipeline  
**Duration:** 12 seconds  
**Validates:**
- ✅ MediaMTX RTSP server starts
- ✅ RTSP camera simulator streams video
- ✅ Field app connects and renders video

**Prerequisites:**
- `simulators/rtsp/mediamtx/mediamtx.exe`
- `simulators/rtsp/data/IMG_1318.MOV`

**Run:**
```powershell
python run_rtsp_pipeline_test.py
```

---

### 3. **run_ui_toggle_test.py**
**Purpose:** UI component functionality  
**Duration:** < 1 second  
**Validates:**
- ✅ Display modes: Default, Thermal, Grid
- ✅ Fusion overlay rendering
- ✅ Alarm LED color changes (red/green)
- ✅ No crashes during mode switching

**Run:**
```powershell
python run_ui_toggle_test.py
```

---

### 4. **run_hybrid_alarm_test.py**
**Purpose:** Hybrid alarm logic (fusion + rules)  
**Duration:** < 1 second  
**Validates:**
- ✅ Rule-based alarm evaluation
- ✅ Severity classification (CRITICAL, HIGH, MEDIUM)
- ✅ Confidence threshold enforcement
- ✅ Multi-detection handling

**Run:**
```powershell
python run_hybrid_alarm_test.py
```

---

### 5. **run_threshold_config_test.py** 🆕
**Purpose:** Threshold configuration impact on alarms  
**Duration:** < 1 second  
**Validates:**
- ✅ Fusion confidence threshold (0.0-1.0)
- ✅ YOLO confidence threshold (0.0-1.0)
- ✅ Alarm triggering at various thresholds
- ✅ Edge cases (boundary values, very high confidence)
- ✅ Severity adjustment based on thresholds

**Test Scenarios:**
1. Default thresholds → CRITICAL alarm
2. High fusion threshold → no alarm
3. High YOLO threshold → fusion fallback
4. Low confidence everywhere → no alarm
5. Smoke vs. flame severity
6. Multiple detections → highest severity
7. Boundary confidence values
8. Very high confidence → always alarm

**Run:**
```powershell
python run_threshold_config_test.py
```

---

### 6. **run_multi_camera_grid_test.py** 🆕
**Purpose:** Multi-camera 2x2 grid layout  
**Duration:** 5 seconds  
**Validates:**
- ✅ 4 RTSP cameras in grid
- ✅ Unique location IDs per camera
- ✅ Independent display mode per tile
- ✅ Independent alarm state per tile
- ✅ Video rendering in all tiles

**Prerequisites:**
- `simulators/rtsp/mediamtx/mediamtx.exe`
- `simulators/rtsp/data/IMG_1318.MOV`

**Run:**
```powershell
python run_multi_camera_grid_test.py
```

---

### 7. **run_pfds_integration_test.py** 🆕
**Purpose:** PFDS (EmberHawk) device integration  
**Duration:** 5 seconds  
**Validates:**
- ✅ PFDS simulator connects on port 5000
- ✅ REQUEST1 command returns thermal frame
- ✅ #frame marker detected
- ✅ #Sensor marker detected
- ✅ EEPROM1 command response
- ✅ PERIOD_ON command response

**Prerequisites:**
- `simulators/pfds/pfds_simulator.py`
- `simulators/pfds/data/NEW DATA 10 MINS.txt`

**Run:**
```powershell
python run_pfds_integration_test.py
```

---

### 8. **run_tcp_server_test.py** 🆕
**Purpose:** Embedded TCP server functionality  
**Duration:** 3 seconds  
**Validates:**
- ✅ TCP server accepts connections (port 9999)
- ✅ Single client connection
- ✅ Incident data transmission (JSON)
- ✅ Multiple clients (if supported)
- ✅ Reconnection after disconnect
- ✅ Malformed data handling

**Note:** Requires Field app running with TCP server enabled

**Run:**
```powershell
# Start Field app first
python embereye-field\main.py

# In another terminal:
python run_tcp_server_test.py
```

---

## 🔧 Test Utilities

### _test_utils.py
**Functions:**
- `get_log_path(name)` → Creates timestamped log file
- `log_line(log_path, message)` → Logs to file + console
- `assert_true(condition, message)` → Assertion with error message

**Example:**
```python
from _test_utils import get_log_path, log_line, assert_true

log_path = get_log_path("my_test")
log_line(log_path, "Starting test")
assert_true(result == expected, "Result should match expected")
```

---

## 📊 Test Results

### Expected Output
```
[12:34:56] [SMOKE] Launching Field app for 8.0s
[12:35:04] [SMOKE] Completed

[12:35:05] [RTSP] Starting MediaMTX
[12:35:07] [RTSP] Starting simulator
[12:35:08] [RTSP] Launching Field app
[12:35:20] [RTSP] Completed

[12:35:21] Default mode rendered
[12:35:21] Thermal mode rendered
[12:35:21] Grid mode rendered
[12:35:21] Alarm LED set to red
[12:35:21] Fusion overlay rendered
[12:35:21] [UI] Toggle test completed

[12:35:22] [HYBRID] Rule evaluation test completed

[12:35:23] [THRESHOLD] Test 1: Default thresholds (fusion=0.3, yolo=0.5)
[12:35:23] ✓ Alarm triggered: CRITICAL
[12:35:23] [THRESHOLD] All threshold configuration tests passed

[12:35:24] [GRID] 4 widgets created
[12:35:24] [GRID] All location IDs are unique
[12:35:29] [GRID] Multi-camera grid test completed successfully

[12:35:30] [PFDS] Simulator started on port 5000
[12:35:30] [PFDS] Sending REQUEST1 command
[12:35:31] [PFDS] Thermal frame parsing successful
[12:35:35] [PFDS] Integration test completed successfully

[12:35:36] [TCP] Connected to 127.0.0.1:9999
[12:35:36] ✓ Single client connected
[12:35:41] [TCP] All TCP server tests completed

All Field tests completed
```

### Check Logs
```powershell
# View latest test log
Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

---

## ⚠️ Known Limitations

### Incomplete Coverage
- ❌ **Model Import Dialog:** Not tested (GUI workflow)
- ❌ **RTSP Config Dialog:** Not tested (GUI workflow)
- ❌ **PFDS Config Dialog:** Not tested (GUI workflow)
- ❌ **Analytics Export:** EmberSync incident export not validated
- ❌ **Visual Regression:** No screenshot comparison
- ❌ **Load Testing:** No stress/endurance tests

### Partial Coverage
- ⚠️ **YOLO Model:** Uses dummy model path, no actual inference
- ⚠️ **Thermal Parsing:** Basic validation, not pixel-perfect
- ⚠️ **TCP Server:** Requires manual Field app startup

---

## 🛠️ Troubleshooting

### Test Fails: "MediaMTX not found"
**Solution:**
```powershell
# Verify MediaMTX exists
Test-Path simulators\rtsp\mediamtx\mediamtx.exe
```

### Test Fails: "Video file not found"
**Solution:**
```powershell
# Verify video file exists
Test-Path simulators\rtsp\data\IMG_1318.MOV

# If missing, check .gitignore (data/ folders are excluded)
```

### Test Fails: "PFDS simulator did not start"
**Solution:**
```powershell
# Run PFDS simulator manually
python simulators\pfds\pfds_simulator.py

# Check if data file exists
Test-Path simulators\pfds\data\NEW DATA 10 MINS.txt
```

### Test Hangs
**Solution:**
```powershell
# Kill all Python/MediaMTX processes
Get-Process python, mediamtx | Stop-Process -Force

# Re-run test
```

---

## 🚀 Next Steps

### Phase 1: Run Existing Tests
1. Run `python run_all_field_tests.py`
2. Review logs in `tests/field/logs/`
3. Fix any failures

### Phase 2: Add Missing Tests
4. `run_model_import_test.py` - Model import workflow
5. `run_rtsp_config_test.py` - RTSP stream configuration
6. `run_pfds_config_test.py` - PFDS device configuration
7. `run_analytics_export_test.py` - EmberSync incident export

### Phase 3: Advanced Testing
8. `run_visual_regression_test.py` - Screenshot comparison
9. `run_stress_test.py` - 4 cameras + 4 PFDS, 1 hour
10. `run_end_to_end_scenario_test.py` - Realistic fire scenario

---

## 📞 Support

**Documentation:**
- `TEST_COVERAGE_ANALYSIS.md` - Detailed gap analysis
- `../docs/TESTING_*.md` - Additional testing guides

**Logs:**
- All tests produce timestamped logs in `tests/field/logs/`
- Logs include timestamps, test results, and error messages

**Issues:**
- Check test logs first
- Verify prerequisites (MediaMTX, video files, PFDS data)
- Run tests individually to isolate failures
