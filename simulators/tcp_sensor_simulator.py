#!/usr/bin/env python3
"""
TCP Sensor Simulator for EmberEye
Emits #serialno, #frame (32x24 hex grid), and #Sensor packets to test TCP sensor server.
"""
import socket
import time
import random
import argparse
import numpy as np

class TCPSensorSimulator:
    def __init__(self, host='127.0.0.1', port=9001, interval=2.0, loc_id='default room', packet_format='separate'):
        self.host = host
        self.port = port
        self.interval = interval
        self.loc_id = loc_id
        self.serial_number = f"SIM{random.randint(100000, 999999)}"
        self.frame_count = 0
        self.packet_format = packet_format  # 'separate', 'embedded', 'continuous', 'no_loc'

    def generate_thermal_frame(self):
        """
        Generate a synthetic thermal frame matching camera datasheet format.
        
        Total: 834 word blocks (4 chars each) = 3336 chars
        - Grid data: 768 blocks (24x32) = 3072 chars
        - EEPROM config: 66 blocks = 264 chars
        
        Format: Signed 16-bit values in centi-degrees (hundredths)
        Formula: temp_celsius = (signed_raw * 0.01) + 27.0
        Example: 0xFFB6 (-74) * 0.01 + 27 = 26.26°C
        """
        # Create base temperature in Celsius (room temp variations)
        # Target: 24-28°C room temperature
        base_temp = 25.0  # Base room temp in Celsius
        
        # Create temperature grid in Celsius
        temp_grid = np.zeros((24, 32), dtype=np.float32)
        
        # Add animated wave pattern (±2°C variation)
        t = self.frame_count * 0.1
        for r in range(24):
            for c in range(32):
                # Gentle animated pattern around room temp
                variation = 2.0 * np.sin(r * 0.3 + t) * np.cos(c * 0.3 + t)
                temp_grid[r, c] = base_temp + variation
        
        # Add 2-3 random hot spots for fire detection testing (40-80°C)
        # These hot spots will be detected as:
        # 1. Hot cells highlighted in red overlay (sensor_fusion)
        # 2. Target temperature shown in widget (max value from grid)
        num_hotspots = random.randint(2, 4)
        for _ in range(num_hotspots):
            center_r = random.randint(3, 20)
            center_c = random.randint(3, 28)
            hotspot_temp = random.uniform(45.0, 85.0)  # Fire range
            # Create a hot region (3x3 cells)
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    r, c = center_r + dr, center_c + dc
                    if 0 <= r < 24 and 0 <= c < 32:
                        # Gradual falloff from center
                        distance = abs(dr) + abs(dc)
                        temp_grid[r, c] = hotspot_temp - (distance * 5.0)
        
        self.frame_count += 1
        
        # Generate grid data (768 word blocks = 3072 chars)
        # Convert Celsius to device format: signed 16-bit centi-degrees with 27°C offset
        # Formula inverted: raw = (temp_celsius - 27.0) * 100
        # Result is signed value in centi-degrees
        hex_values = []
        for r in range(24):
            for c in range(32):
                temp_celsius = temp_grid[r, c]
                
                # Convert to signed centi-degrees offset from 27°C
                centi_degrees = int((temp_celsius - 27.0) * 100)
                
                # Convert signed to unsigned 16-bit (two's complement)
                if centi_degrees < 0:
                    raw_value = centi_degrees + 0x10000
                else:
                    raw_value = centi_degrees
                
                # Clamp to 16-bit range
                raw_value = max(0, min(0xFFFF, raw_value))
                hex_word = f"{raw_value:04X}"
                hex_values.append(hex_word)
        
        grid_data = "".join(hex_values)  # 3072 chars
        
        # Generate EEPROM config data (66 word blocks = 264 chars)
        # Use synthetic calibration data
        eeprom_data = "".join([f"{random.randint(0, 65535):04X}" for _ in range(66)])
        
        # Total frame: 3336 chars
        return grid_data + eeprom_data

    def generate_sensor_packet(self):
        """Generate #Sensor packet with ADC1, ADC2, MPY30 values."""
        adc1 = random.randint(1000, 4000)
        adc2 = random.randint(500, 3000)
        mpy30 = random.choice([0, 1])
        return f"ADC1={adc1},ADC2={adc2},MPY30={mpy30}"

    def connect(self):
        """Attempt to connect to TCP server."""
        while True:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.host, self.port))
                print(f"Connected to {self.host}:{self.port}")
                return sock
            except Exception as e:
                print(f"Connection failed: {e}. Retrying in 5s...")
                time.sleep(5)

    def run(self):
        """Main simulator loop."""
        sock = self.connect()
        try:
            # Send serial number
            sock.sendall(f"#serialno:{self.serial_number}!\n".encode('utf-8'))
            print(f"Sent serialno: {self.serial_number}")
            
            # Send loc_id if using separate format
            if self.packet_format in ['separate', 'continuous']:
                sock.sendall(f"#locid:{self.loc_id}!\n".encode('utf-8'))
                print(f"Sent loc_id: {self.loc_id}")

            while True:
                # Send thermal frame in datasheet format: #frame1234:DATA!
                frame_data = self.generate_thermal_frame()
                
                # Use frame count as frame ID
                frame_packet = f"#frame{self.frame_count}:{frame_data}!\n"
                sock.sendall(frame_packet.encode('utf-8'))
                print(f"Sent frame #{self.frame_count} ({len(frame_data)} chars) to {self.loc_id}")

                # Send sensor data
                sensor_data = self.generate_sensor_packet()
                
                if self.packet_format == 'embedded':
                    # Embedded format: #Sensor1234:data!
                    sensor_packet = f"#Sensor{self.loc_id}:{sensor_data}!\n"
                    print(f"Sent sensor (embedded loc_id: {self.loc_id}): {sensor_data}")
                elif self.packet_format == 'no_loc':
                    # No loc_id: #Sensor:data! (will use IP fallback)
                    sensor_packet = f"#Sensor:{sensor_data}!\n"
                    print(f"Sent sensor (no loc_id, IP fallback): {sensor_data}")
                else:
                    # Separate format: #Sensor:loc_id:data!
                    sensor_packet = f"#Sensor:{self.loc_id}:{sensor_data}!\n"
                    print(f"Sent sensor to {self.loc_id}: {sensor_data}")
                
                sock.sendall(sensor_packet.encode('utf-8'))

                time.sleep(self.interval)
        except KeyboardInterrupt:
            print("\nStopping simulator...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TCP Sensor Simulator for EmberEye")
    parser.add_argument('--host', default='127.0.0.1', help='TCP server host')
    parser.add_argument('--port', type=int, default=9001, help='TCP server port')
    parser.add_argument('--interval', type=float, default=2.0, help='Interval between packets (seconds)')
    parser.add_argument('--loc-id', default='default room', help='Location ID for routing thermal data')
    parser.add_argument('--format', choices=['separate', 'embedded', 'continuous', 'no_loc'], 
                        default='separate', help='Packet format: separate (default), embedded (loc in prefix), continuous (hex), no_loc (IP fallback)')
    args = parser.parse_args()

    simulator = TCPSensorSimulator(host=args.host, port=args.port, interval=args.interval, 
                                   loc_id=args.loc_id, packet_format=args.format)
    print(f"Starting TCP Sensor Simulator: {args.host}:{args.port} (interval={args.interval}s, loc_id={args.loc_id}, format={args.format})")
    simulator.run()
