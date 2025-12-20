# Device Monitoring & Auto-Reconnection System

## Overview
The EmberEye application now includes comprehensive device connection monitoring with automatic reconnection capabilities. When devices go offline (network issues, power loss, etc.), the system automatically attempts to reconnect and restore communication.

## Key Features

### 1. **Automatic Device Status Tracking**
- Monitors all PFDS devices in real-time
- Tracks online/offline status
- Records last seen timestamp
- Logs failure reasons

### 2. **Intelligent Auto-Reconnection**
- Automatically detects offline devices (30-second timeout)
- Attempts reconnection every 10 seconds
- Maximum 5 consecutive retry attempts
- Resends initialization commands (EEPROM1 + PERIOD_ON)

### 3. **Failed Devices Monitoring Tab**
A new tab appears beside the "Anomalies" tab showing:
- All offline/failed devices
- Connection statistics (Total/Online/Offline)
- Last seen timestamps
- Failure reasons
- Connection attempt counts

### 4. **Manual Reconnection Controls**
- Individual device reconnect buttons
- "Reconnect All" for bulk recovery
- Auto-reconnect toggle per device
- Real-time status updates

## How It Works

### Automatic Monitoring
1. **Activity Tracking**: Every time a device sends data (sensor readings, thermal frames), its "last seen" timestamp is updated
2. **Health Checks**: Background monitor checks device activity every 5 seconds
3. **Offline Detection**: If no data received for 30 seconds, device marked as offline
4. **Auto-Retry**: System attempts reconnection every 10 seconds (max 5 attempts)

### Reconnection Process
When a device goes offline:
1. Device status changes to "Offline" in Failed Devices tab
2. System waits 10 seconds before first retry
3. Sends EEPROM1 command for calibration data
4. Sends PERIOD_ON (Continuous mode) or REQUEST1 (On-Demand mode)
5. If device responds, marked as "Online" automatically
6. If no response after 5 attempts, auto-retry stops (manual reconnect available)

## Using the Failed Devices Tab

### Viewing Device Status
- **Total**: Number of registered PFDS devices
- **Online**: Devices currently connected and sending data
- **Offline**: Devices that are unreachable

### Device Information Columns
- **Device Name**: Name configured in PFDS settings
- **IP Address**: Device network address
- **Location ID**: Camera location identifier
- **Type**: Device type (PFDS, TCP, etc.)
- **Last Seen**: Time since last successful communication
- **Failure Reason**: Why the device went offline
- **Attempts**: Reconnection attempts (X/5)

### Manual Reconnection
1. **Single Device**: Click "🔄 Reconnect" button for specific device
2. **All Devices**: Click "🔄 Reconnect All" at the top
3. **Auto Toggle**: Enable/disable automatic reconnection per device

### What Happens During Manual Reconnect
- Resets connection attempt counter to 0
- Immediately sends initialization commands
- Restarts automatic retry cycle
- Shows confirmation dialog with status

## Configuration

### Timeout Settings (in `device_status_manager.py`)
```python
OFFLINE_TIMEOUT = 30        # Mark offline after 30s of no data
RECONNECT_INTERVAL = 10     # Retry every 10 seconds
MAX_RECONNECT_ATTEMPTS = 5  # Maximum 5 consecutive retries
```

### Database Storage
Device status persisted in: `device_status.db`
- Connection states survive application restarts
- Historical failure reasons logged
- Last seen timestamps preserved

## Troubleshooting

### Device Shows as Offline But Is Running
1. Check network connectivity (ping device IP)
2. Verify device is sending data (check simulator logs)
3. Check TCP server port matches device configuration
4. Look for firewall blocking connections

### Auto-Reconnect Not Working
1. Verify "Auto" checkbox is enabled in Failed Devices tab
2. Check if max attempts (5/5) reached - use manual reconnect to reset
3. Review application console for error messages
4. Ensure PFDS device exists in database with correct IP

### Manual Reconnect Fails
1. Verify device is powered on and network accessible
2. Check PFDS device configuration (IP, loc_id)
3. Restart the device if necessary
4. Check application logs for detailed error messages

## Status Indicators

### Console Messages
- `✅ Device back online: [name] ([ip])` - Device reconnected
- `⚠️ Device offline: [name] ([ip])` - Device disconnected
- `🔄 Auto-reconnect attempt X/5` - Automatic retry in progress
- `🔄 Manual reconnect: [name] ([ip])` - User-initiated reconnect
- `❌ Giving up on [name] ([ip])` - Max attempts reached

### Status Bar Updates
- Shows device online/offline notifications
- Displays for 5 seconds before returning to normal status

## Testing the System

### Simulate Device Failure
1. Stop the simulator: `pkill -f tcp_sensor_simulator_v2.py`
2. Watch Failed Devices tab - device appears after 30 seconds
3. Auto-reconnect attempts start automatically

### Test Auto-Recovery
1. Stop simulator (as above)
2. Wait for device to appear in Failed Devices tab
3. Restart simulator: `python tcp_sensor_simulator_v2.py --ip 127.0.0.1 --port 9001 --loc_id cam01`
4. Device should automatically reconnect within 10 seconds
5. Device disappears from Failed Devices tab (back online)

### Test Manual Reconnect
1. Device shows in Failed Devices tab
2. Click "🔄 Reconnect" button
3. Check console for command sending messages
4. Verify device starts sending data again

## Architecture

### Components
1. **DeviceStatusManager** (`device_status_manager.py`)
   - Core monitoring logic
   - Background health check thread
   - Database persistence

2. **FailedDevicesTab** (`failed_devices_tab.py`)
   - User interface for device monitoring
   - Manual reconnect controls
   - Real-time status updates

3. **TCP Server Integration** (`tcp_sensor_server.py`)
   - Disconnect detection
   - Callback notifications

4. **PFDS Manager Integration** (`pfds_manager.py`)
   - Command resending
   - Device registration

### Data Flow
```
Device Sends Data → TCP Server → Update Activity → DeviceStatusManager
                                                      ↓
                                              Device Status: Online
                                                      
No Data for 30s → Monitor Thread → Mark Offline → Failed Devices Tab
                                         ↓
                                  Auto-Reconnect Logic
                                         ↓
                                  Send Commands → Device Responds
                                                       ↓
                                                Device Status: Online
```

## Future Enhancements
- Email/SMS notifications for critical device failures
- Connection quality metrics (packet loss, latency)
- Historical uptime reports
- Device groups for batch operations
- Custom retry intervals per device
- Webhook integration for external monitoring systems

## Support
For issues or questions about device monitoring:
1. Check application console logs for detailed error messages
2. Review `device_status.db` for persistent state information
3. Verify network connectivity and device configuration
4. Check simulator logs for device-side issues
