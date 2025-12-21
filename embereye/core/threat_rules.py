"""
Threat rules storage for EmberEye taxonomy UI.
Simple JSON persistence for threat matrix and example scenarios.
"""
import json
import os

SEVERITIES = ["NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Threat matrix based on detected classes and proximity
DEFAULT_THREAT_RULES = {
    "CRITICAL": [
        "flame + person_distress in same quadrant",
        "smoke_toxic + confined_space",
        "damaged_vent + smoke_heavy + pressure_vessel",
        "vehicle_fire + road (traffic context)",
        "explosion detected",
        "electrical_arc detected"
    ],
    "HIGH": [
        "flame detected alone",
        "smoke_heavy + indoor",
        "spark + equipment_leak",
        "person_distress alone",
        "fire + fuel_tank",
        "fire + gas_cylinder"
    ],
    "MEDIUM": [
        "smoke detected alone",
        "ember + industrial_vehicle",
        "steam + pressure_vessel",
        "structural_deform alone",
        "spark + flammable_liquid",
        "heat_haze + pressure_vessel"
    ],
    "LOW": [
        "steam alone",
        "heat_haze alone",
        "person_protected alone",
        "fire_extinguisher visible",
        "sprinkler visible",
        "alarm_light active"
    ]
}

# Example threat scenarios for reference
DEFAULT_EXAMPLES = [
    {
        "name": "Factory Fire (Critical)",
        "detected": ["flame", "smoke_heavy", "indoor", "person_distress"],
        "classification": "CRITICAL",
        "rule": "flame + person_distress in same quadrant",
        "notes": "Active fire with occupants at risk"
    },
    {
        "name": "Vehicle Fire on Road (Critical)",
        "detected": ["flame", "vehicle", "road", "smoke"],
        "classification": "CRITICAL",
        "rule": "vehicle_fire + road (traffic context)",
        "notes": "Traffic hazard with active fire"
    },
    {
        "name": "Dented Vent with Smoke (High)",
        "detected": ["damaged_vent", "smoke", "outdoor"],
        "classification": "HIGH",
        "rule": "damaged equipment + smoke",
        "notes": "Structural damage with smoke emission"
    },
    {
        "name": "Unclassified Fire (Default)",
        "detected": ["flame"],
        "classification": "unclassified_fire",
        "rule": "flame only (no context)",
        "notes": "Flame without additional context clues"
    },
    {
        "name": "Normal Scene (No Threat)",
        "detected": ["person_protected", "industrial_vehicle"],
        "classification": "non_threat",
        "rule": "safe configuration",
        "notes": "Normal industrial operations"
    }
]

DEFAULT_SETTINGS = {
    "default_flame": "HIGH",
    "default_smoke": "MEDIUM",
    "score_threshold": 0.4,
    "notes": "",
}

RULES_FILE = "threat_rules.json"


def load_threat_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r") as f:
                data = json.load(f)
                rules = data.get("threat_matrix", DEFAULT_THREAT_RULES.copy())
                examples = data.get("examples", DEFAULT_EXAMPLES.copy())
                settings = data.get("settings", DEFAULT_SETTINGS.copy())
                return rules, examples, settings
        except Exception as e:
            print(f"[THREAT_RULES] Error loading: {e}")
    return DEFAULT_THREAT_RULES.copy(), DEFAULT_EXAMPLES.copy(), DEFAULT_SETTINGS.copy()


def save_threat_rules(rules, examples, settings):
    try:
        payload = {
            "threat_matrix": rules,
            "examples": examples,
            "settings": settings,
        }
        with open(RULES_FILE, "w") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception as e:
        print(f"[THREAT_RULES] Error saving: {e}")
        return False

