#!/usr/bin/env python
"""Debug model loading and class name mapping"""
import sys
from pathlib import Path

# Check what models are actually available
models_dir = Path("models") / "yolo_versions"
print(f"Models directory: {models_dir}")
print(f"Exists: {models_dir.exists()}\n")

if models_dir.exists():
    version_dirs = sorted(models_dir.glob("v*"), reverse=True)
    print(f"Found {len(version_dirs)} model versions:")
    for idx, version_dir in enumerate(version_dirs):
        best_pt = version_dir / "best.pt"
        exists = best_pt.exists()
        size = best_pt.stat().st_size if exists else 0
        print(f"  {idx}: {version_dir.name} - best.pt exists: {exists}, size: {size}")
    print()

# Try loading a model and checking class names
try:
    from ultralytics import YOLO
    
    # Find the latest trained model
    latest_model = None
    for version_dir in sorted(models_dir.glob("v*"), reverse=True):
        best_pt = version_dir / "best.pt"
        if best_pt.exists():
            latest_model = str(best_pt)
            break
    
    if latest_model:
        print(f"Loading model: {latest_model}")
        model = YOLO(latest_model)
        
        print(f"\nModel names property: {model.names}")
        print(f"Number of classes: {len(model.names)}")
        
        # Test class mapping
        for cls_id in range(min(5, len(model.names))):
            print(f"  Class {cls_id}: {model.names[cls_id]}")
        
        # Load dataset.yaml to compare
        dataset_yaml = Path("training_data/yolo_dataset/dataset.yaml")
        if dataset_yaml.exists():
            import yaml
            print(f"\nDataset YAML: {dataset_yaml}")
            with open(dataset_yaml) as f:
                data = yaml.safe_load(f)
                yaml_names = data.get('names', {})
                print(f"YAML classes: {len(yaml_names)}")
                for cls_id in range(min(5, len(yaml_names))):
                    print(f"  Class {cls_id}: {yaml_names.get(cls_id, f'UNKNOWN_{cls_id}')}")
    else:
        print("No trained models found!")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
