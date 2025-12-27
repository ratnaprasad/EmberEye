# Frame Storage & Model Versioning FAQ

## ❓ Where are frames stored?

**Answer:** In `annotations/<video_name>/` folder

### Example
If you load `fire_detection.mp4`:
```
annotations/
└── fire_detection/              ← Directory created from video name
    ├── frame_00000.jpg          ← Saved when you click "Save Frame Annotations"
    ├── frame_00000.txt          ← YOLO annotations
    ├── frame_00001.jpg
    ├── frame_00001.txt
    ├── frame_00050.jpg
    ├── frame_00050.txt
    └── labels.txt               ← Class names
```

### What happens when I click "Save Frame Annotations"?

**Both files are saved:**
1. **frame_XXXXX.jpg** - Actual frame image (uses `cv2.imwrite()`)
2. **frame_XXXXX.txt** - YOLO annotations (class_id x_center y_center width height)

This is configured in [annotation_tool.py](annotation_tool.py#L569):
```python
# Line 569-571: Save frame image
frame_name = f"frame_{self.frame_index:05d}.jpg"
frame_path = os.path.join(out_dir, frame_name)
cv2.imwrite(frame_path, self.current_frame)  # ← Saves the actual image

# Line 573-580: Save YOLO annotations
out_file = os.path.join(out_dir, f"frame_{self.frame_index:05d}.txt")
with open(out_file, "w") as f:
    for cls, x, y, w, h in labeled:
        f.write(f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
```

---

## ❓ Do old models get replaced when I train a new model?

**Answer:** No, ALL models are kept. New versions are created (v1, v2, v3...).

### Model Versioning Explained

**First Training (1000 images):**
```
models/yolo_versions/
└── v1/
    ├── weights/
    │   ├── best.pt
    │   └── last.pt
    └── metadata.json
        ├── version: "v1"
        ├── training_images: 1000
        ├── best_accuracy: 0.92
        └── timestamp: 2025-12-20T10:30:00
```

**Second Training (1000 + 100 new = 1100 images):**
```
models/yolo_versions/
├── v1/
│   ├── weights/
│   │   ├── best.pt       ← KEPT - can rollback
│   │   └── last.pt
│   └── metadata.json
├── v2/                    ← NEW VERSION
│   ├── weights/
│   │   ├── best.pt       ← Best from this training
│   │   └── last.pt
│   └── metadata.json
│       ├── version: "v2"
│       ├── training_images: 1100
│       ├── best_accuracy: 0.945
│       └── timestamp: 2025-12-21T14:15:00
└── current_best.pt ──→ v2/weights/best.pt  ← Symlink to production model
```

### Why Keep All Versions?

| Reason | Benefit |
|--------|---------|
| **Rollback** | If v2 performs worse in production, switch back to v1 instantly |
| **Comparison** | See which version performs best across different metrics |
| **Audit trail** | Track when each model was trained and with how much data |
| **Storage cheap** | Each model ~50-200MB - negligible compared to benefits |
| **A/B testing** | Run v1 vs v2 in production to see real-world performance |

---

## ❓ What's the incremental training workflow?

**Step-by-step example:**

### Step 1: Initial Training (v1)
```python
# You have 1000 annotated frames
# annotation/fire_video/frame_00000.jpg through frame_00999.jpg

config_v1 = TrainingConfig(epochs=100, batch_size=16)
pipeline_v1 = YOLOTrainingPipeline(config=config_v1)
success, msg = pipeline_v1.run_full_pipeline()

# Creates: models/yolo_versions/v1/weights/best.pt
# Metadata: 1000 images, mAP50 = 0.92, loss = 0.045
```

### Step 2: Add 100 New Frames
```
# Annotate 100 more frames
# Now have: frame_01000.jpg through frame_01099.jpg

# Total frames: 1000 + 100 = 1100
# This triggers: "Recommended retraining: 100 new images (threshold: 50)"
```

### Step 3: Retrain (v2) - Fast with Transfer Learning
```python
# Only retrain with NEW data (faster!)
config_v2 = TrainingConfig(
    epochs=30,          # ← Fewer epochs (was 100 for v1)
    batch_size=8,       # ← Smaller batch
    lr0=0.001,          # ← Lower learning rate (fine-tune)
    device="auto"
)

pipeline_v2 = YOLOTrainingPipeline(config=config_v2)
success, msg = pipeline_v2.run_full_pipeline()

# Training time: 0.3 hours (vs 2.5 for v1)
# Creates: models/yolo_versions/v2/weights/best.pt
# Metadata: 1100 total images, mAP50 = 0.945 (improved!), loss = 0.038
```

### Step 4: Production Update
```python
# Automatically promotes best version
version_mgr.promote_to_best("v2")

# Now: current_best.pt points to v2/weights/best.pt
# v1 still available at: models/yolo_versions/v1/weights/best.pt
```

---

## ❓ How do I use these systems?

### Using Annotation Tool
```
1. Open annotation_tool.py (or click "Annotation" in main app)
2. Select video file
3. Click "Load Video"
4. Draw boxes around objects
5. Select class label from dropdown
6. Click "Save Frame Annotations"
   ✅ Saves: frame_00000.jpg + frame_00000.txt
7. Repeat for more frames
```

### Using Training Pipeline
```python
from training_pipeline import TrainingConfig, YOLOTrainingPipeline
from pathlib import Path

# Configure training
config = TrainingConfig(
    project_name="fire_detector_v1",
    epochs=100,
    batch_size=16,
    device="auto"  # Auto-detects CUDA/MPS/CPU
)

# Run training
pipeline = YOLOTrainingPipeline(config=config)
success, msg = pipeline.run_full_pipeline()

print(f"Training: {msg}")
# Output: Training completed. Model saved to models/yolo_versions/v1/
```

### Using Model Versioning
```python
from model_versioning import ModelVersionManager, IncrementalTrainingManager

# Check status
version_mgr = ModelVersionManager()
print(version_mgr.get_version_comparison())

# Output:
# 📊 MODEL VERSION HISTORY
# ================================================================================
# Version     Date                 Images       mAP50      Loss      
# ───────────────────────────────────────────────────────────────────────────
# v1          2025-12-20           1000         0.9200     0.0450    
# v2          2025-12-21           1100         0.9450     0.0380    
# ================================================================================
# 🎯 Current Best: models/yolo_versions/v2/weights/best.pt

# Check if retraining needed
training_mgr = IncrementalTrainingManager()
recommended, msg = training_mgr.suggest_retraining("v2", threshold=50)
print(msg)
# Output: "Recommended retraining: 120 new images (threshold: 50)"
```

---

## ❓ Data Flow Diagram

```
VIDEO FILE
    ↓
[annotation_tool.py]
    ↓ User draws boxes, saves
    ↓
annotations/fire_detection/
    ├── frame_00000.jpg  ← Actual image pixel data
    ├── frame_00000.txt  ← YOLO format: "0 0.45 0.67 0.30 0.25"
    ├── frame_00001.jpg
    ├── frame_00001.txt
    └── ...
    ↓
[training_pipeline.py]
    ├── Validates all .jpg + .txt pairs
    ├── Creates train/val/test splits (80/10/10)
    ├── Trains YOLOv8 model
    └── Generates training logs
    ↓
training_data/
    └── runs/detect/fire_detector_v1/
        ├── weights/
        │   ├── best.pt   ← Best model during training
        │   └── last.pt   ← Last checkpoint
        ├── results.csv
        └── confusion_matrix.png
    ↓
[model_versioning.py]
    ├── Copies best.pt to models/yolo_versions/v1/
    ├── Creates metadata.json with training details
    └── Sets current_best.pt symlink to v1
    ↓
models/yolo_versions/
    ├── v1/
    │   ├── weights/best.pt      ← First trained model
    │   └── metadata.json
    ├── v2/
    │   ├── weights/best.pt      ← Incremental update
    │   └── metadata.json
    └── current_best.pt ──→ v2/weights/best.pt  ← Production model
```

---

## 🎓 Key Commands Reference

```bash
# List all annotated frames
ls annotations/fire_detection/

# Check model versions
ls -la models/yolo_versions/

# Check which model is in production
ls -la models/yolo_versions/current_best.pt

# See training metadata for v2
cat models/yolo_versions/v2/metadata.json

# Compare v1 vs v2
diff models/yolo_versions/v1/metadata.json models/yolo_versions/v2/metadata.json
```

---

## 📋 Checklist

- [ ] **Annotate frames:** Use annotation tool to save 50+ frames with boxes
- [ ] **Prepare dataset:** Run `training_pipeline.py` to validate & split
- [ ] **Train v1:** Start first training (creates v1 model)
- [ ] **Add more data:** Annotate 50+ more frames
- [ ] **Train v2:** Retrain with new + old frames (incremental)
- [ ] **Compare:** Check metadata files to compare v1 vs v2
- [ ] **Deploy:** Use `current_best.pt` in production

