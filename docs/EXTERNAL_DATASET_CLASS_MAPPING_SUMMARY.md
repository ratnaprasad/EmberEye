# External Dataset Class Mapping Issue - Complete Analysis Summary

**Created:** April 3, 2026  
**Issue Type:** Data Quality / Class Mapping Bug  
**Severity:** 🔴 HIGH (Silent data corruption possible)  
**Scope:** External dataset import, annotation display, QC review, training

---

## The Issue (What You're Experiencing)

You import an external dataset and notice:
- **Annotation Screen shows:** "CLASS A" ✓
- **QC Review shows:** "CLASS B" ❌
- **Should both be:** "CLASS A"

Or even worse:
- You train a model with the (incorrectly mapped) data
- Model performance suffers due to silent class corruption

---

## Root Cause (Why It Happens)

### The Problem in 3 Lines

```python
# Line A (import time): class_id = 0   # Based on master_classes.json order at import
# Line B (QC view time): name = flat_classes[0]  # Based on master_classes.json order at view
# Result: WRONG if order changed between A and B
```

### The Technical Issue

The external dataset import pipeline:
1. Creates class ID mappings **when you import** (based on current master_classes.json order)
2. Stores annotation files with just the numeric class IDs (0, 1, 2, ...)
3. Stores metadata with class names but NO reverse mapping (ID → name)
4. When you open QC Review, it looks up IDs directly in the CURRENT master_classes.json order
5. **If class order changed, the IDs don't match anymore** ← BUG

---

## Data Flow (Detailed)

### What SHOULD Happen (Fixed Flow)

```
1. IMPORT:
   - External dataset: {"helmet": {...}, "person": {...}, ...}
   - Current classes: [CLASS A, CLASS B, CLASS C, CLASS D]
   - Map and assign IDs: helmet→CLASS A(0), person→CLASS D(3)
   - ✓ Write annotations with ID=0, ID=3
   - ✓ ALSO write mapping: 0→CLASS A, 3→CLASS D
   
2. QC REVIEW (Days later, even if classes were reordered):
   - Load annotation: ID=0
   - Look up in mapping: 0→CLASS A
   - ✓ Display "CLASS A" CORRECTLY
   
3. TRAINING:
   - Load annotation: ID=0
   - Look up in mapping: 0→CLASS A
   - ✓ Train with CLASS A CORRECTLY
```

### What ACTUALLY Happens Now (Broken Flow)

```
1. IMPORT:
   - External dataset: {"helmet": {...}, "person": {...}, ...}
   - Current classes: [CLASS A, CLASS B, CLASS C, CLASS D]
   - Map and assign IDs: helmet→CLASS A(0), person→CLASS D(3)
   - ✓ Write annotations with ID=0, ID=3
   - ✗ NO explicit mapping saved (0→CLASS A, 3→CLASS D)
   
2. QC REVIEW (Days later, someone reordered classes):
   - Classes now: [CLASS B, CLASS A, CLASS C, CLASS D]  ← REORDERED!
   - Load annotation: ID=0
   - Look up CURRENT flat_classes[0]
   - ✗ Gets "CLASS B" (WRONG! Was CLASS A at import)
   - ✗ Display "CLASS B" INCORRECTLY
   
3. TRAINING:
   - Load annotation: ID=0
   - Look up CURRENT flat_classes[0]
   - ✗ Gets "CLASS B" 
   - ✗ Train with CLASS B instead of CLASS A
   - ✗ Model learns WRONG connections
```

---

## Files Involved

### Primary Files (Where Changes Needed)

| File | Issue | Line | Severity |
|------|-------|------|----------|
| `embereye-studio/qc_review_dialog.py` | Doesn't use metadata when mapping IDs to names | 595 | 🔴 CRITICAL |
| `embereye-studio/external_dataset_importer.py` | Doesn't create/store `_id_map.json` | 522 | 🔴 CRITICAL |
| `embereye-studio/annotation_tab.py` | Rebuilds class map from current state | 811 | 🟡 MEDIUM |
| `embereye-studio/forgelab/training_pipeline.py` | Doesn't validate ID mappings during prep | 505 | 🟡 MEDIUM |

### Related Documentation

| Document | Status |
|----------|--------|
| [PPE_DATASET_REMAP_FIX_NOTE_20260327.md](PPE_DATASET_REMAP_FIX_NOTE_20260327.md) | Mentions _id_map was supposed to be generated (not fully implemented) |
| [EXTERNAL_DATASET_CLASS_MAPPING_ANALYSIS.md](EXTERNAL_DATASET_CLASS_MAPPING_ANALYSIS.md) | Full detailed analysis (NEW) |
| [EXTERNAL_DATASET_CLASS_MAPPING_DIAGRAM.md](EXTERNAL_DATASET_CLASS_MAPPING_DIAGRAM.md) | Visual flow diagrams (NEW) |
| [EXTERNAL_DATASET_CLASS_MAPPING_QUICK_FIX.md](EXTERNAL_DATASET_CLASS_MAPPING_QUICK_FIX.md) | Quick implementation guide (NEW) |
| [EXTERNAL_DATASET_CLASS_MAPPING_CODE_CHANGES.md](EXTERNAL_DATASET_CLASS_MAPPING_CODE_CHANGES.md) | Code-level changes (NEW) |

---

## Pain Areas (Why This Matters)

### 🔴 Pain Area 1: Inconsistent Display
**Impact:** Medium  
**Frequency:** Every time you import and later change class order  
**User Experience:** "Why do different screens show different class names?"

### 🔴 Pain Area 2: Silent Training Data Corruption
**Impact:** HIGH  
**Frequency:** Every import followed by class reordering + training  
**User Experience:** Model trains with wrong class labels → poor performance → confusion

### 🔴 Pain Area 3: No Warning or Validation
**Impact:** Medium  
**Frequency:** Unknown (happens silently)  
**User Experience:** No visibility into the problem

### 🔴 Pain Area 4: Fragile Architecture
**Impact:** HIGH  
**Frequency:** Ongoing risk for any new imports  
**User Experience:** System is unpredictable, requires careful class management

---

## Impact Assessment

### Current State (BROKEN)
```
✅ Annotation works correctly (loads from metadata when available)
❌ QC Review shows wrong classes (direct index into flat_classes)
❌ Training uses wrong classes (indirect impact via QC)
❌ User sees inconsistency between screens
❌ Model degradation risk
```

### After Minimal Fix
```
✅ Annotation works correctly
✅ QC Review shows correct classes (uses metadata)
❌ Training still at risk if using old import logic
✅ User sees consistent classes across screens
⚠️  Model still at risk if trained before fix applied
```

### After Complete Fix
```
✅ All screens show correct classes
✅ Training uses correct class mappings
✅ New imports are future-proof
⚠️  Old imports still at risk if reordered
```

---

## Solution Summary

### What Needs to Be Fixed

| Problem | Solution | Effort | Impact |
|---------|----------|--------|--------|
| QC Review uses wrong mapping | Use metadata vs. current flatlist | 10 min | 🔴 HIGH |
| No mapping stored at import | Generate _id_map.json | 5 min | 🔴 HIGH |
| Training pipeline fragile | Validate and use _id_map | 20 min | 🟡 MEDIUM |
| No warnings when classes change | Add validation checks | 15 min | 🟢 LOW |

### Quick Implementation Plan

**Phase 1: Immediate (30 min)** - Make QC Review use metadata
- File: `qc_review_dialog.py`
- Changes: 3 code locations + 1 new method
- Result: QC displays correct classes

**Phase 2: Medium-term (15 min)** - Generate _id_map at import
- File: `external_dataset_importer.py`
- Changes: 2 new file writes
- Result: New imports store explicit mappings

**Phase 3: Nice-to-have (30 min)** - Hardening training pipeline
- File: `training_pipeline.py`
- Changes: 1 new method + 2 call sites
- Result: Training pipeline uses deterministic remapping

---

## Key Insight

The root cause is **temporal coupling**: the system assumes the class order in master_classes.json never changes. But it does. The fix is to capture the class order **at import time** and use that captured snapshot when displaying/training, instead of reconstructing from the current (possibly different) master_classes.json.

```
BAD PRACTICE:
  "I'll just look at the current state"

GOOD PRACTICE:
  "I'll save the state at import time and refer to that snapshot later"
```

---

## Next Steps

1. **Understand the Issue**
   - Read [EXTERNAL_DATASET_CLASS_MAPPING_ANALYSIS.md](EXTERNAL_DATASET_CLASS_MAPPING_ANALYSIS.md) for full details
   
2. **See What Happens**
   - Review [EXTERNAL_DATASET_CLASS_MAPPING_DIAGRAM.md](EXTERNAL_DATASET_CLASS_MAPPING_DIAGRAM.md) for flow diagrams

3. **Implement the Fix**
   - Follow [EXTERNAL_DATASET_CLASS_MAPPING_CODE_CHANGES.md](EXTERNAL_DATASET_CLASS_MAPPING_CODE_CHANGES.md)
   - Or use [EXTERNAL_DATASET_CLASS_MAPPING_QUICK_FIX.md](EXTERNAL_DATASET_CLASS_MAPPING_QUICK_FIX.md) for quick reference

4. **Verify the Fix**
   - Import new external dataset
   - Check that _id_map.json was created
   - Reorder classes in master_classes.json
   - Verify QC Review still shows correct classes

5. **Document the Change**
   - Add to CHANGELOG
   - Consider adding to developer guidelines: "Always append new classes, never reorder existing ones"

---

## Most Critical Function

As you mentioned, this IS the most important function because:

1. **External dataset import** is the main way to get labeled training data
2. **Class mapping** directly affects model training quality
3. **Silent corruption** (where model trains with wrong labels) is the worst kind of bug
4. **Affects downstream** everything: QC, training, model inference

Fix priority: **CRITICAL** 🔴

---

## FAQ

**Q: Why does Annotation Screen show the right class?**  
A: It has better metadata handling in some cases, plus it loads data differently.

**Q: Could this affect my existing trained models?**  
A: If they were trained with this dataset after class reordering, possibly yes.

**Q: What happens if I don't fix this?**  
A: Every future import is at risk of silently corrupting training data.

**Q: How do I fix old imports?**  
A: Re-import them with the fixed code, or manually create _id_map.json files.

**Q: Is this a quick fix?**  
A: Yes - Phase 1 is 10-15 minutes to fix QC Review. Complete fix is ~50 minutes.

---

## Documentation Files Created

1. **EXTERNAL_DATASET_CLASS_MAPPING_ANALYSIS.md** (Detailed analysis)
   - Root causes
   - Data flow diagrams
   - Pain areas
   - Impact assessment

2. **EXTERNAL_DATASET_CLASS_MAPPING_DIAGRAM.md** (Visual guides)
   - Flow diagrams showing current vs. fixed
   - Timeline showing how the bug manifests
   - Data structure comparisons

3. **EXTERNAL_DATASET_CLASS_MAPPING_QUICK_FIX.md** (Implementation)
   - Quick reference for fixes
   - Before/after code snippets
   - Testing checklist

4. **EXTERNAL_DATASET_CLASS_MAPPING_CODE_CHANGES.md** (Detailed code)
   - Exact line numbers
   - Complete code changes
   - All three phases with full code

This document (Summary)
   - Overview of the issue
   - What, why, how
   - Action items

---

## Is this the only issue in dataset mapping?

**Likely not.** This analysis found:
- 4 critical/high severity issues
- 2 medium severity issues
- Possibly more in related areas

But the QC Review display issue is the most visible and most corrupting for data quality.

---

## Version Information

- **Codebase:** EmberEye 2.x develop branch
- **Analysis Date:** April 3, 2026
- **Python Version:** 3.x
- **Frameworks:** PyQt6, PyInstaller, YOLOv8

---

## Contact / Questions

For deeper technical questions, see the detailed analysis documents. For implementation help, see code changes document. For visual understanding, see diagram document.

All documentation files are in `/docs/` folder with `EXTERNAL_DATASET_CLASS_MAPPING_` prefix.
