from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .models import LicensePayload


def get_signing_payload_bytes(payload: LicensePayload) -> bytes:
    return json.dumps(
        payload.signing_payload_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_license_payload(payload: LicensePayload, private_key_path: str | Path) -> str:
    key_path = Path(private_key_path).expanduser()
    private_key_bytes = key_path.read_bytes()
    private_key = serialization.load_pem_private_key(private_key_bytes, password=None)

    signature = private_key.sign(
        get_signing_payload_bytes(payload),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def create_signed_license_dict(payload: LicensePayload, private_key_path: str | Path) -> dict[str, object]:
    signature = sign_license_payload(payload, private_key_path)
    return {
        "customer": payload.customer,
        "hardware_id": payload.hardware_id,
        "max_devices": payload.max_devices,
        "analytics": list(payload.analytics),
        "expiry": payload.expiry,
        "signature": signature,
    }


def write_signed_license_file(
    payload: LicensePayload,
    private_key_path: str | Path,
    output_path: str | Path,
) -> Path:
    target_path = Path(output_path).expanduser()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    signed_payload = create_signed_license_dict(payload, private_key_path)
    target_path.write_text(json.dumps(signed_payload, indent=2, sort_keys=True), encoding="utf-8")
    return target_path
