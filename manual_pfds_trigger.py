#!/usr/bin/env python3
"""Manual PFDS command trigger - sends EEPROM1 and PERIOD_ON to all configured devices."""
import sqlite3
import time
from pathlib import Path

DB_PATH = Path("pfds_devices.db")

def send_manual_commands():
    """Manually trigger PFDS commands by updating database timestamps."""
    if not DB_PATH.exists():
        print("❌ PFDS database not found!")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all devices
        cursor.execute("SELECT id, name, ip, location_id, mode FROM pfds_devices")
        devices = cursor.fetchall()
        
        if not devices:
            print("❌ No PFDS devices configured!")
            return
        
        print(f"Found {len(devices)} device(s):")
        for dev_id, name, ip, loc_id, mode in devices:
            print(f"  - {name} ({ip}) → {loc_id or 'N/A'} [{mode}]")
        
        # Force re-initialization by deleting and re-adding each device
        print("\n🔄 Forcing PFDS scheduler to resend commands...")
        
        for dev_id, name, ip, loc_id, mode in devices:
            # Get current poll_seconds
            cursor.execute("SELECT poll_seconds FROM pfds_devices WHERE id=?", (dev_id,))
            poll = cursor.fetchone()[0]
            
            # Delete and re-insert to force scheduler reset
            cursor.execute("DELETE FROM pfds_devices WHERE id=?", (dev_id,))
            cursor.execute(
                "INSERT INTO pfds_devices (name, ip, location_id, mode, poll_seconds) VALUES (?, ?, ?, ?, ?)",
                (name, ip, loc_id, mode, poll)
            )
            conn.commit()
            print(f"✅ Reset device: {name}")
        
        conn.close()
        
        print("\n✅ PFDS scheduler will send EEPROM1 and PERIOD_ON within 1-2 seconds!")
        print("   Check simulator logs: tail -f simulator_debug.log")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Manual PFDS Command Trigger")
    print("=" * 60)
    send_manual_commands()
    print("=" * 60)
