import json
from pathlib import Path

from embereye_base.core.licensing import LicenseManager, get_embereye_home, get_license_dir


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