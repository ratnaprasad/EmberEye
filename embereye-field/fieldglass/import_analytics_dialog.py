from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QProgressDialog, QWidget

from embereye_base.core.marketplace import validate_eapkg


@dataclass(slots=True)
class ImportAnalyticsResult:
    source_dir: Path
    target_dir: Path
    discovered: int = 0
    imported: int = 0
    failed: int = 0
    canceled: bool = False
    failures: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        lines = [
            f"Imported: {self.imported}",
            f"Failed: {self.failed}",
            f"Target folder: {self.target_dir}",
        ]
        if self.canceled:
            lines.append("Status: canceled by user")

        if self.failures:
            preview = "\n".join(self.failures[:8])
            if len(self.failures) > 8:
                preview += f"\n... and {len(self.failures) - 8} more"
            lines.append("")
            lines.append("Failure details:")
            lines.append(preview)

        return "\n".join(lines)


def next_available_target_path(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    counter = 1
    while True:
        candidate = base_path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def import_analytics_packages(
    source_dir: Path,
    target_dir: Path,
    *,
    show_progress: bool = False,
    parent: QWidget | None = None,
    progress_callback=None,
) -> ImportAnalyticsResult:
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        return ImportAnalyticsResult(
            source_dir=source_dir,
            target_dir=target_dir,
            discovered=0,
            failed=1,
            failures=[f"Source directory does not exist: {source_dir}"],
        )

    candidates = sorted(source_dir.rglob("*.eapkg"))
    result = ImportAnalyticsResult(
        source_dir=source_dir,
        target_dir=target_dir,
        discovered=len(candidates),
    )

    progress = None
    if show_progress and candidates:
        progress = QProgressDialog("Importing analytics packages...", "Cancel", 0, len(candidates), parent)
        progress.setWindowTitle("Import Analytics")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

    target_dir.mkdir(parents=True, exist_ok=True)

    for index, package_path in enumerate(candidates, start=1):
        if progress and progress.wasCanceled():
            result.canceled = True
            break

        if progress:
            progress.setValue(index - 1)
            progress.setLabelText(f"Validating {package_path.name} ({index}/{len(candidates)})")
            QApplication.processEvents()
        if callable(progress_callback):
            progress_callback(
                "validate",
                {
                    "index": index,
                    "total": len(candidates),
                    "package": package_path.name,
                },
            )

        validation = validate_eapkg(package_path)
        if not validation.is_valid:
            result.failed += 1
            error_text = "; ".join(validation.errors) if validation.errors else "Unknown validation error"
            result.failures.append(f"{package_path.name}: {error_text}")
            continue

        destination = next_available_target_path(target_dir / package_path.name)

        try:
            if progress:
                progress.setLabelText(f"Importing {package_path.name} ({index}/{len(candidates)})")
                QApplication.processEvents()
            if callable(progress_callback):
                progress_callback(
                    "copy",
                    {
                        "index": index,
                        "total": len(candidates),
                        "package": package_path.name,
                    },
                )
            shutil.copy2(package_path, destination)
            result.imported += 1
        except Exception as exc:
            result.failed += 1
            result.failures.append(f"{package_path.name}: copy failed ({exc})")

    if progress:
        progress.setValue(len(candidates))
        progress.setLabelText(
            f"Completed: imported {result.imported}, failed {result.failed}, canceled={result.canceled}"
        )
        progress.close()

    if callable(progress_callback):
        progress_callback(
            "complete",
            {
                "total": len(candidates),
                "imported": result.imported,
                "failed": result.failed,
                "canceled": result.canceled,
            },
        )

    return result


class ImportAnalyticsDialog:
    """Encapsulates operator-driven analytics package import flow."""

    def __init__(self, target_dir: Path, parent: QWidget | None = None):
        self.target_dir = Path(target_dir)
        self.parent = parent

    def run(self) -> ImportAnalyticsResult | None:
        source_dir = QFileDialog.getExistingDirectory(
            self.parent,
            "Select Folder to Import Analytics",
            str(Path.home()),
        )
        if not source_dir:
            return None

        result = import_analytics_packages(
            Path(source_dir),
            self.target_dir,
            show_progress=True,
            parent=self.parent,
        )

        if result.discovered == 0:
            QMessageBox.information(
                self.parent,
                "Import Analytics",
                "No .eapkg files found in the selected folder.",
            )

        return result
