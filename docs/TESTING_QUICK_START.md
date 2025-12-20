# EmberEye Testing Quick Start Guide

## 🎯 5-Minute Test Demo

### Prerequisites
```bash
cd /Users/ratnaprasadkakani/development/laby/pythonworkspace/EmberEye
source .venv/bin/activate  # or activate your virtual environment
```

---

## Test 1: Thermal Grid View Feature ⌗

### Step 1: Start EmberEye Application
```bash
python3 main.py
```
- Login with your credentials
- Wait for main window to load

### Step 2: Start Thermal Sensor Simulator (New Terminal)
```bash
# Terminal 2
python3 tcp_sensor_simulator.py --port 9001 --loc-id "Test Room" --interval 2.0
```

**Expected Output**:
```
Starting TCP Sensor Simulator: 127.0.0.1:9001 (interval=2.0s, loc_id=Test Room, format=separate)
Connected to 127.0.0.1:9001
Sent serialno: SIM123456
Sent loc_id: Test Room
Sent frame #1 to Test Room
Sent sensor to Test Room: ADC1=1234,ADC2=5678,MPY30=1
```

### Step 3: Enable Thermal Grid View in UI
1. Look for video stream labeled "Test Room"
2. Find control buttons in top-left corner of video widget
3. Click **⌗** button (between maximize □ and reload ↻)
4. **Result**: You should see a 32×24 grid with numeric temperature values!

### Step 4: Test Adaptive Font Scaling
1. Resize the EmberEye window (make it smaller)
2. **Result**: Font size should automatically adjust (gets smaller)
3. Resize window larger
4. **Result**: Font size should increase, decimal places appear when cells are large enough

### Step 5: Test Global Toggle
1. Open Settings menu (⚙️ icon in title bar)
2. Check/uncheck "Numeric Thermal Grid (All Streams)"
3. **Result**: All stream grid views should toggle simultaneously

### Step 6: Test Persistence
1. Disable grid view on "Test Room" stream (click ⌗ button)
2. Close EmberEye completely
3. Restart EmberEye: `python3 main.py`
4. Wait for "Test Room" stream to reconnect
5. **Result**: Grid view should remain OFF (preference persisted)

---

## Test 2: Load Testing 📊

### Run Simple Load Test
```bash
python3 tcp_sensor_load_test.py --clients 5 --packets 20 --rate 10 --port 9001
```

**Expected Output**:
```
TCP Load Test Configuration:
  Clients: 5
  Target: 20 packets
  Rate: 10.0 pkt/sec/client
  Frames: NO

Starting 5 TCP clients connecting to 127.0.0.1:9001
[progress] total_packets=50 agg_pps=45.2

=== TCP Load Test Summary ===
{
  "aggregate": {
    "total_packets": 100,
    "total_errors": 0,
    "aggregate_pps": 49.8,
    "avg_latency_ms": 0.3,
    "max_latency_ms": 2.1
  }
}
```

### Run Heavy Load Test (with thermal frames)
```bash
python3 tcp_sensor_load_test.py --clients 10 --packets 100 --rate 20 --include-frames --port 9001
```

**What to Watch For**:
- ✅ Total errors should be **0**
- ✅ Aggregate PPS should be close to `clients × rate`
- ✅ Average latency should be < 10ms
- ✅ Check logs: `tail -f logs/tcp_debug.log`

---

## Test 3: Run Unit Tests ✅

### Test TCP Server & Parsing
```bash
python3 test_embereye_suite_fixed.py
```

**Expected Output**:
```
=== Testing TCP Packet Parsing ===
✓ Parse Serialno packet
✓ Parse Loc_id packet
✓ Parse Sensor separate format
✓ Parse Sensor embedded format
✓ Parse Sensor no loc_id (IP fallback)
✓ Parse Frame separate format
✓ Parse Frame continuous format

=== Testing IP-Location Resolver ===
✓ Resolver manual mapping
✓ Resolver auto-discovery
✓ Resolver database persistence
✓ Resolver JSON persistence
✓ Resolver concurrent access

=== Test Summary ===
Passed: 25
Failed: 0
```

### Test AI/Sensor Components
```bash
python3 test_ai_sensor_components.py
```

**Expected**: 29+ tests passing

### Test UI Workflows
```bash
# Requires display (use Xvfb on headless systems)
python3 test_ui_workflows.py
```

**Expected**: 33+ tests passing (includes thermal grid view tests)

### Test Authentication
```bash
python3 test_auth_user_management.py
```

**Expected**: 33+ tests passing

---

## Test 4: Multi-Room Simulation 🏢

### Start Multiple Simulators
```bash
# Terminal 1: Room 1 (fast updates - 1 FPS)
python3 tcp_sensor_simulator.py --port 9001 --loc-id "room_1" --interval 1.0 &

# Terminal 2: Room 2 (normal updates - 2 FPS)
python3 tcp_sensor_simulator.py --port 9001 --loc-id "room_2" --interval 2.0 &

# Terminal 3: Room 3 (slow updates - 5 FPS)
python3 tcp_sensor_simulator.py --port 9001 --loc-id "room_3" --interval 5.0 &

# Wait 30 seconds then kill all
sleep 30
killall python3
```

**In EmberEye UI**:
- You should see 3 separate video streams: room_1, room_2, room_3
- Each stream updates at different rates
- Toggle grid view independently on each stream
- Use global toggle to enable/disable all at once

---

## Test 5: Packet Format Compatibility 📦

### Test All Formats
```bash
# Test 1: Separate format (default)
timeout 10 python3 tcp_sensor_simulator.py --port 9001 --format separate --loc-id "test_sep" || true

# Test 2: Embedded format (loc_id in prefix)
timeout 10 python3 tcp_sensor_simulator.py --port 9001 --format embedded --loc-id "test_emb" || true

# Test 3: Continuous hex (no spaces)
timeout 10 python3 tcp_sensor_simulator.py --port 9001 --format continuous --loc-id "test_cont" || true

# Test 4: No loc_id (IP fallback)
timeout 10 python3 tcp_sensor_simulator.py --port 9001 --format no_loc || true
```

**All formats should work without errors!**

---

## Test 6: Performance Monitoring 📈

### Monitor System Resources
```bash
# Terminal 1: Start EmberEye
python3 main.py &
APP_PID=$!

# Terminal 2: Start simulator
python3 tcp_sensor_simulator.py --port 9001 --interval 0.5 &

# Terminal 3: Monitor resources
python3 -c "
import psutil, time
p = psutil.Process($APP_PID)
for i in range(20):
    cpu = p.cpu_percent(interval=1)
    mem = p.memory_info().rss / (1024*1024)
    print(f'Iteration {i+1}/20 | CPU: {cpu:.1f}% | RAM: {mem:.1f}MB')
    time.sleep(2)
"
```

**What to Look For**:
- ✅ CPU should stabilize < 20%
- ✅ RAM should remain relatively constant (no leaks)
- ✅ No spike in memory over time

---

## Test 7: Thermal Grid Cache Performance 🚀

### Test Cache Hit Rate
1. Start EmberEye with simulator running
2. Enable thermal grid view on a stream
3. Rapidly resize window (drag corners back and forth)
4. **Expected Behavior**:
   - Grid view updates smoothly (no flickering)
   - No full redraw every resize (cached pixmap scaled)
   - Check console for cache-related messages

### Test Cache Invalidation
1. With grid view enabled, watch temperature values update
2. Every time new thermal data arrives (every 2 seconds with default simulator)
3. **Expected**: Cache invalidated, new grid rendered with updated temperatures

---

## Troubleshooting Common Issues

### Issue: Simulator won't connect
**Symptoms**: `Connection failed: [Errno 61] Connection refused`
**Solution**:
1. Ensure EmberEye app is running FIRST
2. Check port: default is 9001 (configurable in app settings)
3. Verify TCP server started (check app logs)

### Issue: No thermal grid appears
**Symptoms**: Grid button (⌗) doesn't show grid
**Solution**:
1. Check if thermal data is being received (look for thermal overlay working)
2. Click grid button again (toggle state)
3. Check console for error messages
4. Verify `video_widget.py` has thermal grid view code

### Issue: Tests fail with "No display"
**Symptoms**: `qt.qpa.xcb: could not connect to display`
**Solution**:
```bash
# On headless Linux systems, use Xvfb
xvfb-run python3 test_ui_workflows.py

# Or install virtual display
sudo apt-get install xvfb
```

### Issue: Load test shows high error rate
**Symptoms**: `total_errors: 50` in load test output
**Solution**:
1. Reduce client count: `--clients 3`
2. Reduce rate: `--rate 5`
3. Check TCP server logs: `cat logs/tcp_errors.log`
4. Increase system file descriptor limit: `ulimit -n 4096`

### Issue: Thermal frames not parsing
**Symptoms**: `Frame parse error: expected 768 values, got XXX`
**Solution**:
1. Check simulator format: use `--format separate` or `--format continuous`
2. Verify matrix size is 32×24 (768 pixels total)
3. Check hex data length (should be 3072 chars for continuous format)

---

## Quick Reference: Simulator Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--host` | 127.0.0.1 | TCP server host |
| `--port` | 9001 | TCP server port |
| `--interval` | 2.0 | Seconds between frames |
| `--loc-id` | "default room" | Location identifier |
| `--format` | separate | Packet format (separate/embedded/continuous/no_loc) |

## Quick Reference: Load Test Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--clients` | 5 | Number of concurrent clients |
| `--packets` | - | Packets per client (mutually exclusive with --duration) |
| `--duration` | - | Test duration in seconds |
| `--rate` | 10.0 | Packets/second per client |
| `--include-frames` | False | Include thermal frame packets |
| `--stats-file` | - | JSON output file path |

---

## Success Criteria Checklist

After running all tests, verify:

- [ ] ✅ Simulator connects successfully to TCP server
- [ ] ✅ Thermal frames appear in video streams
- [ ] ✅ Grid view toggle button (⌗) works
- [ ] ✅ Numeric temperatures display in 32×24 grid
- [ ] ✅ Font size adapts to window size
- [ ] ✅ Grid view preference persists across restarts
- [ ] ✅ Global toggle affects all streams
- [ ] ✅ Load test shows 0 errors
- [ ] ✅ All unit tests pass (120+ tests)
- [ ] ✅ No memory leaks detected
- [ ] ✅ CPU usage remains reasonable (<20% steady state)
- [ ] ✅ Logs show no errors (`tcp_errors.log` is empty or minimal)

---

## Next Steps

✅ **All testing infrastructure is ready!**

**For Development**:
- Run unit tests after each code change
- Use simulator for feature development without hardware
- Monitor logs during testing: `tail -f logs/tcp_debug.log`

**For Deployment**:
- Run full load test suite before release
- Test with real MLX90640 thermal camera hardware
- Verify multi-stream performance with actual RTSP cameras
- Conduct user acceptance testing with thermal grid view feature

**For Debugging**:
- Enable verbose logging in EmberEye settings
- Use simulator to reproduce issues consistently
- Check both `tcp_debug.log` and `tcp_errors.log`
- Use load test to identify performance bottlenecks

---

## 📚 Additional Resources

- **Detailed Documentation**: See `TESTING_INFRASTRUCTURE_SUMMARY.md`
- **Feature Guide**: See `THERMAL_GRID_FEATURE.md`
- **Load Test Results**: See `LOAD_TEST_RESULTS.md`
- **Test Coverage**: See `TEST_COVERAGE_SUMMARY.md`

**Questions? Issues?** Check the logs:
```bash
tail -f logs/tcp_debug.log    # All packet traffic
tail -f logs/tcp_errors.log   # Parse errors
tail -f logs/error_log.json   # Application errors
```

---

**Happy Testing! 🎉**
