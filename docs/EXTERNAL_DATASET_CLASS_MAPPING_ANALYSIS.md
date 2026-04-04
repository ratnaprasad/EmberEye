# External Dataset Class Mapping Flow Analysis
**Date:** April 3, 2026  
**Status:** Critical Issue Identified - Fragile Class ID Mapping Pipeline

---

## Executive Summary

**THE PROBLEM:** When you import an external dataset and then view it in the **Annotation Screen** vs **QC Verification**, the classes display differently because:

1. **External dataset importer writes class IDs** based on the master_classes.json order **at import time**
2. **Annotation Screen & QC Review load class names** based on the current master_classes.json order **at display time**
3. **If master_classes.json changes** (classes reordered, added, removed), the class IDs in stored annotation files become stale and map to the WRONG class names

**The Pain:** You see `CLASS A` in annotations but `CLASS B` in QC because the class ordering changed between import and verification.

---

## Complete Data Flow Analysis

### Phase 1: Import External Dataset (external_dataset_importer.py)

#### Step 1A: Parse External Format
**File:** `embereye-studio/external_dataset_importer.py` lines 405-472

```python
# Load external dataset (YOLO/COCO/VOC format)
parsed = parse_dataset(normalized_source, forced_format)  
# parsed.class_names = ["class_a", "class_b", "class_c", ...]
# parsed.samples = list of ImageSample with normalized annotations
```

**Output:** Class names from external dataset extracted

#### Step 1B: Resolve Class Conflicts
**File:** `embereye-studio/external_dataset_importer.py` lines 433-456

```python
# Load current master_classes.json
classes_dict = load_master_classes()
current_leaf = flatten_classes(classes_dict)  # ["CLASS A", "CLASS B", ...]
case_map = {c.lower(): c for c in current_leaf}  # case-insensitive lookup

class_mapping: Dict[str, str] = {}  # external_name -> target_master_name

# For each external class:
for ext_name in parsed.class_names:
    hit = case_map.get(ext_name.lower())
    if hit:
        # Case-insensitive match found
        class_mapping[ext_name] = hit
    else:
        # Unknown class - call resolver (interactive dialog)
        action, value = resolver(ext_name, flatten_classes(classes_dict), target_category)
        # action = "create" | "map" | "skip"
        # value = new class name or mapped class name
        class_mapping[ext_name] = value  # or skipped
```

**Output:** `class_mapping` = {"class_a" -> "CLASS A", "class_b" -> "CLASS B", ...}

#### Step 1C: Write Annotations with Class IDs
**File:** `embereye-studio/external_dataset_importer.py` lines 460-506

```python
# Load CURRENT master_classes.json again (to ensure consistency)
final_classes = flatten_classes(load_master_classes())
class_to_id = {name: idx for idx, name in enumerate(final_classes)}
# class_to_id = {"CLASS A": 0, "CLASS B": 1, "CLASS C": 2, ...}

# For each annotation in the external dataset:
for sample in parsed.samples:
    for ann in sample.annotations:
        mapped = class_mapping.get(ann.class_name)  # "class_a" -> "CLASS A"
        if not mapped:
            continue
        cid = class_to_id.get(mapped)  # "CLASS A" -> 0
        # Write YOLO line: "0 x y w h\n"
        ds_lbl.write_text(f"{cid} {ann.x:.6f} {ann.y:.6f} {ann.w:.6f} {ann.h:.6f}\n")
        qc_lbl.write_text(...)  # Same file written to both locations
```

**Critical Output:**
- **Annotation files (.txt):** Only contain CLASS IDs (0, 1, 2, ...)
- **Metadata (.json):** Stores `class_mapping` = {external_name -> target_name} but NOT the reverse (ID -> name mapping)

---

### Phase 2: View in Annotation Screen (annotation_tab.py)

**File:** `embereye-studio/annotation_tab.py` lines 811

```python
# When annotation screen loads current media:
def _rebuild_class_map(self, class_list):
    self.leaf_classes = list(class_list or [])
    # REBUILDS MAP BASED ON CURRENT ORDER
    self.class_id_map = {cls: idx for idx, cls in enumerate(self.leaf_classes)}
    # class_id_map = {"CLASS A": 0, "CLASS B": 1, ...}
```

**Display Logic (lines 470-481):**
```python
def get_yolo_annotations(self, class_id_map):
    for shape in self.shapes:
        cls = shape.get('class')
        class_id = class_id_map[cls]  # Map class name to ID for saving
        # When displaying, reads class from the shape object directly
```

**What You See:** Classes shown as "CLASS A", "CLASS B" based on current master_classes.json

---

### Phase 3: View in QC Review (qc_review_dialog.py)

**File:** `embereye-studio/qc_review_dialog.py` lines 31-38, 595

```python
def __init__(self, annotations_dir: str, ...):
    # Load master classes AT QC OPEN TIME
    self.classes_dict = load_master_classes()
    self.flat_classes = self._get_flat_class_list()
    # flat_classes = ["CLASS A", "CLASS B", ...] (current order)

def _draw_annotations(self, image):
    for annotation in self.current_annotations:
        class_id = annotation[0]  # e.g., 0, 1, 2
        # CRITICAL BUG: Direct index into current flat_classes list
        class_name = self.flat_classes[class_id]  
        # If class_id=0 but current flat_classes[0] = "CLASS B" (due to reordering)
        # → Wrong class displayed!
```

**The Bug:**
- Reads class ID from annotation file (e.g., `0`)
- Directly indexes into current `flat_classes` list
- **Assumes the order hasn't changed since import** ← WRONG!

---

## Concrete Example: How Classes Get Swapped

### Scenario: Reordering between import and QC review

**Day 1 - Import Time:**
- master_classes.json order: `["CLASS A", "CLASS B", "CLASS C", "CLASS D"]`
- External dataset has "helmet", "person", "vest"
- **Mapped to:** A=helmet(0), D=person(3), C=vest(2)
- **Annotation written:** `0 0.5 0.5 0.2 0.2` (CLASS A) and `3 0.4 0.4 0.1 0.1` (CLASS D)

**Day 2 - QC Review (Someone reordered classes):**
- master_classes.json order: `["CLASS B", "CLASS A", "CLASS C", "CLASS D"]` (swapped A↔B)
- flat_classes now: `["CLASS B"(idx 0), "CLASS A"(idx 1), ...]`
- **Annotation file still has:** `0 0.5 0.5` and `3 0.4 0.4`
- **QC Display reads:**
  - `flat_classes[0]` → **"CLASS B"** (WRONG! Should be "CLASS A")
  - `flat_classes[3]` → **"CLASS D"** (correct)

**Result:** Annotation shows "CLASS B helmet" instead of "CLASS A helmet" ❌

---

## Pain Areas Identified

### 🔴 **PAIN AREA 1: Fragile Class ID Persistence**
- **Root:** Class IDs are assigned based on order in master_classes.json at import time
- **Problem:** Any class reordering, insertion, or deletion breaks all imported datasets
- **Impact:** Medium-High. Someone reorders classes → all old annotations become wrong
- **Fix Required:** Explicit ID → name mapping stored at import time

### 🔴 **PAIN AREA 2: Missing Metadata Usage in QC Review**
- **Root:** QCReviewDialog doesn't load or use metadata.json
- **Problem:** It rebuilds class list from current master_classes.json instead of using import-time metadata
- **Impact:** High. QC verification shows wrong classes for any imported dataset
- **Fix Required:** QC dialog should:
  1. Check for metadata.json in the annotation folder
  2. Use `class_mapping` from metadata to reverse-map class IDs
  3. Fall back to current master_classes if metadata missing
- **Code Location:** `embereye-studio/qc_review_dialog.py` lines 200-210, 595

### 🔴 **PAIN AREA 3: No _id_map.json Created**
- **Root:** Documentation (PPE_DATASET_REMAP_FIX_NOTE_20260327.md) says `_id_map.json` should be created but code doesn't generate it
- **Problem:** Training pipeline can't deterministically remap classes without explicit ID mapping
- **Impact:** Medium. Silent class corruptions during training dataset prep
- **Fix Required:** external_dataset_importer.py should generate:
  ```json
  {
    "0": "CLASS A",      // class_id -> target_class_name
    "1": "CLASS B",
    "2": "CLASS C",
    "3": "CLASS D"
  }
  ```
- **Code Location:** `embereye-studio/external_dataset_importer.py` after line 522

### 🔴 **PAIN AREA 4: Annotation Tab Class Rebuilds on Every Load**
- **Root:** `annotation_tab.py` rebuilds `class_id_map` every time media loads
- **Problem:** If classes are reordered, old annotations become inconsistent
- **Impact:** Medium. Writing annotations after class reorder corrupts them
- **Fix Required:** Annotation tab should also check metadata and use import-time mapping

### 🟡 **PAIN AREA 5: No Validation/Warning on Class Changes**
- **Root:** System silently accepts class reordering without warning
- **Problem:** User doesn't know their imports are now broken
- **Impact:** Low. But prevents accidents
- **Fix Required:** Add validation when loading datasets to warn if class order differs from metadata

---

## Data Structure Issues

### Current Architecture (BROKEN):

```
external_dataset/
├── images/
│   └── image1.jpg
├── annotations/
│   └── image1.txt          # Content: "0 x y w h" (only IDs!)
└── metadata.json           # Has class_mapping but NOT id_map
    {
      "class_mapping": {
        "helmet": "CLASS A",    # ← Only forward direction!
        "person": "CLASS D"
      }
    }
```

**The Issue:** To go from ID (0) back to name, you need the INVERSE mapping, which isn't stored.

### Required Architecture (FIXED):

```
external_dataset/
├── images/
│   └── image1.jpg
├── annotations/
│   └── image1.txt          # Content: "0 x y w h"
├── metadata.json           # Enhanced with ID mapping
│   {
│     "class_mapping": {
│       "helmet": "CLASS A",
│       "person": "CLASS D"
│     }
│   }
└── _id_map.json            # NEW! Explicit reverse mapping
    {
      "0": "CLASS A",
      "1": "CLASS B",
      "2": "CLASS C",
      "3": "CLASS D"
    }
```

---

## Current Code Issues Summary

| File | Line | Issue | Severity |
|------|------|-------|----------|
| `qc_review_dialog.py` | 595 | Direct index into flat_classes without metadata lookup | **CRITICAL** |
| `external_dataset_importer.py` | 522 | No `_id_map.json` file generated | **HIGH** |
| `qc_review_dialog.py` | 31-38 | Doesn't check for metadata.json or _id_map.json | **HIGH** |
| `annotation_tab.py` | 811 | Rebuilds class_id_map without checking import metadata | **MEDIUM** |
| `studio_main_window.py` | 2747-2790 | Resolver shows ALL existing classes, not category-specific | **MEDIUM** |

---

## Recommended Fixes (Priority Order)

### 1️⃣ **CRITICAL: Fix QC Review Display Logic**
**File:** `embereye-studio/qc_review_dialog.py`

Change refresh_annotation_list() and _draw_annotations() to:
```python
def _get_class_name_for_id(self, class_id: int) -> str:
    """Get class name from ID, using metadata if available."""
    # Check if metadata.json exists with _id_map
    metadata_path = self.annotations_dir / "metadata.json"
    if metadata_path.exists():
        try:
            meta = json.loads(metadata_path.read_text())
            id_map = meta.get("_id_map", {})
            if str(class_id) in id_map:
                return id_map[str(class_id)]
        except Exception:
            pass
    
    # Fallback to current master_classes order
    return self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
```

### 2️⃣ **HIGH: Generate _id_map.json on Import**
**File:** `embereye-studio/external_dataset_importer.py`

After line 522, add:
```python
# Generate explicit ID → name mapping for deterministic future lookups
id_map = {str(idx): name for name, idx in class_to_id.items()}
id_map_file_ds = ds_root / "_id_map.json"
id_map_file_qc = qc_root / "_id_map.json"
id_map_file_ds.write_text(json.dumps(id_map, indent=2), encoding="utf-8")
id_map_file_qc.write_text(json.dumps(id_map, indent=2), encoding="utf-8")
```

### 3️⃣ **HIGH: Update metadata.json with _id_map**
Update the metadata dict before writing (line 514-523):
```python
meta = {
    ...
    "_id_map": {str(idx): name for name, idx in class_to_id.items()},
    ...
}
```

### 4️⃣ **MEDIUM: Add Validation on QC Open**
**File:** `embereye-studio/qc_review_dialog.py`

In `__init__`, add warning if class order differs from metadata:
```python
metadata_path = self.annotations_dir / "metadata.json"
if metadata_path.exists():
    meta = json.loads(metadata_path.read_text())
    stored_id_map = meta.get("_id_map", {})
    if stored_id_map and stored_id_map != current_id_map:
        logger.warning(
            f"Class order changed since import! "
            f"May be viewing wrong class names. Please re-import or verify."
        )
```

### 5️⃣ **MEDIUM: Enhance Annotation Tab**
**File:** `embereye-studio/annotation_tab.py`

When loading media, check metadata:
```python
metadata_path = Path(get_data_path(f"annotations/{self.media_base}")) / "metadata.json"
if metadata_path.exists():
    # Use import-time class order instead of current master_classes
    meta = json.loads(metadata_path.read_text())
    classes_from_meta = meta.get("_id_map", {})
    loaded_classes = [classes_from_meta.get(str(i)) for i in range(len(classes_from_meta))]
    self._rebuild_class_map(loaded_classes)  # Use import-time order
```

---

## Why This Happens: Root Causes

### Root Cause 1: Design Assumption
**Assumption:** "The order of classes in master_classes.json never changes"  
**Reality:** Users add/reorder classes all the time during model development

### Root Cause 2: Temporal Decoupling  
- Class IDs are assigned **at import time** based on master_classes.json v1
- Class names are resolved **at display time** based on master_classes.json v2
- No guarantee v1 == v2

### Root Cause 3: Missing Inverse Mapping
- `class_mapping` stores: external_name → master_name (forward)
- But we need: class_id → master_name (reverse, for display)
- System doesn't generate the reverse mapping

### Root Cause 4: Stateless Display Logic
- QC/Annotation screens are stateless - they reconstruct display from scratch each time
- They don't consult the "snapshot" of classes that existed at import time
- They use current master_classes.json as ground truth

---

## Testing Recommendations

### Test 1: Class Reordering
```python
# 1. Import dataset with mapping A→0, B→1, C→2
# 2. Reorder classes in master_classes.json: B→0, A→1, C→2
# 3. Open QC review
# EXPECTED: Show correct class names (using metadata)
# ACTUAL: Shows wrong classes (QC displays B for ID 0)
```

### Test 2: Class Insertion
```python
# 1. Import dataset with A→0, B→1
# 2. Add new class X at beginning
# 3. Now A→1, B→2, X→0
# EXPECTED: Old annotations still show A, B (from metadata)
# ACTUAL: Shows B, X (direct indexing)
```

### Test 3: Metadata Fallback
```python
# 1. Import dataset normally (should write _id_map.json)
# 2. Delete _id_map.json
# 3. Open QC review
# EXPECTED: Fall back to current master_classes (safe degradation)
# ACTUAL: Crash or show wrong names
```

---

## Impact Assessment

| Scenario | Impact | Current | Fixed |
|----------|--------|---------|-------|
| Import + immediate QC | ✅ Works | Right classes | Right classes |
| Import + reorder classes + QC | ❌ BROKEN | Wrong classes | Right classes |
| Import + add classes + QC | ❌ BROKEN | Index out of range | Right classes |
| Train after import + reorder | ⚠️ Risky | Silent corruption | Deterministic |

---

## Related Issues

See also: [docs/PPE_DATASET_REMAP_FIX_NOTE_20260327.md](PPE_DATASET_REMAP_FIX_NOTE_20260327.md)

The PPE remapping documentation already identified that `_id_map.json` should exist, but it was never fully implemented in the importer.

---

## Conclusion

The most important function for external dataset mapping is **BROKEN** because of this fragile temporal dependency on master_classes.json ordering. The fix requires:

1. **Generate `_id_map.json`** at import time (5 lines of code)
2. **Check `_id_map.json`** in QC review (15 lines of code)
3. **Validate consistency** when loading (10 lines of code)
4. **Document the requirement** that imports lock in class order

This is a **Medium-High priority fix** because every external dataset import is currently at risk of displaying/training with wrong classes after any master_classes.json modification.
