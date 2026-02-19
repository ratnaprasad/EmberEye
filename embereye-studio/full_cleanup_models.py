#!/usr/bin/env python
"""Clean up both archived and run  models."""
import shutil
from pathlib import Path

# 1. Clean archived models
models_dir = Path("models/yolo_versions")
print("=" * 60)
print("CLEANING ARCHIVED MODELS")
print("=" * 60)

if models_dir.exists():
    for v_dir in models_dir.glob("v*"):
        if (v_dir / "best.pt").exists():
            print(f"Deleting archived: {v_dir.name}")
            shutil.rmtree(v_dir)

# 2. Clean runs directory
runs_dirs = [
    Path("runs/detect"),
    Path("training_data/runs/detect"),
    Path.cwd() / "embereye-studio" / "runs" / "detect",
]

print("\n" + "=" * 60)
print("CLEANING RUNS MODELS")
print("=" * 60)

for runs_base in runs_dirs:
    if runs_base.exists():
        # Find embereye_* directories
        for run_dir in runs_base.glob("embereye_*"):
            print(f"Deleting run: {run_dir.name}")
            shutil.rmtree(run_dir)
        
        # Also check for nested runs
        for run_dir in runs_base.glob("*/runs/detect/embereye_*"):
            print(f"Deleting nested run: {run_dir.name}")
            shutil.rmtree(run_dir)

print("\n✅ Cleanup complete!")
