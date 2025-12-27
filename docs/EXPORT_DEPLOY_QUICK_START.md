# Quick Integration Guide - Export & Deploy

## 🚀 TL;DR - Fast Setup

### 1. Train Model Locally
```python
from training_pipeline import TrainingConfig, YOLOTrainingPipeline
from model_versioning import ModelVersionManager, ModelMetadata
from datetime import datetime
from pathlib import Path

config = TrainingConfig(project_name="fire_detector_v2", epochs=50)
pipeline = YOLOTrainingPipeline(config=config)
pipeline.run_full_pipeline()

metadata = ModelMetadata(
    version="v2",
    timestamp=datetime.now().isoformat(),
    training_images=1100,      # ALL images (v1 + new)
    new_images=100,
    total_epochs=50,
    best_accuracy=0.945,
    loss=0.038,
    training_time_hours=1.2,
    base_model="yolov8n",
    config_snapshot=config.to_dict(),
    previous_version="v1",
    training_strategy="full_retrain",
    notes="Incremental training"
)

version_mgr = ModelVersionManager()
version_mgr.create_version(metadata, Path("runs/detect/fire_detector_v2/weights"))
```

### 2. Export Model
```python
from model_export_deploy import ModelExporter

exporter = ModelExporter()
exporter.export_trained_model("v2")
```

### 3. Create Package
```python
from model_export_deploy import ModelDeployer

deployer = ModelDeployer()
success, package_path = deployer.create_deployment_package("v2", target_os="auto", device_type="all")
```

### 4. Deploy on Client
```python
from model_export_deploy import ModelImporter

importer = ModelImporter("C:\\Program Files\\EmberEye")  # Or /Applications/EmberEye or /opt/embereye
success, msg = importer.import_model_package(package_path, device_type="auto")
```

---

## 📂 File Locations After Each Step

### After Training
```
models/yolo_versions/v2/
├── weights/
│   ├── best.pt
│   ├── EmberEye.pt           ← Production name
│   └── last.pt
└── metadata.json
```

### After Export
```
models/yolo_versions/exports/v2/
├── EmberEye.pt               ← CPU version
├── EmberEye_config.json
├── EmberEye_gpu.pt           ← NVIDIA GPU version
├── EmberEye_gpu_config.json
├── EmberEye_mps.pt           ← Apple Metal version
├── EmberEye_mps_config.json
└── deployment_manifest.json
```

### After Packaging
```
models/yolo_versions/exports/packages/
└── EmberEye_v2_auto_all.zip  ← Distribution package
```

### After Deployment (Client Machine)
```
C:\Program Files\EmberEye\models\        (Windows)
├── EmberEye.pt                          ← Imported model
├── EmberEye_config.json
└── backups/
    └── EmberEye_backup_20251221_143015.pt
```

---

## 🔄 Data Flow Diagram

```
Training Location:
frames/               videos
  ├── video1/        (1000 images)
  │   ├── frame_0.jpg
  │   ├── frame_0.txt
  │   └── ...
  └── video2/        (100 NEW images)
      ├── frame_1000.jpg
      ├── frame_1000.txt
      └── ...
       ↓
DatasetManager validates & splits (train/val/test)
       ↓
YOLOTrainingPipeline (50 epochs, transfer learning from v1)
       ↓
runs/detect/fire_detector_v2/weights/best.pt
       ↓
ModelVersionManager creates v2:
  - models/yolo_versions/v2/weights/best.pt
  - models/yolo_versions/v2/weights/EmberEye.pt ← PRODUCTION
  - models/yolo_versions/v2/metadata.json
       ↓
ModelExporter exports variants:
  - models/yolo_versions/exports/v2/EmberEye.pt (CPU)
  - models/yolo_versions/exports/v2/EmberEye_gpu.pt (GPU)
  - models/yolo_versions/exports/v2/EmberEye_mps.pt (Apple)
       ↓
ModelDeployer packages:
  - models/yolo_versions/exports/packages/EmberEye_v2_auto_all.zip
       ↓
Distributed to Client Machines
       ↓
ModelImporter (on each client):
  - Auto-detects device (CPU/GPU/MPS)
  - Extracts EmberEye*.pt
  - Backs up old model
  - Installs new model to C:\Program Files\EmberEye\models\
  - EmberEye app uses EmberEye.pt automatically
```

---

## 🎯 Key Design Decisions

### 1. Full Retrain Approach ✅
- **v2 trains on 1100 images** (not just 100 new)
- **Transfer learning from v1 weights** (fewer epochs needed)
- **Metadata tracks both:**
  - `training_images: 1100` (total used for this training)
  - `new_images: 100` (only new ones added this round)

### 2. EmberEye Naming Convention ✅
- **Production files named:** `EmberEye.pt`, `EmberEye_gpu.pt`, `EmberEye_mps.pt`
- **Internal tracking:** Also saved as `best.pt` (YOLOv8 standard)
- **Symlink:** `current_best.pt` → `v2/weights/EmberEye.pt`

### 3. Device-Aware Export ✅
- **Export creates 3 variants:**
  - `EmberEye.pt` - Works on all platforms, CPU optimized
  - `EmberEye_gpu.pt` - NVIDIA CUDA 11.8+
  - `EmberEye_mps.pt` - Apple macOS 12.3+ (M1/M2/M3)
- **Each variant includes config file** with training metadata

### 4. Auto-Detect Deployment ✅
- **Client machine auto-detects capabilities:**
  - Try NVIDIA GPU (nvidia-smi)
  - Try Apple MPS (macOS 12.3+)
  - Fallback to CPU
- **Imports appropriate variant automatically**
- **Backs up current model before updating**

### 5. Cross-Platform Support ✅
- **Single package (.zip)** contains all variants
- **Works on Windows, macOS, Linux**
- **Supports both GPU and CPU scenarios**

---

## 📊 Example Metadata Comparison

### v1 Metadata
```json
{
  "version": "v1",
  "training_images": 1000,
  "new_images": 1000,
  "best_accuracy": 0.92,
  "training_strategy": "full_retrain",
  "previous_version": null
}
```

### v2 Metadata
```json
{
  "version": "v2",
  "training_images": 1100,          ← ALL images (1000 + 100)
  "new_images": 100,                ← Only new this round
  "best_accuracy": 0.945,           ← Improved!
  "training_strategy": "full_retrain",
  "previous_version": "v1",         ← Transfer learning from v1
  "training_time_hours": 1.2        ← Faster (transfer learning)
}
```

---

## ✅ Verification Checklist

After each step, verify:

```
[ ] Step 1: Model trained
    - runs/detect/fire_detector_v2/weights/best.pt exists
    
[ ] Step 2: Version created
    - models/yolo_versions/v2/weights/EmberEye.pt exists
    - models/yolo_versions/v2/metadata.json contains all fields
    
[ ] Step 3: Models exported
    - models/yolo_versions/exports/v2/EmberEye.pt exists
    - models/yolo_versions/exports/v2/EmberEye_gpu.pt exists
    - models/yolo_versions/exports/v2/EmberEye_mps.pt exists
    - models/yolo_versions/exports/v2/deployment_manifest.json exists
    
[ ] Step 4: Package created
    - models/yolo_versions/exports/packages/EmberEye_v2_auto_all.zip exists
    - Size: ~500MB (contains all variants)
    
[ ] Step 5: Deployed on client
    - C:\Program Files\EmberEye\models\EmberEye.pt exists
    - C:\Program Files\EmberEye\models\backups\EmberEye_backup_*.pt exists
    - EmberEye app loads new model on restart
```

---

## 🐛 Debugging

### Check what model is in use
```python
from model_versioning import ModelVersionManager

mgr = ModelVersionManager()
current_model = mgr.get_current_best()
print(f"Current production model: {current_model}")
```

### Check version history
```python
mgr = ModelVersionManager()
print(mgr.get_version_comparison())

# Output:
# 📊 MODEL VERSION HISTORY
# ════════════════════════════════════════
# Version    Images    mAP50     Loss
# ────────────────────────────────────────
# v1         1000      0.9200    0.0450
# v2         1100      0.9450    0.0380
# ════════════════════════════════════════
```

### Verify client installation
```python
from model_export_deploy import ModelImporter

importer = ModelImporter("C:\\Program Files\\EmberEye")
is_valid, status = importer.verify_installation()
print(f"Installation valid: {is_valid}")
print(f"Status: {status}")
```

### Rollback to previous version
```bash
# Manual rollback
rm C:\Program Files\EmberEye\models\EmberEye.pt
cp C:\Program Files\EmberEye\models\backups\EmberEye_backup_20251220_143015.pt \
   C:\Program Files\EmberEye\models\EmberEye.pt
```

---

## 📦 Package Contents Example

When you unzip `EmberEye_v2_auto_all.zip`:

```
EmberEye_v2_auto_all/
├── EmberEye.pt                    (70MB - CPU)
├── EmberEye_config.json           (5KB)
├── EmberEye_gpu.pt                (70MB - NVIDIA GPU)
├── EmberEye_gpu_config.json       (5KB)
├── EmberEye_mps.pt                (70MB - Apple Metal)
├── EmberEye_mps_config.json       (5KB)
├── deployment_manifest.json       (2KB)
└── README.md                      (Installation guide)
```

Total size: ~500MB (contains all 3 variants)

---

## 🎓 Next Steps

1. ✅ Implement full retrain approach (v2 uses 1100 images)
2. ✅ Export models with device-specific variants
3. ✅ Create deployment package for distribution
4. ✅ Deploy to multiple client machines
5. 📋 Integrate export/import into main EmberEye UI (optional)
6. 📋 Create CI/CD pipeline for automated training (optional)
7. 📋 Monitor model performance across all deployments (optional)

