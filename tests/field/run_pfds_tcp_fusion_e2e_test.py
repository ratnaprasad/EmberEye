#!/usr/bin/env python3
"""End-to-end validation: PFDS simulator -> upgraded TCP server -> FusionOrchestrator."""

import argparse
import subprocess
import sys
import threading
import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from embereye.core.fusion import FusionOrchestrator  # noqa: E402
from embereye.core.tcp_sensor_server import TCPSensorServer  # noqa: E402


@dataclass
class E2EStats:
    serial_packets: int = 0
    sensor_packets: int = 0
    frame_packets: int = 0
    fusion_runs: int = 0
    fusion_alarms: int = 0


class FusionBridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = E2EStats()
        self.latest_sensor_by_loc: Dict[str, dict] = {}
        self.latest_serial: Optional[str] = None

        self.fusion = FusionOrchestrator(
            {
                "temp_threshold": 40.0,
                "critical_temp_threshold": 60.0,
                "gas_ppm_threshold": 400.0,
                "smoke_threshold_pct": 25.0,
                "flame_threshold_pct": 25.0,
                "vision_threshold": 0.7,
                "vision_confidence_weight": 0.5,
                "enable_temporal_fusion": False,
            }
        )

    def on_packet(self, packet: dict):
        pkt_type = str(packet.get("type") or "")
        loc_id = str(packet.get("loc_id") or packet.get("client_ip") or "")

        with self.lock:
            if pkt_type in ("serialno", "device_id"):
                self.stats.serial_packets += 1
                serial = packet.get("serial_number") or packet.get("serialno")
                if serial:
                    self.latest_serial = str(serial)
                return

            if pkt_type == "sensor":
                self.stats.sensor_packets += 1
                self.latest_sensor_by_loc[loc_id] = dict(packet)
                return

            if pkt_type != "frame":
                return

            self.stats.frame_packets += 1
            matrix = packet.get("matrix")
            if matrix is None:
                return

            frame_data = {"thermal": np.array(matrix, dtype=float)}
            sensor = self.latest_sensor_by_loc.get(loc_id)
            if sensor:
                adc1 = float(sensor.get("ADC1", 0.0))
                adc2 = float(sensor.get("ADC2", 0.0))
                frame_data["flame_analog_pct"] = max(0.0, min(100.0, (adc1 / 4095.0) * 100.0))
                frame_data["smoke_pct"] = max(0.0, min(100.0, (adc2 / 4095.0) * 100.0))
                frame_data["gas_ppm"] = (adc2 / 4095.0) * 1500.0
                if "MPY30" in sensor:
                    frame_data["flame_digital"] = int(float(sensor.get("MPY30", 0.0)))

            result = self.fusion.process_frame(frame_data)
            self.stats.fusion_runs += 1
            if bool(result.alarm):
                self.stats.fusion_alarms += 1


def _build_min_pfds_replay_log() -> str:
    frame_payload = "A" * 3336
    sensor_payload = "ADC1=1300,ADC2=1100,MPY30=0"
    eeprom_payload = "B" * 3328
    return (
        f"[10:00:00.000]IN #frame1:{frame_payload}!\n"
        f"[10:00:00.100]IN #Sensordemo_room:{sensor_payload}!\n"
        f"[10:00:00.200]IN #EEPROM1:{eeprom_payload}!\n"
    )


def _start_pfds_simulator(host: str, port: int, loc_id: str, replay_file: str) -> subprocess.Popen:
    script = ROOT / "simulators" / "emberhawk_simulator.py"
    cmd = [
        sys.executable,
        str(script),
        "--host",
        host,
        "--port",
        str(port),
        "--data",
        replay_file,
        "--speed",
        "8.0",
        "--no-loop",
    ]
    return subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_test(host: str, port: int, timeout_s: int) -> int:
    bridge = FusionBridge()
    server = TCPSensorServer(host=host, port=port, packet_callback=bridge.on_packet)
    sim_proc: Optional[subprocess.Popen] = None
    replay_temp: Optional[str] = None

    try:
        server.start()
        time.sleep(0.5)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
            tf.write(_build_min_pfds_replay_log())
            replay_temp = tf.name
        sim_proc = _start_pfds_simulator(host=host, port=port, loc_id="demo_room", replay_file=replay_temp)

        deadline = time.time() + float(timeout_s)
        command_kick_sent = False
        while time.time() < deadline:
            with bridge.lock:
                ready = (
                    bridge.stats.frame_packets > 0
                    and bridge.stats.sensor_packets > 0
                    and bridge.stats.fusion_runs > 0
                )
                serial = bridge.latest_serial

            # Ensure the simulator receives parseable commands through serial routing.
            if (not command_kick_sent) and serial:
                server.send_command_to_client(serial, "PERIOD_ON\n")
                server.send_command_to_client(serial, "REQUEST1\n")
                command_kick_sent = True

            if ready:
                break
            time.sleep(0.25)

        with bridge.lock:
            s = bridge.stats

        ok = (
            s.serial_packets > 0
            and s.sensor_packets > 0
            and s.frame_packets > 0
            and s.fusion_runs > 0
        )

        print(
            "PFDS_TCP_FUSION_E2E: "
            + ("PASS" if ok else "FAIL")
            + f" serial_packets={s.serial_packets}"
            + f" sensor_packets={s.sensor_packets}"
            + f" frame_packets={s.frame_packets}"
            + f" fusion_runs={s.fusion_runs}"
            + f" fusion_alarms={s.fusion_alarms}"
        )
        return 0 if ok else 1
    finally:
        try:
            server.stop()
        except Exception:
            pass

        if sim_proc is not None:
            try:
                sim_proc.terminate()
                sim_proc.wait(timeout=4)
            except Exception:
                try:
                    sim_proc.kill()
                except Exception:
                    pass
        if replay_temp:
            try:
                Path(replay_temp).unlink(missing_ok=True)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="PFDS -> TCP Server -> Fusion E2E validation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9106)
    parser.add_argument("--timeout-seconds", type=int, default=35)
    args = parser.parse_args()

    return run_test(host=args.host, port=args.port, timeout_s=max(5, args.timeout_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
