"""
External dataset import helpers for EmberEye Studio.

Phase-1 scope:
- Local folder/ZIP imports (YOLO, COCO, Pascal VOC; detection only)
- Optional Kaggle/Roboflow download helpers
- Class mapping + taxonomy updates via master_classes.json
- Writes imported datasets to analytics-domain storage and QC pending annotations
"""

from __future__ import annotations

import json
import importlib
import os
import shutil
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

from PIL import Image

from embereye.core.class_config import (
    ANALYTICS_CATEGORY_KEYS,
    flatten_classes,
    get_leaf_classes_for_category,
    load_master_classes,
    save_master_classes,
)
from embereye.utils.resource_helper import get_data_path

try:
    import yaml
except Exception:
    yaml = None


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


@dataclass
class AnnotationNorm:
    class_name: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class ImageSample:
    image_path: Path
    annotations: List[AnnotationNorm]


@dataclass
class ParsedDataset:
    source_format: str
    class_names: List[str]
    samples: List[ImageSample]


@dataclass
class ImportSummary:
    dataset_id: str
    domain: str
    source_format: str
    images: int
    annotations: int
    created_classes: List[str]
    skipped_classes: List[str]
    domain_storage: str
    qc_pending_storage: str


ResolverFn = Callable[[str, List[str], str], Tuple[str, Optional[str]]]


def _timestamp_id(prefix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in prefix).strip("_")
    return f"{ts}_{safe or 'dataset'}"


def _domain_target_category(active_domain: str, classes_dict: Dict[str, List[str]]) -> str:
    domain = str(active_domain or "").strip().lower()
    preferred = {
        "fire": "FIRE_CATEGORY",
        "ppe": "PPE_CATEGORY",
    }
    target = preferred.get(domain)
    if not target:
        keys = ANALYTICS_CATEGORY_KEYS.get(domain) or []
        target = keys[0] if keys else "FIRE_CATEGORY"

    if target not in classes_dict:
        classes_dict[target] = []
    root = classes_dict.setdefault("IncidentEnvironment", [])
    if target not in root:
        root.append(target)
    return target


def _read_stream_active_domain() -> str:
    cfg = Path(__file__).resolve().parent.parent / "stream_config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        value = str(data.get("active_analytics_category", "fire")).strip().lower()
        return value or "fire"
    except Exception:
        return "fire"


def _extract_if_zip(path: Path) -> Tuple[Path, Optional[str]]:
    if path.is_file() and path.suffix.lower() == ".zip":
        td = tempfile.mkdtemp(prefix="embereye_ext_import_")
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(td)
        return Path(td), td
    return path, None


def _find_matching_image(label_file: Path) -> Optional[Path]:
    stem = label_file.stem

    # Common YOLO split layout: .../labels/<split>/x.txt -> .../images/<split>/x.jpg
    # Build candidate names from `stem` directly instead of `with_suffix(...)` so
    # Roboflow names containing extra dots (e.g. *.rf.<hash>.txt) are preserved.
    parts = list(label_file.parts)
    if "labels" in parts:
        idx = parts.index("labels")
        images_dir = Path(*parts[:idx], "images", *parts[idx + 1 : -1])
        for ext in IMAGE_EXTS:
            p = images_dir / f"{stem}{ext}"
            if p.exists():
                return p

    for ext in IMAGE_EXTS:
        p = label_file.parent / f"{stem}{ext}"
        if p.exists():
            return p

    root = label_file.parent
    for ext in IMAGE_EXTS:
        found = list(root.rglob(stem + ext))
        if found:
            return found[0]

    return None


def _parse_yolo(root: Path) -> ParsedDataset:
    label_files = [p for p in root.rglob("*.txt") if p.name.lower() != "labels.txt"]
    names_map: Dict[int, str] = {}

    data_yaml = None
    for candidate in [root / "data.yaml", root / "dataset.yaml"]:
        if candidate.exists():
            data_yaml = candidate
            break
    if data_yaml is None:
        for candidate in root.rglob("*.yaml"):
            if candidate.name in ("data.yaml", "dataset.yaml"):
                data_yaml = candidate
                break

    if data_yaml and yaml is not None:
        try:
            y = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
            names = y.get("names", {})
            if isinstance(names, list):
                names_map = {i: str(v) for i, v in enumerate(names)}
            elif isinstance(names, dict):
                names_map = {int(k): str(v) for k, v in names.items()}
        except Exception:
            names_map = {}

    samples: List[ImageSample] = []
    classes: set[str] = set()

    for lbl in label_files:
        image = _find_matching_image(lbl)
        if image is None:
            continue
        anns: List[AnnotationNorm] = []
        try:
            for line in lbl.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                cid = int(float(parts[0]))
                x, y, w, h = map(float, parts[1:5])
                cname = names_map.get(cid, f"class_{cid}")
                anns.append(AnnotationNorm(cname, x, y, w, h))
                classes.add(cname)
        except Exception:
            continue
        if anns:
            samples.append(ImageSample(image, anns))

    return ParsedDataset("yolo", sorted(classes), samples)


def _find_coco_json(root: Path) -> Optional[Path]:
    for p in root.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "images" in data and "annotations" in data and "categories" in data:
                return p
        except Exception:
            continue
    return None


def _normalize_bbox_abs(x: float, y: float, w: float, h: float, iw: int, ih: int) -> Tuple[float, float, float, float]:
    x1 = max(0.0, x)
    y1 = max(0.0, y)
    x2 = min(float(iw), x + w)
    y2 = min(float(ih), y + h)
    bw = max(0.0, x2 - x1)
    bh = max(0.0, y2 - y1)
    cx = x1 + bw / 2.0
    cy = y1 + bh / 2.0
    if iw <= 0 or ih <= 0:
        return 0.0, 0.0, 0.0, 0.0
    return cx / iw, cy / ih, bw / iw, bh / ih


def _parse_coco(root: Path) -> ParsedDataset:
    coco_json = _find_coco_json(root)
    if coco_json is None:
        raise ValueError("COCO annotations JSON not found")

    data = json.loads(coco_json.read_text(encoding="utf-8"))
    cat_map = {int(c["id"]): str(c["name"]) for c in data.get("categories", []) if "id" in c and "name" in c}

    image_by_id = {}
    for img in data.get("images", []):
        iid = int(img.get("id", -1))
        if iid < 0:
            continue
        image_by_id[iid] = {
            "file_name": str(img.get("file_name", "")),
            "width": int(img.get("width", 0) or 0),
            "height": int(img.get("height", 0) or 0),
        }

    anns_by_image: Dict[int, List[dict]] = defaultdict(list)
    for ann in data.get("annotations", []):
        iid = int(ann.get("image_id", -1))
        if iid < 0:
            continue
        if "bbox" not in ann:
            continue
        anns_by_image[iid].append(ann)

    # Build lookup by basename to survive nested file_name values
    all_images = [p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS]
    by_name = {p.name: p for p in all_images}

    samples: List[ImageSample] = []
    classes: set[str] = set()

    for iid, meta in image_by_id.items():
        fname = Path(meta["file_name"]).name
        image_path = by_name.get(fname)
        if image_path is None:
            candidate = root / meta["file_name"]
            if candidate.exists():
                image_path = candidate
        if image_path is None:
            continue

        iw = meta["width"]
        ih = meta["height"]
        if iw <= 0 or ih <= 0:
            try:
                with Image.open(image_path) as im:
                    iw, ih = im.size
            except Exception:
                continue

        anns: List[AnnotationNorm] = []
        for ann in anns_by_image.get(iid, []):
            cid = int(ann.get("category_id", -1))
            cname = cat_map.get(cid, f"class_{cid}")
            bbox = ann.get("bbox") or [0, 0, 0, 0]
            x, y, w, h = [float(v) for v in bbox[:4]]
            nx, ny, nw, nh = _normalize_bbox_abs(x, y, w, h, iw, ih)
            anns.append(AnnotationNorm(cname, nx, ny, nw, nh))
            classes.add(cname)

        if anns:
            samples.append(ImageSample(image_path, anns))

    return ParsedDataset("coco", sorted(classes), samples)


def _parse_voc(root: Path) -> ParsedDataset:
    xml_files = list(root.rglob("*.xml"))
    samples: List[ImageSample] = []
    classes: set[str] = set()

    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root_el = tree.getroot()
            fname = (root_el.findtext("filename") or "").strip()
            if not fname:
                continue
            image_path = None
            candidate = xml_file.parent / fname
            if candidate.exists():
                image_path = candidate
            else:
                matches = list(root.rglob(Path(fname).name))
                if matches:
                    image_path = matches[0]
            if image_path is None:
                continue

            size = root_el.find("size")
            iw = int(size.findtext("width", default="0")) if size is not None else 0
            ih = int(size.findtext("height", default="0")) if size is not None else 0
            if iw <= 0 or ih <= 0:
                with Image.open(image_path) as im:
                    iw, ih = im.size

            anns: List[AnnotationNorm] = []
            for obj in root_el.findall("object"):
                cname = (obj.findtext("name") or "").strip()
                box = obj.find("bndbox")
                if not cname or box is None:
                    continue
                xmin = float(box.findtext("xmin", default="0"))
                ymin = float(box.findtext("ymin", default="0"))
                xmax = float(box.findtext("xmax", default="0"))
                ymax = float(box.findtext("ymax", default="0"))
                nx, ny, nw, nh = _normalize_bbox_abs(xmin, ymin, xmax - xmin, ymax - ymin, iw, ih)
                anns.append(AnnotationNorm(cname, nx, ny, nw, nh))
                classes.add(cname)

            if anns:
                samples.append(ImageSample(image_path, anns))
        except Exception:
            continue

    return ParsedDataset("voc", sorted(classes), samples)


def detect_format(path: Path) -> str:
    if _find_coco_json(path) is not None:
        return "coco"
    if list(path.rglob("*.xml")):
        return "voc"
    if list(path.rglob("*.txt")):
        return "yolo"
    raise ValueError("Could not detect dataset format (supported: YOLO, COCO, Pascal VOC)")


def parse_dataset(path: Path, forced_format: Optional[str] = None) -> ParsedDataset:
    fmt = (forced_format or detect_format(path)).strip().lower()
    if fmt == "yolo":
        return _parse_yolo(path)
    if fmt == "coco":
        return _parse_coco(path)
    if fmt in ("voc", "pascal", "pascal_voc"):
        return _parse_voc(path)
    raise ValueError(f"Unsupported format: {fmt}")


def download_kaggle(dataset_id: str) -> Path:
    try:
        kaggle = importlib.import_module("kaggle")
    except Exception as exc:
        raise RuntimeError(
            "Kaggle package is not installed. Install with: pip install kaggle"
        ) from exc

    td = Path(tempfile.mkdtemp(prefix="embereye_kaggle_"))
    kaggle.api.dataset_download_files(dataset_id, path=str(td), unzip=True)
    return td


def download_roboflow(api_key: str, workspace: str, project: str, version: str, export_format: str = "yolov8") -> Path:
    try:
        roboflow_mod = importlib.import_module("roboflow")
        roboflow_cls = roboflow_mod.Roboflow
    except Exception as exc:
        raise RuntimeError(
            "Roboflow package is not installed. Install with: pip install roboflow"
        ) from exc

    td = Path(tempfile.mkdtemp(prefix="embereye_roboflow_"))
    rf = roboflow_cls(api_key=api_key)
    proj = rf.workspace(workspace).project(project)
    proj.version(int(version)).download(export_format, location=str(td))
    return td


def import_external_dataset(
    source_path: Path,
    active_domain: Optional[str] = None,
    forced_format: Optional[str] = None,
    resolver: Optional[ResolverFn] = None,
) -> ImportSummary:
    """Import external dataset into analytics-domain storage + QC pending queue."""
    active_domain = (active_domain or _read_stream_active_domain()).strip().lower() or "fire"

    source_path = Path(source_path)
    normalized_source, temp_dir = _extract_if_zip(source_path)

    try:
        parsed = parse_dataset(normalized_source, forced_format)
        if not parsed.samples:
            raise ValueError("No labeled samples found in dataset")

        classes_dict = load_master_classes()
        target_category = _domain_target_category(active_domain, classes_dict)

        current_leaf = get_leaf_classes_for_category(active_domain, classes_dict)
        if not current_leaf:
            current_leaf = flatten_classes(classes_dict)
        case_map = {c.lower(): c for c in current_leaf}
        class_mapping: Dict[str, str] = {}
        created_classes: List[str] = []
        skipped_classes: List[str] = []

        # Resolve class names
        for ext_name in parsed.class_names:
            hit = case_map.get(ext_name.lower())
            if hit:
                class_mapping[ext_name] = hit
                continue

            action = "create"
            value = ext_name
            if resolver is not None:
                action, value = resolver(ext_name, list(current_leaf), target_category)

            if action == "skip":
                skipped_classes.append(ext_name)
                continue
            if action == "map" and value:
                class_mapping[ext_name] = value
                continue

            new_name = (value or ext_name).strip()
            if new_name not in classes_dict[target_category]:
                classes_dict[target_category].append(new_name)
                created_classes.append(new_name)
            class_mapping[ext_name] = new_name

        if created_classes:
            ok = save_master_classes(classes_dict)
            if not ok:
                raise RuntimeError("Failed to save taxonomy updates to master_classes.json")

        # Use latest class order for class ids
        final_classes = get_leaf_classes_for_category(active_domain, load_master_classes())
        if not final_classes:
            final_classes = flatten_classes(load_master_classes())
        class_to_id = {name: idx for idx, name in enumerate(final_classes)}

        dataset_id = _timestamp_id(source_path.stem)
        domain_root = Path(get_data_path(os.path.join("data", f"{active_domain}_analytics", "imported_datasets")))
        qc_root = Path(get_data_path(os.path.join("annotations", dataset_id)))
        ds_root = domain_root / dataset_id

        (ds_root / "images").mkdir(parents=True, exist_ok=True)
        (ds_root / "annotations").mkdir(parents=True, exist_ok=True)
        qc_root.mkdir(parents=True, exist_ok=True)

        labels_payload = "\n".join(final_classes) + "\n"
        (ds_root / "annotations" / "labels.txt").write_text(labels_payload, encoding="utf-8")
        (qc_root / "labels.txt").write_text(labels_payload, encoding="utf-8")

        used_names = set()
        ann_count = 0

        for idx, sample in enumerate(parsed.samples):
            base_name = sample.image_path.name
            if base_name in used_names:
                base_name = f"{idx:06d}_{base_name}"
            used_names.add(base_name)

            ds_img = ds_root / "images" / base_name
            ds_lbl = ds_root / "annotations" / f"{Path(base_name).stem}.txt"
            qc_img = qc_root / base_name
            qc_lbl = qc_root / f"{Path(base_name).stem}.txt"

            shutil.copy2(sample.image_path, ds_img)
            shutil.copy2(sample.image_path, qc_img)

            lines = []
            for ann in sample.annotations:
                mapped = class_mapping.get(ann.class_name)
                if not mapped:
                    continue
                cid = class_to_id.get(mapped)
                if cid is None:
                    continue
                lines.append(f"{cid} {ann.x:.6f} {ann.y:.6f} {ann.w:.6f} {ann.h:.6f}\n")

            if not lines:
                continue

            ds_lbl.write_text("".join(lines), encoding="utf-8")
            qc_lbl.write_text("".join(lines), encoding="utf-8")
            ann_count += len(lines)

        meta = {
            "source": str(source_path),
            "source_format": parsed.source_format,
            "active_domain": active_domain,
            "target_category": target_category,
            "class_mapping": class_mapping,
            "created_classes": created_classes,
            "skipped_classes": skipped_classes,
            "qc_status": "pending",
            "imported_at": datetime.now().isoformat(),
        }
        (ds_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (qc_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return ImportSummary(
            dataset_id=dataset_id,
            domain=active_domain,
            source_format=parsed.source_format,
            images=len(parsed.samples),
            annotations=ann_count,
            created_classes=created_classes,
            skipped_classes=skipped_classes,
            domain_storage=str(ds_root),
            qc_pending_storage=str(qc_root),
        )
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
