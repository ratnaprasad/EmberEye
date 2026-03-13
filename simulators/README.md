# Simulators

This folder contains standalone simulators used for local testing and demos.

## EmberHawk Simulator v2.0 (current — use this)

**`simulators/emberhawk_simulator.py`** — unified PFDS/EmberHawk device simulator.

Supports two modes:

### Replay mode (uses a real PFDS log file)
```bash
python simulators/emberhawk_simulator.py \
  --host 127.0.0.1 --port 9001 \
  --serial 1829602101142 \
  --data simulators/pfds/data/"NEW DATA 10 MINS.txt"
```

### Synthetic mode (generates frames on the fly — no data file needed)
```bash
python simulators/emberhawk_simulator.py \
  --host 127.0.0.1 --port 9001 \
  --interval 1.0
```

### CLI options
| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Field TCP server host |
| `--port` | `9001` | Field TCP server port |
| `--serial` | auto-generated | Device serial number |
| `--data` | *(none)* | PFDS log file path (enables replay mode) |
| `--speed` | `1.0` | Replay speed multiplier |
| `--pair-window-ms` | `1000` | Frame/sensor pairing window (ms) |
| `--no-loop` | off | Stop after one full replay pass |
| `--interval` | `1.0` | Frame send interval in seconds (synthetic mode) |
| `--preview` | `0` | Print first N replay events and exit |

### Commands handled
| Command | Action |
|---------|--------|
| `DEVICE_ID` | Responds `#DEVICE_ID:<serial>!` |
| `EEPROM1`   | Sends 3328-char calibration blob |
| `PERIOD_ON` | Starts continuous frame streaming |
| `PERIOD_OFF`| Stops streaming |
| `REQUEST1`  | Sends one frame immediately |
| `ALARM_ON`  | Sets siren-active state |
| `ACK_ON`    | Acknowledges active alarm |

### Packet wire format
```
#DEVICE_ID:<serial>!
#frame<serial>:<3336_hex_chars>!
#Sensor<serial>:ADC1=...,ADC2=...,Button=...,MQ_IN=...,MPY_IN=...,DIO_OUT=...!
#EEPROM<serial>:<3328_hex_chars>!
```

Log file: `simulators/logs/emberhawk_simulator.log`

---

## RTSP Camera Simulator (unchanged)

`simulators/rtsp/rtsp_camera_simulator.py` — RTSP camera feed via FFmpeg + MediaMTX.
See inline `--help` for usage.

---

## Retired simulators (do not use)

The following files are retired and kept only for reference:

| File | Replaced by |
|------|------------|
| `tcp_sensor_simulator_v3.py` | `simulators/emberhawk_simulator.py` |
| `tcp_simulator.py` | `simulators/emberhawk_simulator.py` |
| `simulators/pfds/pfds_simulator.py` | `simulators/emberhawk_simulator.py` |
