#!/usr/bin/env python3
"""
Play fusion CSV cases into the live EmberEye Field app one-by-one.

Manual mode (default): press Enter to advance.
Auto mode: --auto --delay N
"""

from __future__ import annotations

import argparse
import csv
import random
import socket
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_CSV = REPO_ROOT / "tests" / "data" / "fusion_testcases_input.csv"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4888
DEFAULT_SERIAL = "EHWK005001"
DEFAULT_DELAY = 4.0
DEFAULT_REPEAT = 2
EEPROM_CHARS = 3328


def requires_live_vision(tc: dict) -> bool:
    temp = float(tc["temp"])
    smoke = float(tc["smoke"])
    flame = float(tc["flame"])
    return not (temp >= 60.0 or smoke >= 25.0 or flame >= 25.0)


def _celsius_to_raw(temp_c: float) -> str:
    raw = int(round((float(temp_c) - 27.0) * 100.0))
    if raw < 0:
        raw += 0x10000
    raw = max(0, min(0xFFFF, raw))
    return f"{raw:04X}"


def make_thermal_frame_packet(serial: str, temp_c: float) -> str:
    word = _celsius_to_raw(temp_c)
    grid_hex = word * 768
    eeprom_hex = "0000" * 66
    return f"#frame{serial}:{grid_hex}{eeprom_hex}!"


def make_sensor_packet(serial: str, smoke_pct: float, flame_pct: float, mpy_in: int = 0) -> str:
    adc1 = max(0, min(4095, round(smoke_pct * 4095.0 / 100.0)))
    adc2 = max(0, min(4095, round(flame_pct * 4095.0 / 100.0)))
    return (
        f"#Sensor{serial}:ADC1={adc1},ADC2={adc2},"
        f"Button=0,MQ_IN=0,MPY_IN={mpy_in},DIO_OUT=0!"
    )


def make_eeprom_packet(serial: str) -> str:
    word0 = "0000"
    rest = "".join(f"{random.randint(100, 9999):04X}" for _ in range(EEPROM_CHARS // 4 - 1))
    return f"#EEPROM{serial}:{word0}{rest}!"


def load_test_cases(csv_path: Path) -> List[dict]:
    cases = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cases.append(
                {
                    "tc": int(row["Test Case"]),
                    "vision": float(row["Vision Score"]),
                    "temp": float(row["Temp (°C)"]),
                    "smoke": float(row["Smoke (%)"]),
                    "flame": float(row["Flame (%)"]),
                    "expected": row["Expected Alarm (Provided)"].strip().upper(),
                    "description": row["Description"].strip(),
                }
            )
    return cases


def _banner(tc: dict, idx: int, total: int, mode_hint: str) -> str:
    bar = "-" * 70
    alarm_word = "ALARM" if tc["expected"] == "Y" else "clear"
    live_path = "needs live vision" if requires_live_vision(tc) else "sensor-only live trigger"
    lines = [
        "",
        bar,
        f"TC {tc['tc']:>2}/{total:<2}  {alarm_word}  {mode_hint}",
        tc["description"],
        f"Temp={tc['temp']:5.1f}C  Smoke={tc['smoke']:5.1f}%  Flame={tc['flame']:5.1f}%  Vision={tc['vision']:.2f}",
        f"Live UI path: {live_path}",
        bar,
    ]
    return "\n".join(lines)


class PlaybackClient:
    def __init__(self, host: str, port: int, serial: str):
        self.host = host
        self.port = port
        self.serial = serial
        self._sock: Optional[socket.socket] = None
        self._shutdown = threading.Event()

    def connect(self) -> bool:
        print(f"Connecting to {self.host}:{self.port} as serial={self.serial} ...", end="", flush=True)
        for _ in range(30):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                s.connect((self.host, self.port))
                s.settimeout(None)
                self._sock = s
                print(" connected")
                return True
            except Exception:
                time.sleep(2.0)
                print(".", end="", flush=True)
        print(" failed")
        return False

    def disconnect(self) -> None:
        self._shutdown.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _send(self, packet: str) -> bool:
        if not self._sock:
            return False
        try:
            self._sock.sendall((packet + "\n").encode("utf-8"))
            return True
        except Exception as exc:
            print(f"\n[WARN] send failed: {exc}")
            return False

    def _handle_cmd(self, cmd: str) -> None:
        if cmd == "DEVICE_ID":
            self._send(f"#DEVICE_ID:{self.serial}!")
            print("\n< DEVICE_ID")
        elif cmd == "EEPROM1":
            self._send(make_eeprom_packet(self.serial))
            print("\n< EEPROM1")
        elif cmd:
            print(f"\n< {cmd}")

    def start_listener(self) -> None:
        t = threading.Thread(target=self._listener, daemon=True)
        t.start()

    def _listener(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        buf = ""
        while not self._shutdown.is_set():
            try:
                chunk = self._sock.recv(1024)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    self._handle_cmd(line.strip())
            except socket.timeout:
                continue
            except Exception:
                break

    def send_case(self, tc: dict, repeat: int = 1) -> None:
        frame_pkt = make_thermal_frame_packet(self.serial, tc["temp"])
        sensor_pkt = make_sensor_packet(self.serial, tc["smoke"], tc["flame"])
        for _ in range(max(1, repeat)):
            self._send(frame_pkt)
            self._send(sensor_pkt)
            time.sleep(0.15)

    def send_reset_state(self, temp_c: float = 35.0, repeat: int = 1) -> None:
        """Send a neutral non-alarm state to separate test-case transitions."""
        frame_pkt = make_thermal_frame_packet(self.serial, temp_c)
        sensor_pkt = make_sensor_packet(self.serial, smoke_pct=0.0, flame_pct=0.0)
        for _ in range(max(1, repeat)):
            self._send(frame_pkt)
            self._send(sensor_pkt)
            time.sleep(0.12)


def run_playback(args) -> None:
    cases = load_test_cases(INPUT_CSV)
    if args.case is not None:
        selected = [tc for tc in cases if int(tc.get("tc", -1)) == int(args.case)]
        if not selected:
            print(f"No test case found for --case {args.case}")
            sys.exit(2)
        cases = selected
    else:
        total = len(cases)
        start_idx = max(0, min(args.start - 1, total - 1))
        cases = cases[start_idx:]

    client = PlaybackClient(args.host, args.port, args.serial)
    if not client.connect():
        sys.exit(1)

    client.start_listener()
    print("Waiting for handshake (2s) ...")
    time.sleep(2.0)

    mode_label = f"AUTO {args.delay}s/case" if args.auto else "MANUAL (Enter for next)"
    print(f"Mode: {mode_label} | Cases: {len(cases)} | Serial: {args.serial}")
    print("Note: TCP playback feeds thermal+sensor packets only. Vision-only or vision-correlated alarms stay clear unless the widget/camera path supplies vision_score.")

    try:
        for i, tc in enumerate(cases):
            if i > 0 and bool(args.reset_between):
                client.send_reset_state(temp_c=float(args.reset_temp), repeat=max(1, int(args.reset_repeat)))
                if float(args.reset_hold) > 0:
                    time.sleep(float(args.reset_hold))

            hint = f"[{i + 1}/{len(cases)}]"
            print(_banner(tc, i + 1, len(cases), hint))
            client.send_case(tc, repeat=args.repeat)
            print(f"Sent TC{tc['tc']:02d}")
            if requires_live_vision(tc):
                print("Live expectation: no alarm unless a vision score is being produced for this tile.")

            if i < len(cases) - 1:
                if args.auto:
                    time.sleep(args.delay)
                else:
                    input("Press Enter for next case (Ctrl+C to stop) ...")

        print("\nAll cases sent. Keeping connection open (Ctrl+C to exit).")
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        client.disconnect()


def parse_args():
    p = argparse.ArgumentParser(description="Replay fusion test CSV into live EmberEye Field UI.")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", default=DEFAULT_PORT, type=int)
    p.add_argument("--serial", default=DEFAULT_SERIAL)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--delay", default=DEFAULT_DELAY, type=float)
    p.add_argument("--repeat", default=DEFAULT_REPEAT, type=int)
    p.add_argument("--start", default=1, type=int)
    p.add_argument("--case", default=None, type=int, help="Run only a single test case number")
    p.add_argument("--reset-temp", default=35.0, type=float, help="Neutral reset temperature between cases")
    p.add_argument("--reset-hold", default=0.8, type=float, help="Seconds to wait after reset packet")
    p.add_argument("--reset-repeat", default=2, type=int, help="How many reset packets to send between cases")
    p.add_argument("--reset-between", dest="reset_between", action="store_true", help="Inject neutral reset state between cases")
    p.add_argument("--no-reset-between", dest="reset_between", action="store_false", help="Do not inject reset state between cases")
    p.set_defaults(reset_between=True)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print("EmberHawk Test Case UI Playback")
    print(f"CSV: {INPUT_CSV}")
    run_playback(args)
