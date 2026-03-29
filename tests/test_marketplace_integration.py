import json
import importlib
import os
import sys
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIELDGLASS_ROOT = PROJECT_ROOT / "embereye-field" / "fieldglass"
if str(FIELDGLASS_ROOT) not in sys.path:
    sys.path.insert(0, str(FIELDGLASS_ROOT))

from PyQt6.QtWidgets import QApplication, QCheckBox

from embereye_base.core.licensing import LicenseManager
from embereye_base.core.marketplace import PluginManager


_analytics_cards_view = importlib.import_module("analytics_cards_view")
_import_analytics_dialog = importlib.import_module("import_analytics_dialog")

AnalyticCardWidget = _analytics_cards_view.AnalyticCardWidget
AnalyticsCardsView = _analytics_cards_view.AnalyticsCardsView
import_analytics_packages = _import_analytics_dialog.import_analytics_packages


def _ensure_qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_eapkg(
    package_path: Path,
    *,
    analytic_id: str,
    name: str,
    required_license: str | None = None,
):
    payload = {
        "analytic_id": analytic_id,
        "name": name,
        "version": "1.0.0",
        "module_name": analytic_id,
        "entry_class": "Analytic",
        "description": "Sample package used by marketplace integration tests.",
        "dependencies": [],
        "execution_hints": {"trigger": "every_n_frames", "value": 5},
        "required_license": required_license or analytic_id,
    }

    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("metadata.json", json.dumps(payload, indent=2))
        archive.writestr(f"{analytic_id}/__init__.py", "from .analytic import Analytic\n")
        archive.writestr(f"{analytic_id}/analytic.py", "class Analytic:\n    pass\n")


def test_marketplace_import_refresh_and_cards_render(tmp_path):
    app = _ensure_qt_app()

    source = tmp_path / "source"
    target = tmp_path / "marketplace"
    source.mkdir()

    _build_eapkg(source / "licensed_guard.eapkg", analytic_id="licensed_guard", name="Licensed Guard")
    _build_eapkg(source / "trial_guard.eapkg", analytic_id="trial_guard", name="Trial Guard")

    result = import_analytics_packages(source, target, show_progress=False)
    assert result.imported == 2
    assert result.failed == 0

    license_manager = LicenseManager(licensed_analytics=["licensed_guard"], allow_all=False)
    manager = PluginManager(target, license_manager=license_manager)
    view = AnalyticsCardsView()

    manager.scan_completed.connect(lambda: view.set_descriptors(manager.descriptors()))
    manager.refresh()
    app.processEvents()

    assert view.summary_label.text() == "Marketplace analytics: 2 (enabled: 0)"

    cards = view.findChildren(AnalyticCardWidget)
    assert len(cards) == 2

    card_by_id = {card.descriptor.analytic_id: card for card in cards}
    assert set(card_by_id) == {"licensed_guard", "trial_guard"}

    licensed_toggle = card_by_id["licensed_guard"].findChild(QCheckBox)
    trial_toggle = card_by_id["trial_guard"].findChild(QCheckBox)

    assert licensed_toggle is not None
    assert trial_toggle is not None
    assert licensed_toggle.isEnabled() is True
    assert trial_toggle.isEnabled() is False
