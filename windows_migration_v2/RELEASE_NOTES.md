# EmberEye v2.0 Release Notes

## Version 2.0 - PFDS Integration & Enhanced Logging
**Release Date:** November 29, 2025

### 🎉 Major New Features

#### PFDS Device Management
- **SQLite-backed persistence** for device configuration
- **Add Device dialog** with IP validation, mode selection, and poll frequency
- **View Devices interface** for managing configured devices
- **Background scheduler** automatically sends REQUEST1 commands per device schedule
- **Automatic PERIOD_ON** command for Continuous mode devices
- **TCP command dispatch** with success/failure logging
- **Location ID linking** to camera streams for device-stream association

#### Enhanced Log Viewer
- **Tabbed interface** replacing single error log dialog
- **App Error Log tab**
  - Search by message text
  - Filter by source component
  - Auto-refresh every 2 seconds
  - Export, clear, and copy capabilities
- **TCP Log Viewer tab**
  - Debug/Error mode toggle
  - Location ID filtering
  - Shows raw packets, parse errors, and PFDS commands
  - Last 1000 lines with auto-refresh

#### File-Based Logging
- **TCP Debug Log** (`logs/tcp_debug.log`) - All TCP traffic and commands
- **TCP Error Log** (`logs/tcp_errors.log`) - Parse errors and failures
- **Structured format** with timestamps and location IDs
- **No console pollution** - all logs to files only

### 🔧 Technical Improvements

#### Core Architecture
- New `pfds_manager.py` module with SQLite ORM and threading
- Enhanced `tcp_sensor_server.py` with logging hooks
- New `tcp_logger.py` for centralized TCP logging
- Updated `main_window.py` with PFDS and Log Viewer integration

#### Database Schema
```sql
CREATE TABLE pfds_devices (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    location_id TEXT,
    mode TEXT NOT NULL,  -- 'Continuous' or 'On Demand'
    poll_seconds INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Scheduler Logic
- Single background thread for all devices
- Per-device poll tracking
- One-time PERIOD_ON on scheduler start for Continuous devices
- REQUEST1 dispatched based on individual poll frequencies
- Graceful shutdown on app close

### 🐛 Bug Fixes
- Fixed console stdout flush errors in EXE mode (from v1.0)
- Improved platform-specific single-instance locking
- Enhanced error handling for TCP command dispatch
- Better cleanup of video widget threads on shutdown

### 📝 Documentation Updates
- Comprehensive README.md with troubleshooting
- New QUICKSTART.md for rapid deployment
- Updated setup scripts with error handling
- Windows-specific installation guides

### ⚙️ Configuration Changes
- Menu reorganization: "Configure PFDS Device" submenu under Settings
- "Error Log" renamed to "Log Viewer" under Profile menu
- New keyboard shortcuts (none yet - planned for v2.1)

### 🔄 Migration from v1.0
1. All v1.0 features remain functional
2. Existing stream_config.json compatible
3. New pfds_devices.db created automatically
4. Logs directory auto-created on first run
5. No breaking changes to existing workflows

### 🚀 Performance
- Minimal overhead from scheduler (~1% CPU)
- SQLite queries cached for device list
- Log writes are async to avoid blocking UI
- Video widgets unaffected by new features

### 🛠️ Known Issues & Limitations
1. **Log Rotation**: Logs grow unbounded (planned for v2.1)
2. **Device Validation**: IP format validated, but reachability not tested on add
3. **Command Retry**: No automatic retry for failed PFDS commands
4. **Device Status**: No real-time online/offline status tracking
5. **Bulk Operations**: No bulk add/remove for devices

### 📦 Deployment Notes
- Python 3.11 recommended for Windows builds
- PyInstaller 6.16.0 required (earlier versions may fail)
- NumPy/OpenCV must use pre-built wheels
- Cryptography 41.0.7 pinned for compatibility

### 🔮 Coming in v2.1 (Planned)
- Log rotation with configurable size limits
- Real-time device status monitoring
- Command retry logic with exponential backoff
- Bulk device import from CSV
- Device restart detection
- Enhanced error recovery

### 👥 Credits
- Core development: EmberEye Team
- Windows migration: Automated setup scripts
- Testing: Windows 10/11 validation

### 📞 Support
For issues, check:
- README.md troubleshooting section
- logs/tcp_debug.log and logs/tcp_errors.log
- PyInstaller warn-EmberEye.txt

---

## Version 1.0 - Initial Windows Migration
**Release Date:** November 26, 2025

### Initial Features
- Cross-platform single-instance locking (fcntl/msvcrt)
- TCP sensor server with status indicator
- Basic error logging
- Stream configuration
- Video widget grid with maximize/minimize
- Sensor fusion with thermal overlay
- Gas sensor integration
- Baseline detection
- Windows EXE generation

### Known Issues (Resolved in v2.0)
- Console stdout flush errors in EXE mode ✓
- Port conflict handling needed ✓
- Limited error visibility ✓
