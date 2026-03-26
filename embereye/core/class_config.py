"""
Central class configuration for EmberEye.
Provides a single source of truth for class taxonomy and helpers.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "master_classes.json"

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
    if _CONFIG_PATH.exists():
        data = _safe_read_json(_CONFIG_PATH)
        if data:
            return data
    return DEFAULT_MASTER_CLASSES


def save_master_classes(classes_dict: Dict[str, List[str]]) -> bool:
    """Save master class configuration to the central JSON file."""
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(classes_dict, handle, indent=2)
        return True
    except Exception as exc:
        print(f"[MASTER_CLASS] Error saving config: {exc}")
        return False


def flatten_classes(classes_dict: Dict[str, List[str]]) -> List[str]:
    """
    Convert hierarchical class dict to flat list of only the leaf classes.
    Skips the root 'IncidentEnvironment' key and only includes the actual class names.
    This must match the model's training class order exactly (41 classes, indices 0-40).
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
    """Expose the central config path for export and diagnostics."""
    return _CONFIG_PATH


# ---------------------------------------------------------------------------
# Analytics-category helpers
# ---------------------------------------------------------------------------

#: Maps an analytics_category name to the master_classes.json category keys
#: that belong to it.  Extend this dict when new categories are added.
ANALYTICS_CATEGORY_KEYS: Dict[str, List[str]] = {
    "fire": [
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
    "ppe": [
        "PPE_CATEGORY",
    ],
}


def get_leaf_classes_for_category(
    analytics_category: str,
    classes_dict: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """Return the flat leaf-class list for a specific analytics category.

    Falls back to all leaf classes if the category is unknown.
    """
    if classes_dict is None:
        classes_dict = load_master_classes()
    category_keys = ANALYTICS_CATEGORY_KEYS.get(str(analytics_category).lower())
    if not category_keys:
        # Unknown category — return all leaf classes (safe fallback)
        return flatten_classes(classes_dict)
    flat: List[str] = []
    for key in category_keys:
        for leaf in classes_dict.get(key, []) or []:
            flat.append(leaf)
    return flat
