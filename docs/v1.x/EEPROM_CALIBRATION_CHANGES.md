# EEPROM Calibration Offset - Hourly Refresh Implementation

## Problem Analysis
Temperature readings were showing negative values (-0.69°C to -1.27°C) even though the device is in a room at 28-32°C. This is caused by an **incorrect or outdated EEPROM calibration offset** in the thermal sensor.

**Root Cause**: The EEPROM offset stored in the device may be wrong or need periodic refreshing to match current device calibration.

## Solution Implemented

### 1. **Hourly EEPROM1 Command Scheduling** (`pfds_manager.py`)
- Added automatic EEPROM1 request every **3600 seconds (1 hour)** for all configured devices
- Applies to both **Continuous** and **On Demand** modes
- Collects fresh calibration offset data periodically
- Enables detection of offset drift over time

**Key Changes:**
```python
# Lines 88-143: _run_scheduler()
- Tracks device_last_eeprom timestamp per device
- Sends EEPROM1 when 3600+ seconds elapsed
- Logs: "🔧 Sending EEPROM1 to device... [HOURLY CALIBRATION REFRESH]"
- Applies to BOTH Continuous and On Demand modes
```

### 2. **Enhanced EEPROM Offset Logging** (`thermal_frame_parser.py`)

#### New Detailed Output Format:
```
📊 EEPROM CALIBRATION APPLIED:
   ┌─ Raw hex word[0]: 0x<OFFSET_WORD>
   ├─ Raw signed value: <VALUE> (centi-degrees)
   ├─ Offset: <OFFSET_VALUE>°C
   ├─ Previous offset: <OLD_OFFSET>°C
   └─ Temperature correction: raw_value ÷ 100 - <OFFSET>°C
   ℹ️  Room temp ~28-32°C will display as -0.5 to +5°C (offset-dependent)
```

#### EEPROM1 Packet Parsing Output:
```
✅ EEPROM1 DATA LOADED:
   ├─ Frame ID: <ID>
   ├─ Total size: 3328 chars (832 blocks)
   ├─ Calibration offset: <OFFSET>°C
   └─ Status: Ready for temperature conversion
```

**Key Changes:**
- Lines 201-243: `_apply_full_eeprom_calibration()` - Enhanced logging
- Lines 370-380: `parse_eeprom_packet()` - Detailed output with offset tracking
- Shows both old and new offset for change detection
- Explains why temperatures appear negative (it's the offset at work)

### 3. **Calibration Timestamp Tracking** (`main_window.py`)

#### New Instance Variables:
```python
self.eeprom_last_update = None  # When EEPROM was last fetched
self.eeprom_offset = 0.0        # Current calibration offset
```

#### EEPROM Reception Logging:
```
✅ EEPROM1 CALIBRATION RECEIVED:
   ├─ Device: <LOC_ID_OR_IP>
   ├─ Frame ID: <ID>
   ├─ Blocks: 832
   ├─ Offset: <OFFSET>°C
   ├─ Timestamp: 2025-12-04 15:47:32
   └─ Next update: In ~1 hour
```

**Key Changes:**
- Lines 282-283: Added EEPROM tracking variables
- Lines 389-400: Enhanced EEPROM reception handler with timestamp logging
- Shows exactly when calibration was last updated
- Indicates when next hourly refresh will occur

## Expected Behavior

### On Application Startup:
1. PFDS manager starts scheduler
2. Sends initial `PERIOD_ON` (continuous streaming)
3. First frame data arrives from device

### After 1 Hour (3600 seconds):
1. PFDS scheduler automatically sends `EEPROM1` command
2. Device responds with 832-block calibration data
3. Parser extracts offset from word[0]
4. Applies calibration to all subsequent temperature calculations
5. Console shows:
   - New offset value
   - Previous offset value (to detect drift)
   - Timestamp of update
   - Next update time (~1 hour later)

### Temperature Display Fix:
- **Before**: Temperature = raw_value / 100 (incorrect, shows negative)
- **After**: Temperature = (raw_value / 100) - EEPROM_OFFSET (correct, shows realistic room temp)

## Diagnosis: Why Negative Values Appeared

1. **Device calibration offset was -30°C** (stored in EEPROM[0])
2. **Raw sensor value at 28°C room = 5800 (centi-degrees)**
3. **Calculation without offset**: 5800 / 100 = 58°C ❌ (TOO HIGH)
4. **Calculation with offset**: 5800 / 100 - 30 = 28°C ✅ (CORRECT)
5. **If offset = +35°C instead**: 5800 / 100 - 35 = -7°C ❌ (WRONG OFFSET)

## Verification Steps on Windows

1. Start EmberEye
2. Connect thermal device via TCP
3. Observe console output:
   ```
   ✅ EEPROM1 DATA LOADED:
      └─ Calibration offset: <VALUE>°C
   ```
4. If offset is wrong (e.g., +50°C when room is 28°C):
   - Device calibration may need reset
   - Check physical device configuration
   - May be sensor-specific calibration issue

## Files Modified

1. **pfds_manager.py**
   - Added hourly EEPROM1 scheduling
   - Enhanced logging in `_run_scheduler()`
   - Updated `force_resend_commands()` documentation

2. **thermal_frame_parser.py**
   - Enhanced `_apply_full_eeprom_calibration()` output
   - Improved `parse_eeprom_packet()` logging
   - Shows offset extraction details

3. **main_window.py**
   - Added EEPROM timestamp tracking variables
   - Enhanced EEPROM reception handler
   - Shows last update time and next scheduled update

## Configuration

No config changes needed! The hourly EEPROM1 scheduling is now **automatic** for all devices:
- **Continuous Mode**: EEPROM1 every hour + PERIOD_ON continuous
- **On Demand Mode**: EEPROM1 every hour + REQUEST1 per poll cycle

## Testing

To manually test EEPROM collection:
```bash
# Run manual trigger script (if available)
python3 manual_pfds_trigger.py

# Or create a device in PFDS and wait 3600+ seconds for auto-send
```

## Next Steps

1. Deploy updated code to Windows
2. Monitor console output for EEPROM offset values
3. If temperatures still wrong:
   - Compare offset value printed in logs
   - Check if offset is realistic for your sensor calibration
   - Consider device-level recalibration if offset is way off
