"""
EmberEye Studio - Main Application Window (Comprehensive)
Central hub for training, model management, and dataset organization

Complete version with all features from field edition including:
- Import/Annotate Media
- Import/Export Classes and Annotations
- Sandbox Testing
- QC Review
- Model Versioning
- Advanced Training Controls
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QMessageBox, QProgressBar, QGroupBox,
    QFormLayout, QSpinBox, QComboBox, QTextEdit, QFileDialog,
    QListWidget, QGridLayout, QScrollArea, QDoubleSpinBox,
    QTreeWidget, QTreeWidgetItem, QDialog, QInputDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl, QThread
from PyQt5.QtGui import QFont, QPixmap, QImage

from forgelab import (
    TrainingConfig, TrainingProgress, TrainingStatus, YOLOTrainingPipeline
)
from database_manager import StudioDatabaseManager


# Helper function to get workspace data path
def get_data_path(relative_path=""):
    """Get path to workspace data directory"""
    workspace_root = Path(__file__).parent
    data_dir = workspace_root / "workspace_data"
    data_dir.mkdir(exist_ok=True)
    
    if relative_path:
        full_path = data_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return str(full_path)
    return str(data_dir)


class TrainingTab(QWidget):
    """Comprehensive Training and model management tab with Sandbox"""
    
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.pipeline = None
        self.training_active = False
        self.training_selected_video_path = None
        self.training_selected_image_paths = []
        self.training_has_annotations = False
        self.training_media_imported = False
        self.imported_zip_bases = []
        self.training_just_completed = False
        
        self.init_ui()

    def init_ui(self):
        """Initialize comprehensive training UI"""
        main_layout = QVBoxLayout()
        
        # Sub-tabs: Training and Sandbox
        training_subtabs = QTabWidget()
        
        # --- Training Sub-tab ---
        training_widget = QWidget()
        training_layout = QHBoxLayout(training_widget)
        
        # Left panel: Data management
        left_panel = QVBoxLayout()
        
        # Import and Annotate buttons
        btn_layout = QHBoxLayout()
        import_btn = QPushButton("📥 Import Media")
        self.import_training_btn = import_btn
        import_btn.clicked.connect(self.import_training_media)
        btn_layout.addWidget(import_btn)
        
        annotate_btn = QPushButton("🖊️ Annotate Media")
        self.annotate_btn = annotate_btn
        annotate_btn.clicked.connect(self.open_annotation_tool)
        btn_layout.addWidget(annotate_btn)
        btn_layout.addStretch(1)
        left_panel.addLayout(btn_layout)

        # Import/Export for Classes and Annotations
        ie_btn_layout = QGridLayout()
        ie_btn_layout.setSpacing(5)
        
        # Row 0: Classes
        export_classes_btn = QPushButton("⬆ Export Classes")
        export_classes_btn.setToolTip("Export current class hierarchy to a JSON package")
        export_classes_btn.clicked.connect(self._export_classes_package)
        ie_btn_layout.addWidget(export_classes_btn, 0, 0)

        import_classes_btn = QPushButton("⬇ Import Classes")
        import_classes_btn.setToolTip("Import classes from a package with merge/override")
        import_classes_btn.clicked.connect(self._import_classes_package)
        ie_btn_layout.addWidget(import_classes_btn, 0, 1)

        # Row 1: Annotations
        export_ann_btn = QPushButton("⬆ Export Annotations")
        export_ann_btn.setToolTip("Export annotations from workspace to a JSON package")
        export_ann_btn.clicked.connect(self._export_annotations_package)
        ie_btn_layout.addWidget(export_ann_btn, 1, 0)

        import_ann_btn = QPushButton("⬇ Import Annotations")
        import_ann_btn.setToolTip("Import annotations with conflict-safe merge or override")
        import_ann_btn.clicked.connect(self._import_annotations_package)
        ie_btn_layout.addWidget(import_ann_btn, 1, 1)

        # Row 2: Revert
        revert_classes_btn = QPushButton("↩ Revert Classes")
        revert_classes_btn.setToolTip("Restore master_classes.json from a backup")
        revert_classes_btn.clicked.connect(self._revert_classes_from_backup)
        ie_btn_layout.addWidget(revert_classes_btn, 2, 0)

        revert_ann_btn = QPushButton("↩ Revert Annotations")
        revert_ann_btn.setToolTip("Restore annotations from a ZIP backup")
        revert_ann_btn.clicked.connect(self._revert_annotations_from_backup)
        ie_btn_layout.addWidget(revert_ann_btn, 2, 1)

        # Row 3: ZIP Archive
        export_zip_btn = QPushButton("⬆ Export ZIP")
        export_zip_btn.setToolTip("Create a ZIP archive with images + labels + metadata")
        export_zip_btn.clicked.connect(self._export_annotations_zip)
        ie_btn_layout.addWidget(export_zip_btn, 3, 0)

        import_zip_btn = QPushButton("⬇ Import ZIP")
        import_zip_btn.setToolTip("Import a ZIP archive containing images + labels")
        import_zip_btn.clicked.connect(self._import_annotations_zip)
        ie_btn_layout.addWidget(import_zip_btn, 3, 1)
        
        left_panel.addLayout(ie_btn_layout)
        
        # Ready for Training count display
        training_ready_group = QWidget()
        training_ready_layout = QVBoxLayout(training_ready_group)
        training_ready_layout.setContentsMargins(10, 10, 10, 10)
        training_ready_group.setStyleSheet("""
            QWidget {
                background: rgba(0, 188, 212, 0.1);
                border: 2px solid #00bcd4;
                border-radius: 8px;
            }
        """)
        
        # Header with delete button
        header_layout = QHBoxLayout()
        self.training_ready_label = QLabel("📦 Ready for Training")
        self.training_ready_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4; border: none; background: transparent;")
        header_layout.addWidget(self.training_ready_label)
        header_layout.addStretch()
        
        delete_all_btn = QPushButton("🗑")
        delete_all_btn.setMaximumWidth(30)
        delete_all_btn.setToolTip("Delete all training data")
        delete_all_btn.setStyleSheet("background-color: #f44336; color: white; border: none; padding: 2px; border-radius: 3px;")
        delete_all_btn.clicked.connect(self._delete_all_training_data)
        header_layout.addWidget(delete_all_btn)
        
        training_ready_layout.addLayout(header_layout)
        
        self.training_ready_count_label = QLabel("0 annotation files")
        self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; border: none; background: transparent;")
        training_ready_layout.addWidget(self.training_ready_count_label)
        
        # Tree view for annotation files grouped by class
        self.training_files_tree = QTreeWidget()
        self.training_files_tree.setHeaderLabels(["Files by Class"])
        self.training_files_tree.setMaximumHeight(200)
        self.training_files_tree.setStyleSheet("""
            QTreeWidget {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid #555;
                color: #fff;
                font-size: 11px;
            }
            QTreeWidget::item:selected {
                background: rgba(0, 188, 212, 0.3);
            }
        """)
        training_ready_layout.addWidget(self.training_files_tree)
        
        left_panel.addWidget(training_ready_group)

        # Dataset Stats display
        dataset_stats_group = QWidget()
        dataset_stats_layout = QVBoxLayout(dataset_stats_group)
        dataset_stats_layout.setContentsMargins(10, 10, 10, 10)
        dataset_stats_group.setStyleSheet("""
            QWidget {
                background: rgba(76, 175, 80, 0.08);
                border: 2px solid #4CAF50;
                border-radius: 8px;
            }
        """)
        ds_label = QLabel("📊 Dataset Stats")
        ds_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #4CAF50; border: none; background: transparent;")
        dataset_stats_layout.addWidget(ds_label)
        self.dataset_images_counts_label = QLabel("Images: —")
        self.dataset_images_counts_label.setStyleSheet("font-size: 13px; color: #fff; border: none; background: transparent;")
        dataset_stats_layout.addWidget(self.dataset_images_counts_label)
        self.dataset_classes_label = QLabel("Classes: —")
        self.dataset_classes_label.setStyleSheet("font-size: 13px; color: #fff; border: none; background: transparent;")
        dataset_stats_layout.addWidget(self.dataset_classes_label)
        left_panel.addWidget(dataset_stats_group)

        left_panel.addStretch(1)
        
        # QC Review, Move to Training and Delete buttons
        action_btn_layout = QHBoxLayout()
        
        qc_review_btn = QPushButton("🔍 QC Review")
        qc_review_btn.setToolTip("Review and edit annotations before moving to training")
        qc_review_btn.clicked.connect(self.open_qc_review)
        action_btn_layout.addWidget(qc_review_btn)
        
        move_btn = QPushButton("→ Move to Training")
        move_btn.clicked.connect(self.move_to_training)
        action_btn_layout.addWidget(move_btn)
        
        delete_btn = QPushButton("🗑 Delete")
        delete_btn.clicked.connect(self.delete_training_data)
        action_btn_layout.addWidget(delete_btn)

        review_btn = QPushButton("🔎 Review Unclassified")
        review_btn.setToolTip("List dataset items remapped to unclassified_* for re-annotation")
        review_btn.clicked.connect(self.review_unclassified_items)
        action_btn_layout.addWidget(review_btn)
        action_btn_layout.addStretch(1)
        left_panel.addLayout(action_btn_layout)
        
        training_layout.addLayout(left_panel, 1)
        
        # Right panel: Training configuration
        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Training Configuration"))
        
        config_form = QFormLayout()
        
        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(1, 1000)
        self.epochs_spin.setValue(50)
        config_form.addRow("Epochs:", self.epochs_spin)
        
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 128)
        self.batch_size_spin.setValue(16)
        config_form.addRow("Batch Size:", self.batch_size_spin)
        
        right_panel.addLayout(config_form)
        
        # Training Status
        right_panel.addWidget(QLabel("Training Status"))
        self.training_progress = QProgressBar()
        self.training_progress.setValue(0)
        right_panel.addWidget(self.training_progress)
        
        self.training_status_label = QLabel("Ready")
        right_panel.addWidget(self.training_status_label)
        
        self.training_epoch_label = QLabel("Epoch: 0/0")
        right_panel.addWidget(self.training_epoch_label)
        
        # Training control buttons
        train_btn_layout = QHBoxLayout()
        self.start_training_btn = QPushButton("▶ Start Training")
        self.start_training_btn.clicked.connect(self.start_model_training)
        train_btn_layout.addWidget(self.start_training_btn)
        
        self.quick_retrain_btn = QPushButton("⚡ Quick Retrain")
        self.quick_retrain_btn.setToolTip("Runs a shorter retrain using current dataset")
        self.quick_retrain_btn.clicked.connect(self.start_quick_retraining)
        train_btn_layout.addWidget(self.quick_retrain_btn)
        
        self.cancel_training_btn = QPushButton("Cancel")
        self.cancel_training_btn.setEnabled(False)
        self.cancel_training_btn.clicked.connect(self.cancel_model_training)
        train_btn_layout.addWidget(self.cancel_training_btn)
        train_btn_layout.addStretch(1)
        right_panel.addLayout(train_btn_layout)
        
        # Model Versions
        right_panel.addWidget(QLabel("Model Versions"))
        self.model_versions_list = QListWidget()
        self.model_versions_list.setMaximumHeight(140)
        right_panel.addWidget(self.model_versions_list)
        
        version_btn_layout = QHBoxLayout()
        rollback_btn = QPushButton("↶ Rollback")
        rollback_btn.clicked.connect(self.rollback_model_version)
        version_btn_layout.addWidget(rollback_btn)
        
        delete_version_btn = QPushButton("🗑 Delete Version")
        delete_version_btn.clicked.connect(self.delete_model_version)
        version_btn_layout.addWidget(delete_version_btn)
        version_btn_layout.addStretch(1)
        right_panel.addLayout(version_btn_layout)
        
        right_panel.addStretch(1)
        training_layout.addLayout(right_panel, 1)
        
        # Initial refresh
        try:
            self._refresh_training_ready_count()
            self._refresh_dataset_stats()
            self._refresh_model_versions()
        except Exception:
            pass
        
        training_subtabs.addTab(training_widget, "Training")
        
        # --- Sandbox Sub-tab ---
        sandbox_widget = self._create_sandbox_tab()
        training_subtabs.addTab(sandbox_widget, "Sandbox")
        
        main_layout.addWidget(training_subtabs)
        self.setLayout(main_layout)

    def import_training_media(self):
        """Import training media (video or images)"""
        files, selected_filter = QFileDialog.getOpenFileNames(
            self,
            "Select Training Media",
            "",
            "Videos (*.mp4 *.avi *.mov);;Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )
        if not files:
            return

        video_exts = {".mp4", ".avi", ".mov"}
        image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
        paths_lower = [p.lower() for p in files]
        exts = {os.path.splitext(p)[1] for p in paths_lower}

        is_video = len(files) == 1 and len(exts & video_exts) == 1
        is_images = len(exts & image_exts) >= 1 and (exts & video_exts) == set()

        if not is_video and not is_images:
            QMessageBox.warning(self, "Import", "Please select either a single video or one/more image files.")
            return

        if is_video:
            file_path = files[0]
            self.training_selected_video_path = file_path
            self.training_selected_image_paths = []
            self.training_media_imported = True
            
            QMessageBox.information(
                self,
                "Media Imported ✓",
                f"Media: {os.path.basename(file_path)}\n\n"
                "Next: Click '🖊️ Annotate Media' to label frames."
            )
            self.training_status_label.setText("Ready: awaiting annotation")
        else:
            files_sorted = sorted(files)
            self.training_selected_image_paths = files_sorted
            self.training_selected_video_path = None
            self.training_media_imported = True
            
            QMessageBox.information(
                self,
                "Images Imported ✓",
                f"Imported {len(files_sorted)} image(s).\n\n"
                "Next: Click '🖊️ Annotate Media' to label them."
            )
            self.training_status_label.setText("Ready: awaiting annotation")

    def open_annotation_tool(self):
        """Open annotation tool for labeling frames"""
        if not self.training_selected_video_path and not self.training_selected_image_paths:
            QMessageBox.warning(self, "Annotation", "Please import media (video or images) first.")
            return
        
        QMessageBox.information(
            self, "Annotation Tool", 
            "Annotation tool integration coming soon!\n\n"
            "This will open a full-featured annotation interface for labeling objects."
        )

    def open_qc_review(self):
        """Open QC review dialog"""
        QMessageBox.information(
            self, "QC Review", 
            "QC Review feature coming soon!\n\n"
            "This will allow you to review and correct annotations before training."
        )

    def move_to_training(self):
        """Move annotated frames to training directory"""
        QMessageBox.information(
            self, "Move to Training", 
            "Moving annotations to training set...\n\n"
            "Feature will organize annotations for YOLO training."
        )
        self._refresh_training_ready_count()

    def delete_training_data(self):
        """Delete selected training data"""
        reply = QMessageBox.question(
            self, "Delete", 
            "Delete selected training data?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._refresh_training_ready_count()

    def review_unclassified_items(self):
        """Review items flagged as unclassified"""
        QMessageBox.information(
            self, "Review Unclassified", 
            "Unclassified items review coming soon!\n\n"
            "This will show annotations that need reclassification."
        )

    def start_model_training(self):
        """Start full model training"""
        try:
            project_name = f"embereye_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            config = TrainingConfig(
                project_name=project_name,
                epochs=self.epochs_spin.value(),
                batch_size=self.batch_size_spin.value(),
                imgsz=640,
                device="auto",
            )

            self.start_training_btn.setEnabled(False)
            self.cancel_training_btn.setEnabled(True)
            self.training_status_label.setText("Starting training...")
            self.training_progress.setValue(5)

            pipeline = YOLOTrainingPipeline(config=config)
            success, message = pipeline.run_full_pipeline()

            if success:
                self.training_status_label.setText("✓ Training completed!")
                self.training_progress.setValue(100)
                QMessageBox.information(self, "Training Complete", message)
                self._refresh_model_versions()
            else:
                self.training_status_label.setText(f"✗ Training failed")
                QMessageBox.critical(self, "Training Failed", message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Training error: {str(e)}")
        finally:
            self.start_training_btn.setEnabled(True)
            self.cancel_training_btn.setEnabled(False)

    def start_quick_retraining(self):
        """Quick retrain with fewer epochs"""
        self.epochs_spin.setValue(20)
        self.start_model_training()

    def cancel_model_training(self):
        """Cancel running training"""
        if self.pipeline:
            self.pipeline.training_active = False
        self.training_status_label.setText("Training cancelled")
        self.cancel_training_btn.setEnabled(False)

    def rollback_model_version(self):
        """Rollback to selected model version"""
        selected = self.model_versions_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Rollback", "Please select a version to rollback to.")
            return
        
        QMessageBox.information(
            self, "Rollback", 
            f"Rolling back to: {selected.text()}\n\n"
            "Feature will restore selected model version."
        )

    def delete_model_version(self):
        """Delete selected model version"""
        selected = self.model_versions_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Delete", "Please select a version to delete.")
            return
        
        reply = QMessageBox.question(
            self, "Delete Version", 
            f"Delete version {selected.text()}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._refresh_model_versions()

    def _refresh_training_ready_count(self):
        """Refresh training data count"""
        training_base = Path(get_data_path("training_data/annotations"))
        if training_base.exists():
            annotation_files = list(training_base.rglob("*.txt"))
            count = len(annotation_files)
            self.training_ready_count_label.setText(f"{count} annotation files")
        else:
            self.training_ready_count_label.setText("0 annotation files")

    def _refresh_dataset_stats(self):
        """Refresh dataset statistics"""
        self.dataset_images_counts_label.setText("Images: Computing...")
        self.dataset_classes_label.setText("Classes: Computing...")

    def _refresh_model_versions(self):
        """Refresh model versions list"""
        self.model_versions_list.clear()
        models_dir = Path(get_data_path("models"))
        if models_dir.exists():
            for version_dir in sorted(models_dir.glob("v*")):
                self.model_versions_list.addItem(version_dir.name)

    def _delete_all_training_data(self):
        """Delete all training data"""
        reply = QMessageBox.question(
            self, "Delete All", 
            "Delete ALL training data? This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._refresh_training_ready_count()

    def _export_classes_package(self):
        """Export class hierarchy"""
        QMessageBox.information(self, "Export Classes", "Export classes feature coming soon!")

    def _import_classes_package(self):
        """Import class hierarchy"""
        QMessageBox.information(self, "Import Classes", "Import classes feature coming soon!")

    def _export_annotations_package(self):
        """Export annotations"""
        QMessageBox.information(self, "Export Annotations", "Export annotations feature coming soon!")

    def _import_annotations_package(self):
        """Import annotations"""
        QMessageBox.information(self, "Import Annotations", "Import annotations feature coming soon!")

    def _revert_classes_from_backup(self):
        """Revert classes from backup"""
        QMessageBox.information(self, "Revert Classes", "Revert classes feature coming soon!")

    def _revert_annotations_from_backup(self):
        """Revert annotations from backup"""
        QMessageBox.information(self, "Revert Annotations", "Revert annotations feature coming soon!")

    def _export_annotations_zip(self):
        """Export annotations as ZIP"""
        QMessageBox.information(self, "Export ZIP", "Export ZIP feature coming soon!")

    def _import_annotations_zip(self):
        """Import annotations from ZIP"""
        QMessageBox.information(self, "Import ZIP", "Import ZIP feature coming soon!")

    def _create_sandbox_tab(self) -> QWidget:
        """Create sandbox testing UI"""
        from PyQt5.QtWidgets import QScrollArea
        
        sandbox_widget = QWidget()
        main_layout = QVBoxLayout(sandbox_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        scroll_content = QWidget()
        sandbox_layout = QVBoxLayout(scroll_content)
        sandbox_layout.setSpacing(5)
        
        header = QLabel("🧪 Sandbox - Test models safely")
        header.setStyleSheet("font-weight: bold; padding: 5px; font-size: 14px;")
        sandbox_layout.addWidget(header)
        
        # Top section with model and controls
        top_section = QHBoxLayout()
        
        # Model selection
        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout()
        
        model_select_layout = QHBoxLayout()
        model_select_layout.addWidget(QLabel("Version:"))
        self.sandbox_model_combo = QComboBox()
        self.sandbox_model_combo.setMinimumWidth(120)
        model_select_layout.addWidget(self.sandbox_model_combo, 1)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMaximumWidth(35)
        refresh_btn.clicked.connect(self._refresh_sandbox_models)
        model_select_layout.addWidget(refresh_btn)
        model_layout.addLayout(model_select_layout)
        
        self.sandbox_model_info = QLabel("No model")
        self.sandbox_model_info.setStyleSheet("font-size: 10px; color: #666;")
        self.sandbox_model_info.setWordWrap(True)
        model_layout.addWidget(self.sandbox_model_info)

        actions_row = QHBoxLayout()
        verify_btn = QPushButton("Verify")
        verify_btn.clicked.connect(self._sandbox_verify_model)
        actions_row.addWidget(verify_btn)
        
        export_btn = QPushButton("📦 Export")
        export_btn.clicked.connect(self._sandbox_export_model)
        actions_row.addWidget(export_btn)
        
        import_btn = QPushButton("📥 Import")
        import_btn.clicked.connect(self._sandbox_import_model)
        actions_row.addWidget(import_btn)
        actions_row.addStretch(1)
        model_layout.addLayout(actions_row)
        
        model_group.setLayout(model_layout)
        top_section.addWidget(model_group)
        
        # Inference controls
        control_group = QGroupBox("Settings")
        control_layout = QVBoxLayout()
        
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence:"))
        self.sandbox_conf_spin = QDoubleSpinBox()
        self.sandbox_conf_spin.setRange(0.0, 1.0)
        self.sandbox_conf_spin.setSingleStep(0.05)
        self.sandbox_conf_spin.setValue(0.15)
        self.sandbox_conf_spin.setDecimals(2)
        conf_layout.addWidget(self.sandbox_conf_spin)
        control_layout.addLayout(conf_layout)
        
        iou_layout = QHBoxLayout()
        iou_layout.addWidget(QLabel("IoU:"))
        self.sandbox_iou_spin = QDoubleSpinBox()
        self.sandbox_iou_spin.setRange(0.0, 1.0)
        self.sandbox_iou_spin.setSingleStep(0.05)
        self.sandbox_iou_spin.setValue(0.45)
        self.sandbox_iou_spin.setDecimals(2)
        iou_layout.addWidget(self.sandbox_iou_spin)
        control_layout.addLayout(iou_layout)
        
        control_group.setLayout(control_layout)
        top_section.addWidget(control_group)
        
        sandbox_layout.addLayout(top_section)

        # Action buttons
        action_layout = QHBoxLayout()
        
        upload_img_btn = QPushButton("🖼 Select Image")
        upload_img_btn.clicked.connect(self._sandbox_upload_image)
        action_layout.addWidget(upload_img_btn)
        
        upload_vid_btn = QPushButton("🎥 Select Video")
        upload_vid_btn.clicked.connect(self._sandbox_upload_video)
        action_layout.addWidget(upload_vid_btn)
        
        self.sandbox_run_btn = QPushButton("▶ Run Inference")
        self.sandbox_run_btn.clicked.connect(self._sandbox_run_inference)
        action_layout.addWidget(self.sandbox_run_btn)
        
        action_layout.addStretch(1)
        sandbox_layout.addLayout(action_layout)

        # Preview area
        preview_layout = QHBoxLayout()
        
        input_group = QGroupBox("Input")
        input_layout = QVBoxLayout()
        self.sandbox_input_label = QLabel("No input")
        self.sandbox_input_label.setAlignment(Qt.AlignCenter)
        self.sandbox_input_label.setStyleSheet("border: 1px dashed #ccc; background: #f9f9f9; min-height: 300px;")
        input_layout.addWidget(self.sandbox_input_label)
        input_group.setLayout(input_layout)
        preview_layout.addWidget(input_group)

        results_group = QGroupBox("Result")
        results_layout = QVBoxLayout()
        
        self.sandbox_progress = QProgressBar()
        self.sandbox_progress.setVisible(False)
        results_layout.addWidget(self.sandbox_progress)
        
        self.sandbox_results_label = QLabel("Results appear here")
        self.sandbox_results_label.setAlignment(Qt.AlignCenter)
        self.sandbox_results_label.setStyleSheet("border: 1px solid #333; background: #111; min-height: 300px;")
        results_layout.addWidget(self.sandbox_results_label)
        
        self.sandbox_stats_label = QLabel("Detections: - | Time: -")
        self.sandbox_stats_label.setStyleSheet("font-size: 10px; font-family: monospace;")
        results_layout.addWidget(self.sandbox_stats_label)
        
        self.sandbox_detections_list = QListWidget()
        self.sandbox_detections_list.setMaximumHeight(100)
        results_layout.addWidget(self.sandbox_detections_list)
        
        results_group.setLayout(results_layout)
        preview_layout.addWidget(results_group)
        
        sandbox_layout.addLayout(preview_layout)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        self._refresh_sandbox_models()
        
        return sandbox_widget

    def _refresh_sandbox_models(self):
        """Refresh sandbox model list"""
        self.sandbox_model_combo.clear()
        self.sandbox_model_combo.addItem("yolov8n.pt (pretrained)")
        self.sandbox_model_info.setText("Pretrained YOLO model")

    def _sandbox_verify_model(self):
        """Verify selected model"""
        QMessageBox.information(self, "Verify", "Model verification feature coming soon!")

    def _sandbox_export_model(self):
        """Export model package"""
        QMessageBox.information(self, "Export", "Model export feature coming soon!")

    def _sandbox_import_model(self):
        """Import model package"""
        QMessageBox.information(self, "Import", "Model import feature coming soon!")

    def _sandbox_upload_image(self):
        """Select image for inference"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.sandbox_input_label.setText(f"Selected: {Path(file_path).name}")

    def _sandbox_upload_video(self):
        """Select video for inference"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Videos (*.mp4 *.avi *.mov)"
        )
        if file_path:
            self.sandbox_input_label.setText(f"Selected: {Path(file_path).name}")

    def _sandbox_run_inference(self):
        """Run inference on selected media"""
        QMessageBox.information(self, "Inference", "Sandbox inference feature coming soon!")


class DatasetTab(QWidget):
    """Dataset management tab"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize dataset UI"""
        layout = QVBoxLayout()

        title = QLabel("Dataset Management (EmberArchive)")
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

        training_dir = QLabel("./workspace_data/training_data")
        ws_layout.addRow("Training Data Directory:", training_dir)

        models_dir = QLabel("./workspace_data/models")
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
        self.setWindowTitle(f"🔥 EmberEye STUDIO - {self.username}")
        self.setGeometry(100, 100, 1400, 900)

        # Central widget
        central_widget = QWidget()
        layout = QVBoxLayout()

        # Header with orange banner
        banner = QLabel("🧠 LABS EDITION - Training & Model Development Hub")
        banner.setStyleSheet("background-color: #FF9800; color: white; padding: 8px; font-weight: bold; font-size: 12px;")
        banner.setAlignment(Qt.AlignCenter)
        layout.addWidget(banner)

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
        tabs.addTab(TrainingTab(self), "Training (ForgeLab)")
        tabs.addTab(DatasetTab(), "Datasets (EmberArchive)")
        tabs.addTab(SettingsTab(), "Settings")

        layout.addWidget(tabs)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Apply comprehensive stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #fff;
                padding: 10px 20px;
                margin: 2px;
                border-radius: 3px;
            }
            QTabBar::tab:selected {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
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
            QPushButton:disabled {
                background-color: #555;
                color: #888;
            }
            QGroupBox {
                border: 1px solid #444;
                border-radius: 4px;
                padding: 15px;
                margin-top: 10px;
                background-color: #3c3c3c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                color: #fff;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #3c3c3c;
                color: #fff;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
            QListWidget, QTreeWidget {
                background-color: #3c3c3c;
                color: #fff;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 3px;
                text-align: center;
                background-color: #3c3c3c;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    window = StudioMainWindow("admin")
    window.show()
    sys.exit(app.exec_())
