# External Dataset Class Mapping - Quick Fix Guide

## The 3-Line Problem

```
Import writes: class_id = 0   (based on master_classes.json order on Day 1)
QC reads:     flat_classes[0] (based on master_classes.json order on Day 2)
Result:       WRONG CLASS if order changed ❌
```

---

## Quick Fixes to Apply (Today)

### Fix #1: QC Review - Use Metadata (HIGH PRIORITY)
**File:** `embereye-studio/qc_review_dialog.py`

**Change line 595 from:**
```python
class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
```

**To:**
```python
class_name = self._get_class_name_for_id(class_id)
```

**Add new method after line 620:**
```python
def _get_class_name_for_id(self, class_id: int) -> str:
    """Get class name from ID, checking metadata first."""
    # Try to load _id_map from metadata
    metadata_file = self.annotations_dir / "metadata.json"
    if metadata_file.exists():
        try:
            import json
            meta = json.loads(metadata_file.read_text())
            id_map = meta.get("_id_map", {})
            if str(class_id) in id_map:
                return id_map[str(class_id)]
        except Exception:
            pass
    
    # Fallback to current class list
    return self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
```

**Also update _draw_annotations() line 576:**
```python
# OLD:
class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"

# NEW:
class_name = self._get_class_name_for_id(class_id)
```

---

### Fix #2: Importer - Generate _id_map.json (HIGH PRIORITY)
**File:** `embereye-studio/external_dataset_importer.py`

**Add after line 522 (after saving metadata.json):**
```python
# Generate explicit ID → name mapping for deterministic future lookups
id_map = {str(idx): name for name, idx in class_to_id.items()}
meta["_id_map"] = id_map  # Also add to metadata dict

# Write _id_map.json to both locations for redundancy
id_map_json = json.dumps(id_map, indent=2)
(ds_root / "_id_map.json").write_text(id_map_json, encoding="utf-8")
(qc_root / "_id_map.json").write_text(id_map_json, encoding="utf-8")

# Update metadata with _id_map before final save
(ds_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
(qc_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
```

---

### Fix #3: Training Pipeline - Use _id_map (MEDIUM PRIORITY)
**File:** `embereye-studio/forgelab/training_pipeline.py`

**In the `copy_dataset_samples()` method around line 505**, ensure it checks for `_id_map.json`:

```python
# Improved class mapping lookup (add this helper method to DatasetManager class)
def _get_id_map_for_dataset(self, ann_file: Path) -> dict:
    """Load _id_map.json from metadata if available."""
    # Look for _id_map.json in the same directory as annotations
    id_map_file = ann_file.parent / "_id_map.json"
    if not id_map_file.exists():
        # Try parent directory
        id_map_file = ann_file.parent.parent / "_id_map.json"
    
    if id_map_file.exists():
        try:
            return json.loads(id_map_file.read_text())
        except Exception:
            return {}
    
    # Also check metadata.json  
    metadata_file = ann_file.parent / "metadata.json"
    if metadata_file.exists():
        try:
            meta = json.loads(metadata_file.read_text())
            return meta.get("_id_map", {})
        except Exception:
            pass
    
    return {}
```

---

## Verification Checklist

After applying fixes:

- [ ] Create a new external dataset import
- [ ] Check that `_id_map.json` was created in both dataset and QC folders
- [ ] Check that `metadata.json` contains `_id_map` field
- [ ] Open import in Annotation screen - verify class display
- [ ] Open import in QC Review - verify class display matches
- [ ] Reorder classes in master_classes.json
- [ ] Re-open QC Review - classes should still display correctly (from metadata)
- [ ] Train model - should use correct class IDs (from _id_map)

---

## Why This Matters (For User Context)

You're seeing:
- **Annotation screen showing:** "CLASS A" (correct - uses metadata)
- **QC Review showing:** "CLASS B" (wrong - direct index into current master_classes)

This happens because:
1. Annotation screen loads from metadata when available
2. QC Review directly indexes into current master_classes.json
3. If class order changed, the indices no longer match

**After fix:** Both will use metadata and show the same class names.

---

## File Locations

```
For imported PPE dataset:
├── data/fire_analytics/imported_datasets/20260327_ppe_import/
│   ├── images/
│   ├── annotations/
│   └── metadata.json           ← Add _id_map here
└── annotations/20260327_ppe_import/
    ├── (images)
    ├── (label .txt files)
    ├── metadata.json           ← Add _id_map here
    └── _id_map.json            ← CREATE THIS FILE

For regular annotated media:
└── annotations/video_20260327_marker1234/
    ├── (images)
    ├── (label .txt files)
    ├── metadata.json           ← MAY NEED CREATING
    └── _id_map.json            ← CREATE THIS FILE
```

---

## Time Estimate

- **Fix #1 (QC Review):** 10 minutes
- **Fix #2 (Importer):** 5 minutes  
- **Fix #3 (Training):** 15 minutes (validation)
- **Testing:** 20 minutes

**Total:** ~50 minutes to resolve the most critical issue

---

## Prevention (For Future)

After applying fixes, add to your dev guidelines:

> **NEVER** reorder classes in master_classes.json after importing datasets.  
> New classes should always be APPENDED to the end of each category.
> 
> This ensures class IDs remain stable across the codebase.

Also consider:
- Adding a migration script that updates class IDs if reordering is necessary
- Adding validation warnings when opening old datasets
- Auto-generating _id_map.json at startup for backward compatibility
