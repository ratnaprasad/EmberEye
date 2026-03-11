#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from embereye.core.fusion import DetectionSource, FusionOrchestrator


def intended_alarm(vision: float, temp: float, smoke: float, flame: float):
    if temp >= 60.0 or smoke >= 20.0 or flame >= 20.0:
        return "Y", "independent_trigger"

    if vision >= 0.70:
        return "Y", "vision>=0.70"

    if 0.50 <= vision < 0.70:
        if temp > 50.0 and flame >= 10.0:
            return "Y", "0.50<=vision<0.70 and temp>50 and flame>=10"
        return "N", "0.50<=vision<0.70 but temp/flame condition failed"

    if 0.30 <= vision < 0.50:
        if temp > 50.0 and flame >= 10.0:
            return "Y", "0.30<=vision<0.50 and temp>50 and flame>=10"
        return "N", "0.30<=vision<0.50 but temp/flame condition failed"

    if temp > 50.0 and flame >= 10.0:
        return "Y", "vision<0.30 and temp>50 and flame>=10"
    return "N", "vision<0.30 and temp/flame condition failed"


def run_regression():
    repo_root = REPO_ROOT
    data_csv = repo_root / "tests" / "data" / "fusion_testcases_input.csv"
    out_actual_csv = repo_root / "tests" / "artifacts" / "fusion_testcase_results.csv"
    out_actual_md = repo_root / "tests" / "artifacts" / "fusion_testcase_results.md"
    out_compare_csv = repo_root / "tests" / "artifacts" / "fusion_testcase_intended_vs_actual.csv"
    out_compare_md = repo_root / "tests" / "artifacts" / "fusion_testcase_intended_vs_actual.md"

    config = {
        "temp_threshold": 40.0,
        "critical_temp_threshold": 60.0,
        "gas_ppm_threshold": 400.0,
        "smoke_threshold_pct": 25.0,
        "flame_threshold_pct": 25.0,
        "flame_active_value": 1,
        "vision_threshold": 0.7,
        "vision_confidence_weight": 0.5,
        "enable_temporal_fusion": False,
    }

    fusion = FusionOrchestrator(config)

    with data_csv.open("r", newline="", encoding="utf-8") as f:
        input_rows = list(csv.DictReader(f))

    actual_rows = []
    compare_rows = []

    for row in input_rows:
        case_id = int(float(row["Test Case"]))
        vision = float(row["Vision Score"])
        temp = float(row["Temp (°C)"])
        smoke = float(row["Smoke (%)"])
        flame = float(row["Flame (%)"])
        expected = (row.get("Expected Alarm (Provided)", "") or "").strip().upper()
        description = row.get("Description", "")

        frame_data = {
            "thermal": np.full((24, 32), temp, dtype=float),
            "vision_score": vision,
            "smoke_pct": smoke,
            "flame_analog_pct": flame,
        }

        result = fusion.process_frame(frame_data)
        actual_alarm = "Y" if result.alarm else "N"

        source_names = []
        for detection in result.detections:
            if detection.source in (DetectionSource.FLAME_ANALOG, DetectionSource.FLAME_DIGITAL):
                source_names.append("flame")
            else:
                source_names.append(detection.source.name.lower())

        independent_actual = (
            temp >= config["critical_temp_threshold"]
            or smoke >= config["smoke_threshold_pct"]
            or flame >= config["flame_threshold_pct"]
        )

        why_no_alarm = ""
        if actual_alarm == "N":
            if (
                result.severity.name == "NONE"
                and "thermal" in source_names
                and not any(name in source_names for name in ["smoke", "flame", "gas", "vision"])
            ):
                why_no_alarm = (
                    "Thermal detected (>= temp threshold) but not critical (< critical temp) and no "
                    "smoke/flame/gas/vision-qualified correlation trigger."
                )
            elif result.severity.name == "NONE":
                why_no_alarm = "No fusion rule set alarm=true for this source combination."
            else:
                why_no_alarm = "Alarm remains false under current fusion decision path."

        actual_row = {
            "Test Case": case_id,
            "Vision Score": vision,
            "Temp (°C)": temp,
            "Smoke (%)": smoke,
            "Flame (%)": flame,
            "Expected Alarm (Provided)": expected,
            "Actual Alarm (Current Logic)": actual_alarm,
            "Match?": "PASS" if expected == actual_alarm else "FAIL",
            "Actual Severity": result.severity.name,
            "Actual Confidence": round(float(result.confidence), 4),
            "Actual Sources": ";".join(source_names),
            "Actual Independent Trigger? (60/25/25)": "Y" if independent_actual else "N",
            "Actual Reason": (result.metadata or {}).get("reason") or "",
            "Description": description,
            "Why Alarm=N (Current Logic)": why_no_alarm,
        }
        actual_rows.append(actual_row)

        intended, intended_path = intended_alarm(vision, temp, smoke, flame)
        compare_rows.append(
            {
                "Test Case": case_id,
                "Vision Score": vision,
                "Temp (°C)": temp,
                "Smoke (%)": smoke,
                "Flame (%)": flame,
                "Expected Alarm (Provided)": expected,
                "Expected Alarm (Intended Rules)": intended,
                "Actual Alarm (Current Logic)": actual_alarm,
                "Provided vs Intended": "PASS" if expected == intended else "FAIL",
                "Intended vs Actual": "PASS" if intended == actual_alarm else "FAIL",
                "Intended Rule Path": intended_path,
                "Actual Reason": actual_row["Actual Reason"],
                "Description": description,
            }
        )

    out_actual_csv.parent.mkdir(parents=True, exist_ok=True)

    actual_fields = [
        "Test Case",
        "Vision Score",
        "Temp (°C)",
        "Smoke (%)",
        "Flame (%)",
        "Expected Alarm (Provided)",
        "Actual Alarm (Current Logic)",
        "Match?",
        "Actual Severity",
        "Actual Confidence",
        "Actual Sources",
        "Actual Independent Trigger? (60/25/25)",
        "Actual Reason",
        "Description",
        "Why Alarm=N (Current Logic)",
    ]

    with out_actual_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=actual_fields)
        writer.writeheader()
        writer.writerows(actual_rows)

    actual_fail = [r for r in actual_rows if r["Match?"] == "FAIL"]
    actual_pass_count = len(actual_rows) - len(actual_fail)

    md_actual = [
        "# Fusion Regression Results (Actual Current Logic)",
        "",
        "- Logic source: `FusionOrchestrator` + detectors (unchanged).",
        "- Config used: temp>=40 detect, critical temp>=60 override, smoke>=25, flame>=25, vision>=0.7 gate, temporal fusion disabled.",
        f"- Summary: **{actual_pass_count}/{len(actual_rows)}** match your provided expected column; **{len(actual_fail)}** mismatches.",
        "",
    ]

    if actual_fail:
        md_actual.extend(
            [
                "## Mismatches",
                "",
                "| Test Case | Provided | Actual | Severity | Sources | Why Alarm=N (if N) | Reason |",
                "|---:|:---:|:---:|:---:|---|---|---|",
            ]
        )
        for r in actual_fail:
            md_actual.append(
                f"| {r['Test Case']} | {r['Expected Alarm (Provided)']} | {r['Actual Alarm (Current Logic)']} | {r['Actual Severity']} | {r['Actual Sources']} | {r['Why Alarm=N (Current Logic)'].replace('|', '/')} | {r['Actual Reason'].replace('|', '/')} |"
            )
        md_actual.append("")

    md_actual.extend(
        [
            "## Full Results",
            "",
            "| Test Case | Vision | Temp | Smoke | Flame | Provided | Actual | Match | Severity | Confidence | Sources | Why Alarm=N (if N) |",
            "|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---:|---|---|",
        ]
    )
    for r in actual_rows:
        md_actual.append(
            f"| {r['Test Case']} | {r['Vision Score']} | {r['Temp (°C)']} | {r['Smoke (%)']} | {r['Flame (%)']} | {r['Expected Alarm (Provided)']} | {r['Actual Alarm (Current Logic)']} | {r['Match?']} | {r['Actual Severity']} | {r['Actual Confidence']} | {r['Actual Sources']} | {r['Why Alarm=N (Current Logic)'].replace('|', '/')} |"
        )

    out_actual_md.write_text("\n".join(md_actual), encoding="utf-8")

    compare_fields = [
        "Test Case",
        "Vision Score",
        "Temp (°C)",
        "Smoke (%)",
        "Flame (%)",
        "Expected Alarm (Provided)",
        "Expected Alarm (Intended Rules)",
        "Actual Alarm (Current Logic)",
        "Provided vs Intended",
        "Intended vs Actual",
        "Intended Rule Path",
        "Actual Reason",
        "Description",
    ]

    with out_compare_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=compare_fields)
        writer.writeheader()
        writer.writerows(compare_rows)

    pvi_fail = [r for r in compare_rows if r["Provided vs Intended"] == "FAIL"]
    iva_fail = [r for r in compare_rows if r["Intended vs Actual"] == "FAIL"]

    md_compare = [
        "# Fusion Intended Rules vs Actual Logic",
        "",
        "- Intended rules are taken from your regression specification (independent 60/20/20 + vision-banded conditions).",
        f"- Provided vs Intended mismatches: **{len(pvi_fail)}**",
        f"- Intended vs Actual mismatches: **{len(iva_fail)}**",
        "",
    ]

    if pvi_fail:
        md_compare.extend(
            [
                "## Provided vs Intended Mismatches",
                "",
                "| Test Case | Provided | Intended | Rule Path | Description |",
                "|---:|:---:|:---:|---|---|",
            ]
        )
        for r in pvi_fail:
            md_compare.append(
                f"| {r['Test Case']} | {r['Expected Alarm (Provided)']} | {r['Expected Alarm (Intended Rules)']} | {r['Intended Rule Path']} | {r['Description'].replace('|', '/')} |"
            )
        md_compare.append("")

    if iva_fail:
        md_compare.extend(
            [
                "## Intended vs Actual Mismatches",
                "",
                "| Test Case | Intended | Actual | Rule Path | Actual Reason |",
                "|---:|:---:|:---:|---|---|",
            ]
        )
        for r in iva_fail:
            md_compare.append(
                f"| {r['Test Case']} | {r['Expected Alarm (Intended Rules)']} | {r['Actual Alarm (Current Logic)']} | {r['Intended Rule Path']} | {(r['Actual Reason'] or '').replace('|', '/')} |"
            )
        md_compare.append("")

    md_compare.extend(
        [
            "## Full Table",
            "",
            "| Test Case | Vision | Temp | Smoke | Flame | Provided | Intended | Actual | PvsI | IvsA | Rule Path |",
            "|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|:---:|---|",
        ]
    )
    for r in compare_rows:
        md_compare.append(
            f"| {r['Test Case']} | {r['Vision Score']} | {r['Temp (°C)']} | {r['Smoke (%)']} | {r['Flame (%)']} | {r['Expected Alarm (Provided)']} | {r['Expected Alarm (Intended Rules)']} | {r['Actual Alarm (Current Logic)']} | {r['Provided vs Intended']} | {r['Intended vs Actual']} | {r['Intended Rule Path']} |"
        )

    out_compare_md.write_text("\n".join(md_compare), encoding="utf-8")

    print(f"Input cases: {len(input_rows)}")
    print(f"Actual behavior matches provided: {actual_pass_count}/{len(actual_rows)}")
    print(f"Intended-vs-actual mismatches: {len(iva_fail)}")
    print(f"Wrote: {out_actual_csv}")
    print(f"Wrote: {out_actual_md}")
    print(f"Wrote: {out_compare_csv}")
    print(f"Wrote: {out_compare_md}")


if __name__ == "__main__":
    run_regression()
