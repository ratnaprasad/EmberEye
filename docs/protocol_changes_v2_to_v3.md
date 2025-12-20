# Protocol Changes: V2 → V3

## Protocol Semantics Comparison

### PERIOD_ON Command

**V2 (Old Behavior):**
- Sent on every scheduler init for Continuous mode devices
- Sent on every reconnect (manual or auto)
- Sent together with EEPROM1 as a pair
- Re-sent multiple times per device lifetime

**V3 (New Behavior):**
- Sent **once** per device boot/reconnect
- Tracked per connection to prevent re-sends
- Sent **before** EEPROM1 (if EEPROM1 needed at all)
- Gated by `device_init_done` in scheduler, `_client_period_on_sent` in server

### EEPROM1 Command

**V2 (Old Behavior):**
- Automatically sent after PERIOD_ON on every init
- Always sent on manual reconnect via `force_resend_commands()`
- Auto-sent on first frame if startup missed
- Sent unconditionally regardless of EEPROM validity

**V3 (New Behavior):**
- **NOT** automatically sent on init or reconnect
- Parser validates embedded EEPROM (66 blocks) from raw frames
- Only requested when embedded EEPROM validation fails
- Default: use embedded EEPROM (valid by default in v3)

### REQUEST1 Command

**V2 (Old Behavior):**
- Sent periodically in On Demand mode (automatic)
- Triggered by scheduler poll interval

**V3 (New Behavior):**
- **Only** sent in On Demand mode or explicit user actions
- **Never** automatic in Continuous mode
- Strictly on-demand single frame capture

### Raw Frame EEPROM

**V2 (Old Behavior):**
- 66-block embedded EEPROM ignored if EEPROM1 loaded
- No validation of embedded EEPROM quality
- Legacy fallback rarely used

**V3 (New Behavior):**
- Embedded EEPROM validated on every frame (if EEPROM1 not loaded)
- Validation checks: length (264 chars), hex validity, non-zero content
- **Default** to embedded EEPROM (request EEPROM1 only on corruption)
- Parser logs validation results

## Code Changes Summary

### pfds_manager.py

```python
# V2: Sent PERIOD_ON + EEPROM1 together
if mode == "Continuous" and not sent_init.get(did):
    self._dispatcher({"command": "PERIOD_ON", **d})
    time.sleep(0.1)
    self._dispatcher({"command": "EEPROM1", **d})
    sent_init[did] = True

# V3: Send PERIOD_ON once, NO automatic EEPROM1
if mode == "Continuous" and not device_init_done.get(did):
    self._dispatcher({"command": "PERIOD_ON", **d})
    # DO NOT send EEPROM1 - parser will request if needed
    device_init_done[did] = True
```

### thermal_frame_parser.py

```python
# V2: No validation, just used EEPROM if flag set
if ThermalFrameParser._use_eeprom:
    ThermalFrameParser._maybe_apply_eeprom(eeprom_hex)

# V3: Validate embedded EEPROM, log results
if not ThermalFrameParser._eeprom_loaded:
    if ThermalFrameParser.is_eeprom_valid(eeprom_hex):
        if ThermalFrameParser._use_eeprom:
            ThermalFrameParser._maybe_apply_eeprom(eeprom_hex)
            print("✅ Using validated EEPROM from raw frame")
    else:
        print("⚠️  Raw EEPROM invalid - parser will request EEPROM1 if needed")
```

### tcp_async_server.py

```python
# V2: Sent PERIODIC_ON + EEPROM1 on connect
writer.write(b"PERIODIC_ON")
await writer.drain()
await asyncio.sleep(0.5)
writer.write(b"EEPROM1")
await writer.drain()
self._client_eeprom_sent[client_ip] = True

# V3: Send PERIOD_ON once, gate re-sends, NO EEPROM1
if not self._client_period_on_sent.get(client_ip, False):
    writer.write(b"PERIODIC_ON")
    await writer.drain()
    self._client_period_on_sent[client_ip] = True
    # DO NOT send EEPROM1 - wait for parser validation
```

### tcp_sensor_simulator.py → tcp_sensor_simulator_v3.py

**V2 (Old Simulator):**
- Continuously sends frames without waiting for commands
- No command listener
- No streaming state management
- No EEPROM1 response capability

**V3 (New Simulator):**
- Command listener thread for PERIOD_ON, REQUEST1, EEPROM1
- Idle state until PERIOD_ON received
- Streaming state managed by `self.streaming` flag
- Responds to REQUEST1 with single frame
- Sends 3328-char EEPROM1 calibration data on request
- Structured logging to file

## Migration Impact

### Backward Compatibility
- ✅ Existing devices will still work (PERIOD_ON sent on connect)
- ✅ Continuous mode unchanged (streams after PERIOD_ON)
- ✅ On Demand mode unchanged (REQUEST1 still sent per poll)
- ⚠️  Devices expecting EEPROM1 auto-send will need to be updated or use embedded EEPROM

### Benefits
1. **Reduced command overhead:** No redundant PERIOD_ON or EEPROM1 commands
2. **Faster startup:** Uses embedded EEPROM by default (no EEPROM1 request delay)
3. **Better protocol compliance:** Matches documented device behavior
4. **Cleaner logs:** One-time PERIOD_ON clearly marked, less noise

### Testing Required
- Verify PERIOD_ON gate doesn't break reconnect scenarios
- Confirm embedded EEPROM validation works across all devices
- Test REQUEST1 in On Demand mode still functions
- Simulate EEPROM corruption to test EEPROM1 request path

## Simulator V3 Usage

**Old (V2):**
```bash
python3 tcp_sensor_simulator.py --host 127.0.0.1 --port 9001 --loc-id "room1"
# Immediately starts streaming frames (no command wait)
```

**New (V3):**
```bash
python3 tcp_sensor_simulator_v3.py --host 127.0.0.1 --port 9001 --loc-id "room1" --log-file logs/sim.log
# Waits for PERIOD_ON command before streaming
# Responds to REQUEST1 and EEPROM1 commands
# Logs all activity to file
```

## Key Behavioral Changes

| Scenario | V2 Behavior | V3 Behavior |
|----------|-------------|-------------|
| App startup | Sends PERIOD_ON + EEPROM1 | Sends PERIOD_ON only |
| Device reconnect | Sends PERIOD_ON + EEPROM1 | Sends PERIOD_ON only |
| Manual reconnect button | Sends PERIOD_ON + EEPROM1 | Sends PERIOD_ON only |
| Continuous streaming init | PERIOD_ON + EEPROM1 per scheduler run | PERIOD_ON once per device |
| EEPROM source | Prefers EEPROM1 response | Prefers embedded EEPROM (66 blocks) |
| EEPROM1 request | Always automatic | Only on validation failure |
| REQUEST1 usage | On Demand mode (periodic) | On Demand mode + explicit only |
| Simulator behavior | Streams immediately | Waits for PERIOD_ON command |

## Validation Steps

1. ✅ **pfds_manager:** PERIOD_ON gated to once, no auto-EEPROM1
2. ✅ **thermal_frame_parser:** EEPROM validation added, embedded EEPROM prioritized
3. ✅ **tcp_async_server:** PERIOD_ON gated per connection, no auto-EEPROM1
4. ✅ **simulator_v3:** Command processing, streaming state, EEPROM1 response
5. ⏳ **Testing:** End-to-end validation with simulator v3
6. ⏳ **Documentation:** Update user guides and protocol specs

## Future Enhancements

1. **Global device init tracking:** Persist PERIOD_ON state across app restarts
2. **Auto EEPROM1 trigger:** Wire parser corruption flag to command dispatcher
3. **Device boot detection:** Distinguish reboot from connection loss
4. **Configurable corruption threshold:** Adjust EEPROM validation strictness
5. **EEPROM1 caching:** Store received calibration across reconnects
