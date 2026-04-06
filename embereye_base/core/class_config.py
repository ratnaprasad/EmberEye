"""
Central class configuration for EmberEye.
Provides a single source of truth for class taxonomy and helpers.
"""

import json
import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "master_classes.json"


def _candidate_config_paths() -> List[Path]:
    """Return candidate config locations in priority order."""
    candidates: List[Path] = []

    env_override = os.environ.get("EMBEREYE_MASTER_CLASSES_PATH", "").strip()
    if env_override:
        candidates.append(Path(env_override))

    # Runtime-writable location for packaged deployments.
    candidates.append(Path.home() / ".embereye" / "master_classes.json")

    # Source-tree packaged module location.
    candidates.append(_CONFIG_PATH)

    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        candidates.append(exe_parent / "_internal" / "master_classes.json")
        candidates.append(exe_parent / "master_classes.json")
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            meipass_path = Path(meipass)
            candidates.append(meipass_path / "master_classes.json")
            candidates.append(meipass_path / "_internal" / "master_classes.json")

    unique: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _get_existing_config_path() -> Optional[Path]:
    for path in _candidate_config_paths():
        if path.exists():
            return path
    return None


def _get_writable_config_path() -> Path:
    for path in _candidate_config_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            continue
    return _CONFIG_PATH

DEFAULT_MASTER_CLASSES: Dict[str, List[str]] = {
    "IncidentEnvironment": [
        "FIRE_CATEGORY",
        "SMOKE_CATEGORY",
        "STRUCTURAL_CATEGORY",
        "HUMAN_CATEGORY",
        "VEHICLE_CATEGORY",
        "SAFETY_CATEGORY",
        "ENVIRONMENT_MARKERS",
        "SMOKE_SENSITIVITY",
        "FIRE_SENSITIVITY",
    ],
    "FIRE_CATEGORY": ["CLASS A", "CLASS B", "CLASS C", "CLASS D", "CLASS K"],
    "SMOKE_CATEGORY": ["WHITE SMOKE", "BLACK SMOKE", "BLUE SMOKE", "YELLOW/BROWN SMOKE"],
    "STRUCTURAL_CATEGORY": [
        "DAMAGED EQUIPMENT",
        "HIGH_PRESSURE_EQUIPMENT",
        "FUEL CONTAINER",
        "ROTARY MACHINES",
        "ELECTRICAL SWITCHGEAR",
    ],
    "HUMAN_CATEGORY": [
        "PERSON WITHOUT SAFETY WEAR",
        "PERSON WITH PPE",
        "PERSON IN DISTRESS",
        "RESCUE TEAM",
        "FIRE SENTRY",
    ],
    "VEHICLE_CATEGORY": ["COMMERCIAL VEHICLE", "SHIP", "AIRCRAFT", "INDUSTRIAL VEHICLE"],
    "SAFETY_CATEGORY": [
        "FIRE EXTINGUISHER",
        "SAFETY ALARM",
        "SPRINKLER",
        "EMERGENCY EXIT",
        "EMERGENCY LIGHT",
    ],
    "ENVIRONMENT_MARKERS": ["INDOOR", "OUTDOOR", "RESTRICTED AREA", "WEARHOUSE", "PATHWAY"],
    "SMOKE_SENSITIVITY": ["STEAM", "HARMFUL GASES", "FUMES", "SMOKE WITH FIRE"],
    "FIRE_SENSITIVITY": ["EXPLOSIVES", "WELDING ARC", "CUTTING SPARKS", "FIRE TORCH"],
}


def _safe_read_json(path: Path) -> Dict[str, List[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def load_master_classes() -> Dict[str, List[str]]:
    """
    Load master class configuration from the central JSON file.
    Returns hierarchical dict of classes and their subclasses.
    """
    cfg_path = _get_existing_config_path()
    if cfg_path is not None:
        data = _safe_read_json(cfg_path)
        if data:
            return data
    return DEFAULT_MASTER_CLASSES


def save_master_classes(classes_dict: Dict[str, List[str]]) -> bool:
    """Save master class configuration to the central JSON file."""
    try:
        target_path = _get_writable_config_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", encoding="utf-8") as handle:
            json.dump(classes_dict, handle, indent=2)
        return True
    except Exception as exc:
        print(f"[MASTER_CLASS] Error saving config: {exc}")
        return False


def flatten_classes(classes_dict: Dict[str, List[str]]) -> List[str]:
    """
    Convert hierarchical class dict to flat list of only the leaf classes.
    Skips the root 'IncidentEnvironment' key and only includes the actual class names.
    This must match the model's training class order exactly.
    """
    flat_list: List[str] = []
    categories_order = classes_dict.get("IncidentEnvironment", [])

    for category in categories_order:
        for leaf_class in classes_dict.get(category, []) or []:
            flat_list.append(leaf_class)

    return flat_list


def get_leaf_classes(classes_dict: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Get flat list of leaf classes from the central config or provided dict."""
    if classes_dict is None:
        classes_dict = load_master_classes()
    return flatten_classes(classes_dict)


def get_hierarchical_class_labels() -> List[str]:
    """
    Build hierarchical labels for level-3 detection classes in the form:
    "IncidentEnvironment -> <CATEGORY> -> <CLASS>".
    """
    classes = load_master_classes()
    root = "IncidentEnvironment"
    labels: List[str] = []
    categories = classes.get(root, []) or []
    for category in categories:
        leaf_classes = classes.get(category, []) or []
        for leaf in leaf_classes:
            labels.append(f"{root} -> {category} -> {leaf}")
    return labels


def get_classes_hash(class_list: List[str]) -> str:
    """Return a stable hash for a class list."""
    payload = "\n".join(class_list).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_config_path() -> Path:
    """Expose the resolved config path for export and diagnostics."""
    existing = _get_existing_config_path()
    if existing is not None:
        return existing
    return _get_writable_config_path()
