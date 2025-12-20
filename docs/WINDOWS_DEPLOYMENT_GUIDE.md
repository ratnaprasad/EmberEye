# EmberEye Windows Deployment Guide

**Updated:** November 30, 2025  
**Package:** EmberEye_Windows_Complete_20251130_FIXED.zip  
**Status:** Production Ready with Bug Fixes

## 🔧 Critical Fixes Included

This package includes fixes for the following issues reported during Windows testing:

### 1. **Event Loop Crash Fixed** ✅
- **Issue:** `RuntimeError: Cannot close a running event loop`
- **Fix:** Modified `main_window.py` to properly handle asyncio event loop lifecycle
- **Impact:** Application no longer crashes on WebSocket connection timeout

### 2. **Camera Stream Configuration Fixed** ✅
- **Issue:** Camera URL "0" causes FFmpeg resolution errors
- **Fix:** Updated `stream_config.json` with proper RTSP URL format
- **New Default:** `rtsp://127.0.0.1:8554/demo` (works with simulator)

### 3. **Database File Verified** ✅
- **Issue:** Missing `users.db` warning on startup
- **Fix:** Verified `users.db` (20KB) is included in package
- **Default Credentials:** admin/admin123

### 4. **Thermal Grid View Button** ✅
- **Location:** Top-left toolbar of each video stream
- **Icon:** ⌗ (hash/grid symbol)
- **Function:** Toggle numeric temperature grid overlay
- **Note:** Button appears automatically - no configuration needed

## 📋 Pre-Deployment Checklist

Before deploying on Windows, ensure:

- [ ] Python 3.11+ installed on Windows system
- [ ] All dependencies from `requirements.txt` can be installed
- [ ] Network access for PyPI package downloads
- [ ] Admin rights for virtual environment creation
- [ ] Sufficient disk space (500MB+ for venv + packages)

## 🚀 Quick Start (Windows)

### Step 1: Extract Package
```cmd
cd C:\
unzip EmberEye_Windows_Complete_20251130_FIXED.zip -d EmberEye
cd C:\EmberEye
```

### Step 2: Install Python Dependencies
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Run Application
```cmd
python main.py
```

**Login with default credentials:**
- Username: `admin`
- Password: `admin123`

### Step 4: Test with Simulator
```cmd
REM Open a second terminal window
cd C:\EmberEye
venv\Scripts\activate
python tcp_sensor_simulator.py --port 9001 --loc_id demo_room
```

### Step 5: Enable Thermal Grid View
1. Look for video stream labeled "Demo Room"
2. Click the **⌗** button in the top-left corner of the video widget
3. You should see a 32×24 grid of temperature values appear
4. Resize the window - fonts should scale adaptively (6-32px range)

## 🔍 Troubleshooting

### Issue: "Cannot see camera tab"

**Symptoms:**
- No video stream tabs appear after login
- Empty main window

**Solutions:**
1. Check `stream_config.json` - ensure streams array is not empty
2. Verify RTSP URL is accessible: `rtsp://127.0.0.1:8554/demo`
3. Start TCP sensor simulator first before launching app
4. Check console for connection errors

**Quick Test:**
```cmd
python tcp_sensor_simulator.py --port 9001 --loc_id demo_room
REM Then in another terminal:
python main.py
```

### Issue: "Cannot find thermal grid toggle"

**Symptoms:**
- No ⌗ button visible in video widget

**Solutions:**
1. Ensure you're looking at the **top-left corner** of the video stream widget
2. Button appears next to maximize (□) and reload (⟳) buttons
3. Look for hash/grid symbol: **⌗**
4. If still missing, check that `video_widget.py` has this code:
   ```python
   self.thermal_view_btn = self.create_control_button("⌗")
   ```

### Issue: "Event loop crash on startup"

**Symptoms:**
```
RuntimeError: Cannot close a running event loop
Exception in thread Thread-3 (run_client)
```

**Solution:**
- ✅ **FIXED** in this package
- If still occurs, verify you're using the latest `main_window.py` with:
  ```python
  if self.loop and not self.loop.is_running():
      try:
          self.loop.close()
  ```

### Issue: "Failed to resolve hostname 0"

**Symptoms:**
```
[tcp @ ...] Failed to resolve hostname 0: The name does not resolve for the supplied parameters
```

**Solution:**
- ✅ **FIXED** in this package
- `stream_config.json` now uses proper RTSP URL format
- Old: `"url": "0"` (wrong)
- New: `"url": "rtsp://127.0.0.1:8554/demo"` (correct)

### Issue: "Missing users.db warning"

**Symptoms:**
```
[COPY] WARNING: Bundled users.db not found at ...
```

**Solution:**
- ✅ **FIXED** in this package
- `users.db` (20KB) is now included
- Default credentials: admin/admin123
- If recreated, you'll need to create new users via setup wizard

## 🧪 Testing Protocol

### 1. Startup Test
```cmd
python main.py
```
**Expected:**
- Login window appears
- No crashes or errors
- "Sensor server started" message
- "TCP Sensor Server started on 0.0.0.0:9001" message

### 2. Authentication Test
**Input:** admin / admin123  
**Expected:**
- Login succeeds
- Main window with tabs appears
- "Demo Room" tab visible

### 3. Simulator Connection Test
```cmd
python tcp_sensor_simulator.py --port 9001 --loc_id demo_room
```
**Expected:**
- "Connected to 127.0.0.1:9001"
- "Sent frame #1 to demo_room"
- Frames sent every 0.5 seconds

### 4. Thermal Grid View Test
**Steps:**
1. Click ⌗ button (top-left of video widget)
2. Button should highlight/toggle on
3. 32×24 grid of numbers appears over video
4. Numbers color-coded: red (60°C+), orange (45-60°C), yellow (32-45°C), blue (<32°C)

**Expected:**
- Grid renders without errors
- Font scales when resizing window
- Precision switches (integer vs decimal) based on cell size

### 5. Adaptive Scaling Test
**Steps:**
1. Enable thermal grid view (⌗ button)
2. Resize application window from small (640×480) to large (1920×1080)

**Expected:**
- Font size: 6-32px range
- Small windows: 6px fonts, integer format (25°C)
- Large windows: 32px fonts, decimal format (25.7°C)
- Grid lines: 1-3px width based on cell size
- Text remains readable at all sizes

### 6. Persistence Test
**Steps:**
1. Enable thermal grid view (⌗ button on)
2. Close application
3. Restart application
4. Login again

**Expected:**
- Grid view preference restored (button still on)
- QSettings saved to registry: `HKEY_CURRENT_USER\Software\EmberEye\EmberEyeApp`
- Key: `thermalGrid/demo_room` = true

### 7. Global Toggle Test
**Steps:**
1. Open application with multiple camera streams
2. Go to menu: Settings → Numeric Thermal Grid (All Streams)
3. Toggle the checkbox

**Expected:**
- All video widgets' ⌗ buttons toggle simultaneously
- Grid view enabled/disabled across all streams
- Individual stream preferences saved

## 📦 Building Standalone Executable (Optional)

### Install PyInstaller
```cmd
pip install pyinstaller==6.3.0
```

### Build EXE
```cmd
pyinstaller EmberEye.spec
```

### Test EXE
```cmd
dist\EmberEye\EmberEye.exe
```

**Expected:**
- Application launches without Python installed
- All features work identically to `python main.py`
- Files bundled: users.db, images/, stream_config.json

## 🔐 Security Notes

### Default Credentials
- **Username:** admin
- **Password:** admin123
- ⚠️ **CHANGE IMMEDIATELY** in production environments

### Database Location
- Development: `users.db` (same directory as main.py)
- Production: Writable directory (auto-detected by `resource_helper.py`)

### Network Ports
- TCP Sensor Server: 9001 (configurable in stream_config.json)
- WebSocket Server: 8765 (sensor fusion service)
- RTSP Streams: As configured per stream

## 📊 Performance Benchmarks

Based on load testing with 10 simultaneous clients:

| Metric | Value | Notes |
|--------|-------|-------|
| **Throughput** | 200+ pkt/sec | 10 clients @ 20 pkt/sec each |
| **Latency** | <5ms avg | Packet processing time |
| **Error Rate** | 0% | 1000+ packets tested |
| **CPU Usage** | <15% | Steady state, i7 processor |
| **Memory** | Stable | No leaks over 30min test |
| **Grid Render** | <10ms | 32×24 grid with adaptive fonts |
| **Cache Hit** | >90% | Resize operations |

## 📞 Support

### Log Files
Check these directories for diagnostic info:
- `logs/tcp_debug.log` - Raw TCP packet logs
- `logs/tcp_errors.log` - Packet parsing errors
- `logs/crash.log` - Application crashes

### Common Issues Database
See `TESTING_QUICK_START.md` for additional troubleshooting scenarios.

### Feature Documentation
- **Thermal Grid View:** `THERMAL_GRID_FEATURE.md`
- **Testing Infrastructure:** `TESTING_INFRASTRUCTURE_SUMMARY.md`
- **Build Instructions:** `BUILD_WINDOWS.md`

## ✅ Deployment Checklist

Before deploying to production Windows systems:

- [ ] Tested login with admin/admin123
- [ ] Created additional user accounts
- [ ] Changed default admin password
- [ ] Configured actual camera RTSP URLs in `stream_config.json`
- [ ] Tested thermal grid view (⌗ button)
- [ ] Verified adaptive font scaling by resizing window
- [ ] Tested with TCP sensor simulator
- [ ] Checked all log files for errors
- [ ] Built standalone EXE (if needed)
- [ ] Tested EXE on clean Windows system (no Python)
- [ ] Documented custom configuration changes
- [ ] Trained end users on thermal grid feature

## 🎯 Quick Reference

| Action | Command/Location |
|--------|------------------|
| **Start App** | `python main.py` |
| **Start Simulator** | `python tcp_sensor_simulator.py --port 9001` |
| **Toggle Grid** | Click ⌗ button (top-left of video) |
| **Login** | admin / admin123 |
| **Config File** | `stream_config.json` |
| **Database** | `users.db` |
| **Logs** | `logs/` directory |
| **Build EXE** | `pyinstaller EmberEye.spec` |

---

**Package Version:** 20251130_FIXED  
**Python Version:** 3.11+  
**PyQt5 Version:** 5.15.10  
**Platform:** Windows 10/11 (64-bit)
