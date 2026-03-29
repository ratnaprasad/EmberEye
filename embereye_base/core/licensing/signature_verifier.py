from __future__ import annotations

import base64
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .license_signing import get_signing_payload_bytes
from .models import LicensePayload


def verify_license_payload_signature(
    payload: LicensePayload,
    signature_b64: str,
    public_key_path: Path,
) -> tuple[bool, str | None]:
    try:
        public_key_bytes = public_key_path.read_bytes()
    except OSError as exc:
        return False, f"failed to read public key: {exc}"

    try:
        public_key = serialization.load_pem_public_key(public_key_bytes)
    except ValueError as exc:
        return False, f"invalid public key format: {exc}"

    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError) as exc:
        return False, f"invalid signature encoding: {exc}"

    signing_bytes = get_signing_payload_bytes(payload)

    try:
        public_key.verify(
            signature,
            signing_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature:
        return False, "signature verification failed"
    except TypeError as exc:
        return False, f"unsupported public key type: {exc}"

    return True, None
