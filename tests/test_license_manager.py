import json
from base64 import b64encode
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from embereye_base.core.licensing import LicenseManager, get_embereye_home, get_license_dir


def _create_test_key_pair(tmp_path: Path) -> tuple[Any, Path]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    public_key_path = tmp_path / "license_public_key.pem"
    public_key_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_key, public_key_path


def _sign_license_payload(private_key, payload: dict) -> str:
    signing_payload = {
        "customer": payload["customer"],
        "hardware_id": payload.get("hardware_id", ""),
        "max_devices": payload.get("max_devices", 0),
        "analytics": payload.get("analytics", []),
        "expiry": payload.get("expiry"),
    }
    signing_bytes = json.dumps(signing_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(signing_bytes, padding.PKCS1v15(), hashes.SHA256())
    return b64encode(signature).decode("utf-8")


def test_license_paths_respect_embereye_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEREYE_HOME", str(tmp_path / "embereye-home"))

    home = get_embereye_home()
    license_dir = get_license_dir()

    assert home == tmp_path / "embereye-home"
    assert license_dir == home / "licenses"
    assert license_dir.exists()


def test_license_manager_refresh_merges_license_files(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "a.lic").write_text(
        json.dumps(
            {
                "customer": "Acme",
                "max_devices": 2,
                "analytics": ["fire", "ppe"],
            }
        ),
        encoding="utf-8",
    )
    (license_dir / "b.lic").write_text(
        json.dumps(
            {
                "customer": "Acme Expansion",
                "max_devices": 5,
                "analytics": ["thermal"],
            }
        ),
        encoding="utf-8",
    )

    manager = LicenseManager(allow_all=False, license_dir=license_dir)
    state = manager.refresh_from_directory()

    assert manager.get_license_dir() == license_dir
    assert manager.get_max_devices() == 5
    assert sorted(state.analytics) == ["fire", "ppe", "thermal"]
    assert manager.is_analytic_licensed("thermal") is True
    assert len(manager.get_license_summary()) == 2
    assert manager.get_invalid_license_files() == []


def test_license_manager_skips_invalid_license_files(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "good.lic").write_text(
        json.dumps(
            {
                "customer": "Valid Customer",
                "max_devices": 1,
                "analytics": ["fire"],
            }
        ),
        encoding="utf-8",
    )
    (license_dir / "bad.lic").write_text("not-json", encoding="utf-8")

    manager = LicenseManager(allow_all=False, license_dir=license_dir)
    state = manager.refresh_from_directory()

    assert state.max_devices == 1
    assert state.analytics == ["fire"]
    assert len(state.invalid_files) == 1
    assert "bad.lic" in state.invalid_files[0]


def test_license_manager_bypasses_hardware_mismatch_by_default(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "bound.lic").write_text(
        json.dumps(
            {
                "customer": "Bound Customer",
                "hardware_id": "expected-device",
                "max_devices": 2,
                "analytics": ["fire"],
            }
        ),
        encoding="utf-8",
    )

    manager = LicenseManager(allow_all=False, license_dir=license_dir)
    manager.hardware_id = "local-device"
    state = manager.refresh_from_directory()

    assert state.analytics == ["fire"]
    assert state.invalid_files == []
    assert len(state.mismatched_files) == 1
    assert state.hardware_id_enforced is False
    assert state.loaded_files[0].hardware_match is False
    assert state.loaded_files[0].status.endswith("hardware-mismatch-bypassed")


def test_license_manager_can_enforce_hardware_match(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "bound.lic").write_text(
        json.dumps(
            {
                "customer": "Bound Customer",
                "hardware_id": "expected-device",
                "max_devices": 2,
                "analytics": ["fire"],
            }
        ),
        encoding="utf-8",
    )

    manager = LicenseManager(allow_all=False, license_dir=license_dir, enforce_hardware_id=True)
    manager.hardware_id = "local-device"
    state = manager.refresh_from_directory()

    assert state.analytics == []
    assert state.max_devices == 0
    assert state.hardware_id_enforced is True
    assert state.loaded_files == []
    assert len(state.mismatched_files) == 1
    assert len(state.invalid_files) == 1
    assert "hardware_id mismatch" in state.invalid_files[0]


def test_license_manager_accepts_valid_signature_when_enforced(tmp_path):
    private_key, public_key_path = _create_test_key_pair(tmp_path)
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    payload = {
        "customer": "Signed Customer",
        "hardware_id": "",
        "max_devices": 3,
        "analytics": ["fire", "ppe"],
        "expiry": "2027-01-01",
    }
    payload["signature"] = _sign_license_payload(private_key, payload)

    (license_dir / "signed.lic").write_text(json.dumps(payload), encoding="utf-8")

    manager = LicenseManager(
        allow_all=False,
        license_dir=license_dir,
        enforce_signature=True,
        public_key_path=public_key_path,
    )
    state = manager.refresh_from_directory()

    assert sorted(state.analytics) == ["fire", "ppe"]
    assert state.invalid_files == []
    assert state.signature_issues == []
    assert len(state.loaded_files) == 1
    assert state.loaded_files[0].status == "signature-verified"


def test_license_manager_rejects_invalid_signature_when_enforced(tmp_path):
    _, public_key_path = _create_test_key_pair(tmp_path)
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    payload = {
        "customer": "Signed Customer",
        "hardware_id": "",
        "max_devices": 3,
        "analytics": ["fire", "ppe"],
        "expiry": "2027-01-01",
        "signature": "invalid-base64***",
    }
    (license_dir / "signed.lic").write_text(json.dumps(payload), encoding="utf-8")

    manager = LicenseManager(
        allow_all=False,
        license_dir=license_dir,
        enforce_signature=True,
        public_key_path=public_key_path,
    )
    state = manager.refresh_from_directory()

    assert state.analytics == []
    assert state.loaded_files == []
    assert len(state.signature_issues) == 1
    assert len(state.invalid_files) == 1
    assert "invalid signature encoding" in state.invalid_files[0]


def test_license_manager_bypasses_expired_license_by_default(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "expired.lic").write_text(
        json.dumps(
            {
                "customer": "Expired Customer",
                "max_devices": 1,
                "analytics": ["fire"],
                "expiry": "2000-01-01",
            }
        ),
        encoding="utf-8",
    )

    manager = LicenseManager(allow_all=False, license_dir=license_dir)
    state = manager.refresh_from_directory()

    assert state.expiry_enforced is False
    assert state.analytics == ["fire"]
    assert len(state.expiry_issues) == 1
    assert state.invalid_files == []
    assert state.loaded_files[0].status.endswith("expired-bypassed")


def test_license_manager_enforces_expiry_when_enabled(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "expired.lic").write_text(
        json.dumps(
            {
                "customer": "Expired Customer",
                "max_devices": 1,
                "analytics": ["fire"],
                "expiry": "2000-01-01",
            }
        ),
        encoding="utf-8",
    )

    manager = LicenseManager(allow_all=False, license_dir=license_dir, enforce_expiry=True)
    state = manager.refresh_from_directory()

    assert state.expiry_enforced is True
    assert state.analytics == []
    assert state.max_devices == 0
    assert state.loaded_files == []
    assert len(state.expiry_issues) == 1
    assert len(state.invalid_files) == 1
    assert "license expired" in state.invalid_files[0]


def test_license_manager_accepts_non_expired_license_when_enforced(tmp_path):
    license_dir = tmp_path / "licenses"
    license_dir.mkdir()

    (license_dir / "active.lic").write_text(
        json.dumps(
            {
                "customer": "Active Customer",
                "max_devices": 2,
                "analytics": ["fire", "ppe"],
                "expiry": "2999-01-01",
            }
        ),
        encoding="utf-8",
    )

    manager = LicenseManager(allow_all=False, license_dir=license_dir, enforce_expiry=True)
    state = manager.refresh_from_directory()

    assert state.expiry_enforced is True
    assert sorted(state.analytics) == ["fire", "ppe"]
    assert state.invalid_files == []
    assert state.expiry_issues == []
    assert state.loaded_files[0].status == "unsigned-development"