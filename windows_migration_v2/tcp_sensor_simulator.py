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
    def __init__(self, host='127.0.0.1', port=9000, interval=2.0, loc_id='default room'):
        self.host = host
        self.port = port
        self.interval = interval
        self.loc_id = loc_id
        self.serial_number = f"SIM{random.randint(100000, 999999)}"
        self.frame_count = 0

    def generate_thermal_frame(self):
        """Generate a synthetic 32x24 thermal frame with hot spots."""
        # Create base temperature around 25°C (scaled to 0-255)
        frame = np.full((24, 32), 100, dtype=np.uint8)  # Base ~25°C
        
        # Add animated wave pattern
        t = self.frame_count * 0.1
        for r in range(24):
            for c in range(32):
                # Gentle animated pattern
                val = int(100 + 30 * np.sin(r * 0.3 + t) * np.cos(c * 0.3 + t))
                frame[r, c] = np.clip(val, 80, 140)
        
        # Add 2-3 random hot spots above threshold (40°C ~ 160 in 0-255 scale)
        num_hotspots = random.randint(2, 4)
        for _ in range(num_hotspots):
            center_r = random.randint(3, 20)
            center_c = random.randint(3, 28)
            # Create a hot region (3x3 cells)
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    r, c = center_r + dr, center_c + dc
                    if 0 <= r < 24 and 0 <= c < 32:
                        # Temperature 50-70°C (200-255 in scale)
                        frame[r, c] = random.randint(200, 255)
        
        self.frame_count += 1
        # Convert to hex strings
        hex_values = [f"{frame[r, c]:04X}" for r in range(24) for c in range(32)]
        return " ".join(hex_values)

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
            # Send serial number and loc_id
            sock.sendall(f"#serialno:{self.serial_number}!\n".encode('utf-8'))
            print(f"Sent serialno: {self.serial_number}")
            sock.sendall(f"#locid:{self.loc_id}!\n".encode('utf-8'))
            print(f"Sent loc_id: {self.loc_id}")

            while True:
                # Send thermal frame with loc_id
                frame_data = self.generate_thermal_frame()
                frame_packet = f"#frame:{self.loc_id}:{frame_data}!\n"
                sock.sendall(frame_packet.encode('utf-8'))
                print(f"Sent frame #{self.frame_count} to {self.loc_id}")

                # Send sensor data with loc_id
                sensor_data = self.generate_sensor_packet()
                sensor_packet = f"#Sensor:{self.loc_id}:{sensor_data}!\n"
                sock.sendall(sensor_packet.encode('utf-8'))
                print(f"Sent sensor to {self.loc_id}: {sensor_data}")

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
    parser.add_argument('--port', type=int, default=9000, help='TCP server port')
    parser.add_argument('--interval', type=float, default=2.0, help='Interval between packets (seconds)')
    parser.add_argument('--loc-id', default='default room', help='Location ID for routing thermal data')
    args = parser.parse_args()

    simulator = TCPSensorSimulator(host=args.host, port=args.port, interval=args.interval, loc_id=args.loc_id)
    print(f"Starting TCP Sensor Simulator: {args.host}:{args.port} (interval={args.interval}s, loc_id={args.loc_id})")
    simulator.run()
