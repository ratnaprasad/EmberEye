
import socket
import threading
import json
import os
import sys
import json as jsonlib


def safe_flush():
    """Safely flush stdout, handling PyInstaller EXE mode where stdout may be None"""
    try:
        if sys.stdout and hasattr(sys.stdout, 'flush'):
            sys.stdout.flush()
    except (AttributeError, ValueError):
        pass  # Ignore if stdout is None or closed


class TCPSensorServer:
    def __init__(self, host='0.0.0.0', port=None, packet_callback=None, disconnect_callback=None):
        self.host = host
        self.port = port if port is not None else self._get_config_port()
        self.server_socket = None
        self.running = False
        self.thread = None
        self.packet_callback = packet_callback  # Function to call with parsed packet
        self.disconnect_callback = disconnect_callback  # Function to call when client disconnects
        self._client_sockets = {}  # Track active client connections: {ip: socket}
        self._socket_lock = threading.Lock()  # Lock for thread-safe socket access

    def _get_config_port(self):
        config_path = os.path.join(os.path.dirname(__file__), 'stream_config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = jsonlib.load(f)
                    port = config.get('tcp_port')
                    if port:
                        return int(port)
        except Exception as e:
            print(f"Config port read error: {e}")
        return 9000  # default

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self.run_server, daemon=True)
        self.thread.start()
        print(f"TCP Sensor Server started on {self.host}:{self.port}")
        safe_flush()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                print(f"Error closing server socket: {e}")
        if self.thread:
            self.thread.join(timeout=5)
        print("TCP Sensor Server stopped")

    def run_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)  # Set timeout to allow clean shutdown
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"TCP Server listening on {self.host}:{self.port}", flush=True)
        except Exception as e:
            print(f"Failed to start TCP server: {e}", flush=True)
            return
            
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                print(f"Accepted connection from {addr}", flush=True)
                threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True).start()
            except socket.timeout:
                # Normal timeout, continue loop
                continue
            except Exception as e:
                if self.running:
                    print(f"Accept error: {e}", flush=True)

    def handle_client(self, client_sock):
        client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        client_sock.settimeout(30.0)  # 30 second timeout for client operations
        # Get client IP address
        try:
            client_ip = client_sock.getpeername()[0]
        except Exception:
            client_ip = "unknown"
        
        # Register client socket
        with self._socket_lock:
            self._client_sockets[client_ip] = client_sock
        
        print(f"Client handler started for {client_ip}", flush=True)
        print(f"🔌 Device connected from IP: {client_ip}", flush=True)
        
        # AUTO-SEND PERIOD_ON to start continuous streaming from thermal devices
        # Wait a moment for socket to stabilize
        import time
        time.sleep(0.1)
        try:
            print(f"📤 Auto-sending PERIOD_ON to device at IP: {client_ip}", flush=True)
            client_sock.sendall("PERIOD_ON\n".encode('utf-8'))
            print(f"✅ PERIOD_ON successfully sent to device IP: {client_ip}", flush=True)
        except Exception as e:
            print(f"⚠️  Failed to auto-send PERIOD_ON to device IP {client_ip}: {e}", flush=True)
        
        buffer = ''
        try:
            while self.running:
                try:
                    data = client_sock.recv(4096)
                    if not data:
                        print(f"Client {client_ip} disconnected")
                        break
                    buffer += data.decode('utf-8', errors='ignore')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            # Debug log raw packet
                            try:
                                from tcp_logger import log_raw_packet
                                log_raw_packet(line, locationId=client_ip)
                            except Exception as e:
                                print(f"TCP logger error: {e}")
                                import traceback
                                traceback.print_exc()
                            try:
                                self.handle_packet(line, client_ip)
                            except Exception as e:
                                print(f"Packet handling error: {e}")
                                try:
                                    from tcp_logger import log_error_packet
                                    log_error_packet(reason=str(e), raw=line, loc_id=client_ip)
                                except Exception:
                                    pass
                                # Continue processing other packets
                except socket.timeout:
                    # Timeout is normal, continue loop
                    if not self.running:
                        break
                    continue
                except Exception as e:
                    print(f"Client recv error: {e}")
                    break
        finally:
            # Unregister client socket
            with self._socket_lock:
                if client_ip in self._client_sockets:
                    del self._client_sockets[client_ip]
            
            # Notify about disconnection
            if self.disconnect_callback:
                try:
                    self.disconnect_callback(client_ip)
                except Exception as e:
                    print(f"Disconnect callback error: {e}")
            
            try:
                client_sock.close()
            except:
                pass
            print(f"Client handler stopped for {client_ip}")

    def send_command_to_client(self, ip: str, command: str) -> bool:
        """Send a command to a connected client by IP address.
        Returns True if sent successfully, False otherwise.
        Thread-safe.
        
        If exact IP not found, tries to find client by matching last octet (for NAT/localhost scenarios).
        """
        with self._socket_lock:
            client_sock = None
            matched_ip = None
            
            # Try exact match first
            if ip in self._client_sockets:
                client_sock = self._client_sockets[ip]
                matched_ip = ip
            else:
                # Try to match if there's only one connected client (common case)
                if len(self._client_sockets) == 1:
                    matched_ip = list(self._client_sockets.keys())[0]
                    client_sock = self._client_sockets[matched_ip]
                    print(f"🔄 IP mismatch: configured={ip}, actual={matched_ip}. Using actual IP (single client).")
                else:
                    print(f"❌ No active connection for IP {ip}. Connected clients: {list(self._client_sockets.keys())}")
                    return False
        
        try:
            print(f"📤 Sending command '{command}' to device IP: {matched_ip} (configured as {ip})")
            client_sock.sendall((command + "\n").encode('utf-8'))
            print(f"✅ Command '{command}' successfully sent to device IP: {matched_ip}")
            return True
        except Exception as e:
            print(f"❌ Failed to send command to {matched_ip}: {e}")
            # Remove dead connection
            with self._socket_lock:
                if matched_ip in self._client_sockets:
                    del self._client_sockets[matched_ip]
            return False

    def handle_packet(self, line, client_ip=None):
        """Parse incoming sensor packets and invoke callback with structured data.
        
        Args:
            line: The packet string to parse
            client_ip: IP address of the client sending the packet (used as fallback loc_id)
        """
        result = None
        if line.startswith('#serialno:'):
            # Example: #serialno:123456!
            try:
                serial = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'serialno', 'serialno': serial}
                # Add client IP as fallback identifier
                if client_ip:
                    result['client_ip'] = client_ip
            except Exception as e:
                print(f"Serialno parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"serialno parse error: {e}", raw=line, loc_id=client_ip)
                except Exception:
                    pass
        elif line.startswith('#locid:'):
            # Example: #locid:default room!
            try:
                loc_id = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'locid', 'loc_id': loc_id}
                if client_ip:
                    result['client_ip'] = client_ip
            except Exception as e:
                print(f"Loc_id parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"loc_id parse error: {e}", raw=line, loc_id=client_ip)
                except Exception:
                    pass
        elif line.startswith('#frame'):
            # Supports multiple formats:
            # 1. #frame1234:FFCCFFC7...! (loc_id embedded: frame1234)
            # 2. #frame:default room:0102 0103...! (loc_id as separate field)
            # 3. #frame:0102 0103...! (no loc_id)
            try:
                # Remove '#' prefix and '!' suffix
                content = line[1:].rstrip('!')
                
                # Split on first colon to separate packet type from data
                if ':' in content:
                    prefix, data = content.split(':', 1)
                    
                    # Check if loc_id is embedded in prefix (e.g., "frame1234")
                    if prefix.startswith('frame') and len(prefix) > 5:
                        loc_id = prefix[5:]  # Extract loc_id from "frame1234"
                        frame_data = data.strip()
                    else:
                        # Check for additional colon indicating separate loc_id field
                        if ':' in data:
                            loc_id, frame_data = data.split(':', 1)
                            loc_id = loc_id.strip()
                            frame_data = frame_data.strip()
                        else:
                            loc_id = None
                            frame_data = data.strip()
                    
                    # Resolve/fallback loc_id: default to client IP when not provided
                    if not loc_id:
                        loc_id = client_ip
                    
                    # Parse frame data using thermal_frame_parser
                    # Expected: 834 word blocks (4 chars each) = 3336 chars total
                    # Grid: 768 blocks (24x32) = 3072 chars
                    # EEPROM: 66 blocks = 264 chars
                    try:
                        from thermal_frame_parser import ThermalFrameParser
                        
                        # Remove any spaces/whitespace
                        frame_data_clean = frame_data.replace(" ", "").replace("\n", "").strip()
                        
                        if len(frame_data_clean) == ThermalFrameParser.FRAME_TOTAL_SIZE:
                            # Parse using thermal frame parser
                            parsed = ThermalFrameParser.parse_frame(frame_data_clean)
                            
                            # Convert numpy grid to list for JSON serialization
                            matrix = parsed['grid'].tolist()
                            
                            result = {
                                'type': 'frame',
                                'matrix': matrix,
                                'loc_id': loc_id,
                                'rows': parsed['rows'],
                                'cols': parsed['cols'],
                                'eeprom': parsed['eeprom']  # Keep EEPROM data for diagnostics
                            }
                            if client_ip:
                                result['client_ip'] = client_ip
                        else:
                            print(f"Frame parse error: expected {ThermalFrameParser.FRAME_TOTAL_SIZE} chars, got {len(frame_data_clean)}")
                            try:
                                from tcp_logger import log_error_packet
                                log_error_packet(
                                    reason=f"frame length {len(frame_data_clean)} (expected {ThermalFrameParser.FRAME_TOTAL_SIZE})",
                                    loc_id=loc_id or client_ip,
                                    raw=line[:100]+"..."
                                )
                            except Exception:
                                pass
                    except ImportError:
                        # Fallback to old parsing if thermal_frame_parser not available
                        print("Warning: thermal_frame_parser not found, using legacy parsing")
                        # Parse frame data - supports both space-separated hex (0102 0103) and continuous hex (FFCCFFC7)
                        if ' ' in frame_data:
                            # Space-separated format
                            hex_values = frame_data.split()
                            if len(hex_values) == 32*24:
                                matrix = [[int(hex_values[row*32+col], 16) for col in range(32)] for row in range(24)]
                                result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id}
                                if client_ip:
                                    result['client_ip'] = client_ip
                            else:
                                print(f"Frame parse error: expected 768 values, got {len(hex_values)}")
                        else:
                            # Continuous hex format - assume 3072 chars (24x32 grid only)
                            expected_chars = 32 * 24 * 4  # 3072 hex characters
                            if len(frame_data) == expected_chars:
                                hex_values = [frame_data[i:i+4] for i in range(0, len(frame_data), 4)]
                                matrix = [[int(hex_values[row*32+col], 16) for col in range(32)] for row in range(24)]
                                result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id}
                                if client_ip:
                                    result['client_ip'] = client_ip
                else:
                    print(f"Frame parse error: no colon separator")
                    try:
                        from tcp_logger import log_error_packet
                        log_error_packet(reason="frame no colon", loc_id=client_ip, raw=line[:100]+"...")
                    except Exception:
                        pass
            except Exception as e:
                print(f"Frame parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"frame parse error: {e}", loc_id=client_ip, raw=line[:100]+"...")
                except Exception:
                    pass
        elif line.startswith('#Sensor'):
            # Supports multiple formats:
            # 1. #Sensor1234:ADC1=592,...! (loc_id embedded: Sensor1234)
            # 2. #Sensor:default room:ADC1=...! (loc_id as separate field)
            # 3. #Sensor:ADC1=...! (no loc_id)
            try:
                # Remove '#' prefix and '!' suffix
                content = line[1:].rstrip('!')
                
                # Split on first colon
                if ':' in content:
                    prefix, data = content.split(':', 1)
                    
                    # Check if loc_id is embedded in prefix (e.g., "Sensor1234")
                    if prefix.startswith('Sensor') and len(prefix) > 6:
                        loc_id = prefix[6:]  # Extract loc_id from "Sensor1234"
                        sensor_data = data.strip()
                    else:
                        # Check for additional colon indicating separate loc_id field
                        if ':' in data:
                            loc_id, sensor_data = data.split(':', 1)
                            loc_id = loc_id.strip()
                            sensor_data = sensor_data.strip()
                        else:
                            loc_id = None
                            sensor_data = data.strip()
                    
                    # Resolve/fallback loc_id: default to client IP when not provided
                    if not loc_id:
                        loc_id = client_ip
                    
                    sensors = {}
                    for part in sensor_data.split(','):
                        if '=' in part:
                            k, v = part.split('=', 1)
                            # Handle malformed entries like "ADC3:=905" (extra colon)
                            k = k.strip().rstrip(':')
                            v = v.strip()
                            sensors[k] = float(v) if '.' in v else int(v)
                    result = {'type': 'sensor', 'loc_id': loc_id, **sensors}
                    if client_ip:
                        result['client_ip'] = client_ip
                else:
                    print(f"Sensor parse error: no colon separator")
                    try:
                        from tcp_logger import log_error_packet
                        log_error_packet(reason="sensor no colon", loc_id=client_ip, raw=line)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Sensor parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"sensor parse error: {e}", loc_id=client_ip, raw=line)
                except Exception:
                    pass
        else:
            print(f"Unknown packet type: {line[:50]}...")
            try:
                from tcp_logger import log_error_packet
                log_error_packet(reason="unknown packet type", loc_id=client_ip, raw=line[:100]+"...")
            except Exception:
                pass
        if result:
            # Do not print parsed packet to console in production; handled via debug logs
            if self.packet_callback:
                self.packet_callback(result)


if __name__ == "__main__":
    def print_packet(packet):
        print(f"Callback: {packet}")
    server = TCPSensorServer(packet_callback=print_packet)
    try:
        server.start()
        while True:
            pass
    except KeyboardInterrupt:
        server.stop()
