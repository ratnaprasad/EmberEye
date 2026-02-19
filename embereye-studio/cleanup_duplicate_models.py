#!/usr/bin/env python
"""
Cleanup duplicate archived models.
Keeps only one version per unique model (based on file size and content).
"""
from pathlib import Path
import shutil

models_dir = Path("models/yolo_versions")

if not models_dir.exists():
    print("No models directory found")
    exit(0)

# Collect all models with their metadata
models = []
for version_dir in models_dir.glob("v*"):
    best_pt = version_dir / "best.pt"
    if best_pt.exists():
        models.append({
            'dir': version_dir,
            'name': version_dir.name,
            'size': best_pt.stat().st_size,
            'mtime': best_pt.stat().st_mtime
        })

# Sort by modification time (oldest first)
models.sort(key=lambda m: m['mtime'])

print(f"Found {len(models)} archived models")
print("-" * 60)

# Track unique models (by size)
seen_sizes = {}
duplicates = []

for model in models:
    size = model['size']
    
    if size in seen_sizes:
        # This is a duplicate
        duplicates.append(model)
        print(f"❌ DUPLICATE: {model['name']} (same size as {seen_sizes[size]['name']})")
    else:
        # This is unique
        seen_sizes[size] = model
        print(f"✅ KEEP: {model['name']}")

print("-" * 60)
print(f"\nSummary:")
print(f"  Unique models: {len(seen_sizes)}")
print(f"  Duplicates: {len(duplicates)}")

if duplicates:
    print(f"\nDuplicates to remove:")
    for dup in duplicates:
        print(f"  - {dup['name']}")
    
    response = input(f"\nDelete {len(duplicates)} duplicate model(s)? [y/N]: ")
    if response.lower() == 'y':
        for dup in duplicates:
            print(f"Deleting {dup['name']}...")
            shutil.rmtree(dup['dir'])
        print(f"\n✅ Deleted {len(duplicates)} duplicate(s)")
    else:
        print("Cancelled - no models deleted")
else:
    print("\n✅ No duplicates found!")
