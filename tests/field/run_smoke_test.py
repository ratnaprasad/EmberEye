import subprocess
import sys
import time
from pathlib import Path

from _test_utils import get_log_path, log_line, capture_text_screenshot


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    app_path = root / "embereye-field" / "main.py"
    log_path = get_log_path("smoke_test")

    if not app_path.exists():
        log_line(log_path, f"ERROR: Field app not found at {app_path}")
        return 1

    duration = 8.0
    log_line(log_path, f"[SMOKE] Launching Field app for {duration:.1f}s")

    proc = subprocess.Popen(
        [sys.executable, str(app_path)],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(duration)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    capture_text_screenshot(
        "smoke_test",
        f"Smoke test completed\nDuration: {duration:.1f}s",
        log_path,
    )
    log_line(log_path, "[SMOKE] Completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
