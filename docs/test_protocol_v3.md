# Protocol V3 Testing Guide

## Changes Made

### 1. PFDS Manager (`pfds_manager.py`)
- ✅ PERIOD_ON now sent **once per device** (tracked by `device_init_done` dict)
- ✅ Removed automatic EEPROM1 sending on init
- ✅ `force_resend_commands()` no longer sends EEPROM1 automatically
- ✅ REQUEST1 remains in On Demand mode only

### 2. Thermal Frame Parser (`thermal_frame_parser.py`)
- ✅ Added `is_eeprom_valid()` static method to validate embedded EEPROM:
  - Checks length (264 chars for 66 blocks)
  - Validates hex characters
  - Ensures at least 10% non-zero blocks
- ✅ `parse_frame()` now validates embedded EEPROM before use
- ✅ Prints warning if EEPROM invalid (triggers EEPROM1 request path)

### 3. TCP Async Server (`tcp_async_server.py`)
- ✅ Replaced `_client_eeprom_sent` with `_client_period_on_sent`
- ✅ PERIOD_ON sent **once per client connection** (gated)
- ✅ Removed automatic EEPROM1 sending on connect
- ✅ Removed auto-send EEPROM1 on first frame
- ✅ Failsafe PERIOD_ON auto-send if initial send missed

### 4. Simulator V3 (`tcp_sensor_simulator_v3.py`)
- ✅ Command listener thread for incoming commands
- ✅ PERIOD_ON/PERIODIC_ON: Starts continuous streaming
- ✅ REQUEST1: Sends single frame (on-demand)
- ✅ EEPROM1: Responds with 3328-char calibration data
- ✅ Streaming state management (idle until PERIOD_ON)
- ✅ Valid EEPROM embedded in frames (non-zero values)
- ✅ Structured logging to `logs/simulator_v3.log`

## Testing Protocol V3

### Test 1: Start Simulator V3
```bash
cd /Users/ratnaprasadkakani/development/laby/pythonworkspace/EmberEye
python3 tcp_sensor_simulator_v3.py --host 127.0.0.1 --port 9001 --loc-id "test room" --interval 2.0
```

**Expected Behavior:**
- Simulator connects to server
- Sends `#serialno:` and `#locid:` packets
- Waits idle (log: "⏳ Waiting for PERIOD_ON command to start streaming...")
- Does NOT send frames until PERIOD_ON received

### Test 2: App Startup (First Connection)
1. Start EmberEye app
2. Wait for TCP server to accept simulator connection

**Expected Behavior:**
- TCP async server sends **PERIOD_ON once** on connection
- Simulator receives PERIOD_ON and starts streaming
- Frames arrive with embedded EEPROM (66 blocks, 264 chars)
- Parser validates embedded EEPROM (should pass - non-zero values)
- Parser uses embedded EEPROM (log: "✅ Using validated EEPROM from raw frame")
- **NO EEPROM1 request sent** (because validation passed)

### Test 3: Device Reconnect
1. Stop simulator (Ctrl+C)
2. Restart simulator
3. Wait for reconnection

**Expected Behavior:**
- Connection detected as new
- PERIOD_ON sent again (per-connection gate, not global)
- Parser resets EEPROM state on reconnect
- Embedded EEPROM validation re-runs
- Still no EEPROM1 request (validation passes)

### Test 4: Manual "Reconnect All" Button
1. With simulator running and streaming
2. Click "Reconnect All" button in Failed Devices tab

**Expected Behavior:**
- `pfds_manager.force_resend_commands()` called
- PERIOD_ON sent (Continuous mode)
- **NO EEPROM1 sent** automatically
- Streaming continues with validated embedded EEPROM
- UI does NOT hang (async threading)

### Test 5: On-Demand Mode (REQUEST1)
1. Change device mode to "On Demand" in PFDS settings
2. Observe scheduler behavior

**Expected Behavior:**
- Scheduler sends **REQUEST1** (not PERIOD_ON) per poll interval
- Simulator receives REQUEST1 and sends single frame
- No continuous streaming
- Each REQUEST1 triggers one frame

### Test 6: EEPROM1 Request (Corruption Path)
**Note:** Current implementation doesn't auto-trigger EEPROM1 on corruption.
To fully test, you would need to:
1. Modify simulator to send corrupted EEPROM (all zeros or wrong length)
2. Parser detects corruption (log: "⚠️ Raw EEPROM invalid...")
3. Parser sets internal flag to request EEPROM1
4. App/server sends EEPROM1 command
5. Simulator responds with 3328-char calibration data

**Future Enhancement:** Wire parser corruption flag to auto-send EEPROM1 command.

## Verification Checklist

- [ ] Simulator v3 starts and waits for PERIOD_ON (idle state)
- [ ] PERIOD_ON sent once on connection (check logs: "Sent PERIOD_ON command to {ip} [ONE-TIME]")
- [ ] Frames stream continuously after PERIOD_ON
- [ ] Embedded EEPROM validates successfully (check: "✅ Using validated EEPROM from raw frame")
- [ ] No EEPROM1 command sent automatically
- [ ] REQUEST1 works in On Demand mode
- [ ] Manual reconnect sends PERIOD_ON but NOT EEPROM1
- [ ] UI remains responsive during bulk reconnects
- [ ] Simulator logs show command reception and responses

## Log Files to Monitor

1. **Simulator:** `logs/simulator_v3.log` (detailed command processing)
2. **TCP Server:** Check console for PERIOD_ON send confirmations
3. **Parser:** Check console for EEPROM validation messages
4. **PFDS Manager:** Check console for "Sent PERIOD_ON [ONE-TIME INIT]"

## Protocol Compliance Summary

| Command | When Sent | Who Sends | Expected Response |
|---------|-----------|-----------|-------------------|
| PERIOD_ON | Once per device boot/reconnect | App → Device | Start continuous streaming |
| REQUEST1 | On-demand capture only | App → Device | Send single frame |
| EEPROM1 | Only when embedded EEPROM corrupted | App → Device | Send 3328-char calibration |

**Default Flow:**
1. Device boots → App sends PERIOD_ON (once)
2. Device streams frames with valid embedded EEPROM
3. App validates embedded EEPROM → uses it (no EEPROM1 request)
4. Continuous streaming with no additional commands

**Corruption Flow:**
1. Device boots → App sends PERIOD_ON (once)
2. Device streams frames with **corrupted** embedded EEPROM
3. App detects corruption → sends EEPROM1 command
4. Device responds with full calibration data
5. App uses EEPROM1 calibration instead of embedded

## Known Limitations

1. **No automatic EEPROM1 trigger:** Parser detects corruption but doesn't auto-send EEPROM1 command yet. Requires wiring parser flag to command dispatcher.

2. **Per-connection PERIOD_ON gate:** Currently gates PERIOD_ON per connection (not global per device). Device reboot detection would require persistence layer.

3. **No device boot detection:** System can't distinguish device reboot from connection loss. Both trigger reconnect flow.

## Next Steps

If testing reveals issues:
1. Check simulator log for command reception
2. Verify PERIOD_ON gate logic in tcp_async_server
3. Confirm embedded EEPROM validation passes
4. Add debug logs to trace EEPROM1 request path

To add corruption testing:
1. Add `--corrupt-eeprom` flag to simulator v3
2. Generate all-zero or wrong-length EEPROM blocks
3. Verify parser detects corruption
4. Wire parser flag to auto-send EEPROM1 command
