
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
    def __init__(self, host='0.0.0.0', port=None, packet_callback=None):
        self.host = host
        self.port = port if port is not None else self._get_config_port()
        self.server_socket = None
        self.running = False
        self.thread = None
        self.packet_callback = packet_callback  # Function to call with parsed packet

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
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"TCP Server listening, waiting for connections...", flush=True)
        while self.running:
            try:
                print(f"About to accept...", flush=True)
                client_sock, addr = self.server_socket.accept()
                print(f"Accepted connection from {addr}", flush=True)
                threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True).start()
            except Exception as e:
                if self.running:
                    print(f"Accept error: {e}", flush=True)

    def handle_client(self, client_sock):
        client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        print(f"Client handler started", flush=True)
        buffer = ''
        try:
            while self.running:
                try:
                    data = client_sock.recv(4096)
                    if not data:
                        print("Client disconnected")
                        break
                    buffer += data.decode('utf-8', errors='ignore')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            # Debug log raw packet
                            try:
                                from tcp_logger import log_raw_packet
                                log_raw_packet(line)
                            except Exception:
                                pass
                            try:
                                self.handle_packet(line)
                            except Exception as e:
                                print(f"Packet handling error: {e}")
                                try:
                                    from tcp_logger import log_error_packet
                                    log_error_packet(reason=str(e), raw=line)
                                except Exception:
                                    pass
                                # Continue processing other packets
                except Exception as e:
                    print(f"Client recv error: {e}")
                    break
        finally:
            try:
                client_sock.close()
            except:
                pass
            print("Client handler stopped")

    def handle_packet(self, line):
        """Parse incoming sensor packets and invoke callback with structured data."""
        result = None
        if line.startswith('#serialno:'):
            # Example: #serialno:123456!
            try:
                serial = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'serialno', 'serialno': serial}
            except Exception as e:
                print(f"Serialno parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"serialno parse error: {e}", raw=line)
                except Exception:
                    pass
        elif line.startswith('#locid:'):
            # Example: #locid:default room!
            try:
                loc_id = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'locid', 'loc_id': loc_id}
            except Exception as e:
                print(f"Loc_id parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"loc_id parse error: {e}", raw=line)
                except Exception:
                    pass
        elif line.startswith('#frame:'):
            # Example: #frame:default room:0102 0103 ... 0320! or #frame:0102 0103 ... 0320! (legacy)
            try:
                parts = line.split(':', 2)
                if len(parts) == 3:  # New format with loc_id
                    loc_id = parts[1].strip()
                    frame_data = parts[2].rstrip('!').strip()
                else:  # Legacy format without loc_id
                    loc_id = None
                    frame_data = parts[1].rstrip('!').strip()
                hex_values = frame_data.split()
                if len(hex_values) == 32*24:
                    matrix = [[int(hex_values[row*32+col], 16) for col in range(32)] for row in range(24)]
                    result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id}
                else:
                    print(f"Frame parse error: expected 768 values, got {len(hex_values)}")
                    try:
                        from tcp_logger import log_error_packet
                        log_error_packet(reason=f"frame count {len(hex_values)}", raw=line)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Frame parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"frame parse error: {e}", raw=line)
                except Exception:
                    pass
        elif line.startswith('#Sensor:'):
            # Example: #Sensor:default room:ADC1=1234,ADC2=5678,MPY30=1! or #Sensor:ADC1=... (legacy)
            try:
                parts = line.split(':', 2)
                if len(parts) == 3:  # New format with loc_id
                    loc_id = parts[1].strip()
                    sensor_data = parts[2].rstrip('!').strip()
                else:  # Legacy format without loc_id
                    loc_id = None
                    sensor_data = parts[1].rstrip('!').strip()
                sensors = {}
                for part in sensor_data.split(','):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        sensors[k.strip()] = float(v.strip()) if '.' in v else int(v.strip())
                result = {'type': 'sensor', 'loc_id': loc_id, **sensors}
            except Exception as e:
                print(f"Sensor parse error: {e}")
                try:
                    from tcp_logger import log_error_packet
                    log_error_packet(reason=f"sensor parse error: {e}", raw=line)
                except Exception:
                    pass
        else:
            print(f"Unknown packet type: {line}")
            try:
                from tcp_logger import log_error_packet
                log_error_packet(reason="unknown packet type", raw=line)
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
