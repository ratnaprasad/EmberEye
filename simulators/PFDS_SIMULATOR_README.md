# PFDS Device Simulator v3

Real data replay simulator for Precision Fire Detection System (PFDS) devices.

## Overview

This simulator replays actual captured device data from a 10-minute recording, providing authentic behavior for testing and development.

## Features

✅ **Real Data Replay**: Uses actual device data from `NEW DATA 10 MINS.txt`  
✅ **Chronological Playback**: Automatically sorts and plays data in time order  
✅ **5-Second Intervals**: Matches actual PFDS device transmission timing  
✅ **Infinite Loop**: Automatically restarts from beginning after reaching end  
✅ **Full Protocol Support**: PERIOD_ON, REQUEST1, EEPROM1 commands  
✅ **Three Data Types**: Thermal frames, sensor data, EEPROM calibration  

## Quick Start

```bash
# Navigate to simulators directory
cd d:\EE\EmberEye\simulators

# Run with defaults (0.0.0.0:9001, 5-second interval)
python pfdsdevicesimulator.py

# Custom port
python pfdsdevicesimulator.py --port 9002

# Custom interval (e.g., 3 seconds for faster testing)
python pfdsdevicesimulator.py --interval 3.0

# Specific host
python pfdsdevicesimulator.py --host 127.0.0.1 --port 9001
```

## Data File Format

The simulator reads from `data/NEW DATA 10 MINS.txt` which contains timestamped device communications:

```
[13:06:38.922]OUT→¡óEEPROM1¡õ
[13:07:20.822]IN←¡ô#frame1234:FFD9FFD5FFCB...!
[13:07:21.223]IN←¡ô#Sensor1234:ADC1=1048,ADC2=489,...!
```

- **OUT**: Commands sent to device (recorded for reference)
- **IN**: Responses from device (what simulator replays)

## Protocol Commands

### PERIOD_ON / PERIODIC_ON
Start continuous streaming mode. Simulator sends data packets every 5 seconds.

```bash
echo "PERIOD_ON" | nc localhost 9001
```

### PERIOD_OFF
Stop continuous streaming.

```bash
echo "PERIOD_OFF" | nc localhost 9001
```

### REQUEST1
Request single thermal frame (on-demand).

```bash
echo "REQUEST1" | nc localhost 9001
```

### EEPROM1
Request full calibration data (832 blocks).

```bash
echo "EEPROM1" | nc localhost 9001
```

## Packet Types

### 1. Thermal Frames
```
#frame1234:FFD9FFD5FFCB...484E17FC7FFF...!
```
- 834 word blocks (4 chars each) = 3336 chars
- 24x32 thermal grid data
- Embedded EEPROM configuration

### 2. Sensor Data
```
#Sensor1234:ADC1=1048,ADC2=489,Button=1,MQ_IN=0,MPY_IN=0,DIO_OUT=0!
```
- ADC readings
- Button state
- Digital I/O states

### 3. EEPROM Calibration
```
#EEPROM1234:00AC899F000020610005...!
```
- Full calibration dataset (832 blocks)
- Temperature offset correction
- Device configuration

## Data Flow

```
Client              Simulator               Data File
  |                    |                        |
  |--PERIOD_ON-------->|                        |
  |                    |----read records------->|
  |                    |<-sorted by timestamp---|
  |                    |                        |
  |<--thermal frame----|  (every 5 seconds)     |
  |<--sensor data------|  (every 5 seconds)     |
  |<--thermal frame----|  (every 5 seconds)     |
  |                    |                        |
  |                    |----loop to start------>|
  |<--thermal frame----|  (continues forever)   |
  ...                 ...                      ...
```

## Looping Behavior

1. Simulator loads all records from data file
2. Sorts by timestamp (13:06:38 → 13:17:59)
3. Filters to response packets only (IN←)
4. Starts sending from first record
5. Sends packets every 5 seconds
6. When reaching last record → resets to first record
7. Infinite loop continues until client disconnects

## Testing with EmberEye

1. **Start simulator**:
   ```bash
   python pfdsdevicesimulator.py
   ```

2. **Configure EmberEye** to connect to `127.0.0.1:9001`

3. **Trigger streaming** - EmberEye sends `PERIOD_ON` on connect

4. **Observe data** - Should receive thermal frames and sensor data every 5 seconds

## Log Output

```
[2026-01-31 12:00:00.123] PFDS Device Simulator v3 Initialized
[2026-01-31 12:00:00.124] Server: 0.0.0.0:9001
[2026-01-31 12:00:00.125] Loading data from data/NEW DATA 10 MINS.txt...
[2026-01-31 12:00:00.234] ✓ Loaded 1220 total records
[2026-01-31 12:00:00.235] ✓ Filtered to 543 response packets
[2026-01-31 12:00:00.236] ✓ Time range: 13:06:58 - 13:17:59 (661.0s)
[2026-01-31 12:00:00.237] ✓ Packet breakdown:
[2026-01-31 12:00:00.238]   - EEPROM_DATA: 3
[2026-01-31 12:00:00.239]   - SENSOR_DATA: 270
[2026-01-31 12:00:00.240]   - THERMAL_FRAME: 270
[2026-01-31 12:00:00.241] ✓ Server listening on 0.0.0.0:9001
[2026-01-31 12:00:00.242] Ready to replay 543 packets in loop
```

## Statistics

During operation, the simulator tracks:
- **Packets sent**: Total number of packets transmitted
- **Loop count**: Number of times data file has been replayed
- **Connection status**: Client connected/disconnected events

Example after 30 minutes:
```
⏸ Streaming stopped (sent 360 packets, 3 loops)
```

## Troubleshooting

### Data file not found
```
ERROR: Data file not found: data/NEW DATA 10 MINS.txt
```
**Solution**: Ensure `NEW DATA 10 MINS.txt` exists in `simulators/data/` directory

### Port already in use
```
ERROR starting server: [Errno 98] Address already in use
```
**Solution**: Use different port with `--port 9002` or stop other process using port 9001

### No packets sent
- Check if client sent `PERIOD_ON` command
- Try sending `REQUEST1` for single frame test
- Verify client connection established

## Advanced Usage

### Custom Data File
```bash
python pfdsdevicesimulator.py --data my_custom_data.txt
```

### Faster Testing (2-second intervals)
```bash
python pfdsdevicesimulator.py --interval 2.0
```

### Multiple Simulators (different ports)
```bash
# Simulator 1
python pfdsdevicesimulator.py --port 9001 &

# Simulator 2  
python pfdsdevicesimulator.py --port 9002 &

# Simulator 3
python pfdsdevicesimulator.py --port 9003 &
```

## Architecture

```
PFDSDeviceSimulator
├── load_data()          # Parse data file
├── get_next_packet()    # Get next record (with looping)
├── send_packet()        # Send to client
├── handle_command()     # Process PERIOD_ON, REQUEST1, etc.
├── streaming_loop()     # Background thread (every 5s)
└── start_server()       # TCP server
```

## Comparison with v2

| Feature | v2 (Synthetic) | v3 (Real Data) |
|---------|---------------|----------------|
| Data Source | Generated | Real device capture |
| Timing | Configurable | 5s (authentic) |
| Patterns | Synthetic waves | Real variations |
| Calibration | Random | Actual EEPROM |
| Accuracy | Approximate | Exact replay |

## Future Enhancements

- [ ] Support multiple data files
- [ ] Speed control (1x, 2x, 0.5x playback)
- [ ] Packet filtering by type
- [ ] Timestamp synchronization
- [ ] Data export/import tools

## License

Part of EmberEye Fire Detection System  
© 2026 EmberEye

---

**Version**: 3.0  
**Date**: January 2026  
**Author**: EmberEye Development Team
