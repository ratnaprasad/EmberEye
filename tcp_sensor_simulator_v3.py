#!/usr/bin/env python3
"""
TCP Sensor Simulator v3 for EmberEye (Protocol Compliant)

Protocol Implementation:
- PERIOD_ON/PERIODIC_ON: Start continuous streaming (sent once by app on boot/reconnect)
- REQUEST1: Single frame capture (on-demand only)
- EEPROM1: Request full calibration data (832 blocks = 3328 chars)

Streaming State:
- Idle: Wait for PERIOD_ON or REQUEST1
- Streaming: Continuously send frames after PERIOD_ON
- On-Demand: Send single frame per REQUEST1

EEPROM Data:
- Raw frames include embedded EEPROM (66 blocks, valid by default)
- EEPROM1 response provides full calibration (832 blocks)
- First word (chars 0-3) contains temperature offset in centi-degrees
- Offset range: typically -2°C to +2°C (simulated as -200 to +200 centi-degrees)

Temperature Calibration:
- Formula: Temperature = (raw_value / 100) - EEPROM_Offset
- EEPROM1 offset is randomly generated between -2.0°C and +2.0°C
- Offset logged when EEPROM1 command received
"""
import socket
import time
import random
import argparse
import numpy as np
import threading
import os
from pathlib import Path

class TCPSensorSimulatorV3:
    def __init__(self, host='127.0.0.1', port=9001, interval=2.0, loc_id='default room', 
                 packet_format='separate', log_file=None):
        self.host = host
        self.port = port
        self.interval = interval
        self.loc_id = loc_id
        self.serial_number = f"SIM{random.randint(100000, 999999)}"
        self.frame_count = 0
        self.packet_format = packet_format
        
        # Streaming state
        self.streaming = False
        self.streaming_lock = threading.Lock()
        
        # Logging
        self.log_file = log_file
        if self.log_file:
            log_dir = os.path.dirname(self.log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            self._log(f"=== TCP Sensor Simulator v3 Started ===")
            self._log(f"Target: {host}:{port}, loc_id={loc_id}, format={packet_format}")
    
    def _log(self, message):
        """Write log message to file and console."""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(log_line + "\n")
            except Exception as e:
                print(f"Log write error: {e}")
    
    def generate_thermal_frame(self):
        """
        Generate a synthetic thermal frame matching camera datasheet format.
        
        Total: 834 word blocks (4 chars each) = 3336 chars
        - Grid data: 768 blocks (24x32) = 3072 chars
        - EEPROM config: 66 blocks = 264 chars (valid by default)
        
        Format: Signed 16-bit values in centi-degrees (hundredths)
        Formula: temp_celsius = (signed_raw * 0.01) + 27.0
        Example: 0xFFB6 (-74) * 0.01 + 27 = 26.26°C
        """
        # Create base temperature in Celsius (room temp variations)
        base_temp = 25.0  # Base room temp in Celsius
        
        # Create temperature grid in Celsius
        temp_grid = np.zeros((24, 32), dtype=np.float32)
        
        # Add animated wave pattern (±2°C variation)
        t = self.frame_count * 0.1
        for r in range(24):
            for c in range(32):
                variation = 2.0 * np.sin(r * 0.3 + t) * np.cos(c * 0.3 + t)
                temp_grid[r, c] = base_temp + variation
        
        # Add 2-3 random hot spots for fire detection testing (40-80°C)
        num_hotspots = random.randint(2, 4)
        for _ in range(num_hotspots):
            center_r = random.randint(3, 20)
            center_c = random.randint(3, 28)
            hotspot_temp = random.uniform(45.0, 85.0)
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    r, c = center_r + dr, center_c + dc
                    if 0 <= r < 24 and 0 <= c < 32:
                        distance = abs(dr) + abs(dc)
                        temp_grid[r, c] = hotspot_temp - (distance * 5.0)
        
        self.frame_count += 1
        
        # Generate grid data (768 word blocks = 3072 chars)
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
                hex_word = f"{raw_value:04X}"
                hex_values.append(hex_word)
        
        grid_data = "".join(hex_values)  # 3072 chars
        
        # Generate VALID EEPROM config data (66 word blocks = 264 chars)
        # Use non-zero values to pass validation
        eeprom_data = "".join([f"{random.randint(100, 9999):04X}" for _ in range(66)])
        
        # Total frame: 3336 chars
        return grid_data + eeprom_data
    
    def generate_eeprom1_response(self):
        """
        Generate EEPROM1 calibration data.
        
        Format: 832 word blocks = 3328 chars (full calibration data)
        
        EEPROM Layout:
        - word[0] (chars 0-3): Calibration offset (signed 16-bit, centi-degrees)
        - word[1-831]: Additional calibration data
        
        Example: For -0.80°C offset:
          raw_offset = -80 (centi-degrees)
          hex = 0xFFB0 (two's complement of -80)
        
        This simulates a typical thermal sensor calibration offset.
        """
        # Generate realistic calibration offset (-5°C to +5°C range)
        # Most devices have small negative offsets (-2°C to +2°C)
        offset_celsius = random.uniform(-2.0, 2.0)
        offset_centidegrees = int(offset_celsius * 100)  # Convert to centi-degrees
        
        # Convert to 16-bit signed hex (two's complement if negative)
        if offset_centidegrees < 0:
            offset_word_raw = offset_centidegrees + 0x10000
        else:
            offset_word_raw = offset_centidegrees
        
        offset_word = f"{offset_word_raw:04X}"
        
        # Generate remaining calibration data (831 blocks)
        remaining_data = "".join([f"{random.randint(100, 9999):04X}" for _ in range(831)])
        
        eeprom1_data = offset_word + remaining_data
        
        self._log(f"🔧 Generated EEPROM1 calibration: offset={offset_celsius:.2f}°C (0x{offset_word})")
        return eeprom1_data
    
    def generate_sensor_packet(self):
        """Generate #Sensor packet with ADC1, ADC2, MPY30 values."""
        adc1 = random.randint(1000, 4000)
        adc2 = random.randint(500, 3000)
        mpy30 = random.choice([0, 1])
        return f"ADC1={adc1},ADC2={adc2},MPY30={mpy30}"
    
    def send_frame(self, sock):
        """Send a single thermal frame and sensor packet."""
        try:
            # Send thermal frame in datasheet format: #frame1234:DATA!
            frame_data = self.generate_thermal_frame()
            frame_packet = f"#frame{self.frame_count}:{frame_data}!\n"
            sock.sendall(frame_packet.encode('utf-8'))
            self._log(f"📤 Sent frame #{self.frame_count} ({len(frame_data)} chars) to {self.loc_id}")

            # Send sensor data
            sensor_data = self.generate_sensor_packet()
            if self.packet_format == 'embedded':
                sensor_packet = f"#Sensor{self.loc_id}:{sensor_data}!\n"
            elif self.packet_format == 'no_loc':
                sensor_packet = f"#Sensor:{sensor_data}!\n"
            else:
                sensor_packet = f"#Sensor:{self.loc_id}:{sensor_data}!\n"
            
            sock.sendall(sensor_packet.encode('utf-8'))
            return True
        except Exception as e:
            self._log(f"❌ Frame send error: {e}")
            return False
    
    def handle_command(self, command, sock):
        """Process received command from server."""
        cmd = command.strip().upper()
        
        if cmd in ['PERIOD_ON', 'PERIODIC_ON']:
            self._log(f"📥 Received PERIOD_ON command - starting continuous streaming")
            with self.streaming_lock:
                self.streaming = True
            return True
        
        elif cmd == 'REQUEST1':
            self._log(f"📥 Received REQUEST1 command - sending single frame")
            # Send single frame immediately (on-demand capture)
            return self.send_frame(sock)
        
        elif cmd == 'EEPROM1':
            self._log(f"📥 Received EEPROM1 command - sending calibration data")
            try:
                eeprom1_data = self.generate_eeprom1_response()
                # Format: #EEPROM<frame_id>:<3328_chars>!
                eeprom_packet = f"#EEPROM{self.frame_count}:{eeprom1_data}!\n"
                sock.sendall(eeprom_packet.encode('utf-8'))
                self._log(f"📤 Sent EEPROM1 response ({len(eeprom1_data)} chars, frame_id={self.frame_count})")
                return True
            except Exception as e:
                self._log(f"❌ EEPROM1 send error: {e}")
                return False
        
        else:
            self._log(f"⚠️  Unknown command: {command}")
            return True
    
    def command_listener(self, sock):
        """Background thread to listen for commands from server."""
        self._log("🎧 Command listener thread started")
        try:
            while True:
                # Set socket to non-blocking for command reception
                sock.settimeout(0.5)
                try:
                    data = sock.recv(1024)
                    if not data:
                        self._log("🔌 Connection closed by server")
                        break
                    
                    commands = data.decode('utf-8', errors='ignore').strip().split('\n')
                    for cmd in commands:
                        if cmd:
                            self.handle_command(cmd, sock)
                except socket.timeout:
                    continue
                except Exception as e:
                    self._log(f"❌ Command receive error: {e}")
                    break
        finally:
            self._log("🔇 Command listener thread stopped")
    
    def connect(self):
        """Attempt to connect to TCP server."""
        while True:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.host, self.port))
                self._log(f"✅ Connected to {self.host}:{self.port}")
                return sock
            except Exception as e:
                self._log(f"❌ Connection failed: {e}. Retrying in 5s...")
                time.sleep(5)
    
    def run(self):
        """Main simulator loop (v3 protocol compliant)."""
        sock = self.connect()
        
        try:
            # Send serial number
            sock.sendall(f"#serialno:{self.serial_number}!\n".encode('utf-8'))
            self._log(f"📤 Sent serialno: {self.serial_number}")
            
            # Send loc_id if using separate format
            if self.packet_format in ['separate', 'continuous']:
                sock.sendall(f"#locid:{self.loc_id}!\n".encode('utf-8'))
                self._log(f"📤 Sent loc_id: {self.loc_id}")
            
            # Start command listener thread
            listener_thread = threading.Thread(target=self.command_listener, args=(sock,), daemon=True)
            listener_thread.start()
            
            self._log("⏳ Waiting for PERIOD_ON command to start streaming...")
            
            # Main loop: only send frames when streaming is enabled
            while True:
                with self.streaming_lock:
                    is_streaming = self.streaming
                
                if is_streaming:
                    # Send frame in streaming mode
                    if not self.send_frame(sock):
                        break
                    time.sleep(self.interval)
                else:
                    # Idle: wait for commands (PERIOD_ON or REQUEST1)
                    time.sleep(0.5)
        
        except KeyboardInterrupt:
            self._log("\n⛔ Stopping simulator...")
        except Exception as e:
            self._log(f"❌ Fatal error: {e}")
        finally:
            sock.close()
            self._log("🔌 Socket closed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TCP Sensor Simulator v3 (Protocol Compliant)")
    parser.add_argument('--host', default='127.0.0.1', help='TCP server host')
    parser.add_argument('--port', type=int, default=9001, help='TCP server port')
    parser.add_argument('--interval', type=float, default=2.0, help='Interval between packets (seconds)')
    parser.add_argument('--loc-id', default='default room', help='Location ID for routing thermal data')
    parser.add_argument('--format', choices=['separate', 'embedded', 'continuous', 'no_loc'], 
                        default='separate', help='Packet format')
    parser.add_argument('--log-file', default='logs/simulator_v3.log', help='Log file path')
    args = parser.parse_args()

    simulator = TCPSensorSimulatorV3(
        host=args.host, 
        port=args.port, 
        interval=args.interval, 
        loc_id=args.loc_id, 
        packet_format=args.format,
        log_file=args.log_file
    )
    print(f"Starting TCP Sensor Simulator v3: {args.host}:{args.port}")
    print(f"Protocol: PERIOD_ON (continuous) | REQUEST1 (on-demand) | EEPROM1 (calibration)")
    print(f"Log file: {args.log_file}")
    simulator.run()
