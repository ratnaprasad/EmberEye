"""
Master Class Configuration Module for EmberEye.
Manages hierarchical class/subclass definitions for object detection.
"""

import json
import os

DEFAULT_MASTER_CLASSES = {
    "person": ["adult", "child", "worker", "visitor"],
    "vehicle": ["car", "truck", "motorcycle", "bicycle"],
    "fire": ["flame", "smoke"],
    "equipment": ["forklift", "crane", "robot"],
    "hazard": ["spill", "obstruction", "unauthorized_entry"]
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
