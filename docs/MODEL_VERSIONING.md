# EmberEye Model Versioning Guide

Complete guide to managing, versioning, and deploying trained models in EmberEye.

## Table of Contents

1. [Overview](#overview)
2. [Version Lifecycle](#version-lifecycle)
3. [Version Metadata](#version-metadata)
4. [Version Operations](#version-operations)
5. [Model Export](#model-export)
6. [Deployment Workflows](#deployment-workflows)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Overview

EmberEye's model versioning system provides:

- **Automatic Versioning**: Every training run creates a new version
- **Metadata Tracking**: Performance metrics, training parameters, timestamps
- **Version Control**: Activate, compare, and delete versions
- **Export Capabilities**: Convert to ONNX, TorchScript, CoreML, TFLite
- **Rollback Safety**: Switch between versions without losing models

### Version Storage Structure

```
models/
├── current_best.pt              # Active production model (symlink)
├── versions/
│   ├── v1/
│   │   ├── metadata.json       # Version metadata
│   │   └── weights/
│   │       ├── best.pt         # Best model from training
│   │       └── last.pt         # Final epoch model
│   ├── v2/
│   │   ├── metadata.json
│   │   └── weights/
│   │       ├── best.pt
│   │       └── last.pt
│   └── v3/
│       ├── metadata.json
│       └── weights/
│           ├── best.pt
│           └── last.pt
└── train/                       # Latest training artifacts
    ├── weights/
    └── results/
```

---

## Version Lifecycle

### 1. Creation (Automatic)

When training completes:

1. **Version number assigned**: Incremental (v1, v2, v3, ...)
2. **Metadata generated**: From training results and configuration
3. **Weights copied**: From `train/weights/best.pt` to `versions/vX/weights/`
4. **Metadata saved**: To `versions/vX/metadata.json`
5. **First version auto-activated**: v1 becomes `current_best.pt`

### 2. Storage

Each version maintains:

- **metadata.json**: Performance metrics and training config
- **weights/best.pt**: Best model from training (highest mAP)
- **weights/last.pt**: Final epoch model (optional)

### 3. Activation

Promoting a version to production:

1. Select version from list
2. Click "Activate Model"
3. System updates `current_best.pt` symlink
4. All inference uses activated model
5. UI shows ✓ indicator on active version

### 4. Deletion

Removing unused versions:

1. Select non-active version
2. Click "Delete Version"
3. Confirm deletion
4. Version directory permanently removed

**Safety**: Cannot delete active model.

---

## Version Metadata

### Metadata Structure

**metadata.json format:**
```json
{
  "version": "v3",
  "created_at": "2025-12-22T10:30:15.123456",
  "best_accuracy": 0.8945,
  "training_time_hours": 1.25,
  "epochs": 100,
  "batch_size": 16,
  "image_size": 640,
  "pretrained_model": "yolov8m.pt",
  "dataset": {
    "train_images": 150,
    "val_images": 30,
    "test_images": 20,
    "classes": ["fire", "smoke", "person"]
  },
  "metrics": {
    "map50": 0.8945,
    "map50_95": 0.7623,
    "precision": 0.9012,
    "recall": 0.8734
  }
}
```

### Key Fields

| Field | Description | Example |
|-------|-------------|---------|
| `version` | Version identifier | "v3" |
| `created_at` | Training completion timestamp | ISO 8601 format |
| `best_accuracy` | mAP50 score (0-1) | 0.8945 |
| `training_time_hours` | Total training duration | 1.25 |
| `epochs` | Training epochs | 100 |
| `batch_size` | Batch size used | 16 |
| `image_size` | Input image resolution | 640 |
| `pretrained_model` | Starting weights | "yolov8m.pt" |
| `map50` | mAP at IoU 50% | 0.8945 |
| `map50_95` | mAP averaged IoU 50-95% | 0.7623 |
| `precision` | Detection precision | 0.9012 |
| `recall` | Detection recall | 0.8734 |

### Metadata Usage

**In UI:**
```
v3 | mAP: 0.8945 | Time: 1.25h [ACTIVE]
```

**Programmatic Access:**
```python
from embereye.core.model_version_manager import ModelVersionManager

manager = ModelVersionManager()
metadata = manager.get_version_metadata("v3")
print(f"mAP: {metadata.best_accuracy}")
print(f"Classes: {metadata.dataset['classes']}")
```

---

## Version Operations

### Viewing Versions

**Model Versions List** (Training tab):
- Shows all versions with mAP and training time
- Active version marked with ✓
- Sorted by version number (newest first)

**Interpreting the List:**
```
✓ v5 | mAP: 0.9123 | Time: 2.15h [ACTIVE]  ← Production model
  v4 | mAP: 0.8945 | Time: 1.80h           ← Previous best
  v3 | mAP: 0.8521 | Time: 1.25h           ← Older version
  v2 | mAP: 0.7834 | Time: 0.98h           ← Initial training
  v1 | mAP: 0.0000 | Time: 0.00h           ← Placeholder
```

### Activating a Version

**Purpose**: Switch production model to different version

**Steps:**
1. Select version from list (click to highlight)
2. Click **"Activate Model"** button
3. Confirm activation in dialog
4. ✓ indicator moves to newly activated version

**Use Cases:**
- Roll back to previous model after poor performance
- A/B test different versions
- Deploy specialized model for specific scenario
- Recover from failed training

**Example Workflow:**
```
Training v6 → Poor results (mAP 0.65)
              ↓
Activate v5 → Restore production to known good model (mAP 0.91)
              ↓
Analyze v6 → Determine what went wrong
              ↓
Retrain v7 → With improved data/config
```

### Deleting a Version

**Purpose**: Remove unused or failed versions

**Steps:**
1. Select non-active version
2. Click **"Delete Version"** button
3. Confirm deletion (permanent)
4. Version removed from list and storage

**Restrictions:**
- ❌ Cannot delete active version
- ❌ No undo after deletion
- ✅ Must activate different version first

**When to Delete:**
- Failed training runs (mAP < 0.50)
- Experimental versions no longer needed
- Disk space management
- Organizational cleanup

**Storage Impact:**
- Each version: ~10-50 MB (depending on model size)
- Delete regularly to free disk space

### Comparing Versions

**Manual Comparison:**
1. Note mAP values in list
2. Test each version in Sandbox
3. Compare detection results
4. Review metadata for differences

**Metrics to Compare:**
- **mAP50**: Overall accuracy (higher is better)
- **Training Time**: Efficiency (lower is faster)
- **FPS in Sandbox**: Inference speed
- **False Positive Rate**: Incorrect detections

**Decision Matrix:**

| Scenario | Choose Version With |
|----------|---------------------|
| Best accuracy | Highest mAP50 |
| Fastest inference | Smallest model, highest FPS |
| Balanced | High mAP, low training time |
| Specialized | Trained on domain-specific data |

---

## Model Export

### Export Formats

EmberEye supports exporting models to multiple deployment formats:

| Format | Extension | Use Case | Platform |
|--------|-----------|----------|----------|
| **ONNX** | .onnx | Universal deployment | All platforms |
| **TorchScript** | .pt | PyTorch inference | Python, C++ |
| **CoreML** | .mlmodel | Apple devices | iOS, macOS |
| **TFLite** | .tflite | Mobile/edge devices | Android, embedded |

### Export Process

**Access Export:**
- Settings Menu (⚙️) → **📦 Export Model** → Select format

**Steps:**
1. Click Settings (top-right gear icon)
2. Hover over "📦 Export Model"
3. Select format:
   - Export to ONNX
   - Export to TorchScript
   - Export to CoreML
   - Export to TFLite
4. Choose save location in file dialog
5. Wait for export to complete (progress dialog)
6. Exported file ready for deployment

**Export Settings:**
- **Image Size**: 640 (default, matches training)
- **Dynamic Shapes**: Enabled for ONNX
- **Optimization**: FP16 for faster inference

### ONNX Export

**Advantages:**
- Platform-agnostic (CPU, GPU, mobile)
- Optimized inference engines (ONNX Runtime)
- Wide framework support

**Usage:**
```python
import onnxruntime as ort

session = ort.InferenceSession("EmberEye_v3.onnx")
input_name = session.get_inputs()[0].name
outputs = session.run(None, {input_name: image})
```

**Deployment:**
- Cloud: AWS, Azure, GCP
- Edge: NVIDIA Jetson, Intel NCS
- Mobile: ONNX Runtime Mobile

### TorchScript Export

**Advantages:**
- Native PyTorch format
- C++ deployment (no Python runtime)
- Fastest inference on PyTorch

**Usage:**
```python
import torch

model = torch.jit.load("EmberEye_v3.pt")
model.eval()
with torch.no_grad():
    output = model(image_tensor)
```

**Deployment:**
- Server applications
- C++ embedded systems
- LibTorch integration

### CoreML Export

**Advantages:**
- Optimized for Apple Silicon (M1/M2/M3)
- Native iOS/macOS integration
- Metal GPU acceleration

**Usage (Swift):**
```swift
let model = try EmberEye_v3()
let input = EmberEye_v3Input(image: pixelBuffer)
let output = try model.prediction(input: input)
```

**Deployment:**
- iOS apps (iPhone, iPad)
- macOS applications
- Apple Watch (limited)

### TFLite Export

**Advantages:**
- Lightweight (smallest file size)
- Android optimization
- Embedded device support

**Usage (Python):**
```python
import tensorflow as tf

interpreter = tf.lite.Interpreter(model_path="EmberEye_v3.tflite")
interpreter.allocate_tensors()
# ... inference ...
```

**Deployment:**
- Android apps
- Raspberry Pi
- Microcontrollers (ESP32, etc.)

---

## Deployment Workflows

### Development Workflow

```
Train → Test in Sandbox → Activate → Export → Deploy
```

1. **Train**: Create new version with updated data
2. **Test**: Validate accuracy and performance in Sandbox
3. **Activate**: Promote to production if satisfactory
4. **Export**: Convert to deployment format
5. **Deploy**: Integrate into target platform

### Production Deployment

**Pre-Deployment Checklist:**
- [ ] Model mAP > 0.80 (or target threshold)
- [ ] Tested on diverse inputs in Sandbox
- [ ] FPS meets real-time requirements (>15 for video)
- [ ] Exported to appropriate format
- [ ] Version metadata documented
- [ ] Rollback plan prepared (previous version ready)

**Deployment Steps:**

1. **Export Model**:
   ```bash
   # Via UI: Settings → Export Model → ONNX
   # Or programmatically:
   yolo export model=models/current_best.pt format=onnx
   ```

2. **Transfer to Deployment Environment**:
   ```bash
   scp EmberEye_v3.onnx user@server:/app/models/
   ```

3. **Update Configuration**:
   ```yaml
   model:
     path: /app/models/EmberEye_v3.onnx
     version: v3
     confidence: 0.25
     iou: 0.45
   ```

4. **Test in Production** (staging first):
   - Run inference on sample data
   - Verify detection accuracy
   - Measure performance (FPS, latency)
   - Check memory usage

5. **Monitor**:
   - Log detection results
   - Track false positives/negatives
   - Monitor inference time
   - Alert on anomalies

### Rollback Procedure

**When to Rollback:**
- New version performs worse than expected
- Increased false positive rate
- Performance degradation (slow FPS)
- Deployment issues

**Steps:**
1. Identify last known good version (e.g., v4)
2. In EmberEye: Activate v4
3. Re-export model
4. Re-deploy to production
5. Verify restoration of expected behavior

**Prevention:**
- Always keep previous version available
- Test thoroughly in Sandbox before deploy
- Use canary deployments (gradual rollout)
- Monitor metrics continuously

### Edge Deployment

**Raspberry Pi / Jetson Nano:**
1. Export to TFLite or ONNX
2. Use smaller model (yolov8n/s)
3. Optimize for FP16 or INT8
4. Test thermal throttling

**Mobile Devices:**
1. Export to CoreML (iOS) or TFLite (Android)
2. Quantize to INT8 for size/speed
3. Test battery impact
4. Handle orientation changes

**Cloud Services:**
1. Export to ONNX for flexibility
2. Use containerization (Docker)
3. Scale horizontally with load balancers
4. Monitor costs and latency

---

## Best Practices

### Version Management

✅ **Do:**
- Keep at least 2-3 recent versions
- Document version changes in metadata
- Test thoroughly before activating
- Export versions before deletion
- Use semantic naming for exports (EmberEye_v3_production.onnx)

❌ **Don't:**
- Delete all versions except active
- Activate untested versions in production
- Skip Sandbox validation
- Deploy without rollback plan
- Ignore performance metrics

### Metadata Hygiene

**Record Important Details:**
- Training dataset size and composition
- Special configurations or hyperparameters
- Known issues or limitations
- Intended use case or deployment target

**Example Extended Metadata:**
```json
{
  "version": "v5",
  "notes": "Trained on night-time images, improved low-light detection",
  "limitations": "May have false positives in reflective surfaces",
  "deployment_target": "Jetson Nano, TFLite format",
  "reviewed_by": "QA Team",
  "approved_for_production": true
}
```

### Export Strategy

**Development:**
- Export to PyTorch (.pt) for quick testing
- Use CPU-compatible formats

**Production:**
- Export to ONNX for maximum compatibility
- Test exported model before deployment
- Keep original .pt files as backup

**Optimization:**
- Use FP16 quantization for 2x speed
- Use INT8 for 4x speed (slight accuracy loss)
- Profile exported model on target hardware

### Version Naming Conventions

**Internal Versions:**
```
v1, v2, v3, ...  (automatic)
```

**Export Naming:**
```
EmberEye_v3_production_20251222.onnx
EmberEye_v3_jetson_fp16.tflite
EmberEye_v3_ios_coreml.mlmodel
```

**Include:**
- Project name (EmberEye)
- Version number (v3)
- Environment (production, staging)
- Date (YYYYMMDD)
- Platform/optimization (jetson, fp16)

---

## Troubleshooting

### Version List Issues

**Symptom**: Version list empty or shows only v1/v2

**Causes:**
- No successful training runs
- Metadata files corrupted
- Wrong models directory

**Solutions:**
1. Complete at least one training session
2. Check `models/versions/` directory exists
3. Verify metadata.json files are valid JSON
4. Restart application to refresh list

### Activation Failures

**Symptom**: "Activate Model" button doesn't work

**Causes:**
- Version weights missing (best.pt not found)
- Permissions issue (can't update symlink)
- Corrupted version directory

**Solutions:**
1. Verify `versions/vX/weights/best.pt` exists
2. Check file permissions on models directory
3. Re-run training to recreate version
4. Use file manager to manually check structure

### Export Errors

**Symptom**: Export fails with error message

**Common Errors:**

1. **"Model not found"**
   - Cause: current_best.pt doesn't exist
   - Solution: Activate a version first

2. **"ONNX export failed"**
   - Cause: Incompatible operator
   - Solution: Update ultralytics: `pip install -U ultralytics`

3. **"CoreML requires Mac"**
   - Cause: CoreML export only works on macOS
   - Solution: Use ONNX or TorchScript instead

4. **"Out of memory"**
   - Cause: Large model, insufficient RAM
   - Solution: Export on machine with more memory

### Deployment Issues

**Symptom**: Exported model doesn't work on target platform

**ONNX Issues:**
```python
# Test exported model locally
import onnxruntime as ort
session = ort.InferenceSession("EmberEye_v3.onnx")
print("ONNX model loaded successfully")
```

**TFLite Issues:**
```python
# Verify TFLite model
import tensorflow as tf
interpreter = tf.lite.Interpreter(model_path="EmberEye_v3.tflite")
interpreter.allocate_tensors()
print("TFLite model loaded successfully")
```

**Performance Issues:**
- Check model size (yolov8n vs yolov8l)
- Verify hardware acceleration (GPU, NPU)
- Use quantization (FP16/INT8)
- Reduce input image size

---

## Advanced Topics

### Programmatic Version Management

```python
from embereye.core.model_version_manager import ModelVersionManager, ModelMetadata

manager = ModelVersionManager()

# Create new version
metadata = ModelMetadata(
    version="v10",
    best_accuracy=0.92,
    training_time_hours=2.5,
    epochs=150,
    batch_size=16
)
manager.create_version(metadata, weights_dir="models/train/weights")

# List all versions
versions = manager.list_versions()
print(f"Available versions: {versions}")

# Get metadata
meta = manager.get_version_metadata("v10")
print(f"mAP: {meta.best_accuracy}")

# Activate version
success, message = manager.promote_to_best("v10")
if success:
    print("Version v10 activated")

# Delete version
manager.delete_version("v5")
```

### Custom Export Scripts

```python
from ultralytics import YOLO

# Load model
model = YOLO("models/current_best.pt")

# Export with custom settings
model.export(
    format="onnx",
    imgsz=640,
    half=True,  # FP16 quantization
    dynamic=True,  # Dynamic batch size
    simplify=True,  # Simplify ONNX graph
    opset=12  # ONNX opset version
)

# Export multiple formats
for fmt in ["onnx", "torchscript", "tflite"]:
    model.export(format=fmt, imgsz=640)
    print(f"Exported to {fmt}")
```

### Batch Export Workflow

```bash
#!/bin/bash
# Export active model to all formats

VERSION=$(cat models/current_best_version.txt)
OUTPUT_DIR="exports/${VERSION}"
mkdir -p "${OUTPUT_DIR}"

# Export each format
python -c "from ultralytics import YOLO; \
           m = YOLO('models/current_best.pt'); \
           m.export(format='onnx', imgsz=640)" && \
    mv models/*.onnx "${OUTPUT_DIR}/"

python -c "from ultralytics import YOLO; \
           m = YOLO('models/current_best.pt'); \
           m.export(format='tflite', imgsz=640)" && \
    mv models/*.tflite "${OUTPUT_DIR}/"

echo "Exported ${VERSION} to ${OUTPUT_DIR}"
```

---

## Quick Reference

### Version Operations Cheat Sheet

| Operation | UI Path | Safety |
|-----------|---------|--------|
| View Versions | Training Tab → Model Versions | Read-only |
| Activate | Select version → Activate Model | Reversible |
| Delete | Select version → Delete Version | Permanent |
| Export | Settings → 📦 Export Model | Safe |

### Metadata Quick Check

```bash
# View metadata for version v3
cat models/versions/v3/metadata.json | python -m json.tool

# Extract mAP
cat models/versions/v3/metadata.json | grep "best_accuracy"

# List all versions with mAP
for v in models/versions/v*/; do
    echo -n "$(basename $v): "
    cat "$v/metadata.json" | grep "best_accuracy" | cut -d: -f2
done
```

### Export Commands

```bash
# ONNX export (universal)
yolo export model=models/current_best.pt format=onnx imgsz=640

# TFLite export (mobile)
yolo export model=models/current_best.pt format=tflite imgsz=640 int8=True

# TorchScript export (PyTorch)
yolo export model=models/current_best.pt format=torchscript imgsz=640

# CoreML export (iOS, macOS only)
yolo export model=models/current_best.pt format=coreml imgsz=640
```

---

## Additional Resources

- **Training Guide**: [TRAINING_GUIDE.md](TRAINING_GUIDE.md)
- **YOLOv8 Export Docs**: https://docs.ultralytics.com/modes/export/
- **ONNX Runtime**: https://onnxruntime.ai/
- **TensorFlow Lite**: https://www.tensorflow.org/lite

---

**Last Updated**: December 22, 2025  
**Version**: 1.0  
**Author**: EmberEye Team
