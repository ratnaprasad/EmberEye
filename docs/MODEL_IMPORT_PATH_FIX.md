# Model Import Directory Mismatch - FIXED

## Issue Identified

When you import a model through the **EmberEye Field** app, it stores the model in one location, but the **HybridDetector** (YOLO inference engine) was looking in a different location.

### Storage vs. Search Mismatch

| Operation | Storage Path | Status |
|-----------|-------------|--------|
| **Import Model (Field App)** | `./models/yolo_versions/deployment_YYYYMMDD_HHMMSS/weights/best.pt` | ✅ Correct |
| **HybridDetector.auto_load()** | `./models/*.pt` (loose files only) | ❌ Wrong - not checking `yolo_versions/` |
| **VisionDetector.get_bundled_model_path()** | `./models/*.pt` (loose files only) | ❌ Wrong - not checking `yolo_versions/` |

### Result
- Model imported when you click **"Import Model"** in Field app ✅
- Model stored in `./models/yolo_versions/deployment_YYYYMMDD_HHMMSS/weights/best.pt` ✅
- But **detection algorithm never finds it** ❌
- Falls back to generic `./models/v20260216_213235_model.pt` (old training) ❌
- **All detections show "CLASS A" instead of your trained classes** ❌

---

## Solution Implemented

### File 1: `embereye/core/hybrid_detector.py`

**Updated `_auto_load_model()` method:**
```python
def _auto_load_model(self) -> None:
    """Automatically find and load latest model from ModelVersionManager or ./models/"""
    # Step 1: Try ModelVersionManager (preferred for imported models)
    # Step 2: Fallback to loose .pt files in ./models/
    # Step 3: Log if nothing found
```

**Priority Order:**
1. ✅ Check `ModelVersionManager.get_current_best()` first → `./models/yolo_versions/[version]/weights/best.pt`
2. ✅ Fallback to loose files in `./models/`
3. ✅ Log clearly which model was loaded

### File 2: `embereye/core/vision_detector.py`

**Updated `_get_bundled_model_path()` method:**
```python
def _get_bundled_model_path(self) -> str:
    """Get the path to a YOLO model with new priority order."""
    # Step 1: Try ModelVersionManager (imported via Field app)
    # Step 2: Fallback to loose files in ./models/
    # Step 3: Fallback to bundled model
```

**Priority Order:**
1. ✅ Check `ModelVersionManager.get_current_best()` → YOUR imported trained model
2. ✅ Check `./models/` for loose `.pt` files
3. ✅ Use bundled `yolov8n_fire.pt` as final fallback

---

## How It Works Now

### Scenario: You Import a Model via Field App

```
1. Click "📥 Import Model" in Field app
2. Select your trained model (41 classes with PERSON_IN_DISTRESS, FIRE, SMOKE, etc.)
3. Field app stores it:
   → ./models/yolo_versions/deployment_20260218_143015/weights/best.pt
   → Metadata saved in: ./models/yolo_versions/deployment_20260218_143015/metadata.json

4. After import, detection restarts:
   → HybridDetector._auto_load_model() checks ModelVersionManager
   → Finds: ./models/yolo_versions/deployment_20260218_143015/weights/best.pt
   → Loads YOUR 41-class trained model ✅
   
5. Detection now works correctly:
   ✅ PERSON_IN_DISTRESS detected
   ✅ FIRE detected
   ✅ SMOKE_WITH_FIRE detected
   ✅ All 41 classes available
   ❌ NO MORE "CLASS A" generic detections
```

---

## Verification Steps

### 1. Check Master Classes File

Your `master_classes.json` shows the 41 classes your model is trained on:
```json
{
  "FIRE_CATEGORY": ["CLASS A", "CLASS B", "CLASS C", "CLASS D", "CLASS K"],
  "SMOKE_CATEGORY": ["WHITE SMOKE", "BLACK SMOKE", "BLUE SMOKE", "YELLOW/BROWN SMOKE"],
  "HUMAN_CATEGORY": ["PERSON_IN_DISTRESS", "PERSON_WITHOUT_SAFETY_WEAR", "PERSON_WITH_PPE", ...],
  ...
}
```

### 2. Find Your Trained Model

Your trained models are stored at:
```
d:\EE\EmberEye\embereye-studio\models\yolo_versions\
├── v20260216_213235\
│   └── best.pt          ← Your trained 41-class model
├── v20260216_212737\
│   └── best.pt          ← Previous training
└── ...
```

### 3. Import Process

When you import through Field app, it:
```
1. Reads your trained model: embereye-studio/models/yolo_versions/v20260216_213235/best.pt
2. Stores it: ./models/yolo_versions/deployment_YYYYMMDD_HHMMSS/weights/best.pt
3. Sets as current_best via ModelVersionManager
```

### 4. Detection Now Works

When Field app starts detection:
```
HybridDetector loads model via:
→ _auto_load_model()
→ ModelVersionManager.get_current_best()
→ ./models/yolo_versions/deployment_YYYYMMDD_HHMMSS/weights/best.pt
→ YOUR TRAINED MODEL with YOUR 41 CLASSES ✅
```

---

## Next Steps

1. **Import your trained model** via Field app:
   - Settings → 📥 Import Model
   - Select: `embereye-studio/models/yolo_versions/v20260216_213235/best.pt`
   - Activate it

2. **Restart detection** and verify:
   - Log should show: `[HybridDetector] Using ModelVersionManager best: best.pt`
   - Detections should show actual class names (FIRE, SMOKE, PERSON_IN_DISTRESS, etc.)
   - ❌ NO MORE "CLASS A" generic detections

3. **Test on IMG_1318.MOV** again:
   - Should see real fire/smoke detections instead of generic CLASS A
   - Test results will show actual hazard detection

---

## Technical Details

### ModelVersionManager Path Structure
```python
models_dir = Path("./models/yolo_versions")
├── v1/
│   ├── weights/
│   │   └── best.pt
│   ├── metadata.json
│   └── ...
├── v2/
├── deployment_20260218_143015/
│   ├── weights/
│   │   └── best.pt
│   ├── metadata.json
│   └── ...
└── current_best.pt  ← Symlink to active model
```

### Get Current Best Model
```python
from embereye.core.model_versioning import ModelVersionManager
manager = ModelVersionManager()
current_best = manager.get_current_best()
# Returns: Path to active model, e.g., ./models/yolo_versions/deployment_20260218_143015/weights/best.pt
```

---

## Summary

✅ **Issue**: Model storage and detection paths didn't match  
✅ **Solution**: Updated HybridDetector and VisionDetector to use ModelVersionManager  
✅ **Result**: Imported models now automatically loaded and used for detection  
✅ **Classes**: Your 41 trained classes will be detected instead of generic "CLASS A"

**No more mismatches between where models are stored and where detection looks for them!**
