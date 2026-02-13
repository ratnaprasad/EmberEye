# PFDS Log Replay Simulator

Replays PFDS device log data with near real-time timing and frame/sensor pairing.

## Usage

From the repo root:

```
D:\EE\EmberEye\.venv\Scripts\python.exe simulators\pfds\pfds_simulator.py --host 127.0.0.1 --port 9001 --loc-id demo_room
```

## Options

- `--data` Path to PFDS log file (default: `data/NEW DATA 10 MINS.txt`)
- `--speed` Replay speed factor (1.0 = real-time)
- `--pair-window-ms` Max time delta for pairing frame + sensor packets
- `--no-loop` Stop after one pass instead of looping
- `--preview N` Print first N parsed events and exit

## Notes

- The simulator responds to `EEPROM1`, `PERIOD_ON`, `PERIOD_OFF`, and `REQUEST1`.
- Logs are written to `simulators/pfds/logs/simulator_debug.log`.
