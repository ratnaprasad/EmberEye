"""
EmberHawk Manager - Device management for EmberEye Field Application.
Manages EmberHawk (formerly PFDS) thermal sensor devices.
"""

import sqlite3
import threading
import time
import os
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

_REQUIRED_COLUMNS = {
    "serial_number": "TEXT",
    "is_authorized": "INTEGER NOT NULL DEFAULT 1",
    "is_linked": "INTEGER NOT NULL DEFAULT 1",
    "last_seen_ip": "TEXT",
    "last_seen_at": "TIMESTAMP",
}

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
            self._ensure_schema_compat(conn)

    def _ensure_schema_compat(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(pfds_devices)")
        existing = {row[1] for row in cur.fetchall()}

        for col, ddl in _REQUIRED_COLUMNS.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE pfds_devices ADD COLUMN {col} {ddl}")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_pfds_devices_serial ON pfds_devices(serial_number)")
        conn.commit()

    @staticmethod
    def _normalize_host(endpoint: Optional[str]) -> str:
        raw = str(endpoint or "").strip()
        if not raw:
            return ""
        return raw.split(":", 1)[0].strip()

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
            cur.execute(
                """
                SELECT id, name, ip, location_id, mode, poll_seconds,
                       serial_number, is_authorized, is_linked, last_seen_ip, last_seen_at
                FROM pfds_devices
                ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "ip": r[2],
                    "location_id": r[3],
                    "mode": r[4],
                    "poll_seconds": r[5],
                    "serial_number": r[6],
                    "is_authorized": bool(r[7]),
                    "is_linked": bool(r[8]),
                    "last_seen_ip": r[9],
                    "last_seen_at": r[10],
                } for r in rows
            ]

    def get_device_by_serial(self, serial_number: str) -> Optional[Dict]:
        serial = str(serial_number or "").strip()
        if not serial:
            return None
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, name, ip, location_id, mode, poll_seconds,
                       serial_number, is_authorized, is_linked, last_seen_ip, last_seen_at
                FROM pfds_devices
                WHERE serial_number = ?
                LIMIT 1
                """,
                (serial,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "ip": row[2],
            "location_id": row[3],
            "mode": row[4],
            "poll_seconds": row[5],
            "serial_number": row[6],
            "is_authorized": bool(row[7]),
            "is_linked": bool(row[8]),
            "last_seen_ip": row[9],
            "last_seen_at": row[10],
        }

    def bind_serial_to_existing_device(self, serial_number: str, client_ip: Optional[str]) -> Optional[Dict]:
        """Bind a serial to an existing device by exact endpoint match or host-IP match."""
        serial = str(serial_number or "").strip()
        peer_ip = str(client_ip or "").strip()
        if not serial:
            return None

        existing = self.get_device_by_serial(serial)
        if existing:
            self.touch_device_seen(serial, peer_ip)
            return self.get_device_by_serial(serial)

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, ip, serial_number FROM pfds_devices ORDER BY id DESC"
            )
            rows = cur.fetchall()

            match_id = None
            for did, endpoint, bound_serial in rows:
                # Never overwrite an existing serial binding during auto-discovery.
                if str(bound_serial or "").strip():
                    continue
                host = self._normalize_host(endpoint)
                if peer_ip and (endpoint == peer_ip or host == peer_ip):
                    match_id = did
                    break

            if match_id is None:
                return None

            cur.execute(
                """
                UPDATE pfds_devices
                SET serial_number = ?,
                    last_seen_ip = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (serial, peer_ip or None, match_id),
            )
            conn.commit()

        return self.get_device_by_serial(serial)

    def bulk_reconcile_pending_serials(
        self,
        pending_by_serial: Dict[str, Dict],
        auto_link: bool = True,
        actor: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, object]:
        """Bulk-bind pending serial identities to unbound devices by endpoint/last-seen IP match."""
        summary = {
            "dry_run": bool(dry_run),
            "attempted": 0,
            "bound": 0,
            "would_bind": 0,
            "already_bound": 0,
            "unmatched": 0,
            "errors": 0,
            "bound_serials": [],
            "unmatched_serials": [],
            "error_items": [],
            "report_rows": [],
        }
        pending = pending_by_serial or {}
        if not isinstance(pending, dict):
            return summary

        devices = self.list_devices()
        for raw_serial, info in pending.items():
            serial = str(raw_serial or "").strip()
            if not serial:
                continue
            summary["attempted"] += 1

            existing = self.get_device_by_serial(serial)
            if existing:
                summary["already_bound"] += 1
                summary["report_rows"].append(
                    {
                        "serial": serial,
                        "status": "already_bound",
                        "candidate_device_id": existing.get("id"),
                        "candidate_device_name": existing.get("name"),
                        "candidate_ip": existing.get("ip"),
                        "client_ip": str((info or {}).get("client_ip") or "").strip(),
                        "dry_run": bool(dry_run),
                    }
                )
                continue

            peer_ip = str((info or {}).get("client_ip") or "").strip()
            peer_host = self._normalize_host(peer_ip)

            candidate = None
            for d in devices:
                device_serial = str(d.get("serial_number") or "").strip()
                if device_serial:
                    continue

                endpoint = str(d.get("ip") or "").strip()
                endpoint_host = self._normalize_host(endpoint)
                seen_ip = str(d.get("last_seen_ip") or "").strip()
                if peer_ip and (endpoint == peer_ip or endpoint_host == peer_host or seen_ip == peer_ip):
                    candidate = d
                    break

            if not candidate:
                summary["unmatched"] += 1
                summary["unmatched_serials"].append(serial)
                summary["report_rows"].append(
                    {
                        "serial": serial,
                        "status": "unmatched",
                        "candidate_device_id": None,
                        "candidate_device_name": None,
                        "candidate_ip": None,
                        "client_ip": peer_ip,
                        "dry_run": bool(dry_run),
                    }
                )
                continue

            try:
                did = int(candidate["id"])
                if dry_run:
                    summary["would_bind"] += 1
                    summary["report_rows"].append(
                        {
                            "serial": serial,
                            "status": "would_bind",
                            "candidate_device_id": did,
                            "candidate_device_name": candidate.get("name"),
                            "candidate_ip": candidate.get("ip"),
                            "client_ip": peer_ip,
                            "dry_run": True,
                        }
                    )
                else:
                    self.bind_serial_to_device(did, serial, peer_ip)
                    if auto_link:
                        self.set_device_access(
                            did,
                            is_linked=True,
                            actor=str(actor or "").strip() or "system:bulk_reconcile",
                            reason="bulk_reconcile_pending_serials",
                        )
                    summary["bound"] += 1
                    summary["bound_serials"].append(serial)
                    summary["report_rows"].append(
                        {
                            "serial": serial,
                            "status": "bound",
                            "candidate_device_id": did,
                            "candidate_device_name": candidate.get("name"),
                            "candidate_ip": candidate.get("ip"),
                            "client_ip": peer_ip,
                            "dry_run": False,
                        }
                    )
                    candidate["serial_number"] = serial
                    candidate["last_seen_ip"] = peer_ip or candidate.get("last_seen_ip")
                    candidate["is_linked"] = True if auto_link else candidate.get("is_linked", True)
            except Exception as e:
                summary["errors"] += 1
                summary["error_items"].append({"serial": serial, "error": str(e)})
                summary["report_rows"].append(
                    {
                        "serial": serial,
                        "status": "error",
                        "candidate_device_id": candidate.get("id") if isinstance(candidate, dict) else None,
                        "candidate_device_name": candidate.get("name") if isinstance(candidate, dict) else None,
                        "candidate_ip": candidate.get("ip") if isinstance(candidate, dict) else None,
                        "client_ip": peer_ip,
                        "dry_run": bool(dry_run),
                        "error": str(e),
                    }
                )

        return summary

    def touch_device_seen(self, serial_number: str, client_ip: Optional[str]) -> None:
        serial = str(serial_number or "").strip()
        if not serial:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE pfds_devices
                SET last_seen_ip = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE serial_number = ?
                """,
                (str(client_ip or "").strip() or None, serial),
            )
            conn.commit()

    def remove_device(self, device_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM pfds_devices WHERE id = ?", (device_id,))
            conn.commit()

    def bind_serial_to_device(self, device_id: int, serial_number: str, client_ip: Optional[str] = None) -> None:
        serial = str(serial_number or "").strip()
        if not serial:
            raise ValueError("serial_number is required")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE pfds_devices
                SET serial_number = ?,
                    last_seen_ip = COALESCE(?, last_seen_ip),
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (serial, str(client_ip or "").strip() or None, int(device_id)),
            )
            conn.commit()

    def update_device_location(self, device_id: int, location_id: Optional[str]) -> None:
        loc = str(location_id or "").strip() or None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE pfds_devices SET location_id = ? WHERE id = ?",
                (loc, int(device_id)),
            )
            conn.commit()

    def update_device_poll_seconds(self, device_id: int, poll_seconds: int) -> None:
        poll = max(1, int(poll_seconds))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE pfds_devices SET poll_seconds = ? WHERE id = ?",
                (poll, int(device_id)),
            )
            conn.commit()

    def update_all_poll_seconds(self, poll_seconds: int) -> int:
        poll = max(1, int(poll_seconds))
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE pfds_devices SET poll_seconds = ?", (poll,))
            conn.commit()
            return int(cur.rowcount or 0)

    def set_device_access(
        self,
        device_id: int,
        is_authorized: Optional[bool] = None,
        is_linked: Optional[bool] = None,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        fields = []
        params = []
        if is_authorized is not None:
            fields.append("is_authorized = ?")
            params.append(1 if bool(is_authorized) else 0)
        if is_linked is not None:
            fields.append("is_linked = ?")
            params.append(1 if bool(is_linked) else 0)
        if not fields:
            return

        old_device = None
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, name, ip, location_id, mode, poll_seconds,
                           serial_number, is_authorized, is_linked, last_seen_ip, last_seen_at
                    FROM pfds_devices
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (int(device_id),),
                )
                row = cur.fetchone()
            if row:
                old_device = {
                    "id": row[0],
                    "name": row[1],
                    "ip": row[2],
                    "location_id": row[3],
                    "mode": row[4],
                    "poll_seconds": row[5],
                    "serial_number": row[6],
                    "is_authorized": bool(row[7]),
                    "is_linked": bool(row[8]),
                    "last_seen_ip": row[9],
                    "last_seen_at": row[10],
                }
        except Exception:
            old_device = None

        params.append(int(device_id))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE pfds_devices SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()

        new_device = None
        try:
            devices = self.list_devices()
            for d in devices:
                if int(d.get("id", -1)) == int(device_id):
                    new_device = d
                    break
        except Exception:
            new_device = None

        try:
            from tcp_logger import log_device_audit

            actor_name = str(actor or "").strip() or f"system:{os.getenv('USER', 'unknown')}"
            payload = {
                "device_id": int(device_id),
                "actor": actor_name,
                "reason": str(reason or "").strip() or "unspecified",
                "old_is_authorized": old_device.get("is_authorized") if old_device else None,
                "new_is_authorized": new_device.get("is_authorized") if new_device else None,
                "old_is_linked": old_device.get("is_linked") if old_device else None,
                "new_is_linked": new_device.get("is_linked") if new_device else None,
                "serial_number": (new_device or old_device or {}).get("serial_number"),
                "location_id": (new_device or old_device or {}).get("location_id"),
                "device_name": (new_device or old_device or {}).get("name"),
            }
            log_device_audit("device_access_changed", payload)
        except Exception:
            pass

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
        device_last_retry_log: Dict[int, float] = {}
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
                    if not bool(d.get("is_authorized", True)) or not bool(d.get("is_linked", True)):
                        continue
                    serial_number = str(d.get("serial_number") or "").strip()
                    if not serial_number:
                        if did not in device_last_retry_log or now - device_last_retry_log.get(did, 0) >= 30:
                            print(f"⚠️  Skipping device {d.get('name')} ({d.get('ip')}): serial_number not bound")
                            device_last_retry_log[did] = now
                        continue
                    
                    # Send PERIOD_ON for Continuous mode
                    if mode == "Continuous":
                        if not device_init_done.get(did):
                            # Retry every 5 seconds when connection is not ready
                            if now - device_last_retry.get(did, 0) < 5:
                                continue

                            if did not in device_last_retry_log or now - device_last_retry_log.get(did, 0) >= 30:
                                # Intentionally suppress periodic startup chatter while link is unavailable.
                                pass
                            
                            if self._dispatcher:
                                success = self._dispatcher({"command": "PERIOD_ON", **d})
                                device_last_retry[did] = now
                                if success:
                                    device_init_done[did] = True
                                    print(f"✅ PERIOD_ON sent successfully to {d['ip']}")
                                else:
                                    if did not in device_last_retry_log or now - device_last_retry_log.get(did, 0) >= 30:
                                        device_last_retry_log[did] = now
                        
                        # Send EEPROM1 every hour for calibration
                        if now - device_last_eeprom.get(did, 0) >= 3600:
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
