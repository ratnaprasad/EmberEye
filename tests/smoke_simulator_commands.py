#!/usr/bin/env python3
"""
Smoke test for EmberHawk Simulator v2.0 (simulators/emberhawk_simulator.py).

Tests both operating modes:
  synthetic — no data file, frames are generated on the fly
  replay    — replay a minimal PFDS-format log file

In both modes all 7 protocol commands must be handled correctly:
  DEVICE_ID  EEPROM1  PERIOD_ON  REQUEST1  ALARM_ON  ACK_ON  PERIOD_OFF
"""
import argparse
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

_COMMANDS = [
    "DEVICE_ID\n",
    "EEPROM1\n",
    "PERIOD_ON\n",
    "REQUEST1\n",
    "ALARM_ON\n",
    "ACK_ON\n",
    "PERIOD_OFF\n",
]

_LOG_CHECKS = {
    "device_id_handled": "Sent DEVICE_ID response",
    "eeprom1_handled":   "Received command: EEPROM1",
    "period_on_handled": "Received command: PERIOD_ON",
    "request1_handled":  "Received command: REQUEST1",
    "alarm_on_handled":  "Received ALARM_ON command - siren state ACTIVE",
    "ack_on_handled":    "Received ACK_ON command - siren acknowledged",
    "period_off_handled":"Received command: PERIOD_OFF",
}

_SIM_PATH = "simulators/emberhawk_simulator.py"
_LOG_PATH = Path("simulators/logs/emberhawk_simulator.log")


def _make_tcp_server(host: str, port: int) -> threading.Thread:
    def _server():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(1)
        conn, _ = srv.accept()
        time.sleep(0.2)
        for cmd in _COMMANDS:
            conn.sendall(cmd.encode("utf-8"))
            time.sleep(0.3)
        conn.close()
        srv.close()

    t = threading.Thread(target=_server, daemon=True)
    t.start()
    return t


def _read_log() -> str:
    return _LOG_PATH.read_text(encoding="utf-8") if _LOG_PATH.exists() else ""


def _print_checks(label: str, log_text: str) -> bool:
    all_ok = True
    for key, needle in _LOG_CHECKS.items():
        found = needle in log_text
        print(f"  [{label}] {key:25s} = {found}")
        if not found:
            all_ok = False
    return all_ok


def _run_smoke(
    host: str,
    port: int,
    label: str,
    extra_args: list,
    wait_secs: float,
) -> bool:
    try:
        _LOG_PATH.unlink(missing_ok=True)
    except Exception:
        pass

    _make_tcp_server(host, port)

    proc = subprocess.Popen(
        [sys.executable, _SIM_PATH, "--host", host, "--port", str(port)] + extra_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(wait_secs)
    proc.terminate()
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate(timeout=5)

    log_text = _read_log()
    all_ok = _print_checks(label, log_text)

    if not all_ok:
        print("  --- stdout ---")
        print(out)
        print("  --- stderr ---")
        print(err)
        print("  --- log ---")
        print(log_text)
    return all_ok


def _build_min_replay_log() -> str:
    frame_payload = "A0" * 1668          # 3336 hex chars
    sensor_payload = "ADC1=1001,ADC2=334,Button=1,MQ_IN=0,MPY_IN=0,DIO_OUT=0"
    eeprom_payload = "B0" * 1664         # 3328 hex chars
    return textwrap.dedent(
        f"""
        [10:00:00.000]IN #frame1829602101142:{frame_payload}!
        [10:00:00.100]IN #Sensor1829602101142:{sensor_payload}!
        [10:00:00.200]IN #EEPROM1829602101142:{eeprom_payload}!
        """
    ).strip() + "\n"


def run_synthetic_smoke(host: str, port: int) -> bool:
    print("\n=== synthetic mode ===")
    return _run_smoke(
        host, port,
        label="synthetic",
        extra_args=["--serial", "SMOKETEST001", "--interval", "0.2"],
        wait_secs=4.5,
    )


def run_replay_smoke(host: str, port: int) -> bool:
    print("\n=== replay mode ===")
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write(_build_min_replay_log())
        temp_log = tf.name
    try:
        return _run_smoke(
            host, port,
            label="replay",
            extra_args=[
                "--serial", "1829602101142",
                "--data", temp_log,
                "--no-loop",
            ],
            wait_secs=5.0,
        )
    finally:
        try:
            Path(temp_log).unlink(missing_ok=True)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test for EmberHawk Simulator v2.0"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-port", type=int, default=9101)
    args = parser.parse_args()

    ok_synthetic = run_synthetic_smoke(args.host, args.base_port)
    ok_replay    = run_replay_smoke(args.host, args.base_port + 1)

    print()
    print("RESULT emberhawk_simulator (synthetic):", "PASS" if ok_synthetic else "FAIL")
    print("RESULT emberhawk_simulator (replay   ):", "PASS" if ok_replay else "FAIL")
    return 0 if (ok_synthetic and ok_replay) else 1


if __name__ == "__main__":
    raise SystemExit(main())
