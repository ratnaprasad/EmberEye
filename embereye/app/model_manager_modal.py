"""
Model Manager Modal - UI Component for Managing Trained Models

Integrates into EmberEye Settings Menu
Shows:
- List of available models in system
- Currently active model
- Option to import/export models
- Device type for each model
- Model metrics and metadata
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QFileDialog, QComboBox, QSplitter,
    QWidget, QTabWidget, QListWidget, QListWidgetItem, QStatusBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor
import logging

logger = logging.getLogger(__name__)


class ModelInfo:
    """Information about a model."""
    
    def __init__(self, name: str, path: Path, device_type: str = "cpu"):
        self.name = name
        self.path = path
        self.device_type = device_type  # cpu, gpu, mps
        self.is_active = False
        self.metadata = {}
        self.load_metadata()
    
    def load_metadata(self):
        """Load model metadata if available."""
        try:
            # Look for metadata.json in same directory
            config_file = self.path.with_suffix('.json')
            if config_file.exists():
                with open(config_file, 'r') as f:
                    self.metadata = json.load(f)
        except Exception as e:
            logger.debug(f"No metadata for {self.name}: {e}")
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'path': str(self.path),
            'device_type': self.device_type,
            'is_active': self.is_active,
            'metadata': self.metadata
        }


class ModelManagerModal(QDialog):
    """
    Modal dialog for managing trained models.
    Integrates into Settings menu.
    """
    
    model_changed = pyqtSignal(str)  # Emits path to selected model
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 Model Manager - EmberEye")
        self.setGeometry(100, 100, 1000, 600)
        
        self.models_dir = Path("./models/yolo_versions")
        self.available_models: List[ModelInfo] = []
        self.active_model: Optional[ModelInfo] = None
        
        self.init_ui()
        self.refresh_model_list()
    
    def init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout()
        
        # ========== HEADER ==========
        header_layout = QHBoxLayout()
        header_label = QLabel("📦 Trained Models Manager")
        header_label.setFont(QFont("Arial", 12, QFont.Bold))
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_model_list)
        header_layout.addWidget(refresh_btn)
        layout.addLayout(header_layout)
        
        # ========== MAIN CONTENT (SPLITTER) ==========
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel: Available models list
        left_panel = self.create_models_list_panel()
        
        # Right panel: Model details and actions
        right_panel = self.create_model_details_panel()
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        # ========== STATUS BAR ==========
        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)
        self.update_status("Ready")
        
        # ========== BUTTONS ==========
        button_layout = QHBoxLayout()
        
        import_btn = QPushButton("📥 Import Model Package")
        import_btn.clicked.connect(self.import_model_package)
        button_layout.addWidget(import_btn)
        
        export_btn = QPushButton("📤 Export Selected Model")
        export_btn.clicked.connect(self.export_selected_model)
        button_layout.addWidget(export_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def create_models_list_panel(self) -> QWidget:
        """Create left panel with models list."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Available Models")
        title.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(title)
        
        # Models table
        self.models_table = QTableWidget()
        self.models_table.setColumnCount(4)
        self.models_table.setHorizontalHeaderLabels(["Model", "Device", "Status", "Version"])
        self.models_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.models_table.setSelectionMode(QTableWidget.SingleSelection)
        self.models_table.itemSelectionChanged.connect(self.on_model_selected)
        layout.addWidget(self.models_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_model_details_panel(self) -> QWidget:
        """Create right panel with model details."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Model Details")
        title.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(title)
        
        # Details display
        self.details_text = QLabel("Select a model to view details")
        self.details_text.setWordWrap(True)
        self.details_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.details_text)
        
        layout.addSpacing(20)
        
        # Active model info
        active_label = QLabel("Active Model for Video Analysis")
        active_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(active_label)
        
        self.active_model_label = QLabel("None (Using default)")
        self.active_model_label.setStyleSheet("QLabel { color: #ff9800; font-weight: bold; }")
        layout.addWidget(self.active_model_label)
        
        layout.addSpacing(20)
        
        # Actions
        actions_label = QLabel("Actions")
        actions_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(actions_label)
        
        activate_btn = QPushButton("✓ Activate for Video Analysis")
        activate_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        activate_btn.clicked.connect(self.activate_selected_model)
        layout.addWidget(activate_btn)
        
        delete_btn = QPushButton("🗑️ Delete Model")
        delete_btn.clicked.connect(self.delete_selected_model)
        layout.addWidget(delete_btn)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def refresh_model_list(self):
        """Refresh the list of available models."""
        self.available_models = []
        
        # Scan models directory for available models
        self.find_available_models()
        
        # Update table
        self.models_table.setRowCount(len(self.available_models))
        
        for row, model in enumerate(self.available_models):
            # Model name
            name_item = QTableWidgetItem(model.name)
            self.models_table.setItem(row, 0, name_item)
            
            # Device type
            device_item = QTableWidgetItem(model.device_type.upper())
            if model.device_type == "gpu":
                device_item.setForeground(QColor("#00ff00"))
            elif model.device_type == "mps":
                device_item.setForeground(QColor("#ff9800"))
            self.models_table.setItem(row, 1, device_item)
            
            # Status
            status = "🟢 ACTIVE" if model.is_active else "⚪ Idle"
            status_item = QTableWidgetItem(status)
            self.models_table.setItem(row, 2, status_item)
            
            # Version (from metadata)
            version = model.metadata.get('version', 'N/A')
            version_item = QTableWidgetItem(version)
            self.models_table.setItem(row, 3, version_item)
        
        # Resize columns
        self.models_table.resizeColumnsToContents()
        
        self.update_status(f"Found {len(self.available_models)} model(s)")
    
    def find_available_models(self):
        """Find all available models in the system."""
        # Check versioned models
        if self.models_dir.exists():
            for version_dir in self.models_dir.glob("v*/weights"):
                # Check for EmberEye.pt variants
                for model_file in version_dir.glob("EmberEye*.pt"):
                    device_type = self.extract_device_type(model_file.name)
                    version = version_dir.parent.name
                    
                    model_info = ModelInfo(
                        name=f"{version} ({device_type})",
                        path=model_file,
                        device_type=device_type
                    )
                    
                    # Check if this is the active model
                    current_best = self.models_dir / "current_best.pt"
                    if current_best.exists() and current_best.resolve() == model_file.resolve():
                        model_info.is_active = True
                        self.active_model = model_info
                    
                    self.available_models.append(model_info)
        
        # Also check default models directory
        default_models_dir = Path("./models")
        if default_models_dir.exists():
            for model_file in default_models_dir.glob("EmberEye*.pt"):
                if model_file not in [m.path for m in self.available_models]:
                    device_type = self.extract_device_type(model_file.name)
                    model_info = ModelInfo(
                        name=model_file.stem,
                        path=model_file,
                        device_type=device_type
                    )
                    self.available_models.append(model_info)
    
    @staticmethod
    def extract_device_type(filename: str) -> str:
        """Extract device type from model filename."""
        if "gpu" in filename:
            return "gpu"
        elif "mps" in filename:
            return "mps"
        else:
            return "cpu"
    
    def on_model_selected(self):
        """Handle model selection."""
        selected_rows = self.models_table.selectedIndexes()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        model = self.available_models[row]
        
        # Update details panel
        details = f"""
<b>Model Information</b><br>
<b>Name:</b> {model.name}<br>
<b>Path:</b> {model.path}<br>
<b>Device Type:</b> {model.device_type.upper()}<br>
<b>File Size:</b> {self.get_file_size(model.path)}<br>
<br>
<b>Metadata:</b><br>
"""
        
        if model.metadata:
            for key, value in model.metadata.items():
                if key != 'config_snapshot':
                    details += f"<b>{key}:</b> {value}<br>"
        else:
            details += "No metadata available<br>"
        
        self.details_text.setText(details)
    
    @staticmethod
    def get_file_size(path: Path) -> str:
        """Get human-readable file size."""
        if not path.exists():
            return "N/A"
        
        size_bytes = path.stat().st_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
    
    def activate_selected_model(self):
        """Activate selected model for video analysis."""
        selected_rows = self.models_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "Error", "Please select a model first")
            return
        
        row = selected_rows[0].row()
        model = self.available_models[row]
        
        # Deactivate all others
        for m in self.available_models:
            m.is_active = False
        
        # Activate selected
        model.is_active = True
        self.active_model = model
        
        # Emit signal
        self.model_changed.emit(str(model.path))
        
        # Update UI
        self.active_model_label.setText(f"✓ {model.name}")
        self.update_status(f"Activated: {model.name}")
        
        QMessageBox.information(
            self,
            "Success",
            f"Model '{model.name}' is now active for video stream analysis.\n\n"
            f"Path: {model.path}\n"
            f"Device: {model.device_type.upper()}\n\n"
            f"Restart video streams to apply changes."
        )
        
        self.refresh_model_list()
    
    def delete_selected_model(self):
        """Delete selected model."""
        selected_rows = self.models_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "Error", "Please select a model first")
            return
        
        row = selected_rows[0].row()
        model = self.available_models[row]
        
        if model.is_active:
            QMessageBox.warning(self, "Error", "Cannot delete active model. Activate another model first.")
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete model: {model.name}?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                model.path.unlink()
                self.update_status(f"Deleted: {model.name}")
                QMessageBox.information(self, "Success", f"Model '{model.name}' deleted")
                self.refresh_model_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete model: {e}")
    
    def import_model_package(self):
        """Import a model package."""
        from model_export_deploy import ModelImporter
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Model Package",
            "",
            "Zip Files (*.zip);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Determine install directory
        install_dir = Path("./models")
        install_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            importer = ModelImporter(str(install_dir))
            success, msg = importer.import_model_package(file_path, device_type="auto")
            
            if success:
                QMessageBox.information(self, "Success", f"Model imported:\n{msg}")
                self.update_status("Model imported successfully")
            else:
                QMessageBox.critical(self, "Error", f"Import failed:\n{msg}")
            
            self.refresh_model_list()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Import error: {e}")
    
    def export_selected_model(self):
        """Export selected model."""
        selected_rows = self.models_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "Error", "Please select a model first")
            return
        
        row = selected_rows[0].row()
        model = self.available_models[row]
        
        # Extract version number from name (e.g., "v2" from "v2 (gpu)")
        version = model.name.split(" ")[0] if " " in model.name else "unknown"
        
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Model Package",
            f"EmberEye_{version}.zip",
            "Zip Files (*.zip)"
        )
        
        if not export_path:
            return
        
        try:
            from model_export_deploy import ModelDeployer
            
            deployer = ModelDeployer(str(self.models_dir / "exports"))
            success, package = deployer.create_deployment_package(version, "auto", "all")
            
            if success:
                import shutil
                shutil.copy(package, export_path)
                QMessageBox.information(self, "Success", f"Model exported to:\n{export_path}")
                self.update_status(f"Exported to {export_path}")
            else:
                QMessageBox.critical(self, "Error", f"Export failed: {package}")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export error: {e}")
    
    def update_status(self, message: str):
        """Update status bar."""
        self.status_bar.showMessage(message)


class ModelManagerIntegration:
    """Integration helper for adding Model Manager to settings."""
    
    @staticmethod
    def add_to_settings_menu(settings_menu):
        """
        Add Model Manager action to settings menu.
        
        Usage in main_window.py:
            ModelManagerIntegration.add_to_settings_menu(self.settings_menu)
        """
        settings_menu.addAction("🤖 Model Manager...", lambda: ModelManagerModal().exec_())
    
    @staticmethod
    def get_active_model_path() -> Optional[Path]:
        """Get path to active model."""
        models_dir = Path("./models/yolo_versions")
        current_best = models_dir / "current_best.pt"
        
        if current_best.exists():
            return current_best.resolve()
        
        # Fallback to default
        default_model = Path("./models/EmberEye.pt")
        if default_model.exists():
            return default_model
        
        return None


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    manager = ModelManagerModal()
    manager.show()
    sys.exit(app.exec_())
