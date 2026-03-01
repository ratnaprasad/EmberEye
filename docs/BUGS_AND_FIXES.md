# EmberEye Studio - Known Bugs and Fixes

## Bug Log

### Bug #1: QC Review shows "No annotations found" after successful ZIP import
**Date**: February 4, 2026  
**Severity**: High  
**Component**: Studio - Import/QC Review workflow  

**Description**:
When importing an annotation.zip file into Studio EXE:
1. Import succeeds and shows "Successfully imported" message
2. User clicks "🔍 QC Review" button
3. Alert shows "No annotations found in workspace. Please annotate some frames first."
4. Annotations are actually present in the extracted folder but not being detected

**Root Cause - ACTUAL (February 4, 2026)**:
**Path mismatch between import and QC Review functions:**
- `training_sync.py` uses `embereye.utils.resource_helper.get_data_path()`:
  * In EXE mode: Returns `C:\Users\[user]\.embereye\workspace\annotations`
  * Annotations correctly extracted to: `~/.embereye/workspace/annotations/` (141 bases found!)
  
- `studio_main_window.py` used local `get_data_path()`:
  * Always returns: `D:\EE\EmberEye\embereye-studio\workspace_data\annotations`
  * QC Review looked in WRONG location (folder doesn't exist!)
  
**Result**: Import succeeds silently, QC Review fails to find annotations because it searches in different directory.

**Root Cause - Initial Hypothesis (incorrect)**:
~~The import_annotations_zip() function in training_sync.py was too restrictive in ZIP structure acceptance~~
- This was NOT the issue - user's ZIP has standard `annotations/<base>/` format
- Import actually worked perfectly (141 bases extracted!)
- Problem was path resolution mismatch, not ZIP parsing

**Steps to Reproduce**:
1. Launch EmberEye-Studio.exe
2. Click "⬇ Import ZIP" button
3. Select annotations_full.zip (standard format with annotations/ prefix)
4. See success message: "Imported 141 media base(s)"
5. Check `C:\Users\HP\.embereye\workspace\annotations` → 141 bases present ✅
6. Click "🔍 QC Review" button
7. Code checks `D:\EE\EmberEye\embereye-studio\workspace_data\annotations` → empty! ❌
8. See error: "No annotations found in imported bases!"

**Expected Behavior**:
- Import extracts to: `~/.embereye/workspace/annotations/`
- QC Review reads from: `~/.embereye/workspace/annotations/`
- Both use same path resolution function

**Actual Behavior (before fix)**:
- Import extracts to: `~/.embereye/workspace/annotations/` (using resource_helper)
- QC Review reads from: `workspace_data/annotations/` (using local function)
- Different paths = annotations invisible to QC Review

**Fix Applied**:

**Phase 1** - Validation (completed but unnecessary):
Modified `studio_main_window.py`:
1. Import validation - counts .txt files after extraction, warns if none found
2. QC Review pre-check - validates bases have annotations before opening dialog
**Note**: This identified the symptom but not the root cause

**Phase 2** - ZIP Parsing Enhancement (completed but unnecessary):
Modified `embereye/app/training_sync.py` `import_annotations_zip()`:
- Added support for 3 ZIP structures (standard/direct/flat)
**Note**: User's ZIP already had standard format, this wasn't needed

**Phase 3** - ACTUAL FIX (February 4, 2026)**:
**Unified path resolution across Studio:**
Modified all Studio files to use centralized `get_data_path()`:

1. **embereye-studio/studio_main_window.py**:
   - Removed local `get_data_path()` function
   - Added import: `from embereye.utils.resource_helper import get_data_path`
   - Now uses same path resolution as training_sync.py

2. **embereye-studio/annotation_tab.py**:
   - Removed local `get_data_path()` function
   - Added import: `from embereye.utils.resource_helper import get_data_path`

3. **embereye-studio/studio_main_window_comprehensive.py**:
   - Removed local `get_data_path()` function
   - Added import: `from embereye.utils.resource_helper import get_data_path`

**Impact**:
- All Studio code now uses `~/.embereye/workspace/` in EXE mode
- Import and QC Review use identical path resolution
- Existing 141 imported bases will now be visible to QC Review!

**Files Modified**:
- ✅ `embereye-studio/studio_main_window.py` - Unified path resolution
- ✅ `embereye-studio/annotation_tab.py` - Unified path resolution  
- ✅ `embereye-studio/studio_main_window_comprehensive.py` - Unified path resolution
- `embereye/app/training_sync.py` (lines 757-820) - Enhanced ZIP parsing (bonus fix)

**Testing Needed**:
1. ✅ Verify annotations exist in `~/.embereye/workspace/annotations/` (141 bases confirmed)
2. ⏳ Rebuild Studio EXE with unified path resolution (COMPLETED - 308.1 MB)
3. Launch Studio EXE → Click QC Review → Should show all 141 bases!
4. Test import of new ZIP → verify extracted to same location
5. Verify annotation tab also uses correct paths

**Status**: 🟡 Testing - Rebuilt with unified get_data_path() (Feb 4, 2026 22:00)

---

## Bug Fix Template

### Bug #X: [Title]
**Date**: [Date]  
**Severity**: [Critical/High/Medium/Low]  
**Component**: [Module/Feature]  

**Description**: [What goes wrong]  
**Root Cause**: [Why it happens]  
**Steps to Reproduce**: [How to trigger]  
**Expected Behavior**: [What should happen]  
**Actual Behavior**: [What actually happens]  
**Fix Applied**: [Solution implemented]  
**Status**: [Open/Fixed/Closed]

---

## Notes
- Keep this document updated as bugs are discovered and fixed
- Mark bugs as 🔴 Open, 🟡 In Progress, or 🟢 Fixed
- Include version/build info when bugs are discovered in EXE builds
