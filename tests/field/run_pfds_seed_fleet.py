#!/usr/bin/env python3
"""Generate per-device PFDS replay seed files and launch upgraded simulators as a fleet.

Example:
  python tests/field/run_pfds_seed_fleet.py --host 127.0.0.1 --port 5080 \
    --devices room_101,room_102,room_103,room_104,room_105
"""

import argparse
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
SIMULATOR = ROOT / "simulators" / "pfds" / "pfds_simulator.py"


@dataclass
class DeviceSpec:
    loc_id: str
    serial: str


def _parse_devices(raw_devices: str, count: int) -> List[DeviceSpec]:
    items = [part.strip() for part in str(raw_devices or "").split(",") if part.strip()]
    if not items and count > 0:
        items = [f"room_{idx:03d}" for idx in range(1, count + 1)]
    if not items:
        items = ["demo_room"]

    specs: List[DeviceSpec] = []
    for idx, loc_id in enumerate(items, start=1):
        specs.append(DeviceSpec(loc_id=loc_id, serial=f"SIM{idx:06d}"))
    return specs


def _hex_payload(length: int, seed: int) -> str:
    chars = "0123456789ABCDEF"
    return "".join(chars[(seed + i) % 16] for i in range(length))


def _build_seed_log(loc_id: str, serial: str, frames: int, step_ms: int) -> str:
    base = datetime(2026, 1, 1, 10, 0, 0, 0)
    lines: List[str] = []
    frame_payload = _hex_payload(3336, seed=sum(ord(c) for c in loc_id) % 16)
    eeprom_payload = _hex_payload(3328, seed=sum(ord(c) for c in serial) % 16)

    lines.append(f"[{base.strftime('%H:%M:%S.%f')[:-3]}]IN #EEPROM{loc_id}:{eeprom_payload}!")

    for i in range(frames):
        ts = base + timedelta(milliseconds=(i + 1) * step_ms)
        ts2 = ts + timedelta(milliseconds=max(20, step_ms // 3))

        adc1 = 900 + ((i * 47) % 900)
        adc2 = 650 + ((i * 31) % 700)
        gas = 180 + ((i * 13) % 240)

        lines.append(f"[{ts.strftime('%H:%M:%S.%f')[:-3]}]IN #frame{loc_id}:{frame_payload}!")
        lines.append(
            f"[{ts2.strftime('%H:%M:%S.%f')[:-3]}]IN #Sensor{loc_id}:"
            f"ADC1={adc1},ADC2={adc2},MPY30=0,gas={gas}!"
        )

    return "\n".join(lines) + "\n"


def _write_seed_files(seed_dir: Path, specs: List[DeviceSpec], frames: int, step_ms: int) -> List[Path]:
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed_files: List[Path] = []
    for spec in specs:
        file_name = f"{spec.loc_id}__{spec.serial}.txt"
        target = seed_dir / file_name
        target.write_text(_build_seed_log(spec.loc_id, spec.serial, frames=frames, step_ms=step_ms), encoding="utf-8")
        seed_files.append(target)
    return seed_files


def _start_simulators(
    python_exe: str,
    host: str,
    port: int,
    specs: List[DeviceSpec],
    seed_files: List[Path],
    speed: float,
    no_loop: bool,
    stagger_seconds: float,
) -> List[subprocess.Popen]:
    procs: List[subprocess.Popen] = []
    for spec, seed_file in zip(specs, seed_files):
        cmd = [
            python_exe,
            str(SIMULATOR),
            "--host",
            host,
            "--port",
            str(port),
            "--loc-id",
            spec.loc_id,
            "--serial",
            spec.serial,
            "--data",
            str(seed_file),
            "--speed",
            str(speed),
        ]
        if no_loop:
            cmd.append("--no-loop")

        proc = subprocess.Popen(cmd, cwd=str(ROOT))
        procs.append(proc)
        print(
            f"Started simulator pid={proc.pid} loc_id={spec.loc_id} serial={spec.serial} "
            f"seed={seed_file.name} -> {host}:{port}"
        )
        if stagger_seconds > 0:
            time.sleep(stagger_seconds)
    return procs


def _stop_all(procs: List[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is not None:
            continue
        try:
            proc.terminate()
        except Exception:
            pass
    for proc in procs:
        if proc.poll() is not None:
            continue
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed-based PFDS fleet simulator launcher (upgraded simulator)")
    parser.add_argument("--host", default="127.0.0.1", help="TCP server host")
    parser.add_argument("--port", type=int, default=5080, help="TCP server port")
    parser.add_argument("--devices", default="", help="Comma-separated location IDs (one simulator per ID)")
    parser.add_argument("--count", type=int, default=0, help="Auto-generate N devices (room_001..room_N) when --devices is empty")
    parser.add_argument("--frames", type=int, default=120, help="Frame events per seed file")
    parser.add_argument("--step-ms", type=int, default=300, help="Timestamp interval between frames in seed log")
    parser.add_argument("--speed", type=float, default=6.0, help="Replay speed multiplier")
    parser.add_argument("--seed-dir", default="tests/field/generated_pfds_seeds", help="Directory to write seed files")
    parser.add_argument("--no-loop", action="store_true", help="Run each simulator once then stop")
    parser.add_argument("--stagger-seconds", type=float, default=0.2, help="Delay between process starts")
    parser.add_argument("--generate-only", action="store_true", help="Only generate seed files, do not launch simulators")
    args = parser.parse_args()

    if not SIMULATOR.exists():
        print(f"Upgraded simulator not found: {SIMULATOR}")
        return 2

    specs = _parse_devices(args.devices, args.count)
    seed_dir = (ROOT / args.seed_dir).resolve()
    seed_files = _write_seed_files(seed_dir, specs, frames=max(1, args.frames), step_ms=max(50, args.step_ms))

    print(f"Generated {len(seed_files)} seed files in {seed_dir}")
    for sf in seed_files:
        print(f"  - {sf.name}")

    if args.generate_only:
        return 0

    procs: List[subprocess.Popen] = []

    def _handle_shutdown(_sig, _frame):
        print("Shutting down simulator fleet...")
        _stop_all(procs)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    procs = _start_simulators(
        python_exe=sys.executable,
        host=args.host,
        port=int(args.port),
        specs=specs,
        seed_files=seed_files,
        speed=float(args.speed),
        no_loop=bool(args.no_loop),
        stagger_seconds=max(0.0, float(args.stagger_seconds)),
    )

    if not procs:
        print("No simulators started.")
        return 1

    print("Simulator fleet running. Press Ctrl+C to stop all simulators.")

    if args.no_loop:
        exit_code = 0
        for proc in procs:
            rc = proc.wait()
            if rc != 0:
                exit_code = rc
        return exit_code

    try:
        while True:
            dead = [p for p in procs if p.poll() is not None]
            if dead:
                for proc in dead:
                    print(f"Simulator exited pid={proc.pid} rc={proc.returncode}")
                procs = [p for p in procs if p.poll() is None]
                if not procs:
                    return 1
            time.sleep(0.5)
    finally:
        _stop_all(procs)


if __name__ == "__main__":
    raise SystemExit(main())
