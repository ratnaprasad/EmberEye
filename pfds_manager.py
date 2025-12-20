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
        """
        Main scheduler loop:
        - Send PERIOD_ON once per device for Continuous mode (with retry on failure)
        - Send REQUEST1 per poll cycle for On Demand mode
        - Send EEPROM1 every hour (3600 seconds) to refresh calibration offset
        
        EEPROM1 is now automatically requested hourly to collect and verify offset calibration.
        This ensures temperature display is accurate based on device calibration.
        """
        last_sent: Dict[int, float] = {}
        device_init_done: Dict[int, bool] = {}  # Track per-device init to gate PERIOD_ON
        device_last_retry: Dict[int, float] = {}  # Track last retry attempt for failed PERIOD_ON
        device_last_eeprom: Dict[int, float] = {}  # Track last EEPROM1 request (every 3600s)
        print("PFDS Scheduler started")
        while not self._stop_event.is_set():
            try:
                devices = self.list_devices()
                now = time.time()
                for d in devices:
                    did = d["id"]
                    poll = max(1, int(d["poll_seconds"]))
                    mode = d["mode"]
                    
                    # Send PERIOD_ON for Continuous mode (once per device, with retry on failure)
                    if mode == "Continuous":
                        if not device_init_done.get(did):
                            print(f"PFDS: Sending PERIOD_ON to device {d['name']} ({d['ip']}) [ONE-TIME INIT]")
                            if self._dispatcher:
                                # Start continuous streaming (PERIOD_ON is one-time per device boot)
                                success = self._dispatcher({"command": "PERIOD_ON", **d})
                                # Only mark as done if command was successfully sent
                                if success:
                                    device_init_done[did] = True
                                    print(f"✅ PERIOD_ON sent successfully to {d['ip']}")
                                else:
                                    # Retry after 5 seconds if send failed (connection not ready)
                                    device_last_retry[did] = now
                                    print(f"⚠️  PERIOD_ON failed for {d['ip']}, will retry in 5s")
                            else:
                                print("PFDS: WARNING - No dispatcher set!")
                        elif now - device_last_retry.get(did, 0) >= 5:
                            # Retry PERIOD_ON if it was marked as sent but device might have disconnected
                            # This handles reconnection scenarios
                            print(f"🔄 Retrying PERIOD_ON to {d['name']} ({d['ip']}) [RECONNECT CHECK]")
                            if self._dispatcher:
                                success = self._dispatcher({"command": "PERIOD_ON", **d})
                                if success:
                                    device_last_retry[did] = now
                        
                        # Send EEPROM1 every 3600 seconds (1 hour) to refresh calibration offset
                        if now - device_last_eeprom.get(did, 0) >= 3600:
                            print(f"🔧 Sending EEPROM1 to device {d['name']} ({d['ip']}) [HOURLY CALIBRATION REFRESH]")
                            if self._dispatcher:
                                self._dispatcher({"command": "EEPROM1", **d})
                                device_last_eeprom[did] = now
                                print(f"   Collecting calibration offset data...")
                            else:
                                print("PFDS: WARNING - No dispatcher set!")
                                    
                    # Send REQUEST1 ONLY in On Demand mode per poll cycle
                    elif mode == "On Demand" and now - last_sent.get(did, 0) >= poll:
                        if self._dispatcher:
                            self._dispatcher({"command": "REQUEST1", **d})
                        last_sent[did] = now
                        
                        # Also send EEPROM1 every 3600 seconds for On Demand mode
                        if now - device_last_eeprom.get(did, 0) >= 3600:
                            print(f"🔧 Sending EEPROM1 to device {d['name']} ({d['ip']}) [HOURLY CALIBRATION REFRESH]")
                            if self._dispatcher:
                                self._dispatcher({"command": "EEPROM1", **d})
                                device_last_eeprom[did] = now
                                print(f"   Collecting calibration offset data...")
                
                time.sleep(1)
            except Exception as e:
                print(f"PFDS Scheduler error: {e}")
                time.sleep(1)
    
    def force_resend_commands(self, ip: str):
        """Force resend initialization commands to a specific device IP (on reconnect/restart).
        Now also sends EEPROM1 immediately to collect fresh calibration offset."""
        try:
            devices = self.list_devices()
            for d in devices:
                if d["ip"] == ip:
                    print(f"🔄 Force resending commands to {d['name']} ({ip})")
                    if self._dispatcher:
                        # Send PERIOD_ON or REQUEST1 based on mode (one-time gate per reconnect)
                        if d["mode"] == "Continuous":
                            self._dispatcher({"command": "PERIOD_ON", **d})
                            print(f"   Sent PERIOD_ON (continuous streaming)")
                        else:
                            # In On Demand mode, issue REQUEST1 for a single frame
                            self._dispatcher({"command": "REQUEST1", **d})
                            print(f"   Sent REQUEST1 (on-demand capture)")
                        
                        # Now send EEPROM1 to collect fresh calibration offset
                        self._dispatcher({"command": "EEPROM1", **d})
                        print(f"   Sent EEPROM1 (collecting calibration offset)")
                        
                        print(f"✅ Commands sent to {ip}")
                        return True
                    else:
                        print("PFDS: WARNING - No dispatcher set!")
                        return False
            
            print(f"⚠️  No device found with IP {ip}")
            return False
            
        except Exception as e:
            print(f"Force resend error: {e}")
            import traceback
            traceback.print_exc()
            return False

# Helper: basic IP validation (format only)
import ipaddress

def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except Exception:
        return False
