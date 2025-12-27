# Simulators

This folder contains standalone simulators used for local testing and demos.

- `tcp_simulator.py`: Minimal TCP payload simulator that sends serial number,
  thermal frame, and sensor values to a running server (e.g., `tcp_sensor_server.py`).

Usage:

```bash
python simulators/tcp_simulator.py --help
python simulators/tcp_simulator.py
```

For protocol-compliant streaming tests, use `tcp_sensor_simulator_v3.py` in the repo root.
