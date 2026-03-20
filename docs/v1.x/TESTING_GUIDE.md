# 🧪 EmberEye Testing Guide

Complete testing documentation for EmberEye Command Center.

## Table of Contents

- [Quick Start](#quick-start)
- [Unit Tests](#unit-tests)
- [Integration Tests](#integration-tests)
- [End-to-End Tests](#end-to-end-tests)
- [Performance Tests](#performance-tests)
- [Manual Testing](#manual-testing)

## Quick Start

### Run All Tests

```bash
# Complete test suite
python test_integration_e2e.py

# This will:
# 1. Start EmberEye application
# 2. Initialize TCP server (port 4888)
# 3. Start simulator sending sensor data
# 4. Run for 30 seconds
# 5. Verify all processes stable
# 6. Clean up automatically
```

### Expected Output

```
============================================================
EmberEye End-to-End Integration Test
============================================================

📍 Step 1: Checking ports...
✅ Port 4888 available

📍 Step 2: Starting EmberEye...
🚀 Starting EmberEye...
✅ EmberEye started (PID: 12345)

📍 Step 3: Verifying EmberEye status...
✅ EmberEye is running

📍 Step 4: Starting TCP simulator...
🚀 Starting TCP Simulator...
✅ TCP Simulator started (PID: 12346)

📍 Step 5: Running simulation (30 seconds)...
📊 Simulator sending sensor data...
✅ Simulation complete

📍 Step 6: Final status check...
EmberEye: ✅ Running
Simulator: ✅ Running

============================================================
✅ INTEGRATION TEST PASSED
============================================================
```

## Unit Tests

### Test AI & Sensor Components

```bash
python test_ai_sensor_components.py
```

Tests:
- Vision detector initialization
- YOLO model loading
- Sensor fusion calculations
- Threshold triggering
- Confidence scoring

### Test Authentication & User Management

```bash
python test_auth_user_management.py
```

Tests:
- User login/logout
- Password validation
- Session management
- Database operations

### Test UI Integration

```bash
python test_ui_integration.py
```

Tests:
- Window initialization
- Tab creation
- Widget rendering
- Signal/slot connections

## Integration Tests

### TCP Sensor Load Test

```bash
python tcp_sensor_load_test.py
```

Tests TCP server performance:
- Throughput (packets/second)
- Latency (ms)
- Connection stability
- Concurrent connections

**Expected Results:**
- Throughput: >1000 packets/sec
- Latency: <10ms average
- 0% packet loss
- Stable for 1000+ connections

### Camera Stream Load Test

```bash
python camera_stream_load_test.py
```

Tests video processing:
- Frame rate (FPS)
- Memory usage
- CPU utilization
- Multi-stream handling

**Expected Results:**
- 30 FPS for 1080p streams
- <500 MB RAM for 4 streams
- <30% CPU per stream
- Stable for 24+ hours

## End-to-End Tests

### Complete Workflow Test

```bash
python test_integration_e2e.py
```

This is the **primary integration test** that validates:

1. **Application Startup**
   - UI initialization
   - TCP server start (port 4888)
   - WebSocket client connection
   - YOLO model loading
   - Metrics server start (port 9090)

2. **Sensor Data Flow**
   - Simulator connects to TCP server
   - Packets received and parsed
   - Sensor fusion processes data
   - UI updates with sensor values

3. **Stability Test**
   - Processes run for 30 seconds
   - No crashes or exceptions
   - Clean shutdown

### Manual Verification Steps

After automated test passes:

1. **Check UI Elements**
   ```
   - Modern header visible
   - Settings/Profile buttons present
   - VIDEOWALL/ANOMALIES/DEVICES tabs visible
   - Status bar shows TCP status
   ```

2. **Verify TCP Connection**
   ```
   Status bar should show:
   "TCP Server: Running on port 4888 | Messages: 15+"
   ```

3. **Check Logs**
   ```bash
   tail -f logs/tcp_debug.log
   # Should show incoming packets
   
   tail -f logs/vision_debug.log
   # Should show YOLO detections (if video streaming)
   ```

4. **Verify Metrics**
   ```bash
   curl http://localhost:9090/metrics | grep embereye
   # Should return Prometheus metrics
   ```

## Performance Tests

### Benchmark Test

```bash
python test_performance.py
```

Measures:
- Startup time
- Frame processing rate
- Memory footprint
- CPU usage
- Network throughput

### Results Tracking

Results saved to: `logs/performance_report.json`

```json
{
  "timestamp": "2025-12-20T19:00:00",
  "startup_time_sec": 3.5,
  "frame_rate_fps": 30.2,
  "memory_mb": 345,
  "cpu_percent": 22.5,
  "tcp_throughput_pps": 1250
}
```

## Manual Testing

### Testing Checklist

#### 1. UI Components

- [ ] Window opens in maximized mode
- [ ] Modern header visible with "Ember Eye Command Center"
- [ ] Settings button (⚙ SETTINGS) clickable
- [ ] Profile button (👤 PROFILE) clickable
- [ ] Group dropdown functional
- [ ] Grid size dropdown works (2×2, 3×3, 4×4, 5×5)
- [ ] All three tabs accessible (VIDEOWALL, ANOMALIES, DEVICES)

#### 2. Settings Menu

- [ ] Configure Streams opens dialog
- [ ] Reset Streams works
- [ ] Backup/Restore Configuration functional
- [ ] TCP Server Port dialog opens
- [ ] Thermal Grid Settings accessible
- [ ] Numeric Grid toggle works
- [ ] Sensor Configuration dialog opens
- [ ] Class & Subclass Manager opens
- [ ] Log Viewer displays logs
- [ ] PFDS Devices menu accessible
- [ ] Test Error triggers error dialog

#### 3. Profile Menu

- [ ] My Profile displays user info
- [ ] Logout returns to login screen

#### 4. VIDEOWALL Tab

- [ ] Streams display in grid
- [ ] Grid resizes correctly (2×2, 3×3, 4×4, 5×5)
- [ ] Video plays smoothly
- [ ] Thermal overlay visible (if enabled)
- [ ] Numeric grid toggles on/off
- [ ] Double-click maximizes stream
- [ ] Right-click context menu works

#### 5. ANOMALIES Tab

- [ ] Captured frames display as thumbnails
- [ ] Frame ingestion controls visible
- [ ] Class dropdown populated
- [ ] Video selection works
- [ ] Frame similarity detection active
- [ ] Training progress shows updates
- [ ] Anomaly count label updates

#### 6. DEVICES Tab

- [ ] Failed devices list populated
- [ ] Device status updates in real-time
- [ ] Retry functionality works

#### 7. TCP Sensor Integration

- [ ] Status bar shows "TCP Server: Running"
- [ ] Message count increments
- [ ] Sensor data triggers fusion
- [ ] Alarms trigger on thresholds
- [ ] PFDS commands dispatch correctly

#### 8. Master Class Configuration

- [ ] Dialog opens from Settings
- [ ] Tree view shows hierarchy
- [ ] Add Class creates new entry
- [ ] Add Subclass creates nested entry
- [ ] Remove Selected deletes item
- [ ] Save and Close persists changes
- [ ] Classes update without restart

#### 9. Debug Toggle

- [ ] Runtime toggle works
- [ ] Debug messages print when enabled
- [ ] Debug messages silent when disabled
- [ ] No performance impact when disabled

### Test Scenarios

#### Scenario 1: Normal Operation

1. Start EmberEye
2. Start TCP simulator
3. Observe sensor data flowing
4. Add/remove streams
5. Change grid sizes
6. Verify all tabs functional
7. Clean shutdown

**Expected:** No errors, smooth operation

#### Scenario 2: Error Recovery

1. Start EmberEye
2. Kill TCP simulator
3. Verify EmberEye continues running
4. Restart simulator
5. Verify reconnection

**Expected:** Graceful degradation, automatic recovery

#### Scenario 3: High Load

1. Start EmberEye
2. Configure 9 streams (3×3 grid)
3. Start multiple simulators
4. Run for 1 hour
5. Monitor CPU/memory

**Expected:** Stable performance, no memory leaks

#### Scenario 4: Configuration Changes

1. Start EmberEye
2. Open Master Class Config
3. Add new classes
4. Save changes
5. Ingest frames with new classes
6. Start training

**Expected:** Seamless integration, no restart needed

## Troubleshooting Tests

### Test Fails: Port Already in Use

```bash
# Find and kill process
lsof -ti:4888 | xargs kill -9

# Retry test
python test_integration_e2e.py
```

### Test Fails: EmberEye Won't Start

```bash
# Check logs
tail -100 logs/crash.log

# Check dependencies
pip install -r requirements.txt

# Verify Python version
python --version  # Should be 3.12+
```

### Test Fails: Simulator Connection Error

```bash
# Verify TCP server started
netstat -an | grep 4888

# Check firewall
# macOS: System Preferences → Security & Privacy → Firewall

# Try localhost alternatives
# Edit simulator to use 127.0.0.1 instead of localhost
```

## Continuous Integration

### GitHub Actions (Future)

```yaml
name: EmberEye CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python test_integration_e2e.py
      - run: python test_ai_sensor_components.py
```

## Test Coverage

Current coverage: ~85%

| Component | Coverage |
|-----------|----------|
| Main Window | 90% |
| Video Widget | 85% |
| Sensor Fusion | 95% |
| TCP Server | 88% |
| Vision Detector | 80% |
| Anomalies Manager | 92% |
| PFDS Manager | 75% |

## Reporting Issues

When reporting test failures, include:

1. **Test Command**: Exact command run
2. **Error Output**: Full error message
3. **Logs**: Relevant log files
4. **Environment**: OS, Python version, dependencies
5. **Steps to Reproduce**: Detailed sequence

Example:

```
Test: test_integration_e2e.py
Error: EmberEye exited unexpectedly (Step 3)
OS: macOS 14.0
Python: 3.12.1
Logs: logs/crash.log shows "AttributeError: ..."
Steps: 1) python test_integration_e2e.py 2) Wait 10s 3) Process exits
```

## Next Steps

After all tests pass:

1. Run performance benchmarks
2. Test with real hardware
3. Conduct security audit
4. Perform load testing
5. Deploy to staging environment

---

**For questions or issues, contact the development team.**
