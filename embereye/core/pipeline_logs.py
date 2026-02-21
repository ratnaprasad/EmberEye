import os
import sys
import threading
from datetime import datetime

if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_DIR = os.path.join(app_dir, 'logs')
VISION_LOG = os.path.join(LOG_DIR, 'vision_detection.log')
FUSION_LOG = os.path.join(LOG_DIR, 'fusion_algorithm.log')

_LOCK = threading.Lock()


def _ensure_dir():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        pass


def _write_line(path: str, line: str):
    _ensure_dir()
    try:
        with _LOCK:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
    except Exception:
        pass


def log_vision_event(stage: str, stream_id: str, message: str):
    ts = datetime.utcnow().isoformat() + 'Z'
    _write_line(VISION_LOG, f"{ts}\t{(stage or '').upper()}\t{stream_id or ''}\t{message}")


def log_fusion_event(loc_id: str, message: str):
    ts = datetime.utcnow().isoformat() + 'Z'
    _write_line(FUSION_LOG, f"{ts}\tFUSION\t{loc_id or ''}\t{message}")
