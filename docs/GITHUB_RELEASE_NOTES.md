# EmberEye v1.0.0-beta 🚀

**First comprehensive beta release with advanced training & class management**

## ✨ What's New

### 🎓 Quick Retrain Feature
- **Full Dataset Mode**: Comprehensive retraining on all annotations (10-25 epochs)
- **Filtered Dataset Mode**: Focused retraining on unclassified items only
- Smart dataset selection dialog on every retrain

### 🏷️ Class Consistency System
- **Automatic Orphan Remapping**: Missing classes → `unclassified_*` categories
- **Metadata Snapshots**: Class taxonomy stored in annotation JSON files
- **Save-Time Warnings**: Alerts when class taxonomy changes detected
- Graceful handling of taxonomy evolution without breaking existing data

### 📊 Post-Training Summary
- Comprehensive report showing unclassified item counts by category
- Quick navigation to review unclassified items
- Direct launch of annotation tool for remediation
- One-click access to filtered retraining workflow

### 📦 Import/Export System
- **Class Hierarchy**: Export/import with provenance tracking
- **Annotations**: Full annotation packages with metadata
- **ZIP Archives**: Complete images + labels + metadata bundles
- **Revert Backups**: Restore from backup for classes and annotations
- **Conflict Detection**: Smart merge strategies for data conflicts

### 🎬 Enhanced Video Wall
- Dynamic grid layouts (2×2, 3×3, 4×4, 5×5)
- Maximize/minimize individual video widgets
- Smooth grid resize with proper layout recalculation
- Pagination for large camera arrays
- Group filtering for organized multi-stream viewing

### 🧹 UI/UX Improvements
- Training tab reorganized into logical 2-column grid
- Import/Export buttons grouped by function (Classes, Annotations, Revert, ZIP)
- Reduced horizontal window width for better screen compatibility
- Improved visual hierarchy and accessibility

## 🔧 Technical Improvements

### Bug Fixes
- **Circular Import Resolution**: Broke `training_sync` ↔ `conflict_detection` dependency cycle via standalone `bbox_utils.py`
- **Video Grid Resize**: Fixed grid layout corruption when switching sizes
- **Maximize/Minimize**: Proper widget spanning and layout restoration
- **PFDS Log Spam**: Reduced device polling logs from every 5s to every 30s

### Code Quality
- Removed debug statements from production code
- Enhanced logging for better troubleshooting
- Improved error handling and validation

## 📋 System Requirements

- **Python**: 3.12+
- **UI Framework**: PyQt5
- **ML**: YOLOv8 for object detection
- **Video**: OpenCV + RTSP streaming support
- **Monitoring**: Prometheus metrics endpoint

## 🎯 Key Features

✅ YOLOv8 integration for training & inference  
✅ RTSP multi-stream video processing  
✅ Real-time object detection on video feeds  
✅ Hierarchical class taxonomy management  
✅ Flexible annotation import/export  
✅ PFDS device communication & monitoring  
✅ Thermal imaging calibration tools  
✅ Advanced metrics & analytics dashboard  

## 📚 Documentation

- **CHANGELOG**: Full feature & fix list → [CHANGELOG.md](CHANGELOG.md)
- **Release Checklist**: Testing & deployment → [BETA_V1.0_CHECKLIST.md](BETA_V1.0_CHECKLIST.md)
- **Implementation Guide**: Technical details → [RELEASE_SUMMARY.md](RELEASE_SUMMARY.md)

## 🧪 Testing Status

✅ **Automated Tests**: 4/4 passing (imports, circular import fix, filtered dataset, version)  
✅ **Code Quality**: No syntax errors, all modules validated  
✅ **Manual Testing**: Training workflows, import/export, video wall verified  

## 🔄 What's Coming in v1.1

- Advanced model metrics visualization
- Batch annotation tools
- Active learning recommendations
- Mobile viewer companion app
- Cloud storage integration
- Multi-model comparison dashboard

## 📝 Known Limitations

- PFDS simulator required for device testing
- Video streaming recovery needs improvement
- Batch annotation tools not yet available
- Limited cloud integration in this release

## 🙏 Thank You

This beta represents significant effort in training infrastructure, class management, and UI refinement. We're excited to gather feedback and iterate toward a stable v1.0 release.

**Questions or issues?** Please open a GitHub issue or discussion!

---

**Release Date**: 2025-12-27  
**Commit**: 9e3460b (656 files changed, 860k+ lines)  
**Tag**: v1.0.0-beta
