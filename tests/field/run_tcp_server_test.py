from _test_utils import get_log_path, log_line, assert_true, capture_text_screenshot

from tcp_sensor_server import TCPSensorServer


def main() -> int:
    log_path = get_log_path("tcp_server")
    packets = []

    def on_packet(packet):
        packets.append(packet)

    server = TCPSensorServer(packet_callback=on_packet)

    try:
        server.handle_packet("#serialno:123456!", client_ip="127.0.0.1")
        server.handle_packet("#locid:default room!", client_ip="127.0.0.1")
        server.handle_packet("#Sensor:ADC1=592,ADC2=610!", client_ip="127.0.0.1")

        assert_true(len(packets) == 3, f"Expected 3 packets, got {len(packets)}")
        assert_true(packets[0].get("type") == "serialno", "Serial packet type mismatch")
        assert_true(packets[0].get("serialno") == "123456", "Serial number mismatch")
        assert_true(packets[1].get("type") == "locid", "LocID packet type mismatch")
        assert_true(packets[1].get("loc_id") == "default room", "LocID mismatch")
        assert_true(packets[2].get("type") == "sensor", "Sensor packet type mismatch")
        assert_true(packets[2].get("ADC1") == 592, "Sensor ADC1 mismatch")
        assert_true(packets[2].get("ADC2") == 610, "Sensor ADC2 mismatch")
        assert_true(packets[2].get("client_ip") == "127.0.0.1", "Client IP mismatch")

        capture_text_screenshot(
            "tcp_server",
            "TCP server parsing test completed\nPackets: serialno, locid, sensor",
            log_path,
        )
        log_line(log_path, "[TCP] Server parsing test completed")
        return 0
    except Exception as e:
        log_line(log_path, f"ERROR: TCP server test failed: {e}")
        capture_text_screenshot("tcp_server_error", f"TCP server test failed\n{e}", log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
