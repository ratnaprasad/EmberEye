"""
Training import/export utilities for classes and annotations with merge/override.

Features:
- Export/import classes (hierarchical) with provenance and version.
- Export/import annotations (YOLO + metadata) aggregated into a package.
- Dry-run validation and simple conflict detection with summary report.

This module is designed to be backend-only and callable from UI.
"""

import os
import json
import uuid
import zipfile
import shutil
from datetime import datetime
from typing import Dict, List, Tuple, Any

from embereye.app.master_class_config import load_master_classes, save_master_classes
from embereye.utils.resource_helper import get_data_path
from embereye.app.schema import validate_classes_v2, validate_annotations_v2
from embereye.app.conflict_detection import class_conflicts, annotation_conflicts
from embereye.app.bbox_utils import compute_iou


def _now_iso() -> str:
    return datetime.now().isoformat()


def _guid() -> str:
    return str(uuid.uuid4())


def _class_path(root: str, category: str, leaf: str = None) -> str:
    return f"{root}/{category}" + (f"/{leaf}" if leaf else "")


def _backup_dir() -> str:
    try:
        path = get_data_path("backups")
    except Exception:
        path = os.path.join(os.getcwd(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def _make_backup_file(src_path: str, prefix: str, keep: int = 2) -> str:
    """Copy src_path to backups with timestamp; keep newest `keep` files for this prefix."""
    if not os.path.exists(src_path):
        return ""
    backup_dir = _backup_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"{prefix}_{ts}.json")
    shutil.copy2(src_path, dest)
    # Prune older backups for this prefix
    backups = sorted([f for f in os.listdir(backup_dir) if f.startswith(prefix + "_") and f.endswith(".json")])
    while len(backups) > keep:
        old = backups.pop(0)
        try:
            os.remove(os.path.join(backup_dir, old))
        except Exception:
            pass
    return dest


def _make_backup_zip(src_dir: str, prefix: str, keep: int = 2) -> str:
    """Zip a directory for backup; keep newest `keep` archives for this prefix."""
    if not os.path.isdir(src_dir):
        return ""
    backup_dir = _backup_dir()
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"{prefix}_{ts}.zip")
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for fname in files:
                full = os.path.join(root, fname)
                arc = os.path.relpath(full, src_dir)
                zf.write(full, arcname=arc)
    # Prune older backups for this prefix
    backups = sorted([f for f in os.listdir(backup_dir) if f.startswith(prefix + "_") and f.endswith(".zip")])
    while len(backups) > keep:
        old = backups.pop(0)
        try:
            os.remove(os.path.join(backup_dir, old))
        except Exception:
            pass
    return dest


def _list_backups(prefix: str, ext: str) -> List[str]:
    backup_dir = _backup_dir()
    files = []
    for name in os.listdir(backup_dir):
        if name.startswith(prefix + "_") and name.endswith(ext):
            files.append(os.path.join(backup_dir, name))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def restore_classes_backup(backup_file: str) -> Dict[str, Any]:
    """Restore master_classes.json from a backup file. Creates a safety backup of current file."""
    target = os.path.join(os.getcwd(), "master_classes.json")
    safety = ""
    if os.path.exists(target):
        safety = _make_backup_file(target, "master_classes_restore", keep=3)
    shutil.copy2(backup_file, target)
    return {"status": "ok", "restored": target, "used_backup": backup_file, "safety_backup": safety}


def list_class_backups() -> List[str]:
    return _list_backups("master_classes", ".json")


def list_annotation_backups() -> List[str]:
    return _list_backups("annotations", ".zip")


def restore_annotations_backup(backup_zip: str) -> Dict[str, Any]:
    """Restore annotations tree from a backup ZIP. Existing annotations are backed up then replaced."""
    target_root = get_data_path(os.path.join("training_data", "annotations"))
    os.makedirs(target_root, exist_ok=True)
    safety = _make_backup_zip(target_root, "annotations_restore", keep=3)
    # Remove current tree to avoid mixing
    try:
        shutil.rmtree(target_root)
    except Exception:
        pass
    os.makedirs(target_root, exist_ok=True)
    with zipfile.ZipFile(backup_zip, "r") as zf:
        zf.extractall(target_root)
    return {"status": "ok", "restored": target_root, "used_backup": backup_zip, "safety_backup": safety}


def export_classes(output_file: str, origin: str = "offline") -> Dict[str, Any]:
    """Export current classes to a portable JSON package.

    Schema v1:
    {
      "type": "classes",
      "version": 1,
      "export_id": "uuid",
      "origin": "device/user",
      "timestamp": "iso",
      "root": "IncidentEnvironment",
      "categories": [
        {"name": "FIRE_CATEGORY", "classes": ["flame", ...]},
        ...
      ]
    }
    """
    classes = load_master_classes() or {}
    root = "IncidentEnvironment"
    categories = classes.get(root, []) or []
    payload = {
        "type": "classes",
        "version": 1,
        "export_id": _guid(),
        "origin": origin,
        "timestamp": _now_iso(),
        "root": root,
        "categories": []
    }
    for cat in categories:
        payload["categories"].append({
            "name": cat,
            "classes": classes.get(cat, []) or []
        })
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(payload, f, indent=2)
    return {"status": "ok", "written": output_file, "counts": {
        "categories": len(payload["categories"]),
        "classes": sum(len(c.get("classes", [])) for c in payload["categories"])
    }}


def export_classes_v2(output_file: str, origin: str = "offline") -> Dict[str, Any]:
    """Export classes with stable IDs and tombstone support (v2)."""
    import uuid
    classes = load_master_classes() or {}
    root = "IncidentEnvironment"
    categories = classes.get(root, []) or []
    # Deterministic IDs via UUID5 over names for stability across devices
    def _id(name: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"embereye:{name}"))
    payload = {
        "type": "classes",
        "version": 2,
        "export_id": _guid(),
        "origin": origin,
        "timestamp": _now_iso(),
        "root": root,
        "categories": [],
        "classes": []
    }
    for cat in categories:
        payload["categories"].append({"id": _id(cat), "name": cat, "tombstone": False})
        for leaf in classes.get(cat, []) or []:
            payload["classes"].append({"id": _id(f"{cat}/{leaf}"), "name": leaf, "category_id": _id(cat), "tombstone": False})
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(payload, f, indent=2)
    return {"status": "ok", "written": output_file, "counts": {
        "categories": len(payload["categories"]),
        "classes": len(payload["classes"])
    }}


def _diff_classes(current: Dict[str, List[str]], incoming: Dict[str, List[str]], root: str) -> Dict[str, Any]:
    """Compute differences between current and incoming class maps.
    Returns dict with adds/updates/conflicts.
    """
    report = {"adds": [], "updates": [], "conflicts": []}
    curr_cats = set(current.get(root, []) or [])
    in_cats = set(incoming.get(root, []) or [])

    # Category additions
    for new_cat in sorted(in_cats - curr_cats):
        report["adds"].append({"type": "category", "name": new_cat})

    # For overlapping categories, check leaf classes
    for cat in sorted(curr_cats & in_cats):
        curr_leaves = set(current.get(cat, []) or [])
        in_leaves = set(incoming.get(cat, []) or [])
        for leaf in sorted(in_leaves - curr_leaves):
            report["adds"].append({"type": "class", "category": cat, "name": leaf})
        # Potential conflicts: same leaf present but case/spacing differences
        for leaf in sorted(in_leaves & curr_leaves):
            # No content to update, but record as common for accounting
            report["updates"].append({"type": "class", "category": cat, "name": leaf, "action": "noop"})

    # Incoming categories not in current may also carry leaves
    for cat in sorted(in_cats - curr_cats):
        leaves = incoming.get(cat, []) or []
        for leaf in leaves:
            report["adds"].append({"type": "class", "category": cat, "name": leaf})

    return report


def import_classes(input_file: str, mode: str = "merge", dry_run: bool = True) -> Dict[str, Any]:
    """Import classes from a package.

    mode: "merge" (default) or "override".
    dry_run: when True, only return report without applying.
    """
    with open(input_file, "r") as f:
        payload = json.load(f)
    if payload.get("type") != "classes":
        return {"status": "error", "error": "Invalid package type"}

    root = payload.get("root", "IncidentEnvironment")
    incoming = {root: [c.get("name") for c in payload.get("categories", [])]}
    for cat in payload.get("categories", []):
        incoming[cat.get("name")] = list(cat.get("classes", []) or [])

    current = load_master_classes() or {}
    report = _diff_classes(current, incoming, root)
    report.update({
        "type": "classes",
        "mode": mode,
        "dry_run": dry_run,
        "origin": payload.get("origin"),
        "timestamp": payload.get("timestamp"),
    })

    if dry_run:
        return {"status": "ok", "report": report}

    # Apply according to mode
    backup_path = ""
    if mode == "override":
        # Backup current classes before override (retain last two backups)
        try:
            master_path = os.path.join(os.getcwd(), "master_classes.json")
            backup_path = _make_backup_file(master_path, "master_classes", keep=2)
        except Exception:
            backup_path = ""
        # Replace root categories and their leaves from incoming, but preserve unknown categories
        current[root] = incoming.get(root, [])
        for cat in incoming.get(root, []):
            current[cat] = incoming.get(cat, [])
        save_master_classes(current)
        return {"status": "ok", "applied": "override", "report": report, "backup": backup_path}
    else:
        # merge: add categories/leaves if not present
        if root not in current:
            current[root] = []
        for add in report.get("adds", []):
            if add["type"] == "category":
                if add["name"] not in current[root]:
                    current[root].append(add["name"])
                if add["name"] not in current:
                    current[add["name"]] = []
            elif add["type"] == "class":
                cat = add["category"]
                if cat not in current:
                    current[cat] = []
                if add["name"] not in current[cat]:
                    current[cat].append(add["name"])
        save_master_classes(current)
        return {"status": "ok", "applied": "merge", "report": report, "backup": backup_path}


def import_classes_v2(input_file: str, mode: str = "merge", dry_run: bool = True, resolutions: Dict[str, Any] = None) -> Dict[str, Any]:
    """Import classes v2 with conflict detection and tombstone support.

    - merge: add categories/classes; tombstones mark deletions (no physical delete, report only)
    - override: replace root categories and class lists from incoming
    """
    with open(input_file, "r") as f:
        payload = json.load(f)
    errs = validate_classes_v2(payload)
    if errs:
        return {"status": "error", "error": "; ".join(errs)}
    current = load_master_classes() or {}
    cls_conf = class_conflicts(current, payload)
    report = {"type": "classes", "mode": mode, "dry_run": dry_run, "conflicts": cls_conf}
    if dry_run:
        return {"status": "ok", "report": report}
    backup_path = ""
    root = payload.get("root", "IncidentEnvironment")
    if mode == "override":
        try:
            master_path = os.path.join(os.getcwd(), "master_classes.json")
            backup_path = _make_backup_file(master_path, "master_classes", keep=2)
        except Exception:
            backup_path = ""
        # Build new dict from payload
        new = {root: []}
        for cat in payload.get("categories", []):
            new[root].append(cat["name"])
            new[cat["name"]] = []
        for cl in payload.get("classes", []):
            cat_name = next((c["name"] for c in payload.get("categories", []) if c["id"] == cl["category_id"]), None)
            if cat_name is None:
                continue
            new[cat_name].append(cl["name"])
        save_master_classes(new)
        return {"status": "ok", "applied": "override", "report": report, "backup": backup_path}
    else:
        # merge
        if root not in current:
            current[root] = []
        for cat in payload.get("categories", []):
            if cat.get("tombstone"):
                continue  # don't add deleted categories
            if cat["name"] not in current[root]:
                current[root].append(cat["name"])
            if cat["name"] not in current:
                current[cat["name"]] = []
        for cl in payload.get("classes", []):
            if cl.get("tombstone"):
                continue  # don't add deleted classes
            cat_name = next((c["name"] for c in payload.get("categories", []) if c["id"] == cl["category_id"]), None)
            if cat_name is None:
                continue
            if cl["name"] not in current.get(cat_name, []):
                current[cat_name].append(cl["name"])
        # Apply per-item resolutions for moved and tombstones
        if resolutions:
            # Handle moved class resolutions
            for mv in resolutions.get("classes", {}).get("moved", []):
                if mv.get("resolution") == "incoming":
                    nm = mv.get("name")
                    frm = mv.get("from")
                    to = mv.get("to")
                    try:
                        # Remove from old category if present
                        if frm in current and nm in current.get(frm, []):
                            current[frm] = [c for c in current.get(frm, []) if c != nm]
                        # Ensure destination category exists under root
                        if to not in current[root]:
                            current[root].append(to)
                        if to not in current:
                            current[to] = []
                        if nm not in current[to]:
                            current[to].append(nm)
                    except Exception:
                        pass
            # Handle tombstone resolutions (apply = remove)
            for td in resolutions.get("classes", {}).get("deleted_in_incoming", []):
                if td.get("resolution") == "apply":
                    nm = td.get("name")
                    # Remove leaf from any category
                    for cat in list(current.keys()):
                        if cat == root:
                            continue
                        if nm in current.get(cat, []):
                            current[cat] = [c for c in current.get(cat, []) if c != nm]
        save_master_classes(current)
        return {"status": "ok", "applied": "merge", "report": report, "backup": backup_path}


def _scan_annotations_dir() -> List[str]:
    """Return list of annotation media bases under annotations/ directory."""
    ann_root = get_data_path("annotations")
    if not os.path.exists(ann_root):
        return []
    bases = []
    for name in os.listdir(ann_root):
        full = os.path.join(ann_root, name)
        if os.path.isdir(full):
            bases.append(full)
    return bases


def export_annotations(output_file: str, origin: str = "offline", bases: List[str] = None) -> Dict[str, Any]:
    """Export annotations (YOLO + per-frame metadata) from annotations/ directory.

    Package schema v1:
    {
      "type": "annotations",
      "version": 1,
      "export_id": "uuid",
      "origin": "device/user",
      "timestamp": "iso",
      "items": [
        {
          "media_base": "base",
          "frames": [
            {"image": "frame_00001.jpg", "labels": [[class_name, x,y,w,h], ...]},
            ...
          ],
          "labels_order": [leaf classes used for ids]
        }
      ]
    }
    """
    selected = bases or _scan_annotations_dir()
    package = {
        "type": "annotations",
        "version": 1,
        "export_id": _guid(),
        "origin": origin,
        "timestamp": _now_iso(),
        "items": []
    }
    ann_root = get_data_path("annotations")
    for base_dir in selected:
        media_base = os.path.basename(base_dir)
        frames = []
        labels_order = None
        for fname in sorted(os.listdir(base_dir)):
            fpath = os.path.join(base_dir, fname)
            stem, ext = os.path.splitext(fname)
            if ext.lower() == ".json":
                try:
                    with open(fpath, "r") as mf:
                        meta = json.load(mf)
                        labels_order = labels_order or meta.get("leaf_classes")
                except Exception:
                    pass
            elif ext.lower() in {".jpg", ".png"}:
                # corresponding .txt if any
                txt = os.path.join(base_dir, stem + ".txt")
                labels = []
                if os.path.exists(txt):
                    try:
                        with open(txt, "r") as tf:
                            for line in tf:
                                parts = line.strip().split()
                                if len(parts) == 5:
                                    # class_id mapping to class name via labels_order
                                    cid = 0
                                    try:
                                        cid = int(parts[0])
                                    except Exception:
                                        cid = 0
                                    cls_name = None
                                    if labels_order and 0 <= cid < len(labels_order):
                                        cls_name = labels_order[cid]
                                    labels.append([cls_name, float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])])
                    except Exception:
                        pass
                frames.append({"image": fname, "labels": labels})
        package["items"].append({
            "media_base": media_base,
            "frames": frames,
            "labels_order": labels_order or []
        })
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(package, f, indent=2)
    return {"status": "ok", "written": output_file, "counts": {
        "media": len(package["items"]),
        "frames": sum(len(it["frames"]) for it in package["items"])
    }}


def export_annotations_v2(output_file: str, origin: str = "offline", bases: List[str] = None) -> Dict[str, Any]:
    """Export annotations with richer label metadata (v2)."""
    selected = bases or _scan_annotations_dir()
    package = {
        "type": "annotations",
        "version": 2,
        "export_id": _guid(),
        "origin": origin,
        "timestamp": _now_iso(),
        "items": []
    }
    for base_dir in selected:
        media_base = os.path.basename(base_dir)
        frames = []
        labels_order = None
        for fname in sorted(os.listdir(base_dir)):
            fpath = os.path.join(base_dir, fname)
            stem, ext = os.path.splitext(fname)
            if ext.lower() == ".json":
                try:
                    with open(fpath, "r") as mf:
                        meta = json.load(mf)
                        labels_order = labels_order or meta.get("leaf_classes")
                except Exception:
                    pass
            elif ext.lower() in {".jpg", ".png"}:
                txt = os.path.join(base_dir, stem + ".txt")
                labels = []
                if os.path.exists(txt):
                    try:
                        with open(txt, "r") as tf:
                            for line in tf:
                                parts = line.strip().split()
                                if len(parts) == 5:
                                    cid = int(parts[0])
                                    cls_name = labels_order[cid] if labels_order and 0 <= cid < len(labels_order) else None
                                    labels.append({"class": cls_name, "bbox": [float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])], "created_by": origin, "confidence": 1.0, "updated_at": _now_iso()})
                    except Exception:
                        pass
                frames.append({"image": fname, "labels": labels})
        package["items"].append({"media_base": media_base, "frames": frames, "labels_order": labels_order or []})
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(package, f, indent=2)
    return {"status": "ok", "written": output_file, "counts": {
        "media": len(package["items"]),
        "frames": sum(len(it["frames"]) for it in package["items"])
    }}


def export_annotations_zip(output_zip: str, bases: List[str] = None) -> Dict[str, Any]:
    """Export raw annotations directories (images + .txt + .json) into a ZIP.

    ZIP layout:
      annotations/
        <media_base>/
          *.jpg|*.png, *.txt, *.json
      manifest.json  (small summary of media bases and counts)
    """
    selected = bases or _scan_annotations_dir()
    os.makedirs(os.path.dirname(output_zip) or ".", exist_ok=True)
    counts = {"media": 0, "files": 0}
    manifest = {"type": "annotations-raw-zip", "version": 1, "bases": []}
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base_dir in selected:
            media_base = os.path.basename(base_dir)
            counts["media"] += 1
            base_files = []
            for root, _, files in os.walk(base_dir):
                for fname in files:
                    src = os.path.join(root, fname)
                    rel = os.path.join("annotations", media_base, os.path.relpath(src, base_dir))
                    zf.write(src, arcname=rel)
                    base_files.append(rel)
                    counts["files"] += 1
            manifest["bases"].append({"media_base": media_base, "files": len(base_files)})
        # Write manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return {"status": "ok", "written": output_zip, "counts": counts}





def import_annotations(input_file: str, mode: str = "merge", dry_run: bool = True, iou_threshold: float = 0.85) -> Dict[str, Any]:
    """Import annotations package into training_data/annotations.

    mode: "merge" (dedupe per frame by IoU) or "override" (replace frame labels).
    dry_run: when True, only return report without applying.
    """
    with open(input_file, "r") as f:
        package = json.load(f)
    if package.get("type") != "annotations":
        return {"status": "error", "error": "Invalid package type"}

    target_root = get_data_path(os.path.join("training_data", "annotations"))
    os.makedirs(target_root, exist_ok=True)

    backup_path = ""
    if mode == "override" and not dry_run:
        # Backup existing annotations tree to zip with retention of last two
        backup_path = _make_backup_zip(target_root, "annotations", keep=2)

    summary = {"media": 0, "frames": 0, "conflicts": 0, "replaced": 0, "merged": 0}
    details = []

    for item in package.get("items", []):
        media_base = item.get("media_base")
        labels_order = item.get("labels_order") or []
        dest_dir = os.path.join(target_root, media_base)
        os.makedirs(dest_dir, exist_ok=True)
        summary["media"] += 1

        for frame in item.get("frames", []):
            img_name = frame.get("image")
            labels = frame.get("labels") or []
            summary["frames"] += 1
            txt_path = os.path.join(dest_dir, os.path.splitext(img_name)[0] + ".txt")
            existing = []
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r") as tf:
                        for line in tf:
                            parts = line.strip().split()
                            if len(parts) == 5:
                                cid = int(parts[0])
                                existing.append([cid, float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])])
                except Exception:
                    pass

            if mode == "override":
                summary["replaced"] += 1
                action = "override"
                merged_labels = labels
            else:
                # merge with IoU dedupe against existing
                action = "merge"
                merged_labels = []
                # Convert incoming classes to IDs using labels_order; if missing, keep None
                for cls_name, x, y, w, h in labels:
                    cid = labels_order.index(cls_name) if cls_name in labels_order else 0
                    # Check for duplicate against existing by IoU
                    dup = False
                    for ecid, ex, ey, ew, eh in existing:
                        if compute_iou((x, y, w, h), (ex, ey, ew, eh)) >= iou_threshold and (ecid == cid):
                            dup = True
                            break
                    if not dup:
                        merged_labels.append([cls_name, x, y, w, h])
                summary["merged"] += 1
                if merged_labels and existing:
                    # If many overlaps, mark as conflict for reporting
                    summary["conflicts"] += 1

            details.append({
                "media_base": media_base,
                "image": img_name,
                "action": action,
                "existing_count": len(existing),
                "incoming_count": len(labels),
                "result_count": len(merged_labels)
            })

            if not dry_run:
                # Write labels.txt lines in YOLO format using labels_order
                with open(txt_path, "w") as tf:
                    for cls_name, x, y, w, h in merged_labels:
                        cid = labels_order.index(cls_name) if cls_name in labels_order else 0
                        tf.write(f"{cid} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")

    return {"status": "ok", "report": {"summary": summary, "details": details}, "backup": backup_path}


def import_annotations_v2(input_file: str, mode: str = "merge", dry_run: bool = True, iou_threshold: float = 0.85, resolutions: Dict[str, Any] = None) -> Dict[str, Any]:
    with open(input_file, "r") as f:
        package = json.load(f)
    errs = validate_annotations_v2(package)
    if errs:
        return {"status": "error", "error": "; ".join(errs)}
    target_root = get_data_path(os.path.join("training_data", "annotations"))
    os.makedirs(target_root, exist_ok=True)
    conf = annotation_conflicts(target_root, package, iou_threshold=iou_threshold)
    report = {"type": "annotations", "mode": mode, "dry_run": dry_run, "conflicts": conf}
    if dry_run:
        return {"status": "ok", "report": report}
    # Apply using existing merge/override policy, reading labels as v2 structure
    summary = {"media": 0, "frames": 0, "conflicts": 0, "replaced": 0, "merged": 0}
    details = []
    backup_path = ""
    if mode == "override":
        backup_path = _make_backup_zip(target_root, "annotations", keep=2)
    # Build resolution lookup sets for quick checks
    dup_incoming_keys = set()
    dis_incoming_keys = set()
    if resolutions:
        for rec in resolutions.get("annotations", {}).get("duplicates", []):
            if rec.get("resolution") == "incoming":
                k = (rec.get("media_base"), rec.get("image"), rec.get("class"), tuple(rec.get("bbox", [0, 0, 0, 0])))
                dup_incoming_keys.add(k)
        for rec in resolutions.get("annotations", {}).get("disagreements", []):
            if rec.get("resolution") == "incoming":
                k = (rec.get("media_base"), rec.get("image"), rec.get("incoming_class"), tuple(rec.get("bbox", [0, 0, 0, 0])))
                dis_incoming_keys.add(k)

    for item in package.get("items", []):
        media_base = item.get("media_base")
        labels_order = item.get("labels_order") or []
        dest_dir = os.path.join(target_root, media_base)
        os.makedirs(dest_dir, exist_ok=True)
        summary["media"] += 1
        for frame in item.get("frames", []):
            img_name = frame.get("image")
            labels = frame.get("labels") or []
            summary["frames"] += 1
            txt_path = os.path.join(dest_dir, os.path.splitext(img_name)[0] + ".txt")
            existing = []
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r") as tf:
                        for line in tf:
                            parts = line.strip().split()
                            if len(parts) == 5:
                                cid = int(parts[0])
                                existing.append([cid, float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])])
                except Exception:
                    pass
            if mode == "override":
                summary["replaced"] += 1
                action = "override"
                merged_labels = labels
            else:
                action = "merge"
                merged_labels = []
                for lab in labels:
                    cls_name = lab.get("class")
                    x, y, w, h = lab.get("bbox", [0, 0, 0, 0])
                    # Check explicit incoming resolution overrides
                    key = (media_base, img_name, cls_name, (x, y, w, h))
                    if key in dup_incoming_keys or key in dis_incoming_keys:
                        # Force include incoming regardless of IoU duplicate detection
                        merged_labels.append({"class": cls_name, "bbox": [x, y, w, h]})
                        continue
                    cid = labels_order.index(cls_name) if cls_name in labels_order else 0
                    dup = False
                    for ecid, ex, ey, ew, eh in existing:
                        if compute_iou((x, y, w, h), (ex, ey, ew, eh)) >= iou_threshold and (ecid == cid):
                            dup = True
                            break
                    if not dup:
                        merged_labels.append({"class": cls_name, "bbox": [x, y, w, h]})
                summary["merged"] += 1
                if merged_labels and existing:
                    summary["conflicts"] += 1
            details.append({"media_base": media_base, "image": img_name, "action": action, "existing_count": len(existing), "incoming_count": len(labels), "result_count": len(merged_labels)})
            if not dry_run:
                with open(txt_path, "w") as tf:
                    for lab in merged_labels:
                        cls_name = lab.get("class")
                        x, y, w, h = lab.get("bbox")
                        cid = labels_order.index(cls_name) if cls_name in labels_order else 0
                        tf.write(f"{cid} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
    return {"status": "ok", "report": {"summary": summary, "details": details}, "backup": backup_path}


def import_annotations_zip(input_zip: str) -> Dict[str, Any]:
    """Import raw annotations ZIP by extracting into annotations/ for QC review.

    No merge logic is applied; it copies frames + txt + json as-is. Use this when the
    export was created via export_annotations_zip. After QC review, use 'Move to Training'
    to copy the approved annotations to training_data/annotations/.
    """
    target_root = get_data_path("annotations")
    os.makedirs(target_root, exist_ok=True)
    extracted = 0
    bases = 0
    with zipfile.ZipFile(input_zip, "r") as zf:
        # Extract per media base under annotations/
        for name in zf.namelist():
            if name.startswith("annotations/") and not name.endswith("/"):
                # annotations/<media_base>/...
                rel_path = name.split("annotations/", 1)[1]
                # Destination under annotations/ (for QC review)
                dest = os.path.join(target_root, rel_path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted += 1
        # Count bases from manifest if present
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            bases = len(manifest.get("bases", []))
        except Exception:
            pass
    return {"status": "ok", "extracted": extracted, "media": bases, "dest": target_root}
