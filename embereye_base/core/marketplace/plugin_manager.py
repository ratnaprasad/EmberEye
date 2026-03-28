from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QFileSystemWatcher, pyqtSignal

from embereye_base.core.licensing import LicenseManager

from .eapkg_validator import validate_eapkg
from .models import AnalyticDescriptor
from .plugin_registry import PluginRegistry


class PluginManager(QObject):
    analytic_added = pyqtSignal(str)
    analytic_removed = pyqtSignal(str)
    analytic_updated = pyqtSignal(str)
    scan_completed = pyqtSignal()

    def __init__(self, marketplace_dir: str | Path, license_manager: LicenseManager | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.marketplace_dir = Path(marketplace_dir).expanduser()
        self.marketplace_dir.mkdir(parents=True, exist_ok=True)
        self.license_manager = license_manager or LicenseManager()
        self.registry = PluginRegistry()
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(str(self.marketplace_dir))
        self.watcher.directoryChanged.connect(self.refresh)

    def refresh(self) -> None:
        seen_ids: set[str] = set()

        for package_path in sorted(self.marketplace_dir.glob("*.eapkg")):
            validation = validate_eapkg(package_path)
            if not validation.is_valid or not validation.metadata:
                continue

            metadata = validation.metadata
            license_key = metadata.required_license or metadata.analytic_id
            descriptor = AnalyticDescriptor(
                analytic_id=metadata.analytic_id,
                package_path=package_path,
                metadata=metadata,
                license_status=(
                    "licensed"
                    if self.license_manager.is_analytic_licensed(license_key)
                    else "unlicensed"
                ),
            )

            seen_ids.add(descriptor.analytic_id)
            existing = self.registry.get(descriptor.analytic_id)
            self.registry.upsert(descriptor)

            if existing is None:
                self.analytic_added.emit(descriptor.analytic_id)
            else:
                self.analytic_updated.emit(descriptor.analytic_id)

        for analytic_id in self.registry.ids() - seen_ids:
            self.registry.remove(analytic_id)
            self.analytic_removed.emit(analytic_id)

        self.scan_completed.emit()

    def descriptors(self) -> list[AnalyticDescriptor]:
        return self.registry.all()
