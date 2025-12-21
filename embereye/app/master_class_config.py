"""
Master Class Configuration Module for EmberEye.
Manages hierarchical class/subclass definitions for object detection.
"""

import json
import os

DEFAULT_MASTER_CLASSES = {
    "IncidentEnvironment": ["FIRE_CATEGORY", "SMOKE_CATEGORY", "STRUCTURAL_CATEGORY", "HUMAN_CATEGORY", "VEHICLE_CATEGORY", "SAFETY_CATEGORY", "ENVIRONMENT_MARKERS"],
    "FIRE_CATEGORY": ["flame", "spark", "ember", "heat_haze"],
    "SMOKE_CATEGORY": ["smoke", "smoke_heavy", "smoke_toxic", "steam"],
    "STRUCTURAL_CATEGORY": ["damaged_vent", "structural_deform", "equipment_leak", "pressure_vessel"],
    "HUMAN_CATEGORY": ["person", "person_protected", "person_distress", "person_rescuer"],
    "VEHICLE_CATEGORY": ["vehicle", "ship", "aircraft", "industrial_vehicle"],
    "SAFETY_CATEGORY": ["fire_extinguisher", "emergency_exit", "sprinkler", "alarm_light"],
    "ENVIRONMENT_MARKERS": ["indoor", "outdoor", "confined_space", "road"]
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
    Convert hierarchical class dict to flat list of all classes and subclasses.
    Returns list like: ['person', 'person:adult', 'person:child', ...]
    """
    flat_list = []
    for main_class, subclasses in classes_dict.items():
        flat_list.append(main_class)
        if subclasses:
            for subclass in subclasses:
                flat_list.append(f"{main_class}:{subclass}")
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
