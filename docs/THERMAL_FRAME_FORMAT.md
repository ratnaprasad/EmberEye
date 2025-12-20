# Thermal Camera Frame Processing

## Overview
The thermal camera sends frames in a specific format with 834 word blocks (3336 characters total):
- **Grid data**: 24 rows × 32 cols = 768 word blocks = 3072 chars
- **EEPROM config**: 66 word blocks = 264 chars

## Frame Format

### Packet Structure
```
#frame1234:<3336_HEX_CHARS>!
```

Where:
- `1234` = frame ID (incremental counter)
- `<3336_HEX_CHARS>` = raw thermal data (no spaces)
  - First 3072 chars: Grid data (FFCBFFC6FFCB...)
  - Last 264 chars: EEPROM configuration data

### Example
```
#frame1:FFCBFFC6FFCBFFBF...!(3336 chars total)
```

## Components

### 1. `thermal_frame_parser.py`
Parses raw thermal frames according to sensor datasheet.

**Key Features:**
- Validates frame size (3336 chars)
- Extracts 24×32 temperature grid
- Separates EEPROM configuration data
- Converts raw hex values to Celsius

**Usage:**
```python
from thermal_frame_parser import ThermalFrameParser

# Parse frame
result = ThermalFrameParser.parse_frame(raw_hex_data)

# Access grid (24x32 numpy array)
temp_grid = result['grid']  # Values in Celsius

# Access EEPROM data
eeprom = result['eeprom']  # 264 char hex string
```

### 2. `tcp_sensor_simulator.py`
Updated simulator generates frames in correct format with realistic thermal data.

**Start Simulator:**
```bash
python tcp_sensor_simulator.py --port 4888 --loc-id cam01 --interval 0.5
```

**Output:**
- Sends `#serialno:SIM409534!`
- Sends `#locid:cam01!`
- Sends `#frame1:<3336_chars>!` every 0.5s (contains room temp + hot spots)
- Sends `#Sensor:cam01:ADC1=...,ADC2=...,MPY30=...!`

**Thermal Data Features:**
- **Ambient temperature**: Base room temp (24-28°C) with animated wave pattern
- **Target temperature**: 2-4 random hot spots (45-85°C) for fire detection testing
- Hot spots are 3×3 cells with gradual temperature falloff from center
- Widget displays the **maximum temperature** from the grid as the target temperature
- Hot cells (above threshold) are highlighted in red overlay with yellow borders

### 3. `tcp_sensor_server.py`
TCP server updated to parse new frame format.

**Changes:**
- Imports `ThermalFrameParser`
- Validates 3336-char frames
- Parses grid + EEPROM data
- Forwards parsed matrix to video widgets

## Temperature Conversion

Conversion uses a **signed linear calibration model** loaded from `stream_config.json` and optionally overridden by the EEPROM stub:

```python
if signed and raw_value > 0x7FFF:
    raw_value -= 0x10000  # two's complement
temp_celsius = raw_value * scale + offset
```

### Current Calibration (stream_config.json)
```json
"thermal_calibration": {
    "signed": true,
    "scale": 0.01,
    "offset": 27.0,
    "description": "signed=true: interpret as two's complement. Raw values in centi-degrees, offset calibrates to ambient."
}
```

**How it works:**
- Sensor outputs **signed 16-bit values** in centi-degrees (hundredths)
- Example: `0xFFB6` = -74 (signed) → -74 × 0.01 + 27.0 = **26.26°C**
- Example: `0x14D0` = 5328 (unsigned) → 5328 × 0.01 + 27.0 = **80.28°C** (fire)
- Example: `0xF574` = -2700 (signed) → -2700 × 0.01 + 27.0 = **0.00°C** (freezing)

**Configuration sources:**
1. `stream_config.json` → `thermal_calibration` block (baseline)
2. If `thermal_use_eeprom` is `true`, EEPROM first two words can override `scale` & `offset` (see below)
3. Runtime adjustment via `ThermalFrameParser.set_calibration()` or `calibrate_thermal.py`

**Temperature Range:**
- Sensor: -40°C to +300°C (typical thermal camera range)
- Detection: Works dynamically for fire (>40°C), freezing (<5°C), or any threshold
- No hardcoded limits - fully configurable thresholds in GUI## Integration Flow

1. **TCP Client → Server**
   - Camera sends `#frame1234:<3336_chars>!`
   - Server receives and buffers until `!` terminator

2. **Server → Parser**
   - Extracts raw hex data (3336 chars)
   - Calls `ThermalFrameParser.parse_frame()`
   - Returns 24×32 temperature matrix

3. **Parser → Video Widget**
   - Matrix forwarded via packet callback
   - Widget calls `_handle_thermal_data(matrix, loc_id)`
   - Grid overlay or hot cell detection applied

4. **Display**
   - Grid view: Show all 768 temperature values
   - Normal view: Highlight hot cells above threshold

## Testing

### Test Parser:
```bash
python thermal_frame_parser.py
```

### Test with Real Frame:
```bash
python test_parse_frame.py
```
This parses a real thermal frame and shows:
- Temperature range and statistics
- EEPROM calibration detection
- Hot/cold spot analysis
- Grid samples from different regions

### Test Full Stack:
```bash
# Terminal 1: Start app
python main.py

# Terminal 2: Start simulator (generates realistic temps 24-28°C + fire hotspots 45-85°C)
python tcp_sensor_simulator.py --port 4888 --loc-id cam01 --interval 0.5
```

### Verify Output:
- Check terminal logs for "Sent frame #N (3336 chars)"
- In app, toggle thermal grid view (⌗ button)
- Should see 24×32 grid overlay with temperature values
- **Temperature widget** displays the **target temperature** (maximum value from the grid)
- **Hot cells** (above threshold) are highlighted in red overlay with yellow borders

### Run Test Suite:
```bash
python test_embereye_suite.py
```
Tests include:
- Thermal frame parsing with target temperature extraction
- Sensor fusion hot cell detection
- TCP packet parsing
- Integration tests

## Troubleshooting

### Frame Length Errors
If you see: `Frame parse error: expected 3336 chars, got XXXX`
- Check simulator output: must generate exactly 3336 chars
- Verify no spaces in frame data
- Ensure EEPROM data included (264 chars)

### Temperature Scale Issues
If temperatures seem wrong:
1. **Check calibration in `stream_config.json`:**
   - Ensure `signed: true` (sensor uses two's complement)
   - Verify `scale: 0.01` (centi-degrees to Celsius)
   - Adjust `offset` to match ambient temperature (default 27.0°C)

2. **Recalibrate using helper script:**
   ```bash
   python calibrate_thermal.py
   ```
   Prompts for ambient reference temperature and calculates correct offset

3. **Check EEPROM override:**
   - If `thermal_use_eeprom: true`, check first two EEPROM words
   - Invalid EEPROM values (out of sanity bounds) are automatically rejected
   - Parser will fall back to config-based calibration

### Sensor Fusion Alarm Not Triggering
If high temperatures are displayed but fusion shows "Normal":
1. **Check threshold in Sensor Configuration:**
   - Open menu: **Profile → Sensor Configuration** (or similar submenu)
   - Go to **Fusion Thresholds** tab
   - Default **Temperature Threshold: 40.0°C** (fire detection level)
   - Adjust threshold based on your environment:
     - 30-35°C: Detect warm objects
     - 40-45°C: Typical fire detection range
     - 50°C+: High-confidence fire only

2. **Threshold units changed from raw to Celsius:**
   - **Old system**: Used 0-255 raw scale (160 ≈ 40°C)
   - **Current system**: Uses actual Celsius values (40.0°C)
   - If upgrading from old version, threshold may need adjustment

3. **Verify min_sources setting:**
   - Fusion requires data from multiple sensors by default
   - **min_sources: 2** means alarm needs 2+ sensors agreeing
   - Lower to 1 for thermal-only detection
   - Increase to 3 for higher confidence (requires thermal + gas + flame)

### EEPROM Stub Auto-Calibration
The EEPROM tail (last 264 chars = 66 words) now provides an optional override for global scale & offset when `thermal_use_eeprom` is enabled in `stream_config.json`.

Stub convention (first two 16-bit words):
| Word | Meaning                                  | Encoding                    | Example    | Result        |
|------|------------------------------------------|-----------------------------|------------|---------------|
| 0    | Global scale (milli units per raw count) | Unsigned 16-bit             | `03E8`     | 1000 -> 1.000 |
| 1    | Global offset (centi-degrees)            | Signed 16-bit two's complement | `FF9C` | -100 -> -1.00 |

Algorithm implemented in `_maybe_apply_eeprom(eeprom_hex)`:
1. Extract first 8 chars (2 words).
2. `scale = word0 / 1000.0` ; `offset = signed(word1) / 100.0`.
3. Sanity bounds: `0.0005 <= scale <= 0.2`, `-100 <= offset <= 100`.
4. If valid and different from current, update parser's in-memory calibration before grid conversion.

This provides quick field calibration without restarting the app. All remaining EEPROM words are ignored by the stub but reserved for future per-pixel or factory data (bad pixel maps, serial, etc.).

Disable by setting `"thermal_use_eeprom": false` in `stream_config.json` to rely solely on the static `thermal_calibration` block.

### EEPROM Data (Future Extensions)
Beyond the stub, future versions may parse:
- Per-pixel gain/offset arrays
- Dead pixel correction tables
- Sensor serial & production metadata
- Emissivity / ambient compensation parameters

## Files Modified
- ✅ `thermal_frame_parser.py` - Frame parsing + EEPROM stub auto-calibration
- ✅ `tcp_sensor_simulator.py` - Updated: 834-word frame generation
- ✅ `tcp_sensor_server.py` - Updated: Parse 3336-char frames
- ✅ `stream_config.json` - `enable_grafana: false`
- ✅ `EmberEye.spec` - Exclude WebEngine modules

## Windows Deployment
All changes included in: `EmberEye_Windows_Source_20251130.zip` (regenerated after EEPROM stub integration)
