import os
from datetime import datetime
import shutil
import sys

# Determine log directory - handle both normal Python and PyInstaller frozen apps
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    app_dir = os.path.dirname(sys.executable)
else:
    # Running as normal Python script
    app_dir = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = os.path.join(app_dir, 'logs')
DEBUG_LOG = os.path.join(LOG_DIR, 'tcp_debug.log')
ERROR_LOG = os.path.join(LOG_DIR, 'tcp_errors.log')

# Ensure log directory exists
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    print(f"[TCP_LOGGER] Log directory: {LOG_DIR}")
except Exception as e:
    print(f"[TCP_LOGGER] WARNING: Could not create log directory {LOG_DIR}: {e}")

MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ROTATE_KEEP = 3


def _rotate_if_needed(path: str):
    try:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_SIZE_BYTES:
            # Shift existing rotations
            for i in range(ROTATE_KEEP, 0, -1):
                src = f"{path}.{i}"
                dst = f"{path}.{i+1}"
                if os.path.exists(src):
                    try:
                        if i == ROTATE_KEEP:
                            os.remove(src)
                        else:
                            os.replace(src, dst)
                    except Exception:
                        pass
            # Move current to .1 and create new empty file
            try:
                shutil.move(path, f"{path}.1")
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

def log_raw_packet(raw: str, locationId: str = None, location_id: str = None):
    """Log raw TCP packet. Accepts both locationId and location_id for compatibility."""
    ts = datetime.utcnow().isoformat() + 'Z'
    loc = locationId or location_id or ''
    line = f"{ts}\t{loc}\tRAW\t{raw}"
    _write_line(DEBUG_LOG, line)

def log_error_packet(reason: str, raw: str, loc_id: str = None, location_id: str = None):
    """Log error packet. Accepts both loc_id and location_id for compatibility."""
    ts = datetime.utcnow().isoformat() + 'Z'
    loc = loc_id or location_id or ''
    line = f"{ts}\t{loc}\tERROR\t{reason}\t{raw}"
    _write_line(ERROR_LOG, line)
