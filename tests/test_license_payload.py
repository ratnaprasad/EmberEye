import pytest

from embereye_base.core.licensing import LicensePayload


def test_license_payload_from_dict_parses_expected_fields():
    payload = LicensePayload.from_dict(
        {
            "customer": "Acme",
            "hardware_id": "abc123",
            "max_devices": 3,
            "analytics": ["fire", "ppe"],
            "expiry": "2026-12-31",
            "signature": "signed",
        }
    )

    assert payload.customer == "Acme"
    assert payload.hardware_id == "abc123"
    assert payload.max_devices == 3
    assert payload.analytics == ["fire", "ppe"]
    assert payload.expiry == "2026-12-31"
    assert payload.signature == "signed"


def test_license_payload_rejects_missing_customer():
    with pytest.raises(ValueError, match="missing required field: customer"):
        LicensePayload.from_dict({"max_devices": 1, "analytics": []})


def test_license_payload_rejects_invalid_analytics_type():
    with pytest.raises(ValueError, match="field 'analytics' must be a list"):
        LicensePayload.from_dict({"customer": "Acme", "analytics": "fire"})


def test_signing_payload_dict_excludes_signature_field():
    payload = LicensePayload.from_dict(
        {
            "customer": "Acme",
            "hardware_id": "abc123",
            "max_devices": 3,
            "analytics": ["fire"],
            "expiry": "2026-12-31",
            "signature": "signed",
        }
    )

    signing_payload = payload.signing_payload_dict()
    assert "signature" not in signing_payload
    assert signing_payload["customer"] == "Acme"