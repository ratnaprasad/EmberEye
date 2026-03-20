#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stream_config import StreamConfig  # noqa: E402


def _read_scheduled_reconcile_count(telemetry_path: Path) -> Tuple[int, int]:
    if not telemetry_path.exists():
        return 0, 0
    count = 0
    rows = 0
    try:
        for line in telemetry_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("event") == "scheduled_reconcile_run":
                count += 1
    except Exception:
        return 0, rows
    return count, rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rollback drill for scheduled reconcile disablement")
    parser.add_argument(
        "--restart-cmd",
        default="",
        help="Optional app restart command (e.g. 'bash scripts/runtime/start_studio.sh').",
    )
    parser.add_argument(
        "--observe-seconds",
        type=int,
        default=15,
        help="Seconds to observe telemetry after disable/restart.",
    )
    parser.add_argument(
        "--restore-original",
        action="store_true",
        help="Restore the original reconcile_schedule_enabled value after drill.",
    )
    parser.add_argument(
        "--report-json",
        default=str(REPO_ROOT / "tests" / "artifacts" / "rollback_drill_report.json"),
        help="Path for rollback drill report JSON.",
    )
    return parser.parse_args()


def _run_restart(cmd: str) -> Tuple[bool, str]:
    if not cmd.strip():
        return True, "restart skipped (no --restart-cmd provided)"
    try:
        completed = subprocess.run(
            shlex.split(cmd),
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=120,
        )
        ok = completed.returncode == 0
        detail = (
            f"restart rc={completed.returncode} "
            f"stdout_tail={completed.stdout[-300:].strip()} stderr_tail={completed.stderr[-300:].strip()}"
        )
        return ok, detail
    except Exception as exc:
        return False, f"restart exception: {exc}"


def main() -> int:
    args = _parse_args()
    telemetry_path = REPO_ROOT / "logs" / "device_telemetry.jsonl"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": "FAIL",
        "steps": [],
    }

    config = StreamConfig.load_config()
    original_flag = bool(config.get("reconcile_schedule_enabled", False))

    before_count, before_rows = _read_scheduled_reconcile_count(telemetry_path)
    report["steps"].append(
        {
            "name": "baseline_telemetry",
            "ok": True,
            "detail": f"scheduled_reconcile_run_count={before_count} rows={before_rows}",
        }
    )

    saved_ok = False
    try:
        config["reconcile_schedule_enabled"] = False
        saved_ok = bool(StreamConfig.save_config(config))
        report["steps"].append(
            {
                "name": "disable_reconcile_schedule",
                "ok": saved_ok,
                "detail": "set reconcile_schedule_enabled=false",
            }
        )

        restart_ok, restart_detail = _run_restart(args.restart_cmd)
        report["steps"].append(
            {
                "name": "restart_app_hook",
                "ok": restart_ok,
                "detail": restart_detail,
            }
        )

        observe_seconds = max(1, int(args.observe_seconds))
        time.sleep(observe_seconds)

        after_count, after_rows = _read_scheduled_reconcile_count(telemetry_path)
        delta = after_count - before_count
        no_new_runs = delta <= 0
        report["steps"].append(
            {
                "name": "verify_no_new_scheduled_reconcile_events",
                "ok": no_new_runs,
                "detail": (
                    f"before={before_count} after={after_count} delta={delta} "
                    f"observe_seconds={observe_seconds} rows_before={before_rows} rows_after={after_rows}"
                ),
            }
        )

        overall_ok = all(bool(step.get("ok", False)) for step in report["steps"])
        report["decision"] = "PASS" if overall_ok else "FAIL"
    finally:
        if args.restore_original:
            restore_cfg = StreamConfig.load_config()
            restore_cfg["reconcile_schedule_enabled"] = original_flag
            restored = bool(StreamConfig.save_config(restore_cfg))
            report["steps"].append(
                {
                    "name": "restore_original_config",
                    "ok": restored,
                    "detail": f"reconcile_schedule_enabled restored to {original_flag}",
                }
            )
            if report["decision"] == "PASS" and not restored:
                report["decision"] = "FAIL"

    out_path = Path(args.report_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"ROLLBACK_DRILL_DECISION: {report['decision']}")
    for step in report["steps"]:
        status = "PASS" if step.get("ok") else "FAIL"
        print(f"[{status}] {step.get('name')} :: {step.get('detail')}")
    print(f"REPORT_JSON: {out_path}")

    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
