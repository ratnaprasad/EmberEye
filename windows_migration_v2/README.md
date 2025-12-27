# EmberEye Windows Migration Package v2.0

This package contains everything needed to migrate EmberEye to Windows with the latest features:
- **Log Viewer** with tabbed interface (App Error Log + TCP Log Viewer)
- **PFDS Device Management** (Add/View/Remove devices with scheduler)
- **TCP Command Dispatch** to PFDS devices
- **Enhanced Logging** (file-based TCP logs with debug/error modes)

## What's New in v2.0

### UI Enhancements
- Renamed "Error Log" to "Log Viewer" with tabbed interface
- New "Configure PFDS Device" submenu under Settings
- Add Device dialog with IP validation, mode selection (Continuous/On Demand), and poll frequency
- View Devices dialog with SQLite-backed persistence and remove functionality

### Backend Features
- SQLite database for PFDS device persistence (`pfds_devices.db`)
- Background scheduler sending REQUEST1 commands per device poll schedule
- Automatic PERIOD_ON command for Continuous mode devices
- TCP transport for PFDS commands with success/failure logging
- File-based TCP logging (`logs/tcp_debug.log`, `logs/tcp_errors.log`)

### Files Included
- All Python source files with latest updates
- `pfds_manager.py` - New PFDS device manager with SQLite and scheduler
- `tcp_logger.py` - TCP logging module
- Updated `main_window.py` with new UI and PFDS integration
- Windows-specific setup scripts and requirements
- PyInstaller spec file for EXE generation

## Prerequisites

- Windows 10/11
- Python 3.11 (recommended) or Python 3.9-3.12
- Administrator privileges (for installing dependencies)

## Installation Steps

### Option 1: Full Setup (Recommended for First-Time Setup)

1. **Install Python 3.11**
   - Download from https://www.python.org/downloads/
   - During installation, check "Add Python to PATH"
   - Verify: `python --version` (should show 3.11.x)

2. **Run the automated setup**
   ```batch
   setup_windows_complete.bat
   ```
   This will:
   - Create a virtual environment
   - Install all dependencies with pre-built wheels
   - Handle numpy/opencv/PyQt5 compatibility
   - Install PyInstaller and cryptography

3. **If numpy fails**, run the fallback script:
   ```batch
   setup_windows_numpy_fix.bat
   ```

### Option 2: Conda Environment (Alternative)

If you have Anaconda/Miniconda installed:

```batch
setup_windows_conda.bat
```

This creates a conda environment with all dependencies pre-compiled.

## Building the Windows EXE

1. **Activate your environment**
   - Virtual env: `venv\Scripts\activate`
   - Conda: `conda activate embereye`

2. **Create the icon file** (if not present)
   
   If `logo.ico` doesn't exist, create it from `logo.png`:
   ```batch
   magick convert logo.png -define icon:auto-resize=256,128,64,48,32,16 logo.ico
   ```
   
   Or use an online converter: https://convertio.co/png-ico/

3. **Build the EXE**
   ```batch
   pyinstaller EmberEye.spec
   ```

4. **Test the executable**
   ```batch
   dist\EmberEye\EmberEye.exe
   ```

## Using the New Features

### PFDS Device Management

1. **Add a Device**
   - Open app → Settings → Configure PFDS Device → Add Device...
   - Enter device name, IP address (validated), location ID (from streams)
   - Select mode: Continuous (auto sends PERIOD_ON) or On Demand
   - Set poll frequency in seconds (1-3600)
   - Click OK to save

2. **View/Remove Devices**
   - Settings → Configure PFDS Device → View Devices...
   - See all configured devices with ID, name, IP, location, mode, poll frequency
   - Select a row and click "Remove Selected" to delete

3. **Monitor Commands**
   - Settings → Log Viewer... → TCP Log Viewer tab
   - Select "Debug" mode to see all PFDS commands
   - Filter by Location ID if needed
   - Commands show as: `PFDS_CMD REQUEST1 to 192.168.1.50 (DeviceName) | sent`
   - Errors logged to Error mode

### Log Viewer

1. **App Error Log**
   - Shows all application errors from `error_logger`
   - Search by message text
   - Filter by source component
   - Auto-refreshes every 2 seconds
   - Export to JSON, clear, or copy selected entries

2. **TCP Log Viewer**
   - Toggle between Debug and Error modes
   - Filter by Location ID
   - Shows raw TCP packets, parse errors, and PFDS commands
   - Loads last 1000 lines from log files
   - Auto-refreshes every 2 seconds

## Troubleshooting

### Build Issues

**Error: numpy not found or build fails**
- Run `setup_windows_numpy_fix.bat`
- Or manually: `pip install numpy --only-binary :all:`

**Error: PyInstaller version not found**
- Edit `requirements_windows.txt` and change `pyinstaller==6.16.0` to `pyinstaller==6.10.0`
- Re-run setup

**Error: cryptography build fails**
- Install pre-built wheel: `pip install cryptography==41.0.7 --only-binary :all:`

**Error: logo.ico not found**
- Create icon using ImageMagick: `magick convert logo.png -define icon:auto-resize=256,128,64,48,32,16 logo.ico`
- Or download a converter tool

### Runtime Issues

**TCP Server won't start**
- Port already in use: Settings → TCP Server Port... → Change to different port
- Check Windows Firewall settings
- Verify no other app using the port: `netstat -ano | findstr :<port>`

**PFDS commands not sending**
- Check device IP is reachable: `ping <device_ip>`
- Verify TCP port matches device configuration
- Check TCP Error logs in Log Viewer

**Database errors**
- Delete `pfds_devices.db` and `stream_config.json` to reset
- Restart application

### Log Files Not Created

- Logs are written to `logs/` directory in the app folder
- On first run, directory is auto-created
- For EXE, logs are in the same folder as `EmberEye.exe`

## File Structure

```
EmberEye/
├── main.py                          # Entry point (single-instance, platform checks)
├── main_window.py                   # Main UI (updated with Log Viewer & PFDS)
├── pfds_manager.py                  # NEW: PFDS device manager with SQLite & scheduler
├── tcp_logger.py                    # NEW: TCP logging module
├── tcp_sensor_server.py             # TCP server with logging hooks
├── error_logger.py                  # App error logging (JSON-based)
├── ee_loginwindow.py                # Login UI
├── database_manager.py              # User database
├── video_widget.py                  # Camera feed widget
├── sensor_fusion.py                 # Multi-sensor fusion
├── gas_sensor.py                    # Gas sensor calculations
├── baseline_manager.py              # Baseline detection
├── stream_config.py                 # Stream configuration
├── EmberEye.spec                    # PyInstaller spec
├── requirements_windows.txt         # Windows dependencies
├── setup_windows_complete.bat       # Full setup script
├── setup_windows_numpy_fix.bat      # NumPy fallback script
├── setup_windows_conda.bat          # Conda setup script
├── logo.png / logo.ico              # App icon
├── logs/                            # Log directory (auto-created)
│   ├── tcp_debug.log               # TCP debug logs
│   └── tcp_errors.log              # TCP error logs
├── pfds_devices.db                  # PFDS device database (auto-created)
└── stream_config.json               # Stream configuration
```

## Known Limitations

1. **PFDS Command Protocol**
   - Currently sends plain text commands over TCP
   - No retry logic for failed commands
   - Device restart detection not implemented

2. **Log Rotation**
   - Logs grow unbounded (rotation planned for future)
   - Manually clear old logs if needed

3. **Device Validation**
   - IP format validated, but reachability not tested on add
   - Test connectivity manually with ping/telnet

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review `warn-EmberEye.txt` after PyInstaller build
- Test with Python directly before building EXE

## Version History

**v2.0 (Current)**
- Added PFDS device management with SQLite persistence
- Implemented scheduler for REQUEST1/PERIOD_ON commands
- Renamed Error Log to Log Viewer with tabs
- Added TCP Log Viewer with debug/error modes
- Integrated TCP command dispatch to devices

**v1.0**
- Initial Windows migration
- Basic TCP server with status indicator
- Error logging
- Stream configuration
