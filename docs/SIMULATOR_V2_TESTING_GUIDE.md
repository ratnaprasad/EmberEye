# Simulator V2 Testing Guide

## Quick Start

### 1. Start the Simulator
```bash
python tcp_sensor_simulator_v2.py --host 127.0.0.1 --port 9001 --loc-id demo_room
```

**Output:** `✅ Simulator started (logs: simulator_debug.log)`

### 2. Start EmberEye Application
- Run `main.py` or the .exe
- The simulator will automatically respond to:
  - `EEPROM1` → Sends 832-block calibration data
  - `PERIOD_ON` → Enables continuous frame streaming
  - `REQUEST1` → Sends single frame on demand

### 3. Check Logs (No Console Output)

**Simulator logs:**
- `simulator_debug.log` - All simulator events

**Application logs:**
- `logs/tcp_server_debug.log` - TCP server events  
- `logs/tcp_server_error.log` - TCP server errors
- `logs/vision_debug.log` - Vision detection events
- `logs/vision_error.log` - Vision detection errors
- `logs/tcp_raw_packets.log` - Raw TCP packets
- `logs/tcp_errors.log` - TCP packet errors

## What the Simulator Does

1. **Connects** to your TCP server (port 9001 default)
2. **Sends** initial packets:
   - `#serialno:SIM123456!`
   - `#locid:demo_room!`
3. **Waits** for commands from server
4. **Responds** to `EEPROM1` with 832-block calibration data
5. **Starts** continuous streaming after `PERIOD_ON` command
6. **Sends** frame + sensor data every 2 seconds

## Frame Data Format

- **Thermal frames:** 834 blocks (3336 chars)
  - 768 grid blocks (24×32 thermal grid)
  - 66 invalid EEPROM blocks (ignored after EEPROM1)
- **EEPROM data:** 832 blocks (3328 chars)
  - Block 0: Calibration offset (27.0°C = 2700 centi-degrees)
  - Blocks 1-831: Random calibration data
- **Sensor data:** `ADC1=xxx,ADC2=xxx,MPY30=x`

## Hotspot Simulation

The simulator generates 2-3 random hotspots per frame:
- **Temperature range:** 50-80°C (fire detection range)
- **Location:** Random positions in 24×32 grid
- **Size:** 3×3 cell regions with temperature falloff

## Command Response Times

- **EEPROM1** → Immediate response (832 blocks)
- **PERIOD_ON** → Starts continuous 2-second interval frames
- **REQUEST1** → Single frame sent immediately

## Testing Checklist

- [ ] Simulator connects successfully
- [ ] EEPROM1 command received and responded
- [ ] PERIOD_ON command received and continuous mode enabled
- [ ] Frames visible in EmberEye (thermal grid overlay)
- [ ] Sensor data visible (ADC1, ADC2, MPY30 percentages)
- [ ] Hotspots highlighted in red on thermal overlay
- [ ] No console output from either simulator or application
- [ ] All logs writing to files only

## Troubleshooting

### Simulator not connecting
- Check port 9001 is not in use: `lsof -i :9001` (macOS/Linux) or `netstat -ano | findstr 9001` (Windows)
- Check TCP server started in EmberEye

### No frames received
- Check `simulator_debug.log` for "Continuous mode enabled"
- Check `logs/tcp_server_debug.log` for "Sent PERIOD_ON command"
- Verify loc_id matches a configured device in EmberEye

### Console still showing prints
- Check `tcp_async_server.py` has `tcp_server_logger` import
- Check `vision_detector.py` has `vision_logger` import
- Restart application after code changes

## Command Line Options

```bash
python tcp_sensor_simulator_v2.py [options]

Options:
  --host HOST       TCP server host (default: 127.0.0.1)
  --port PORT       TCP server port (default: 9001)
  --loc-id LOC_ID   Location ID for routing (default: demo_room)
```

## Example: Multiple Simulators

Run multiple simulators for different rooms:

```bash
# Terminal 1: Demo room
python tcp_sensor_simulator_v2.py --loc-id demo_room

# Terminal 2: Office
python tcp_sensor_simulator_v2.py --loc-id office

# Terminal 3: Warehouse
python tcp_sensor_simulator_v2.py --loc-id warehouse
```

Each simulator will create its own log file: `simulator_debug.log`

---

**Status:** ✅ Simulator V2 ready for testing with EEPROM1, PERIOD_ON, REQUEST1 support and silent operation.
