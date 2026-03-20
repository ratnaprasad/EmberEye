# Quick Integration - Copy & Paste Code Snippets

## 🎯 Add Model Manager to main_window.py

### 1️⃣ Modify `init_settings_menu()` method

**Location:** Around line 1626 in main_window.py

**Find this code:**
```python
def init_settings_menu(self, title_bar):
    menu_btn = QToolButton()
    menu_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
    menu_btn.setPopupMode(QToolButton.InstantPopup)
    menu = QMenu()
    menu.addAction("Profile", self.show_profile)
    menu.addAction("Configure Streams", self.configure_streams)
    menu.addAction("Reset Streams", self.reset_streams)
    # Add backup/restore actions
    menu.addSeparator()
    menu.addAction("Backup Configuration", self.backup_config)
    menu.addAction("Restore Configuration", self.restore_config)
    menu.addSeparator()
    menu.addAction("TCP Server Port...", self.show_tcp_port_dialog)
    menu.addAction("Thermal Grid Settings...", self.show_thermal_grid_config)
```

**Replace with:**
```python
def init_settings_menu(self, title_bar):
    menu_btn = QToolButton()
    menu_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
    menu_btn.setPopupMode(QToolButton.InstantPopup)
    menu = QMenu()
    menu.addAction("Profile", self.show_profile)
    menu.addAction("Configure Streams", self.configure_streams)
    menu.addAction("Reset Streams", self.reset_streams)
    # Add backup/restore actions
    menu.addSeparator()
    menu.addAction("Backup Configuration", self.backup_config)
    menu.addAction("Restore Configuration", self.restore_config)
    menu.addSeparator()
    menu.addAction("TCP Server Port...", self.show_tcp_port_dialog)
    menu.addAction("Thermal Grid Settings...", self.show_thermal_grid_config)
    # ➕ ADD THIS LINE:
    menu.addAction("🤖 Model Manager...", self.show_model_manager)
```

---

### 2️⃣ Add Handler Methods

**Add these methods to the MainWindow class:**

```python
def show_model_manager(self):
    """Open Model Manager modal for managing trained models."""
    from model_manager_modal import ModelManagerModal
    
    dialog = ModelManagerModal(self)
    
    # Connect model change signal
    def on_model_changed(model_path):
        logger.info(f"🔄 Model changed to: {model_path}")
        self.update_video_streams_model(model_path)
    
    dialog.model_changed.connect(on_model_changed)
    dialog.exec_()

def update_video_streams_model(self, model_path):
    """Update all video stream detectors with new model."""
    logger.info(f"📊 Updating video streams with model: {model_path}")
    
    # If using videowall tabs
    if hasattr(self, 'videowall_tabs'):
        for tab_name, tab_widget in self.videowall_tabs.items():
            try:
                from ultralytics import YOLO
                
                # Reload model for this stream
                new_model = YOLO(str(model_path))
                if hasattr(tab_widget, 'detector_model'):
                    tab_widget.detector_model = new_model
                    logger.info(f"✓ Updated stream: {tab_name}")
            except Exception as e:
                logger.error(f"Failed to update stream {tab_name}: {e}")
    
    # Show success notification
    QMessageBox.information(
        self,
        "✓ Model Updated",
        f"All video streams updated with new model\n\nModel: {model_path}"
    )
```

---

## 📊 Example: Video Stream Processor Integration

### Option A: YOLOTrainer-based processor

If you're using `YOLOTrainer` from anomalies.py:

```python
from model_manager_modal import ModelManagerIntegration

class VideoStreamProcessor:
    def __init__(self):
        # Get currently active model
        model_path = ModelManagerIntegration.get_active_model_path()
        logger.info(f"Loading model: {model_path}")
        
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))
    
    def process_frame(self, frame):
        """Process frame with current model."""
        results = self.model(frame)
        return results
    
    def switch_model(self, model_path):
        """Switch to a different model."""
        from ultralytics import YOLO
        
        logger.info(f"Switching model to: {model_path}")
        self.model = YOLO(str(model_path))
```

### Option B: Custom detector

```python
class FireDetector:
    def __init__(self, model_path=None):
        from model_manager_modal import ModelManagerIntegration
        from ultralytics import YOLO
        
        if model_path is None:
            model_path = ModelManagerIntegration.get_active_model_path()
        
        self.model_path = model_path
        self.model = YOLO(str(model_path))
        logger.info(f"Detector initialized with: {model_path}")
    
    def detect(self, frame):
        """Detect objects in frame."""
        results = self.model(frame)
        return results
```

---

## 🎨 Display Active Model Info

### In Status Bar:

```python
def update_status_bar(self):
    """Update status bar with active model info."""
    from model_manager_modal import ModelManagerIntegration
    from pathlib import Path
    
    active_model = ModelManagerIntegration.get_active_model_path()
    if active_model:
        model_name = active_model.stem  # e.g., "EmberEye_gpu"
        self.statusBar().showMessage(f"🤖 Model: {model_name}")
    else:
        self.statusBar().showMessage("🤖 Model: None (Using default)")

# Call in __init__ or after model changes:
# self.update_status_bar()
```

### In Tab Title:

```python
def update_tab_titles_with_model(self):
    """Show model name in tab titles."""
    from model_manager_modal import ModelManagerIntegration
    
    active_model = ModelManagerIntegration.get_active_model_path()
    model_name = active_model.stem if active_model else "default"
    
    if hasattr(self, 'videowall_tab_widget'):
        for i in range(self.videowall_tab_widget.count()):
            tab_label = self.videowall_tab_widget.tabText(i)
            # Remove old model info if present
            if "Model:" in tab_label:
                tab_label = tab_label.split(" (Model:")[0]
            
            new_label = f"{tab_label} (Model: {model_name})"
            self.videowall_tab_widget.setTabText(i, new_label)
```

---

## 🔧 Full Integration Example

Complete code showing everything together:

```python
# At top of main_window.py, add imports:
from model_manager_modal import ModelManagerModal, ModelManagerIntegration
from pathlib import Path

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... existing code ...
        
        # Initialize active model for video streams
        self.current_model_path = ModelManagerIntegration.get_active_model_path()
        logger.info(f"Using model: {self.current_model_path}")
        
        # Initialize video processors
        self.init_video_processors()
    
    def init_settings_menu(self, title_bar):
        """Initialize settings menu with Model Manager."""
        menu_btn = QToolButton()
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu()
        
        # ... existing actions ...
        
        # ➕ ADD MODEL MANAGER:
        menu.addSeparator()
        menu.addAction("🤖 Model Manager...", self.show_model_manager)
        
        menu.addAction("Log Viewer...", self.show_log_viewer_dialog)
        menu.addSeparator()
        menu.addAction("Logout", self.logout)
        
        menu_btn.setMenu(menu)
        title_bar.addWidget(menu_btn)
    
    # ➕ ADD THESE METHODS:
    
    def show_model_manager(self):
        """Open Model Manager modal."""
        dialog = ModelManagerModal(self)
        dialog.model_changed.connect(self.on_model_changed)
        dialog.exec_()
    
    def on_model_changed(self, model_path: str):
        """Handle model change from Model Manager."""
        logger.info(f"🔄 Model switched to: {model_path}")
        self.current_model_path = Path(model_path)
        
        # Update all video processors with new model
        self.update_all_video_streams()
        
        # Update UI elements
        self.update_status_bar()
        self.update_tab_titles_with_model()
    
    def init_video_processors(self):
        """Initialize video stream processors with active model."""
        from ultralytics import YOLO
        
        try:
            model = YOLO(str(self.current_model_path))
            
            # Apply to all video processors/tabs
            if hasattr(self, 'videowall_tabs'):
                for tab_name, tab_widget in self.videowall_tabs.items():
                    tab_widget.detector_model = model
            
            logger.info(f"✓ Video processors initialized with: {self.current_model_path}")
        except Exception as e:
            logger.error(f"Failed to initialize video processors: {e}")
    
    def update_all_video_streams(self):
        """Update all active video streams with new model."""
        logger.info("📊 Updating all video streams...")
        self.init_video_processors()
    
    def update_status_bar(self):
        """Update status bar with active model."""
        if self.current_model_path:
            model_name = self.current_model_path.stem
            self.statusBar().showMessage(f"🤖 Model: {model_name}")
    
    def update_tab_titles_with_model(self):
        """Update tab titles to show active model."""
        if not self.current_model_path:
            return
        
        model_name = self.current_model_path.stem
        if hasattr(self, 'videowall_tab_widget'):
            for i in range(self.videowall_tab_widget.count()):
                tab_label = self.videowall_tab_widget.tabText(i)
                # Remove old model info
                if " (Model:" in tab_label:
                    tab_label = tab_label.split(" (Model:")[0]
                
                new_label = f"{tab_label} (Model: {model_name})"
                self.videowall_tab_widget.setTabText(i, new_label)
```

---

## ✅ Implementation Checklist

- [ ] Copy `model_manager_modal.py` to project
- [ ] Import ModelManagerModal in main_window.py
- [ ] Add menu item to `init_settings_menu()`
- [ ] Add `show_model_manager()` method
- [ ] Add `on_model_changed()` method
- [ ] Add `update_video_streams_model()` method
- [ ] Update video processors to use active model
- [ ] (Optional) Show model in status bar
- [ ] (Optional) Show model in tab titles
- [ ] Test: Open Model Manager from Settings
- [ ] Test: Select different model
- [ ] Test: Video stream updates
- [ ] Done! 🎉

---

## 🎯 You Now Have

✅ Centralized model management UI  
✅ View all available models  
✅ See which model is active  
✅ Import new models  
✅ Export models  
✅ Switch models for real-time video analysis  
✅ No restart needed (hot-swap models)  
✅ Full device type support (CPU/GPU/MPS)  

Perfect for production deployments! 🚀

