#!/usr/bin/env python3
"""
TCP Sensor Simulator V2 for EmberEye
- Responds to EEPROM1, PERIOD_ON, REQUEST1 commands
- 832-block EEPROM data support
- Silent operation (no console prints)
"""
import socket
import time
import random
import argparse
import numpy as np
import threading
import logging

# Setup logger (file only, no console)
import os
import sys
# Determine log file path - handle both normal Python and PyInstaller frozen apps
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    app_dir = os.path.dirname(sys.executable)
else:
    # Running as normal Python script
    app_dir = os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(app_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(log_dir, 'simulator_debug.log'),
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

class TCPSensorSimulatorV2:
    def __init__(self, host='127.0.0.1', port=9001, loc_id='demo_room'):
        self.host = host
        self.port = port
        self.loc_id = loc_id
        self.serial_number = f"SIM{random.randint(100000, 999999)}"
        self.frame_count = 0
        self.continuous_mode = False
        self.eeprom_sent = False
        self.sock = None
        
    def generate_eeprom_data(self):
        """Generate 832-block EEPROM calibration data (3328 chars)."""
        # Block 0: Calibration offset (e.g., 27.0°C = 0x0A8C = 2700 in centi-degrees)
        offset_raw = 2700  # 27.0°C in centi-degrees
        eeprom_blocks = [f"{offset_raw:04X}"]
        
        # Blocks 1-831: Random calibration data
        for _ in range(831):
            eeprom_blocks.append(f"{random.randint(0, 65535):04X}")
        
        return "".join(eeprom_blocks)  # 832 blocks = 3328 chars
    
    def generate_thermal_frame(self):
        """Generate 834-block thermal frame (3336 chars).
        - 768 grid blocks (24x32)
        - 66 invalid EEPROM blocks (ignored after EEPROM1)
        """
        # Base temperature: 25°C ± variations
        base_temp = 25.0
        temp_grid = np.zeros((24, 32), dtype=np.float32)
        
        # Add animated pattern
        t = self.frame_count * 0.1
        for r in range(24):
            for c in range(32):
                variation = 2.0 * np.sin(r * 0.3 + t) * np.cos(c * 0.3 + t)
                temp_grid[r, c] = base_temp + variation
        
        # Add hotspots (45-85°C for fire detection)
        for _ in range(random.randint(2, 3)):
            center_r = random.randint(3, 20)
            center_c = random.randint(3, 28)
            hotspot_temp = random.uniform(50.0, 80.0)
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    r, c = center_r + dr, center_c + dc
                    if 0 <= r < 24 and 0 <= c < 32:
                        distance = abs(dr) + abs(dc)
                        temp_grid[r, c] = hotspot_temp - (distance * 5.0)
        
        self.frame_count += 1
        
        # Convert to hex (768 blocks)
        hex_values = []
        for r in range(24):
            for c in range(32):
                temp_celsius = temp_grid[r, c]
                raw_delta = int((temp_celsius - 27.0) / 0.01)
                if raw_delta < 0:
                    raw_value = raw_delta + 0x10000
                else:
                    raw_value = raw_delta
                raw_value = max(0, min(0xFFFF, raw_value))
                hex_values.append(f"{raw_value:04X}")
        
        grid_data = "".join(hex_values)  # 3072 chars
        
        # Add 66 invalid EEPROM blocks (264 chars)
        invalid_eeprom = "".join([f"{random.randint(0, 65535):04X}" for _ in range(66)])
        
        return grid_data + invalid_eeprom  # 3336 chars total
    
    def generate_sensor_data(self):
        """Generate ADC1, ADC2, MPY30 values."""
        adc1 = random.randint(1000, 4000)
        adc2 = random.randint(500, 3000)
        mpy30 = random.choice([0, 1])
        return f"ADC1={adc1},ADC2={adc2},MPY30={mpy30}"
    
    def send_packet(self, packet):
        """Send packet with newline."""
        try:
            self.sock.sendall((packet + "\n").encode('utf-8'))
            logger.debug(f"Sent: {packet[:60]}...")
        except Exception as e:
            logger.error(f"Send failed: {e}")
    
    def handle_commands(self):
        """Listen for incoming commands in background thread."""
        self.sock.settimeout(0.5)
        while self.sock:
            try:
                data = self.sock.recv(1024)
                if not data:
                    break
                
                command = data.decode('utf-8').strip()
                logger.info(f"Received command: {command}")
                
                if command == "EEPROM1":
                    # Send EEPROM calibration response
                    eeprom_data = self.generate_eeprom_data()
                    response = f"#EEPROM{self.loc_id}:{eeprom_data}!"
                    self.send_packet(response)
                    self.eeprom_sent = True
                    logger.info(f"Sent EEPROM calibration (832 blocks) for {self.loc_id}")
                
                elif command == "PERIOD_ON":
                    self.continuous_mode = True
                    logger.info("Continuous mode enabled")
                
                elif command == "REQUEST1":
                    # Send single frame + sensor data
                    frame_data = self.generate_thermal_frame()
                    self.send_packet(f"#frame{self.frame_count}:{frame_data}!")
                    sensor_data = self.generate_sensor_data()
                    self.send_packet(f"#Sensor:{self.loc_id}:{sensor_data}!")
                    logger.info("Sent single frame (REQUEST1)")
                
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Command handler error: {e}")
                break
    
    def run(self):
        """Main simulator loop."""
        try:
            # Connect to server
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to {self.host}:{self.port}")
            
            # Start command listener thread
            cmd_thread = threading.Thread(target=self.handle_commands, daemon=True)
            cmd_thread.start()
            
            # Send initial packets
            self.send_packet(f"#serialno:{self.serial_number}!")
            self.send_packet(f"#locid:{self.loc_id}!")
            time.sleep(0.5)
            
            # Wait for EEPROM1 and PERIOD_ON commands
            logger.info("Waiting for EEPROM1 and PERIOD_ON commands...")
            time.sleep(2)
            
            # Main loop: send frames if continuous mode enabled
            while True:
                if self.continuous_mode:
                    # Send thermal frame data with loc_id embedded in frame ID
                    frame_data = self.generate_thermal_frame()
                    self.send_packet(f"#frame{self.loc_id}:{frame_data}!")
                    
                    # Send sensor data
                    sensor_data = self.generate_sensor_data()
                    self.send_packet(f"#Sensor:{self.loc_id}:{sensor_data}!")
                    
                    logger.debug(f"Sent frame #{self.frame_count} + sensor to {self.loc_id}")
                    time.sleep(2)  # 2 second interval
                else:
                    time.sleep(0.5)  # Wait for PERIOD_ON command
        
        except KeyboardInterrupt:
            logger.info("Stopping simulator...")
        except Exception as e:
            logger.error(f"Simulator error: {e}")
        finally:
            if self.sock:
                self.sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TCP Sensor Simulator V2 for EmberEye")
    parser.add_argument('--host', default='127.0.0.1', help='TCP server host')
    parser.add_argument('--port', type=int, default=9001, help='TCP server port')
    parser.add_argument('--loc-id', default='demo_room', help='Location ID')
    args = parser.parse_args()

    simulator = TCPSensorSimulatorV2(host=args.host, port=args.port, loc_id=args.loc_id)
    logger.info(f"Starting simulator: {args.host}:{args.port}, loc_id={args.loc_id}")
    print(f"✅ Simulator started (logs: simulator_debug.log)")
    simulator.run()
