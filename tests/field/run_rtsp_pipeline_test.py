import socket
import subprocess
import sys
import time
from pathlib import Path

from _test_utils import get_log_path, log_line, capture_text_screenshot


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    mediamtx_exe = root / "simulators" / "rtsp" / "mediamtx" / "mediamtx.exe"
    simulator_script = root / "simulators" / "rtsp" / "rtsp_camera_simulator.py"
    video_file = root / "simulators" / "rtsp" / "data" / "IMG_1318.MOV"
    app_path = root / "embereye-field" / "main.py"

    log_path = get_log_path("rtsp_pipeline")

    if not mediamtx_exe.exists():
        log_line(log_path, f"ERROR: MediaMTX not found at {mediamtx_exe}")
        return 1
    if not simulator_script.exists():
        log_line(log_path, f"ERROR: RTSP simulator not found at {simulator_script}")
        return 1
    if not video_file.exists():
        log_line(log_path, f"ERROR: Video file not found at {video_file}")
        return 1
    if not app_path.exists():
        log_line(log_path, f"ERROR: Field app not found at {app_path}")
        return 1

    procs = []
    try:
        log_line(log_path, "[RTSP] Starting MediaMTX")
        mediamtx_proc = subprocess.Popen(
            [str(mediamtx_exe)],
            cwd=str(mediamtx_exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(mediamtx_proc)

        if not _wait_for_port("127.0.0.1", 8554, timeout=10.0):
            log_line(log_path, "ERROR: MediaMTX did not open port 8554")
            return 1

        log_line(log_path, "[RTSP] Starting simulator")
        sim_proc = subprocess.Popen(
            [sys.executable, str(simulator_script), "--video", str(video_file)],
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(sim_proc)

        log_line(log_path, "[RTSP] Launching Field app")
        app_proc = subprocess.Popen(
            [sys.executable, str(app_path)],
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(app_proc)

        duration = 12.0
        log_line(log_path, f"[RTSP] Running for {duration:.1f}s")
        time.sleep(duration)

        capture_text_screenshot(
            "rtsp_pipeline",
            f"RTSP pipeline test completed\nDuration: {duration:.1f}s",
            log_path,
        )
        log_line(log_path, "[RTSP] Completed")
        return 0
    finally:
        for proc in reversed(procs):
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in reversed(procs):
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
