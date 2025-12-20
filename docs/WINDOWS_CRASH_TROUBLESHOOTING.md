# EmberEye Windows Crash Troubleshooting Guide

## Common Crash Causes & Fixes

### 1. **Crash After 2 Minutes (WebSocket Connection Issue)**
**Symptom:** App launches but crashes after ~2 minutes with no error message.

**Cause:** WebSocket client trying to connect to `ws://localhost:8765` times out.

**Fixed in latest version:** WebSocket connection is now optional and won't block the app.

**Manual Fix (if using old version):**
- Comment out WebSocket initialization in `main_window.py`:
  ```python
  # self.ws_client = WebSocketClient()
  # self.ws_client.data_received.connect(self.handle_sensor_data)
  # self.ws_client.start()
  ```

---

### 2. **Port Already in Use**
**Symptom:** Error message about TCP port already in use.

**Fix:**
1. Edit `stream_config.json`:
   ```json
   {
     "groups": ["Default"],
     "streams": [],
     "tcp_port": 9002
   }
   ```
2. Change `9001` to another port (e.g., `9002`, `9003`, etc.)
3. Restart the app

---

### 3. **Missing DLL Files**
**Symptom:** Error about missing VCRUNTIME140.dll or similar.

**Fix:** Install Visual C++ Redistributable:
- Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
- Run installer
- Restart computer

---

### 4. **Database Lock Error**
**Symptom:** SQLite database locked errors in logs.

**Fix:**
1. Close all EmberEye instances
2. Delete `users.db` file (you'll need to recreate admin account)
3. Restart app

---

### 5. **Crash Logs**
**Location:** `logs\crash.log` (in same folder as EXE)

**How to check:**
1. Navigate to EXE folder
2. Open `logs\crash.log` in Notepad
3. Look for latest timestamp
4. Share the error traceback for support

**Example crash log:**
```
================================================================================
Crash at: 2025-11-29 14:30:45
================================================================================
Traceback (most recent call last):
  File "main.py", line 50, in <module>
  ...
```

---

### 6. **Video Stream Errors**
**Symptom:** App crashes when adding RTSP streams.

**Fixes:**
- Ensure OpenCV DLLs are bundled (should be automatic with PyInstaller)
- Test stream URL in VLC first to verify it works
- Reduce number of simultaneous streams (max 9 recommended for 3x3 grid)

---

### 7. **Memory Leaks / Slow Crashes**
**Symptom:** App becomes sluggish over time then crashes.

**Fixes:**
- Reduce grid size (use 2x2 instead of 4x4)
- Lower video resolution in stream configuration
- Restart app daily for long-running deployments

---

### 8. **Sensor Server Timeout**
**Symptom:** TCP sensor connections hang or timeout.

**Fixed in latest version:** Server now has 1-second timeout on accept and 30-second timeout on client operations.

**Verify Fix:**
- Check `logs\tcp_debug.log` for connection errors
- Ensure firewall allows port (default 9001)
- Test with: `telnet localhost 9001`

---

## Emergency Debugging Steps

1. **Enable console output:**
   - Run from Command Prompt instead of double-clicking:
     ```cmd
     cd C:\EmberEye
     dist\EmberEye\EmberEye.exe
     ```
   - Errors will print to console

2. **Check logs directory:**
   - `logs\crash.log` - Fatal errors
   - `logs\tcp_debug.log` - TCP sensor packets
   - `logs\tcp_error.log` - TCP parsing errors

3. **Clean rebuild:**
   ```cmd
   rmdir /s /q build dist
   windows_bundle\setup_windows_complete.bat
   ```

4. **Test in Python (before building EXE):**
   ```cmd
   .venv\Scripts\activate
   python main.py
   ```

---

## Reporting Crashes

When reporting crashes, please include:
1. **Crash log:** Copy from `logs\crash.log`
2. **Windows version:** Run `winver` to check
3. **Python version:** Run `.venv\Scripts\python --version`
4. **Steps to reproduce:** What you did before crash
5. **Timing:** Does it crash immediately or after X minutes?

---

## Known Issues (Fixed in Latest Build)

✅ **WebSocket connection timeout** - Now gracefully handled  
✅ **TCP server blocking** - Now uses timeouts to prevent hangs  
✅ **Missing crash logs** - Now logs all exceptions to file  

Make sure you're using the latest build from today (Nov 29, 2025).
