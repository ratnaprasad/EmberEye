# Model Manager Integration Guide

## 🎯 How to Add Model Manager to EmberEye Settings

The Model Manager modal provides a centralized UI for:
- ✅ Viewing all trained models in system
- ✅ Seeing which model is currently active for video analysis
- ✅ Importing new model packages
- ✅ Exporting models for distribution
- ✅ Switching active model (updates real-time video streams)
- ✅ Managing model versions and device types (CPU/GPU/MPS)

---

## 📍 Integration Steps

### Step 1: Add Menu Item to Settings

In [main_window.py](main_window.py), find the `init_settings_menu()` method (~line 1626):

```python
def init_settings_menu(self, title_bar):
    menu_btn = QToolButton()
    menu_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
    menu_btn.setPopupMode(QToolButton.InstantPopup)
    menu = QMenu()
    menu.addAction("Profile", self.show_profile)
    menu.addAction("Configure Streams", self.configure_streams)
    # ... other menu items ...
    
    # ➕ ADD THIS LINE:
    menu.addAction("🤖 Model Manager...", self.show_model_manager)
    
    # ... rest of menu setup ...
```

### Step 2: Add Handler Method

Add this method to the MainWindow class:

```python
def show_model_manager(self):
    """Open Model Manager modal."""
    from model_manager_modal import ModelManagerModal
    
    dialog = ModelManagerModal(self)
    
    # Connect model change signal to update video streams
    def on_model_changed(model_path):
        logger.info(f"Model changed to: {model_path}")
        # Update all active video stream processors
        self.update_video_streams_model(model_path)
    
    dialog.model_changed.connect(on_model_changed)
    dialog.exec_()

def update_video_streams_model(self, model_path):
    """Update all video stream detectors with new model."""
    logger.info(f"Updating video streams with model: {model_path}")
    
    # Update all detector instances used in video tabs/videowall
    if hasattr(self, 'videowall_tabs'):
        for tab_name, tab_widget in self.videowall_tabs.items():
            if hasattr(tab_widget, 'detector'):
                logger.info(f"Updating detector in tab: {tab_name}")
                # Reinitialize detector with new model
                # (implementation depends on your VideoStreamProcessor)
```

### Step 3: Use in Video Processing

In your video stream processor (e.g., `anomalies.py` or similar):

```python
from model_manager_modal import ModelManagerIntegration

class VideoStreamProcessor:
    def __init__(self):
        # Get active model path
        model_path = ModelManagerIntegration.get_active_model_path()
        logger.info(f"Loading model: {model_path}")
        
        # Load YOLO model
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))
    
    def process_frame(self, frame):
        # Use model for detection
        results = self.model(frame)
        return results
```

---

## 🎨 UI Structure

```
Model Manager Modal
├── 📦 Header
│   ├── Title: "Trained Models Manager"
│   └── Refresh Button
│
├── 📊 Left Panel: Models List
│   ├── Table with columns:
│   │   ├── Model (name/version)
│   │   ├── Device (CPU/GPU/MPS)
│   │   ├── Status (ACTIVE/Idle)
│   │   └── Version (v1, v2, v3...)
│   └── Click to select model
│
├── 📋 Right Panel: Model Details
│   ├── Model Information
│   │   ├── Name
│   │   ├── Path
│   │   ├── Device Type
│   │   ├── File Size
│   │   └── Metadata
│   │
│   ├── Active Model for Video Analysis
│   │   └── Shows currently active model
│   │
│   └── Actions
│       ├── ✓ Activate for Video Analysis
│       └── 🗑️ Delete Model
│
├── 📥 Status Bar
│   └── Shows current status/messages
│
└── 🔘 Buttons
    ├── 📥 Import Model Package
    ├── 📤 Export Selected Model
    └── Close
```

---

## 💾 File Locations After Setup

```
models/
├── yolo_versions/
│   ├── v1/
│   │   └── weights/
│   │       ├── best.pt
│   │       └── EmberEye.pt
│   ├── v2/
│   │   └── weights/
│   │       ├── best.pt
│   │       └── EmberEye.pt          ← Active (shown in manager)
│   ├── current_best.pt ──→ v2/weights/EmberEye.pt
│   └── exports/
│       └── packages/EmberEye_v2_auto_all.zip
│
└── EmberEye.pt                      ← Fallback model
```

**Model Manager displays:**
- ✓ v2 (cpu) - 120MB - ACTIVE
- ⚪ v2 (gpu) - 120MB - Idle
- ⚪ v2 (mps) - 120MB - Idle
- ⚪ v1 (cpu) - 120MB - Idle

---

## 🔄 Workflow: Switching Models

### Before (Manual):
```
1. Train new model (v2)
2. Manually update config files
3. Restart video streams
4. Hope detections work
```

### After (With Model Manager):
```
1. Train new model (v2)
2. Open Settings → Model Manager
3. See v1 and v2 listed
4. Click "Activate for Video Analysis" on v2
5. Video streams auto-update with new model
6. See performance improvements immediately
```

---

## 📊 Features Explained

### 1. View All Models
```
Table shows:
- Model name/version
- Device type (CPU/GPU/MPS)
- Status (ACTIVE or Idle)
- Version number from metadata

Easy to see what's available!
```

### 2. Import Package
```
Click: 📥 Import Model Package
  → File browser opens
  → Select EmberEye_v2_auto_all.zip
  → Auto-detects device capabilities
  → Backs up old model
  → Imports new model
  → Refreshes list

One-click deployment!
```

### 3. Activate Model
```
1. Select model from table
2. Click: ✓ Activate for Video Analysis
3. Signal emitted: model_changed(path)
4. Video processors update
5. New model active on all video streams

Zero downtime model switch!
```

### 4. Export Model
```
Click: 📤 Export Selected Model
  → Calls ModelDeployer
  → Creates package with all variants
  → Saves to chosen location
  → Ready to distribute

Easy deployment!
```

---

## 🎯 Integration with Video Streams

### Current Flow (Before):
```
VideoStreamProcessor
  └── Hardcoded model path: "models/yolov8n.pt"
      (Requires code change to update)
```

### New Flow (After):
```
Settings Menu
  └── 🤖 Model Manager
      └── Select Active Model
          └── model_changed signal
              └── VideoStreamProcessor.update_model()
                  └── Reload model with new weights
                      └── Continue analysis with new model
```

---

## 📝 Code Example: Full Integration

```python
# In main_window.py

from model_manager_modal import ModelManagerModal, ModelManagerIntegration
from pathlib import Path

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... initialization ...
        
        # Initialize with active model from manager
        self.current_model_path = ModelManagerIntegration.get_active_model_path()
        self.init_video_processors()
    
    def init_settings_menu(self, title_bar):
        """Add Model Manager to settings."""
        menu_btn = QToolButton()
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu()
        
        # Existing menu items
        menu.addAction("Profile", self.show_profile)
        menu.addAction("Configure Streams", self.configure_streams)
        menu.addSeparator()
        
        # ➕ NEW: Model Manager
        menu.addAction("🤖 Model Manager...", self.show_model_manager)
        
        menu.addSeparator()
        menu.addAction("Logout", self.logout)
        menu_btn.setMenu(menu)
        title_bar.addWidget(menu_btn)
    
    def show_model_manager(self):
        """Open Model Manager modal."""
        dialog = ModelManagerModal(self)
        dialog.model_changed.connect(self.on_model_changed)
        dialog.exec_()
    
    def on_model_changed(self, model_path: str):
        """Handle model change from Model Manager."""
        logger.info(f"Model changed to: {model_path}")
        self.current_model_path = Path(model_path)
        
        # Update all video processors
        self.update_all_video_streams()
    
    def init_video_processors(self):
        """Initialize video stream processors with active model."""
        # Example: Initialize videowall tabs
        if hasattr(self, 'videowall_tabs'):
            for tab_name, tab_widget in self.videowall_tabs.items():
                self.initialize_stream_processor(tab_widget)
    
    def initialize_stream_processor(self, tab_widget):
        """Initialize or update stream processor with current model."""
        try:
            from ultralytics import YOLO
            
            model = YOLO(str(self.current_model_path))
            tab_widget.detector_model = model
            
            logger.info(f"Stream processor initialized with: {self.current_model_path}")
        except Exception as e:
            logger.error(f"Failed to initialize stream processor: {e}")
    
    def update_all_video_streams(self):
        """Update all video streams with new model."""
        logger.info("Updating all video streams...")
        self.init_video_processors()  # Re-initialize with new model
        
        # Show notification
        QMessageBox.information(
            self,
            "Model Updated",
            f"All video streams updated with new model:\n{self.current_model_path}"
        )
```

---

## 🔍 Viewing Active Model in Video Wall

### Option 1: Show in Status Bar
```python
def update_status_bar_model(self):
    """Show active model in status bar."""
    active_model = ModelManagerIntegration.get_active_model_path()
    self.statusBar().showMessage(f"Model: {active_model.name}")
```

### Option 2: Show in Video Tab Title
```python
def update_tab_titles(self):
    """Show model in each tab."""
    for i, tab_name in enumerate(self.videowall_tabs):
        active_model = ModelManagerIntegration.get_active_model_path()
        new_title = f"{tab_name} (Model: {active_model.stem})"
        self.videowall_tabs_widget.setTabText(i, new_title)
```

### Option 3: Overlay on Video
```python
def draw_model_info(self, frame, model_path):
    """Draw model info on video frame."""
    import cv2
    
    text = f"Model: {model_path.stem}"
    cv2.putText(
        frame,
        text,
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )
    return frame
```

---

## ✅ Features Summary

| Feature | Status | Purpose |
|---------|--------|---------|
| View all models | ✅ | See what's available |
| Show active model | ✅ | Know which model is in use |
| Import package | ✅ | Deploy new models |
| Export model | ✅ | Share models |
| Activate model | ✅ | Switch models for video analysis |
| Delete model | ✅ | Clean up unused models |
| Auto-detect device | ✅ | Smart variant selection |
| Model metadata | ✅ | View training info |
| Real-time update | ✅ | No video restart needed |

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Models not showing | Check `models/yolo_versions/` exists |
| Import fails | Verify package format is .zip |
| Model not activating | Check file permissions |
| Video not updating | Ensure video processors reload model |
| Wrong device selected | Check nvidia-smi or Apple Silicon support |

---

## 📚 Related Files

- [model_manager_modal.py](model_manager_modal.py) - UI component
- [model_export_deploy.py](model_export_deploy.py) - Import/export system
- [model_versioning.py](model_versioning.py) - Version management
- [EXPORT_DEPLOYMENT_GUIDE.md](EXPORT_DEPLOYMENT_GUIDE.md) - Deployment workflow

