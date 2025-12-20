#!/usr/bin/env python3
"""Quick script to send PFDS commands to simulator for testing."""
import socket
import time

def send_commands(host='127.0.0.1', port=9001):
    """Send EEPROM1 and PERIOD_ON commands to start simulator streaming."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"✅ Connected to {host}:{port}")
        
        # Send EEPROM1 command to request calibration data
        eeprom_cmd = "EEPROM1\n"
        sock.sendall(eeprom_cmd.encode('utf-8'))
        print(f"📤 Sent: {eeprom_cmd.strip()}")
        time.sleep(0.5)
        
        # Send PERIOD_ON command to start continuous streaming
        period_cmd = "PERIOD_ON\n"
        sock.sendall(period_cmd.encode('utf-8'))
        print(f"📤 Sent: {period_cmd.strip()}")
        
        print("✅ Commands sent! Simulator should now be streaming thermal data.")
        print("   Check your Demo Room camera for thermal grid overlay.")
        
        sock.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        print("   Make sure the TCP server is running on port 9001")

if __name__ == "__main__":
    send_commands()
