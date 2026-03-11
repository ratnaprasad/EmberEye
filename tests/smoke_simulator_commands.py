#!/usr/bin/env python3
import argparse
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path


def run_tcp_simulator_smoke(host: str, port: int) -> bool:
    tcp_log = Path("logs/smoke_simulator_v3.log")
    try:
        tcp_log.unlink(missing_ok=True)
    except Exception:
        pass

    def server():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(1)
        conn, _ = srv.accept()
        time.sleep(0.2)
        for cmd in ("ALARM_ON\n", "ACK_ON\n", "PERIOD_OFF\n"):
            conn.sendall(cmd.encode("utf-8"))
            time.sleep(0.25)
        conn.close()
        srv.close()

    t = threading.Thread(target=server, daemon=True)
    t.start()

    proc = subprocess.Popen(
        [
            sys.executable,
            "tcp_sensor_simulator_v3.py",
            "--host",
            host,
            "--port",
            str(port),
            "--loc-id",
            "demo_room",
            "--interval",
            "0.2",
            "--log-file",
            str(tcp_log),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Let simulator connect, receive commands, and log reactions.
    time.sleep(2.5)
    proc.terminate()
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate(timeout=5)

    log_text = tcp_log.read_text(encoding="utf-8") if tcp_log.exists() else ""
    ok_alarm = "Received ALARM_ON command - siren state ACTIVE" in log_text
    ok_ack = "Received ACK_ON command - siren acknowledged" in log_text
    print("[tcp_sensor_simulator_v3] alarm_on_handled=", ok_alarm)
    print("[tcp_sensor_simulator_v3] ack_on_handled=", ok_ack)
    if not (ok_alarm and ok_ack):
        print("--- stdout ---")
        print(out)
        print("--- stderr ---")
        print(err)
        print("--- log ---")
        print(log_text)
    return ok_alarm and ok_ack


def _build_min_pfds_log() -> str:
    frame_payload = "A" * 3336
    sensor_payload = "ADC1=1200,ADC2=900,MPY30=0"
    eeprom_payload = "B" * 3328
    return textwrap.dedent(
        f"""
        [10:00:00.000]IN #frame1:{frame_payload}!
        [10:00:00.100]IN #Sensordemo_room:{sensor_payload}!
        [10:00:00.200]IN #EEPROM1:{eeprom_payload}!
        """
    ).strip() + "\n"


def run_pfds_simulator_smoke(host: str, port: int) -> bool:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write(_build_min_pfds_log())
        temp_log = tf.name

    try:
        def server():
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((host, port))
            srv.listen(1)
            conn, _ = srv.accept()
            time.sleep(0.2)
            for cmd in ("ALARM_ON\n", "ACK_ON\n", "PERIOD_OFF\n"):
                conn.sendall(cmd.encode("utf-8"))
                time.sleep(0.25)
            conn.close()
            srv.close()

        t = threading.Thread(target=server, daemon=True)
        t.start()

        log_path = Path("simulators/pfds/logs/simulator_debug.log")
        try:
            log_path.unlink(missing_ok=True)
        except Exception:
            pass

        proc = subprocess.Popen(
            [
                sys.executable,
                "simulators/pfds/pfds_simulator.py",
                "--host",
                host,
                "--port",
                str(port),
                "--loc-id",
                "demo_room",
                "--data",
                temp_log,
                "--no-loop",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Allow command exchange and logging, then stop simulator.
        time.sleep(3.0)
        proc.terminate()
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate(timeout=5)

        # PFDS simulator logs to file; verify by log content.
        log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        ok_alarm = "Received ALARM_ON command - siren state ACTIVE" in log_text
        ok_ack = "Received ACK_ON command - siren acknowledged" in log_text
        print("[pfds_simulator] alarm_on_handled=", ok_alarm)
        print("[pfds_simulator] ack_on_handled=", ok_ack)
        if not (ok_alarm and ok_ack):
            print("--- stdout ---")
            print(out)
            print("--- stderr ---")
            print(err)
        return ok_alarm and ok_ack
    finally:
        try:
            Path(temp_log).unlink(missing_ok=True)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test ALARM_ON/ACK_ON command handling in simulators")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-port", type=int, default=9101)
    args = parser.parse_args()

    ok_tcp = run_tcp_simulator_smoke(args.host, args.base_port)
    ok_pfds = run_pfds_simulator_smoke(args.host, args.base_port + 1)

    print("RESULT tcp_sensor_simulator_v3:", "PASS" if ok_tcp else "FAIL")
    print("RESULT pfds_simulator:", "PASS" if ok_pfds else "FAIL")
    return 0 if (ok_tcp and ok_pfds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
