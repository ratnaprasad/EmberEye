import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
DEBUG_LOG = os.path.join(LOG_DIR, 'tcp_debug.log')
ERROR_LOG = os.path.join(LOG_DIR, 'tcp_errors.log')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ROTATE_KEEP = 3

def _rotate_if_needed(path: str):
    try:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_SIZE_BYTES:
            # Rotate: path -> path.1, path.1 -> path.2, etc.
            for i in range(ROTATE_KEEP, 0, -1):
                src = f"{path}.{i}"
                dst = f"{path}.{i+1}"
                if os.path.exists(src):
                    try:
                        if i == ROTATE_KEEP:
                            os.remove(src)
                        else:
                            os.rename(src, dst)
                    except Exception:
                        pass
            try:
                os.rename(path, f"{path}.1")
            except Exception:
                pass
    except Exception:
        pass

def _write_line(path: str, line: str):
    try:
        _rotate_if_needed(path)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        # Avoid raising in packet path
        pass

def log_raw_packet(raw: str, location_id: str = None):
    ts = datetime.utcnow().isoformat() + 'Z'
    loc = location_id or ''
    line = f"{ts}\t{loc}\tRAW\t{raw}"
    _write_line(DEBUG_LOG, line)

def log_error_packet(reason: str, raw: str, location_id: str = None):
    ts = datetime.utcnow().isoformat() + 'Z'
    loc = location_id or ''
    line = f"{ts}\t{loc}\tERROR\t{reason}\t{raw}"
    _write_line(ERROR_LOG, line)
