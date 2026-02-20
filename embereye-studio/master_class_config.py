"""
Master Class Configuration Module for EmberEye.
Manages hierarchical class/subclass definitions for object detection.
"""

import json
import os

DEFAULT_MASTER_CLASSES = {
    "IncidentEnvironment": ["FIRE_CATEGORY", "SMOKE_CATEGORY", "STRUCTURAL_CATEGORY", "HUMAN_CATEGORY", "VEHICLE_CATEGORY", "SAFETY_CATEGORY", "ENVIRONMENT_MARKERS", "SMOKE_SENSITIVITY", "FIRE_SENSITIVITY"],
    "FIRE_CATEGORY": ["CLASS A", "CLASS B", "CLASS C", "CLASS D", "CLASS K"],
    "SMOKE_CATEGORY": ["WHITE SMOKE", "BLACK SMOKE", "BLUE SMOKE", "YELLOW/BROWN SMOKE"],
    "STRUCTURAL_CATEGORY": ["DAMAGED EQUIPMENT", "HIGH_PRESSURE_EQUIPMENT", "FUEL CONTAINER", "ROTARY MACHINES", "ELECTRICAL SWITCHGEAR"],
    "HUMAN_CATEGORY": ["PERSON WITHOUT SAFETY WEAR", "PERSON WITH PPE", "PERSON IN DISTRESS", "RESCUE TEAM", "FIRE SENTRY"],
    "VEHICLE_CATEGORY": ["COMMERCIAL VEHICLE", "SHIP", "AIRCRAFT", "INDUSTRIAL VEHICLE"],
    "SAFETY_CATEGORY": ["FIRE EXTINGUISHER", "SAFETY ALARM", "SPRINKLER", "EMERGENCY EXIT", "EMERGENCY LIGHT"],
    "ENVIRONMENT_MARKERS": ["INDOOR", "OUTDOOR", "RESTRICTED AREA", "WEARHOUSE", "PATHWAY"],
    "SMOKE_SENSITIVITY": ["STEAM", "HARMFUL GASES", "FUMES", "SMOKE WITH FIRE"],
    "FIRE_SENSITIVITY": ["EXPLOSIVES", "WELDING ARC", "CUTTING SPARKS", "FIRE TORCH"]
}

def load_master_classes():
    """
    Load master class configuration from JSON file.
    Returns hierarchical dict of classes and their subclasses.
    """
    config_file = "master_classes.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[MASTER_CLASS] Error loading config: {e}")
    
    # Return defaults if file doesn't exist
    return DEFAULT_MASTER_CLASSES

def save_master_classes(classes_dict):
    """
    Save master class configuration to JSON file.
    """
    config_file = "master_classes.json"
    try:
        with open(config_file, 'w') as f:
            json.dump(classes_dict, f, indent=2)
        return True
    except Exception as e:
        print(f"[MASTER_CLASS] Error saving config: {e}")
        return False

def flatten_classes(classes_dict):
    """
    Convert hierarchical class dict to flat list of only the leaf classes.
    Skips the root 'IncidentEnvironment' key and only includes the actual class names.
    This must match the model's training class order exactly (41 classes, indices 0-40).
    """
    flat_list = []
    # Get the order from IncidentEnvironment
    categories_order = classes_dict.get("IncidentEnvironment", [])
    
    # Flatten only the leaf classes in order
    for category in categories_order:
        if category in classes_dict:
            for leaf_class in classes_dict[category]:
                flat_list.append(leaf_class)
    
    return flat_list

def get_all_classes():
    """Get flat list of all classes."""
    return flatten_classes(load_master_classes())

def get_hierarchical_class_labels():
    """
    Build hierarchical labels for level-3 detection classes in the form:
    "IncidentEnvironment → <CATEGORY> → <CLASS>".

    Returns a list of strings suitable for UI dropdowns.
    """
    classes = load_master_classes()
    root = "IncidentEnvironment"
    labels = []
    categories = classes.get(root, []) or []
    for category in categories:
        leaf_classes = classes.get(category, []) or []
        for leaf in leaf_classes:
            labels.append(f"{root} → {category} → {leaf}")
    return labels
