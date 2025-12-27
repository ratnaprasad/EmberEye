"""
Conflict detection for classes and annotations.
"""

import os
import json
from typing import Dict, Any, List, Tuple

from embereye.app.bbox_utils import compute_iou


def class_conflicts(current: Dict[str, List[str]], incoming_v2: Dict[str, Any]) -> Dict[str, Any]:
    """Detect class conflicts: different category for same leaf name, tombstones vs existing, duplicates."""
    report = {"moved": [], "deleted_in_incoming": [], "duplicates": []}
    root = incoming_v2.get("root", "IncidentEnvironment")
    categories = {c["id"]: c["name"] for c in incoming_v2.get("categories", [])}
    by_name_cat = {(cl["name"], cl["category_id"]): cl for cl in incoming_v2.get("classes", [])}
    # Current mapping name -> category
    curr_cats = set(current.get(root, []) or [])
    curr_map = {}
    for cat in curr_cats:
        for leaf in current.get(cat, []) or []:
            curr_map[leaf] = cat

    seen_names = {}
    for cl in incoming_v2.get("classes", []):
        nm = cl["name"]
        seen_names.setdefault(nm, 0)
        seen_names[nm] += 1
        if nm in curr_map and categories.get(cl["category_id"]) != curr_map[nm]:
            report["moved"].append({
                "name": nm,
                "from": curr_map[nm],
                "to": categories.get(cl["category_id"])})
        if cl.get("tombstone"):
            report["deleted_in_incoming"].append({"name": nm})
    report["duplicates"] = [nm for nm, cnt in seen_names.items() if cnt > 1]
    return report


def annotation_conflicts(existing_dir: str, incoming_pkg: Dict[str, Any], iou_threshold: float = 0.85) -> Dict[str, Any]:
    """Detect annotation duplicates and label disagreements per frame.
    - duplicates: incoming box overlaps existing with IoU>=threshold and same class
    - disagreements: incoming overlaps existing IoU>=threshold but class differs

    Returns entries that include bbox to support per-item resolution.
    """
    duplicates = []
    disagreements = []
    for item in incoming_pkg.get("items", []):
        media_base = item.get("media_base")
        labels_order = item.get("labels_order") or []
        dest_dir = os.path.join(existing_dir, media_base)
        for frame in item.get("frames", []):
            img_name = frame.get("image")
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
            for lab in frame.get("labels", []):
                # lab may be v1 (tuple) or v2 (dict)
                if isinstance(lab, list) and len(lab) == 5:
                    cls_name, x, y, w, h = lab
                else:
                    cls_name = lab.get("class")
                    x, y, w, h = lab.get("bbox", [0, 0, 0, 0])
                cid = labels_order.index(cls_name) if cls_name in labels_order else 0
                for ecid, ex, ey, ew, eh in existing:
                    iou = compute_iou((x, y, w, h), (ex, ey, ew, eh))
                    if iou >= iou_threshold:
                        if ecid == cid:
                            duplicates.append({
                                "media_base": media_base,
                                "image": img_name,
                                "class": cls_name,
                                "bbox": [x, y, w, h],
                                "iou": iou
                            })
                        else:
                            disagreements.append({
                                "media_base": media_base,
                                "image": img_name,
                                "incoming_class": cls_name,
                                "bbox": [x, y, w, h],
                                "existing_cid": ecid,
                                "iou": iou
                            })
    return {"duplicates": duplicates, "disagreements": disagreements}
