from __future__ import annotations

import argparse
from pathlib import Path

from .license_signing import write_signed_license_file
from .models import LicensePayload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate signed EmberEye .lic files")
    parser.add_argument("--customer", required=True, help="Customer name")
    parser.add_argument("--private-key", required=True, help="Path to PEM private key")
    parser.add_argument("--output", required=True, help="Output .lic file path")
    parser.add_argument("--hardware-id", default="", help="Bound hardware ID")
    parser.add_argument("--max-devices", type=int, default=0, help="Maximum allowed devices")
    parser.add_argument("--expiry", default=None, help="Expiry date in YYYY-MM-DD format")
    parser.add_argument(
        "--analytic",
        action="append",
        default=[],
        help="Licensed analytic id (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    payload = LicensePayload(
        customer=args.customer,
        hardware_id=args.hardware_id,
        max_devices=args.max_devices,
        analytics=[item.strip() for item in args.analytic if item.strip()],
        expiry=args.expiry,
    )
    output = write_signed_license_file(payload, args.private_key, args.output)
    print(f"Wrote signed license: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
