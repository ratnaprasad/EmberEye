# EEPROM Protocol Implementation

## Overview
Implemented new thermal frame EEPROM protocol based on datasheet requirements. The system now requests calibration data once per connection using the `EEPROM1` command and caches it for the entire session.

## Protocol Flow

### 1. Connection Establishment
```
Client connects → Server sends "EEPROM1" command → Device responds with #EEPROM1234:<3336_chars>!\r\n
```

### 2. Fallback on First Frame
If EEPROM request is missed during connection:
```
First #frame received → Auto-send "EEPROM1" → Device responds with EEPROM data
```

### 3. Normal Frame Processing
After EEPROM loaded:
```
#frame1234:<3336_chars>! → Parse grid (768 blocks) + partial EEPROM (66 blocks)
```

## Implementation Details

### A. Thermal Frame Parser (`thermal_frame_parser.py`)

#### New State Variables
```python
_eeprom_cache = None          # Cached 834-block EEPROM data
_eeprom_loaded = False        # Session-based EEPROM state
_eeprom_request_sent = False  # Track if EEPROM1 sent
```

#### New Methods

**`parse_eeprom_packet(packet: str) -> dict`**
- Parses `#EEPROM1234:<3336_chars>!\r\n` format
- Validates 3336 chars (834 blocks × 4 chars)
- Caches EEPROM data for session
- Applies calibration from EEPROM
- Returns success status with frame_id and block count

**`needs_eeprom_request() -> bool`**
- Returns `True` if EEPROM not loaded and not yet requested
- Used by TCP server to determine if EEPROM1 should be sent

**`mark_eeprom_requested()`**
- Marks EEPROM1 command as sent
- Prevents duplicate requests

**`reset_eeprom_state()`**
- Resets EEPROM state on new connection
- Keeps cached data for temporary disconnects
- Called by TCP server on client connect

**`_apply_full_eeprom_calibration(eeprom_hex: str)`**
- Replaces old `_maybe_apply_eeprom()` logic
- Uses full 834-block EEPROM data
- Extracts offset from first word (block 0)
- Formula: `temperature = raw_value - offset`
- Sanity bounds: offset range -100.0 to 100.0°C

#### Updated Calibration Formula
**Old protocol:**
```python
temperature = raw_value * scale + offset
```

**New protocol:**
```python
temperature = raw_value - offset
```

### B. TCP Async Server (`tcp_async_server.py`)

#### New State Variables
```python
_client_eeprom_sent: Dict[str, bool] = {}  # Track EEPROM1 sent per client IP
```

#### Connection Handler Updates

**On Client Connect:**
```python
1. Reset EEPROM state: ThermalFrameParser.reset_eeprom_state()
2. Send EEPROM1 command: writer.write(b"EEPROM1")
3. Mark client: self._client_eeprom_sent[client_ip] = True
```

**On First Frame Received:**
```python
if not first_frame_received and raw.startswith('#frame'):
    if needs_eeprom_request():
        writer.write(b"EEPROM1")
        mark_eeprom_requested()
```

**On Client Disconnect:**
```python
Clean up: del self._client_eeprom_sent[client_ip]
```

#### Packet Parsing Updates

**New EEPROM Packet Type:**
```python
elif line.startswith('#EEPROM'):
    eeprom_result = ThermalFrameParser.parse_eeprom_packet(line)
    if eeprom_result.get('success'):
        result = {
            'type': 'eeprom',
            'frame_id': eeprom_result.get('frame_id'),
            'blocks': eeprom_result.get('blocks'),
            'client_ip': client_ip
        }
```

### C. Main Window (`main_window.py`)

#### Packet Handler Updates

**New EEPROM Handler:**
```python
if packet.get('type') == 'eeprom':
    print(f"✅ EEPROM calibration loaded for loc_id: {loc_id or packet.get('client_ip')}")
    print(f"   Frame ID: {packet.get('frame_id')}, Blocks: {packet.get('blocks')}")
    return
```

## Protocol Specifications

### Frame Format
**EEPROM Response:**
```
Format: #EEPROM1234:<3336_chars>!\r\n
- Frame ID: 1234 (sequential)
- Data: 834 blocks × 4 chars = 3336 chars total
- Terminator: !\r\n
```

**Thermal Frame (unchanged):**
```
Format: #frame1234:<3336_chars>!
- Frame ID: 1234 (location ID)
- Grid: 768 blocks (24×32) = 3072 chars
- EEPROM: 66 blocks = 264 chars
- Terminator: !
```

### EEPROM Data Structure

**Block 0 (chars 0-3):** Offset calibration
- 16-bit signed value (two's complement)
- Unit: centi-degrees (0x0064 = 100 = 1.00°C)
- Example: 0xFF9C = -100 = -1.00°C

**Blocks 1-833 (chars 4-3335):** Reserved
- Additional calibration parameters (currently unused)
- Available for future extensions

### Calibration Formula

**Temperature Conversion:**
```python
raw_value = int(hex_word, 16)  # 16-bit value from frame
if raw_value > 0x7FFF:
    raw_value -= 0x10000  # Two's complement for signed
temperature = raw_value - offset  # Apply offset calibration
```

## Error Handling

### EEPROM Request Failure
- No timeout enforcement (per requirements)
- Falls back to old protocol (partial EEPROM per frame)
- No error display to user
- No automatic retry

### EEPROM Parse Failure
- Logs error with reason
- Continues using default calibration
- Does not disable thermal processing

### Connection Loss
- EEPROM state reset on reconnection
- Cached data preserved for quick recovery
- New EEPROM1 request sent on new connection

## Session Management

### EEPROM Cache Duration
- **Cached for entire session:** ✅
- **Re-request on reconnection:** ✅ (one time per connection)
- **Expire after time period:** ❌ (no expiration)

### State Tracking
```python
Connection Open → EEPROM1 sent → EEPROM loaded → Use cached data
                     ↓
Connection Close → State reset → Connection Open → New EEPROM1
```

## Backward Compatibility

### Protocol Support
- **New protocol:** Primary implementation (EEPROM1 command)
- **Old protocol:** Fallback support (partial EEPROM per frame)
- **Detection:** Automatic based on EEPROM1 response

### Transition
```python
if EEPROM1 response received:
    Use new protocol (cached EEPROM)
else:
    Use old protocol (66 blocks per frame)
```

## Testing Recommendations

1. **Connection Test:**
   - Verify EEPROM1 command sent on connect
   - Confirm EEPROM response parsing
   - Check calibration applied

2. **Frame Processing:**
   - Verify temperature calculations use offset
   - Confirm frame format unchanged (3336 chars)
   - Check thermal overlay displays correctly

3. **Reconnection:**
   - Verify EEPROM state reset
   - Confirm new EEPROM1 request
   - Check calibration re-applied

4. **Fallback:**
   - Test with device not supporting EEPROM1
   - Verify old protocol still works
   - Confirm no errors or crashes

## Configuration

No configuration changes required. Protocol automatically adapts based on device response.

## Logging

**EEPROM Events:**
```
✅ Sent EEPROM1 command to 192.168.1.100
✅ EEPROM calibration loaded: 3336 chars (834 blocks)
   Calibration offset: -1.00°C
   Applied EEPROM offset: -1.00°C
✅ EEPROM calibration loaded from 192.168.1.100
🔄 EEPROM state reset for new connection
```

**Error Logging:**
```
⚠️ Failed to send EEPROM1 to 192.168.1.100: Connection refused
⚠️ EEPROM offset out of range: 150.00°C, using default
⚠️ EEPROM calibration parse error: invalid hex
```

## Files Modified

1. **`thermal_frame_parser.py`**
   - Added EEPROM cache and state management
   - Implemented `parse_eeprom_packet()`
   - Updated calibration formula
   - Added session management methods

2. **`tcp_async_server.py`**
   - Added EEPROM1 command sender on connect
   - Implemented auto-request on first frame
   - Added EEPROM packet parsing
   - Added client state tracking

3. **`main_window.py`**
   - Added EEPROM packet handler
   - Added logging for EEPROM events

## Performance Impact

- **Minimal:** EEPROM requested once per connection
- **Cache hit:** Zero overhead after initial load
- **Frame processing:** No change in frame parsing speed
- **Memory:** ~3KB per cached EEPROM (negligible)

## Future Enhancements

1. **Extended Calibration:** Use blocks 1-833 for advanced calibration
2. **Persistence:** Save EEPROM cache to disk for offline use
3. **Multi-device:** Support different EEPROM per location ID
4. **Validation:** Add CRC/checksum for EEPROM integrity
5. **UI Indicator:** Show EEPROM calibration status in UI
