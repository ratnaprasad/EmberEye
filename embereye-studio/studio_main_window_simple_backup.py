"""
EmberEye Studio - Main Application Window
Central hub for training, model management, and dataset organization
"""

import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QMessageBox, QProgressBar, QGroupBox,
    QFormLayout, QSpinBox, QComboBox, QTextEdit, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

from forgelab import (
    TrainingConfig, TrainingProgress, TrainingStatus, YOLOTrainingPipeline
)


class TrainingTab(QWidget):
    """Training and model management tab"""
    
    def __init__(self):
        super().__init__()
        self.pipeline = None
        self.training_active = False
        self.init_ui()

    def init_ui(self):
        """Initialize training UI"""
        layout = QVBoxLayout()

        # Config section
        config_group = QGroupBox("Training Configuration")
        config_layout = QFormLayout()

        self.project_name = QLabel("fire_detector_v1")
        self.model_size = QComboBox()
        self.model_size.addItems(["nano (n)", "small (s)", "medium (m)", "large (l)", "xlarge (x)"])
        self.model_size.setCurrentText("nano (n)")

        self.epochs = QSpinBox()
        self.epochs.setRange(10, 500)
        self.epochs.setValue(150)

        self.batch_size = QSpinBox()
        self.batch_size.setRange(1, 128)
        self.batch_size.setValue(16)

        self.device = QComboBox()
        self.device.addItems(["auto (auto-detect)", "gpu (0)", "cpu"])
        self.device.setCurrentText("auto (auto-detect)")

        config_layout.addRow("Project Name:", self.project_name)
        config_layout.addRow("Model Size:", self.model_size)
        config_layout.addRow("Epochs:", self.epochs)
        config_layout.addRow("Batch Size:", self.batch_size)
        config_layout.addRow("Device:", self.device)
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Control section
        control_layout = QHBoxLayout()
        
        self.precheck_btn = QPushButton("Pre-check Configuration")
        self.precheck_btn.clicked.connect(self.run_precheck)
        
        self.prepare_btn = QPushButton("Prepare Dataset")
        self.prepare_btn.clicked.connect(self.prepare_dataset)
        
        self.train_btn = QPushButton("Start Training")
        self.train_btn.clicked.connect(self.start_training)
        self.train_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton("Cancel Training")
        self.cancel_btn.clicked.connect(self.cancel_training)
        self.cancel_btn.setEnabled(False)
        
        control_layout.addWidget(self.precheck_btn)
        control_layout.addWidget(self.prepare_btn)
        control_layout.addWidget(self.train_btn)
        control_layout.addWidget(self.cancel_btn)
        layout.addLayout(control_layout)

        # Progress section
        progress_group = QGroupBox("Training Progress")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        
        self.status_text = QLabel("Ready")
        self.status_text.setStyleSheet("color: #666; font-size: 12px;")
        
        self.metrics_text = QTextEdit()
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setPlaceholderText("Training metrics will appear here...")
        self.metrics_text.setMaximumHeight(150)

        progress_layout.addWidget(QLabel("Progress:"))
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_text)
        progress_layout.addWidget(QLabel("Metrics:"))
        progress_layout.addWidget(self.metrics_text)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        layout.addStretch()
        self.setLayout(layout)

    def run_precheck(self):
        """Run pre-training checks"""
        try:
            config = self.get_config()
            pipeline = YOLOTrainingPipeline(config=config)
            success, message = pipeline.precheck_training()
            
            if success:
                QMessageBox.information(self, "Pre-check Passed", message)
                self.train_btn.setEnabled(True)
            else:
                QMessageBox.critical(self, "Pre-check Failed", message)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Pre-check error: {str(e)}")

    def prepare_dataset(self):
        """Prepare dataset for training"""
        try:
            config = self.get_config()
            pipeline = YOLOTrainingPipeline(config=config)
            
            self.status_text.setText("Preparing dataset...")
            success, message = pipeline.dataset_manager.prepare_dataset(config)
            
            if success:
                self.status_text.setText(f"✓ {message}")
                self.metrics_text.setText(f"Dataset prepared successfully!\n\n{message}")
                QMessageBox.information(self, "Success", message)
                self.train_btn.setEnabled(True)
            else:
                self.status_text.setText(f"✗ Dataset preparation failed")
                self.metrics_text.setText(f"Error: {message}")
                QMessageBox.critical(self, "Error", message)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Preparation error: {str(e)}")

    def get_config(self) -> TrainingConfig:
        """Get current training configuration"""
        model_size = self.model_size.currentText().split()[0]
        device = self.device.currentText().split()[0]
        
        return TrainingConfig(
            project_name=self.project_name.text(),
            model_size=model_size,
            epochs=self.epochs.value(),
            batch_size=self.batch_size.value(),
            device=device
        )

    def start_training(self):
        """Start training"""
        try:
            config = self.get_config()
            self.pipeline = YOLOTrainingPipeline(config=config)
            
            # Set callbacks for progress
            self.pipeline.set_progress_callback(self.on_training_progress)
            
            self.training_active = True
            self.train_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.prepare_btn.setEnabled(False)
            
            self.status_text.setText("Starting training...")
            
            # Run training in main thread (would need QThread for non-blocking in production)
            success, message = self.pipeline.run_full_pipeline()
            
            if success:
                self.status_text.setText("✓ Training completed successfully!")
                self.progress_bar.setValue(100)
                best_model = self.pipeline.get_best_model_path()
                msg = f"{message}\n\nBest model saved at:\n{best_model}"
                QMessageBox.information(self, "Training Complete", msg)
            else:
                self.status_text.setText(f"✗ Training failed: {message}")
                QMessageBox.critical(self, "Training Failed", message)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Training error: {str(e)}")
        finally:
            self.training_active = False
            self.train_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.prepare_btn.setEnabled(True)

    def cancel_training(self):
        """Cancel running training"""
        if self.pipeline:
            self.pipeline.training_active = False
            self.status_text.setText("Training cancelled by user")
            QMessageBox.information(self, "Cancelled", "Training cancellation requested")

    def on_training_progress(self, progress: TrainingProgress):
        """Handle training progress update"""
        if progress.total_epochs > 0:
            percent = int((progress.current_epoch / progress.total_epochs) * 100)
            self.progress_bar.setValue(percent)
        
        # Update metrics display
        metrics_str = (
            f"Status: {progress.status.value}\n"
            f"Epoch: {progress.current_epoch}/{progress.total_epochs}\n"
            f"Loss: {progress.loss:.4f}\n"
            f"mAP50: {progress.map50:.4f}\n"
            f"Precision: {progress.precision:.4f}\n"
            f"Recall: {progress.recall:.4f}\n"
            f"ETA: {progress.eta_seconds}s\n"
            f"Message: {progress.message}"
        )
        self.metrics_text.setText(metrics_str)
        self.status_text.setText(progress.message)


class DatasetTab(QWidget):
    """Dataset management tab"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize dataset UI"""
        layout = QVBoxLayout()

        title = QLabel("Dataset Management")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Import section
        import_group = QGroupBox("Import Incident Data")
        import_layout = QVBoxLayout()

        info = QLabel(
            "Import incident ZIP files exported from EmberEye Field Edition.\n"
            "Each ZIP should contain frames and annotation metadata."
        )
        info.setStyleSheet("color: #666; font-size: 11px;")

        import_btn = QPushButton("Import ZIP File")
        import_btn.clicked.connect(self.import_dataset)

        import_layout.addWidget(info)
        import_layout.addWidget(import_btn)
        import_group.setLayout(import_layout)
        layout.addWidget(import_group)

        # Dataset list section
        list_group = QGroupBox("Available Datasets")
        list_layout = QVBoxLayout()

        self.dataset_list = QTextEdit()
        self.dataset_list.setReadOnly(True)
        self.dataset_list.setPlaceholderText("Imported datasets will appear here...")
        list_layout.addWidget(self.dataset_list)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        layout.addStretch()
        self.setLayout(layout)

    def import_dataset(self):
        """Import dataset from ZIP"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Incident ZIP", "", "ZIP Files (*.zip)"
        )
        if file_path:
            QMessageBox.information(
                self, "Import", 
                f"Dataset import feature coming soon!\n\nSelected: {Path(file_path).name}"
            )


class SettingsTab(QWidget):
    """Settings and configuration tab"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize settings UI"""
        layout = QVBoxLayout()

        title = QLabel("Settings")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Workspace settings
        ws_group = QGroupBox("Workspace Configuration")
        ws_layout = QFormLayout()

        training_dir = QLabel("./training_data")
        ws_layout.addRow("Training Data Directory:", training_dir)

        models_dir = QLabel("./models")
        ws_layout.addRow("Models Directory:", models_dir)

        ws_group.setLayout(ws_layout)
        layout.addWidget(ws_group)

        # About section
        about_group = QGroupBox("About")
        about_layout = QVBoxLayout()

        about_text = QLabel(
            "EmberEye Studio v1.0.0\n"
            "Training and Model Development Hub\n\n"
            "ForgeLab Module - Phoenix Cycle Training\n"
            "© EmberEye Team 2026"
        )
        about_text.setAlignment(Qt.AlignCenter)
        about_layout.addWidget(about_text)
        about_group.setLayout(about_layout)
        layout.addWidget(about_group)

        layout.addStretch()
        self.setLayout(layout)


class StudioMainWindow(QMainWindow):
    """Main application window for EmberEye Studio"""
    
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.init_ui()

    def init_ui(self):
        """Initialize main UI"""
        self.setWindowTitle(f"EmberEye Studio - {self.username}")
        self.setGeometry(100, 100, 1200, 800)

        # Central widget
        central_widget = QWidget()
        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("🔥 EmberEye Studio")
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)

        user_label = QLabel(f"User: {self.username}")
        user_label.setAlignment(Qt.AlignRight)
        user_label.setStyleSheet("color: #666; font-size: 11px;")

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(user_label)
        layout.addLayout(header_layout)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(TrainingTab(), "Training (ForgeLab)")
        tabs.addTab(DatasetTab(), "Datasets (EmberArchive)")
        tabs.addTab(SettingsTab(), "Settings")

        layout.addWidget(tabs)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Apply stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QTabWidget::pane {
                border: 1px solid #ddd;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                color: #333;
                padding: 8px 20px;
                margin: 2px;
                border-radius: 3px;
            }
            QTabBar::tab:selected {
                background-color: #2196F3;
                color: white;
            }
            QPushButton {
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                background-color: #2196F3;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 15px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
            }
        """)
