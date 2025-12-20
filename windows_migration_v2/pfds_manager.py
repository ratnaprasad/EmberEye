import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional

DB_PATH = Path("pfds_devices.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pfds_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    location_id TEXT,
    mode TEXT NOT NULL, -- 'Continuous' or 'On Demand'
    poll_seconds INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

class PFDSManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._init_db()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dispatcher = None  # callable: (device)->None to send commands

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(SCHEMA_SQL)

    # CRUD operations
    def add_device(self, name: str, ip: str, location_id: Optional[str], mode: str, poll_seconds: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO pfds_devices (name, ip, location_id, mode, poll_seconds) VALUES (?, ?, ?, ?, ?)",
                (name, ip, location_id, mode, poll_seconds)
            )
            conn.commit()
            return cur.lastrowid

    def list_devices(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, ip, location_id, mode, poll_seconds FROM pfds_devices ORDER BY id DESC")
            rows = cur.fetchall()
            return [
                {
                    "id": r[0], "name": r[1], "ip": r[2], "location_id": r[3], "mode": r[4], "poll_seconds": r[5]
                } for r in rows
            ]

    def remove_device(self, device_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM pfds_devices WHERE id = ?", (device_id,))
            conn.commit()

    # Scheduler
    def set_dispatcher(self, dispatcher_callable):
        """Set a function to dispatch PFDS commands. Signature: dispatcher(device_dict)."""
        self._dispatcher = dispatcher_callable

    def start_scheduler(self):
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._scheduler_thread.start()

    def stop_scheduler(self):
        self._stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=3)

    def _run_scheduler(self):
        """Simple loop: periodically send REQUEST1 per device; PERIOD_ON on first run for Continuous."""
        last_sent: Dict[int, float] = {}
        sent_period_on: Dict[int, bool] = {}
        while not self._stop_event.is_set():
            try:
                devices = self.list_devices()
                now = time.time()
                for d in devices:
                    did = d["id"]
                    poll = max(1, int(d["poll_seconds"]))
                    mode = d["mode"]
                    # Send PERIOD_ON once for Continuous mode
                    if mode == "Continuous" and not sent_period_on.get(did):
                        if self._dispatcher:
                            self._dispatcher({"command": "PERIOD_ON", **d})
                        sent_period_on[did] = True
                    # Send REQUEST1 based on poll
                    if now - last_sent.get(did, 0) >= poll:
                        if self._dispatcher:
                            self._dispatcher({"command": "REQUEST1", **d})
                        last_sent[did] = now
                time.sleep(1)
            except Exception:
                time.sleep(1)

# Helper: basic IP validation (format only)
import ipaddress

def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except Exception:
        return False
