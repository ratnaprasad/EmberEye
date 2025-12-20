# Log Viewer Quick Guide

## How to Access Log Viewer

1. **Launch EmberEye application**
2. **Click the settings icon** (⚙️) in the top-right corner
3. **Select "Log Viewer..."** from the menu

## Log Viewer Tabs

### 1. App Error Log Tab
- Shows application-level errors from `error_logger`
- Filter by source module
- Search by keyword
- Export/import functionality
- Real-time updates

### 2. TCP Log Viewer Tab ⭐ NEW
- Shows TCP sensor packets in real-time
- Two modes: **Debug** and **Error**
- Location-based filtering
- Auto-refreshes every 2 seconds

## Using TCP Log Viewer

### Step 1: Select Mode
Choose between two modes in the dropdown:
- **Debug**: Shows all raw TCP packets (recommended for monitoring)
- **Error**: Shows only error packets (for troubleshooting)

### Step 2: Select Location
Choose from dropdown:
- **All Locations**: Shows packets from all sources
- **Specific Location**: Shows packets from selected location ID only

Location IDs are populated from:
- Stream configuration (camera locations)
- Active TCP connections
- Received locid packets

### Step 3: View Real-time Logs
The log view automatically updates every 2 seconds with:
- **Timestamp**: When the packet was received (UTC)
- **Location ID**: Source location or IP address
- **Type**: RAW (normal packet) or ERROR (malformed packet)
- **Data**: Full packet contents

## Log File Locations

### On macOS/Linux:
```
EmberEye/logs/tcp_debug.log   # Debug/raw packets
EmberEye/logs/tcp_errors.log  # Error packets
EmberEye/logs/crash.log       # Application crashes
```

### On Windows:
```
EmberEye\logs\tcp_debug.log   # Debug/raw packets
EmberEye\logs\tcp_errors.log  # Error packets
EmberEye\logs\crash.log       # Application crashes
```

## Understanding TCP Log Format

### Debug Log Entry Format:
```
TIMESTAMP       LOCATION_ID     RAW     PACKET_DATA
```

### Example Entries:
```
2025-11-29T17:58:35.454341Z     127.0.0.1       RAW     #locid:room_0!
2025-11-29T17:58:35.471371Z     room_0          RAW     map 127.0.0.1->room_0
2025-11-29T17:58:35.507531Z     127.0.0.1       RAW     #Sensor:ADC1=500,ADC2=800,ADC3=900!
```

**Reading the log**:
1. **First line**: Client sends location ID packet from IP 127.0.0.1
2. **Second line**: System maps IP → location (room_0)
3. **Third line**: Client sends sensor data (ADC values)

### Error Log Entry Format:
```
TIMESTAMP       LOCATION_ID     ERROR   REASON          RAW_DATA
```

### Example Error:
```
2025-11-29T18:00:01.123456Z     192.168.1.100   ERROR   frame count 500 expected 768     #frame:FFCC...
```

**Reading the error**:
- Client at 192.168.1.100 sent malformed frame packet
- Expected 768 values, received only 500
- Raw packet data shown for debugging

## Common Packet Types

### 1. Location ID Packet
```
#locid:room_name!
```
**Purpose**: Identifies the location sending data  
**Log shows**: IP-to-location mapping

### 2. Sensor Data Packet
```
#Sensor:ADC1=592,ADC2=894,ADC3=905!
```
**Purpose**: Gas sensor readings  
**ADC1**: CO2 sensor analog value  
**ADC2**: Smoke sensor analog value  
**ADC3**: Additional sensor (optional)

### 3. Thermal Frame Packet
```
#frame:FFCCFFC7...!
```
**Purpose**: 32x24 thermal camera frame  
**Format**: 3072 hex characters (768 pixels × 4 chars each)  
**Log shows**: Full frame data (truncated in error logs)

### 4. Serial Number Packet
```
#serialno:123456!
```
**Purpose**: Device serial number  
**Log shows**: Serial registration

## Troubleshooting

### Problem: No logs showing
**Possible causes**:
1. TCP server not started
2. No clients connected
3. No packets sent yet

**Solutions**:
- Check application console for "TCP Sensor Server started on 0.0.0.0:9001"
- Send test packet from TCP client
- Verify firewall allows port 9001

**Test command** (from terminal):
```bash
echo "#locid:test!" | nc localhost 9001
```

### Problem: "Log file not found"
**Cause**: No packets received yet, log file not created

**Solution**: 
1. Send at least one packet to create log file
2. Check that TCP server is listening on correct port
3. Verify client connecting to correct IP:port

### Problem: Location filter shows nothing
**Cause**: Location ID mismatch or whitespace

**Solutions**:
1. Select "All Locations" first to see all packets
2. Note the exact location ID from the log (second column)
3. Select that location from dropdown
4. Check for extra spaces or typos

### Problem: Logs stop updating
**Cause**: Timer stopped or file permission issue

**Solutions**:
1. Close and reopen Log Viewer
2. Check file permissions on logs/ directory
3. Restart application

## Advanced Usage

### View logs from command line:
```bash
# Tail debug log (live monitoring)
tail -f logs/tcp_debug.log

# View last 50 lines
tail -50 logs/tcp_debug.log

# Search for specific location
grep "room_5" logs/tcp_debug.log

# Count packets by location
cut -f2 logs/tcp_debug.log | sort | uniq -c

# View only sensor packets
grep "#Sensor" logs/tcp_debug.log
```

### Filter by time range:
```bash
# Packets from specific date
grep "2025-11-29" logs/tcp_debug.log

# Packets from specific hour
grep "2025-11-29T17:" logs/tcp_debug.log

# Last 5 minutes (approximate)
tail -100 logs/tcp_debug.log | grep "$(date -u +%Y-%m-%dT%H:)"
```

### Check for errors:
```bash
# All errors
cat logs/tcp_errors.log

# Error count by type
cut -f4 logs/tcp_errors.log | sort | uniq -c

# Errors from specific location
grep "room_5" logs/tcp_errors.log
```

## Log Rotation

Logs automatically rotate when reaching 5 MB:
- `tcp_debug.log` → Current log
- `tcp_debug.log.1` → Previous rotation
- `tcp_debug.log.2` → Second previous
- `tcp_debug.log.3` → Third previous (oldest)

Older logs (`.4` and beyond) are automatically deleted.

## Performance Tips

1. **Use location filtering** when monitoring specific sensors
2. **Switch to Error mode** when troubleshooting issues
3. **Clear old logs** if disk space is limited:
   ```bash
   rm logs/tcp_*.log.*
   ```
4. **Export logs** for analysis before clearing:
   ```bash
   cp logs/tcp_debug.log analysis_$(date +%Y%m%d).log
   ```

## Quick Reference: Menu Path
```
Application Window
  └─ Settings Icon (⚙️)
      └─ Log Viewer...
          ├─ App Error Log (application errors)
          └─ TCP Log Viewer (sensor packets) ⭐
              ├─ Mode: [Debug ▼]
              ├─ Location: [All Locations ▼]
              └─ [Auto-updating text view]
```

## Need Help?

### Check these files for more info:
- `TCP_LOGGING_FIX_SUMMARY.md` - Detailed technical documentation
- `WINDOWS_CRASH_TROUBLESHOOTING.md` - Windows-specific issues
- `TEST_COVERAGE_SUMMARY.md` - Testing information

### Common Questions:

**Q: How often does the log viewer update?**  
A: Every 2 seconds automatically

**Q: How many log lines are shown?**  
A: Last 1000 lines (most recent)

**Q: Can I export logs from the viewer?**  
A: Currently no, use command line: `cp logs/tcp_debug.log exported.log`

**Q: What timezone are timestamps in?**  
A: UTC (Coordinated Universal Time)

**Q: Can I see historical logs?**  
A: Yes, rotated logs are in `tcp_debug.log.1`, `.2`, `.3`

**Q: How do I clear logs?**  
A: Delete files in `logs/` directory or restart with `rm logs/tcp_*.log`

**Q: Why is my location not in the dropdown?**  
A: Location IDs come from stream config. Add it there or send a `#locid:` packet first.

## Success Checklist

✅ Can open Log Viewer from settings menu  
✅ TCP Log Viewer tab is visible  
✅ Mode dropdown shows "Debug" and "Error"  
✅ Location dropdown shows "All Locations" + location IDs  
✅ Log view shows packet data  
✅ View updates every 2 seconds  
✅ Can filter by location  
✅ Can switch between Debug and Error modes  

If all checkboxes pass: **Log Viewer is working correctly!** 🎉
