#!/usr/bin/env python3
"""
PFDS Simulator (real log replay)
- Replays PFDS device log with near real-time timing
- Responds to EEPROM1, PERIOD_ON, PERIOD_OFF, REQUEST1 commands
- Pairs thermal frames with nearest sensor packet
"""
import argparse
import logging
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# Determine log file path - handle both normal Python and PyInstaller frozen apps
if getattr(sys, "frozen", False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(app_dir, "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(log_dir, "simulator_debug.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class DataRecord:
    timestamp: datetime
    data: str
    packet_type: str


@dataclass
class ReplayEvent:
    timestamp: datetime
    packets: List[str]


class PFDSSimulator:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9001,
        loc_id: str = "demo_room",
        data_file: str = "data/NEW DATA 10 MINS.txt",
        speed: float = 1.0,
        pair_window_ms: int = 1000,
        loop: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.loc_id = loc_id
        self.data_file = Path(__file__).parent / data_file
        self.speed = max(0.1, float(speed))
        self.pair_window_ms = max(50, int(pair_window_ms))
        self.loop = loop

        self.sock: Optional[socket.socket] = None
        self.records: List[DataRecord] = []
        self.events: List[ReplayEvent] = []
        self.event_index = 0
        self.eeprom_packet: Optional[str] = None

        self.streaming = False
        self.stop_event = threading.Event()
        self.streaming_thread: Optional[threading.Thread] = None

    def _log(self, message: str) -> None:
        logger.info(message)

    def _detect_type(self, data: str) -> str:
        if data.startswith("#frame"):
            return "THERMAL_FRAME"
        if data.startswith("#Sensor"):
            return "SENSOR_DATA"
        if data.startswith("#EEPROM"):
            return "EEPROM_DATA"
        return "UNKNOWN"

    def _normalize_packet(self, packet: str) -> str:
        if packet.startswith("#frame"):
            # Normalize frame payload by keeping only hex chars and trimming to valid sizes.
            match = re.search(r"^#frame[^:]*:(.*)", packet, re.DOTALL)
            payload = match.group(1) if match else ""
            payload = payload.strip().rstrip("!")
            payload = re.sub(r"[^0-9A-Fa-f]", "", payload)
            if len(payload) >= 3336:
                payload = payload[:3336]
            elif len(payload) >= 3072:
                payload = payload[:3072]
            else:
                # Pad short payloads to grid-only size for parser compatibility.
                payload = payload.ljust(3072, "0")
            return f"#frame{self.loc_id}:{payload}!"
        if packet.startswith("#Sensor"):
            return re.sub(r"^#Sensor[^:]*:", f"#Sensor{self.loc_id}:", packet)
        if packet.startswith("#EEPROM"):
            return re.sub(r"^#EEPROM[^:]*:", f"#EEPROM{self.loc_id}:", packet)
        return packet

    def load_data(self) -> bool:
        if not self.data_file.exists():
            self._log(f"ERROR: Data file not found: {self.data_file}")
            return False

        self._log(f"Loading data from {self.data_file}...")
        pattern = re.compile(r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\](OUT|IN).*?(#.*?)(?=\[|$)", re.DOTALL)
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        records: List[DataRecord] = []
        try:
            # Use latin-1 to preserve raw bytes; utf-8 with ignore can truncate frame payloads.
            content = self.data_file.read_text(encoding="latin-1")
            for match in pattern.finditer(content):
                time_str = match.group(1)
                direction = match.group(2)
                raw_data = match.group(3).strip()

                if direction != "IN":
                    continue

                try:
                    time_obj = datetime.strptime(time_str, "%H:%M:%S.%f")
                    ts = base_date.replace(
                        hour=time_obj.hour,
                        minute=time_obj.minute,
                        second=time_obj.second,
                        microsecond=time_obj.microsecond,
                    )
                except ValueError:
                    continue

                data = re.sub(r"[¡ó¡õ¡ô¡ú¡û→←]", "", raw_data).strip()
                if not data.startswith("#"):
                    continue

                packet_type = self._detect_type(data)
                if packet_type == "UNKNOWN":
                    continue

                records.append(DataRecord(timestamp=ts, data=data, packet_type=packet_type))

            records.sort(key=lambda r: r.timestamp)
            self.records = records
            self._log(f"Loaded {len(records)} IN packets")
            return len(records) > 0
        except Exception as e:
            self._log(f"ERROR loading data: {e}")
            return False

    def build_events(self) -> None:
        frames = [r for r in self.records if r.packet_type == "THERMAL_FRAME"]
        sensors = [r for r in self.records if r.packet_type == "SENSOR_DATA"]
        eeproms = [r for r in self.records if r.packet_type == "EEPROM_DATA"]

        if eeproms:
            self.eeprom_packet = self._normalize_packet(eeproms[0].data)

        sensor_idx = 0
        window_s = self.pair_window_ms / 1000.0
        events: List[ReplayEvent] = []
        for frame in frames:
            packets = [self._normalize_packet(frame.data)]

            # Find nearest sensor packet within window
            best_sensor: Optional[DataRecord] = None
            best_delta_ms: Optional[float] = None

            while (
                sensor_idx < len(sensors)
                and sensors[sensor_idx].timestamp < frame.timestamp
                - timedelta(seconds=window_s)
            ):
                sensor_idx += 1

            scan_idx = sensor_idx
            while scan_idx < len(sensors):
                sensor = sensors[scan_idx]
                if sensor.timestamp > frame.timestamp + timedelta(seconds=window_s):
                    break
                delta_ms = abs((sensor.timestamp - frame.timestamp).total_seconds() * 1000)
                if best_delta_ms is None or delta_ms < best_delta_ms:
                    best_delta_ms = delta_ms
                    best_sensor = sensor
                scan_idx += 1

            if best_sensor:
                packets.append(self._normalize_packet(best_sensor.data))

            events.append(ReplayEvent(timestamp=frame.timestamp, packets=packets))

        self.events = events
        self._log(f"Built {len(events)} replay events (frame + optional sensor)")

    def preview_events(self, count: int) -> None:
        preview_count = max(0, int(count))
        if preview_count == 0:
            return
        print("Previewing parsed events:")
        for idx, event in enumerate(self.events[:preview_count], start=1):
            types = [self._detect_type(p) for p in event.packets]
            print(f"{idx:03d} {event.timestamp.time()} {types}")

    def send_packet(self, packet: str) -> None:
        try:
            if not self.sock:
                return
            if packet.startswith("#frame"):
                payload = re.sub(r"^#frame[^:]*:", "", packet).rstrip("!")
                logger.info(f"Sent frame packet (payload_len={len(payload)})")
            self.sock.sendall((packet + "\n").encode("utf-8"))
            logger.debug(f"Sent: {packet[:60]}...")
        except Exception as e:
            logger.error(f"Send failed: {e}")

    def send_eeprom(self) -> None:
        if self.eeprom_packet:
            self.send_packet(self.eeprom_packet)
        else:
            self.send_packet(f"#EEPROM{self.loc_id}:" + "0" * 3328 + "!")

    def _send_next_event(self) -> None:
        if not self.events:
            return
        event = self.events[self.event_index]
        self.event_index += 1
        if self.event_index >= len(self.events):
            self.event_index = 0
            if not self.loop:
                self.streaming = False

        for packet in event.packets:
            self.send_packet(packet)

    def _stream_loop(self) -> None:
        if not self.events:
            return
        self.stop_event.clear()

        while not self.stop_event.is_set() and self.streaming:
            current = self.events[self.event_index]
            next_idx = self.event_index + 1
            if next_idx >= len(self.events):
                next_idx = 0

            self._send_next_event()

            next_event = self.events[next_idx]
            delta = (next_event.timestamp - current.timestamp).total_seconds()
            if delta < 0:
                delta = 0.1
            sleep_s = max(0.05, delta / self.speed)

            end_time = time.time() + sleep_s
            while time.time() < end_time:
                if self.stop_event.is_set() or not self.streaming:
                    return
                time.sleep(0.05)

    def handle_commands(self) -> None:
        if not self.sock:
            return
        self.sock.settimeout(0.5)
        while self.sock:
            try:
                data = self.sock.recv(1024)
                if not data:
                    break

                command = data.decode("utf-8").strip()
                logger.info(f"Received command: {command}")

                if command == "EEPROM1":
                    self.send_eeprom()
                elif command in ("PERIOD_ON", "PERIODIC_ON"):
                    if not self.streaming:
                        self.streaming = True
                        self.stop_event.clear()
                        self.streaming_thread = threading.Thread(target=self._stream_loop, daemon=True)
                        self.streaming_thread.start()
                elif command in ("PERIOD_OFF", "PERIODIC_OFF"):
                    self.streaming = False
                    self.stop_event.set()
                elif command == "REQUEST1":
                    self._send_next_event()

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Command handler error: {e}")
                break

    def run(self, preview_count: int = 0) -> None:
        if not self.load_data():
            return
        self.build_events()

        if preview_count > 0:
            self.preview_events(preview_count)
            return

        try:
            # Keep trying until Field TCP server is ready (e.g., after login window).
            while self.sock is None:
                try:
                    candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    candidate.connect((self.host, self.port))
                    self.sock = candidate
                    logger.info(f"Connected to {self.host}:{self.port}")
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.warning(f"Connect retry to {self.host}:{self.port}: {e}")
                    try:
                        candidate.close()
                    except Exception:
                        pass
                    time.sleep(2.0)

            cmd_thread = threading.Thread(target=self.handle_commands, daemon=True)
            cmd_thread.start()

            self.send_packet(f"#serialno:SIM{int(time.time()) % 1000000}!")
            self.send_packet(f"#locid:{self.loc_id}!")
            time.sleep(0.5)

            # Wait for commands
            while True:
                time.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("Stopping simulator...")
        except Exception as e:
            logger.error(f"Simulator error: {e}")
        finally:
            if self.sock:
                self.sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PFDS Simulator (log replay)")
    parser.add_argument("--host", default="127.0.0.1", help="TCP server host")
    parser.add_argument("--port", type=int, default=9001, help="TCP server port")
    parser.add_argument("--loc-id", default="demo_room", help="Location ID")
    parser.add_argument("--data", default="data/NEW DATA 10 MINS.txt", help="PFDS log file")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed factor")
    parser.add_argument("--pair-window-ms", type=int, default=1000, help="Frame/sensor pairing window (ms)")
    parser.add_argument("--no-loop", action="store_true", help="Stop after one pass")
    parser.add_argument("--preview", type=int, default=0, help="Print first N events and exit")
    args = parser.parse_args()

    simulator = PFDSSimulator(
        host=args.host,
        port=args.port,
        loc_id=args.loc_id,
        data_file=args.data,
        speed=args.speed,
        pair_window_ms=args.pair_window_ms,
        loop=not args.no_loop,
    )
    logger.info(
        f"Starting PFDS simulator: {args.host}:{args.port}, loc_id={args.loc_id}, speed={args.speed}"
    )
    print("✅ PFDS simulator started (logs: simulator_debug.log)")
    simulator.run(preview_count=args.preview)
