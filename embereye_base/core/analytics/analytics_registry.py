"""
Analytics category registry for EmberEye.

A single config value — `active_analytics_category` in stream_config.json —
controls which inference model is loaded by the Field app and which Fusion
banner cards are displayed.  EmberEye Studio uses the same registry to filter
annotation classes and tag training runs.

Adding a new category:
1. Add an entry to ANALYTICS_REGISTRY below.
2. Add corresponding category keys to embereye/core/class_config.ANALYTICS_CATEGORY_KEYS.
3. Add the PPE class entries (or fire class entries) to embereye/config/master_classes.json.
4. Add a banner rendering branch in embereye-field/util/fusionbanner.py.
"""

from __future__ import annotations
from typing import Dict, Any

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ANALYTICS_REGISTRY: Dict[str, Dict[str, Any]] = {
    "fire": {
        "display_name": "Fire & Smoke Detection",
        # Filename hint used to locate the model inside ./models/.
        # The Field app searches for any .pt file whose name contains this hint.
        "model_hint": "fire",
        # Keys from master_classes.json whose leaf classes this model detects.
        "class_category_keys": [
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
        # Cards shown in the Fusion banner (matches keys in fusionbanner.py).
        "fusion_cards": ["global", "thermal", "gas", "smoke", "flame", "action"],
        # fusion_data keys expected by the banner renderer for this category.
        "banner_data_keys": [
            "confidence", "alarm", "sources",
            "thermal_max", "gas_ppm", "smoke_level",
            "flame_digital", "flame_analog_pct",
            "temp_threshold", "critical_temp_threshold",
            "gas_ppm_threshold", "smoke_threshold_pct", "flame_threshold_pct",
            "hot_cells",
        ],
    },
    "ppe": {
        "display_name": "PPE Compliance Monitoring",
        "model_hint": "ppe",
        "class_category_keys": [
            "PPE_CATEGORY",
        ],
        # Fusion banner cards for PPE mode.
        "fusion_cards": ["global", "helmet", "vest", "violations", "action"],
        "banner_data_keys": [
            "confidence", "alarm",
            # Counts produced by the PPE inference pipeline.
            "helmet_count",      # workers wearing helmet
            "no_helmet_count",   # workers NOT wearing helmet
            "vest_count",        # workers wearing vest
            "no_vest_count",     # workers NOT wearing vest
            "total_persons",     # total person detections in frame
        ],
    },
}

# Ordered list of all registered categories (used for UI dropdowns).
ANALYTICS_CATEGORY_NAMES = list(ANALYTICS_REGISTRY.keys())

DEFAULT_ANALYTICS_CATEGORY = "fire"


def get_category(name: str) -> Dict[str, Any]:
    """Return registry entry for *name*, or the default 'fire' entry."""
    return ANALYTICS_REGISTRY.get(str(name).lower(), ANALYTICS_REGISTRY[DEFAULT_ANALYTICS_CATEGORY])


def get_display_name(name: str) -> str:
    return get_category(name).get("display_name", name.upper())


def get_model_hint(name: str) -> str:
    return get_category(name).get("model_hint", "fire")


def get_fusion_cards(name: str):
    return list(get_category(name).get("fusion_cards", ["global", "action"]))
