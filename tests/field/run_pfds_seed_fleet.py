#!/usr/bin/env python3
"""Launch N EmberHawk simulators, each with its matching per-instance seed file.

Expected seed naming convention:
  simulators/pfds/data/emberhawk_fusion_seed_3min_inst001.txt
  simulators/pfds/data/emberhawk_fusion_seed_3min_inst002.txt
  ...

Example:
  python tests/field/run_pfds_seed_fleet.py --host 127.0.0.1 --port 9001 --instances 3
"""

from __future__ import annotations

import argparse
import glob
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
SIMULATOR = ROOT / "simulators" / "emberhawk_simulator.py"


@dataclass
class FleetInstance:
    index: int
    serial: str
    seed_file: Path


def _extract_instance_index(path: Path) -> int:
    m = re.search(r"inst(\d{3,})", path.stem)
    if not m:
        raise ValueError(f"Cannot parse instance index from seed filename: {path.name}")
    return int(m.group(1))


def _extract_serial_from_seed(path: Path) -> str:
    # First preference: EEPROM packet id in seed file.
    # Example: #EEPROMEHWK005001:....!
    line_re = re.compile(r"#EEPROM([^:]+):")
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            m = line_re.search(raw)
            if m:
                return m.group(1).strip()
    raise ValueError(f"No #EEPROM<serial>: packet found in {path.name}")


def _discover_instances(seed_pattern: str, limit: int) -> List[FleetInstance]:
    matched = sorted(Path(p) for p in glob.glob(seed_pattern))
    if not matched:
        return []

    fleet: List[FleetInstance] = []
    for seed_file in matched:
        idx = _extract_instance_index(seed_file)
        serial = _extract_serial_from_seed(seed_file)
        fleet.append(FleetInstance(index=idx, serial=serial, seed_file=seed_file.resolve()))

    fleet.sort(key=lambda x: x.index)
    if limit > 0:
        fleet = fleet[:limit]
    return fleet


def _start_fleet(
    instances: List[FleetInstance],
    host: str,
    port: int,
    speed: float,
    stagger_seconds: float,
    no_loop: bool,
    dry_run: bool,
) -> List[subprocess.Popen]:
    procs: List[subprocess.Popen] = []
    for inst in instances:
        cmd = [
            sys.executable,
            str(SIMULATOR),
            "--host",
            host,
            "--port",
            str(port),
            "--serial",
            inst.serial,
            "--data",
            str(inst.seed_file),
            "--speed",
            str(speed),
        ]
        if no_loop:
            cmd.append("--no-loop")

        printable = " ".join(cmd)
        if dry_run:
            print(f"[DRY-RUN] inst={inst.index:03d} serial={inst.serial} cmd={printable}")
        else:
            proc = subprocess.Popen(cmd, cwd=str(ROOT))
            procs.append(proc)
            print(
                f"Started inst={inst.index:03d} pid={proc.pid} serial={inst.serial} "
                f"seed={inst.seed_file.name} -> {host}:{port}"
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
    parser = argparse.ArgumentParser(description="Launch EmberHawk fleet using per-instance seed files")
    parser.add_argument("--host", default="127.0.0.1", help="TCP server host")
    parser.add_argument("--port", type=int, default=9001, help="TCP server port")
    parser.add_argument("--instances", type=int, default=0, help="Number of instances to launch (0 = all discovered)")
    parser.add_argument(
        "--seed-pattern",
        default=str(ROOT / "simulators" / "pfds" / "data" / "emberhawk_fusion_seed_3min_inst*.txt"),
        help="Glob pattern for per-instance seed files",
    )
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier")
    parser.add_argument("--stagger-seconds", type=float, default=0.05, help="Delay between process starts")
    parser.add_argument("--no-loop", action="store_true", help="Run each simulator once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print launch commands without starting processes")
    args = parser.parse_args()

    if not SIMULATOR.exists():
        print(f"Simulator not found: {SIMULATOR}")
        return 2

    fleet = _discover_instances(args.seed_pattern, max(0, int(args.instances)))
    if not fleet:
        print(f"No matching seed files found for pattern: {args.seed_pattern}")
        return 2

    print(f"Discovered {len(fleet)} instance seed files")
    for inst in fleet:
        print(f"  inst={inst.index:03d} serial={inst.serial} seed={inst.seed_file.name}")

    procs: List[subprocess.Popen] = []

    def _handle_shutdown(_sig, _frame):
        print("Shutting down simulator fleet...")
        _stop_all(procs)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    procs = _start_fleet(
        instances=fleet,
        host=str(args.host),
        port=int(args.port),
        speed=float(args.speed),
        stagger_seconds=max(0.0, float(args.stagger_seconds)),
        no_loop=bool(args.no_loop),
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        return 0

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
