# Changelog

All notable changes to EmberEye will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-beta] - 2025-12-27

### Added
- **Quick Retrain Feature**: Shorter training runs (10-25 epochs) for rapid iteration
  - Full dataset mode for comprehensive retraining
  - Filtered dataset mode for focused retraining on unclassified items only
- **Class Consistency System**: Automatic handling of taxonomy changes
  - Snapshot class metadata in annotation JSON files
  - Orphaned class detection and remapping to `unclassified_*` categories
  - Save-time warning dialog when class taxonomy is modified
- **Post-Training Summary**: Comprehensive report after training completion
  - Unclassified item counts by category
  - Option to review and re-annotate unclassified items
  - Quick access to filtered retraining workflow
- **Review Unclassified Dialog**: Browse and manage items remapped during training
  - List all unclassified items with file paths
  - Quick navigation to annotation folder
  - Direct launch of annotation tool
- **Import/Export System**: Comprehensive data management
  - Export/Import class hierarchy (JSON packages with provenance)
  - Export/Import annotations (JSON packages with metadata)
  - Export/Import ZIP archives (images + labels + metadata)
  - Revert from backups for classes and annotations
  - Conflict detection and merge strategies
- **Video Wall Enhancements**
  - Dynamic grid layouts: 2×2, 3×3, 4×4, 5×5
  - Maximize/minimize individual video widgets
  - Smooth grid resize with proper layout recalculation
  - Pagination for large camera arrays
  - Group filtering for organized viewing
- **Training Tab Reorganization**
  - 2-column grid layout for import/export buttons
  - Logical grouping: Classes, Annotations, Revert, ZIP
  - Reduced horizontal window width
  - Better visual hierarchy

### Fixed
- **Circular Import**: Broke `training_sync` ↔ `conflict_detection` dependency cycle by creating standalone `bbox_utils.py`
- **Grid Resize**: Video wall grid now properly resets row/column stretches when switching sizes (e.g., 2×2 ↔ 3×3)
- **Maximize/Minimize**: 
  - Widgets now span entire grid correctly instead of just hiding others
  - Grid positions captured before modifications to prevent corruption
  - Proper restoration of original layout on minimize
- **PFDS Log Spam**: Reduced PERIOD_ON retry logging from every 5s to every 30s

### Changed
- **Dataset Structure**: Annotations now include metadata JSON alongside YOLO labels
  - `frame_XXXXX.json` contains class_mapping, leaf_classes, timestamp, version
  - Enables audit trail and graceful handling of class changes
- **Training Pipeline**: Enhanced DatasetManager with orphan detection and remapping
  - Pre-scan for missing classes before dataset preparation
  - Automatic `unclassified_<category>` generation
  - Label ID remapping to preserve training integrity
- **Logging**: Consolidated debug output, reduced noise in production logs

### Technical
- Python 3.12+ compatibility
- PyQt5 UI framework
- YOLOv8 integration for object detection
- OpenCV for video processing
- RTSP stream support
- WebSocket for sensor data
- Prometheus metrics endpoint

### Known Limitations
- PFDS connection requires manual simulator setup
- Video streaming recovery needs improvement
- No batch annotation tools yet
- Limited cloud storage integration

### Migration Notes
- Existing annotations without metadata JSON will work but won't benefit from class change protection
- Re-annotate critical frames to generate metadata snapshots
- Backup your data before upgrading

---

## [Unreleased]

### Planned for v1.1
- Advanced model metrics visualization
- Batch annotation tools
- Active learning suggestions
- Mobile viewer companion app
- Cloud storage integration
- Multi-model comparison dashboard

---

## Version History

- **1.0.0-beta** (2025-12-27): First beta release with comprehensive training workflow
