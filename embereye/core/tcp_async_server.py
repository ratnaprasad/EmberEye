import asyncio
import os
import json as jsonlib
import re
from typing import Callable, Dict, Any
import numpy as np

from tcp_logger import log_raw_packet, log_error_packet
from tcp_server_logger import log_info, log_debug, log_warning, log_error as log_server_error
from metrics import get_metrics
from embereye.core.thermal_decoder_bridge import decode_frame_to_matrix, parse_eeprom_packet
from embereye.core.thermal_frame_parser import ThermalFrameParser

class TCPAsyncSensorServer:
    """High-performance asyncio-based TCP sensor server with queue-based packet processing.

    Features:
    - Single-threaded event loop (no Qt cross-thread violations)
    - Backpressure via asyncio.Queue (drops oldest on overflow)
    - Batch processing of packets to reduce per-line overhead
    - Reuses existing packet parsing logic (adapted)
    """

    def __init__(self, host: str = '0.0.0.0', port: int | None = None, packet_callback: Callable[[Dict[str, Any]], None] | None = None,
                 max_queue: int = 10000, batch_interval_ms: int = 50,
                 auto_request_eeprom_on_connect: bool = True,
                 collect_eeprom_until_received: bool = True,
                 eeprom_retry_interval_seconds: float = 8.0,
                 binding_mode: str = 'auto_bind'):
        self.host = host
        self.port = port if port is not None else self._get_config_port()
        self.packet_callback = packet_callback
        self.server: asyncio.AbstractServer | None = None
        self.running = False
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue)
        self.batch_interval = batch_interval_ms / 1000.0
        self._batch_task: asyncio.Task | None = None
        self.metrics = get_metrics()
        self._active_connections = 0
        self._client_period_on_sent: Dict[str, bool] = {}  # Track PERIOD_ON sent per client key (ip:port)
        self._client_writers: Dict[str, asyncio.StreamWriter] = {}  # Active client connections keyed by ip:port
        self._serial_to_client: Dict[str, str] = {}  # serial -> client key
        self._client_to_serial: Dict[str, str] = {}  # client key -> serial
        self._latest_client_by_ip: Dict[str, str] = {}  # ip -> latest connected client key
        self._loop: asyncio.AbstractEventLoop | None = None  # Store event loop reference
        self._client_eeprom_hex: Dict[str, str] = {}  # Latest valid EEPROM1 payload per client key
        self._client_eeprom_requested: Dict[str, bool] = {}  # Track one-time EEPROM1 request per client key
        self._client_last_eeprom_request: Dict[str, float] = {}  # Last EEPROM1 request send time per client key
        self.auto_request_eeprom_on_connect = bool(auto_request_eeprom_on_connect)
        self.collect_eeprom_until_received = bool(collect_eeprom_until_received)
        self.eeprom_retry_interval_seconds = max(2.0, float(eeprom_retry_interval_seconds))
        self.binding_mode = self._normalize_binding_mode(binding_mode)

    @staticmethod
    def _normalize_binding_mode(mode: str) -> str:
        value = str(mode or 'auto_bind').strip().lower()
        if value in ('handshake', 'device_id', 'device_id_handshake'):
            return 'handshake'
        return 'auto_bind'

    @staticmethod
    def _looks_like_serial_token(token: str | None) -> bool:
        candidate = str(token or '').strip()
        if not candidate or ' ' in candidate:
            return False
        if re.match(r'^\d{1,3}(?:\.\d{1,3}){3}$', candidate):
            return False
        upper = candidate.upper()
        if upper.startswith('EHWK') and len(upper) >= 8:
            return True
        if candidate.isdigit() and len(candidate) >= 8:
            return True
        if re.match(r'^[A-Z]{2,}\d{4,}$', upper):
            return True
        return False

    def _bind_serial_to_client(self, serial: str | None, client_key: str | None) -> str | None:
        serial_key = str(serial or '').strip()
        key = str(client_key or '').strip()
        if not serial_key or not key:
            return None
        self._serial_to_client[serial_key] = key
        self._client_to_serial[key] = serial_key
        return serial_key

    def _get_config_port(self) -> int:
        config_path = os.path.join(os.path.dirname(__file__), 'stream_config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = jsonlib.load(f)
                    port = config.get('tcp_port')
                    if port:
                        return int(port)
        except Exception as e:
            log_server_error(f"Config port read error: {e}")
        return 9001

    async def start(self):
        if self.running:
            return
        self.running = True
        self._loop = asyncio.get_event_loop()  # Store loop reference
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        log_info(f"TCP Server started on {self.host}:{self.port}")
        self._batch_task = asyncio.create_task(self._batch_processor())

    async def stop(self):
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except Exception:
                pass
        log_info("TCP Server stopped")

    def send_command_to_client(self, target: str, command: str) -> bool:
        """Send a command to a connected client by IP address or serial.
        Returns True if sent successfully, False otherwise.
        Thread-safe: can be called from any thread."""
        token = str(target or "").strip()
        target_key = token
        if token not in self._client_writers:
            if token in self._serial_to_client:
                target_key = self._serial_to_client[token]
            elif token in self._latest_client_by_ip:
                target_key = self._latest_client_by_ip[token]
            elif self._looks_like_serial_token(token) and len(self._client_writers) == 1:
                # Bootstrap path: when serial is not bound yet, route via the only active client.
                target_key = next(iter(self._client_writers.keys()))
                log_warning(
                    f"Bootstrap route for unresolved serial {token} via sole client {target_key}"
                )

        if target_key not in self._client_writers:
            log_warning(
                f"No active connection for target {token}. "
                f"Connected clients: {list(self._client_writers.keys())} serials: {list(self._serial_to_client.keys())}"
            )
            return False
        
        if not self._loop:
            log_warning("Event loop not available")
            return False
        
        writer = self._client_writers[target_key]
        try:
            # Schedule the command send in the event loop (thread-safe)
            print(f"📤 Scheduling command '{command}' to {target_key} (target={token})")
            asyncio.run_coroutine_threadsafe(
                self._send_command_async(writer, command, target_key),
                self._loop
            )
            if str(command or "").strip().upper() == "EEPROM1":
                self._client_eeprom_requested[target_key] = True
            return True
        except Exception as e:
            log_server_error(f"Failed to schedule command {command} to {target_key}: {e}")
            return False

    def request_eeprom1(self, ip: str) -> bool:
        return self.send_command_to_client(ip, "EEPROM1")

    def request_one_time_frame(self, ip: str) -> bool:
        return self.send_command_to_client(ip, "REQUEST1")
    
    async def _send_command_async(self, writer: asyncio.StreamWriter, command: str, ip: str):
        """Actually send the command asynchronously."""
        try:
            writer.write((str(command).rstrip('\n') + '\n').encode('ascii', errors='ignore'))
            await writer.drain()
            log_raw_packet(f"SENT_CMD {command} to {ip}", locationId=ip)
        except Exception as e:
            log_error_packet(reason=f"Command send failed: {e}", raw=command, loc_id=ip)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info('peername')
        client_ip = peer[0] if peer else 'unknown'
        client_port = int(peer[1]) if peer and len(peer) > 1 else 0
        client_key = f"{client_ip}:{client_port}"
        self._active_connections += 1
        self.metrics.update_tcp_connections(self._active_connections)
        self._client_writers[client_key] = writer  # Store writer for command sending
        self._latest_client_by_ip[client_ip] = client_key
        log_info(f"Client connected: {client_key}")
        log_debug(f"TCP binding mode for {client_key}: {self.binding_mode}")
        
        # Send DEVICE_ID query, PERIOD_ON and EEPROM1 once on connection establishment.
        # Each command must be \n-terminated so the device's line-based parser can delimit it.
        try:
            writer.write(b"DEVICE_ID\n")
            await writer.drain()
            log_debug(f"Sent DEVICE_ID query to {client_key} [ONE-TIME]")

            if not self._client_period_on_sent.get(client_key, False):
                # Start continuous streaming (one-time per connection)
                writer.write(b"PERIOD_ON\n")
                await writer.drain()
                self._client_period_on_sent[client_key] = True
                log_debug(f"Sent PERIOD_ON command to {client_key} for continuous streaming [ONE-TIME]")

            if self.auto_request_eeprom_on_connect and not self._client_eeprom_requested.get(client_key, False):
                writer.write(b"EEPROM1\n")
                await writer.drain()
                self._client_eeprom_requested[client_key] = True
                self._client_last_eeprom_request[client_key] = asyncio.get_running_loop().time()
                log_debug(f"Sent EEPROM1 command to {client_key} [ONE-TIME]")
        except Exception as e:
            log_warning(f"Failed to send connect commands to {client_key}: {e}")
            self._client_period_on_sent[client_key] = False

        eeprom_collect_task: asyncio.Task | None = None
        if self.collect_eeprom_until_received:
            eeprom_collect_task = asyncio.create_task(self._eeprom_collect_loop(writer, client_key))
        
        try:
            first_frame_received = False
            while self.running:
                line = await reader.readline()
                if not line:
                    break
                raw = line.decode('utf-8', errors='ignore').strip()
                if not raw:
                    continue
                log_raw_packet(raw, locationId=client_ip)
                
                # Auto-send PERIODIC_ON on first frame if initial send missed (failsafe)
                if not first_frame_received and raw.startswith('#frame'):
                    first_frame_received = True
                    if not self._client_period_on_sent.get(client_key, False):
                        try:
                            # Failsafe: ensure streaming is active
                            writer.write(b"PERIOD_ON\n")
                            await writer.drain()
                            self._client_period_on_sent[client_key] = True
                            log_debug(f"Auto-sent PERIOD_ON to {client_key} on first frame [FAILSAFE]")
                        except Exception as e:
                            log_warning(f"Auto PERIOD_ON failed: {e}")
                
                # Queue with backpressure: drop oldest if full
                if self.queue.full():
                    try:
                        _ = self.queue.get_nowait()
                    except Exception:
                        pass
                try:
                    self.queue.put_nowait((raw, client_key, client_ip))
                    self.metrics.update_tcp_queue_depth(self.queue.qsize())
                except Exception as e:
                    log_error_packet(reason=f"queue put error {e}", raw=raw, loc_id=client_ip)
                    self.metrics.record_tcp_error(client_ip)
        except Exception as e:
            log_error_packet(reason=f"client error {e}", raw='(stream)', loc_id=client_ip)
            self.metrics.record_tcp_error(client_ip)
        finally:
            if eeprom_collect_task:
                eeprom_collect_task.cancel()
                try:
                    await eeprom_collect_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            self._active_connections -= 1
            self.metrics.update_tcp_connections(self._active_connections)
            # Clean up client PERIOD_ON gate state
            if client_key in self._client_period_on_sent:
                del self._client_period_on_sent[client_key]
            serial = self._client_to_serial.pop(client_key, None)
            if serial and self._serial_to_client.get(serial) == client_key:
                del self._serial_to_client[serial]
            if client_key in self._client_eeprom_hex:
                del self._client_eeprom_hex[client_key]
            if client_key in self._client_eeprom_requested:
                del self._client_eeprom_requested[client_key]
            if client_key in self._client_last_eeprom_request:
                del self._client_last_eeprom_request[client_key]
            # Remove writer from active connections
            if client_key in self._client_writers:
                del self._client_writers[client_key]
            if self._latest_client_by_ip.get(client_ip) == client_key:
                replacement = None
                prefix = f"{client_ip}:"
                for key in self._client_writers.keys():
                    if key.startswith(prefix):
                        replacement = key
                if replacement:
                    self._latest_client_by_ip[client_ip] = replacement
                else:
                    self._latest_client_by_ip.pop(client_ip, None)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            log_info(f"Client disconnected: {client_key}")

    async def _eeprom_collect_loop(self, writer: asyncio.StreamWriter, client_key: str):
        loop = asyncio.get_running_loop()
        while self.running and client_key in self._client_writers:
            if client_key in self._client_eeprom_hex:
                return

            last_sent = float(self._client_last_eeprom_request.get(client_key, 0.0))
            if loop.time() - last_sent >= self.eeprom_retry_interval_seconds:
                try:
                    writer.write(b"EEPROM1\n")
                    await writer.drain()
                    self._client_eeprom_requested[client_key] = True
                    self._client_last_eeprom_request[client_key] = loop.time()
                    log_debug(f"Sent EEPROM1 command to {client_key} [RETRY]")
                except Exception:
                    return

            await asyncio.sleep(1.0)

    async def _batch_processor(self):
        """Periodically drain queue and process packets in batches for efficiency."""
        while self.running:
            await asyncio.sleep(self.batch_interval)
            batch: list[tuple[str, str, str]] = []
            try:
                while not self.queue.empty() and len(batch) < 2000:
                    batch.append(self.queue.get_nowait())
                self.metrics.update_tcp_queue_depth(self.queue.qsize())
            except Exception:
                pass
            if not batch:
                continue
            for raw, client_key, ip in batch:
                try:
                    import time
                    start = time.time()
                    packet = self._parse_packet(raw, client_key, ip)
                    latency_ms = (time.time() - start) * 1000
                    if packet:
                        self.metrics.record_tcp_packet(packet.get('loc_id', ip), latency_ms)
                        if self.packet_callback:
                            self.packet_callback(packet)
                except Exception as e:
                    log_error_packet(reason=f"parse error {e}", raw=raw, loc_id=ip)
                    self.metrics.record_tcp_error(ip)

    def _parse_packet(self, line: str, client_key: str | None, client_ip: str | None):
        result = None
        try:
            if line.startswith('#DEVICE_ID:'):
                serial = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'device_id', 'serial_number': serial, 'client_ip': client_ip}
                self._bind_serial_to_client(serial, client_key)
            elif line.startswith('#serialno:'):
                serial = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'serialno', 'serialno': serial, 'client_ip': client_ip}
                self._bind_serial_to_client(serial, client_key)
            elif line.startswith('#locid:'):
                loc_id = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'locid', 'loc_id': loc_id, 'client_ip': client_ip}
            elif line.startswith('#EEPROM'):
                eeprom_result = parse_eeprom_packet(line)
                if eeprom_result.get('success'):
                    frame_id = str(eeprom_result.get('frame_id') or '').strip()
                    # Some real devices send serial in EEPROM frame_id (e.g. #EEPROM<serial>:...)
                    if self.binding_mode == 'auto_bind' and self._looks_like_serial_token(frame_id):
                        self._bind_serial_to_client(frame_id, client_key)
                    self._client_eeprom_hex[client_key] = eeprom_result.get('hex')
                    result = {
                        'type': 'eeprom',
                        'frame_id': frame_id,
                        'blocks': eeprom_result.get('blocks'),
                        'client_ip': client_ip
                    }
                    serial = self._client_to_serial.get(client_key or '')
                    if serial:
                        result['serial_number'] = serial
                    log_debug(f"EEPROM calibration loaded from {client_ip}")
                else:
                    log_error_packet(reason=f"EEPROM parse error: {eeprom_result.get('error')}", raw=line[:80], loc_id=client_ip)
            elif line.startswith('#frame'):
                content = line[1:].rstrip('!')
                if ':' not in content:
                    log_error_packet(reason="frame no colon", raw=line[:80], loc_id=client_ip)
                else:
                    prefix, data = content.split(':', 1)
                    if prefix.startswith('frame') and len(prefix) > 5:
                        loc_id = prefix[5:]
                        frame_data = data.strip()
                        if self.binding_mode == 'auto_bind' and self._looks_like_serial_token(loc_id):
                            self._bind_serial_to_client(loc_id, client_key)
                    else:
                        if ':' in data:
                            loc_id, frame_data = data.split(':', 1)
                            loc_id = loc_id.strip(); frame_data = frame_data.strip()
                            if self.binding_mode == 'auto_bind' and self._looks_like_serial_token(loc_id):
                                self._bind_serial_to_client(loc_id, client_key)
                        else:
                            loc_id = None; frame_data = data.strip()
                    if not loc_id and client_ip:
                        loc_id = client_ip
                    frame_data_clean = frame_data.replace(" ", "").replace("\n", "").strip()
                    if ' ' in frame_data and len(frame_data_clean) == 0:
                        hex_values = frame_data.split()
                        if len(hex_values) == 32*24:
                            matrix = [
                                [
                                    ThermalFrameParser._raw_to_celsius(int(hex_values[r * 32 + c], 16))
                                    for c in range(32)
                                ]
                                for r in range(24)
                            ]
                            result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id, 'client_ip': client_ip}
                            serial = self._client_to_serial.get(client_key or '')
                            if serial:
                                result['serial_number'] = serial
                        else:
                            log_error_packet(reason=f"frame count {len(hex_values)}", raw=line[:80], loc_id=loc_id or client_ip)
                    else:
                        expected_grid_chars = 32*24*4  # 3072
                        total_with_eeprom = expected_grid_chars + 66*4  # 3336
                        if len(frame_data_clean) >= expected_grid_chars and len(frame_data_clean) < total_with_eeprom:
                            # Legacy format: only grid (no embedded EEPROM)
                            frame_grid = frame_data_clean[:expected_grid_chars]
                            matrix = ThermalFrameParser._parse_grid(frame_grid)
                            result = {
                                'type': 'frame',
                                'matrix': matrix.tolist() if hasattr(matrix, 'tolist') else matrix,
                                'rows': 24,
                                'cols': 32,
                                'eeprom_source': 'legacy_grid_parser',
                                'loc_id': loc_id,
                                'client_ip': client_ip,
                            }
                        elif len(frame_data_clean) >= total_with_eeprom:
                            frame_payload = frame_data_clean[:total_with_eeprom]
                            decoded = decode_frame_to_matrix(
                                frame_payload,
                                # Use client_key (ip:port) — that is also what the EEPROM store uses.
                                # Using client_ip alone was a key mismatch: EEPROM was stored by
                                # client_key but looked up by client_ip, so it always missed and
                                # fell through to the bundled test EEPROM, producing garbage temps.
                                eeprom_hex=self._client_eeprom_hex.get(client_key) or self._client_eeprom_hex.get(client_ip),
                            )
                            if decoded.get('success'):
                                matrix = decoded.get('matrix')
                                # Guard against invalid calibration payloads (common in simulator seeds)
                                # that can produce absurd temperatures. Fall back to deterministic
                                # raw parser when decoded range is physically implausible.
                                try:
                                    arr = np.asarray(matrix, dtype=float)
                                    if arr.size == 0:
                                        raise ValueError("empty decoded matrix")
                                    t_min = float(np.nanmin(arr))
                                    t_max = float(np.nanmax(arr))
                                    if t_max > 300.0 or t_min < -80.0:
                                        raise ValueError(f"implausible decoded range min={t_min:.2f} max={t_max:.2f}")
                                except Exception as sanity_exc:
                                    decoded = {
                                        'success': False,
                                        'error': f'decode_sanity_failed:{sanity_exc}',
                                    }
                                    matrix = None

                            if decoded.get('success'):
                                matrix = decoded.get('matrix')
                                result = {
                                    'type': 'frame',
                                    'matrix': matrix,
                                    'rows': decoded.get('rows', 24),
                                    'cols': decoded.get('cols', 32),
                                    'eeprom_source': decoded.get('eeprom_source', 'unknown'),
                                    'loc_id': loc_id,
                                    'client_ip': client_ip
                                }
                                serial = self._client_to_serial.get(client_key or '')
                                if serial:
                                    result['serial_number'] = serial
                            else:
                                # Fallback to parser that can handle raw 834-word frame without EEPROM1
                                try:
                                    parsed = ThermalFrameParser.parse_frame(frame_payload)
                                    matrix = parsed.get('grid')
                                    if matrix is not None:
                                        result = {
                                            'type': 'frame',
                                            'matrix': matrix.tolist() if hasattr(matrix, 'tolist') else matrix,
                                            'rows': parsed.get('rows', 24),
                                            'cols': parsed.get('cols', 32),
                                            'eeprom_source': 'fallback_parser',
                                            'loc_id': loc_id,
                                            'client_ip': client_ip
                                        }
                                    else:
                                        log_error_packet(reason=f"frame decode error {decoded.get('error')}", raw=line[:80], loc_id=loc_id or client_ip)
                                except Exception as parse_exc:
                                    log_error_packet(reason=f"frame decode error {decoded.get('error')} | fallback {parse_exc}", raw=line[:80], loc_id=loc_id or client_ip)
                        else:
                            log_error_packet(reason=f"frame length {len(frame_data_clean)}", raw=line[:80], loc_id=loc_id or client_ip)
            elif line.startswith('#Sensor'):
                content = line[1:].rstrip('!')
                if ':' not in content:
                    log_error_packet(reason="sensor no colon", raw=line[:80], loc_id=client_ip)
                else:
                    prefix, data = content.split(':', 1)
                    serial_candidate = None
                    if prefix.startswith('Sensor') and len(prefix) > 6:
                        loc_id = prefix[6:]; sensor_data = data.strip()
                        if self.binding_mode == 'auto_bind' and self._looks_like_serial_token(loc_id):
                            serial_candidate = loc_id
                    else:
                        if ':' in data:
                            loc_id, sensor_data = data.split(':', 1)
                            loc_id = loc_id.strip(); sensor_data = sensor_data.strip()
                            if self.binding_mode == 'auto_bind' and self._looks_like_serial_token(loc_id):
                                serial_candidate = loc_id
                        else:
                            loc_id = None; sensor_data = data.strip()
                    if not loc_id and client_ip:
                        loc_id = client_ip
                    sensors = {}
                    for part in sensor_data.split(','):
                        if '=' in part:
                            k, v = part.split('=', 1)
                            k = k.strip().rstrip(':'); v = v.strip()
                            key_lower = k.lower()
                            if key_lower in ('serial', 'serialno', 'serial_number', 'device_id'):
                                serial_candidate = str(v)
                                sensors['serial_number'] = str(v)
                                continue
                            try:
                                sensors[k] = float(v) if '.' in v else int(v)
                            except (ValueError, TypeError):
                                sensors[k] = str(v)
                    if self.binding_mode == 'auto_bind' and serial_candidate and client_key:
                        self._bind_serial_to_client(serial_candidate, client_key)
                    result = {'type': 'sensor', 'loc_id': loc_id, 'client_ip': client_ip, **sensors}
                    serial = self._client_to_serial.get(client_key or '')
                    if serial:
                        result['serial_number'] = serial
            else:
                log_error_packet(reason="unknown packet type", raw=line[:80], loc_id=client_ip)
        except Exception as e:
            log_error_packet(reason=f"parsing exception {e}", raw=line[:80], loc_id=client_ip)
        return result

async def _demo():
    def cb(p):
        log_debug(f'Callback: {p}')
    srv = TCPAsyncSensorServer(packet_callback=cb)
    await srv.start()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await srv.stop()

if __name__ == '__main__':
    asyncio.run(_demo())
