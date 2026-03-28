
# ============================================================
# DEPRECATED — DO NOT USE IN NEW CODE
# This threaded TCP server is retired as of 2026-03-13.
# It uses an IP-keyed client map that causes identity collisions
# when multiple devices connect from the same host (e.g. localhost
# simulators), leading to missed packets for some rooms.
#
# Use embereye.core.tcp_async_server.TCPAsyncSensorServer instead.
# The field app enforces this via tcp_mode=async in stream_config.json.
#
# This file is kept only for reference and legacy test compatibility.
# It will be removed in a future cleanup pass.
# ============================================================

import socket
import threading
import time
from time import time as now_time
import json
import os
import sys
import json as jsonlib
import warnings

from embereye_base.core.thermal_decoder_bridge import (
    decode_frame_to_matrix,
    parse_eeprom_packet,
)
from embereye_base.core.thermal_frame_parser import ThermalFrameParser


def safe_flush():
    """Safely flush stdout, handling PyInstaller EXE mode where stdout may be None"""
    try:
        if sys.stdout and hasattr(sys.stdout, 'flush'):
            sys.stdout.flush()
    except (AttributeError, ValueError):
        pass  # Ignore if stdout is None or closed


class TCPSensorServer:
    def __init__(self, host='0.0.0.0', port=None, packet_callback=None, disconnect_callback=None,
                 auto_request_eeprom_on_connect=True, collect_eeprom_until_received=True,
                 eeprom_retry_interval_seconds=8.0):
        warnings.warn(
            "TCPSensorServer (threaded) is DEPRECATED and will be removed. "
            "Use TCPAsyncSensorServer (tcp_mode=async in stream_config.json) instead. "
            "Threaded mode causes IP-keyed identity collisions for multi-device localhost setups.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.host = host
        self.port = port if port is not None else self._get_config_port()
        self.server_socket = None
        self.running = False
        self.thread = None
        self.packet_callback = packet_callback  # Function to call with parsed packet
        self.disconnect_callback = disconnect_callback  # Function to call when client disconnects
        self._client_sockets = {}  # Track active client connections: {ip: socket}
        self._serial_to_ip = {}  # Track latest serial -> client ip binding
        self._ip_to_serial = {}  # Track latest client ip -> serial binding
        self._socket_lock = threading.Lock()  # Lock for thread-safe socket access
        self._client_eeprom_hex = {}  # Track latest valid EEPROM1 payload per client
        self._client_eeprom_requested = {}  # Track EEPROM1 command sent per client
        self._client_last_eeprom_request = {}  # Track latest EEPROM1 command timestamp per client
        self.auto_request_eeprom_on_connect = bool(auto_request_eeprom_on_connect)
        self.collect_eeprom_until_received = bool(collect_eeprom_until_received)
        self.eeprom_retry_interval_seconds = max(2.0, float(eeprom_retry_interval_seconds))

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
        
        # AUTO-SEND commands on connect to start streaming and register device identity.
        # `\n` is required so the device's line-based command parser can delimit each command.
        import time
        time.sleep(0.1)
        try:
            print(f"📤 Auto-sending DEVICE_ID to device at IP: {client_ip}", flush=True)
            client_sock.sendall("DEVICE_ID\n".encode('ascii'))
            print(f"✅ DEVICE_ID query sent to device IP: {client_ip}", flush=True)
        except Exception as e:
            print(f"⚠️  Failed to send DEVICE_ID to device IP {client_ip}: {e}", flush=True)
        try:
            print(f"📤 Auto-sending PERIOD_ON to device at IP: {client_ip}", flush=True)
            client_sock.sendall("PERIOD_ON\n".encode('ascii'))
            print(f"✅ PERIOD_ON successfully sent to device IP: {client_ip}", flush=True)
        except Exception as e:
            print(f"⚠️  Failed to auto-send PERIOD_ON to device IP {client_ip}: {e}", flush=True)

        if self.auto_request_eeprom_on_connect:
            try:
                print(f"📤 Auto-sending EEPROM1 to device at IP: {client_ip}", flush=True)
                client_sock.sendall("EEPROM1\n".encode('ascii'))
                self._client_eeprom_requested[client_ip] = True
                self._client_last_eeprom_request[client_ip] = now_time()
                print(f"✅ EEPROM1 request sent to device IP: {client_ip}", flush=True)
            except Exception as e:
                print(f"⚠️  Failed to auto-send EEPROM1 to device IP {client_ip}: {e}", flush=True)

        eeprom_collector_stop = threading.Event()
        eeprom_collector_thread = None
        if self.collect_eeprom_until_received:
            eeprom_collector_thread = threading.Thread(
                target=self._eeprom_collect_loop,
                args=(client_sock, client_ip, eeprom_collector_stop),
                daemon=True,
            )
            eeprom_collector_thread.start()
        
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
                                from embereye_base.utils.tcp_logger import log_raw_packet
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
                                    from embereye_base.utils.tcp_logger import log_error_packet
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
            eeprom_collector_stop.set()
            if eeprom_collector_thread and eeprom_collector_thread.is_alive():
                eeprom_collector_thread.join(timeout=1.0)
            # Unregister client socket
            with self._socket_lock:
                if client_ip in self._client_sockets:
                    del self._client_sockets[client_ip]
                serial = self._ip_to_serial.pop(client_ip, None)
                if serial and self._serial_to_ip.get(serial) == client_ip:
                    self._serial_to_ip.pop(serial, None)
            self._client_eeprom_hex.pop(client_ip, None)
            self._client_eeprom_requested.pop(client_ip, None)
            self._client_last_eeprom_request.pop(client_ip, None)
            
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

    def send_command_to_client(self, target: str, command: str) -> bool:
        """Send a command to a connected client by IP address or serial number.
        Returns True if sent successfully, False otherwise.
        Thread-safe.
        
        If exact IP not found, tries to find client by matching last octet (for NAT/localhost scenarios).
        """
        with self._socket_lock:
            client_sock = None
            matched_ip = None
            token = str(target or "").strip()
            
            # Try exact match first
            if token in self._client_sockets:
                client_sock = self._client_sockets[token]
                matched_ip = token
            elif token in self._serial_to_ip and self._serial_to_ip[token] in self._client_sockets:
                matched_ip = self._serial_to_ip[token]
                client_sock = self._client_sockets[matched_ip]
            else:
                now = now_time()
                if not hasattr(self, '_no_connection_warn_ts'):
                    self._no_connection_warn_ts = {}
                warn_key = token
                last_warn = float(self._no_connection_warn_ts.get(warn_key, 0.0))
                if now - last_warn >= 30.0:
                    print(f"❌ No active connection for target {token}. Connected clients: {list(self._client_sockets.keys())} serials: {list(self._serial_to_ip.keys())} (repeated logs suppressed)")
                    self._no_connection_warn_ts[warn_key] = now
                return False
        
        try:
            print(f"📤 Sending command '{command}' to device IP: {matched_ip} (target={token})")
            client_sock.sendall((str(command).rstrip('\n') + '\n').encode('ascii', errors='ignore'))
            print(f"✅ Command '{command}' successfully sent to device IP: {matched_ip}")
            cmd = (command or "").strip().upper()
            if cmd == "EEPROM1":
                self._client_eeprom_requested[matched_ip] = True
            return True
        except Exception as e:
            print(f"❌ Failed to send command to {matched_ip}: {e}")
            # Remove dead connection
            with self._socket_lock:
                if matched_ip in self._client_sockets:
                    del self._client_sockets[matched_ip]
            return False

    def request_eeprom1(self, ip_or_serial: str) -> bool:
        return self.send_command_to_client(ip_or_serial, "EEPROM1")

    def _eeprom_collect_loop(self, client_sock, client_ip: str, stop_event: threading.Event):
        while self.running and not stop_event.is_set():
            if client_ip in self._client_eeprom_hex:
                return

            last_sent = float(self._client_last_eeprom_request.get(client_ip, 0.0))
            if now_time() - last_sent >= self.eeprom_retry_interval_seconds:
                try:
                    client_sock.sendall("EEPROM1\n".encode('ascii'))
                    self._client_eeprom_requested[client_ip] = True
                    self._client_last_eeprom_request[client_ip] = now_time()
                except Exception:
                    return

            stop_event.wait(timeout=1.0)

    def request_one_time_frame(self, ip_or_serial: str) -> bool:
        return self.send_command_to_client(ip_or_serial, "REQUEST1")

    def _bind_serial_to_client(self, serial: str, client_ip: str) -> None:
        serial_key = str(serial or "").strip()
        ip_key = str(client_ip or "").strip()
        if not serial_key or not ip_key:
            return
        with self._socket_lock:
            self._serial_to_ip[serial_key] = ip_key
            self._ip_to_serial[ip_key] = serial_key

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
                    self._bind_serial_to_client(serial, client_ip)
            except Exception as e:
                print(f"Serialno parse error: {e}")
                try:
                    from embereye_base.utils.tcp_logger import log_error_packet
                    log_error_packet(reason=f"serialno parse error: {e}", raw=line, loc_id=client_ip)
                except Exception:
                    pass
        elif line.startswith('#DEVICE_ID:'):
            # Example: #DEVICE_ID:1829602101142!
            try:
                serial = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'device_id', 'serial_number': serial}
                if client_ip:
                    result['client_ip'] = client_ip
                    self._bind_serial_to_client(serial, client_ip)
            except Exception as e:
                print(f"DEVICE_ID parse error: {e}")
                try:
                    from embereye_base.utils.tcp_logger import log_error_packet
                    log_error_packet(reason=f"DEVICE_ID parse error: {e}", raw=line, loc_id=client_ip)
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
                    from embereye_base.utils.tcp_logger import log_error_packet
                    log_error_packet(reason=f"loc_id parse error: {e}", raw=line, loc_id=client_ip)
                except Exception:
                    pass
        elif line.startswith('#EEPROM'):
            try:
                parsed = parse_eeprom_packet(line)
                if parsed.get('success'):
                    self._client_eeprom_hex[client_ip] = parsed['hex']
                    result = {
                        'type': 'eeprom',
                        'frame_id': parsed.get('frame_id'),
                        'blocks': parsed.get('blocks'),
                        'client_ip': client_ip,
                    }
                    serial = self._ip_to_serial.get(client_ip)
                    if serial:
                        result['serial_number'] = serial
                    print(f"✅ EEPROM cached for {client_ip}: {parsed.get('blocks')} blocks")
                else:
                    print(f"⚠️ EEPROM parse failed from {client_ip}: {parsed.get('error')}")
            except Exception as e:
                print(f"EEPROM parse error: {e}")
                try:
                    from embereye_base.utils.tcp_logger import log_error_packet
                    log_error_packet(reason=f"eeprom parse error: {e}", raw=line[:100]+"...", loc_id=client_ip)
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
                    
                    frame_data_clean = frame_data.replace(" ", "").replace("\n", "").strip()

                    decoded = decode_frame_to_matrix(
                        frame_data_clean,
                        eeprom_hex=self._client_eeprom_hex.get(client_ip),
                    )

                    if decoded.get('success'):
                        result = {
                            'type': 'frame',
                            'matrix': decoded['matrix'],
                            'loc_id': loc_id,
                            'rows': decoded.get('rows', 24),
                            'cols': decoded.get('cols', 32),
                            'eeprom_source': decoded.get('eeprom_source', 'unknown'),
                        }
                        if client_ip:
                            result['client_ip'] = client_ip
                            serial = self._ip_to_serial.get(client_ip)
                            if serial:
                                result['serial_number'] = serial
                    else:
                        # Fallback for grid-only/legacy packets
                        if ' ' in frame_data:
                            hex_values = frame_data.split()
                            if len(hex_values) == 32 * 24:
                                matrix = [[int(hex_values[row * 32 + col], 16) for col in range(32)] for row in range(24)]
                                result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id}
                                if client_ip:
                                    result['client_ip'] = client_ip
                                    serial = self._ip_to_serial.get(client_ip)
                                    if serial:
                                        result['serial_number'] = serial
                        elif len(frame_data_clean) == 32 * 24 * 4:
                            hex_values = [frame_data_clean[i:i + 4] for i in range(0, len(frame_data_clean), 4)]
                            matrix = [[int(hex_values[row * 32 + col], 16) for col in range(32)] for row in range(24)]
                            result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id}
                            if client_ip:
                                result['client_ip'] = client_ip
                                serial = self._ip_to_serial.get(client_ip)
                                if serial:
                                    result['serial_number'] = serial
                        elif len(frame_data_clean) >= 32 * 24 * 4 + 66 * 4:
                            # Fallback: parse 834-word raw frame without EEPROM1 (best-effort rendering)
                            try:
                                frame_payload = frame_data_clean[: (32 * 24 * 4 + 66 * 4)]
                                parsed = ThermalFrameParser.parse_frame(frame_payload)
                                matrix = parsed.get('grid')
                                if matrix is not None:
                                    result = {
                                        'type': 'frame',
                                        'matrix': matrix.tolist() if hasattr(matrix, 'tolist') else matrix,
                                        'loc_id': loc_id,
                                        'rows': parsed.get('rows', 24),
                                        'cols': parsed.get('cols', 32),
                                        'eeprom_source': 'fallback_parser',
                                    }
                                    if client_ip:
                                        result['client_ip'] = client_ip
                                        serial = self._ip_to_serial.get(client_ip)
                                        if serial:
                                            result['serial_number'] = serial
                            except Exception as parse_exc:
                                print(f"Frame fallback parse error: {parse_exc}")
                        else:
                            print(f"Frame decode failed ({decoded.get('error')}); length={len(frame_data_clean)}")
                else:
                    print(f"Frame parse error: no colon separator")
                    try:
                        from embereye_base.utils.tcp_logger import log_error_packet
                        log_error_packet(reason="frame no colon", loc_id=client_ip, raw=line[:100]+"...")
                    except Exception:
                        pass
            except Exception as e:
                print(f"Frame parse error: {e}")
                try:
                    from embereye_base.utils.tcp_logger import log_error_packet
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
                            key_lower = k.lower()
                            if key_lower in ('serial', 'serialno', 'serial_number', 'device_id'):
                                sensors['serial_number'] = str(v)
                                continue
                            try:
                                sensors[k] = float(v) if '.' in v else int(v)
                            except Exception:
                                # Keep parser resilient to mixed string fields in sensor payloads.
                                sensors[k] = str(v)
                    result = {'type': 'sensor', 'loc_id': loc_id, **sensors}
                    if client_ip:
                        result['client_ip'] = client_ip
                        serial = result.get('serial_number') or self._ip_to_serial.get(client_ip)
                        if serial:
                            result['serial_number'] = serial
                            self._bind_serial_to_client(serial, client_ip)
                else:
                    print(f"Sensor parse error: no colon separator")
                    try:
                        from embereye_base.utils.tcp_logger import log_error_packet
                        log_error_packet(reason="sensor no colon", loc_id=client_ip, raw=line)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Sensor parse error: {e}")
                try:
                    from embereye_base.utils.tcp_logger import log_error_packet
                    log_error_packet(reason=f"sensor parse error: {e}", loc_id=client_ip, raw=line)
                except Exception:
                    pass
        else:
            print(f"Unknown packet type: {line[:50]}...")
            try:
                from embereye_base.utils.tcp_logger import log_error_packet
                log_error_packet(reason="unknown packet type", loc_id=client_ip, raw=line[:100]+"...")
            except Exception:
                pass
        if result:
            # Do not print parsed packet to console in production; handled via debug logs
            if self.packet_callback:
                pkt_type = result.get('type', 'unknown')
                print(f"📡 TCP CALLBACK: type={pkt_type}, loc_id={result.get('loc_id')}, keys={list(result.keys())}")
                try:
                    self.packet_callback(result)
                    print(f"✅ Callback executed for {pkt_type} packet")
                except Exception as e:
                    print(f"❌ Callback error: {e}")



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
