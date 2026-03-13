#!/usr/bin/env python3
"""
EmberHawk Simulator v2.0

Unified PFDS/EmberHawk device simulator for EmberEye testing.

Modes:
  replay   - Replay a real PFDS log file with near real-time timing (default when --data is given)
  synthetic - Generate synthetic thermal frames when no data file is supplied

Protocol (commands received from server):
  DEVICE_ID   - Respond with #DEVICE_ID:<serial>!
  EEPROM1     - Respond with full 3328-char EEPROM calibration blob
  PERIOD_ON   - Start continuous streaming
  PERIOD_OFF  - Stop continuous streaming
  REQUEST1    - Send one frame immediately (on-demand)
  ALARM_ON    - Mark siren active
  ACK_ON      - Acknowledge active alarm

Packet wire format:
  #DEVICE_ID:<serial>!
  #frame<serial>:<3336_hex_chars>!
  #Sensor<serial>:ADC1=...,ADC2=...,Button=...,MQ_IN=...,MPY_IN=...,DIO_OUT=...!
  #EEPROM<serial>:<3328_hex_chars>!
"""
import argparse
import logging
import os
import random
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# ── Logging setup ────────────────────────────────────────────────────────────

if getattr(sys, "frozen", False):
    _app_dir = os.path.dirname(sys.executable)
else:
    _app_dir = os.path.dirname(os.path.abspath(__file__))

_log_dir = os.path.join(_app_dir, "logs")
os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(_log_dir, "emberhawk_simulator.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class _DataRecord:
    timestamp: datetime
    data: str
    packet_type: str   # THERMAL_FRAME | SENSOR_DATA | EEPROM_DATA


@dataclass
class _ReplayEvent:
    timestamp: datetime
    packets: List[str]


# ── Simulator ─────────────────────────────────────────────────────────────────

class EmberHawkSimulator:
    """
    EmberHawk device simulator v2.0.

    Call ``run()`` to start. Connects to *host:port* as a TCP client and
    responds to the full EmberHawk command set.
    """

    VERSION = "2.0"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9001,
        serial_number: Optional[str] = None,
        data_file: Optional[str] = None,
        speed: float = 1.0,
        pair_window_ms: int = 1000,
        loop: bool = True,
        interval: float = 1.0,
    ) -> None:
        self.host = host
        self.port = port
        self.serial_number = (
            str(serial_number or "").strip()
            or f"SIM{int(time.time()) % 1_000_000:06d}"
        )
        self.speed = max(0.1, float(speed))
        self.pair_window_ms = max(50, int(pair_window_ms))
        self.loop = loop
        self.interval = max(0.05, float(interval))

        # Replay mode: populated by load_data / build_events
        self._data_file: Optional[Path] = Path(data_file) if data_file else None
        self._records: List[_DataRecord] = []
        self._events: List[_ReplayEvent] = []
        self._event_index = 0
        self._eeprom_packet: Optional[str] = None

        # Connection
        self._sock: Optional[socket.socket] = None

        # Streaming state
        self._streaming = False
        self._streaming_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._streaming_thread: Optional[threading.Thread] = None

        # Siren state
        self.siren_active = False
        self.siren_acknowledged = False

        # Synthetic frame counter
        self._frame_count = 0
        self._replay_frame_count = 0

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logger.info(msg)

    def _send_raw(self, packet: str) -> None:
        """Send a complete packet string over the socket."""
        if not self._sock:
            return
        try:
            self._sock.sendall((packet + "\n").encode("utf-8"))
            if packet.startswith("#frame"):
                payload_len = len(re.sub(r"^#frame[^:]*:", "", packet).rstrip("!"))
                logger.debug(f"Sent frame (payload_len={payload_len})")
            else:
                logger.debug(f"Sent: {packet[:80]}")
        except Exception as exc:
            logger.error(f"Send failed: {exc}")

    # ── Packet normalisation (replay mode) ────────────────────────────────────

    @staticmethod
    def _detect_type(data: str) -> str:
        if data.startswith("#frame"):
            return "THERMAL_FRAME"
        if data.startswith("#Sensor"):
            return "SENSOR_DATA"
        if data.startswith("#EEPROM"):
            return "EEPROM_DATA"
        return "UNKNOWN"

    def _normalize_packet(self, packet: str) -> str:
        """Re-stamp packet names with this simulator's serial number."""
        if packet.startswith("#frame"):
            match = re.search(r"^#frame[^:]*:(.*)", packet, re.DOTALL)
            payload = match.group(1) if match else ""
            payload = payload.strip().rstrip("!")
            payload = re.sub(r"[^0-9A-Fa-f]", "", payload)
            if len(payload) >= 3336:
                payload = payload[:3336]
            elif len(payload) >= 3072:
                payload = payload[:3072]
            else:
                payload = payload.ljust(3072, "0")
            payload = self._inject_replay_hotspot(payload)
            return f"#frame{self.serial_number}:{payload}!"
        if packet.startswith("#Sensor"):
            return re.sub(r"^#Sensor[^:]*:", f"#Sensor{self.serial_number}:", packet)
        if packet.startswith("#EEPROM"):
            return re.sub(r"^#EEPROM[^:]*:", f"#EEPROM{self.serial_number}:", packet)
        return packet

    @staticmethod
    def _raw_to_celsius(raw_value: int) -> float:
        if raw_value > 0x7FFF:
            raw_value -= 0x10000
        return (raw_value / 100.0) + 27.0

    @staticmethod
    def _celsius_to_raw(temp_c: float) -> str:
        raw = int(round((float(temp_c) - 27.0) * 100.0))
        if raw < 0:
            raw += 0x10000
        raw = max(0, min(0xFFFF, raw))
        return f"{raw:04X}"

    def _inject_replay_hotspot(self, payload: str) -> str:
        """Convert flat replay frames into a realistic hotspot field with falloff.

        Existing replay data is mostly uniform across the 24x32 grid. That is useful
        for threshold testing but not for visual hotspot validation, so shape a local
        hot region while preserving the original baseline temperature of the frame.
        """
        clean = re.sub(r"[^0-9A-Fa-f]", "", payload or "")
        if len(clean) < 3072:
            return clean

        grid_hex = clean[:3072]
        tail_hex = clean[3072:3336] if len(clean) >= 3336 else clean[3072:]
        words = [grid_hex[i:i + 4] for i in range(0, 3072, 4)]
        if len(words) != 768:
            return clean

        # Detect nearly-uniform frames from the replay seed. If the frame is already
        # spatially interesting, leave it alone.
        unique_words = set(words)
        if len(unique_words) > 8:
            return clean[:3336] if len(clean) >= 3336 else clean

        temps = [self._raw_to_celsius(int(word, 16)) for word in words]
        baseline = sum(temps) / max(1, len(temps))

        frame_idx = self._replay_frame_count
        self._replay_frame_count += 1

        # Deterministic per-device hotspot motion so three devices do not overlap.
        serial_bias = sum(ord(ch) for ch in self.serial_number) % 7
        center_row = 6 + ((frame_idx // 6) + serial_bias) % 12
        center_col = 8 + ((frame_idx // 4) + serial_bias * 3) % 16
        hotspot_peak = max(65.0, min(90.0, baseline + 22.0))
        warm_ring = max(38.0, baseline + 6.0)

        shaped_words = []
        for idx, base_temp in enumerate(temps):
            row = idx // 32
            col = idx % 32
            dist = ((row - center_row) ** 2 + (col - center_col) ** 2) ** 0.5

            if dist <= 1.6:
                target = hotspot_peak - (dist * 6.0)
            elif dist <= 3.2:
                target = warm_ring + max(0.0, (3.2 - dist) * 5.0)
            elif dist <= 5.5:
                target = baseline + max(0.0, (5.5 - dist) * 1.2)
            else:
                target = base_temp

            shaped_words.append(self._celsius_to_raw(max(base_temp, target)))

        return "".join(shaped_words) + tail_hex

    # ── Replay mode: load & build ─────────────────────────────────────────────

    def load_data(self) -> bool:
        if not self._data_file:
            return False
        if not self._data_file.exists():
            self._log(f"ERROR: Data file not found: {self._data_file}")
            return False

        self._log(f"Loading data from {self._data_file} ...")
        pattern = re.compile(
            r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\](OUT|IN).*?(#.*?)(?=\[|$)", re.DOTALL
        )
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        records: List[_DataRecord] = []

        try:
            content = self._data_file.read_text(encoding="latin-1")
            for m in pattern.finditer(content):
                if m.group(2) != "IN":
                    continue
                try:
                    t = datetime.strptime(m.group(1), "%H:%M:%S.%f")
                    ts = base_date.replace(
                        hour=t.hour, minute=t.minute,
                        second=t.second, microsecond=t.microsecond,
                    )
                except ValueError:
                    continue
                data = re.sub(r"[¡ó¡õ¡ô¡ú¡û→←]", "", m.group(3).strip()).strip()
                if not data.startswith("#"):
                    continue
                ptype = self._detect_type(data)
                if ptype == "UNKNOWN":
                    continue
                records.append(_DataRecord(timestamp=ts, data=data, packet_type=ptype))

            records.sort(key=lambda r: r.timestamp)
            self._records = records
            self._log(f"Loaded {len(records)} IN packets")
            return len(records) > 0
        except Exception as exc:
            self._log(f"ERROR loading data: {exc}")
            return False

    def build_events(self) -> None:
        frames = [r for r in self._records if r.packet_type == "THERMAL_FRAME"]
        sensors = [r for r in self._records if r.packet_type == "SENSOR_DATA"]
        eeproms = [r for r in self._records if r.packet_type == "EEPROM_DATA"]

        if eeproms:
            self._eeprom_packet = self._normalize_packet(eeproms[0].data)

        window_s = self.pair_window_ms / 1000.0
        sensor_idx = 0
        events: List[_ReplayEvent] = []

        for frame in frames:
            packets = [self._normalize_packet(frame.data)]
            best_sensor: Optional[_DataRecord] = None
            best_delta: Optional[float] = None

            while (
                sensor_idx < len(sensors)
                and sensors[sensor_idx].timestamp
                < frame.timestamp - timedelta(seconds=window_s)
            ):
                sensor_idx += 1

            scan = sensor_idx
            while scan < len(sensors):
                s = sensors[scan]
                if s.timestamp > frame.timestamp + timedelta(seconds=window_s):
                    break
                d = abs((s.timestamp - frame.timestamp).total_seconds() * 1000)
                if best_delta is None or d < best_delta:
                    best_delta = d
                    best_sensor = s
                scan += 1

            if best_sensor:
                packets.append(self._normalize_packet(best_sensor.data))

            events.append(_ReplayEvent(timestamp=frame.timestamp, packets=packets))

        self._events = events
        self._log(f"Built {len(events)} replay events")

    def preview_events(self, count: int) -> None:
        if count <= 0:
            return
        print("Previewing parsed events:")
        for idx, ev in enumerate(self._events[:count], 1):
            types = [self._detect_type(p) for p in ev.packets]
            print(f"{idx:03d} {ev.timestamp.time()} {types}")

    # ── Synthetic mode: frame / sensor / EEPROM generation ───────────────────

    def _generate_thermal_frame(self) -> str:
        """
        Generate a 3336-char hex frame (768 grid blocks + 66 EEPROM blocks).
        Uses numpy when available; falls back to pure-Python.
        """
        base_temp = 25.0
        t = self._frame_count * 0.1

        if _HAS_NUMPY:
            r_idx = np.arange(24)[:, None]
            c_idx = np.arange(32)[None, :]
            grid = base_temp + 2.0 * np.sin(r_idx * 0.3 + t) * np.cos(c_idx * 0.3 + t)
            grid = grid.astype(float)
        else:
            import math
            grid = [
                [base_temp + 2.0 * math.sin(r * 0.3 + t) * math.cos(c * 0.3 + t)
                 for c in range(32)]
                for r in range(24)
            ]

        # Add 2–4 hot spots
        for _ in range(random.randint(2, 4)):
            cr, cc = random.randint(3, 20), random.randint(3, 28)
            ht = random.uniform(45.0, 85.0)
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    rr, rc = cr + dr, cc + dc
                    if 0 <= rr < 24 and 0 <= rc < 32:
                        if _HAS_NUMPY:
                            grid[rr, rc] = ht - (abs(dr) + abs(dc)) * 5.0
                        else:
                            grid[rr][rc] = ht - (abs(dr) + abs(dc)) * 5.0

        self._frame_count += 1
        parts = []
        for r in range(24):
            for c in range(32):
                raw = int(((grid[r, c] if _HAS_NUMPY else grid[r][c]) - 27.0) / 0.01)
                raw = max(0, min(0xFFFF, raw + 0x10000 if raw < 0 else raw))
                parts.append(f"{raw:04X}")

        grid_hex = "".join(parts)
        eeprom_hex = "".join(f"{random.randint(100, 9999):04X}" for _ in range(66))
        return grid_hex + eeprom_hex  # 3072 + 264 = 3336 chars

    def _generate_eeprom1_response(self) -> str:
        """Generate 3328-char EEPROM1 calibration blob."""
        offset_c = random.uniform(-2.0, 2.0)
        offset_cd = int(offset_c * 100)
        raw = offset_cd + 0x10000 if offset_cd < 0 else offset_cd
        word0 = f"{raw:04X}"
        rest = "".join(f"{random.randint(100, 9999):04X}" for _ in range(831))
        self._log(f"Generated EEPROM1 calibration: offset={offset_c:.2f}°C (0x{word0})")
        return word0 + rest  # 3328 chars

    def _generate_sensor_fields(self) -> str:
        """Generate sensor field string matching real device format."""
        adc1 = random.randint(800, 1200)
        adc2 = random.randint(250, 500)
        return (
            f"ADC1={adc1},ADC2={adc2},"
            f"Button={random.randint(0, 1)},"
            f"MQ_IN={random.randint(0, 1)},"
            f"MPY_IN={random.randint(0, 1)},"
            f"DIO_OUT={random.randint(0, 1)}"
        )

    # ── Packet sending ────────────────────────────────────────────────────────

    def _send_eeprom1(self) -> None:
        if self._eeprom_packet:
            self._send_raw(self._eeprom_packet)
        else:
            data = self._generate_eeprom1_response()
            self._send_raw(f"#EEPROM{self.serial_number}:{data}!")

    def _send_one_event(self) -> None:
        """Send the next replay event, or a synthetic frame if in synthetic mode."""
        if self._events:
            ev = self._events[self._event_index]
            self._event_index += 1
            if self._event_index >= len(self._events):
                self._event_index = 0
                if not self.loop:
                    with self._streaming_lock:
                        self._streaming = False
            for pkt in ev.packets:
                self._send_raw(pkt)
        else:
            # Synthetic mode
            frame_hex = self._generate_thermal_frame()
            self._send_raw(f"#frame{self.serial_number}:{frame_hex}!")
            self._send_raw(
                f"#Sensor{self.serial_number}:{self._generate_sensor_fields()}!"
            )

    # ── Streaming loop ────────────────────────────────────────────────────────

    def _stream_loop(self) -> None:
        self._stop_event.clear()
        while not self._stop_event.is_set():
            with self._streaming_lock:
                if not self._streaming:
                    return

            if self._events:
                current = self._events[self._event_index]
                next_idx = (self._event_index + 1) % len(self._events)
                self._send_one_event()
                next_ev = self._events[next_idx]
                delta = (next_ev.timestamp - current.timestamp).total_seconds()
                sleep_s = max(0.05, (delta if delta > 0 else 0.1) / self.speed)
            else:
                self._send_one_event()
                sleep_s = self.interval

            deadline = time.time() + sleep_s
            while time.time() < deadline:
                if self._stop_event.is_set():
                    return
                time.sleep(0.05)

    # ── Command handler ───────────────────────────────────────────────────────

    def _handle_command(self, command: str) -> None:
        cmd = command.strip()
        logger.info(f"Received command: {cmd}")

        if cmd == "DEVICE_ID":
            self._send_raw(f"#DEVICE_ID:{self.serial_number}!")
            logger.info(f"Sent DEVICE_ID response: {self.serial_number}")

        elif cmd == "EEPROM1":
            logger.info("Received EEPROM1 command - sending calibration data")
            self._send_eeprom1()

        elif cmd == "PERIOD_ON":
            logger.info("Received PERIOD_ON command - starting continuous streaming")
            with self._streaming_lock:
                if not self._streaming:
                    self._streaming = True
                    self._stop_event.clear()
                    self._streaming_thread = threading.Thread(
                        target=self._stream_loop, daemon=True
                    )
                    self._streaming_thread.start()

        elif cmd == "PERIOD_OFF":
            logger.info("Received PERIOD_OFF command - stopping streaming")
            with self._streaming_lock:
                self._streaming = False
            self._stop_event.set()

        elif cmd == "REQUEST1":
            logger.info("Received REQUEST1 command - sending single frame")
            self._send_one_event()

        elif cmd == "ALARM_ON":
            self.siren_active = True
            self.siren_acknowledged = False
            logger.info("Received ALARM_ON command - siren state ACTIVE")

        elif cmd == "ACK_ON":
            if self.siren_active:
                self.siren_acknowledged = True
                logger.info("Received ACK_ON command - siren acknowledged")
            else:
                logger.info("Received ACK_ON command with no active alarm")

        else:
            logger.warning(f"Unknown command ignored: {cmd}")

    def _command_listener(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        buf = ""
        while self._sock and not self._shutdown_event.is_set():
            try:
                chunk = self._sock.recv(1024)
                if not chunk:
                    logger.info("Connection closed by server")
                    break
                buf += chunk.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_command(line)
            except socket.timeout:
                continue
            except Exception as exc:
                logger.error(f"Command listener error: {exc}")
                break

    def stop(self) -> None:
        """Stop this simulator instance gracefully."""
        self._shutdown_event.set()
        with self._streaming_lock:
            self._streaming = False
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self, preview_count: int = 0) -> None:
        """Connect to the field server and begin simulation."""
        self._shutdown_event.clear()
        if self._data_file:
            if not self.load_data():
                return
            self.build_events()

        if preview_count > 0:
            self.preview_events(preview_count)
            return

        print(f"EmberHawk Simulator v{self.VERSION} | serial={self.serial_number}")
        print(f"  Mode    : {'replay' if self._events else 'synthetic'}")
        print(f"  Target  : {self.host}:{self.port}")
        mode_info = (
            f"data={self._data_file}, speed={self.speed}x" if self._events
            else f"interval={self.interval}s"
        )
        print(f"  Config  : {mode_info}")
        print(f"  Log     : {os.path.join(_log_dir, 'emberhawk_simulator.log')}")
        print("Connecting ... (Ctrl+C to stop)")

        try:
            # Retry until the Field TCP server is ready
            while self._sock is None and not self._shutdown_event.is_set():
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((self.host, self.port))
                    self._sock = s
                    logger.info(f"Connected to {self.host}:{self.port}")
                    print(f"Connected to {self.host}:{self.port}")
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    logger.warning(f"Connect retry ({exc}), waiting 2s ...")
                    try:
                        s.close()
                    except Exception:
                        pass
                    time.sleep(2.0)

            if self._shutdown_event.is_set():
                return

            # Start command listener
            listener = threading.Thread(target=self._command_listener, daemon=True)
            listener.start()

            # Wait for DEVICE_ID query from server, then idle waiting for commands
            while not self._shutdown_event.is_set():
                time.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("Simulator stopped by user")
            print("\nStopped.")
        except Exception as exc:
            logger.error(f"Simulator fatal error: {exc}")
        finally:
            self._stop_event.set()
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            logger.info("Socket closed")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _serial_for_instance(args, index: int) -> str:
    if args.instances <= 1:
        return args.serial or ""
    if args.serial:
        return f"{args.serial}{index + 1:03d}"
    return f"{args.serial_prefix}{args.serial_start + index:06d}"


def _run_multi_instances(args) -> None:
    sims: List[EmberHawkSimulator] = []
    threads: List[threading.Thread] = []

    print(f"Starting {args.instances} EmberHawk simulator instances for load test")
    for i in range(args.instances):
        serial = _serial_for_instance(args, i)
        sim = EmberHawkSimulator(
            host=args.host,
            port=args.port,
            serial_number=serial or None,
            data_file=args.data or None,
            speed=args.speed,
            pair_window_ms=args.pair_window_ms,
            loop=not args.no_loop,
            interval=args.interval,
        )
        sims.append(sim)

        t = threading.Thread(target=sim.run, kwargs={"preview_count": 0}, daemon=True)
        threads.append(t)
        t.start()
        print(f"  [{i + 1}/{args.instances}] serial={sim.serial_number} started")
        if args.stagger_seconds > 0:
            time.sleep(args.stagger_seconds)

    print("All instances started. Press Ctrl+C to stop all simulators.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping all simulator instances...")
    finally:
        for sim in sims:
            sim.stop()
        for t in threads:
            t.join(timeout=2.0)
        print("All simulator instances stopped.")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="EmberHawk Simulator v2.0 — unified PFDS/EmberHawk device simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Replay mode (real log data):
  python emberhawk_simulator.py --host 127.0.0.1 --port 9001 --serial 1829602101142 --data pfds/data/TOTAL_DATA.txt

  # Synthetic mode (no data file):
  python emberhawk_simulator.py --host 127.0.0.1 --port 9001 --interval 1.0

  # Preview first 10 replay events and exit:
  python emberhawk_simulator.py --data pfds/data/TOTAL_DATA.txt --preview 10
        """,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Field TCP server host")
    parser.add_argument("--port", type=int, default=9001, help="Field TCP server port")
    parser.add_argument("--serial", default="", help="Device serial number (auto-generated if omitted)")
    parser.add_argument("--data", default="", help="Path to PFDS log file (enables replay mode)")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (replay mode only)")
    parser.add_argument("--pair-window-ms", type=int, default=1000, help="Frame/sensor pairing window in ms (replay mode only)")
    parser.add_argument("--no-loop", action="store_true", help="Stop after one full replay pass")
    parser.add_argument("--interval", type=float, default=1.0, help="Frame interval in seconds (synthetic mode only)")
    parser.add_argument("--preview", type=int, default=0, help="Print first N replay events and exit (replay mode only)")
    parser.add_argument("--instances", type=int, default=1, help="Number of concurrent simulator clients (load test mode)")
    parser.add_argument("--serial-prefix", default="SIM", help="Serial prefix for auto-generated multi-instance serials")
    parser.add_argument("--serial-start", type=int, default=1, help="Starting numeric suffix for multi-instance serial generation")
    parser.add_argument("--stagger-seconds", type=float, default=0.1, help="Delay between launching simulator instances")
    args = parser.parse_args()

    if args.instances < 1:
        raise SystemExit("--instances must be >= 1")

    if args.preview > 0 and args.instances > 1:
        raise SystemExit("--preview supports only a single instance")

    if args.instances > 1:
        _run_multi_instances(args)
        return

    sim = EmberHawkSimulator(
        host=args.host,
        port=args.port,
        serial_number=args.serial or None,
        data_file=args.data or None,
        speed=args.speed,
        pair_window_ms=args.pair_window_ms,
        loop=not args.no_loop,
        interval=args.interval,
    )
    sim.run(preview_count=args.preview)


if __name__ == "__main__":
    main()
