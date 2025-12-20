import json
import os
import threading
from datetime import datetime

class ErrorLogger:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._log = []
                cls._instance._log_lock = threading.Lock()
                cls._instance._log_path = os.path.join(os.path.dirname(__file__), 'error_log.json')
                cls._instance._load_existing()
            return cls._instance

    def _load_existing(self):
        try:
            if os.path.exists(self._log_path):
                with open(self._log_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._log = data
        except Exception:
            # Corrupt log - ignore and start fresh
            self._log = []

    def _persist(self):
        try:
            with open(self._log_path, 'w') as f:
                json.dump(self._log, f, indent=2)
        except Exception:
            pass  # Silently ignore persistence errors

    def log(self, source: str, message: str):
        entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'source': source,
            'message': message
        }
        with self._log_lock:
            self._log.append(entry)
            # Keep log bounded (e.g., last 1000 entries)
            if len(self._log) > 1000:
                self._log = self._log[-1000:]
            self._persist()

    def get_entries(self):
        with self._log_lock:
            return list(self._log)

    def clear(self):
        with self._log_lock:
            self._log = []
            self._persist()

    def export(self, path: str) -> bool:
        try:
            with open(path, 'w') as f:
                json.dump(self.get_entries(), f, indent=2)
            return True
        except Exception:
            return False

def get_error_logger():
    return ErrorLogger()
