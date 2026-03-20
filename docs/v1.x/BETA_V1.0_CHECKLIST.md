# EmberEye Beta v1.0 Release Checklist

**Target Date:** TBD  
**Status:** In Progress

---

## 🎯 Core Functionality

### Training System
- [x] Class taxonomy management with hierarchical structure
- [x] Annotation tool with metadata snapshots
- [x] Orphaned class detection and remapping to `unclassified_*`
- [x] Training pipeline with YOLOv8 integration
- [x] Model versioning and rollback
- [x] Quick Retrain feature (10-25 epochs)
- [x] Filtered dataset for unclassified-only retraining
- [ ] **NEEDS TESTING:** Full dataset quick retrain
- [ ] **NEEDS TESTING:** Filtered dataset quick retrain
- [ ] **NEEDS TESTING:** Post-training summary dialog

### Import/Export
- [x] Export/Import classes (JSON package)
- [x] Export/Import annotations (JSON package)
- [x] Export/Import ZIP archives (images + labels)
- [x] Revert from backups (classes and annotations)
- [x] **FIXED:** Circular import issue (training_sync ↔ conflict_detection)
- [ ] **NEEDS TESTING:** Verify all import/export flows work after circular import fix

### Video Wall
- [x] Multi-camera RTSP feed support
- [x] Grid layouts (2×2, 3×3, 4×4, 5×5)
- [x] **FIXED:** Grid resize not applying correctly when switching sizes
- [x] **FIXED:** Maximize/minimize functionality
- [x] Pagination for large camera arrays
- [x] Group filtering

### UI/UX
- [x] **FIXED:** Training tab button layout (8 buttons in one line → 2-column grid)
- [x] Modern theme support
- [x] Sandbox mode for model testing
- [x] Real-time metrics dashboard
- [x] Review Unclassified Items dialog

---

## 🐛 Bug Fixes (Completed)

- [x] Circular import: `training_sync` ↔ `conflict_detection` → Created `bbox_utils.py`
- [x] Video wall grid resize not working when switching 2×2 ↔ 3×3
- [x] Maximize not spanning full grid (was hiding instead of spanning)
- [x] Minimize not restoring widgets (capturing positions after modification)
- [x] Training tab layout causing excessive window width
- [x] PFDS log spam (PERIOD_ON failures every 5s → now every 30s)

---

## 🧹 Code Cleanup

- [x] Remove debug print statements from `handle_maximize()`
- [x] Remove debug print statements from `handle_minimize()`
- [ ] Verify no other debug/TODO comments in production code
- [ ] Check for any hardcoded paths or test values
- [ ] Review error handling consistency across modules

---

## 🧪 Testing Requirements

### Critical Path Testing
1. **Training Workflow**
   - [ ] Import media
   - [ ] Annotate frames (verify metadata JSON created)
   - [ ] Move to training dataset
   - [ ] Start full training (verify runs to completion)
   - [ ] Quick retrain with full dataset
   - [ ] Quick retrain with unclassified-only filter
   - [ ] Verify post-training summary shows unclassified counts
   - [ ] Review unclassified items dialog
   - [ ] Model rollback functionality

2. **Class Management**
   - [ ] Modify class taxonomy (add/remove/rename)
   - [ ] Verify save-time warning appears
   - [ ] Verify orphaned classes get remapped to `unclassified_*`
   - [ ] Export classes package
   - [ ] Import classes package (merge mode)
   - [ ] Import classes package (override mode)
   - [ ] Revert classes from backup

3. **Annotation Management**
   - [ ] Export annotations package
   - [ ] Import annotations package (merge mode)
   - [ ] Import annotations package (override mode)
   - [ ] Export ZIP archive
   - [ ] Import ZIP archive
   - [ ] Revert annotations from backup

4. **Video Wall**
   - [ ] Add multiple RTSP streams
   - [ ] Switch grid sizes (2×2 → 3×3 → 4×4 → back to 2×2)
   - [ ] Maximize video widget (with feed)
   - [ ] Minimize back to grid
   - [ ] Maximize video widget (without feed/simulator)
   - [ ] Minimize back to grid
   - [ ] Test pagination with > 4 cameras

5. **Sandbox Mode**
   - [ ] Load trained model
   - [ ] Upload test image
   - [ ] Run inference
   - [ ] Verify detections and overlays

### Edge Cases
- [ ] Training with 0 annotations (should show warning)
- [ ] Switching grid size while widget is maximized
- [ ] Deleting annotation files mid-training
- [ ] Network disconnection during RTSP streaming
- [ ] Very large annotation datasets (performance)

---

## 📚 Documentation

### Code Documentation
- [ ] Review all docstrings for accuracy
- [ ] Update inline comments where logic changed
- [ ] Document new features (filtered dataset, quick retrain)

### User Documentation
- [ ] Update README.md with v1.0 features
- [ ] Document quick retrain workflow
- [ ] Document class change handling
- [ ] Add troubleshooting section
- [ ] Update installation instructions if needed

### Developer Documentation
- [ ] Architecture diagram (if not exists)
- [ ] Module dependency graph
- [ ] API reference for key classes
- [ ] Contributing guidelines

---

## 📝 Release Artifacts

### Version Updates
- [ ] Update version number in `__init__.py` or version file
- [ ] Update version in installer scripts
- [ ] Update version in about dialog

### Changelog
- [ ] Create CHANGELOG.md entry for v1.0
- [ ] List all major features
- [ ] List all bug fixes
- [ ] List known limitations
- [ ] Credit contributors

### Release Notes
- [ ] Write user-friendly release notes
- [ ] Highlight breaking changes (if any)
- [ ] Migration guide (if upgrading from older version)
- [ ] System requirements

---

## 🚀 Pre-Release

### Performance
- [ ] Profile training pipeline for bottlenecks
- [ ] Check memory leaks (especially video widgets)
- [ ] Optimize large dataset handling
- [ ] Verify CPU/GPU utilization

### Security
- [ ] Review authentication mechanisms
- [ ] Check for hardcoded credentials
- [ ] Validate input sanitization
- [ ] Review file upload security

### Compatibility
- [ ] Test on macOS (current platform)
- [ ] Test on Windows (if supported)
- [ ] Test on Linux (if supported)
- [ ] Verify Python version requirements
- [ ] Check dependency versions

---

## 📦 Build & Deploy

### Build Process
- [ ] Clean build environment
- [ ] Run full test suite
- [ ] Build installer/package
- [ ] Verify installer works on clean system
- [ ] Test uninstall process

### GitHub Release
- [ ] Tag version in git: `git tag -a v1.0.0-beta -m "Beta v1.0"`
- [ ] Push tags: `git push origin v1.0.0-beta`
- [ ] Create GitHub release
- [ ] Upload build artifacts
- [ ] Mark as pre-release (beta)

---

## ✅ Sign-Off Criteria

**All items must be checked before release:**
- [ ] All critical path tests pass
- [ ] No P0/P1 bugs open
- [ ] Documentation complete
- [ ] Version numbers updated
- [ ] Changelog published
- [ ] Build artifacts created
- [ ] At least 2 successful clean installs tested

---

## 🔮 Post-Release (v1.1 Planning)

### Known Limitations to Address
- [ ] PFDS connection handling improvements
- [ ] Better error recovery in video streaming
- [ ] Batch annotation tools
- [ ] Advanced model metrics visualization
- [ ] Export training reports

### Feature Requests
- [ ] Multi-model comparison
- [ ] Active learning suggestions
- [ ] Cloud storage integration
- [ ] Mobile viewer app

---

**Last Updated:** 2025-12-27  
**Maintained By:** Development Team
