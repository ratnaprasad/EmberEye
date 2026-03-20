# EmberEye Training & Model Versioning Guide

## 📁 Data Storage Structure

### Current Structure (After Fix)
```
Project Root/
├── video.mp4  (or other videos)
└── annotations/
    └── video_name/
        ├── frame_00000.jpg         ← ✅ NOW SAVED (was missing!)
        ├── frame_00000.txt         ← YOLO annotations
        ├── frame_00001.jpg
        ├── frame_00001.txt
        ├── frame_00100.jpg
        ├── frame_00100.txt
        └── labels.txt              ← Class names
```

**Key Fix**: Frames are now **automatically saved** when you click "Save Frame Annotations" in the annotation tool.

---

## 🚀 Complete Training Workflow

### **Phase 1: Annotation (One-time per frame)**
1. Open video in annotation tool
2. Draw boxes on frames
3. Click "**Save Frame Annotations**"
   - Saves both: `frame_XXXXX.jpg` + `frame_XXXXX.txt`
   - Repeat for all labeled frames

### **Phase 2: Prepare Dataset**
```python
from training_pipeline import TrainingConfig, YOLOTrainingPipeline

config = TrainingConfig(
    project_name="fire_detector_v1",
    epochs=100,
    batch_size=16,
    device="auto"
)

pipeline = YOLOTrainingPipeline(config=config)
success, msg = pipeline.run_full_pipeline()
```

Result: `training_data/dataset/` with train/val/test splits

### **Phase 3: Version Control**
```python
from model_versioning import ModelVersionManager, ModelMetadata
from datetime import datetime

version_mgr = ModelVersionManager()

# Create metadata
metadata = ModelMetadata(
    version="v1",
    timestamp=datetime.now().isoformat(),
    training_images=1000,
    new_images=1000,
    total_epochs=100,
    best_accuracy=0.92,  # mAP50
    loss=0.045,
    training_time_hours=2.5,
    base_model="yolov8n",
    config_snapshot=config.to_dict(),
    notes="Initial training with 1000 fire frames"
)

# Register version
version_mgr.create_version(
    metadata=metadata,
    source_weights_dir=Path("runs/detect/fire_detector_v1/weights")
)
```

---

## 📈 Incremental Training (Add New Images)

### Scenario: You trained with 1000 images, now add 100 more

```python
from model_versioning import IncrementalTrainingManager

training_mgr = IncrementalTrainingManager()

# Get current stats
stats = training_mgr.get_dataset_stats()
print(f"Total frames: {stats['total_frames']}")  # Now: 1100

# Check if retraining recommended
recommended, msg = training_mgr.suggest_retraining("v1", threshold=50)
print(msg)  # "Recommended retraining: 100 new images (threshold: 50)"

# Start new training
config_v2 = TrainingConfig(
    project_name="fire_detector_v2",
    epochs=50,  # ← Can use fewer epochs (transfer learning)
    batch_size=16,
    device="auto"
)

pipeline_v2 = YOLOTrainingPipeline(config=config_v2)
success, msg = pipeline_v2.run_full_pipeline()

# Create v2 metadata
metadata_v2 = ModelMetadata(
    version="v2",
    timestamp=datetime.now().isoformat(),
    training_images=1100,  # Total now
    new_images=100,        # Only new ones
    total_epochs=50,
    best_accuracy=0.945,   # Should improve!
    loss=0.038,
    training_time_hours=1.2,  # Faster (transfer learning)
    base_model="yolov8n",
    config_snapshot=config_v2.to_dict(),
    notes="Incremental training: added 100 new frames"
)

version_mgr.create_version(metadata_v2, ...)
```

---

## 🎯 Model Management Strategy

### **Keep or Delete Old Models?**

**✅ RECOMMENDATION: Keep All Versions**

**Reasons:**
1. **Rollback capability** - If v2 performs worse, revert to v1
2. **Benchmark tracking** - Compare metrics across versions
3. **Storage is cheap** - Each model ~50-200MB (negligible cost)
4. **Production safety** - Test v2 before replacing v1 in production

**Directory Structure:**
```
models/yolo_versions/
├── v1/
│   ├── weights/
│   │   ├── best.pt
│   │   └── last.pt
│   └── metadata.json          ← Track all training details
├── v2/
│   ├── weights/
│   │   ├── best.pt
│   │   └── last.pt
│   └── metadata.json
├── v3/
│   └── ...
└── current_best.pt ──→ v2/weights/best.pt  ← Symlink to production model
```

---

## 📊 Monitor Training Progress

### Version Comparison Report
```python
# Print all versions with metrics
report = version_mgr.get_version_comparison()
print(report)
```

Output:
```
📊 MODEL VERSION HISTORY
================================================================================
Version     Date                 Images       mAP50      Loss      
--------------------------------------------------------------------------------
v1          2025-12-20           1000         0.9200     0.0450    
v2          2025-12-21           1100         0.9450     0.0380    
v3          2025-12-22           1150         0.9520     0.0365    
================================================================================
🎯 Current Best: models/yolo_versions/v3/weights/best.pt
```

---

## ⚙️ Advanced: Transfer Learning for Incremental Training

When training v2 with only new images:

```python
# Option A: Retrain on ALL data (slower, more accurate)
# Use: training_data/dataset/ (all 1100 images)

# Option B: Fine-tune on NEW data only (faster, uses transfer learning)
# Use: training_data/dataset_v2_new/ (only 100 new images)
# Set: epochs=30 (instead of 100)

config_v2_incremental = TrainingConfig(
    project_name="fire_detector_v2_incremental",
    epochs=30,          # ← Fewer epochs (transfer learning)
    batch_size=8,       # ← Smaller batch for smaller dataset
    lr0=0.001,          # ← Lower learning rate (fine-tune)
    device="auto"
)
```

**Performance Comparison:**
- **Retrain all**: 1.2 hours, mAP50 = 94.5% ✓ Better
- **Incremental**: 0.3 hours, mAP50 = 93.8% (faster but slightly lower)

---

## 🔄 Complete Example Workflow

```python
from pathlib import Path
from datetime import datetime
from training_pipeline import TrainingConfig, YOLOTrainingPipeline
from model_versioning import ModelVersionManager, ModelMetadata, IncrementalTrainingManager

# Managers
version_mgr = ModelVersionManager("./models/yolo_versions")
training_mgr = IncrementalTrainingManager("./training_data")

print("=" * 60)
print("EMBEREYE TRAINING WORKFLOW")
print("=" * 60)

# Step 1: Check dataset
stats = training_mgr.get_dataset_stats()
print(f"📊 Total frames ready: {stats['total_frames']}")

# Step 2: Prepare config
config = TrainingConfig(
    project_name=f"fire_detector_{version_mgr.get_next_version()}",
    epochs=100,
    device="auto"
)

# Step 3: Train
pipeline = YOLOTrainingPipeline(config=config)
print("🚀 Starting training...")
success, msg = pipeline.run_full_pipeline()

if not success:
    print(f"❌ Training failed: {msg}")
    exit(1)

# Step 4: Create version
model_path = pipeline.get_best_model_path()
metadata = ModelMetadata(
    version=version_mgr.get_next_version(),
    timestamp=datetime.now().isoformat(),
    training_images=stats['total_frames'],
    new_images=stats['total_frames'],  # Change for incremental
    total_epochs=config.epochs,
    best_accuracy=0.92,  # Read from training logs
    loss=0.045,
    training_time_hours=2.5,
    base_model=f"yolov8{config.model_size}",
    config_snapshot=config.to_dict(),
    notes="Production training"
)

success, msg = version_mgr.create_version(
    metadata=metadata,
    source_weights_dir=Path(model_path).parent
)

print(msg)

# Step 5: Promote to production
version_mgr.promote_to_best(metadata.version)
print(f"✅ {metadata.version} is now production model")

# Step 6: Show report
print(version_mgr.get_version_comparison())
```

---

## 💾 Where Everything Is Stored

| Component | Location | Purpose |
|-----------|----------|---------|
| **Raw Videos** | `./video.mp4` | Source videos |
| **Annotated Frames** | `./annotations/<video_name>/` | Images + YOLO labels |
| **Training Dataset** | `./training_data/dataset/` | Train/val/test splits |
| **Model v1** | `./models/yolo_versions/v1/weights/best.pt` | First trained model |
| **Model v2** | `./models/yolo_versions/v2/weights/best.pt` | Updated model (incremental) |
| **Current Best** | `./models/yolo_versions/current_best.pt` | Symlink to production model |
| **Metadata** | `./models/yolo_versions/v*/metadata.json` | Training details & metrics |
| **Version Index** | `./models/yolo_versions/all_versions.json` | History of all versions |

---

## 🎓 Key Takeaways

✅ **Frames + Annotations** saved automatically in `annotations/`  
✅ **Every new training = new version** (v1, v2, v3...)  
✅ **Old models kept** for rollback & comparison  
✅ **Incremental training** adds ~100 frames → retrain efficiently  
✅ **Transfer learning** speeds up incremental training  
✅ **Metadata tracked** for auditability  
✅ **Cross-platform** GPU/CPU auto-detection  

