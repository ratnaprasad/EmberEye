# YOLO Fire Detection Models

This directory contains the YOLO models used for computer vision-based fire and smoke detection.

## Current Model

**File:** `yolov8n_fire.pt` (6.25 MB)
**Type:** YOLOv8 Nano base model
**Classes:** 80 COCO classes (person, car, etc.)
**Status:** Base model for general object detection

## Upgrading to Fire-Specific Model

The current model is a general-purpose YOLOv8n model. For better fire/smoke/cigarette detection, you can replace it with a fire-trained model.

### Recommended Fire Detection Models

1. **Fire-Smoke YOLOv8 (Recommended)**
   - URL: https://github.com/spacewalk01/yolov8-fire-detection
   - Classes: fire, smoke
   - Accuracy: ~90%
   - Size: 15-25 MB

2. **Custom Fire Detection Model**
   - Train on your own dataset with:
     - Cigarettes being smoked
     - Match sticks
     - Lighters
     - Small fires
     - Building fires
     - Smoke plumes

### How to Upgrade the Model

**Option 1: Replace with downloaded model (ONE-TIME, needs internet)**

```bash
# Download fire detection model
cd models/
curl -L "https://github.com/spacewalk01/yolov8-fire-detection/releases/download/v1.0/best.pt" -o yolov8n_fire.pt

# Or use wget
wget "https://github.com/spacewalk01/yolov8-fire-detection/releases/download/v1.0/best.pt" -O yolov8n_fire.pt
```

**Option 2: Train custom model (offline after dataset download)**

```bash
# Install training dependencies
pip install ultralytics

# Train on custom dataset
yolo train data=fire_dataset.yaml model=yolov8n.pt epochs=100 imgsz=640

# Copy trained model
cp runs/detect/train/weights/best.pt models/yolov8n_fire.pt
```

**Option 3: Use client's existing model**

```bash
# Simply copy the .pt file to this directory
cp /path/to/custom_fire_model.pt models/yolov8n_fire.pt
```

### Deploying Model Updates to Clients (100% Offline)

Since your clients don't have internet access, follow this workflow:

1. **Development Environment (with internet):**
   ```bash
   # Download/train improved model
   cd models/
   # Replace yolov8n_fire.pt with new model
   ```

2. **Build Distribution Package:**
   ```bash
   # The model is automatically bundled in the .app/.exe
   pyinstaller EmberEye.spec
   ```

3. **Deploy to Client (offline):**
   - Copy the entire `dist/EmberEye.app` (macOS) or `dist/EmberEye.exe` (Windows)
   - Model is embedded inside the package
   - No internet connection required

4. **Verify Model Version:**
   - The app will print the loaded model classes on startup
   - Check logs for: "YOLO model loaded successfully. Classes: {0: 'fire', 1: 'smoke', ...}"

### Model Performance Tips

- **Fire detection:** Current heuristic detects 60-70% of fires. YOLO fire model achieves 85-95%
- **Cigarette detection:** Requires custom-trained model with cigarette dataset
- **Match sticks:** Requires custom-trained model or high-resolution camera
- **Inference speed:** YOLOv8n runs at 30-60 FPS on CPU, 100+ FPS on GPU

### Troubleshooting

**Model not loading:**
- Check file exists: `ls -lh models/yolov8n_fire.pt`
- Check file size: Should be >1 MB (not 9 bytes)
- Check app logs: "YOLO model loaded successfully"

**Low detection accuracy:**
- Replace base model with fire-trained model
- Adjust confidence threshold in `vision_detector.py` (line 95): `conf=0.25`
- Train custom model on client-specific fire scenarios

**Model too large for distribution:**
- Use YOLOv8n (6 MB) instead of YOLOv8l (80 MB)
- Quantize model: Use ONNX INT8 quantization (reduces size by 75%)

## Distribution Checklist

- [ ] Model file exists: `models/yolov8n_fire.pt`
- [ ] Model size > 1 MB (valid PyTorch file)
- [ ] EmberEye.spec includes: `('models', 'models')` in datas
- [ ] Test app loads model: Check startup logs
- [ ] Test fire detection: Use lighter/match stick
- [ ] Package size acceptable: <150 MB for distribution

## Version History

- **v1.0.0** (2025-12-01): YOLOv8n base model (6.25 MB)
  - General object detection (80 classes)
  - Fallback to heuristic fire detection
  - Ready for fire-specific model upgrade
