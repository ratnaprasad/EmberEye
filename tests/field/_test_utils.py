import os
import time
from pathlib import Path


def get_log_path(name: str) -> Path:
    root = Path(__file__).resolve().parent
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{name}_{ts}.log"


def log_line(log_path: Path, message: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
