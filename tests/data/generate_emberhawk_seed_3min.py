#!/usr/bin/env python3
"""
Generate a 3-minute EmberHawk replay seed file from fusion test cases CSV.

Notes:
- Vision score is intentionally ignored (per request).
- Output format is compatible with simulators/emberhawk_simulator.py replay mode.
- Emits one EEPROM packet + one frame + one sensor packet per test case slot.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path


def pct_to_adc(pct: float) -> int:
    pct = max(0.0, min(100.0, float(pct)))
    return int(round((pct / 100.0) * 4095.0))


def temp_to_raw_word(temp_c: float) -> str:
    # Inverse of simulator synthetic mapping: raw ~= (temp - 27.0) / 0.01
    raw = int(round((float(temp_c) - 27.0) / 0.01))
    if raw < 0:
        raw = (raw + 0x10000) & 0xFFFF
    raw = max(0, min(0xFFFF, raw))
    return f"{raw:04X}"


def build_frame_payload(temp_c: float) -> str:
    # 24x32 grid => 768 words => 3072 hex chars
    word = temp_to_raw_word(temp_c)
    grid = word * (24 * 32)

    # Append 66 words (264 hex chars) to match 3336-char frame payload
    # Keep deterministic to make files stable across runs.
    tail = "07D0" * 66
    return grid + tail


def build_eeprom_payload() -> str:
    # 832 words => 3328 chars
    return "03E8" * 832


def parse_cases(csv_path: Path) -> list[dict]:
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    cases: list[dict] = []
    for r in rows:
        # Vision is intentionally ignored.
        cases.append(
            {
                "case_id": int(float(r["Test Case"])),
                "temp_c": float(r["Temp (°C)"]),
                "smoke_pct": float(r["Smoke (%)"]),
                "flame_pct": float(r["Flame (%)"]),
                "expected_alarm": (r.get("Expected Alarm (Provided)", "") or "").strip().upper(),
                "description": (r.get("Description", "") or "").strip(),
            }
        )
    return cases


def serial_for_instance(prefix: str, start: int, idx: int) -> str:
    return f"{prefix}{start + idx:06d}"


def generate_seed(
    csv_path: Path,
    out_seed: Path,
    out_map: Path,
    duration_seconds: int,
    serial: str,
    case_start_offset: int = 0,
) -> None:
    cases = parse_cases(csv_path)
    if not cases:
        raise RuntimeError("No cases found in input CSV")

    total_slots = max(1, duration_seconds)
    base = datetime(2026, 3, 12, 10, 0, 0)

    eeprom_payload = build_eeprom_payload()
    lines: list[str] = []
    lines.append(f"[{base.strftime('%H:%M:%S.%f')[:-3]}]IN #EEPROM{serial}:{eeprom_payload}!")

    mapping_rows: list[dict] = []

    for i in range(total_slots):
        case = cases[(i + case_start_offset) % len(cases)]
        t_frame = base + timedelta(seconds=i)
        t_sensor = t_frame + timedelta(milliseconds=120)

        frame_payload = build_frame_payload(case["temp_c"])
        smoke_adc = pct_to_adc(case["smoke_pct"])
        flame_adc = pct_to_adc(case["flame_pct"])

        sensor_payload = (
            f"ADC1={smoke_adc},"
            f"ADC2={flame_adc},"
            f"Button=1,"
            f"MQ_IN={1 if case['smoke_pct'] >= 20.0 else 0},"
            f"MPY_IN={1 if case['flame_pct'] >= 10.0 else 0},"
            f"DIO_OUT={1 if case['expected_alarm'] == 'Y' else 0}"
        )

        lines.append(
            f"[{t_frame.strftime('%H:%M:%S.%f')[:-3]}]IN #frame{serial}:{frame_payload}!"
        )
        lines.append(
            f"[{t_sensor.strftime('%H:%M:%S.%f')[:-3]}]IN #Sensor{serial}:{sensor_payload}!"
        )

        mapping_rows.append(
            {
                "slot_second": i,
                "timestamp_frame": t_frame.strftime('%H:%M:%S.%f')[:-3],
                "test_case_id": case["case_id"],
                "temp_c": case["temp_c"],
                "smoke_pct": case["smoke_pct"],
                "flame_pct": case["flame_pct"],
                "expected_alarm": case["expected_alarm"],
                "description": case["description"],
            }
        )

    out_seed.parent.mkdir(parents=True, exist_ok=True)
    out_seed.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_map.parent.mkdir(parents=True, exist_ok=True)
    with out_map.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "slot_second",
            "timestamp_frame",
            "test_case_id",
            "temp_c",
            "smoke_pct",
            "flame_pct",
            "expected_alarm",
            "description",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(mapping_rows)


def generate_multi_instance_seeds(
    csv_path: Path,
    out_dir: Path,
    duration_seconds: int,
    instances: int,
    serial_prefix: str,
    serial_start: int,
    case_shift_step: int,
) -> list[tuple[Path, Path, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[tuple[Path, Path, str]] = []
    for i in range(instances):
        serial = serial_for_instance(serial_prefix, serial_start, i)
        seed_path = out_dir / f"emberhawk_fusion_seed_3min_inst{i + 1:03d}.txt"
        map_path = out_dir / f"emberhawk_fusion_seed_3min_inst{i + 1:03d}_map.csv"
        generate_seed(
            csv_path=csv_path,
            out_seed=seed_path,
            out_map=map_path,
            duration_seconds=duration_seconds,
            serial=serial,
            case_start_offset=i * max(0, case_shift_step),
        )
        created.append((seed_path, map_path, serial))
    return created


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(description="Generate 3-minute EmberHawk replay seed from fusion CSV")
    parser.add_argument(
        "--input-csv",
        default=str(repo_root / "tests" / "data" / "fusion_testcases_input.csv"),
        help="Fusion input CSV path",
    )
    parser.add_argument(
        "--out-seed",
        default=str(repo_root / "simulators" / "pfds" / "data" / "emberhawk_fusion_seed_3min.txt"),
        help="Output replay seed file path",
    )
    parser.add_argument(
        "--out-map",
        default=str(repo_root / "simulators" / "pfds" / "data" / "emberhawk_fusion_seed_3min_map.csv"),
        help="Output mapping CSV (timeline to test case)",
    )
    parser.add_argument("--duration-seconds", type=int, default=180, help="Total replay duration in seconds")
    parser.add_argument("--serial", default="1829602101142", help="Serial to stamp into packet names")
    parser.add_argument("--instances", type=int, default=1, help="Generate N per-instance seed files for load testing")
    parser.add_argument("--serial-prefix", default="EHWK", help="Serial prefix for multi-instance seed generation")
    parser.add_argument("--serial-start", type=int, default=1001, help="Starting numeric suffix for multi-instance serials")
    parser.add_argument("--case-shift-step", type=int, default=7, help="Case index shift applied between instances")
    parser.add_argument(
        "--out-dir",
        default=str(repo_root / "simulators" / "pfds" / "data"),
        help="Directory for multi-instance output files",
    )
    args = parser.parse_args()

    duration = max(1, int(args.duration_seconds))

    if int(args.instances) <= 1:
        generate_seed(
            csv_path=Path(args.input_csv),
            out_seed=Path(args.out_seed),
            out_map=Path(args.out_map),
            duration_seconds=duration,
            serial=str(args.serial),
        )

        print(f"Generated seed file: {args.out_seed}")
        print(f"Generated map file : {args.out_map}")
    else:
        created = generate_multi_instance_seeds(
            csv_path=Path(args.input_csv),
            out_dir=Path(args.out_dir),
            duration_seconds=duration,
            instances=int(args.instances),
            serial_prefix=str(args.serial_prefix),
            serial_start=int(args.serial_start),
            case_shift_step=int(args.case_shift_step),
        )
        print(f"Generated {len(created)} instance seed sets in: {args.out_dir}")
        for seed_path, map_path, serial in created:
            print(f"  serial={serial} seed={seed_path.name} map={map_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
