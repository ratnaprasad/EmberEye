# EEPROM Protocol Quick Reference

## Command & Response Format

### EEPROM Request
```
Command: EEPROM1
Sent when: On TCP connection + Auto on first frame (if missed)
Terminator: None
```

### EEPROM Response
```
Format: #EEPROM1234:<DATA>!\r\n
- Frame ID: 1234
- DATA: 3336 chars (834 blocks × 4 chars/block)
- Terminator: !\r\n
```

### Thermal Frame (unchanged)
```
Format: #frame1234:<DATA>!
- Frame ID: 1234 (location ID)
- DATA: 3336 chars (768 grid + 66 EEPROM)
- Terminator: !
```

## Calibration Data

### EEPROM Block 0 (Offset)
```
Chars: 0-3
Format: 16-bit signed hex (two's complement)
Unit: Centi-degrees (0x0064 = 1.00°C)
Example: 0xFF9C = -100 centi = -1.00°C
Range: -100.0°C to +100.0°C
```

### Temperature Calculation
```python
# Parse hex to int
raw_value = int(hex_word_4chars, 16)

# Handle signed values
if raw_value > 0x7FFF:
    raw_value -= 0x10000

# Apply calibration
temperature = raw_value - offset
```

## Session Flow

```
┌─────────────────────────────────────────────────┐
│ 1. Client Connects                              │
│    └─> Send "EEPROM1"                           │
│    └─> Mark EEPROM requested                    │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ 2. Device Responds                              │
│    └─> #EEPROM1234:<3336_chars>!\r\n            │
│    └─> Parse & cache EEPROM                     │
│    └─> Apply offset calibration                 │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ 3. Normal Frame Processing                      │
│    └─> #frame1234:<3336_chars>!                 │
│    └─> Use cached EEPROM offset                 │
│    └─> Calculate temperatures                   │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ 4. Connection Closes                            │
│    └─> Reset EEPROM state                       │
│    └─> Keep cache for quick reconnect           │
└─────────────────────────────────────────────────┘
```

## Fallback Behavior

### If EEPROM1 Missed on Connect
```
First #frame arrives
└─> Check: EEPROM loaded?
    └─> NO: Auto-send "EEPROM1"
    └─> YES: Continue normal processing
```

### If EEPROM1 Not Supported
```
No EEPROM response received
└─> Use old protocol (66 EEPROM blocks per frame)
└─> Extract offset from frame EEPROM section
└─> Continue processing normally
```

## Code Examples

### Check EEPROM State
```python
from thermal_frame_parser import ThermalFrameParser

# Check if EEPROM request needed
if ThermalFrameParser.needs_eeprom_request():
    # Send EEPROM1 command
    writer.write(b"EEPROM1")
    ThermalFrameParser.mark_eeprom_requested()
```

### Parse EEPROM Packet
```python
packet = "#EEPROM1234:<3336_chars>!\r\n"
result = ThermalFrameParser.parse_eeprom_packet(packet)

if result['success']:
    print(f"EEPROM loaded: {result['blocks']} blocks")
    print(f"Frame ID: {result['frame_id']}")
else:
    print(f"Error: {result['error']}")
```

### Reset on Reconnect
```python
# On new connection
ThermalFrameParser.reset_eeprom_state()
print("🔄 EEPROM state reset for new connection")
```

## Error Messages

### Success Messages
```
✅ Sent EEPROM1 command to 192.168.1.100
✅ EEPROM calibration loaded: 3336 chars (834 blocks)
   Calibration offset: -1.00°C
   Applied EEPROM offset: -1.00°C
✅ EEPROM calibration loaded from 192.168.1.100
🔄 EEPROM state reset for new connection
```

### Warning Messages
```
⚠️ Failed to send EEPROM1 to 192.168.1.100: <reason>
⚠️ Auto EEPROM1 request failed: <reason>
⚠️ EEPROM offset out of range: <value>°C, using default
⚠️ EEPROM calibration parse error: <error>
```

### Error Logs
```
EEPROM parse error: Invalid EEPROM packet: must start with #EEPROM
EEPROM parse error: Invalid EEPROM packet: missing colon separator
EEPROM parse error: Invalid EEPROM data size: 3000 chars, expected 3336
EEPROM parse error: EEPROM parse exception: <exception>
```

## Testing Checklist

- [ ] EEPROM1 sent on connection establishment
- [ ] EEPROM response parsed correctly
- [ ] Calibration offset applied to temperatures
- [ ] Auto-request on first frame (if missed)
- [ ] State reset on reconnection
- [ ] Cache preserved across temporary disconnects
- [ ] Fallback to old protocol if EEPROM1 not supported
- [ ] No errors or crashes with invalid EEPROM data
- [ ] Temperature calculations correct with offset
- [ ] Thermal overlay displays correct values

## Configuration Requirements

**Answer Key:**
1. ✅ Send EEPROM1 on TCP connection
2. ✅ Command string: "EEPROM1" (no terminator, no parameters)
3. ✅ Response format: #EEPROM1234:<3336_chars>!\r\n
4. ✅ Frame format stays same (3336 chars)
5. ✅ Calibration formula: raw_value - offset
6. ✅ Fallback to old protocol on failure
7. ✅ Cache for entire session
8. ✅ Re-request on reconnection (one time)
9. ✅ New protocol only

## Key Files

- **thermal_frame_parser.py** - EEPROM parsing & calibration
- **tcp_async_server.py** - EEPROM request & packet handling
- **main_window.py** - EEPROM packet routing

## API Methods

### ThermalFrameParser
```python
# Parse EEPROM packet
parse_eeprom_packet(packet: str) -> dict

# Check if EEPROM request needed
needs_eeprom_request() -> bool

# Mark EEPROM request sent
mark_eeprom_requested()

# Reset state on reconnect
reset_eeprom_state()
```

### TCPAsyncSensorServer
```python
# Connection handler sends EEPROM1
async _handle_client(reader, writer)

# Parse EEPROM packets
_parse_packet(line: str, client_ip: str)
```

### MainWindow
```python
# Handle EEPROM packets
handle_tcp_packet(packet: dict)
```
