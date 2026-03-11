import json
import tempfile
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "embereye-field" / "hawkcore"))

from emberhawk_manager import EmberHawkManager  # noqa: E402


def _run() -> int:
    audit_path = root / "logs" / "device_audit.jsonl"
    before_lines = 0
    if audit_path.exists():
        try:
            before_lines = len(audit_path.read_text(encoding="utf-8").splitlines())
        except Exception:
            before_lines = 0

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "pfds_devices_test.db"
        mgr = EmberHawkManager(db_path=db_path)

        did = mgr.add_device(
            name="dev-audit",
            ip="10.0.1.10:5000",
            location_id="room_audit",
            mode="On Demand",
            poll_seconds=5,
        )
        mgr.set_device_access(
            did,
            is_authorized=False,
            is_linked=False,
            actor="test:device_access_audit",
            reason="unit_test",
        )

    if not audit_path.exists():
        print("DEVICE_ACCESS_AUDIT_TEST: FAIL - audit file missing")
        return 1

    try:
        lines = audit_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"DEVICE_ACCESS_AUDIT_TEST: FAIL - cannot read audit file: {e}")
        return 1

    if len(lines) <= before_lines:
        print("DEVICE_ACCESS_AUDIT_TEST: FAIL - no new audit line appended")
        return 1

    candidate = None
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("event") == "device_access_changed" and rec.get("payload", {}).get("actor") == "test:device_access_audit":
            candidate = rec
            break

    if not candidate:
        print("DEVICE_ACCESS_AUDIT_TEST: FAIL - expected audit event not found")
        return 1

    payload = candidate.get("payload", {})
    if payload.get("reason") != "unit_test":
        print("DEVICE_ACCESS_AUDIT_TEST: FAIL - reason mismatch")
        return 1

    print("DEVICE_ACCESS_AUDIT_TEST: PASS")
    return 0


def main() -> int:
    return _run()


if __name__ == "__main__":
    raise SystemExit(main())
