import subprocess
import sys
from pathlib import Path

from _test_utils import get_log_path, log_line


def _run(script: Path, log_path: Path) -> int:
    log_line(log_path, f"[RUN] {script.name}")
    result = subprocess.run([sys.executable, str(script)], cwd=str(script.parent.parent.parent))
    return result.returncode


def main() -> int:
    log_path = get_log_path("all_field_tests")
    root = Path(__file__).resolve().parent
    scripts = [
        root / "run_smoke_test.py",
        root / "run_rtsp_pipeline_test.py",
        root / "run_ui_toggle_test.py",
        root / "run_hybrid_alarm_test.py",
        root / "run_threshold_config_test.py",
        root / "run_multi_camera_grid_test.py",
        root / "run_pfds_integration_test.py",
        root / "run_tcp_server_test.py",
    ]

    for script in scripts:
        if not script.exists():
            log_line(log_path, f"ERROR: Missing {script}")
            return 1
        code = _run(script, log_path)
        if code != 0:
            log_line(log_path, f"FAILED: {script.name}")
            return code

    log_line(log_path, "All Field tests completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
