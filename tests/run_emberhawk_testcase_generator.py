#!/usr/bin/env python3
"""
EmberHawk Test Case Generator
==============================
Converts each row in ``tests/data/fusion_testcases_input.csv`` into the
equivalent EmberHawk simulator wire-format packets:

  * **Sensor packet** – ``#SensorTCxxx:ADC1=…,ADC2=…,Button=0,MQ_IN=0,MPY_IN=0,DIO_OUT=0!``
        - ADC1 encodes Flame%   (ADC1 = round(flame_pct   × 4095 / 100))
        - ADC2 encodes Smoke%   (ADC2 = round(smoke_pct  × 4095 / 100))
    - MPY_IN is always 0 here; these cases only exercise the *analog* flame path.

  * **Thermal frame packet** – ``#frameTCxxx:{3336_hex}!``
    - 24×32 pixel grid where every pixel is set to the test-case temperature.
    - Pixel encoding: raw = round((temp_c - 27.0) × 100); <0 → add 0x10000.
    - 3072-char grid hex + 264-char zero-filled EEPROM tail = 3336 chars total.

  * **Vision score** – NOT present in any hardware packet (it is the output of a
    CV model that runs on the thermal frame).  It is injected directly into
    ``frame_data`` as ``vision_score`` and flagged as "injected" in the output.

The script then parses those packets *exactly as main_window.py does*
(ADC → %, thermal hex → numpy float array) and feeds the result to
``FusionOrchestrator``.  Two output artefacts are written:

  tests/artifacts/emberhawk_testcase_packets.csv   – one row per test case, the
      two packet strings + all derived sensor values
  tests/artifacts/emberhawk_fusion_results.csv     – fusion outcome per case
  tests/artifacts/emberhawk_fusion_results.md      – human-readable summary
"""

import csv
import struct
import sys
from pathlib import Path

import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from embereye.core.fusion import FusionOrchestrator

# ── Paths ─────────────────────────────────────────────────────────────────────
INPUT_CSV = REPO_ROOT / "tests" / "data" / "fusion_testcases_input.csv"
ARTIFACTS = REPO_ROOT / "tests" / "artifacts"
OUT_PACKETS_CSV = ARTIFACTS / "emberhawk_testcase_packets.csv"
OUT_RESULTS_CSV = ARTIFACTS / "emberhawk_fusion_results.csv"
OUT_RESULTS_MD = ARTIFACTS / "emberhawk_fusion_results.md"

# ── Fusion config (matches run_fusion_regression.py defaults) ─────────────────
FUSION_CONFIG = {
    "temp_threshold": 40.0,
    "critical_temp_threshold": 60.0,
    "gas_ppm_threshold": 400.0,
    "smoke_threshold_pct": 25.0,
    "flame_threshold_pct": 25.0,
    "flame_active_value": 1,
    "vision_threshold": 0.7,
    "vision_confidence_weight": 0.5,
    "enable_temporal_fusion": False,
    "max_history": 100,
}


# ── EmberHawk packet helpers ──────────────────────────────────────────────────

def smoke_pct_to_adc2(smoke_pct: float) -> int:
    """Convert smoke percentage to 12-bit ADC2 value (inverts main_window logic)."""
    return max(0, min(4095, round(smoke_pct * 4095.0 / 100.0)))


def flame_pct_to_adc1(flame_pct: float) -> int:
    """Convert flame percentage to 12-bit ADC1 value (inverts main_window logic)."""
    return max(0, min(4095, round(flame_pct * 4095.0 / 100.0)))


def make_sensor_packet(serial: str, adc1: int, adc2: int, mpy_in: int = 0) -> str:
    """Build an EmberHawk sensor data packet string."""
    return (
        f"#Sensor{serial}:"
        f"ADC1={adc1},ADC2={adc2},"
        f"Button=0,MQ_IN=0,MPY_IN={mpy_in},DIO_OUT=0!"
    )


def celsius_to_raw_word(temp_c: float) -> int:
    """Convert °C to the 16-bit raw integer used in the EmberHawk frame payload."""
    raw = int(round((temp_c - 27.0) * 100.0))
    if raw < 0:
        raw += 0x10000
    return max(0, min(0xFFFF, raw))


def make_thermal_frame_packet(serial: str, temp_c: float) -> str:
    """
    Build a 3336-char EmberHawk thermal frame packet where every pixel
    in the 24×32 grid is set to *temp_c*.
    """
    pixel_word = celsius_to_raw_word(temp_c)
    pixel_hex = f"{pixel_word:04X}"
    # 768 pixels × 4 hex chars = 3072
    grid_hex = pixel_hex * 768
    # 66 EEPROM tail words × 4 hex chars = 264 (filled with zeros)
    eeprom_hex = "0000" * 66
    payload = grid_hex + eeprom_hex  # 3336 chars
    return f"#frame{serial}:{payload}!"


# ── Packet parsing (mirrors main_window.py logic) ────────────────────────────

def parse_sensor_packet(packet: str) -> dict:
    """
    Parse an EmberHawk sensor packet into a Python dict.
    Same field extraction as main_window.py (lines ~1697-1740).
    Returns keys: ADC1, ADC2, MPY_IN (raw integers).
    """
    import re
    result = {}
    body_match = re.search(r"#Sensor[^:]+:(.*?)!", packet)
    if not body_match:
        return result
    for part in body_match.group(1).split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            try:
                result[k.strip()] = int(v.strip())
            except ValueError:
                result[k.strip()] = v.strip()
    return result


def parse_thermal_frame_packet(packet: str) -> np.ndarray:
    """
    Decode an EmberHawk thermal frame packet into a 24×32 numpy float array (°C).
    Same decoding as the field app: raw → (raw - 27.0×100) / 100  with sign handling.
    """
    import re
    body_match = re.search(r"#frame[^:]+:(.*?)!", packet)
    if not body_match:
        return np.zeros((24, 32), dtype=float)
    payload = re.sub(r"[^0-9A-Fa-f]", "", body_match.group(1))
    # Take first 3072 chars = 768 pixel words
    grid_hex = payload[:3072]
    words = [grid_hex[i:i + 4] for i in range(0, 3072, 4)]
    temps = []
    for word in words:
        raw = int(word, 16) if word else 0
        if raw > 0x7FFF:
            raw -= 0x10000
        temps.append(raw / 100.0 + 27.0)
    return np.array(temps, dtype=float).reshape(24, 32)


def sensor_packet_to_frame_data(sensor_parsed: dict) -> dict:
    """
    Convert parsed sensor values to frame_data fields using the same
    arithmetic as main_window.py.
    """
    frame_data = {}
    adc1 = sensor_parsed.get("ADC1")
    adc2 = sensor_parsed.get("ADC2")
    mpy_in = sensor_parsed.get("MPY_IN", 0)

    if adc1 is not None:
        frame_data["flame_analog_pct"] = (adc1 * 100.0) / 4095.0

    if adc2 is not None:
        frame_data["smoke_pct"] = (adc2 * 100.0) / 4095.0
        # ADC2-derived gas (fallback, no explicit GAS_PPM in these test packets)
        frame_data["gas_ppm"] = (adc2 * 1500.0) / 4095.0

    frame_data["flame_digital"] = int(mpy_in)
    return frame_data


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> int:
    with INPUT_CSV.open("r", newline="", encoding="utf-8") as f:
        input_rows = list(csv.DictReader(f))

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    packet_rows = []
    result_rows = []

    for row in input_rows:
        case_id = int(float(row["Test Case"]))
        vision_score = float(row["Vision Score"])
        temp_c = float(row["Temp (°C)"])
        smoke_pct = float(row["Smoke (%)"])
        flame_pct = float(row["Flame (%)"])
        expected = (row.get("Expected Alarm (Provided)") or "").strip().upper()
        description = row.get("Description", "").strip()

        serial = f"TC{case_id:03d}"

        # ── 1. Generate EmberHawk packets ─────────────────────────────────────
        adc1 = flame_pct_to_adc1(flame_pct)
        adc2 = smoke_pct_to_adc2(smoke_pct)
        mpy_in = 0  # analog-only test cases

        sensor_pkt = make_sensor_packet(serial, adc1, adc2, mpy_in)
        thermal_pkt = make_thermal_frame_packet(serial, temp_c)

        # ── 2. Parse packets exactly as main_window.py would ──────────────────
        sensor_parsed = parse_sensor_packet(sensor_pkt)
        thermal_matrix = parse_thermal_frame_packet(thermal_pkt)

        frame_data = sensor_packet_to_frame_data(sensor_parsed)
        frame_data["thermal"] = thermal_matrix
        # Vision score is not in any hardware packet – injected from CV model
        frame_data["vision_score"] = vision_score

        # Derive back what the parsed smoke/flame % are (for verification column)
        parsed_smoke_pct = round(frame_data.get("smoke_pct", 0.0), 4)
        parsed_flame_pct = round(frame_data.get("flame_analog_pct", 0.0), 4)
        parsed_temp = round(float(np.max(thermal_matrix)), 4)

        packet_rows.append({
            "Test Case": case_id,
            "Serial": serial,
            "Sensor Packet": sensor_pkt,
            "Thermal Frame Packet (truncated)": thermal_pkt[:60] + "…",
            "Input Smoke (%)": smoke_pct,
            "Input Flame (%)": flame_pct,
            "Input Temp (°C)": temp_c,
            "ADC1 (derived)": adc1,
            "ADC2 (derived)": adc2,
            "MPY_IN": mpy_in,
            "Parsed Smoke (%)": parsed_smoke_pct,
            "Parsed Flame (%)": parsed_flame_pct,
            "Parsed Max Temp (°C)": parsed_temp,
            "Vision Score (injected)": vision_score,
            "Description": description,
        })

        # ── 3. Run fusion (fresh orchestrator per case – no temporal carry-over) ──
        orchestrator = FusionOrchestrator(FUSION_CONFIG)
        result = orchestrator.process_frame(frame_data)

        actual_alarm = "Y" if result.alarm else "N"
        match = "PASS" if actual_alarm == expected else "FAIL"

        sources = [
            ("flame" if d.source.name.startswith("FLAME") else d.source.name.lower())
            for d in result.detections
        ]

        result_rows.append({
            "Test Case": case_id,
            "Serial": serial,
            "Input Vision": vision_score,
            "Input Temp (°C)": temp_c,
            "Input Smoke (%)": smoke_pct,
            "Input Flame (%)": flame_pct,
            "ADC1": adc1,
            "ADC2": adc2,
            "Expected Alarm": expected,
            "Actual Alarm": actual_alarm,
            "Match?": match,
            "Severity": result.severity.name,
            "Confidence": round(float(result.confidence), 4),
            "Sources": ";".join(sources),
            "Reason": (result.metadata or {}).get("reason") or "",
            "Description": description,
        })

    # ── Write packets CSV ─────────────────────────────────────────────────────
    packet_fields = [
        "Test Case", "Serial", "Sensor Packet", "Thermal Frame Packet (truncated)",
        "Input Smoke (%)", "Input Flame (%)", "Input Temp (°C)",
        "ADC1 (derived)", "ADC2 (derived)", "MPY_IN",
        "Parsed Smoke (%)", "Parsed Flame (%)", "Parsed Max Temp (°C)",
        "Vision Score (injected)", "Description",
    ]
    with OUT_PACKETS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=packet_fields)
        w.writeheader()
        w.writerows(packet_rows)

    # ── Write results CSV ─────────────────────────────────────────────────────
    result_fields = [
        "Test Case", "Serial",
        "Input Vision", "Input Temp (°C)", "Input Smoke (%)", "Input Flame (%)",
        "ADC1", "ADC2",
        "Expected Alarm", "Actual Alarm", "Match?",
        "Severity", "Confidence", "Sources", "Reason", "Description",
    ]
    with OUT_RESULTS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=result_fields)
        w.writeheader()
        w.writerows(result_rows)

    # ── Write Markdown summary ────────────────────────────────────────────────
    n_total = len(result_rows)
    n_pass = sum(1 for r in result_rows if r["Match?"] == "PASS")
    n_fail = n_total - n_pass
    fail_cases = [r for r in result_rows if r["Match?"] == "FAIL"]

    md = [
        "# EmberHawk Fusion Test Case Results",
        "",
        "Each CSV test case was converted to EmberHawk wire-format packets and fed",
        "through `FusionOrchestrator` using the same parsing path as the field app.",
        "",
        "## Packet mapping",
        "",
        "| Input field | EmberHawk packet | Field app conversion |",
        "|---|---|---|",
        "| Smoke (%) | `ADC2 = round(smoke% × 4095/100)` in `#SensorTCxxx:…` | `smoke_pct = ADC2 × 100/4095` |",
        "| Flame (%) | `ADC1 = round(flame% × 4095/100)` in `#SensorTCxxx:…` | `flame_analog_pct = ADC1 × 100/4095` |",
        "| Temp (°C) | 24×32 uniform grid in `#frameTCxxx:…` | `thermal = np.ndarray(24,32)`, max used for threshold |",
        "| Vision Score | *Not in HW packets* | Injected directly as `vision_score` (output of CV model) |",
        "",
        f"## Summary: **{n_pass}/{n_total}** PASS, **{n_fail}** FAIL",
        "",
    ]

    if fail_cases:
        md += [
            "## Mismatches",
            "",
            "| TC | Exp | Actual | Severity | Sources | Reason |",
            "|---:|:---:|:---:|:---:|---|---|",
        ]
        for r in fail_cases:
            md.append(
                f"| {r['Test Case']} | {r['Expected Alarm']} | {r['Actual Alarm']}"
                f" | {r['Severity']} | {r['Sources']}"
                f" | {r['Reason'].replace('|', '/')} |"
            )
        md.append("")

    md += [
        "## Case-by-Case Results",
        "",
        "| TC | Vision | Temp | Smoke% | Flame% | ADC1 | ADC2 | Exp | Actual | Match | Severity | Reason |",
        "|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---|",
    ]
    for r in result_rows:
        md.append(
            f"| {r['Test Case']}"
            f" | {r['Input Vision']}"
            f" | {r['Input Temp (°C)']}"
            f" | {r['Input Smoke (%)']}"
            f" | {r['Input Flame (%)']}"
            f" | {r['ADC1']}"
            f" | {r['ADC2']}"
            f" | {r['Expected Alarm']}"
            f" | {r['Actual Alarm']}"
            f" | {r['Match?']}"
            f" | {r['Severity']}"
            f" | {r['Reason'].replace('|', '/')} |"
        )

    OUT_RESULTS_MD.write_text("\n".join(md), encoding="utf-8")

    # ── Console summary ───────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  EmberHawk Fusion Test Case Generator")
    print(f"{'='*72}")
    print(f"  Input:   {INPUT_CSV}")
    print(f"  Packets: {OUT_PACKETS_CSV}")
    print(f"  Results: {OUT_RESULTS_CSV}")
    print(f"  Report:  {OUT_RESULTS_MD}")
    print(f"{'='*72}")
    print(f"  Total: {n_total}  |  PASS: {n_pass}  |  FAIL: {n_fail}")
    print(f"{'='*72}\n")

    print(f"  {'TC':>4}  {'Exp':>4}  {'Act':>4}  {'Match':>6}  Reason")
    print(f"  {'-'*68}")
    for r in result_rows:
        flag = "  <-- FAIL" if r["Match?"] == "FAIL" else ""
        reason_short = r["Reason"][:52] if r["Reason"] else "(no alarm)"
        print(f"  {r['Test Case']:>4}  {r['Expected Alarm']:>4}  {r['Actual Alarm']:>4}  {r['Match?']:>6}  {reason_short}{flag}")

    print()
    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(run())
