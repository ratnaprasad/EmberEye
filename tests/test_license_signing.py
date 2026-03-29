import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from embereye_base.core.licensing import (
    LicensePayload,
    verify_license_payload_signature,
)
from embereye_base.core.licensing.cli import main as license_cli_main
from embereye_base.core.licensing.license_signing import write_signed_license_file


def _create_key_pair(tmp_path: Path) -> tuple[Path, Path]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_key_path = tmp_path / "private_key.pem"
    public_key_path = tmp_path / "public_key.pem"

    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_key_path, public_key_path


def test_write_signed_license_file_produces_verifiable_signature(tmp_path):
    private_key_path, public_key_path = _create_key_pair(tmp_path)
    payload = LicensePayload(
        customer="Acme",
        hardware_id="hw-1",
        max_devices=3,
        analytics=["fire", "ppe"],
        expiry="2027-12-31",
    )

    output_path = tmp_path / "license.lic"
    write_signed_license_file(payload, private_key_path, output_path)

    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    loaded_payload = LicensePayload.from_dict(loaded)
    assert loaded_payload.signature is not None

    ok, error = verify_license_payload_signature(loaded_payload, loaded_payload.signature, public_key_path)
    assert ok is True
    assert error is None


def test_license_cli_writes_signed_file(tmp_path):
    private_key_path, public_key_path = _create_key_pair(tmp_path)
    output_path = tmp_path / "generated.lic"

    exit_code = license_cli_main(
        [
            "--customer",
            "CLI Customer",
            "--private-key",
            str(private_key_path),
            "--output",
            str(output_path),
            "--hardware-id",
            "hw-cli",
            "--max-devices",
            "5",
            "--expiry",
            "2028-01-01",
            "--analytic",
            "fire",
            "--analytic",
            "ppe",
        ]
    )

    assert exit_code == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    payload = LicensePayload.from_dict(written)
    assert payload.customer == "CLI Customer"
    assert payload.analytics == ["fire", "ppe"]
    assert payload.signature is not None

    ok, error = verify_license_payload_signature(payload, payload.signature, public_key_path)
    assert ok is True
    assert error is None
