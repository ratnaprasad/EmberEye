"""
Device Status Manager - Tracks connection state and handles reconnection
"""
import sqlite3
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable


class DeviceStatus:
    """Represents the connection status of a device"""
    def __init__(self, device_id: int, device_name: str, ip: str, loc_id: str, device_type: str):
        self.device_id = device_id
        self.device_name = device_name
        self.ip = ip
        self.loc_id = loc_id
        self.device_type = device_type  # 'PFDS' or 'TCP'
        self.is_online = False
        self.last_seen = None
        self.last_packet_time = None
        self.connection_attempts = 0
        self.failure_reason = ""
        self.auto_reconnect_enabled = True


class DeviceStatusManager:
    """Manages device connection states and automatic reconnection"""
    
    def __init__(self, db_path='device_status.db'):
        self.db_path = db_path
        self.devices: Dict[str, DeviceStatus] = {}  # key: ip address
        self.lock = threading.Lock()
        self.running = False
        self.monitor_thread = None
        self.reconnect_callback: Optional[Callable] = None
        self.status_change_callback: Optional[Callable] = None
        
        # Timeouts (seconds)
        self.OFFLINE_TIMEOUT = 30  # Mark offline if no data for 30s
        self.RECONNECT_INTERVAL = 10  # Try reconnecting every 10s
        self.MAX_RECONNECT_ATTEMPTS = 5  # Max consecutive failures before giving up
        
        self._init_database()
    
    def _init_database(self):
        """Initialize the device status database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_status (
                ip TEXT PRIMARY KEY,
                device_id INTEGER,
                device_name TEXT,
                loc_id TEXT,
                device_type TEXT,
                is_online INTEGER DEFAULT 0,
                last_seen TEXT,
                last_packet_time TEXT,
                connection_attempts INTEGER DEFAULT 0,
                failure_reason TEXT,
                auto_reconnect_enabled INTEGER DEFAULT 1
            )
        ''')
        conn.commit()
        conn.close()
    
    def register_device(self, device_id: int, device_name: str, ip: str, 
                       loc_id: str, device_type: str = 'PFDS'):
        """Register a device for monitoring"""
        with self.lock:
            if ip not in self.devices:
                device = DeviceStatus(device_id, device_name, ip, loc_id, device_type)
                self.devices[ip] = device
                self._save_device_status(device)
                print(f"📝 Registered device: {device_name} ({ip}) for monitoring")
    
    def update_device_activity(self, ip: str, loc_id: Optional[str] = None):
        """Update device activity timestamp (called when data received)"""
        with self.lock:
            if ip in self.devices:
                device = self.devices[ip]
                device.last_packet_time = datetime.now()
                device.connection_attempts = 0  # Reset on successful data
                
                # Mark as online if it was offline
                if not device.is_online:
                    device.is_online = True
                    device.last_seen = datetime.now()
                    device.failure_reason = ""
                    self._save_device_status(device)
                    print(f"✅ Device back online: {device.device_name} ({ip})")
                    
                    # Trigger status change callback
                    if self.status_change_callback:
                        try:
                            self.status_change_callback(device, 'online')
                        except Exception as e:
                            print(f"Status callback error: {e}")
    
    def mark_device_offline(self, ip: str, reason: str = "Connection timeout"):
        """Mark a device as offline"""
        with self.lock:
            if ip in self.devices:
                device = self.devices[ip]
                if device.is_online:  # Only log if status changed
                    device.is_online = False
                    device.failure_reason = reason
                    device.last_seen = datetime.now()
                    self._save_device_status(device)
                    print(f"⚠️  Device offline: {device.device_name} ({ip}) - {reason}")
                    
                    # Trigger status change callback
                    if self.status_change_callback:
                        try:
                            self.status_change_callback(device, 'offline')
                        except Exception as e:
                            print(f"Status callback error: {e}")
    
    def get_offline_devices(self) -> List[DeviceStatus]:
        """Get list of offline devices"""
        with self.lock:
            return [d for d in self.devices.values() if not d.is_online]
    
    def get_online_devices(self) -> List[DeviceStatus]:
        """Get list of online devices"""
        with self.lock:
            return [d for d in self.devices.values() if d.is_online]
    
    def get_all_devices(self) -> List[DeviceStatus]:
        """Get all registered devices"""
        with self.lock:
            return list(self.devices.values())
    
    def set_auto_reconnect(self, ip: str, enabled: bool):
        """Enable/disable auto-reconnect for a device"""
        with self.lock:
            if ip in self.devices:
                self.devices[ip].auto_reconnect_enabled = enabled
                self._save_device_status(self.devices[ip])
    
    def manual_reconnect(self, ip: str) -> bool:
        """Manually trigger reconnection for a device"""
        with self.lock:
            if ip in self.devices:
                device = self.devices[ip]
                device.connection_attempts = 0  # Reset attempts
                device.failure_reason = "Manual reconnect initiated"
                self._save_device_status(device)
                
                # Trigger reconnection via callback asynchronously to avoid UI blocking
                if self.reconnect_callback:
                    try:
                        print(f"🔄 Manual reconnect: {device.device_name} ({ip})")
                        threading.Thread(target=self._invoke_reconnect_callback_safe, args=(device,), daemon=True).start()
                        return True
                    except Exception as e:
                        print(f"Reconnect error: {e}")
                        device.failure_reason = str(e)
                        return False
        return False

    def _invoke_reconnect_callback_safe(self, device: DeviceStatus):
        """Invoke reconnect callback in a background thread with safety."""
        try:
            # Call user-provided reconnect handler
            self.reconnect_callback(device)
        except Exception as e:
            # Record failure reason but keep thread isolated
            with self.lock:
                if device.ip in self.devices:
                    self.devices[device.ip].failure_reason = str(e)
            print(f"Reconnect handler error (async): {e}")
    
    def start_monitoring(self):
        """Start the monitoring thread"""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            print("🔍 Device status monitor started")
    
    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _monitor_loop(self):
        """Background thread that monitors device health"""
        while self.running:
            try:
                current_time = datetime.now()
                
                with self.lock:
                    for ip, device in self.devices.items():
                        if device.is_online and device.last_packet_time:
                            # Check if device has gone silent
                            elapsed = (current_time - device.last_packet_time).total_seconds()
                            if elapsed > self.OFFLINE_TIMEOUT:
                                self.mark_device_offline(ip, f"No data for {int(elapsed)}s")
                        
                        elif not device.is_online and device.auto_reconnect_enabled:
                            # Check if it's time to retry connection
                            if device.last_seen:
                                elapsed = (current_time - device.last_seen).total_seconds()
                                if elapsed > self.RECONNECT_INTERVAL:
                                    if device.connection_attempts < self.MAX_RECONNECT_ATTEMPTS:
                                        device.connection_attempts += 1
                                        device.last_seen = current_time
                                        
                                        # Trigger reconnection
                                        if self.reconnect_callback:
                                            try:
                                                print(f"🔄 Auto-reconnect attempt {device.connection_attempts}/{self.MAX_RECONNECT_ATTEMPTS}: {device.device_name} ({ip})")
                                                self.reconnect_callback(device)
                                            except Exception as e:
                                                device.failure_reason = str(e)
                                                print(f"Reconnect attempt failed: {e}")
                                    else:
                                        # Max attempts reached
                                        if "max attempts" not in device.failure_reason.lower():
                                            device.failure_reason = f"Max reconnect attempts ({self.MAX_RECONNECT_ATTEMPTS}) reached"
                                            print(f"❌ Giving up on {device.device_name} ({ip}) after {self.MAX_RECONNECT_ATTEMPTS} attempts")
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                print(f"Monitor loop error: {e}")
                time.sleep(5)
    
    def _save_device_status(self, device: DeviceStatus):
        """Save device status to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO device_status 
                (ip, device_id, device_name, loc_id, device_type, is_online, 
                 last_seen, last_packet_time, connection_attempts, failure_reason, auto_reconnect_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device.ip,
                device.device_id,
                device.device_name,
                device.loc_id,
                device.device_type,
                1 if device.is_online else 0,
                device.last_seen.isoformat() if device.last_seen else None,
                device.last_packet_time.isoformat() if device.last_packet_time else None,
                device.connection_attempts,
                device.failure_reason,
                1 if device.auto_reconnect_enabled else 0
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Failed to save device status: {e}")
    
    def load_devices_from_db(self):
        """Load device statuses from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM device_status')
            rows = cursor.fetchall()
            conn.close()
            
            with self.lock:
                for row in rows:
                    ip = row[0]
                    device = DeviceStatus(
                        device_id=row[1],
                        device_name=row[2],
                        ip=ip,
                        loc_id=row[3],
                        device_type=row[4]
                    )
                    device.is_online = bool(row[5])
                    device.last_seen = datetime.fromisoformat(row[6]) if row[6] else None
                    device.last_packet_time = datetime.fromisoformat(row[7]) if row[7] else None
                    device.connection_attempts = row[8]
                    device.failure_reason = row[9] or ""
                    device.auto_reconnect_enabled = bool(row[10])
                    
                    self.devices[ip] = device
                    print(f"📂 Loaded device: {device.device_name} ({ip}) - {'Online' if device.is_online else 'Offline'}")
        
        except Exception as e:
            print(f"Failed to load devices from DB: {e}")
