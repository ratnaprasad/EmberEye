# EmberEye v2.0 - Quick Start Guide

## Installation (5 Minutes)

### Step 1: Install Python 3.11
Download from https://www.python.org/downloads/
✓ Check "Add Python to PATH" during installation

### Step 2: Run Setup
```batch
setup_windows_complete.bat
```
Wait for all dependencies to install (~5 minutes)

### Step 3: Create Icon (Optional)
If you have ImageMagick:
```batch
magick convert logo.png -define icon:auto-resize=256,128,64,48,32,16 logo.ico
```

Or use online converter: https://convertio.co/png-ico/

### Step 4: Build EXE
```batch
venv\Scripts\activate
pyinstaller EmberEye.spec
```

### Step 5: Run
```batch
dist\EmberEye\EmberEye.exe
```

Default login: `admin` / `password`

## New Features Quick Test

### 1. PFDS Device Management
- Settings → Configure PFDS Device → Add Device...
- Enter: Name: "TestDevice", IP: "192.168.1.50", Mode: Continuous, Poll: 10s
- Click OK
- Settings → Configure PFDS Device → View Devices to confirm

### 2. Log Viewer
- Settings → Log Viewer...
- Click "TCP Log Viewer" tab
- Select "Debug" mode
- See PFDS commands appearing every 10s

### 3. TCP Logging
All TCP traffic is now logged to files:
- `logs/tcp_debug.log` - All packets and commands
- `logs/tcp_errors.log` - Parse errors and failures

## Troubleshooting

**NumPy Error?**
```batch
setup_windows_numpy_fix.bat
```

**Conda User?**
```batch
setup_windows_conda.bat
```

**Port Already in Use?**
- Settings → TCP Server Port... → Change to 9002

## What Changed from v1.0?

| Feature | v1.0 | v2.0 |
|---------|------|------|
| Error Log | Simple dialog | Tabbed viewer with search/filter |
| TCP Logs | Console only | File-based with modes |
| PFDS Devices | N/A | Full management + scheduler |
| Commands | N/A | REQUEST1/PERIOD_ON dispatch |
| Location IDs | Manual | Auto-populated from streams |

## File Locations

```
dist/EmberEye/
├── EmberEye.exe           # Main executable
├── logs/                  # Created on first run
│   ├── tcp_debug.log
│   └── tcp_errors.log
├── pfds_devices.db        # Created when adding devices
└── stream_config.json     # Created on first stream config
```

## Support

Need help? Check:
1. `README.md` for detailed docs
2. `logs/` directory for error messages
3. `warn-EmberEye.txt` in build folder
