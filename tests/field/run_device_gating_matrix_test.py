import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "embereye-field" / "fieldglass"))
sys.path.insert(0, str(root))

from main_window import BEMainWindow  # noqa: E402


class _FakeManager:
    def __init__(self, device_by_serial):
        self._device_by_serial = dict(device_by_serial)

    def get_device_by_serial(self, serial):
        key = str(serial or "").strip()
        return self._device_by_serial.get(key)

    def bind_serial_to_existing_device(self, serial, client_ip):
        return self.get_device_by_serial(serial)

    def touch_device_seen(self, serial, client_ip):
        return None


class _WindowStub:
    _normalize_loc_key = BEMainWindow._normalize_loc_key
    _normalize_serial_key = BEMainWindow._normalize_serial_key
    _parse_seen_timestamp = BEMainWindow._parse_seen_timestamp
    _get_device_lifecycle_state = BEMainWindow._get_device_lifecycle_state
    _emit_device_telemetry = BEMainWindow._emit_device_telemetry
    _resolve_packet_identity = BEMainWindow._resolve_packet_identity
    _is_packet_authorized_and_linked = BEMainWindow._is_packet_authorized_and_linked

    def __init__(self, device_by_serial):
        self.emberhawk = _FakeManager(device_by_serial)
        self._serial_by_client_ip = {}
        self._loc_by_serial = {}
        self._pending_warned_tokens = {}
        self._device_ghost_after_s = 120


def _device(serial, authorized, linked):
    return {
        "id": 1,
        "name": "dev-1",
        "location_id": "room_a",
        "serial_number": serial,
        "is_authorized": bool(authorized),
        "is_linked": bool(linked),
        "last_seen_at": None,
    }


def _run_matrix() -> int:
    failures = []

    # serial present + all combinations of authorized/linked.
    combos = [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ]
    for authorized, linked, expected in combos:
        serial = f"SER-{int(authorized)}{int(linked)}"
        stub = _WindowStub({serial: _device(serial, authorized, linked)})
        packet = {"type": "sensor", "serial_number": serial, "client_ip": "10.0.0.10"}
        result = stub._is_packet_authorized_and_linked(packet)
        if result != expected:
            failures.append(
                f"combo authorized={authorized} linked={linked} expected={expected} got={result}"
            )

    # Missing serial should always drop.
    stub_missing = _WindowStub({})
    missing_packet = {"type": "sensor", "client_ip": "10.0.0.11"}
    if stub_missing._is_packet_authorized_and_linked(missing_packet):
        failures.append("missing serial packet should be dropped")

    # Unknown serial should be pending and dropped.
    stub_unknown = _WindowStub({})
    unknown_packet = {"type": "sensor", "serial_number": "SER-UNKNOWN", "client_ip": "10.0.0.12"}
    if stub_unknown._is_packet_authorized_and_linked(unknown_packet):
        failures.append("unknown serial packet should be dropped")

    if failures:
        print("DEVICE_GATING_MATRIX: FAIL")
        for item in failures:
            print(" -", item)
        return 1

    print("DEVICE_GATING_MATRIX: PASS")
    return 0


def main() -> int:
    return _run_matrix()


if __name__ == "__main__":
    raise SystemExit(main())
