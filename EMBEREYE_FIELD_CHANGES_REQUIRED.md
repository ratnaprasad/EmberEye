# EmberEye Field App - Required Changes

**Document Purpose:** Clear communication of all changes needed in the embereye-field application to support the class configuration centralization.

**Date:** February 18, 2026  
**Status:** Action Required

---

## 📋 Summary of Changes

The embereye-field app needs **4 key updates** to work seamlessly with the new centralized class configuration system:

1. ✅ **Use Central Class Configuration** (embereye/core/class_config.py)
2. ✅ **Add Model Import Class Hash Validation**
3. ✅ **Update Model Loading to Use Central Classes**
4. ✅ **Fix Import Paths for Central Modules**

---

## 1️⃣ USE CENTRAL CLASS CONFIGURATION

### What To Do
Replace all imports of the old `master_class_config` with the new central module.

### Current (Broken)
```python
from master_class_config import load_master_classes, flatten_classes
```

### Updated (Correct)
```python
from embereye.core.class_config import load_master_classes, get_leaf_classes, get_classes_hash
```

### Where To Apply
- [ ] `embereye-field/fieldglass/main_window.py` - Search for `master_class_config` imports
- [ ] `embereye-field/main.py` - If it imports class configuration
- [ ] Any file that loads classes for detection or settings

### Why
The old `master_class_config.py` was duplicated across the codebase. The new central module at `embereye/core/class_config.py` is the **single source of truth** for all class operations.

---

## 2️⃣ ADD MODEL IMPORT CLASS HASH VALIDATION

### What To Do
When user imports a model in Field app, validate that the model's class configuration matches the current system.

### Where To Add
**File:** `embereye-field/fieldglass/main_window.py`  
**Method:** `_execute_model_import()` or similar import handler  
**Location:** After model is copied, before showing success message

### Code to Add

```python
# Validate class hash if metadata includes it
try:
    from embereye.core.class_config import load_master_classes, get_classes_hash, get_leaf_classes
    import zipfile
    import json
    
    # Check if imported model had class hash in its metadata
    class_hash_warning = ""
    
    if model_path.suffix.lower() == '.zip':
        try:
            with zipfile.ZipFile(str(model_path), 'r') as zipf:
                if 'metadata.json' in zipf.namelist():
                    with zipf.open('metadata.json') as f:
                        imported_meta = json.load(f)
                        imported_hash = imported_meta.get('class_hash')
                        
                        if imported_hash:
                            current_classes = load_master_classes()
                            current_hash = get_classes_hash(get_leaf_classes(current_classes))
                            
                            if imported_hash != current_hash:
                                class_hash_warning = (
                                    f"\n\n⚠️ CLASS CONFIGURATION MISMATCH:\n"
                                    f"Model trained with {imported_meta.get('class_count', '?')} classes\n"
                                    f"Current system has {len(get_leaf_classes(current_classes))} classes\n\n"
                                    f"Detection labels may be incorrect. "
                                    f"Consider updating master_classes.json."
                                )
        except Exception as e:
            logger.debug(f"Could not read class hash from ZIP: {e}")

except Exception as e:
    logger.debug(f"Class hash validation skipped: {e}")
    class_hash_warning = ""

# Then show success message with warning if applicable
QMessageBox.information(
    self,
    "Import Successful",
    f"✓ Model imported and activated!\n\n"
    f"Model: {model_path.name}\n"
    f"Version: {version_name}\n\n"
    f"The model is now active for all video streams."
    + class_hash_warning  # Add warning here
)
```

### Why
When a model is trained (exported from Studio) with a specific set of classes, that class configuration is saved as a "fingerprint" (class_hash). If the Field app has different classes, the detection labels will be wrong. This validates the match and warns the user.

---

## 3️⃣ UPDATE MODEL LOADING TO USE CENTRAL CLASSES

### What To Do
When loading a model for detection, use the central class configuration to map class IDs to names.

### Where To Update
- [ ] `embereye/core/vision_detector.py` - If it loads class names
- [ ] `embereye/core/hybrid_detector.py` - If it loads class names
- [ ] Any detection inference method that displays class labels

### Current Pattern (Old)
```python
# Hardcoded or loaded from scattered file
class_names = ["CLASS A", "CLASS B", ...]  # Wrong order/duplication
```

### Updated Pattern (New)
```python
from embereye.core.class_config import load_master_classes, get_leaf_classes

classes = load_master_classes()
class_names = get_leaf_classes(classes)  # Always 41 classes, correct order
```

### Why
Ensures all detections use the same class name mapping as the model was trained with. Prevents "CLASS A" generic labels when proper class name should be used.

---

## 4️⃣ FIX IMPORT PATHS FOR CENTRAL MODULES

### What To Do
Ensure all imports use the correct paths for the new central modules.

### Files To Check
```
embereye-field/
├── main.py
├── fieldglass/
│   ├── main_window.py
│   ├── model_manager.py
│   └── any other files using classes
└── any other Python files
```

### Search For & Replace
In **every Python file** in embereye-field, search for:
- `from master_class_config import` → Replace with `from embereye.core.class_config import`
- Old class loading → Update to use `get_leaf_classes()` from central module

### Verification Command
```bash
# Run this to find any remaining old imports
grep -r "master_class_config" embereye-field/
grep -r "from master_class_config" embereye-field/

# Should return: 0 results (no old imports)
```

---

## 📁 FILE-BY-FILE CHECKLIST

### High Priority (Critical)
- [ ] `embereye-field/fieldglass/main_window.py`
  - [ ] Replace `master_class_config` imports
  - [ ] Add class_hash validation in model import method
  - [ ] Update model loading to use central classes

- [ ] `embereye/core/vision_detector.py`
  - [ ] Use `get_leaf_classes()` for class name mapping

- [ ] `embereye/core/hybrid_detector.py`
  - [ ] Use `get_leaf_classes()` for class name mapping

### Medium Priority (Important)
- [ ] `embereye-field/main.py`
  - [ ] Remove any `master_class_config` imports
  - [ ] Use central module if loading classes

- [ ] `embereye-field/fieldglass/model_manager.py` (if exists)
  - [ ] Update class configuration loading
  - [ ] Use central module

### Low Priority (Nice to Have)
- [ ] Any UI dialogs showing class lists
  - [ ] Verify they use `get_leaf_classes()`
  - [ ] Test with 41 classes displayed

---

## 🧪 TESTING CHECKLIST

### Test 1: Import Works Without Errors
```bash
cd embereye-field
python main.py
# Should load without "ImportError" or "ModuleNotFoundError"
# Should not show "cannot import from master_class_config"
```

### Test 2: Model Import Shows Class Hash Warning
```bash
1. Launch embereye-field
2. Go to Settings → Import Model
3. Select a model ZIP file
4. If class_hash differs:
   ✓ Should show warning: "⚠️ CLASS CONFIGURATION MISMATCH"
   ✓ Should still import successfully
5. If class_hash matches:
   ✓ Should show success without warning
```

### Test 3: Detection Shows Proper Class Labels
```bash
1. Load a video with people in it
2. Run detection
3. Check detected boxes:
   ✓ Person boxes → Should show person class (not "CLASS A")
   ✓ Fire boxes → Should show fire class
   ✓ All boxes → Should show actual class names
```

### Test 4: Central Config Used Everywhere
```bash
cd embereye-field
python -c "
from embereye.core.class_config import get_leaf_classes, load_master_classes
classes = load_master_classes()
leaf = get_leaf_classes(classes)
print(f'Classes available: {len(leaf)}')
print(f'First 5: {leaf[:5]}')
# Should print 41 classes
"
```

---

## 📝 DETAILED CHANGES MAP

### main_window.py Methods to Update
```
_execute_model_import()
  └─ ADD: class_hash validation (code provided above)

_load_active_model()
  └─ UPDATE: Use get_leaf_classes() instead of old master_class_config

_refresh_model_list()
  └─ UPDATE: Import paths if using class config
```

### vision_detector.py Methods to Update
```
__init__()
  └─ UPDATE: Load classes from central module

_load_model()
  └─ UPDATE: Ensure class_names from get_leaf_classes()

_run_inference()
  └─ VERIFY: Uses correct class names (should be automatic)
```

### hybrid_detector.py Methods to Update
```
__init__()
  └─ UPDATE: Load classes from central module

_auto_load_model()
  └─ UPDATE: Use central classes

run()
  └─ VERIFY: Detection labels use correct class names
```

---

## 🔍 VALIDATION COMMANDS

### Command 1: Check for old imports
```powershell
cd 'd:\EE\EmberEye\embereye-field'
grep -r "from master_class_config" .
# Expected: 0 results (clean)
```

### Command 2: Check central module is importable
```powershell
cd 'd:\EE\EmberEye\embereye-field'
& "D:\EE\EmberEye\.venv\Scripts\python.exe" -c "
from embereye.core.class_config import get_leaf_classes, load_master_classes
classes = load_master_classes()
leaf = get_leaf_classes(classes)
print(f'✓ Central module works: {len(leaf)} classes')
"
# Expected: "✓ Central module works: 41 classes"
```

### Command 3: Check app starts without errors
```powershell
cd 'd:\EE\EmberEye\embereye-field'
& "D:\EE\EmberEye\.venv\Scripts\python.exe" main.py
# Expected: App launches, no ImportError or AttributeError
```

---

## 💡 KEY POINTS TO REMEMBER

1. **Central Module Location:** `embereye/core/class_config.py`
   - Use this for all class operations
   - Always 41 leaf classes in correct order

2. **Function to Use:** `get_leaf_classes(classes_dict)`
   - Returns list of 41 class names in order
   - Use for: display, inference, labels

3. **Class Hash Validation:** Only on model import
   - Extract from ZIP metadata.json
   - Compare with current system
   - Show warning if different (don't block import)

4. **Backward Compatibility:** Old imports via shims
   - `master_class_config.py` (root) still works
   - But using central module is preferred
   - New code should use `from embereye.core.class_config`

5. **Testing:** Must verify detection labels
   - Check person boxes don't show "CLASS A"
   - Check all 41 classes available
   - Check class_hash warning on mismatched import

---

## 📋 SUMMARY OF IMPACT

| What | Before | After |
|------|--------|-------|
| **Class Config Location** | 3 duplicate files | 1 central file ✅ |
| **Detection Labels** | "CLASS A" generic | Proper class names ✅ |
| **Import Validation** | None | Hash validation ✅ |
| **Backward Compat** | N/A | Via shims ✅ |
| **Code Duplication** | High (3 copies) | None (1 source) ✅ |

---

## Next Steps

1. ✅ Review this document
2. ✅ Implement changes using checklist above
3. ✅ Run validation commands
4. ✅ Test detection labels in Field app
5. ✅ Ask clarifying questions if needed

---

## Questions?

- **"Where exactly do I add the class_hash validation?"**  
  → In the method that imports models (usually `_execute_model_import()` or similar)

- **"How do I know if classes are loaded correctly?"**  
  → Run validation command: should print "41 classes"

- **"Will this break existing models?"**  
  → No. Backward compatibility via shims. Models work as before.

- **"What if user doesn't have class_hash in old models?"**  
  → Validation gracefully handles missing hash (no warning, continues)

---

**Document Created:** 2026-02-18  
**Ready for:** Team Communication & Implementation  
**Status:** Ready to Share ✅
