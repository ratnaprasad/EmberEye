#!/usr/bin/env python3
"""Test script to manually trigger PFDS commands."""
import time
from pfds_manager import PFDSManager

def test_dispatcher(cmd):
    """Test dispatcher that prints commands."""
    print(f"Dispatcher called with: {cmd}")
    # Import TCP server from main window context
    try:
        # Simulate what main_window does
        from tcp_sensor_server import TCPSensorServer
        # Note: This won't work without accessing main_window's tcp_server instance
        print(f"Would send command '{cmd.get('command')}' to IP {cmd.get('ip')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Testing PFDS Manager...")
    manager = PFDSManager()
    manager.set_dispatcher(test_dispatcher)
    
    # List devices
    devices = manager.list_devices()
    print(f"\nConfigured devices: {devices}")
    
    # Manually trigger one device
    if devices:
        device = devices[0]
        print(f"\nManually triggering device: {device}")
        test_dispatcher({"command": "EEPROM1", **device})
        time.sleep(0.1)
        test_dispatcher({"command": "PERIOD_ON", **device})
    
    print("\nDone. Press Ctrl+C to exit.")
