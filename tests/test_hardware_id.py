from embereye_base.core.licensing import get_hardware_id, get_hardware_id_components


def test_hardware_id_components_have_expected_keys():
    components = get_hardware_id_components()

    assert set(components.keys()) == {
        "system",
        "hostname",
        "machine_identifier",
        "mac_address",
    }
    assert isinstance(components["mac_address"], str)
    assert len(components["mac_address"]) == 12


def test_hardware_id_override_is_respected(monkeypatch):
    monkeypatch.setenv("EMBEREYE_HARDWARE_ID", "developer-override")

    assert get_hardware_id() == "developer-override"
