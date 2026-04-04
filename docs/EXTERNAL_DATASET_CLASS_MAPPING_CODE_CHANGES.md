# External Dataset Class Mapping - Code Changes Reference

## Architecture Correction

The earlier diagnosis in this note assumed QC was mainly failing because of missing metadata persistence.

That is not the primary bug for the current Studio architecture.

The authoritative model is now:

1. Annotation IDs are category-local and must follow the active analytics category from settings.
2. QC Review must decode and edit IDs in that same active-category space.
3. `labels.txt` is the preferred per-folder contract for preserving that local ID space.
4. The old global flattened taxonomy path in QC is retired and should not be used for active flows.

For PPE specifically, local IDs like `1 -> NO_HELMET` and `2 -> SAFETY_VEST` were being misread in QC as global flattened IDs `1 -> CLASS B` and `2 -> CLASS C`.

The codebase fix now implemented is based on active analytics category alignment, with `labels.txt` propagation for QC and external imports.

## CHANGE #1: QC Review Dialog - Read Metadata (FIX QC DISPLAY)

**File:** `embereye-studio/qc_review_dialog.py`

### Change 1A: Fix _draw_annotations method

**Line 576 - BEFORE:**
```python
# Draw class label
class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
label = f"{class_name} #{idx+1}"
```

**Line 576 - AFTER:**
```python
# Draw class label
class_name = self._get_class_name_for_id(class_id)
label = f"{class_name} #{idx+1}"
```

---

### Change 1B: Fix refresh_annotation_list method

**Line 595 - BEFORE:**
```python
def refresh_annotation_list(self):
    """Refresh annotations list widget."""
    self.ann_list.clear()
    for idx, annotation in enumerate(self.current_annotations):
        class_id = annotation[0]
        class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
```

**Line 595 - AFTER:**
```python
def refresh_annotation_list(self):
    """Refresh annotations list widget."""
    self.ann_list.clear()
    for idx, annotation in enumerate(self.current_annotations):
        class_id = annotation[0]
        class_name = self._get_class_name_for_id(class_id)
```

---

### Change 1C: Add new helper method (ADD AFTER LINE 620)

**ADD THIS METHOD:**
```python
def _get_class_name_for_id(self, class_id: int) -> str:
    """Get class name from ID, preferring metadata mapping over current class list.
    
    Args:
        class_id: The numeric class ID from annotation file
        
    Returns:
        The mapped class name, or "class_<id>" if unknown
    """
    import json
    
    # Priority 1: Check metadata.json for _id_map
    metadata_file = self.annotations_dir / "metadata.json"
    if metadata_file.exists():
        try:
            meta = json.loads(metadata_file.read_text(encoding="utf-8"))
            id_map = meta.get("_id_map", {})
            if str(class_id) in id_map:
                return id_map[str(class_id)]
        except Exception as e:
            # Log but don't fail - continue to fallback
            import logging
            logging.debug(f"Failed to read _id_map from metadata: {e}")
    
    # Priority 2: Check _id_map.json file directly
    id_map_file = self.annotations_dir / "_id_map.json"
    if id_map_file.exists():
        try:
            id_map = json.loads(id_map_file.read_text(encoding="utf-8"))
            if str(class_id) in id_map:
                return id_map[str(class_id)]
        except Exception as e:
            import logging
            logging.debug(f"Failed to read _id_map.json: {e}")
    
    # Fallback: Use current flat_classes list
    # This allows viewing of old datasets without _id_map
    # but may show wrong names if classes were reordered
    if class_id < len(self.flat_classes):
        return self.flat_classes[class_id]
    
    return f"class_{class_id}"
```

---

## CHANGE #2: External Dataset Importer - Generate _id_map

**File:** `embereye-studio/external_dataset_importer.py`

### Change 2A: Generate and write _id_map.json

**Location:** After line 522 (after metadata.json is written)

**BEFORE (Current code around line 514-523):**
```python
        meta = {
            "source": str(source_path),
            "source_format": parsed.source_format,
            "active_domain": active_domain,
            "target_category": target_category,
            "class_mapping": class_mapping,
            "created_classes": created_classes,
            "skipped_classes": skipped_classes,
            "qc_status": "pending",
            "imported_at": datetime.now().isoformat(),
        }
        (ds_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (qc_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
```

**AFTER (Updated code):**
```python
        # Generate explicit ID → name mapping for deterministic future lookups
        id_map = {str(idx): name for name, idx in class_to_id.items()}
        # id_map example: {"0": "CLASS A", "1": "CLASS B", "2": "CLASS C", "3": "CLASS D"}
        
        meta = {
            "source": str(source_path),
            "source_format": parsed.source_format,
            "active_domain": active_domain,
            "target_category": target_category,
            "class_mapping": class_mapping,
            "created_classes": created_classes,
            "skipped_classes": skipped_classes,
            "qc_status": "pending",
            "imported_at": datetime.now().isoformat(),
            "_id_map": id_map,  # NEW: Store reverse mapping
        }
        (ds_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (qc_root / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        
        # Also write _id_map.json as standalone file for easier access
        id_map_json = json.dumps(id_map, indent=2)
        (ds_root / "_id_map.json").write_text(id_map_json, encoding="utf-8")
        (qc_root / "_id_map.json").write_text(id_map_json, encoding="utf-8")
```

**Total additions:** ~2 lines of active code (id_map generation) + ~3 lines (write _id_map files)

---

## CHANGE #3: Training Pipeline - Use _id_map (Optional but Recommended)

**File:** `embereye-studio/forgelab/training_pipeline.py`

### Change 3A: Add helper method to DatasetManager class

**Location:** Add to DatasetManager class (around line 430)

**ADD THIS METHOD:**
```python
def _load_id_map_for_dataset(self, dataset_root: Path) -> dict[str, str]:
    """Load ID mapping from dataset metadata for deterministic class remapping.
    
    This is critical for datasets imported from external sources where
    the class_id → class_name mapping must be preserved across reorderings
    of master_classes.json
    
    Args:
        dataset_root: Path to the dataset folder
        
    Returns:
        Dictionary mapping class_id (as string) to class_name
    """
    import json
    
    # Check for _id_map.json (preferred - explicit mapping)
    id_map_file = dataset_root / "_id_map.json"
    if id_map_file.exists():
        try:
            return json.loads(id_map_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    # Check for _id_map in metadata.json
    metadata_file = dataset_root / "metadata.json"
    if metadata_file.exists():
        try:
            meta = json.loads(metadata_file.read_text(encoding="utf-8"))
            if "_id_map" in meta:
                return meta["_id_map"]
        except Exception:
            pass
    
    # If no explicit mapping found, return empty dict
    # Caller should fall back to other mapping strategies
    return {}
```

### Change 3B: Use _id_map in copy_dataset_samples

**Location:** Line 505-525 area in copy_dataset_samples method

**BEFORE (Current code - simplified):**
```python
def copy_dataset_samples(self, ...):
    # ... existing code ...
    for split, files in ann_files.items():
        # ... 
        meta_file = ann_file.with_suffix('.json')
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                name_to_id = meta.get("class_mapping", {})
                # invert mapping
                for n, i in name_to_id.items():
                    try:
                        id_to_name[int(i)] = str(n)
                    except Exception:
                        pass
            except Exception:
                pass
```

**AFTER (Enhanced code):**
```python
def copy_dataset_samples(self, ...):
    # ... existing code ...
    
    # Load _id_map from dataset if available (for imported datasets)
    fallback_id_to_name = {}
    try:
        # Try to load from the dataset root where _id_map might exist
        id_map = self._load_id_map_for_dataset(Path(self.dataset_dir).parent)
        fallback_id_to_name = {int(k): v for k, v in id_map.items() if k.isdigit()}
    except Exception:
        pass
    
    for split, files in ann_files.items():
        # ... existing code ...
        for ann_file in files:
            id_to_name: dict[int, str] = {}
            meta_file = ann_file.with_suffix('.json')
            
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    
                    # Priority 1: Check for _id_map (import-time mapping)
                    if "_id_map" in meta:
                        id_map = meta["_id_map"]
                        id_to_name = {int(k): v for k, v in id_map.items() if k.isdigit()}
                    else:
                        # Priority 2: Fall back to class_mapping
                        name_to_id = meta.get("class_mapping", {})
                        for n, i in name_to_id.items():
                            try:
                                id_to_name[int(i)] = str(n)
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # Priority 3: Use fallback from dataset root _id_map
            if not id_to_name and fallback_id_to_name:
                id_to_name = fallback_id_to_name
```

---

## Summary of Changes

### Minimal Fix (Just Fix Display)
**Files:** 1 (`qc_review_dialog.py`)  
**Lines:** ~40 lines (3 changes + 1 new method)  
**Time:** 10 minutes  
**Impact:** QC Review shows correct classes immediately

### Complete Fix (Proper Solution)
**Files:** 2 (`qc_review_dialog.py`, `external_dataset_importer.py`)  
**Lines:** ~55 lines total  
**Time:** 20 minutes  
**Impact:** All new imports protected, existing imports still work with fallback

### Full Solution (Production Ready)
**Files:** 3 (add `training_pipeline.py`)  
**Lines:** ~100 lines total  
**Time:** 40 minutes  
**Impact:** Training pipeline also uses deterministic mappings, zero silent data corruption

---

## Testing Code Snippets

### Test 1: Verify _id_map Generated
```python
import json
from pathlib import Path

dataset_root = Path("data/fire_analytics/imported_datasets/20260327_ppe_import")

# Check files exist
assert (dataset_root / "_id_map.json").exists(), "Missing _id_map.json in dataset"
assert (dataset_root / "metadata.json").exists(), "Missing metadata.json"

# Check _id_map content
id_map = json.loads((dataset_root / "_id_map.json").read_text())
print("ID Map:", id_map)
# Should output: {"0": "CLASS A", "1": "CLASS B", ...}

# Check metadata contains _id_map
meta = json.loads((dataset_root / "metadata.json").read_text())
assert "_id_map" in meta, "metadata.json missing _id_map field"
assert meta["_id_map"] == id_map, "_id_map in metadata doesn't match file"

print("✅ All checks passed!")
```

### Test 2: Verify QC Review Uses Metadata
```python
# Manual test:
# 1. Import external dataset
# 2. Note class mappings
# 3. Reorder classes in master_classes.json  
# 4. Open QC Review
# 5. Verify classes still show correctly (using metadata, not current order)

# Automated test would require PyQt testing setup
```

### Test 3: Verify Fallback Works
```python
# Manual test:
# 1. Delete _id_map.json from imported dataset
# 2. Delete _id_map from metadata.json
# 3. Update _id_map.py to verify fallback behavior
# 4. Open QC Review
# 5. Should still show some class names (from flat_classes fallback)
```

---

## Verification Checklist

After making changes:

```
QC Review Changes:
  [ ] _draw_annotations uses _get_class_name_for_id()
  [ ] refresh_annotation_list uses _get_class_name_for_id()
  [ ] _get_class_name_for_id() method exists
  [ ] Handles missing _id_map gracefully (fallback)
  [ ] Imports json at top of method

External Importer Changes:
  [ ] id_map dict created correctly
  [ ] Added to meta dict as "_id_map"
  [ ] Written to (ds_root / "_id_map.json")
  [ ] Written to (qc_root / "_id_map.json")
  [ ] metadata.json contains "_id_map" field

Testing:
  [ ] Import new external dataset
  [ ] Verify _id_map.json created
  [ ] Verify QC shows correct classes
  [ ] Reorder master_classes
  [ ] Verify QC still shows correct classes
  [ ] Train with dataset (check for warnings/errors)
```

---

## Rollout Order

1. **Day 1:** Deploy Change #1 (QC Review fixes) - Lowest risk
2. **Day 2:** Deploy Change #2 (Importer) - Medium risk  
3. **Day 3+:** Deploy Change #3 (Training) - Optional optimization
4. **Ongoing:** Re-import any affected datasets with new code

---

## Notes for Code Review

- All changes maintain backward compatibility
- Old imports without _id_map will fall back to current class list behavior
- New imports will have explicit _id_map, making them future-proof
- No database schema changes required
- No breaking changes to existing APIs
