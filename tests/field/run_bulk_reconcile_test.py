import tempfile
from pathlib import Path

import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "embereye-field" / "hawkcore"))

from emberhawk_manager import EmberHawkManager  # noqa: E402


def _run() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "pfds_devices_test.db"
        mgr = EmberHawkManager(db_path=db_path)

        # Device without serial, endpoint host matches pending identity IP.
        did = mgr.add_device(
            name="dev-a",
            ip="10.0.0.20:5000",
            location_id="room_a",
            mode="On Demand",
            poll_seconds=5,
        )
        mgr.set_device_access(did, is_authorized=True, is_linked=False)

        pending = {
            "SER-NEW-001": {
                "client_ip": "10.0.0.20",
                "last_seen": 0,
            },
            "SER-UNMATCHED": {
                "client_ip": "10.0.0.77",
                "last_seen": 0,
            },
        }

        summary = mgr.bulk_reconcile_pending_serials(pending, auto_link=True)

        bound = mgr.get_device_by_serial("SER-NEW-001")
        if not bound:
            print("BULK_RECONCILE_TEST: FAIL - expected serial SER-NEW-001 to bind")
            return 1
        if not bool(bound.get("is_linked", False)):
            print("BULK_RECONCILE_TEST: FAIL - expected bound device to be linked")
            return 1

        if int(summary.get("bound", 0)) != 1:
            print(f"BULK_RECONCILE_TEST: FAIL - expected bound=1, got {summary}")
            return 1
        if int(summary.get("unmatched", 0)) != 1:
            print(f"BULK_RECONCILE_TEST: FAIL - expected unmatched=1, got {summary}")
            return 1

    print("BULK_RECONCILE_TEST: PASS")
    return 0


def main() -> int:
    return _run()


if __name__ == "__main__":
    raise SystemExit(main())
