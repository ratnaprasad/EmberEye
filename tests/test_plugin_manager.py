import json
import zipfile
from pathlib import Path

from PyQt6.QtCore import QCoreApplication

from embereye_base.core.licensing import LicenseManager
from embereye_base.core.marketplace import PluginManager


def _ensure_qt_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _build_eapkg(
    package_path: Path,
    *,
    analytic_id: str = "sample_guard",
    name: str = "Sample Guard",
    version: str = "1.0.0",
    required_license: str | None = "sample_guard",
    include_metadata: bool = True,
    include_module_init: bool = True,
    include_analytic_impl: bool = True,
):
    payload = {
        "analytic_id": analytic_id,
        "name": name,
        "version": version,
        "module_name": analytic_id,
        "entry_class": "Analytic",
        "description": "Sample package used by plugin manager tests.",
        "dependencies": [],
        "execution_hints": {"trigger": "every_n_frames", "value": 5},
        "required_license": required_license,
    }

    with zipfile.ZipFile(package_path, "w") as archive:
        if include_metadata:
            archive.writestr("metadata.json", json.dumps(payload, indent=2))
        if include_module_init:
            archive.writestr(f"{analytic_id}/__init__.py", "from .analytic import Analytic\n")
        if include_analytic_impl:
            archive.writestr(f"{analytic_id}/analytic.py", "class Analytic:\n    pass\n")


def test_plugin_manager_adds_descriptor_and_applies_license_state(tmp_path):
    _ensure_qt_app()

    package_path = tmp_path / "sample_guard-1.0.0.eapkg"
    _build_eapkg(package_path)

    license_manager = LicenseManager(licensed_analytics=["sample_guard"], allow_all=False)
    manager = PluginManager(tmp_path, license_manager=license_manager)

    added_events = []
    manager.analytic_added.connect(added_events.append)

    manager.refresh()

    descriptors = manager.descriptors()
    assert len(descriptors) == 1
    assert descriptors[0].analytic_id == "sample_guard"
    assert descriptors[0].license_status == "licensed"
    assert added_events == ["sample_guard"]


def test_plugin_manager_emits_update_for_existing_descriptor(tmp_path):
    _ensure_qt_app()

    package_path = tmp_path / "sample_guard-1.0.0.eapkg"
    _build_eapkg(package_path, version="1.0.0")

    manager = PluginManager(tmp_path)
    updated_events = []
    manager.analytic_updated.connect(updated_events.append)

    manager.refresh()

    _build_eapkg(package_path, version="1.0.1")
    manager.refresh()

    descriptors = manager.descriptors()
    assert len(descriptors) == 1
    assert descriptors[0].metadata.version == "1.0.1"
    assert updated_events == ["sample_guard"]


def test_plugin_manager_emits_remove_when_package_deleted(tmp_path):
    _ensure_qt_app()

    package_path = tmp_path / "sample_guard-1.0.0.eapkg"
    _build_eapkg(package_path)

    manager = PluginManager(tmp_path)
    removed_events = []
    manager.analytic_removed.connect(removed_events.append)

    manager.refresh()

    package_path.unlink()
    manager.refresh()

    assert manager.descriptors() == []
    assert removed_events == ["sample_guard"]


def test_plugin_manager_ignores_invalid_packages(tmp_path):
    _ensure_qt_app()

    invalid_path = tmp_path / "broken.eapkg"
    _build_eapkg(invalid_path, include_analytic_impl=False)

    manager = PluginManager(tmp_path)
    manager.refresh()

    assert manager.descriptors() == []
