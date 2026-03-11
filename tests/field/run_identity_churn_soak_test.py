#!/usr/bin/env python3
import argparse
import random
import tempfile
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "embereye-field" / "hawkcore"))

from emberhawk_manager import EmberHawkManager  # noqa: E402


def _fail(msg: str) -> int:
    print(f"IDENTITY_CHURN_SOAK: FAIL - {msg}")
    return 1


def run_soak(devices: int, rounds: int, seed: int) -> int:
    rng = random.Random(seed)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "pfds_devices_test.db"
        mgr = EmberHawkManager(db_path=db_path)

        base_ips = [f"10.0.{i // 250}.{(i % 250) + 1}" for i in range(max(devices, 10))]
        serials = [f"SER-SOAK-{i:05d}" for i in range(devices)]

        # Seed devices in DB without serials.
        for i in range(devices):
            ip = f"{base_ips[i]}:5000"
            did = mgr.add_device(
                name=f"soak-dev-{i}",
                ip=ip,
                location_id=f"room_{i % 20}",
                mode="On Demand",
                poll_seconds=5,
            )
            mgr.set_device_access(did, is_authorized=True, is_linked=False)

        total_attempted = 0
        total_bound = 0
        total_unmatched = 0
        total_errors = 0

        for r in range(rounds):
            pending = {}
            # Build reconnect storm: random subset of serial identities seen from random endpoints.
            active_count = max(1, devices // 2)
            chosen = rng.sample(serials, k=active_count)

            for serial in chosen:
                idx = int(serial.rsplit("-", 1)[-1])
                # 80% expected endpoint/host, 20% churned/unmatched endpoint.
                if rng.random() < 0.8:
                    client_ip = base_ips[idx]
                else:
                    client_ip = f"172.16.{rng.randint(0, 31)}.{rng.randint(1, 254)}"
                pending[serial] = {
                    "client_ip": client_ip,
                    "last_seen": r,
                }

            summary = mgr.bulk_reconcile_pending_serials(
                pending,
                auto_link=True,
                actor="test:identity_churn_soak",
                dry_run=False,
            )

            total_attempted += int(summary.get("attempted", 0))
            total_bound += int(summary.get("bound", 0))
            total_unmatched += int(summary.get("unmatched", 0))
            total_errors += int(summary.get("errors", 0))

            # Invariant: no duplicate bound serials in DB.
            listed = mgr.list_devices()
            bound_serials = [str(d.get("serial_number") or "").strip() for d in listed if str(d.get("serial_number") or "").strip()]
            if len(bound_serials) != len(set(bound_serials)):
                return _fail(f"duplicate serial detected at round={r}")

            # Invariant: bound devices from this run must be linked.
            for serial in summary.get("bound_serials", []):
                d = mgr.get_device_by_serial(serial)
                if not d:
                    return _fail(f"serial bound then missing from DB: {serial}")
                if not bool(d.get("is_linked", False)):
                    return _fail(f"bound serial is not linked: {serial}")

        if total_errors != 0:
            return _fail(f"reconcile returned errors={total_errors}")
        if total_attempted == 0:
            return _fail("no attempts executed")

        print(
            "IDENTITY_CHURN_SOAK: PASS "
            f"devices={devices} rounds={rounds} attempted={total_attempted} "
            f"bound={total_bound} unmatched={total_unmatched}"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Identity churn/reconnect storm soak test")
    parser.add_argument("--devices", type=int, default=60)
    parser.add_argument("--rounds", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    return run_soak(devices=max(1, args.devices), rounds=max(1, args.rounds), seed=args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
