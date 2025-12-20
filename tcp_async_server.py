import asyncio
import os
import json as jsonlib
from typing import Callable, Dict, Any

from tcp_logger import log_raw_packet, log_error_packet
from tcp_server_logger import log_info, log_debug, log_warning, log_error as log_server_error
from metrics import get_metrics

class TCPAsyncSensorServer:
    """High-performance asyncio-based TCP sensor server with queue-based packet processing.

    Features:
    - Single-threaded event loop (no Qt cross-thread violations)
    - Backpressure via asyncio.Queue (drops oldest on overflow)
    - Batch processing of packets to reduce per-line overhead
    - Reuses existing packet parsing logic (adapted)
    """

    def __init__(self, host: str = '0.0.0.0', port: int | None = None, packet_callback: Callable[[Dict[str, Any]], None] | None = None,
                 max_queue: int = 10000, batch_interval_ms: int = 50):
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
        self._client_period_on_sent: Dict[str, bool] = {}  # Track PERIOD_ON sent per client IP (one-time)
        self._client_writers: Dict[str, asyncio.StreamWriter] = {}  # Active client connections for command sending
        self._loop: asyncio.AbstractEventLoop | None = None  # Store event loop reference

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

    def send_command_to_client(self, ip: str, command: str) -> bool:
        """Send a command to a connected client by IP address.
        Returns True if sent successfully, False otherwise.
        Thread-safe: can be called from any thread."""
        if ip not in self._client_writers:
            log_warning(f"No active connection for IP {ip}. Connected clients: {list(self._client_writers.keys())}")
            return False
        
        if not self._loop:
            log_warning("Event loop not available")
            return False
        
        writer = self._client_writers[ip]
        try:
            # Schedule the command send in the event loop (thread-safe)
            print(f"📤 Scheduling command '{command}' to {ip}")
            asyncio.run_coroutine_threadsafe(
                self._send_command_async(writer, command, ip),
                self._loop
            )
            return True
        except Exception as e:
            log_server_error(f"Failed to schedule command {command} to {ip}: {e}")
            return False
    
    async def _send_command_async(self, writer: asyncio.StreamWriter, command: str, ip: str):
        """Actually send the command asynchronously."""
        try:
            writer.write((command + "\n").encode('utf-8'))
            await writer.drain()
            log_raw_packet(f"SENT_CMD {command} to {ip}", locationId=ip)
        except Exception as e:
            log_error_packet(reason=f"Command send failed: {e}", raw=command, loc_id=ip)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info('peername')
        client_ip = peer[0] if peer else 'unknown'
        self._active_connections += 1
        self.metrics.update_tcp_connections(self._active_connections)
        self._client_writers[client_ip] = writer  # Store writer for command sending
        log_info(f"Client connected: {client_ip}")
        
        # Send PERIODIC_ON ONCE on connection establishment (gate to prevent re-sends)
        try:
            from thermal_frame_parser import ThermalFrameParser
            ThermalFrameParser.reset_eeprom_state()  # Reset for new connection
            
            if not self._client_period_on_sent.get(client_ip, False):
                # Start continuous streaming (one-time per connection)
                writer.write(b"PERIODIC_ON")
                await writer.drain()
                self._client_period_on_sent[client_ip] = True
                log_debug(f"Sent PERIOD_ON command to {client_ip} for continuous streaming [ONE-TIME]")
            
            # DO NOT send EEPROM1 automatically - wait for parser to validate raw EEPROM
            # Parser will trigger EEPROM1 request if raw EEPROM is corrupted
        except Exception as e:
            log_warning(f"Failed to send PERIOD_ON to {client_ip}: {e}")
            self._client_period_on_sent[client_ip] = False
        
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
                    if not self._client_period_on_sent.get(client_ip, False):
                        try:
                            # Failsafe: ensure streaming is active
                            writer.write(b"PERIODIC_ON")
                            await writer.drain()
                            self._client_period_on_sent[client_ip] = True
                            log_debug(f"Auto-sent PERIOD_ON to {client_ip} on first frame [FAILSAFE]")
                        except Exception as e:
                            log_warning(f"Auto PERIOD_ON failed: {e}")
                
                # Queue with backpressure: drop oldest if full
                if self.queue.full():
                    try:
                        _ = self.queue.get_nowait()
                    except Exception:
                        pass
                try:
                    self.queue.put_nowait((raw, client_ip))
                    self.metrics.update_tcp_queue_depth(self.queue.qsize())
                except Exception as e:
                    log_error_packet(reason=f"queue put error {e}", raw=raw, loc_id=client_ip)
                    self.metrics.record_tcp_error(client_ip)
        except Exception as e:
            log_error_packet(reason=f"client error {e}", raw='(stream)', loc_id=client_ip)
            self.metrics.record_tcp_error(client_ip)
        finally:
            self._active_connections -= 1
            self.metrics.update_tcp_connections(self._active_connections)
            # Clean up client PERIOD_ON gate state
            if client_ip in self._client_period_on_sent:
                del self._client_period_on_sent[client_ip]
            # Remove writer from active connections
            if client_ip in self._client_writers:
                del self._client_writers[client_ip]
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            log_info(f"Client disconnected: {client_ip}")

    async def _batch_processor(self):
        """Periodically drain queue and process packets in batches for efficiency."""
        while self.running:
            await asyncio.sleep(self.batch_interval)
            batch: list[tuple[str, str]] = []
            try:
                while not self.queue.empty() and len(batch) < 2000:
                    batch.append(self.queue.get_nowait())
                self.metrics.update_tcp_queue_depth(self.queue.qsize())
            except Exception:
                pass
            if not batch:
                continue
            for raw, ip in batch:
                try:
                    import time
                    start = time.time()
                    packet = self._parse_packet(raw, ip)
                    latency_ms = (time.time() - start) * 1000
                    if packet:
                        self.metrics.record_tcp_packet(packet.get('loc_id', ip), latency_ms)
                        if self.packet_callback:
                            self.packet_callback(packet)
                except Exception as e:
                    log_error_packet(reason=f"parse error {e}", raw=raw, loc_id=ip)
                    self.metrics.record_tcp_error(ip)

    def _parse_packet(self, line: str, client_ip: str | None):
        result = None
        try:
            if line.startswith('#serialno:'):
                serial = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'serialno', 'serialno': serial, 'client_ip': client_ip}
            elif line.startswith('#locid:'):
                loc_id = line.split(':', 1)[1].rstrip('!').strip()
                result = {'type': 'locid', 'loc_id': loc_id, 'client_ip': client_ip}
            elif line.startswith('#EEPROM'):
                # Handle EEPROM response packet
                from thermal_frame_parser import ThermalFrameParser
                eeprom_result = ThermalFrameParser.parse_eeprom_packet(line)
                if eeprom_result.get('success'):
                    result = {
                        'type': 'eeprom',
                        'frame_id': eeprom_result.get('frame_id'),
                        'blocks': eeprom_result.get('blocks'),
                        'client_ip': client_ip
                    }
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
                    else:
                        if ':' in data:
                            loc_id, frame_data = data.split(':', 1)
                            loc_id = loc_id.strip(); frame_data = frame_data.strip()
                        else:
                            loc_id = None; frame_data = data.strip()
                    if not loc_id and client_ip:
                        loc_id = client_ip
                    if ' ' in frame_data:
                        hex_values = frame_data.split()
                        if len(hex_values) == 32*24:
                            matrix = [[int(hex_values[r*32+c], 16) for c in range(32)] for r in range(24)]
                            result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id, 'client_ip': client_ip}
                        else:
                            log_error_packet(reason=f"frame count {len(hex_values)}", raw=line[:80], loc_id=loc_id or client_ip)
                    else:
                        expected_grid_chars = 32*24*4  # 3072
                        total_with_eeprom = expected_grid_chars + 66*4  # 3336
                        if len(frame_data) == expected_grid_chars:
                            # Legacy format: only grid (no embedded EEPROM)
                            hex_values = [frame_data[i:i+4] for i in range(0, len(frame_data), 4)]
                            matrix = [[int(hex_values[r*32+c], 16) for c in range(32)] for r in range(24)]
                            result = {'type': 'frame', 'matrix': matrix, 'loc_id': loc_id, 'client_ip': client_ip}
                        elif len(frame_data) == total_with_eeprom:
                            # New format: grid + embedded EEPROM (3336 chars)
                            try:
                                from thermal_frame_parser import ThermalFrameParser
                                parsed = ThermalFrameParser.parse_frame(frame_data)
                                grid = parsed.get('grid')
                                # Provide both 'grid' (numpy) and legacy 'matrix' (list of lists)
                                matrix = grid.tolist() if hasattr(grid, 'tolist') else grid
                                result = {
                                    'type': 'frame',
                                    'grid': grid,
                                    'matrix': matrix,
                                    'rows': parsed.get('rows'),
                                    'cols': parsed.get('cols'),
                                    'eeprom': parsed.get('eeprom'),
                                    'loc_id': loc_id,
                                    'client_ip': client_ip
                                }
                            except Exception as e:
                                log_error_packet(reason=f"frame parse error {e}", raw=line[:80], loc_id=loc_id or client_ip)
                        else:
                            log_error_packet(reason=f"frame length {len(frame_data)}", raw=line[:80], loc_id=loc_id or client_ip)
            elif line.startswith('#Sensor'):
                content = line[1:].rstrip('!')
                if ':' not in content:
                    log_error_packet(reason="sensor no colon", raw=line[:80], loc_id=client_ip)
                else:
                    prefix, data = content.split(':', 1)
                    if prefix.startswith('Sensor') and len(prefix) > 6:
                        loc_id = prefix[6:]; sensor_data = data.strip()
                    else:
                        if ':' in data:
                            loc_id, sensor_data = data.split(':', 1)
                            loc_id = loc_id.strip(); sensor_data = sensor_data.strip()
                        else:
                            loc_id = None; sensor_data = data.strip()
                    if not loc_id and client_ip:
                        loc_id = client_ip
                    sensors = {}
                    for part in sensor_data.split(','):
                        if '=' in part:
                            k, v = part.split('=', 1)
                            k = k.strip().rstrip(':'); v = v.strip()
                            sensors[k] = float(v) if '.' in v else int(v)
                    result = {'type': 'sensor', 'loc_id': loc_id, 'client_ip': client_ip, **sensors}
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
