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

        did = mgr.add_device(
            name="dev-a",
            ip="10.0.0.20:5000",
            location_id="room_a",
            mode="On Demand",
            poll_seconds=5,
        )
        mgr.set_device_access(did, is_authorized=True, is_linked=False)

        pending = {
            "SER-DRY-001": {
                "client_ip": "10.0.0.20",
                "last_seen": 0,
            },
        }

        summary = mgr.bulk_reconcile_pending_serials(pending, auto_link=True, dry_run=True)

        if not bool(summary.get("dry_run", False)):
            print(f"BULK_RECONCILE_DRY_RUN_TEST: FAIL - dry_run flag missing: {summary}")
            return 1
        if int(summary.get("would_bind", 0)) != 1:
            print(f"BULK_RECONCILE_DRY_RUN_TEST: FAIL - expected would_bind=1: {summary}")
            return 1
        if int(summary.get("bound", 0)) != 0:
            print(f"BULK_RECONCILE_DRY_RUN_TEST: FAIL - expected bound=0 in dry run: {summary}")
            return 1

        # DB state must remain unchanged in dry-run.
        bound = mgr.get_device_by_serial("SER-DRY-001")
        if bound is not None:
            print("BULK_RECONCILE_DRY_RUN_TEST: FAIL - serial was bound during dry run")
            return 1

        rows = summary.get("report_rows") or []
        if not rows or rows[0].get("status") != "would_bind":
            print(f"BULK_RECONCILE_DRY_RUN_TEST: FAIL - expected report_rows status=would_bind: {summary}")
            return 1

    print("BULK_RECONCILE_DRY_RUN_TEST: PASS")
    return 0


def main() -> int:
    return _run()


if __name__ == "__main__":
    raise SystemExit(main())
