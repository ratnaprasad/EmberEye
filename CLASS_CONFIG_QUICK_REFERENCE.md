# Quick Reference - Class Configuration Centralization

## What Was Fixed

**Problem:** People were being detected as "CLASS A" instead of proper person classes in Studio Sandbox and Field app.

**Root Cause:** Training annotations mislabeled - person boxes marked as class_id 0 instead of class_id 14.

**Solution:** Centralized class configuration + multi-layer safeguards.

---

## Key Changes at a Glance

### Central Module
- **File:** `embereye/core/class_config.py`
- **Purpose:** Single source of truth for all class operations
- **Key Functions:** `load_master_classes()`, `flatten_classes()`, `get_classes_hash()`

### Central Config
- **File:** `embereye/config/master_classes.json`
- **Purpose:** Persistent storage of 41-class hierarchy
- **Format:** JSON with IncidentEnvironment → Category → Leaf classes

### Import Rewiring
- **Changed:** All imports from scattered `master_class_config.py` files
- **To:** Centralized `embereye.core.class_config`
- **Locations:** 19 files updated, backward-compatible shims created

### Annotation Safeguarding
- **File:** `embereye-studio/annotation_tab.py`
- **What:** Per-media labels.txt + class hash validation
- **When:** On load (detect class drift), on save (persist mapping)
- **Files Added:** `labels.txt` + `labels_meta.json` per media folder

### Model Versioning
- **Export:** Class count + class_hash added to metadata.json
- **Import:** Validation warns if model trained with different class set
- **User Experience:** Informational warning, import continues

---

## How to Use

### For Studio Users (Training)

1. **Annotate frames** (class list locked by labels.txt from first annotation)
2. **Train model** (uses central class config)
3. **Export model** (ZIP includes class_hash for traceability)

### For Field Users (Deployment)

1. **Import model** (Studio exports ZIP with metadata)
2. **See warning** if class_hash doesn't match current system
3. **Update master_classes.json** if needed (or use as-is)
4. **Run detection** (annotations validated at every load)

### For Developers (Integration)

```python
# Old way (deprecated but still works via shim)
from master_class_config import load_master_classes

# New way (recommended)
from embereye.core.class_config import load_master_classes, get_leaf_classes

classes = load_master_classes()
leaf_classes = get_leaf_classes(classes)  # 41 items
```

---

## Files to Know About

### Core Infrastructure
- `embereye/core/class_config.py` - Central module (156 lines)
- `embereye/config/master_classes.json` - Config storage
- `master_class_config.py` (root) - Backward-compat shim
- `embereye/app/master_class_config.py` - Backward-compat shim

### Annotation Safeguarding
- `embereye-studio/annotation_tab.py` - Enhanced with validation
- `workspace_data/annotations/{media}/ labels.txt` - Class mapping per media
- `workspace_data/annotations/{media}/labels_meta.json` - Metadata

### Model Export/Import
- `embereye-studio/studio_main_window.py#export_model_version()` - Export with hash
- `embereye-field/fieldglass/main_window.py#_execute_model_import()` - Import validation
- `main_window.py#_sandbox_import_model()` - Root import validation

---

## Testing Checklist

- [ ] Import `from embereye.core.class_config import load_master_classes` (no errors)
- [ ] Old import `from master_class_config import load_master_classes` still works
- [ ] `flatten_classes()` returns exactly 41 items
- [ ] Annotate and save frames in Studio (labels.txt created)
- [ ] Export model shows class_hash in metadata.json
- [ ] Import model shows warning if class_hash differs
- [ ] Detection shows actual class labels, not "CLASS A"

---

## The "CLASS A" Problem Explained

### Why It Happened
```
Training data had majority of person boxes labeled class_id 0:
- class_id 0: 580 instances (CLASS A)
- class_id 14: 1 instance (PERSON)

Model learned: "unsure what human is → guess class 0"
Result: All human detections → "CLASS A"
```

### How It's Fixed
```
1. Central config prevents class mapping errors (no duplicates)
2. Labels.txt locks class list per annotation session (no drift)
3. Model export includes class fingerprint (traceability)
4. Model import validates fingerprint (mismatch detection)
5. Training corrected (proper class_id 14 usage)

→ Next training will have correct class distribution
→ Detections will show proper person class names
```

---

## Summary Table

| Component | File | Status | Purpose |
|-----------|------|--------|---------|
| **Core Module** | embereye/core/class_config.py | ✅ | Central class operations |
| **Config Storage** | embereye/config/master_classes.json | ✅ | Persistent config |
| **Annotation Safety** | embereye-studio/annotation_tab.py | ✅ | Labels.txt + validation |
| **Export Versioning** | studio_main_window.py | ✅ | Add class_hash to export |
| **Import Validation** | Field/main imports | ✅ | Warn on mismatch |
| **Backward Compat** | Master_class_config shims | ✅ | Old imports still work |
| **Cleanup** | Deleted duplicate files | ✅ | Removed embereye-studio copy |

---

## Next Steps

1. **Audit existing training data:** Verify person annotations use class_id 14
2. **Retrain model:** Train v2 with corrected annotations
3. **Export & test:** Use new model with hardened safety checks
4. **Monitor deployment:** Watch for any class mapping issues in Field

**Documentation:** See [CLASS_CONFIG_CENTRALIZATION_COMPLETION.md](CLASS_CONFIG_CENTRALIZATION_COMPLETION.md) for full details.
