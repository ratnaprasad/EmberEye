#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "logs"
ARTIFACTS_DIR = REPO_ROOT / "tests" / "artifacts"

REQUIRED_TEST_SCRIPTS = [
    "tests/field/run_device_access_audit_test.py",
    "tests/field/run_bulk_reconcile_test.py",
    "tests/field/run_bulk_reconcile_dry_run_test.py",
    "tests/field/run_device_gating_matrix_test.py",
    "tests/field/run_pfds_tcp_fusion_e2e_test.py",
    "tests/field/run_identity_churn_soak_test.py",
    "tests/smoke_simulator_commands.py",
]


@dataclass
class GateCheck:
    name: str
    passed: bool
    detail: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Release readiness gate runner for Phase C/Phase D operations governance"
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip running required regression scripts")
    parser.add_argument(
        "--metrics-url",
        default="http://127.0.0.1:9108/metrics",
        help="Prometheus metrics endpoint URL",
    )
    parser.add_argument(
        "--allow-missing-metrics",
        action="store_true",
        help="Do not fail gate if metrics endpoint is unreachable",
    )
    parser.add_argument(
        "--telemetry-window-hours",
        type=float,
        default=1.0,
        help="Lookback window for ops alert rate from device telemetry log",
    )
    parser.add_argument(
        "--max-ops-alerts-per-hour",
        type=float,
        default=2.0,
        help="Maximum allowed ops_alert events per hour",
    )
    parser.add_argument(
        "--max-unmatched-ratio",
        type=float,
        default=0.10,
        help="Maximum allowed scheduled unmatched ratio",
    )
    parser.add_argument(
        "--max-command-failure-ratio",
        type=float,
        default=0.01,
        help="Maximum allowed command failure ratio",
    )
    parser.add_argument(
        "--report-json",
        default=str(ARTIFACTS_DIR / "release_readiness_report.json"),
        help="Path for JSON report output",
    )
    return parser.parse_args()


def _run_required_tests() -> List[GateCheck]:
    checks: List[GateCheck] = []
    for script in REQUIRED_TEST_SCRIPTS:
        cmd = [sys.executable, script]
        completed = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
        )
        passed = completed.returncode == 0
        detail = "PASS"
        if not passed:
            detail = (
                f"FAIL rc={completed.returncode} stdout={completed.stdout[-350:].strip()} "
                f"stderr={completed.stderr[-350:].strip()}"
            )
        checks.append(GateCheck(name=f"test:{script}", passed=passed, detail=detail))
    return checks


def _fetch_metrics_text(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        with urllib.request.urlopen(url, timeout=4.0) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except Exception as exc:
        return None, str(exc)


def _parse_metric_samples(metrics_text: str) -> List[Tuple[str, Dict[str, str], float]]:
    samples: List[Tuple[str, Dict[str, str], float]] = []
    line_re = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+]?\d+(?:\.\d+)?)$")
    label_re = re.compile(r'(\w+)="([^"]*)"')

    for raw in metrics_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = line_re.match(line)
        if not m:
            continue

        metric_name = m.group(1)
        label_blob = m.group(2) or ""
        value = float(m.group(3))
        labels: Dict[str, str] = {}
        if label_blob:
            for lm in label_re.finditer(label_blob):
                labels[lm.group(1)] = lm.group(2)
        samples.append((metric_name, labels, value))

    return samples


def _sum_metric(
    samples: List[Tuple[str, Dict[str, str], float]],
    metric_name: str,
    required_labels: Optional[Dict[str, str]] = None,
) -> float:
    total = 0.0
    for name, labels, value in samples:
        if name != metric_name:
            continue
        if required_labels:
            mismatch = False
            for k, v in required_labels.items():
                if labels.get(k) != v:
                    mismatch = True
                    break
            if mismatch:
                continue
        total += value
    return total


def _parse_iso8601_z(ts: str) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw[:-1]).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    except Exception:
        return rows
    return rows


def _evaluate_logs(window_hours: float, max_ops_alert_rate: float) -> List[GateCheck]:
    checks: List[GateCheck] = []

    telemetry_path = LOG_DIR / "device_telemetry.jsonl"
    audit_path = LOG_DIR / "device_audit.jsonl"

    telemetry_rows = _read_jsonl(telemetry_path)
    audit_rows = _read_jsonl(audit_path)

    checks.append(
        GateCheck(
            name="log:device_telemetry_present",
            passed=len(telemetry_rows) > 0,
            detail=f"rows={len(telemetry_rows)} path={telemetry_path}",
        )
    )

    checks.append(
        GateCheck(
            name="log:device_audit_present",
            passed=len(audit_rows) > 0,
            detail=f"rows={len(audit_rows)} path={audit_path}",
        )
    )

    # Audit field sanity check
    audit_ok = False
    for row in reversed(audit_rows):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if row.get("event") != "device_access_changed":
            continue
        required = ["actor", "reason", "old_is_authorized", "new_is_authorized", "old_is_linked", "new_is_linked"]
        if all(k in payload for k in required):
            audit_ok = True
            break

    checks.append(
        GateCheck(
            name="log:audit_schema_sane",
            passed=audit_ok,
            detail="requires actor/reason + old/new auth/link fields on device_access_changed",
        )
    )

    # Ops alert rate over lookback window.
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=max(0.01, window_hours))
    ops_alert_count = 0
    for row in telemetry_rows:
        if row.get("event") != "ops_alert":
            continue
        ts = _parse_iso8601_z(str(row.get("timestamp") or ""))
        if ts and ts >= window_start:
            ops_alert_count += 1

    ops_rate = ops_alert_count / max(0.01, window_hours)
    checks.append(
        GateCheck(
            name="slo:ops_alert_rate",
            passed=ops_rate <= max_ops_alert_rate,
            detail=(
                f"ops_alert_count={ops_alert_count} window_hours={window_hours:.2f} "
                f"rate_per_hour={ops_rate:.2f} threshold={max_ops_alert_rate:.2f}"
            ),
        )
    )

    return checks


def _evaluate_metrics(
    metrics_text: str,
    max_unmatched_ratio: float,
    max_command_failure_ratio: float,
) -> List[GateCheck]:
    checks: List[GateCheck] = []
    samples = _parse_metric_samples(metrics_text)

    sched_errors = _sum_metric(samples, "embereye_scheduled_reconcile_errors_total")
    sched_disabled = _sum_metric(samples, "embereye_scheduled_reconcile_disabled_total")
    sched_unmatched = _sum_metric(samples, "embereye_scheduled_reconcile_unmatched_total")
    sched_bound = _sum_metric(samples, "embereye_scheduled_reconcile_bound_total")

    # Approximate attempted from bound + unmatched in counters.
    attempted = sched_bound + sched_unmatched
    unmatched_ratio = (sched_unmatched / attempted) if attempted > 0 else 0.0

    cmd_sent = _sum_metric(samples, "embereye_device_commands_total", {"event": "command_sent"})
    cmd_failed = _sum_metric(samples, "embereye_device_commands_total", {"event": "command_failed"})
    cmd_total = cmd_sent + cmd_failed
    cmd_failure_ratio = (cmd_failed / cmd_total) if cmd_total > 0 else 0.0

    checks.append(
        GateCheck(
            name="slo:scheduled_reconcile_errors",
            passed=sched_errors <= 0.0,
            detail=f"value={sched_errors:.0f} expected=0",
        )
    )

    checks.append(
        GateCheck(
            name="slo:scheduled_reconcile_disabled",
            passed=sched_disabled <= 0.0,
            detail=f"value={sched_disabled:.0f} expected=0",
        )
    )

    checks.append(
        GateCheck(
            name="slo:scheduled_unmatched_ratio",
            passed=unmatched_ratio <= max_unmatched_ratio,
            detail=(
                f"unmatched={sched_unmatched:.0f} attempted={attempted:.0f} "
                f"ratio={unmatched_ratio:.4f} threshold={max_unmatched_ratio:.4f}"
            ),
        )
    )

    checks.append(
        GateCheck(
            name="slo:command_failure_ratio",
            passed=cmd_failure_ratio <= max_command_failure_ratio,
            detail=(
                f"failed={cmd_failed:.0f} sent={cmd_sent:.0f} total={cmd_total:.0f} "
                f"ratio={cmd_failure_ratio:.4f} threshold={max_command_failure_ratio:.4f}"
            ),
        )
    )

    return checks


def _write_report(path: Path, checks: List[GateCheck], go: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": "GO" if go else "NO-GO",
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in checks
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    checks: List[GateCheck] = []

    if not args.skip_tests:
        checks.extend(_run_required_tests())

    metrics_text, metrics_err = _fetch_metrics_text(args.metrics_url)
    if metrics_text is None:
        checks.append(
            GateCheck(
                name="metrics:endpoint_reachable",
                passed=bool(args.allow_missing_metrics),
                detail=f"unreachable url={args.metrics_url} error={metrics_err}",
            )
        )
    else:
        checks.append(
            GateCheck(
                name="metrics:endpoint_reachable",
                passed=True,
                detail=f"url={args.metrics_url} bytes={len(metrics_text)}",
            )
        )
        checks.extend(
            _evaluate_metrics(
                metrics_text=metrics_text,
                max_unmatched_ratio=float(args.max_unmatched_ratio),
                max_command_failure_ratio=float(args.max_command_failure_ratio),
            )
        )

    checks.extend(
        _evaluate_logs(
            window_hours=float(args.telemetry_window_hours),
            max_ops_alert_rate=float(args.max_ops_alerts_per_hour),
        )
    )

    go = all(c.passed for c in checks)
    _write_report(Path(args.report_json), checks, go)

    print("RELEASE_READINESS_DECISION:", "GO" if go else "NO-GO")
    for c in checks:
        state = "PASS" if c.passed else "FAIL"
        print(f"[{state}] {c.name} :: {c.detail}")
    print(f"REPORT_JSON: {args.report_json}")

    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
