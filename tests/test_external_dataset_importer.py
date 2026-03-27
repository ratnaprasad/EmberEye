import json
import sys
import zipfile
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDIO_ROOT = PROJECT_ROOT / "embereye-studio"
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from external_dataset_importer import import_external_dataset
from embereye.core import class_config


def _write_image(path: Path, size=(100, 100)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 0, 0)).save(path)


def _configure_temp_workspace(monkeypatch, tmp_path):
    workspace_root = tmp_path / "workspace"
    config_path = tmp_path / "config" / "master_classes.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(class_config.DEFAULT_MASTER_CLASSES, indent=2), encoding="utf-8")

    monkeypatch.setattr(class_config, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(
        "external_dataset_importer.get_data_path",
        lambda relative_path: str(workspace_root / relative_path),
    )
    return workspace_root, config_path


def _make_yolo_dataset(root: Path, class_names, label_lines):
    image_path = root / "images" / "train" / "sample.jpg"
    label_path = root / "labels" / "train" / "sample.txt"
    _write_image(image_path)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text("\n".join(label_lines) + "\n", encoding="utf-8")
    (root / "data.yaml").write_text(
        "names: [" + ", ".join(class_names) + "]\n",
        encoding="utf-8",
    )
    return image_path, label_path


def _make_coco_dataset(root: Path):
    image_path = root / "images" / "coco1.jpg"
    _write_image(image_path)
    payload = {
        "images": [{"id": 1, "file_name": "coco1.jpg", "width": 100, "height": 100}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 20, 30, 40]}],
        "categories": [{"id": 1, "name": "CLASS A"}],
    }
    (root / "annotations.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_voc_dataset(root: Path):
    image_path = root / "voc1.jpg"
    _write_image(image_path)
    (root / "voc1.xml").write_text(
        "<annotation>"
        "<filename>voc1.jpg</filename>"
        "<size><width>100</width><height>100</height></size>"
        "<object><name>CLASS A</name><bndbox>"
        "<xmin>5</xmin><ymin>5</ymin><xmax>55</xmax><ymax>60</ymax>"
        "</bndbox></object>"
        "</annotation>",
        encoding="utf-8",
    )


def _assert_summary_outputs(summary, workspace_root: Path):
    assert summary.images == 1
    assert summary.annotations == 1

    qc_root = Path(summary.qc_pending_storage)
    ds_root = Path(summary.domain_storage)

    assert qc_root.exists()
    assert ds_root.exists()
    assert (qc_root / "sample.txt").exists() or (qc_root / "coco1.txt").exists() or (qc_root / "voc1.txt").exists()
    assert (qc_root / "metadata.json").exists()
    assert (ds_root / "metadata.json").exists()
    assert str(workspace_root / "annotations") in str(qc_root)
    assert str(workspace_root / "data" / "fire_analytics" / "imported_datasets") in str(ds_root)


def test_import_external_dataset_supports_yolo_coco_and_voc(tmp_path, monkeypatch):
    workspace_root, _ = _configure_temp_workspace(monkeypatch, tmp_path)

    datasets = []

    yolo_root = tmp_path / "datasets" / "yolo"
    _make_yolo_dataset(yolo_root, ["CLASS A"], ["0 0.5 0.5 0.2 0.2"])
    datasets.append(("yolo", yolo_root))

    coco_root = tmp_path / "datasets" / "coco"
    coco_root.mkdir(parents=True, exist_ok=True)
    _make_coco_dataset(coco_root)
    datasets.append(("coco", coco_root))

    voc_root = tmp_path / "datasets" / "voc"
    voc_root.mkdir(parents=True, exist_ok=True)
    _make_voc_dataset(voc_root)
    datasets.append(("voc", voc_root))

    for expected_format, dataset_root in datasets:
        summary = import_external_dataset(dataset_root, active_domain="fire")
        assert summary.source_format == expected_format
        _assert_summary_outputs(summary, workspace_root)


def test_import_external_dataset_supports_local_zip(tmp_path, monkeypatch):
    _configure_temp_workspace(monkeypatch, tmp_path)

    dataset_root = tmp_path / "zip_dataset"
    _make_yolo_dataset(dataset_root, ["CLASS A"], ["0 0.5 0.5 0.2 0.2"])
    zip_path = tmp_path / "dataset.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for source in dataset_root.rglob("*"):
            if source.is_file():
                archive.write(source, source.relative_to(dataset_root))

    summary = import_external_dataset(zip_path, active_domain="fire")

    assert summary.source_format == "yolo"
    assert summary.images == 1
    assert summary.annotations == 1


def test_import_external_dataset_resolver_can_create_and_skip_classes(tmp_path, monkeypatch):
    _, config_path = _configure_temp_workspace(monkeypatch, tmp_path)

    dataset_root = tmp_path / "resolver_dataset"
    _make_yolo_dataset(
        dataset_root,
        ["ember_flame", "ignore_me"],
        [
            "0 0.5 0.5 0.2 0.2",
            "1 0.4 0.4 0.1 0.1",
        ],
    )

    def resolver(label, _existing_classes, _target_category):
        if label == "ember_flame":
            return "create", "EMBER FLAME"
        return "skip", None

    summary = import_external_dataset(dataset_root, active_domain="fire", resolver=resolver)

    assert summary.created_classes == ["EMBER FLAME"]
    assert summary.skipped_classes == ["ignore_me"]
    assert summary.annotations == 1

    saved_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert "EMBER FLAME" in saved_config["FIRE_CATEGORY"]

    metadata = json.loads((Path(summary.domain_storage) / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["class_mapping"]["ember_flame"] == "EMBER FLAME"
    assert "ignore_me" not in metadata["class_mapping"]