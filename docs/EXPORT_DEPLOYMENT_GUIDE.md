# Export & Deployment Guide - EmberEye ML Models

## 🎯 Overview

This guide explains how to:
1. **Train models** at one central location
2. **Export trained models** with device-specific variants
3. **Deploy to multiple EmberEye installations** (CPU/GPU based)
4. **Auto-detect client device capabilities** and install appropriate variant

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRAINING LOCATION                            │
│                  (Central Server/PC)                             │
│                                                                  │
│  1. Annotate frames (1000 images)                               │
│  2. Train YOLOv8 → v1 (best.pt → EmberEye.pt)                 │
│  3. Add 100 new frames (1100 total)                             │
│  4. Retrain → v2 (ALL 1100 images, transfer learning)          │
│  5. Export with device variants                                 │
│                                                                  │
│     models/yolo_versions/v2/weights/                            │
│     ├── EmberEye.pt           (CPU optimized)                   │
│     ├── EmberEye_gpu.pt       (NVIDIA GPU)                      │
│     └── EmberEye_mps.pt       (Apple Metal)                     │
│                                                                  │
│  6. Create deployment package (.zip)                            │
└─────────────────────────────────────────────────────────────────┘
           ↓ Download/Copy Package ↓
┌─────────────────────────────────────────────────────────────────┐
│              DEPLOYMENT LOCATIONS                               │
│         (Multiple EmberEye Installations)                       │
│                                                                  │
│  Location 1: Windows PC with NVIDIA GPU                         │
│  → Auto-detects GPU → Imports EmberEye_gpu.pt                  │
│                                                                  │
│  Location 2: macOS with Apple Silicon                           │
│  → Auto-detects MPS → Imports EmberEye_mps.pt                  │
│                                                                  │
│  Location 3: Linux Server (CPU only)                            │
│  → Auto-detects CPU → Imports EmberEye.pt                      │
│                                                                  │
│  Each location runs with optimal performance for their device   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Step 1: Implement Full Retrain Approach

### Training v1 (Initial)
```python
from training_pipeline import TrainingConfig, YOLOTrainingPipeline
from model_versioning import ModelVersionManager, ModelMetadata
from datetime import datetime
from pathlib import Path

# Configure for 1000 initial images
config = TrainingConfig(
    project_name="fire_detector_v1",
    epochs=100,
    batch_size=16,
    device="auto"
)

# Train
pipeline = YOLOTrainingPipeline(config=config)
success, msg = pipeline.run_full_pipeline()

if success:
    # Create v1 metadata
    metadata_v1 = ModelMetadata(
        version="v1",
        timestamp=datetime.now().isoformat(),
        training_images=1000,        # Total
        new_images=1000,             # All new
        total_epochs=100,
        best_accuracy=0.92,
        loss=0.045,
        training_time_hours=2.5,
        base_model="yolov8n",
        config_snapshot=config.to_dict(),
        training_strategy="full_retrain",
        notes="Initial training with 1000 fire frames"
    )
    
    # Register v1
    version_mgr = ModelVersionManager()
    version_mgr.create_version(
        metadata=metadata_v1,
        source_weights_dir=Path("runs/detect/fire_detector_v1/weights")
    )
    print("✅ v1 Created with EmberEye.pt ready for export")
```

**Output:**
```
models/yolo_versions/v1/
├── weights/
│   ├── best.pt
│   └── EmberEye.pt  ← Production name (same as best.pt)
└── metadata.json
```

---

## 🚀 Step 2: Incremental Training (v2)

### Add 100 New Frames, Train on ALL 1100
```python
# After annotating 100 more frames:
# Total frames now: 1000 (v1) + 100 (new) = 1100

config_v2 = TrainingConfig(
    project_name="fire_detector_v2",
    epochs=50,          # Fewer epochs (transfer learning from v1)
    batch_size=16,
    device="auto"
)

pipeline_v2 = YOLOTrainingPipeline(config=config_v2)
success, msg = pipeline_v2.run_full_pipeline()
# ⚠️  IMPORTANT: DatasetManager must include ALL 1100 images
#     (1000 from v1 + 100 new)

if success:
    metadata_v2 = ModelMetadata(
        version="v2",
        timestamp=datetime.now().isoformat(),
        training_images=1100,        # ✅ ALL images (v1's 1000 + new 100)
        new_images=100,              # ✅ Only new ones this round
        total_epochs=50,
        best_accuracy=0.945,         # Improved!
        loss=0.038,
        training_time_hours=1.2,     # Faster (transfer learning)
        base_model="yolov8n",
        config_snapshot=config_v2.to_dict(),
        previous_version="v1",       # Transfer learning from v1
        training_strategy="full_retrain",  # Still full retrain (all 1100 images)
        notes="Incremental training: added 100 new frames"
    )
    
    version_mgr.create_version(
        metadata=metadata_v2,
        source_weights_dir=Path("runs/detect/fire_detector_v2/weights")
    )
    
    # Promote v2 as production model
    version_mgr.promote_to_best("v2")
    print("✅ v2 Created and promoted to production")
```

**Output:**
```
models/yolo_versions/
├── v1/
│   ├── weights/
│   │   ├── best.pt
│   │   └── EmberEye.pt
│   └── metadata.json
├── v2/
│   ├── weights/
│   │   ├── best.pt
│   │   └── EmberEye.pt
│   └── metadata.json
└── current_best.pt → v2/weights/EmberEye.pt  ← Points to production model
```

---

## 📦 Step 3: Export Models

### Export v2 with All Device Variants
```python
from model_export_deploy import ModelExporter, DeploymentProfile

exporter = ModelExporter("./models/yolo_versions")

# Export with all device profiles
success, msg = exporter.export_trained_model(
    version="v2",
    deployment_profiles=None  # Uses default: CPU, GPU, MPS
)

if success:
    print(msg)
    # Output: Model v2 exported successfully with 3 profiles
```

**Files Created:**
```
models/yolo_versions/exports/v2/
├── EmberEye.pt                      ← CPU version
├── EmberEye_config.json             ← CPU config
├── EmberEye_gpu.pt                  ← NVIDIA GPU version
├── EmberEye_gpu_config.json         ← GPU config
├── EmberEye_mps.pt                  ← Apple Metal version
├── EmberEye_mps_config.json         ← MPS config
└── deployment_manifest.json         ← Deployment instructions
```

---

## 📮 Step 4: Create Deployment Package

### Package for Distribution
```python
from model_export_deploy import ModelDeployer

deployer = ModelDeployer("./models/yolo_versions/exports")

# Create package with all variants
success, package_path = deployer.create_deployment_package(
    version="v2",
    target_os="auto",        # Include all OS support
    device_type="all"        # Include CPU, GPU, MPS
)

if success:
    print(f"📦 Package created: {package_path}")
    # Output: EmberEye_v2_auto_all.zip (~500MB)
```

**Package Structure:**
```
EmberEye_v2_auto_all.zip
├── EmberEye.pt                    (CPU)
├── EmberEye_config.json
├── EmberEye_gpu.pt                (NVIDIA GPU)
├── EmberEye_gpu_config.json
├── EmberEye_mps.pt                (Apple Metal)
├── EmberEye_mps_config.json
├── deployment_manifest.json
└── README.md                      (Installation instructions)
```

---

## 🖥️ Step 5: Deploy to Client Machines

### Windows PC with NVIDIA GPU
```python
from model_export_deploy import ModelImporter

# Client machine: Windows with NVIDIA GPU
importer = ModelImporter("C:\\Program Files\\EmberEye")

# Import with auto-detection
success, msg = importer.import_model_package(
    package_zip_path="EmberEye_v2_auto_all.zip",
    device_type="auto"  # Auto-detects GPU
)

if success:
    print(msg)
    # Output: Successfully imported EmberEye_gpu.pt (gpu optimized)
```

**Result:**
- Auto-detects NVIDIA GPU
- Imports `EmberEye_gpu.pt`
- Backs up old model
- Restarts EmberEye with new model

---

### macOS with Apple Silicon
```python
# Client machine: macOS M2
importer = ModelImporter("/Applications/EmberEye")

success, msg = importer.import_model_package(
    package_zip_path="EmberEye_v2_auto_all.zip",
    device_type="auto"  # Auto-detects MPS
)

if success:
    print(msg)
    # Output: Successfully imported EmberEye_mps.pt (mps optimized)
```

**Result:**
- Auto-detects Apple Metal Performance Shaders
- Imports `EmberEye_mps.pt`
- ~2-3x faster than CPU

---

### Linux Server (CPU Only)
```python
# Client machine: Linux (no GPU)
importer = ModelImporter("/opt/embereye")

success, msg = importer.import_model_package(
    package_zip_path="EmberEye_v2_auto_all.zip",
    device_type="cpu"   # Fallback to CPU
)

if success:
    print(msg)
    # Output: Successfully imported EmberEye.pt (cpu optimized)
```

---

## 🔍 Step 6: Verify Installation

### Check Model Status on Client
```python
importer = ModelImporter("C:\\Program Files\\EmberEye")

is_valid, status = importer.verify_installation()

print(f"Valid: {is_valid}")
# Output:
# {
#     'install_dir': 'C:\\Program Files\\EmberEye',
#     'models_dir': 'C:\\Program Files\\EmberEye\\models',
#     'model_exists': True,
#     'config_exists': True,
#     'backups': ['EmberEye_backup_20251221_143015.pt']
# }
```

---

## 🔄 Complete Workflow Example

```python
#!/usr/bin/env python
"""Complete export and deployment workflow."""

from pathlib import Path
from datetime import datetime
from training_pipeline import TrainingConfig, YOLOTrainingPipeline
from model_versioning import ModelVersionManager, ModelMetadata
from model_export_deploy import ModelExporter, ModelDeployer, ModelImporter

print("="*70)
print("EMBEREYE TRAINING → EXPORT → DEPLOY WORKFLOW")
print("="*70)

# ========== TRAINING LOCATION ==========
print("\n🏢 TRAINING LOCATION")
print("-"*70)

# Step 1: Train v2 (1100 images: 1000 from v1 + 100 new)
print("\n1️⃣  Training v2 with ALL 1100 images...")
config_v2 = TrainingConfig(
    project_name="fire_detector_v2",
    epochs=50,
    device="auto"
)

pipeline_v2 = YOLOTrainingPipeline(config=config_v2)
success, msg = pipeline_v2.run_full_pipeline()

if success:
    metadata_v2 = ModelMetadata(
        version="v2",
        timestamp=datetime.now().isoformat(),
        training_images=1100,        # ✅ ALL images
        new_images=100,
        total_epochs=50,
        best_accuracy=0.945,
        loss=0.038,
        training_time_hours=1.2,
        base_model="yolov8n",
        config_snapshot=config_v2.to_dict(),
        previous_version="v1",
        training_strategy="full_retrain",
        notes="Incremental training"
    )
    
    version_mgr = ModelVersionManager()
    version_mgr.create_version(
        metadata=metadata_v2,
        source_weights_dir=Path("runs/detect/fire_detector_v2/weights")
    )
    print(f"✅ {msg}")

# Step 2: Export with device variants
print("\n2️⃣  Exporting v2 with device variants...")
exporter = ModelExporter()
success, msg = exporter.export_trained_model("v2")
print(f"✅ {msg}")

# Step 3: Create deployment package
print("\n3️⃣  Creating deployment package...")
deployer = ModelDeployer()
success, package_path = deployer.create_deployment_package(
    version="v2",
    target_os="auto",
    device_type="all"
)
print(f"✅ Package ready: {package_path}")

# ========== DEPLOYMENT LOCATIONS ==========
print("\n\n🌍 DEPLOYMENT LOCATIONS")
print("-"*70)

# Location 1: Windows with GPU
print("\n4️⃣  Client 1 - Windows with NVIDIA GPU")
client1_importer = ModelImporter("C:\\Program Files\\EmberEye")
success, msg = client1_importer.import_model_package(
    package_zip_path=str(package_path),
    device_type="auto"
)
print(f"✅ {msg}")

# Location 2: macOS with Apple Silicon
print("\n5️⃣  Client 2 - macOS with Apple Silicon")
client2_importer = ModelImporter("/Applications/EmberEye")
success, msg = client2_importer.import_model_package(
    package_zip_path=str(package_path),
    device_type="auto"
)
print(f"✅ {msg}")

# Location 3: Linux with CPU
print("\n6️⃣  Client 3 - Linux (CPU only)")
client3_importer = ModelImporter("/opt/embereye")
success, msg = client3_importer.import_model_package(
    package_zip_path=str(package_path),
    device_type="cpu"
)
print(f"✅ {msg}")

print("\n" + "="*70)
print("✅ DEPLOYMENT COMPLETE")
print("="*70)
print("""
Summary:
- v2 trained with 1100 images (full retrain with transfer learning)
- Exported with 3 device variants (CPU/GPU/MPS)
- Deployed to 3 locations with optimal device selection
- Each client auto-selected appropriate model variant

Next Steps:
1. Monitor performance across all locations
2. If satisfied, delete old v1 backups (keep most recent backup)
3. Plan v3 when more data is collected
""")
```

---

## 📋 Model Naming Convention

```
EmberEye.pt          → CPU version (all platforms)
EmberEye_gpu.pt      → NVIDIA CUDA GPU version
EmberEye_mps.pt      → Apple Metal Performance Shaders
```

All files are copied with `_config.json` metadata:
```
EmberEye_config.json
EmberEye_gpu_config.json
EmberEye_mps_config.json
```

---

## ⚠️ Key Points

### Full Retrain Strategy (Recommended)
- ✅ v1 trained on 1000 images
- ✅ v2 trained on 1000 + 100 = **1100 images** (all data)
- ✅ Ensures consistent improvement
- ✅ Better model generalization
- ✅ Faster training with transfer learning from v1 weights
- ✅ Only 50 epochs instead of 100

### Why Keep All Versions?
- **Rollback:** If v2 has issues, revert to v1
- **Comparison:** See metrics for each version
- **Audit trail:** Track training history
- **Storage:** Only ~50-200MB per model

### Deployment Strategy
- **Auto-detect:** Client machine identifies capabilities
- **Optimal selection:** Selects CPU/GPU/MPS variant automatically
- **Portability:** Same package works across Windows/macOS/Linux
- **Backup:** Always backs up previous model before updating

---

## 🔧 Troubleshooting

### Export Failed
```
Check: models/yolo_versions/v2/weights/EmberEye.pt exists
       models/yolo_versions/v2/metadata.json exists
```

### Import Failed on Client
```
1. Extract package manually to models/ folder
2. Copy EmberEye*.pt files
3. Copy EmberEye*_config.json files
4. Restart EmberEye
```

### Wrong Device Variant Imported
```
Manually specify device_type:
- device_type="cpu" (force CPU)
- device_type="gpu" (force NVIDIA GPU)
- device_type="mps" (force Apple Metal)
```

### Model Performance Degraded
```
1. Verify correct model imported (check logs)
2. Check model file size (~120-500MB depending on variant)
3. Restore from backup if needed
4. Report to training team
```

