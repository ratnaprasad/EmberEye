# EmberEye Field App Test Coverage Analysis

**Date:** February 13, 2026  
**Status:** Gap Analysis & Enhancement Plan

## Current Test Coverage

### ✅ **Existing Tests**

| Test | Coverage | Status |
|------|----------|--------|
| `run_smoke_test.py` | App launches without crash (8s) | ✅ Basic |
| `run_rtsp_pipeline_test.py` | MediaMTX + RTSP simulator + Field app integration | ✅ Basic |
| `run_ui_toggle_test.py` | Display modes (default/thermal/grid), fusion overlay rendering, alarm LED | ✅ Partial |
| `run_hybrid_alarm_test.py` | Rule evaluation logic (VisionDetector integration) | ✅ Partial |

---

## ❌ **Test Gaps (Your Questions)**

### 1. **RTSP Camera 2x2 Grid Functionality**
**Current:** ❌ **NOT TESTED**  
- Tests use single VideoWidget instance
- No multi-camera grid layout validation
- No camera tile addition/removal testing

**Gap:** Need to verify:
- 4 cameras render in 2x2 grid
- Each tile independently shows RTSP stream
- Grid auto-adjusts for 1-4 cameras
- Color-coded borders per camera

---

### 2. **YOLO Model Import & Usage Verification**
**Current:** ⚠️ **PARTIALLY TESTED**  
- Hybrid alarm test uses dummy model path (`__no_model__`)
- No actual model loading validation
- No inference execution testing

**Gap:** Need to verify:
- Model import dialog workflow
- ModelVersionManager integration
- Imported model loads successfully
- Inference runs on frames
- Detections are correct class/confidence

---

### 3. **Real-time PFDS (EmberHawk) Device Integration**
**Current:** ❌ **NOT TESTED**  
- No PFDS simulator tests
- No EmberHawk device connection tests
- No thermal frame parsing validation

**Gap:** Need to verify:
- PFDS simulator connects and sends data
- Thermal frames (24x32 matrix) parsed correctly
- Sensor data (CO, temperature) received
- Device pairing logic works
- Command/response protocol (EEPROM1, PERIOD_ON, REQUEST1)

---

### 4. **Fusion Logic + Rules + Analytics → Alarm Triggering**
**Current:** ⚠️ **PARTIALLY TESTED**  
- Rule evaluation tested in isolation
- No full fusion pipeline test
- No analytics integration

**Gap:** Need to verify:
- **Fusion:** thermal + vision + sensor → confidence score
- **Rules:** VisionDetector classifies detections → severity
- **Hybrid:** fusion cache + rule-based alarm → final decision
- **Analytics:** incident logging, ROI extraction, EmberSync export

---

### 5. **Thermal Frame, Grid, Fusion Overlay, Toggle Buttons**
**Current:** ⚠️ **PARTIALLY TESTED**  
- UI toggle test checks mode switching
- Uses synthetic thermal data
- No real thermal frame rendering

**Gap:** Need to verify:
- **Thermal Frame:** Heatmap rendering from real PFDS data
- **Thermal Grid:** 24x32 grid with cell values displayed
- **Fusion Overlay:** Bounding boxes + confidence + hot cells
- **Toggle Buttons:** D/T/# buttons switch modes correctly
- **Visual Regression:** Screenshots match expected output

---

### 6. **Configuration Workflows**
**Current:** ❌ **NOT TESTED**  

#### 6a. **PFDS Device Configuration**
- EmberHawkManager setup
- Device discovery
- Device pairing
- Connection status monitoring

#### 6b. **RTSP Stream Configuration**
- StreamConfigDialog workflow
- Add/edit/remove streams
- stream_config.json persistence
- Grid refresh after config change

#### 6c. **Model Import**
- Import Model dialog
- ModelVersionManager file selection
- Model loading into VisionDetector
- Active model display in UI

**Gap:** Full end-to-end configuration testing needed.

---

### 7. **Threshold Configuration**
**Current:** ❌ **NOT TESTED**  

**Gap:** Need to verify:
- Fusion confidence threshold adjustment
- YOLO confidence threshold adjustment
- Rule-based alarm thresholds
- Settings persistence
- Threshold changes affect alarm triggering

---

### 8. **Embedded TCP Server Functionality**
**Current:** ❌ **NOT TESTED**  

**Gap:** Need to verify:
- TCP server starts on expected port
- Accepts client connections
- Sends incident data (JSON format)
- Handles multiple clients
- Error recovery and reconnection

---

## 🎯 **Proposed Test Plan**

### **Phase 1: Critical Gaps (High Priority)**

| Test Name | Coverage | Effort |
|-----------|----------|--------|
| `run_multi_camera_grid_test.py` | 2x2 grid with 4 RTSP streams | Medium |
| `run_pfds_integration_test.py` | PFDS simulator → thermal frames → alarm | High |
| `run_full_fusion_pipeline_test.py` | RTSP + PFDS + fusion + rules → incident | High |
| `run_model_import_test.py` | Import model → inference → detection validation | Medium |

### **Phase 2: Configuration & Integration (Medium Priority)**

| Test Name | Coverage | Effort |
|-----------|----------|--------|
| `run_rtsp_config_test.py` | Add/edit streams, grid updates | Medium |
| `run_pfds_config_test.py` | Device pairing, connection monitoring | Medium |
| `run_threshold_config_test.py` | Adjust thresholds, verify alarm behavior | Low |
| `run_tcp_server_test.py` | TCP server startup, client connection, data transmission | Medium |

### **Phase 3: Visual & Regression (Low Priority)**

| Test Name | Coverage | Effort |
|-----------|----------|--------|
| `run_visual_regression_test.py` | Screenshot comparison for thermal/grid modes | Medium |
| `run_stress_test.py` | 4 cameras + 4 PFDS devices, 1 hour runtime | High |
| `run_analytics_export_test.py` | Incident recording, EmberSync export validation | Medium |

---

## 🛠️ **Implementation Strategy**

### **Quick Wins (Start Here)**

1. **Multi-Camera Grid Test**  
   - Use existing RTSP simulator with 4 instances
   - Validate grid layout and tile rendering
   - **Effort:** 2-3 hours

2. **PFDS Integration Test**  
   - Use `pfds_simulator.py` with NEW DATA 10 MINS.txt
   - Validate thermal frame parsing and display
   - **Effort:** 3-4 hours

3. **Threshold Configuration Test**  
   - Programmatically adjust thresholds
   - Send detections with varying confidence
   - Validate alarm triggering
   - **Effort:** 1-2 hours

### **Complex Tests (Later)**

4. **Full Fusion Pipeline Test**  
   - Orchestrate RTSP + PFDS + Field app
   - Inject known fire scenario
   - Validate end-to-end alarm flow
   - **Effort:** 6-8 hours

5. **Model Import & Inference Test**  
   - Import FastSAM-s.pt or custom model
   - Feed known test frames
   - Validate detection accuracy
   - **Effort:** 4-5 hours

---

## 📊 **Test Coverage Summary**

| Category | Current | Target | Gap |
|----------|---------|--------|-----|
| **UI Components** | 40% | 90% | 🟡 Medium |
| **RTSP Pipeline** | 50% | 95% | 🟡 Medium |
| **PFDS Integration** | 0% | 90% | 🔴 Critical |
| **Fusion Logic** | 30% | 95% | 🔴 Critical |
| **Configuration** | 0% | 80% | 🔴 Critical |
| **TCP Server** | 0% | 80% | 🟡 Medium |
| **Analytics Export** | 0% | 70% | 🟢 Low |

**Overall Coverage:** ~20% → Target: 85%+

---

## 🚀 **Next Steps**

1. Review and approve test plan
2. Implement Phase 1 tests (multi-camera, PFDS, fusion pipeline)
3. Run tests and document results
4. Fix identified issues
5. Implement Phase 2 & 3 tests

---

## 📝 **Notes**

- All tests should produce timestamped logs in `tests/field/logs/`
- Use `_test_utils.py` for consistent logging and assertions
- Tests should be runnable independently and in batch via `run_all_field_tests.py`
- Consider CI/CD integration for automated regression testing
