#!/usr/bin/env python3
"""
EmberHawk Simulator v3 - Real Data Replay

Simulates EmberHawk (PFDS) device behavior using real captured data.

Features:
- Replays 10 minutes of real device data from NEW DATA 10 MINS.txt
- Maintains chronological order (sorts by timestamp)
- 5-second transmission interval (matches actual PFDS device)
- Infinite loop: restarts from beginning after reaching end
- Full protocol support: PERIOD_ON, REQUEST1, EEPROM1

Data Types:
- Thermal frames: #frame1234:...!
- Sensor data: #Sensor1234:ADC1=...,ADC2=...!
- EEPROM calibration: #EEPROM1234:...!

Protocol:
- PERIOD_ON: Start continuous streaming (every 5 seconds)
- REQUEST1: Single frame on-demand
- EEPROM1: Return calibration data
- PERIOD_OFF: Stop streaming

Author: EmberEye System
Date: January 2026
"""

import socket
import time
import threading
import argparse
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional


class DataRecord:
    """Represents a single data packet from the log file."""
    
    def __init__(self, timestamp: datetime, direction: str, data: str, raw_line: str):
        self.timestamp = timestamp
        self.direction = direction  # 'IN' or 'OUT'
        self.data = data
        self.raw_line = raw_line
        self.packet_type = self._detect_type()
    
    def _detect_type(self) -> str:
        """Detect packet type from data content."""
        if 'PERIOD_ON' in self.data or 'PERIODIC_ON' in self.data:
            return 'PERIOD_ON_CMD'
        elif 'REQUEST1' in self.data:
            return 'REQUEST1_CMD'
        elif 'EEPROM1' in self.data and len(self.data) < 20:  # Command, not response
            return 'EEPROM1_CMD'
        elif '#frame' in self.data:
            return 'THERMAL_FRAME'
        elif '#Sensor' in self.data:
            return 'SENSOR_DATA'
        elif '#EEPROM' in self.data:
            return 'EEPROM_DATA'
        else:
            return 'UNKNOWN'
    
    def is_response_packet(self) -> bool:
        """Check if this is a response packet (sent by device)."""
        return self.packet_type in ['THERMAL_FRAME', 'SENSOR_DATA', 'EEPROM_DATA']
    
    def __repr__(self):
        return f"<DataRecord {self.timestamp.strftime('%H:%M:%S.%f')[:-3]} {self.packet_type} {len(self.data)} bytes>"


class EmberHawkSimulator:
    """EmberHawk Device Simulator - replays real device data."""
    
    def __init__(self, host='0.0.0.0', port=9001, data_file='data/NEW DATA 10 MINS.txt', 
                 interval=5.0):
        self.host = host
        self.port = port
        self.data_file = Path(__file__).parent / data_file
        self.interval = interval  # 5 seconds between transmissions (real device timing)
        
        # Data storage
        self.records: List[DataRecord] = []
        self.current_index = 0
        
        # Streaming state
        self.streaming = False
        self.streaming_thread: Optional[threading.Thread] = None
        self.stop_streaming = threading.Event()
        
        # Connection
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.client_address: Optional[Tuple[str, int]] = None
        
        # Statistics
        self.packets_sent = 0
        self.loop_count = 0
        
        self._log(f"PFDS Device Simulator v3 Initialized")
        self._log(f"Server: {host}:{port}")
        self._log(f"Data file: {self.data_file}")
        self._log(f"Transmission interval: {interval}s (real device timing)")
    
    def _log(self, message: str):
        """Log message with timestamp."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] {message}")
    
    def load_data(self) -> bool:
        """Parse and load data from NEW DATA 10 MINS.txt file."""
        if not self.data_file.exists():
            self._log(f"ERROR: Data file not found: {self.data_file}")
            return False
        
        self._log(f"Loading data from {self.data_file}...")
        
        # Regex to parse log lines: [HH:MM:SS.mmm]DIRECTION→/←data
        # Example: [13:06:38.922]OUT¡ú¡óEEPROM1¡õ
        # Example: [13:07:20.822]IN¡û¡ô#frame1234:...!
        # Pattern captures: timestamp, direction (OUT/IN), and data after special chars
        pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\](OUT|IN).*?([#¡].*?)(?=\[|$)', re.DOTALL)
        
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        records = []
        
        try:
            with open(self.data_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            for match in pattern.finditer(content):
                time_str = match.group(1)  # HH:MM:SS.mmm
                direction = match.group(2)  # OUT or IN
                data = match.group(3).strip()  # The actual data
                
                # Parse timestamp
                try:
                    time_obj = datetime.strptime(time_str, '%H:%M:%S.%f')
                    timestamp = base_date.replace(
                        hour=time_obj.hour,
                        minute=time_obj.minute,
                        second=time_obj.second,
                        microsecond=time_obj.microsecond
                    )
                except ValueError:
                    continue
                
                # Clean up data (remove all special characters, keep only data content)
                # Remove arrows and special markers, keep #frame, #Sensor, #EEPROM
                data = re.sub(r'[¡ó¡õ¡ô¡ú¡û→←]', '', data).strip()
                
                if data and (data.startswith('#') or 'PERIOD' in data or 'REQUEST' in data or 'EEPROM1' in data):
                    record = DataRecord(timestamp, direction, data, match.group(0))
                    records.append(record)
            
            # Sort by timestamp
            records.sort(key=lambda r: r.timestamp)
            
            # Filter only response packets (what device sends)
            self.records = [r for r in records if r.is_response_packet()]
            
            self._log(f"✓ Loaded {len(records)} total records")
            self._log(f"✓ Filtered to {len(self.records)} response packets")
            
            if self.records:
                first = self.records[0]
                last = self.records[-1]
                duration = (last.timestamp - first.timestamp).total_seconds()
                self._log(f"✓ Time range: {first.timestamp.strftime('%H:%M:%S')} - {last.timestamp.strftime('%H:%M:%S')} ({duration:.1f}s)")
                
                # Count packet types
                type_counts = {}
                for r in self.records:
                    type_counts[r.packet_type] = type_counts.get(r.packet_type, 0) + 1
                
                self._log(f"✓ Packet breakdown:")
                for ptype, count in sorted(type_counts.items()):
                    self._log(f"  - {ptype}: {count}")
            
            return len(self.records) > 0
        
        except Exception as e:
            self._log(f"ERROR loading data: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_next_packet(self) -> Optional[DataRecord]:
        """Get next packet in sequence. Loops back to start after reaching end."""
        if not self.records:
            return None
        
        record = self.records[self.current_index]
        self.current_index += 1
        
        # Loop back to beginning
        if self.current_index >= len(self.records):
            self.current_index = 0
            self.loop_count += 1
            self._log(f"♻ Data loop completed ({self.loop_count} cycles), restarting from beginning...")
        
        return record
    
    def send_packet(self, data: str) -> bool:
        """Send a packet to the connected client."""
        if not self.client_socket:
            return False
        
        try:
            # Add protocol framing if not already present
            if not data.startswith('#') and not data.endswith('!'):
                data = f"#{data}!"
            
            self.client_socket.sendall(data.encode('utf-8'))
            self.packets_sent += 1
            return True
        except Exception as e:
            self._log(f"ERROR sending packet: {e}")
            return False
    
    def handle_command(self, command: str) -> bool:
        """Process command from client."""
        command = command.strip().upper()
        
        if 'PERIOD_ON' in command or 'PERIODIC_ON' in command:
            self._log(f"← Command: PERIOD_ON (start streaming)")
            if not self.streaming:
                self.start_streaming()
            return True
        
        elif 'PERIOD_OFF' in command:
            self._log(f"← Command: PERIOD_OFF (stop streaming)")
            if self.streaming:
                self.stop_streaming_flag()
            return True
        
        elif 'REQUEST1' in command:
            self._log(f"← Command: REQUEST1 (single frame)")
            # Send next thermal frame
            for _ in range(len(self.records)):
                record = self.get_next_packet()
                if record and record.packet_type == 'THERMAL_FRAME':
                    self._log(f"→ Sending thermal frame ({len(record.data)} bytes)")
                    self.send_packet(record.data)
                    break
            return True
        
        elif 'EEPROM1' in command:
            self._log(f"← Command: EEPROM1 (calibration data)")
            # Send EEPROM data
            for _ in range(len(self.records)):
                record = self.get_next_packet()
                if record and record.packet_type == 'EEPROM_DATA':
                    self._log(f"→ Sending EEPROM data ({len(record.data)} bytes)")
                    self.send_packet(record.data)
                    break
            return True
        
        else:
            self._log(f"← Unknown command: {command}")
            return False
    
    def streaming_loop(self):
        """Continuous streaming thread - sends data every 5 seconds."""
        self._log(f"▶ Streaming started (every {self.interval}s)")
        
        while not self.stop_streaming.is_set():
            try:
                # Get next packet
                record = self.get_next_packet()
                
                if record:
                    data_preview = record.data[:50] + '...' if len(record.data) > 50 else record.data
                    self._log(f"→ TX [{record.packet_type}] {len(record.data)} bytes | {data_preview}")
                    
                    if not self.send_packet(record.data):
                        self._log("Connection lost, stopping stream")
                        break
                
                # Wait interval (5 seconds for real device timing)
                self.stop_streaming.wait(self.interval)
            
            except Exception as e:
                self._log(f"ERROR in streaming loop: {e}")
                break
        
        self.streaming = False
        self._log(f"⏸ Streaming stopped (sent {self.packets_sent} packets, {self.loop_count} loops)")
    
    def start_streaming(self):
        """Start continuous streaming."""
        if self.streaming:
            return
        
        self.streaming = True
        self.stop_streaming.clear()
        self.streaming_thread = threading.Thread(target=self.streaming_loop, daemon=True)
        self.streaming_thread.start()
    
    def stop_streaming_flag(self):
        """Signal streaming thread to stop."""
        self.stop_streaming.set()
        self.streaming = False
    
    def handle_client(self):
        """Handle client connection and commands."""
        self._log(f"✓ Client connected: {self.client_address}")
        
        buffer = ""
        
        try:
            while True:
                data = self.client_socket.recv(4096).decode('utf-8', errors='ignore')
                
                if not data:
                    self._log("Client disconnected")
                    break
                
                buffer += data
                
                # Process complete commands (terminated by newline or specific chars)
                while '\n' in buffer or '\r' in buffer:
                    if '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                    else:
                        line, buffer = buffer.split('\r', 1)
                    
                    line = line.strip()
                    if line:
                        self.handle_command(line)
        
        except Exception as e:
            self._log(f"ERROR handling client: {e}")
        
        finally:
            # Stop streaming if active
            if self.streaming:
                self.stop_streaming_flag()
            
            if self.client_socket:
                self.client_socket.close()
            
            self.client_socket = None
            self.client_address = None
            self._log("Client connection closed")
    
    def start_server(self):
        """Start TCP server and listen for connections."""
        if not self.records:
            self._log("ERROR: No data loaded, cannot start server")
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            
            self._log(f"✓ Server listening on {self.host}:{self.port}")
            self._log(f"Ready to replay {len(self.records)} packets in loop")
            self._log(f"Waiting for client connection...")
            
            while True:
                try:
                    self.client_socket, self.client_address = self.server_socket.accept()
                    self.handle_client()
                except KeyboardInterrupt:
                    self._log("Server shutdown requested")
                    break
                except Exception as e:
                    self._log(f"ERROR accepting connection: {e}")
                    time.sleep(1)
        
        except Exception as e:
            self._log(f"ERROR starting server: {e}")
        
        finally:
            if self.streaming:
                self.stop_streaming_flag()
            
            if self.server_socket:
                self.server_socket.close()
            
            self._log("Server stopped")
    
    def run(self):
        """Main entry point - load data and start server."""
        self._log("="*60)
        self._log("PFDS Device Simulator v3 - Real Data Replay")
        self._log("="*60)
        
        if not self.load_data():
            self._log("FATAL: Failed to load data file")
            return 1
        
        try:
            self.start_server()
        except KeyboardInterrupt:
            self._log("\nShutdown by user")
        
        return 0


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description='PFDS Device Simulator v3 - Replays real device data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: localhost:9001, 5-second interval
  python pfdsdevicesimulator.py
  
  # Custom port and interval
  python pfdsdevicesimulator.py --port 9002 --interval 3.0
  
  # Listen on all interfaces
  python pfdsdevicesimulator.py --host 0.0.0.0 --port 9001
  
  # Custom data file
  python pfdsdevicesimulator.py --data my_data.txt

Protocol Commands:
  PERIOD_ON  : Start continuous streaming (every 5 seconds)
  PERIOD_OFF : Stop streaming
  REQUEST1   : Request single thermal frame
  EEPROM1    : Request calibration data
        """
    )
    
    parser.add_argument('--host', default='0.0.0.0', 
                       help='Server host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=9001, 
                       help='Server port (default: 9001)')
    parser.add_argument('--data', default='data/NEW DATA 10 MINS.txt',
                       help='Data file to replay (default: data/NEW DATA 10 MINS.txt)')
    parser.add_argument('--interval', type=float, default=5.0,
                       help='Transmission interval in seconds (default: 5.0, real device timing)')
    
    args = parser.parse_args()
    
    simulator = EmberHawkSimulator(
        host=args.host,
        port=args.port,
        data_file=args.data,
        interval=args.interval
    )
    
    return simulator.run()


if __name__ == '__main__':
    exit(main())
