# EmberEye Distribution Package

## 📦 What's Included

### Executable Applications
- **macOS:** `EmberEye.app` (81 MB)
- **Windows:** Build on Windows using `build_installer.py` → `EmberEye.exe`
- **Linux:** Build on Linux using `build_installer.py` → `EmberEye` binary

### Pre-configured Users (All Platforms)
All executables come with these accounts ready to use:

| Username | Password | Role |
|----------|----------|------|
| admin | password | Administrator |
| ratna | ratna | Standard User |
| s3micro | s3micro | Demo User |

### Included Files
- ✓ Phoenix logo (logo.png)
- ✓ User database (users.db) with 3 accounts
- ✓ Configuration file (stream_config.json)
- ✓ User documentation (README.txt)

## 🚀 Quick Start

### macOS
1. Double-click `EmberEye.app`
2. If security warning appears:
   - System Preferences → Security & Privacy
   - Click "Open Anyway"
3. Login with any account above

### Windows
1. Run `EmberEye.exe`
2. If Windows Defender blocks:
   - Click "More info"
   - Click "Run anyway"
3. Login with any account above

### Linux (Ubuntu/Debian)
```bash
chmod +x EmberEye
./EmberEye
```

## ✨ Features

- **Multi-Sensor Fusion:** Thermal, gas, flame, and vision detection
- **Persistent Hot Cell Display:** 5-second decay with fade-out
- **Frame Freeze on Alarm:** Camera view freezes when fire detected
- **Real-time Sensor Data:** Live PPM, smoke %, flame status
- **Configurable Thresholds:** Adjust sensitivity via Settings menu
- **Phoenix Branding:** Professional logo and UI

## 🔧 Building from Source

See `BUILD_GUIDE.md` for detailed instructions on:
- Building for different platforms
- Creating installers (.dmg, .exe, .deb, .rpm)
- Cross-platform compilation
- Troubleshooting

### Quick Build Command
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python build_installer.py
```

## 📋 System Requirements

### All Platforms
- Python 3.8+ (for source builds)
- 500 MB disk space
- 2 GB RAM minimum
- Network access for camera streams

### macOS
- macOS 10.14 (Mojave) or later
- Both Intel and Apple Silicon supported

### Windows
- Windows 10 or later
- 64-bit only

### Linux
- Ubuntu 20.04+, Debian 10+, or compatible
- X11 or Wayland display server

## 🎯 Demo Workflow

1. **Start Application**
   ```bash
   # macOS
   open EmberEye.app
   
   # Windows
   EmberEye.exe
   
   # Linux
   ./EmberEye
   ```

2. **Login**
   - Use `s3micro/s3micro` for demo

3. **Configure Cameras** (Optional)
   - Settings → Stream Configuration
   - Add RTSP/MJPEG camera URLs

4. **Run Simulator** (For testing)
   ```bash
   python tcp_sensor_simulator_v3.py --host 127.0.0.1 --port 9001 --loc-id "default room"
   ```

5. **Observe**
   - Hot cells appear on thermal grid
   - Frame freezes on alarm
   - Fusion panel shows sensor data
   - Confidence bar indicates risk level

## 🎨 Sensor Configuration

Access via: **Settings → Sensor Configuration**

### Tab 1: Fusion Thresholds
- Temperature threshold (0-255)
- Gas PPM threshold
- Flame active value
- Minimum sources for alarm
- Vision threshold and weight

### Tab 2: Gas Calibration
- R0 (clean air resistance)
- RL (load resistance)
- VCC (circuit voltage)

### Tab 3: Display Settings
- Hot cell decay time (seconds)
- Frame freeze on alarm (toggle)
- Show fusion overlay (toggle)

## 📊 Understanding the Display

### Thermal Grid
- **Red cells:** High heat (>threshold)
- **Yellow cells:** Moderate heat
- **Fade-out:** 5-second persistence

### Fusion Panel (Top-right overlay)
```
┌─────────────────────────────┐
│ 🔥 ALARM ACTIVE             │
│ Confidence: ████░░ 76%      │
│ 📷 🌡️ 💨 🔥 (active sensors)│
│ Thermal: 234°C              │
│ Gas: 523 PPM (Hazardous)    │
│ Smoke: 87%                  │
│ Flame: DETECTED             │
└─────────────────────────────┘
```

## 🔐 Security Notes

- Passwords are bcrypt hashed in `users.db`
- Change default passwords in production
- Admin account can create new users
- 3 failed login attempts = account lock

## 🐛 Troubleshooting

### Cannot Login
- Verify username/password (case-sensitive)
- Check database file exists: `users.db`
- Reset: Delete `users.db`, restart app (recreates with defaults)

### No Camera Feed
- Verify RTSP/MJPEG URL
- Check network connectivity
- Test URL in VLC player first

### No Thermal Data
- Ensure TCP sensor server running
- Check port 9001 not blocked
- Verify loc_id matches camera location

### Performance Issues
- Reduce number of cameras
- Lower resolution in camera settings
- Disable fusion overlay if not needed

## 📞 Support

**S3 Micro Technologies**
- Email: support@s3micro.com
- Web: https://s3micro.com
- Phone: [Contact Number]

## 📄 License

Copyright © 2025 S3 Micro Technologies
All rights reserved.

---

**Version:** 1.0.0  
**Build Date:** November 2025  
**Platform:** Cross-platform (macOS, Windows, Linux)
