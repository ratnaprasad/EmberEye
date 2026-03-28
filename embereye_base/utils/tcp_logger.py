import os
from datetime import UTC, datetime
import shutil
import sys
import json
from pathlib import Path

# Determine log directory - handle both normal Python and PyInstaller frozen apps.
# In source mode logs must be written under <repo>/logs so release-readiness
# checks can find device_telemetry.jsonl and device_audit.jsonl.
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle.
    default_log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
else:
    # Running from source, repo root is two levels above this file.
    repo_root = Path(__file__).resolve().parents[2]
    default_log_dir = str(repo_root / 'logs')

LOG_DIR = os.environ.get('EMBEREYE_LOG_DIR', default_log_dir)
DEBUG_LOG = os.path.join(LOG_DIR, 'tcp_debug.log')
ERROR_LOG = os.path.join(LOG_DIR, 'tcp_errors.log')
DEVICE_TELEMETRY_LOG = os.path.join(LOG_DIR, 'device_telemetry.jsonl')
DEVICE_AUDIT_LOG = os.path.join(LOG_DIR, 'device_audit.jsonl')

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
    ts = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    loc = locationId or location_id or ''
    line = f"{ts}\t{loc}\tRAW\t{raw}"
    _write_line(DEBUG_LOG, line)

def log_error_packet(reason: str, raw: str, loc_id: str = None, location_id: str = None):
    """Log error packet. Accepts both loc_id and location_id for compatibility."""
    ts = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    loc = loc_id or location_id or ''
    line = f"{ts}\t{loc}\tERROR\t{reason}\t{raw}"
    _write_line(ERROR_LOG, line)


def log_device_telemetry(event: str, payload: dict):
    """Append structured device telemetry to JSONL log with UTC timestamp."""
    try:
        record = {
            'timestamp': datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            'event': str(event),
            'payload': payload if isinstance(payload, dict) else {'value': payload},
        }
        _write_line(DEVICE_TELEMETRY_LOG, json.dumps(record, sort_keys=True, default=str))
    except Exception:
        # Never raise from runtime packet/dispatch paths.
        pass


def log_device_audit(event: str, payload: dict):
    """Append device access audit events to JSONL log with UTC timestamp."""
    try:
        record = {
            'timestamp': datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            'event': str(event),
            'payload': payload if isinstance(payload, dict) else {'value': payload},
        }
        _write_line(DEVICE_AUDIT_LOG, json.dumps(record, sort_keys=True, default=str))
    except Exception:
        # Never raise from management paths.
        pass
