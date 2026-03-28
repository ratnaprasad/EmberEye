import json
import os
import sys
import zipfile
from pathlib import Path

from PIL import Image
from PyQt6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDIO_ROOT = PROJECT_ROOT / "embereye-studio"
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

import studio_main_window as smw
from embereye.core import class_config


def _write_image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), (255, 0, 0)).save(path)


def _build_zip_dataset(root: Path) -> Path:
    source_root = root / "source"
    _write_image(source_root / "images" / "train" / "sample.jpg")
    (source_root / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (source_root / "labels" / "train" / "sample.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n",
        encoding="utf-8",
    )
    (source_root / "data.yaml").write_text("names: [ember_flame]\n", encoding="utf-8")

    zip_path = root / "source.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for source in source_root.rglob("*"):
            if source.is_file():
                archive.write(source, source.relative_to(source_root))
    return zip_path


def test_dataset_tab_import_external_zip_with_class_creation(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    workspace_root = tmp_path / "workspace"
    config_path = tmp_path / "config" / "master_classes.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(class_config.DEFAULT_MASTER_CLASSES, indent=2), encoding="utf-8")

    stream_config = tmp_path / "stream_config.json"
    stream_config.write_text(json.dumps({"active_analytics_category": "fire"}), encoding="utf-8")
    zip_path = _build_zip_dataset(tmp_path)

    captured_info = []
    captured_critical = []

    monkeypatch.setattr(class_config, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(
        "external_dataset_importer.get_data_path",
        lambda relative_path: str(workspace_root / relative_path),
    )
    monkeypatch.setattr(smw.DatasetTab, "_shared_stream_config_path", lambda self: stream_config)

    item_responses = iter(
        [
            ("Local ZIP", True),
            ("Create new class in current analytics domain", True),
        ]
    )

    monkeypatch.setattr(
        smw.QInputDialog,
        "getItem",
        lambda *args, **kwargs: next(item_responses),
    )
    monkeypatch.setattr(smw.QInputDialog, "getText", lambda *args, **kwargs: ("EMBER FLAME", True))
    monkeypatch.setattr(smw.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(zip_path), "ZIP Files (*.zip)"))
    monkeypatch.setattr(smw.QMessageBox, "information", lambda *args, **kwargs: captured_info.append(args[2]) or 0)
    monkeypatch.setattr(smw.QMessageBox, "critical", lambda *args, **kwargs: captured_critical.append(args[2]) or 0)

    tab = smw.DatasetTab()
    tab.import_external_dataset()

    text = tab.dataset_list.toPlainText()
    assert "[EXTERNAL]" in text
    assert "Created classes: 1" in text
    assert not captured_critical
    assert captured_info

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert "EMBER FLAME" in updated["FIRE_CATEGORY"]

    app.processEvents()


def test_dataset_tab_import_external_zip_with_class_mapping(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    workspace_root = tmp_path / "workspace"
    config_path = tmp_path / "config" / "master_classes.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(class_config.DEFAULT_MASTER_CLASSES, indent=2), encoding="utf-8")

    stream_config = tmp_path / "stream_config.json"
    stream_config.write_text(json.dumps({"active_analytics_category": "fire"}), encoding="utf-8")
    zip_path = _build_zip_dataset(tmp_path)

    captured_info = []
    captured_critical = []

    monkeypatch.setattr(class_config, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(
        "external_dataset_importer.get_data_path",
        lambda relative_path: str(workspace_root / relative_path),
    )
    monkeypatch.setattr(smw.DatasetTab, "_shared_stream_config_path", lambda self: stream_config)

    item_responses = iter(
        [
            ("Local ZIP", True),
            ("Map to existing class", True),
            ("CLASS A", True),
        ]
    )

    monkeypatch.setattr(
        smw.QInputDialog,
        "getItem",
        lambda *args, **kwargs: next(item_responses),
    )
    monkeypatch.setattr(smw.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(zip_path), "ZIP Files (*.zip)"))
    monkeypatch.setattr(smw.QMessageBox, "information", lambda *args, **kwargs: captured_info.append(args[2]) or 0)
    monkeypatch.setattr(smw.QMessageBox, "critical", lambda *args, **kwargs: captured_critical.append(args[2]) or 0)

    tab = smw.DatasetTab()
    tab.import_external_dataset()

    text = tab.dataset_list.toPlainText()
    assert "[EXTERNAL]" in text
    assert "Created classes: 0" in text
    assert not captured_critical
    assert captured_info

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert "EMBER FLAME" not in updated["FIRE_CATEGORY"]

    metadata_files = list((workspace_root / "data" / "fire_analytics" / "imported_datasets").rglob("metadata.json"))
    assert metadata_files
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["class_mapping"]["ember_flame"] == "CLASS A"

    app.processEvents()