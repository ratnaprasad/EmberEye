"""
EmberHawk Manager - Device management for EmberEye Field Application.
Manages EmberHawk (formerly PFDS) thermal sensor devices.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional
import ipaddress

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

class EmberHawkManager:
    """Manage EmberHawk thermal sensor devices (formerly PFDS)."""
    
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
        """Set a function to dispatch device commands. Signature: dispatcher(device_dict)."""
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
        """
        Main scheduler loop:
        - Send PERIOD_ON once per device for Continuous mode (with retry on failure)
        - Send REQUEST1 per poll cycle for On Demand mode
        - Send EEPROM1 every hour (3600 seconds) to refresh calibration offset
        """
        last_sent: Dict[int, float] = {}
        device_init_done: Dict[int, bool] = {}
        device_last_retry: Dict[int, float] = {}
        device_last_eeprom: Dict[int, float] = {}
        
        print("EmberHawk Scheduler started")
        while not self._stop_event.is_set():
            try:
                devices = self.list_devices()
                now = time.time()
                for d in devices:
                    did = d["id"]
                    poll = max(1, int(d["poll_seconds"]))
                    mode = d["mode"]
                    
                    # Send PERIOD_ON for Continuous mode
                    if mode == "Continuous":
                        if not device_init_done.get(did):
                            if did not in device_last_retry or now - device_last_retry.get(did, 0) >= 30:
                                print(f"EmberHawk: Sending PERIOD_ON to device {d['name']} ({d['ip']})")
                            
                            if self._dispatcher:
                                success = self._dispatcher({"command": "PERIOD_ON", **d})
                                if success:
                                    device_init_done[did] = True
                                    print(f"✅ PERIOD_ON sent successfully to {d['ip']}")
                                else:
                                    if did not in device_last_retry or now - device_last_retry.get(did, 0) >= 30:
                                        print(f"⚠️  PERIOD_ON failed for {d['ip']}, retrying...")
                                    device_last_retry[did] = now
                        
                        # Send EEPROM1 every hour for calibration
                        if now - device_last_eeprom.get(did, 0) >= 3600:
                            print(f"🔧 Sending EEPROM1 to device {d['name']} ({d['ip']})")
                            if self._dispatcher:
                                self._dispatcher({"command": "EEPROM1", **d})
                                device_last_eeprom[did] = now
                                    
                    # Send REQUEST1 in On Demand mode
                    elif mode == "On Demand" and now - last_sent.get(did, 0) >= poll:
                        if self._dispatcher:
                            self._dispatcher({"command": "REQUEST1", **d})
                        last_sent[did] = now
                        
                        # Also send EEPROM1 every hour
                        if now - device_last_eeprom.get(did, 0) >= 3600:
                            print(f"🔧 Sending EEPROM1 to device {d['name']} ({d['ip']})")
                            if self._dispatcher:
                                self._dispatcher({"command": "EEPROM1", **d})
                                device_last_eeprom[did] = now
                
                time.sleep(1)
            except Exception as e:
                print(f"EmberHawk Scheduler error: {e}")
                time.sleep(1)
    
    def force_resend_commands(self, ip: str):
        """Force resend initialization commands to a specific device IP."""
        try:
            devices = self.list_devices()
            for d in devices:
                if d["ip"] == ip:
                    print(f"🔄 Force resending commands to {d['name']} ({ip})")
                    if self._dispatcher:
                        if d["mode"] == "Continuous":
                            self._dispatcher({"command": "PERIOD_ON", **d})
                            print(f"   Sent PERIOD_ON")
                        else:
                            self._dispatcher({"command": "REQUEST1", **d})
                            print(f"   Sent REQUEST1")
                        
                        self._dispatcher({"command": "EEPROM1", **d})
                        print(f"   Sent EEPROM1")
                        return True
            
            print(f"⚠️  No device found with IP {ip}")
            return False
            
        except Exception as e:
            print(f"Force resend error: {e}")
            return False


def is_valid_ip(ip: str) -> bool:
    """Validate IP address format."""
    try:
        ipaddress.ip_address(ip)
        return True
    except Exception:
        return False
