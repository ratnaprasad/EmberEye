"""
EmberEye Studio - Main Application Window (Comprehensive)
Central hub for training, model management, and dataset organization

Complete version with all features from field edition including:
- Import/Export Classes and Annotations
- Sandbox Testing
- QC Review
- Model Versioning
- Advanced Training Controls
"""

import sys
import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QMessageBox, QProgressBar, QGroupBox,
    QFormLayout, QSpinBox, QComboBox, QTextEdit, QFileDialog,
    QListWidget, QGridLayout, QScrollArea, QDoubleSpinBox,
    QTreeWidget, QTreeWidgetItem, QDialog, QInputDialog, QToolButton,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl, QThread
from PyQt5.QtGui import QFont, QPixmap, QImage, QIcon

from forgelab import (
    TrainingConfig, TrainingProgress, TrainingStatus, YOLOTrainingPipeline, DeviceManager
)
from studio_db_manager import StudioDatabaseManager

# Import centralized get_data_path from embereye (keep Studio path first)
embereye_path = str(Path(__file__).parent.parent / "embereye")
if embereye_path not in sys.path:
    sys.path.append(embereye_path)
from embereye.utils.resource_helper import get_data_path


class TrainingWorker(QThread):
    progress = pyqtSignal(object)
    finished = pyqtSignal(bool, str)
    device_ready = pyqtSignal(str)

    def __init__(self, config: TrainingConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.pipeline = None

    def run(self):
        self.pipeline = YOLOTrainingPipeline(config=self.config)
        self.device_ready.emit(self.pipeline.device)
        # Ensure epoch callbacks are registered so progress updates include epoch info
        self.pipeline.set_epoch_callback(lambda _cur, _total: None)
        self.pipeline.set_progress_callback(self._emit_progress)
        success, message = self.pipeline.run_full_pipeline()
        self.finished.emit(success, message)

    def _emit_progress(self, progress: TrainingProgress):
        self.progress.emit(progress)


class TrainingTab(QWidget):
    """Comprehensive Training and model management tab with Sandbox"""
    
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.pipeline = None
        self.training_worker = None
        self.training_active = False
        self.training_has_annotations = False
        self.imported_zip_bases = []
        self.training_just_completed = False
        
        self.init_ui()

    def init_ui(self):
        """Initialize comprehensive training UI"""
        main_layout = QVBoxLayout()

        # --- Training Content ---
        training_widget = QWidget()
        training_layout = QHBoxLayout(training_widget)
        
        # Left panel: Data management
        left_panel = QVBoxLayout()
        
        # Import/Export for Annotations
        ie_btn_layout = QGridLayout()
        ie_btn_layout.setSpacing(5)
        
        # Row 0: Annotations
        export_ann_btn = QPushButton("⬆ Export Annotations")
        export_ann_btn.setToolTip("Export annotations from workspace to a JSON package")
        export_ann_btn.clicked.connect(self._export_annotations_package)
        ie_btn_layout.addWidget(export_ann_btn, 0, 0)

        import_ann_btn = QPushButton("⬇ Import Annotations")
        import_ann_btn.setToolTip("Import annotations with conflict-safe merge or override")
        import_ann_btn.clicked.connect(self._import_annotations_package)
        ie_btn_layout.addWidget(import_ann_btn, 0, 1)

        # Row 1: Revert
        revert_classes_btn = QPushButton("↩ Revert Classes")
        revert_classes_btn.setToolTip("Restore master_classes.json from a backup")
        revert_classes_btn.clicked.connect(self._revert_classes_from_backup)
        ie_btn_layout.addWidget(revert_classes_btn, 1, 0)

        revert_ann_btn = QPushButton("↩ Revert Annotations")
        revert_ann_btn.setToolTip("Restore annotations from a ZIP backup")
        revert_ann_btn.clicked.connect(self._revert_annotations_from_backup)
        ie_btn_layout.addWidget(revert_ann_btn, 1, 1)

        # Row 2: ZIP Archive
        export_zip_btn = QPushButton("⬆ Export ZIP")
        export_zip_btn.setToolTip("Create a ZIP archive with images + labels + metadata")
        export_zip_btn.clicked.connect(self._export_annotations_zip)
        ie_btn_layout.addWidget(export_zip_btn, 2, 0)

        import_zip_btn = QPushButton("⬇ Import ZIP")
        import_zip_btn.setToolTip("Import a ZIP archive containing images + labels")
        import_zip_btn.clicked.connect(self._import_annotations_zip)
        ie_btn_layout.addWidget(import_zip_btn, 2, 1)
        
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
        export_btn = QPushButton("📦 Export Model")
        export_btn.clicked.connect(self.export_model_version)
        version_btn_layout.addWidget(export_btn)
        
        delete_version_btn = QPushButton("🗑 Delete Version")
        delete_version_btn.clicked.connect(self.delete_model_version)
        version_btn_layout.addWidget(delete_version_btn)
        version_btn_layout.addStretch(1)
        right_panel.addLayout(version_btn_layout)
        
        right_panel.addStretch(1)
        training_layout.addLayout(right_panel, 1)
        
        # Initial refresh
        try:
            self._archive_existing_models()  # Archive any existing models first
            self._refresh_training_ready_count()
            self._refresh_dataset_stats()
            self._refresh_model_versions()
        except Exception:
            pass
        
        main_layout.addWidget(training_widget)
        self.setLayout(main_layout)

    def create_sandbox_tab(self):
        return self._create_sandbox_tab()

    def open_qc_review(self):
        """Open QC Review dialog to review and edit annotations before training."""
        has_video = bool(getattr(self, 'training_selected_video_path', None))
        has_images = bool(getattr(self, 'training_selected_image_paths', []))
        has_imported_zip = bool(getattr(self, 'imported_zip_bases', []))
        
        annotations_dir = None
        
        if has_video:
            annotations_dir = self._annotations_dir_for_video(self.training_selected_video_path)
        elif has_images:
            annotations_dir = self._annotations_dir_for_images(self.training_selected_image_paths)
        elif has_imported_zip:
            from PyQt5.QtWidgets import QInputDialog
            bases = getattr(self, 'imported_zip_bases', [])
            
            # Bug fix: Verify bases actually have annotations before showing dialog
            valid_bases = []
            for base in bases:
                base_path = get_data_path(os.path.join("annotations", base))
                if self._has_annotations(base_path):
                    valid_bases.append(base)
            
            if not valid_bases:
                QMessageBox.warning(
                    self, 
                    "QC Review", 
                    f"No annotations found in imported bases!\n\n"
                    f"Imported bases: {', '.join(bases)}\n"
                    f"Location: {get_data_path('annotations')}\n\n"
                    f"Annotations may not have been extracted properly."
                )
                return
            
            items = ["All media bases"] + valid_bases
            selected_base, ok = QInputDialog.getItem(
                self,
                "Select Media Base",
                "Choose media base to review:",
                items,
                0,
                False
            )
            if not ok:
                return
            if selected_base == "All media bases":
                annotations_dir = get_data_path("annotations")
            else:
                annotations_dir = get_data_path(os.path.join("annotations", selected_base))
        else:
            # No media selected - check if any annotations exist in workspace
            workspace_annotations = get_data_path("annotations")
            if not os.path.exists(workspace_annotations):
                QMessageBox.warning(self, "QC Review", "No annotations found in workspace. Please annotate some frames first.")
                return
            
            # Find all media bases with annotations
            media_bases = []
            for item in os.listdir(workspace_annotations):
                if item == "qcapproved":
                    continue
                item_path = os.path.join(workspace_annotations, item)
                if os.path.isdir(item_path) and self._has_annotations(item_path):
                    media_bases.append(item)
            
            if not media_bases:
                QMessageBox.warning(self, "QC Review", "No annotations found in workspace. Please annotate some frames first.")
                return
            
            # Let user select which media base to review
            from PyQt5.QtWidgets import QInputDialog
            if len(media_bases) == 1:
                annotations_dir = os.path.join(workspace_annotations, media_bases[0])
            else:
                items = ["All media bases"] + media_bases
                selected_base, ok = QInputDialog.getItem(
                    self,
                    "Select Media Base",
                    "Choose media base to review:",
                    items,
                    0,
                    False
                )
                if not ok:
                    return
                if selected_base == "All media bases":
                    annotations_dir = workspace_annotations
                else:
                    annotations_dir = os.path.join(workspace_annotations, selected_base)
        
        if not os.path.exists(annotations_dir) or not self._has_annotations(annotations_dir):
            QMessageBox.warning(self, "QC Review", "No annotations found. Annotate media first.")
            return
        
        from qc_review_dialog import QCReviewDialog
        dialog = QCReviewDialog(annotations_dir, parent=self.parent_window)
        result = dialog.exec_()
        
        if result == QCReviewDialog.Accepted:
            moved = self._move_to_qc_approved(annotations_dir)
            ann_count = self._count_annotation_files(self._qc_approved_root())
            QMessageBox.information(
                self,
                "QC Review Complete",
                f"Review complete!\n\n"
                f"QC-approved: {moved} base(s)\n"
                f"Annotations in qcapproved: {ann_count} files\n\n"
                f"Click 'Move to Training' to proceed."
            )

    def move_to_training(self):
        """Register annotated frames into training_data/annotations for training."""
        has_video = bool(getattr(self, 'training_selected_video_path', None))
        has_images = bool(getattr(self, 'training_selected_image_paths', []))
        has_imported_zip = bool(getattr(self, 'imported_zip_bases', []))
        
        # Check QC-approved annotations if no media selected
        workspace_annotations = self._qc_approved_root()
        workspace_bases = []
        if not (has_video or has_images or has_imported_zip):
            if os.path.exists(workspace_annotations):
                for item in os.listdir(workspace_annotations):
                    item_path = os.path.join(workspace_annotations, item)
                    if os.path.isdir(item_path) and self._has_annotations(item_path):
                        workspace_bases.append(item)
            
            if not workspace_bases:
                QMessageBox.warning(self, "Training", "Select or import media first, or ensure workspace has annotations.")
                return
        
        if has_video:
            raw_dir = self._annotations_dir_for_video(self.training_selected_video_path)
            annotations_dir = os.path.join(self._qc_approved_root(), os.path.basename(raw_dir))
            if not self._has_annotations(annotations_dir):
                QMessageBox.warning(self, "Training", "QC Review not completed for this media. Please run QC Review first.")
                return
        elif has_images:
            raw_dir = self._annotations_dir_for_images(self.training_selected_image_paths)
            annotations_dir = os.path.join(self._qc_approved_root(), os.path.basename(raw_dir))
            if not self._has_annotations(annotations_dir):
                QMessageBox.warning(self, "Training", "QC Review not completed for this media. Please run QC Review first.")
                return
        else:
            from PyQt5.QtWidgets import QInputDialog
            # Use workspace bases if no media selected, otherwise use imported ZIP bases
            bases = workspace_bases if workspace_bases else getattr(self, 'imported_zip_bases', [])
            items = ["All media bases"] + bases
            selected, ok = QInputDialog.getItem(
                self,
                "Move to Training",
                "Select which QC-approved media to move:",
                items,
                0,
                False
            )
            if not ok:
                return
            
            if selected == "All media bases":
                total_moved = 0
                for base in bases:
                    annotations_dir = os.path.join(workspace_annotations, base)
                    target_dir = self._copy_annotations_to_training(annotations_dir)
                    if target_dir:
                        total_moved += self._count_annotation_files(annotations_dir)
                        self._clear_qc_approved_base(annotations_dir)
                
                if total_moved > 0:
                    self._refresh_training_ready_count()
                    if not workspace_bases:
                        self.imported_zip_bases = []
                    QMessageBox.information(
                        self,
                        "Training",
                        f"Moved {total_moved} annotation files from {len(bases)} media base(s) to training.\n\n"
                        "Ready for next batch. Click 'Import Media' or 'Import ZIP' to add more."
                    )
                else:
                    QMessageBox.warning(self, "Training", "No annotations were moved.")
                return
            else:
                annotations_dir = os.path.join(workspace_annotations, selected)
        
        ann_count = self._count_annotation_files(annotations_dir)
        if ann_count == 0:
            QMessageBox.warning(self, "Training", "No annotations found. Annotate or ensure labels exist before moving to training.")
            return
        
        target_dir = self._copy_annotations_to_training(annotations_dir)
        if target_dir:
            self._clear_qc_approved_base(annotations_dir)
            self._refresh_training_ready_count()
            try:
                self._refresh_dataset_stats()
            except Exception:
                pass
            
            self.training_selected_video_path = None
            self.training_selected_image_paths = []
            self.training_has_annotations = False
            self.training_media_imported = False
            
            QMessageBox.information(
                self,
                "Training",
                f"Registered QC-approved frames for training.\n"
                f"Annotations: {ann_count} files\n"
                f"Copied to: {target_dir}\n\n"
                "QC-approved source cleared. Ready for next batch."
            )
        else:
            QMessageBox.warning(self, "Training", "Failed to copy annotations to training_data.")

    def delete_training_data(self):
        """Delete selected training data (annotations and source media)."""
        has_video = bool(getattr(self, 'training_selected_video_path', None))
        has_images = bool(getattr(self, 'training_selected_image_paths', []))
        
        if not (has_video or has_images):
            QMessageBox.warning(self, "Delete", "No media selected to delete.")
            return
        
        reply = QMessageBox.question(
            self, 
            "Delete Training Data", 
            "Delete annotations and clear imported media?\n\n"
            "This will:\n"
            "• Remove saved annotations\n"
            "• Clear the imported media reference\n\n"
            "Proceed?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if has_video:
                    annotations_dir = self._annotations_dir_for_video(self.training_selected_video_path)
                else:
                    annotations_dir = self._annotations_dir_for_images(self.training_selected_image_paths)
                
                if os.path.exists(annotations_dir):
                    import shutil
                    shutil.rmtree(annotations_dir)
                
                self.training_selected_video_path = None
                self.training_selected_image_paths = []
                self.training_has_annotations = False
                self.training_media_imported = False
                
                QMessageBox.information(self, "Delete", "Annotations and media reference deleted successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", f"Failed to delete: {str(e)}")

    def review_unclassified_items(self):
        """Scan training_data/dataset for labels mapped to unclassified_* and present a review list."""
        try:
            from pathlib import Path
            import yaml
            dataset_dir = Path(get_data_path("training_data")) / "dataset"
            ds_yaml = dataset_dir / "dataset.yaml"
            if not ds_yaml.exists():
                QMessageBox.information(self, "Review", "Dataset not prepared yet. Run training prep first.")
                return
            cfg = yaml.safe_load(ds_yaml.read_text())
            names = cfg.get('names') or []
            unclassified_indices = {i for i, n in enumerate(names) if str(n).startswith('unclassified_')}
            if not unclassified_indices:
                QMessageBox.information(self, "Review", "No unclassified items found in current dataset.")
                return

            label_root = dataset_dir / 'labels'
            image_root = dataset_dir / 'images'
            candidates = []
            for split in ['train', 'val', 'test']:
                split_labels = label_root / split
                split_images = image_root / split
                if not split_labels.exists():
                    continue
                for lbl in split_labels.glob('*.txt'):
                    try:
                        lines = lbl.read_text().splitlines()
                    except Exception:
                        continue
                    matched = set()
                    for line in lines:
                        parts = line.strip().split()
                        if len(parts) == 5:
                            try:
                                cid = int(parts[0])
                                if cid in unclassified_indices:
                                    matched.add(cid)
                            except Exception:
                                pass
                    if matched:
                        stem = lbl.stem
                        img_path = None
                        for ext in ['.jpg', '.png', '.jpeg']:
                            p = split_images / f"{stem}{ext}"
                            if p.exists():
                                img_path = p
                                break
                        candidates.append((split, str(lbl), str(img_path) if img_path else "", sorted(list(matched))))

            if not candidates:
                QMessageBox.information(self, "Review", "Dataset prepared, but no files currently flagged as unclassified.")
                return

            dlg = QDialog(self.parent_window)
            dlg.setWindowTitle("Unclassified Items")
            lay = QVBoxLayout(dlg)
            info = QLabel("Items remapped to unclassified_* — open folder to re-annotate the originals.")
            lay.addWidget(info)
            lst = QListWidget()
            for split, lbl_path, img_path, ids in candidates:
                names_list = ", ".join(names[i] for i in ids if i < len(names))
                lst.addItem(f"[{split}] {os.path.basename(img_path) or os.path.basename(lbl_path)} → {names_list}")
            lay.addWidget(lst)
            btn_row = QHBoxLayout()
            open_btn = QPushButton("Open Folder…")

            def _open_selected_folder():
                idx = lst.currentRow()
                if idx < 0:
                    return
                _, lbl_path, img_path, _ = candidates[idx]
                target = img_path or lbl_path
                try:
                    from PyQt5.QtGui import QDesktopServices
                    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(target)))
                except Exception as e:
                    QMessageBox.warning(dlg, "Open", f"Failed to open folder: {e}")

            open_btn.clicked.connect(_open_selected_folder)
            btn_row.addWidget(open_btn)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.close)
            btn_row.addWidget(close_btn)
            lay.addLayout(btn_row)
            dlg.resize(500, 300)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self.parent_window, "Error", f"Failed to review unclassified items: {str(e)}")

    def _annotations_dir_for_video(self, video_path: str) -> str:
        """Return workspace-relative annotations directory for a video."""
        base = os.path.splitext(os.path.basename(video_path or "video"))[0]
        return get_data_path(os.path.join("annotations", base))

    def _annotations_dir_for_images(self, image_paths) -> str:
        """Return annotations directory for an image set."""
        if not image_paths:
            return get_data_path(os.path.join("annotations", "images"))
        try:
            common_dir = os.path.commonpath(image_paths)
            if os.path.isfile(common_dir):
                common_dir = os.path.dirname(common_dir)
        except Exception:
            common_dir = os.path.dirname(image_paths[0])
        if len(image_paths) == 1:
            base = os.path.splitext(os.path.basename(image_paths[0]))[0]
        else:
            base = os.path.basename(common_dir) or "images"
        return get_data_path(os.path.join("annotations", base))

    def _has_annotations(self, annotations_dir: str) -> bool:
        try:
            if not annotations_dir or not os.path.exists(annotations_dir):
                return False
            for root, dirs, files in os.walk(annotations_dir):
                if any(f.endswith('.txt') for f in files):
                    return True
            return False
        except Exception:
            return False

    def _count_annotation_files(self, annotations_dir: str) -> int:
        """Count all .txt annotation files recursively in directory tree."""
        try:
            if not annotations_dir or not os.path.exists(annotations_dir):
                return 0
            count = 0
            for root, dirs, files in os.walk(annotations_dir):
                count += sum(1 for f in files if f.endswith('.txt'))
            return count
        except Exception:
            return 0

    def _copy_annotations_to_training(self, source_dir: str) -> str:
        """Copy annotated frames (images + txt) into training_data/annotations."""
        try:
            if not source_dir or not os.path.exists(source_dir):
                return ""
            import shutil
            base = os.path.basename(source_dir)
            target_root = get_data_path(os.path.join("training_data", "annotations", base))
            os.makedirs(target_root, exist_ok=True)
            for root, dirs, files in os.walk(source_dir):
                rel = os.path.relpath(root, source_dir)
                dest_dir = os.path.join(target_root, rel) if rel != '.' else target_root
                os.makedirs(dest_dir, exist_ok=True)
                for fname in files:
                    if fname.lower().endswith((".txt", ".jpg", ".png", ".jpeg")):
                        shutil.copy2(os.path.join(root, fname), os.path.join(dest_dir, fname))
            return target_root
        except Exception:
            return ""

    def _clear_qc_approved_base(self, qc_base_dir: str) -> None:
        """Remove a qcapproved base after it is moved to training."""
        try:
            if not qc_base_dir or not os.path.exists(qc_base_dir):
                return
            qc_root = os.path.realpath(self._qc_approved_root())
            qc_base_real = os.path.realpath(qc_base_dir)
            if not qc_base_real.startswith(qc_root):
                return
            shutil.rmtree(qc_base_dir)
        except Exception:
            return

    def _qc_approved_root(self) -> str:
        return get_data_path(os.path.join("annotations", "qcapproved"))

    def _move_to_qc_approved(self, annotations_dir: str) -> int:
        """Move reviewed annotations into annotations/qcapproved."""
        try:
            if not annotations_dir or not os.path.exists(annotations_dir):
                return 0
            qc_root = self._qc_approved_root()
            os.makedirs(qc_root, exist_ok=True)

            ann_root = get_data_path("annotations")
            ann_root_real = os.path.realpath(ann_root)
            qc_root_real = os.path.realpath(qc_root)
            source_real = os.path.realpath(annotations_dir)

            moved = 0
            if source_real == qc_root_real:
                return 0

            # If reviewing all bases, move each base under annotations/
            if source_real == ann_root_real:
                for base in os.listdir(ann_root):
                    if base == "qcapproved":
                        continue
                    base_path = os.path.join(ann_root, base)
                    if os.path.isdir(base_path) and self._has_annotations(base_path):
                        if self._move_base_to_qc_approved(base_path, base):
                            moved += 1
                return moved

            # Otherwise, move the selected base
            base_name = os.path.basename(annotations_dir)
            if self._move_base_to_qc_approved(annotations_dir, base_name):
                moved += 1
            return moved
        except Exception:
            return 0

    def _move_base_to_qc_approved(self, base_path: str, base_name: str) -> bool:
        try:
            if not base_path or not os.path.exists(base_path):
                return False
            qc_root = self._qc_approved_root()
            target_base = os.path.join(qc_root, base_name)
            os.makedirs(target_base, exist_ok=True)
            shutil.copytree(base_path, target_base, dirs_exist_ok=True)
            shutil.rmtree(base_path)
            return True
        except Exception:
            return False

    def _get_files_grouped_by_class(self, annotations_dir: str) -> dict:
        """Group annotation files by detected classes."""
        try:
            from embereye.core.class_config import load_master_classes
            
            files_by_class = {}
            flat_classes = []
            
            classes_dict = load_master_classes()
            for category in classes_dict.get("IncidentEnvironment", []):
                for leaf_class in classes_dict.get(category, []):
                    flat_classes.append(leaf_class)
            
            if not os.path.exists(annotations_dir):
                return files_by_class
            
            for root, dirs, files in os.walk(annotations_dir):
                for fname in files:
                    if fname.endswith('.txt') and fname != 'labels.txt':
                        file_path = os.path.join(root, fname)
                        try:
                            with open(file_path, 'r') as f:
                                for line in f:
                                    parts = line.strip().split()
                                    if len(parts) >= 5:
                                        class_id = int(parts[0])
                                        class_name = flat_classes[class_id] if class_id < len(flat_classes) else f"class_{class_id}"
                                        if class_name not in files_by_class:
                                            files_by_class[class_name] = []
                                        if file_path not in files_by_class[class_name]:
                                            files_by_class[class_name].append(file_path)
                        except Exception:
                            continue
            
            return files_by_class
        except Exception:
            return {}

    def _on_training_progress(self, progress: TrainingProgress):
        """Update progress during training."""
        percent = 0
        if progress.total_epochs > 0:
            percent = int((progress.current_epoch / progress.total_epochs) * 100)
        if progress.status == TrainingStatus.PREPARING:
            percent = max(percent, 5)
        elif progress.status == TrainingStatus.VALIDATING:
            percent = max(percent, 10)
        elif progress.status == TrainingStatus.VALIDATING_FINAL:
            percent = max(percent, 95)
        elif progress.status == TrainingStatus.COMPLETE:
            percent = 100

        if hasattr(self, 'training_progress'):
            self.training_progress.setValue(percent)
        if hasattr(self, 'training_status_label'):
            message = progress.message or progress.status.value
            self.training_status_label.setText(message)
        if hasattr(self, 'training_epoch_label'):
            self.training_epoch_label.setText(
                f"Epoch: {progress.current_epoch}/{progress.total_epochs}"
            )

    def _archive_trained_model(self):
        """Archive the trained model to models/yolo_versions/v[timestamp] - only if not already archived."""
        import logging
        logger = logging.getLogger(__name__)
        
        # Search for best.pt in multiple possible locations
        search_paths = [
            Path(get_data_path("training_data")) / "runs" / "detect",
            Path.cwd() / "runs" / "detect",  # Current working directory
            Path.cwd() / "embereye-studio" / "runs" / "detect",
            Path(get_data_path("")) / "runs" / "detect",
        ]
        
        best_pts = []
        for search_path in search_paths:
            if search_path.exists():
                found = list(search_path.rglob("best.pt"))
                best_pts.extend(found)
        
        if not best_pts:
            logger.warning("No best.pt found in any runs directory")
            return
        
        # Get the most recent best.pt
        best_pt = max(best_pts, key=lambda p: p.stat().st_mtime)
        best_pt_size = best_pt.stat().st_size
        best_pt_mtime = best_pt.stat().st_mtime
        logger.info(f"Found best model: {best_pt} (size: {best_pt_size}, mtime: {best_pt_mtime})")
        
        # Check if this model has already been archived
        models_dir = Path(get_data_path("models"))
        versions_dir = models_dir / "yolo_versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        
        # Check all existing archived versions
        for version_dir in versions_dir.glob("v*"):
            archived_best = version_dir / "best.pt"
            if archived_best.exists():
                # Compare size and modification time
                if (archived_best.stat().st_size == best_pt_size and 
                    abs(archived_best.stat().st_mtime - best_pt_mtime) < 2):
                    logger.info(f"Model already archived as {version_dir.name} - skipping duplicate")
                    return
        
        # Model not yet archived - create new version
        # Use the source file's modification time for the version name to ensure consistency
        version_timestamp = datetime.fromtimestamp(best_pt_mtime).strftime('%Y%m%d_%H%M%S')
        version_name = f"v{version_timestamp}"
        version_dir = versions_dir / version_name
        
        # If this version already exists, skip (shouldn't happen but be safe)
        if version_dir.exists():
            logger.info(f"Version {version_name} already exists - skipping")
            return
            
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy best.pt to version directory
        import shutil
        target_path = version_dir / "best.pt"
        shutil.copy2(best_pt, target_path)
        logger.info(f"Archived model to: {target_path}")
        
        # Also copy any metadata files (dataset.yaml, etc.)
        project_dir = best_pt.parent.parent
        for metadata_file in ["args.yaml", "results.csv", "results.png"]:
            src = project_dir / metadata_file
            if src.exists():
                shutil.copy2(src, version_dir / metadata_file)
        
        # Clean up the runs directory to avoid re-archiving duplicates on next startup
        try:
            runs_root = best_pt.parents[3]  # Go up from best.pt to runs root
            if runs_root.name == "detect" and runs_root.parent.name == "detect":
                # This is a nested runs/detect structure - delete the embereye_* folder
                model_run = best_pt.parents[2]  # The embereye_TIMESTAMP folder
                import shutil
                shutil.rmtree(model_run)
                logger.info(f"Cleaned up runs directory: {model_run}")
        except Exception as e:
            logger.warning(f"Failed to clean up runs directory: {e}")

    def _archive_existing_models(self):
        """Archive any existing trained models that haven't been archived yet."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Search for best.pt in multiple possible locations
            search_paths = [
                Path(get_data_path("training_data")) / "runs" / "detect",
                Path.cwd() / "runs" / "detect",
                Path.cwd() / "embereye-studio" / "runs" / "detect",
                Path(get_data_path("")) / "runs" / "detect",
            ]
            
            best_pts = []
            for search_path in search_paths:
                if search_path.exists():
                    found = list(search_path.rglob("best.pt"))
                    best_pts.extend(found)
            
            if not best_pts:
                return
            
            # Get already archived models
            models_dir = Path(get_data_path("models"))
            versions_dir = models_dir / "yolo_versions"
            versions_dir.mkdir(parents=True, exist_ok=True)
            
            archived_count = 0
            for best_pt in sorted(best_pts, key=lambda p: p.stat().st_mtime):
                # Extract timestamp from parent directory or use file modification time
                try:
                    # Try to parse project name like embereye_20260216_210145
                    project_name = best_pt.parent.parent.name
                    if "_" in project_name and len(project_name.split("_")) >= 3:
                        parts = project_name.split("_")
                        timestamp_str = f"{parts[-2]}_{parts[-1]}"
                        version_name = f"v{timestamp_str}"
                    else:
                        # Use file modification time
                        mtime = datetime.fromtimestamp(best_pt.stat().st_mtime)
                        version_name = f"v{mtime.strftime('%Y%m%d_%H%M%S')}"
                except Exception:
                    # Fallback to file modification time
                    mtime = datetime.fromtimestamp(best_pt.stat().st_mtime)
                    version_name = f"v{mtime.strftime('%Y%m%d_%H%M%S')}"
                
                version_dir = versions_dir / version_name
                
                # Skip if already archived
                if version_dir.exists() and (version_dir / "best.pt").exists():
                    continue
                
                # Archive this model
                version_dir.mkdir(parents=True, exist_ok=True)
                
                import shutil
                target_path = version_dir / "best.pt"
                shutil.copy2(best_pt, target_path)
                
                # Copy metadata files
                project_dir = best_pt.parent.parent
                for metadata_file in ["args.yaml", "results.csv", "results.png"]:
                    src = project_dir / metadata_file
                    if src.exists():
                        shutil.copy2(src, version_dir / metadata_file)
                
                archived_count += 1
            
            if archived_count > 0:
                logger.info(f"Archived {archived_count} existing trained models")
        except Exception as e:
            logger.warning(f"Failed to archive existing models: {e}")

    def _on_training_finished(self, ok: bool, msg: str):
        """Handle training completion."""
        self.training_active = False
        if self.training_worker:
            self.training_worker.quit()
            self.training_worker.wait(5000)
            self.training_worker = None
        if hasattr(self, 'start_training_btn'):
            self.start_training_btn.setEnabled(True)
        if hasattr(self, 'cancel_training_btn'):
            self.cancel_training_btn.setEnabled(False)
        
        if ok:
            self.training_just_completed = True
            if hasattr(self, 'training_status_label'):
                self.training_status_label.setText("✓ Training completed!")
            if hasattr(self, 'training_progress'):
                self.training_progress.setValue(100)
            
            # Archive the trained model to yolo_versions
            try:
                self._archive_trained_model()
            except Exception as e:
                logger.warning(f"Failed to archive model: {e}")
            
            # Refresh UI components
            self._refresh_model_versions()
            self._refresh_dataset_stats()
            # Refresh sandbox models to show the newly trained model
            try:
                self._refresh_sandbox_models()
            except Exception as e:
                logger.warning(f"Failed to refresh sandbox models: {e}")
            
            QMessageBox.information(self, "Training Complete", msg)
        else:
            if hasattr(self, 'training_status_label'):
                self.training_status_label.setText(f"✗ Training failed")
            QMessageBox.critical(self, "Training Failed", msg)

    def _summarize_unclassified_in_dataset(self):
        """Summarize items flagged as unclassified in the dataset."""
        try:
            from pathlib import Path
            import yaml
            
            dataset_dir = Path(get_data_path("training_data")) / "dataset"
            ds_yaml = dataset_dir / "dataset.yaml"
            
            if not ds_yaml.exists():
                return "Dataset not prepared yet"
            
            cfg = yaml.safe_load(ds_yaml.read_text())
            names = cfg.get('names', [])
            
            # Find unclassified indices
            unclassified_indices = {i for i, n in enumerate(names) if str(n).startswith('unclassified_')}
            
            if not unclassified_indices:
                return "No unclassified items found"
            
            # Count occurrences
            label_root = dataset_dir / 'labels'
            total_unclassified = 0
            splits_with_unclassified = []
            
            for split in ['train', 'val', 'test']:
                split_labels = label_root / split
                if not split_labels.exists():
                    continue
                
                split_count = 0
                for lbl in split_labels.glob('*.txt'):
                    try:
                        lines = lbl.read_text().splitlines()
                        for line in lines:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                try:
                                    cid = int(parts[0])
                                    if cid in unclassified_indices:
                                        split_count += 1
                                except:
                                    pass
                    except:
                        pass
                
                if split_count > 0:
                    total_unclassified += split_count
                    splits_with_unclassified.append(f"{split}: {split_count}")
            
            if total_unclassified == 0:
                return "No unclassified items found in dataset"
            
            return f"Total unclassified: {total_unclassified}\n" + "\n".join(splits_with_unclassified)
        except Exception as e:
            return f"Error: {str(e)}"

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
            self.training_epoch_label.setText("Epoch: 0/0")
            self.training_active = True

            self.training_worker = TrainingWorker(config=config, parent=self)
            self.training_worker.progress.connect(self._on_training_progress)
            self.training_worker.finished.connect(self._on_training_finished)
            self.training_worker.device_ready.connect(self._on_device_ready)
            self.training_worker.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Training error: {str(e)}")
        finally:
            if self.training_worker is None:
                self.start_training_btn.setEnabled(True)
                self.cancel_training_btn.setEnabled(False)

    def start_quick_retraining(self):
        """Quick retrain with fewer epochs"""
        self.epochs_spin.setValue(20)
        self.start_model_training()

    def cancel_model_training(self):
        """Cancel running training"""
        if self.training_worker and self.training_worker.pipeline:
            self.training_worker.pipeline.training_active = False
        self.training_status_label.setText("Training cancelled")
        self.cancel_training_btn.setEnabled(False)

    def _on_device_ready(self, device: str):
        if hasattr(self.parent_window, "set_device_status"):
            self.parent_window.set_device_status(device)

    def export_model_version(self):
        """Export selected model version as ZIP package for Field app"""
        selected = self.model_versions_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Export Model", "Please select a model version to export.")
            return
        
        try:
            import zipfile
            import json
            from datetime import datetime
            
            # Get selected version
            version_name = selected.text().split(" ")[0]  # e.g., "v1"
            models_dir = Path(get_data_path("models")) / "yolo_versions"
            version_dir = models_dir / version_name
            best_pt = version_dir / "best.pt"
            
            if not best_pt.exists():
                QMessageBox.critical(self, "Export Error", f"Model file not found: {best_pt}")
                return
            
            # Ask user where to save
            from PyQt5.QtWidgets import QFileDialog
            export_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Model Package",
                f"{version_name}_model.zip",
                "ZIP Files (*.zip);;All Files (*.*)"
            )
            
            if not export_path:
                return  # User cancelled
            
            export_path = Path(export_path)
            
            # Create metadata with class versioning
            from embereye.core.class_config import get_leaf_classes, get_classes_hash, load_master_classes
            
            classes_dict = load_master_classes()
            leaf_classes = get_leaf_classes(classes_dict)
            classes_hash = get_classes_hash(leaf_classes)
            
            metadata = {
                "model_version": version_name,
                "export_date": datetime.now().isoformat(),
                "model_type": "YOLOv8",
                "model_name": "best.pt",
                "app": "EmberEye Studio",
                "compatible_apps": ["EmberEye Field"],
                "class_count": len(leaf_classes),
                "class_hash": classes_hash,
                "class_names": leaf_classes,
                "instructions": [
                    "1. Extract the ZIP file",
                    "2. Copy 'best.pt' to EmberEye Field's models directory",
                    "3. Restart EmberEye Field",
                    "4. Select the model from the model list"
                ]
            }
            
            # Create ZIP package
            with zipfile.ZipFile(str(export_path), 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add model file
                zipf.write(str(best_pt), arcname="best.pt")
                
                # Add master classes
                master_classes_path = Path(__file__).parent / "master_classes.json"
                if master_classes_path.exists():
                    zipf.write(str(master_classes_path), arcname="master_classes.json")
                
                # Add metadata
                zipf.writestr("metadata.json", json.dumps(metadata, indent=2))
                
                # Add README
                readme = f"""# EmberEye Model Export

Model Version: {version_name}
Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Installation Instructions

### For EmberEye Field App:

1. Extract this ZIP file
2. Locate EmberEye Field application directory:
   - Default: `D:\\EE\\EmberEye\\embereye-field\\`
3. Copy `best.pt` to the models directory
4. Copy `master_classes.json` to the main application directory (replace existing if different)
5. Restart EmberEye Field application
6. The model will appear in the model selection dropdown

## Files Included

- `best.pt`: Trained YOLOv8 model weights (ready to use)
- `master_classes.json`: Class definitions (fire, smoke, structural, human, vehicle, safety, environment)
- `metadata.json`: Model information and compatibility details
- `README.md`: This installation guide

## Compatibility

✓ EmberEye Field (Desktop)
✓ EmberEye Studio
✓ YOLOv8 Framework

## Important Notes

- **Class Definitions**: This export includes `master_classes.json` which contains the class hierarchy this model was trained with. For proper detection labeling, ensure these classes are used with this model.
- **Backup**: Consider backing up your existing `master_classes.json` before updating, in case you need to revert.

## Contact

For issues or questions, refer to the main EmberEye documentation.
"""
                zipf.writestr("README.md", readme)
            
            # Verify ZIP contents
            with zipfile.ZipFile(str(export_path), 'r') as zipf:
                file_list = zipf.namelist()
                required_files = {'best.pt', 'master_classes.json', 'metadata.json', 'README.md'}
                missing = required_files - set(file_list)
                
                if missing:
                    QMessageBox.critical(
                        self, "Export Error",
                        f"ZIP package incomplete. Missing: {', '.join(missing)}"
                    )
                    export_path.unlink()  # Delete incomplete file
                    return
            
            # Success message with option to open folder
            reply = QMessageBox.information(
                self,
                "Model Exported Successfully",
                f"Model {version_name} has been exported to:\n\n{export_path}\n\n"
                f"File size: {export_path.stat().st_size / (1024*1024):.2f} MB\n\n"
                f"Would you like to open the destination folder?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                import subprocess
                subprocess.Popen(f'explorer /select,"{export_path}"')
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export model: {e}")

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
        """Update the 'Ready for Training' count display and file tree."""
        # Don't update if training just completed (preserve completion message)
        if getattr(self, 'training_just_completed', False):
            return

        try:
            from PyQt5.QtWidgets import QTreeWidgetItem
            training_ann_base = get_data_path(os.path.join("training_data", "annotations"))
            total = self._count_annotation_files(training_ann_base)

            # Update count label
            if total == 0:
                self.training_ready_count_label.setText("0 annotation files")
                self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #888; border: none; background: transparent;")
            else:
                self.training_ready_count_label.setText(f"{total} annotation files")
                self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50; border: none; background: transparent;")

            # Update tree view grouped by class
            self.training_files_tree.clear()
            if total > 0:
                files_by_class = self._get_files_grouped_by_class(training_ann_base)
                for class_name, files in sorted(files_by_class.items()):
                    class_item = QTreeWidgetItem(self.training_files_tree, [f"{class_name} ({len(files)} files)"])
                    class_item.setExpanded(False)
                    for file_path in sorted(files):
                        file_name = os.path.basename(file_path)
                        QTreeWidgetItem(class_item, [file_name])
        except Exception:
            self.training_ready_count_label.setText("Error")
            self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #f44336; border: none; background: transparent;")

    def _refresh_dataset_stats(self):
        """Update Dataset Stats panel from resolved YOLO dataset."""
        try:
            yolo_dataset_dir = Path(get_data_path("training_data")) / "yolo_dataset"
            
            # Check if resolved dataset exists
            if not yolo_dataset_dir.exists():
                self.dataset_images_counts_label.setText("Images: dataset not prepared")
                self.dataset_classes_label.setText("Classes: —")
                return
            
            # Count images in train/val
            train_imgs = len(list((yolo_dataset_dir / "images" / "train").glob("*.*"))) if (yolo_dataset_dir / "images" / "train").exists() else 0
            val_imgs = len(list((yolo_dataset_dir / "images" / "val").glob("*.*"))) if (yolo_dataset_dir / "images" / "val").exists() else 0
            
            self.dataset_images_counts_label.setText(
                f"Images: train {train_imgs}, val {val_imgs}, test 0"
            )
            
            # Count class distribution from labels
            class_counts = {}
            for split_dir in [(yolo_dataset_dir / "labels" / "train"), (yolo_dataset_dir / "labels" / "val")]:
                if split_dir.exists():
                    for label_file in split_dir.glob("*.txt"):
                        try:
                            with open(label_file) as f:
                                for line in f:
                                    if line.strip():
                                        class_id = int(line.split()[0])
                                        class_counts[class_id] = class_counts.get(class_id, 0) + 1
                        except:
                            pass
            
            total_cls = len(class_counts)
            
            # Show top 5 classes by count
            if class_counts:
                top = sorted(class_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
                # Try to map class IDs to names from dataset.yaml
                class_names = {}
                yaml_file = yolo_dataset_dir / "dataset.yaml"
                if yaml_file.exists():
                    import yaml
                    try:
                        with open(yaml_file) as f:
                            yaml_data = yaml.safe_load(f)
                            class_names = yaml_data.get('names', {})
                    except:
                        pass
                
                top_txt = ", ".join([
                    f"{class_names.get(k, k)} ({v})" if isinstance(class_names.get(k), str) else f"Class {k} ({v})"
                    for k, v in top
                ]) if top else "—"
            else:
                top_txt = "—"
            
            self.dataset_classes_label.setText(f"Classes: {total_cls} ({top_txt})")
        except Exception as e:
            self.dataset_images_counts_label.setText("Images: —")
            self.dataset_classes_label.setText("Classes: —")

    def _refresh_model_versions(self):
        """Refresh model versions list - auto-archive any unarchived trained models first"""
        import logging
        logger = logging.getLogger(__name__)
        
        # First, auto-archive any recent trained models from runs/
        try:
            search_paths = [
                Path(get_data_path("training_data")) / "runs" / "detect",
                Path.cwd() / "runs" / "detect",
                Path.cwd() / "embereye-studio" / "runs" / "detect",
            ]
            
            recent_best_pts = []
            for search_path in search_paths:
                if search_path.exists():
                    found = list(search_path.rglob("best.pt"))
                    recent_best_pts.extend(found)
            
            # If we found recent trained models, archive them
            if recent_best_pts:
                try:
                    self._archive_trained_model()
                    logger.info("Auto-archived recent trained models")
                except Exception as e:
                    logger.warning(f"Failed to auto-archive model: {e}")
        except Exception as e:
            logger.warning(f"Error checking for recent models: {e}")
        
        # Now show all archived versions
        self.model_versions_list.clear()
        models_dir = Path(get_data_path("models")) / "yolo_versions"
        if models_dir.exists():
            version_dirs = sorted(models_dir.glob("v*"), reverse=True)
            for idx, version_dir in enumerate(version_dirs):
                # Only show versions that have a best.pt file
                if (version_dir / "best.pt").exists():
                    # Tag the first (most recent) model as "latest"
                    label = f"{version_dir.name} (latest)" if idx == 0 else version_dir.name
                    self.model_versions_list.addItem(label)

    def _delete_all_training_data(self):
        """Delete all training data"""
        reply = QMessageBox.question(
            self, "Delete All", 
            "Delete ALL training data? This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                import shutil
                training_root = Path(get_data_path("training_data"))
                ann_dir = training_root / "annotations"
                dataset_dir = training_root / "dataset"
                if ann_dir.exists():
                    shutil.rmtree(ann_dir)
                if dataset_dir.exists():
                    shutil.rmtree(dataset_dir)
                self.training_just_completed = False
                self._refresh_training_ready_count()
                try:
                    self._refresh_dataset_stats()
                except Exception:
                    pass
                QMessageBox.information(self, "Delete All", "All training data deleted.")
            except Exception as e:
                QMessageBox.critical(self, "Delete All", f"Failed to delete training data: {e}")

    def _export_annotations_package(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        try:
            default_path = os.path.join(os.path.expanduser("~"), "annotations_export.json")
            path, _ = QFileDialog.getSaveFileName(self, "Export Annotations", default_path, "JSON (*.json)")
            if not path:
                return
            from embereye.app.training_sync import export_annotations_v2
            result = export_annotations_v2(path, origin="ui")
            QMessageBox.information(
                self,
                "Export Annotations",
                f"Written: {result.get('written')}\nMedia: {result['counts']['media']}\nFrames: {result['counts']['frames']}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Annotations", f"Error: {e}")

    def _import_annotations_package(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox, QInputDialog
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Import Annotations", "", "JSON (*.json)")
            if not path:
                return
            modes = ["merge", "override"]
            mode, ok = QInputDialog.getItem(self, "Import Mode", "Choose import mode", modes, 0, False)
            if not ok:
                return
            from embereye.app.training_sync import import_annotations_v2
            from embereye.app.conflict_review_dialog import ConflictReviewDialog
            report = import_annotations_v2(path, mode=mode, dry_run=True)
            conf = report.get('report', {}).get('conflicts', {})
            dlg = ConflictReviewDialog(self, class_conflicts={}, ann_conflicts=conf)
            if dlg.exec_() == QDialog.Accepted:
                if mode == "override":
                    confirm = QMessageBox.warning(
                        self,
                        "Override Confirmation",
                        "Override will replace existing frame labels where present. Backup will be taken. Continue?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if confirm != QMessageBox.Yes:
                        return
                resolutions = dlg.get_resolutions()
                applied = import_annotations_v2(path, mode=mode, dry_run=False, resolutions=resolutions)
                dup = len(conf.get('duplicates', []))
                dis = len(conf.get('disagreements', []))
                backup_msg = f"\nBackup: {applied.get('backup') or 'n/a'}" if mode == 'override' else ""
                QMessageBox.information(
                    self,
                    "Import Annotations",
                    f"Applied: {mode}{backup_msg}\nDuplicates (dry-run): {dup}\nDisagreements (dry-run): {dis}"
                )
                try:
                    self._refresh_training_ready_count()
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, "Import Annotations", f"Error: {e}")

    def _revert_classes_from_backup(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        try:
            from embereye.app.training_sync import list_class_backups, restore_classes_backup
            backups = list_class_backups()
            start_dir = os.path.dirname(backups[0]) if backups else os.path.expanduser("~")
            path, _ = QFileDialog.getOpenFileName(self, "Select Classes Backup", start_dir, "JSON (*.json)")
            if not path:
                return
            confirm = QMessageBox.warning(
                self,
                "Revert Classes",
                "This will replace master_classes.json. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
            result = restore_classes_backup(path)
            QMessageBox.information(
                self,
                "Revert Classes",
                f"Restored from: {result.get('used_backup')}\nSafety backup: {result.get('safety_backup') or 'n/a'}"
            )
            try:
                self._refresh_dataset_stats()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Revert Classes", f"Error: {e}")

    def _revert_annotations_from_backup(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        try:
            from embereye.app.training_sync import list_annotation_backups, restore_annotations_backup
            backups = list_annotation_backups()
            start_dir = os.path.dirname(backups[0]) if backups else os.path.expanduser("~")
            path, _ = QFileDialog.getOpenFileName(self, "Select Annotations Backup", start_dir, "ZIP (*.zip)")
            if not path:
                return
            confirm = QMessageBox.warning(
                self,
                "Revert Annotations",
                "This will replace current annotations with the backup. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
            result = restore_annotations_backup(path)
            QMessageBox.information(
                self,
                "Revert Annotations",
                f"Restored to: {result.get('restored')}\nUsed backup: {result.get('used_backup')}\nSafety backup: {result.get('safety_backup') or 'n/a'}"
            )
            try:
                self._refresh_training_ready_count()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Revert Annotations", f"Error: {e}")

    def _export_annotations_zip(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        try:
            default_path = os.path.join(os.path.expanduser("~"), "annotations_full.zip")
            path, _ = QFileDialog.getSaveFileName(self, "Export Annotations + Frames (ZIP)", default_path, "ZIP (*.zip)")
            if not path:
                return
            from embereye.app.training_sync import export_annotations_zip
            result = export_annotations_zip(path)
            QMessageBox.information(
                self,
                "Export ZIP",
                f"Written: {result.get('written')}\nMedia: {result['counts']['media']}\nFiles: {result['counts']['files']}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export ZIP", f"Error: {e}")

    def _import_annotations_zip(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Import Annotations + Frames (ZIP)", "", "ZIP (*.zip)")
            if not path:
                return
            from embereye.app.training_sync import import_annotations_zip
            result = import_annotations_zip(path)

            dest_path = result.get('dest', '')
            if os.path.exists(dest_path):
                imported_bases = [
                    d for d in os.listdir(dest_path)
                    if os.path.isdir(os.path.join(dest_path, d))
                ]
                if imported_bases:
                    self.imported_zip_bases = imported_bases
                    self.training_media_imported = True
                    
                    # Verify annotations were actually extracted (Bug fix: QC Review not finding annotations)
                    total_annotations = 0
                    for base in imported_bases:
                        base_path = os.path.join(dest_path, base)
                        total_annotations += self._count_annotation_files(base_path)
                    
                    if total_annotations == 0:
                        QMessageBox.warning(
                            self,
                            "Import ZIP",
                            f"ZIP imported but no annotation .txt files found!\n\n"
                            f"Extracted {result.get('extracted', 0)} files to:\n{dest_path}\n\n"
                            f"Please ensure ZIP contains annotations/*.txt files"
                        )
                        return

            QMessageBox.information(
                self,
                "Import ZIP",
                f"Imported {result.get('media', 0)} media base(s) with {result.get('extracted', 0)} files\n\n"
                f"Next steps:\n"
                f"1. Click '🔍 QC Review' to review annotations\n"
                f"2. Click '→ Move to Training' to finalize"
            )
        except Exception as e:
            QMessageBox.critical(self, "Import ZIP", f"Error: {e}")

    def _create_sandbox_tab(self) -> QWidget:
        """Create sandbox testing UI with Active Learning"""
        from PyQt5.QtWidgets import QScrollArea, QSplitter
        
        # Main container with scroll area
        self.sandbox_widget = QWidget()
        main_layout = QVBoxLayout(self.sandbox_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        header = QLabel("🧪 Sandbox - Active Learning Review")
        header.setStyleSheet("font-weight: bold; padding: 5px; font-size: 14px;")
        main_layout.addWidget(header)
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Scroll content widget
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create horizontal splitter for left panel (preview) and right panel (review queue)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        
        # === LEFT PANEL: Model Testing ===
        self.sandbox_left_panel = QWidget()
        left_layout = QVBoxLayout(self.sandbox_left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Top row: Settings box (LEFT) + Buttons (RIGHT)
        top_row_layout = QHBoxLayout()
        
        # LEFT: Combined Settings Box (Version + Thresholds)
        settings_group = QGroupBox("Settings & Thresholds")
        settings_layout = QVBoxLayout()
        
        # Model selection
        model_select_layout = QHBoxLayout()
        model_select_layout.addWidget(QLabel("Version:"))
        self.sandbox_model_combo = QComboBox()
        self.sandbox_model_combo.setMinimumWidth(120)
        model_select_layout.addWidget(self.sandbox_model_combo, 1)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMaximumWidth(35)
        refresh_btn.clicked.connect(self._refresh_sandbox_models)
        model_select_layout.addWidget(refresh_btn)
        settings_layout.addLayout(model_select_layout)
        
        # Confidence threshold
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence:"))
        self.sandbox_conf_spin = QDoubleSpinBox()
        self.sandbox_conf_spin.setRange(0.0, 1.0)
        self.sandbox_conf_spin.setSingleStep(0.05)
        self.sandbox_conf_spin.setValue(0.50)
        self.sandbox_conf_spin.setDecimals(2)
        conf_layout.addWidget(self.sandbox_conf_spin)
        settings_layout.addLayout(conf_layout)
        
        # Grey zone thresholds
        grey_low_layout = QHBoxLayout()
        grey_low_layout.addWidget(QLabel("Grey Zone Low:"))
        self.sandbox_grey_low_spin = QDoubleSpinBox()
        self.sandbox_grey_low_spin.setRange(0.0, 1.0)
        self.sandbox_grey_low_spin.setSingleStep(0.05)
        self.sandbox_grey_low_spin.setValue(0.30)
        self.sandbox_grey_low_spin.setDecimals(2)
        self.sandbox_grey_low_spin.setToolTip("Detections below this are ignored")
        grey_low_layout.addWidget(self.sandbox_grey_low_spin)
        settings_layout.addLayout(grey_low_layout)
        
        grey_high_layout = QHBoxLayout()
        grey_high_layout.addWidget(QLabel("Grey Zone High:"))
        self.sandbox_grey_high_spin = QDoubleSpinBox()
        self.sandbox_grey_high_spin.setRange(0.0, 1.0)
        self.sandbox_grey_high_spin.setSingleStep(0.05)
        self.sandbox_grey_high_spin.setValue(0.70)
        self.sandbox_grey_high_spin.setDecimals(2)
        self.sandbox_grey_high_spin.setToolTip("Detections above this are confirmed")
        grey_high_layout.addWidget(self.sandbox_grey_high_spin)
        settings_layout.addLayout(grey_high_layout)
        
        # Detection mode toggle
        detection_layout = QHBoxLayout()
        detection_layout.addWidget(QLabel("Detection Mode:"))
        self.sandbox_detection_mode_combo = QComboBox()
        self.sandbox_detection_mode_combo.addItems(["YOLO Only", "Hybrid Mode"])
        self.sandbox_detection_mode_combo.setCurrentIndex(0)
        self.sandbox_detection_mode_combo.setToolTip("YOLO Only: pure neural network | Hybrid Mode: YOLO + heuristics")
        detection_layout.addWidget(self.sandbox_detection_mode_combo, 1)
        settings_layout.addLayout(detection_layout)
        
        # Legend
        legend = QLabel("🟢 >70% Confirmed | 🟠 30-70% Grey Zone | 🔴 Flagged")
        legend.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
        settings_layout.addWidget(legend)
        
        settings_group.setLayout(settings_layout)
        top_row_layout.addWidget(settings_group, 1)  # Stretch to take remaining space
        
        # RIGHT: Action buttons - STACKED VERTICALLY
        action_layout = QVBoxLayout()
        
        upload_img_btn = QPushButton("🖼 Select Image")
        upload_img_btn.clicked.connect(self._sandbox_upload_image)
        action_layout.addWidget(upload_img_btn)
        
        upload_vid_btn = QPushButton("🎥 Select Video")
        upload_vid_btn.clicked.connect(self._sandbox_upload_video)
        action_layout.addWidget(upload_vid_btn)
        
        self.sandbox_run_btn = QPushButton("▶ Run Inference")
        self.sandbox_run_btn.clicked.connect(self._sandbox_run_inference)
        action_layout.addWidget(self.sandbox_run_btn)
        
        action_layout.addStretch()  # Push buttons to top
        top_row_layout.addLayout(action_layout)
        
        left_layout.addLayout(top_row_layout)

        # Preview area - Result (LEFT) + Frame Viewer (RIGHT)
        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(5)
        
        # LEFT: Result with Color-Coded Detections
        results_group = QGroupBox("Result with Color-Coded Detections")
        results_layout = QVBoxLayout()
        
        self.sandbox_progress = QProgressBar()
        self.sandbox_progress.setVisible(False)
        results_layout.addWidget(self.sandbox_progress)
        
        self.sandbox_results_label = QLabel("Results appear here")
        self.sandbox_results_label.setAlignment(Qt.AlignCenter)
        self.sandbox_results_label.setStyleSheet("border: 1px solid #333; background: #111;")
        self.sandbox_results_label.setMinimumSize(280, 210)
        self.sandbox_results_label.setMaximumSize(500, 375)
        self.sandbox_results_label.setScaledContents(False)
        self.sandbox_results_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Click to popup full image
        self.sandbox_results_label.mousePressEvent = lambda event: self._sandbox_show_popup_frame(self.sandbox_results_label)
        self.sandbox_results_label.setCursor(Qt.PointingHandCursor)
        results_layout.addWidget(self.sandbox_results_label)
        
        self.sandbox_stats_label = QLabel("Detections: - | Time: -")
        self.sandbox_stats_label.setStyleSheet("font-size: 10px; font-family: monospace;")
        results_layout.addWidget(self.sandbox_stats_label)
        
        results_group.setLayout(results_layout)
        preview_layout.addWidget(results_group)
        
        # RIGHT: Frame Viewer with Prev/Next
        frame_viewer_group = QGroupBox("Frame Viewer")
        frame_viewer_layout = QVBoxLayout()
        
        self.sandbox_frame_label = QLabel("No frame selected")
        self.sandbox_frame_label.setAlignment(Qt.AlignCenter)
        self.sandbox_frame_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
        self.sandbox_frame_label.setMinimumSize(280, 210)
        self.sandbox_frame_label.setMaximumSize(500, 375)
        self.sandbox_frame_label.setScaledContents(False)
        self.sandbox_frame_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Click to popup full image
        self.sandbox_frame_label.mousePressEvent = lambda event: self._sandbox_show_popup_frame(self.sandbox_frame_label)
        self.sandbox_frame_label.setCursor(Qt.PointingHandCursor)
        frame_viewer_layout.addWidget(self.sandbox_frame_label)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.sandbox_prev_btn = QPushButton("◄ PREV")
        self.sandbox_prev_btn.clicked.connect(self._sandbox_prev_frame)
        nav_layout.addWidget(self.sandbox_prev_btn)
        
        self.sandbox_next_btn = QPushButton("NEXT ►")
        self.sandbox_next_btn.clicked.connect(self._sandbox_next_frame)
        nav_layout.addWidget(self.sandbox_next_btn)
        
        frame_viewer_layout.addLayout(nav_layout)
        
        frame_viewer_group.setLayout(frame_viewer_layout)
        preview_layout.addWidget(frame_viewer_group)
        
        left_layout.addLayout(preview_layout)
        
        splitter.addWidget(self.sandbox_left_panel)
        
        # === RIGHT PANEL: Review Queues ===
        self.sandbox_right_panel = QWidget()
        right_layout = QVBoxLayout(self.sandbox_right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        queue_header = QLabel("Review Queues")
        queue_header.setStyleSheet("font-weight: bold; font-size: 12px; padding: 3px;")
        right_layout.addWidget(queue_header)
        
        # Grey Zone Queue
        grey_zone_group = QGroupBox("🟠 Grey Zone (30-70% Confidence)")
        grey_zone_layout = QVBoxLayout()
        
        self.grey_zone_list = QListWidget()
        self.grey_zone_list.setMaximumHeight(200)
        self.grey_zone_list.itemClicked.connect(self._on_grey_zone_item_clicked)
        grey_zone_layout.addWidget(self.grey_zone_list)
        
        grey_zone_btn_layout = QHBoxLayout()
        confirm_grey_btn = QPushButton("✓ Confirm")
        confirm_grey_btn.setStyleSheet("background: #2d5; color: white;")
        confirm_grey_btn.clicked.connect(lambda: self._confirm_detection(is_grey_zone=True))
        grey_zone_btn_layout.addWidget(confirm_grey_btn)
        
        reject_grey_btn = QPushButton("✗ Reject")
        reject_grey_btn.setStyleSheet("background: #d52; color: white;")
        reject_grey_btn.clicked.connect(lambda: self._reject_detection(is_grey_zone=True))
        grey_zone_btn_layout.addWidget(reject_grey_btn)
        
        flag_grey_btn = QPushButton("🚩 Flag")
        flag_grey_btn.setStyleSheet("background: #fa0; color: white;")
        flag_grey_btn.clicked.connect(lambda: self._flag_detection(is_grey_zone=True))
        grey_zone_btn_layout.addWidget(flag_grey_btn)
        
        grey_zone_layout.addLayout(grey_zone_btn_layout)
        grey_zone_group.setLayout(grey_zone_layout)
        right_layout.addWidget(grey_zone_group)
        
        # User Flags Queue
        flags_group = QGroupBox("🔴 User Flagged Items")
        flags_layout = QVBoxLayout()
        
        self.flagged_list = QListWidget()
        self.flagged_list.setMaximumHeight(150)
        self.flagged_list.itemClicked.connect(self._on_flagged_item_clicked)
        flags_layout.addWidget(self.flagged_list)
        
        flags_btn_layout = QHBoxLayout()
        resolve_flag_btn = QPushButton("✓ Resolve")
        resolve_flag_btn.clicked.connect(self._resolve_flagged_item)
        flags_btn_layout.addWidget(resolve_flag_btn)
        
        annotate_btn = QPushButton("✏ Annotate")
        annotate_btn.clicked.connect(self._annotate_flagged_item)
        flags_btn_layout.addWidget(annotate_btn)
        
        flags_layout.addLayout(flags_btn_layout)
        flags_group.setLayout(flags_layout)
        right_layout.addWidget(flags_group)
        
        # Feedback Stats
        stats_group = QGroupBox("📊 Feedback Stats")
        stats_layout = QVBoxLayout()
        self.feedback_stats_label = QLabel("Total Feedback: 0\nGrey Zone: 0\nFlagged: 0")
        self.feedback_stats_label.setStyleSheet("font-size: 10px; font-family: monospace;")
        stats_layout.addWidget(self.feedback_stats_label)
        
        refresh_stats_btn = QPushButton("Refresh Stats")
        refresh_stats_btn.clicked.connect(self._refresh_feedback_stats)
        stats_layout.addWidget(refresh_stats_btn)
        
        stats_group.setLayout(stats_layout)
        right_layout.addWidget(stats_group)
        
        right_layout.addStretch()
        
        splitter.addWidget(self.sandbox_right_panel)
        
        # Set splitter sizes (70% left, 30% right)
        splitter.setSizes([700, 300])
        
        scroll_layout.addWidget(splitter)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Initialize data
        self._refresh_sandbox_models()
        self._refresh_feedback_stats()
        
        # Store current image/video path and detections
        self.sandbox_current_image = None
        self.sandbox_is_video = False
        self.sandbox_current_detections = []
        self.sandbox_current_frame_index = 0  # For frame viewer navigation
        self.sandbox_video_frames = {}  # Cache for video frames {frame_num: frame_data}
        self.sandbox_current_pixmap = None  # For popup
        
        return self.sandbox_widget

    def _refresh_sandbox_models(self):
        """Refresh sandbox model list from trained and pretrained models"""
        import logging
        logger = logging.getLogger(__name__)
        
        self.sandbox_model_combo.clear()
        has_trained_models = False
        
        # First, check for recently trained models in runs/ directory
        try:
            search_paths = [
                Path(get_data_path("training_data")) / "runs" / "detect",
                Path.cwd() / "runs" / "detect",
                Path.cwd() / "embereye-studio" / "runs" / "detect",
            ]
            
            recent_best_pts = []
            for search_path in search_paths:
                if search_path.exists():
                    found = list(search_path.rglob("best.pt"))
                    recent_best_pts.extend(found)
            
            # If we found recent trained models, archive them
            if recent_best_pts:
                try:
                    self._archive_trained_model()
                except Exception as e:
                    logger.warning(f"Failed to auto-archive model: {e}")
        except Exception as e:
            logger.warning(f"Error checking for recent models: {e}")
        
        # Add archived version (trained models)
        try:
            models_dir = Path(get_data_path("models")) / "yolo_versions"
            if models_dir.exists():
                for idx, version_dir in enumerate(sorted(models_dir.glob("v*"), reverse=True)):
                    best_pt = version_dir / "best.pt"
                    if best_pt.exists():
                        # Tag the first (most recent) model as "latest"
                        if idx == 0:
                            label = f"{version_dir.name} (latest)"
                        else:
                            label = f"{version_dir.name} (trained)"
                        self.sandbox_model_combo.addItem(label)
                        has_trained_models = True
                        logger.info(f"Added trained model: {version_dir.name}")
        except Exception as e:
            logger.warning(f"Error loading trained models: {e}")
        
        # Add pretrained models
        self.sandbox_model_combo.addItem("yolov8n.pt (pretrained)")
        
        # Set default selection to latest trained model if available
        if has_trained_models:
            self.sandbox_model_combo.setCurrentIndex(0)
        else:
            self.sandbox_model_combo.setCurrentIndex(self.sandbox_model_combo.count() - 1)

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
            self.sandbox_current_image = file_path
            self.sandbox_is_video = False
            # Clear frame viewer
            self.sandbox_frame_label.setText(f"Ready: {Path(file_path).name}")
            self.sandbox_video_frames.clear()
            self.sandbox_current_frame_index = 0
            QMessageBox.information(self, "Image Selected", f"Ready to run inference on:\n{Path(file_path).name}")

    def _sandbox_upload_video(self):
        """Select video for inference"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Videos (*.mp4 *.avi *.mov)"
        )
        if file_path:
            self.sandbox_current_image = file_path  # Store video path
            self.sandbox_is_video = True
            # Clear frame viewer and cache
            self.sandbox_frame_label.setText(f"Ready: {Path(file_path).name}\n📹 Video selected - run inference to start")
            self.sandbox_video_frames.clear()
            self.sandbox_current_frame_index = 0
            QMessageBox.information(self, "Video Selected", f"Ready to run inference on:\n{Path(file_path).name}")

    def _sandbox_run_inference(self):
        """Run inference on selected image/video with color-coded detections"""
        if not hasattr(self, 'sandbox_current_image') or not self.sandbox_current_image:
            QMessageBox.warning(self, "No Media", "Please select an image or video first")
            return
        
        # Check if it's a video
        if hasattr(self, 'sandbox_is_video') and self.sandbox_is_video:
            self._sandbox_run_video_inference()
            return
        
        # Image inference
        self._sandbox_run_image_inference()

    def _sandbox_run_image_inference(self):
        """Run inference on a single image"""
        
        try:
            import cv2
            import time
            from ultralytics import YOLO
            
            # Get selected model
            model_name = self.sandbox_model_combo.currentText()
            if "(pretrained)" in model_name:
                model_path = "yolov8n.pt"
            else:
                version = model_name.split(" ")[0]
                models_dir = Path(get_data_path("models")) / "yolo_versions"
                model_path = str(models_dir / version / "best.pt")
            
            # Load model
            self.sandbox_progress.setVisible(True)
            self.sandbox_progress.setValue(10)
            model = YOLO(model_path)
            
            # Run inference
            self.sandbox_progress.setValue(30)
            start_time = time.time()
            results = model(self.sandbox_current_image, conf=self.sandbox_conf_spin.value())
            inference_time = time.time() - start_time
            
            # Process results
            self.sandbox_progress.setValue(60)
            img = cv2.imread(self.sandbox_current_image)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            grey_low = self.sandbox_grey_low_spin.value()
            grey_high = self.sandbox_grey_high_spin.value()
            
            grey_zone_items = []
            confirmed_items = []
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get box coordinates and confidence
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    class_name = model.names[cls] if cls < len(model.names) else f"class_{cls}"
                    
                    # Color-code based on confidence
                    if conf >= grey_high:
                        # Green: Confirmed (>70%)
                        color = (0, 255, 0)
                        confirmed_items.append(f"{class_name}: {conf:.2f}")
                    elif conf >= grey_low:
                        # Orange: Grey Zone (30-70%)
                        color = (255, 165, 0)
                        grey_zone_items.append({
                            'class': class_name,
                            'conf': conf,
                            'bbox': [int(x1), int(y1), int(x2), int(y2)]
                        })
                    else:
                        # Skip items below grey_low
                        continue
                    
                    # Draw bounding box
                    cv2.rectangle(img_rgb, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    
                    # Draw label with background
                    label = f"{class_name} {conf:.2f}"
                    (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(img_rgb, (int(x1), int(y1) - label_h - 10), (int(x1) + label_w, int(y1)), color, -1)
                    cv2.putText(img_rgb, label, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Display result
            self.sandbox_progress.setValue(80)
            height, width, channel = img_rgb.shape
            bytes_per_line = 3 * width
            q_img = QImage(img_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            # Scale to fit within label bounds
            label_size = self.sandbox_results_label.size()
            scaled_pixmap = pixmap.scaled(
                label_size.width() - 4,
                label_size.height() - 4,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.sandbox_results_label.setPixmap(scaled_pixmap)
            
            # Update stats
            total_detections = len(confirmed_items) + len(grey_zone_items)
            self.sandbox_stats_label.setText(
                f"Detections: {total_detections} | Confirmed: {len(confirmed_items)} | Grey Zone: {len(grey_zone_items)} | Time: {inference_time:.2f}s"
            )
            
            # Update grey zone queue
            self.grey_zone_list.clear()
            for item in grey_zone_items:
                self.grey_zone_list.addItem(f"{item['class']}: {item['conf']:.2f}")
            
            # Store detections for feedback
            self.sandbox_current_detections = grey_zone_items
            
            self.sandbox_progress.setValue(100)
            self.sandbox_progress.setVisible(False)
            
        except Exception as e:
            self.sandbox_progress.setVisible(False)
            QMessageBox.critical(self, "Inference Error", f"Failed to run inference: {e}")

    def _sandbox_run_video_inference(self):
        """Run inference on video and save output"""
        try:
            import cv2
            import time
            from ultralytics import YOLO
            
            # Get selected model
            model_name = self.sandbox_model_combo.currentText()
            if "(pretrained)" in model_name:
                model_path = "yolov8n.pt"
            else:
                version = model_name.split(" ")[0]
                models_dir = Path(get_data_path("models")) / "yolo_versions"
                model_path = str(models_dir / version / "best.pt")
            
            # Load model
            self.sandbox_progress.setVisible(True)
            self.sandbox_progress.setValue(5)
            model = YOLO(model_path)
            
            # Open video
            cap = cv2.VideoCapture(self.sandbox_current_image)
            if not cap.isOpened():
                raise Exception("Failed to open video file")
            
            # Get video properties
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Create output path
            input_path = Path(self.sandbox_current_image)
            output_path = input_path.parent / f"{input_path.stem}_inference{input_path.suffix}"
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
            
            # Get thresholds
            grey_low = self.sandbox_grey_low_spin.value()
            grey_high = self.sandbox_grey_high_spin.value()
            
            # Process video
            frame_count = 0
            total_detections = 0
            grey_zone_count = 0
            grey_zone_items = []  # Store grey zone detections
            start_time = time.time()
            
            self.sandbox_progress.setValue(10)
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Run inference
                results = model(frame, conf=self.sandbox_conf_spin.value(), verbose=False)
                
                # Draw detections
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        class_name = model.names[cls] if cls < len(model.names) else f"class_{cls}"
                        
                        # Color-code based on confidence
                        if conf >= grey_high:
                            # Green: Confirmed (>70%)
                            color = (0, 255, 0)
                            total_detections += 1
                        elif conf >= grey_low:
                            # Orange: Grey Zone (30-70%)
                            color = (255, 165, 0)
                            total_detections += 1
                            grey_zone_count += 1
                            # Store grey zone item for review
                            grey_zone_items.append({
                                'class': class_name,
                                'conf': conf,
                                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                'frame': frame_count
                            })
                        else:
                            # Skip items below grey_low
                            continue
                        
                        # Draw bounding box
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        
                        # Draw label
                        label = f"{class_name} {conf:.2f}"
                        (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        cv2.rectangle(frame, (int(x1), int(y1) - label_h - 10), (int(x1) + label_w, int(y1)), color, -1)
                        cv2.putText(frame, label, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Write frame
                out.write(frame)
                
                # Update progress
                frame_count += 1
                progress = int(10 + (frame_count / total_frames) * 80)
                self.sandbox_progress.setValue(progress)
                
                # Show sample frame in results (every 30 frames)
                if frame_count % 30 == 0:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, c = frame_rgb.shape
                    bytes_per_line = 3 * w
                    q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_img)
                    label_size = self.sandbox_results_label.size()
                    scaled_pixmap = pixmap.scaled(
                        label_size.width() - 4,
                        label_size.height() - 4,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.sandbox_results_label.setPixmap(scaled_pixmap)
            
            # Release resources
            cap.release()
            out.release()
            
            # Populate grey zone list for review
            self.grey_zone_list.clear()
            for item in grey_zone_items[:100]:  # Limit to first 100 for performance
                self.grey_zone_list.addItem(f"{item['class']}: {item['conf']:.2f} (Frame {item['frame']})")
            
            # Store detections for feedback
            self.sandbox_current_detections = grey_zone_items
            
            # Calculate stats
            processing_time = time.time() - start_time
            avg_fps = frame_count / processing_time if processing_time > 0 else 0
            
            # Update stats
            self.sandbox_stats_label.setText(
                f"Video: {frame_count} frames | Detections: {total_detections} | Grey Zone: {grey_zone_count} | "
                f"Time: {processing_time:.1f}s ({avg_fps:.1f} FPS)"
            )
            
            self.sandbox_progress.setValue(100)
            self.sandbox_progress.setVisible(False)
            
            # Show completion message
            reply = QMessageBox.question(
                self,
                "Video Inference Complete",
                f"Video processed successfully!\n\n"
                f"Frames processed: {frame_count}\n"
                f"Total detections: {total_detections}\n"
                f"Grey zone detections: {grey_zone_count}\n"
                f"Processing time: {processing_time:.1f}s\n\n"
                f"Output saved to:\n{output_path}\n\n"
                f"Would you like to open the output folder?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                import subprocess
                subprocess.Popen(f'explorer /select,"{output_path}"')
            
        except Exception as e:
            self.sandbox_progress.setVisible(False)
            QMessageBox.critical(self, "Video Inference Error", f"Failed to process video: {e}")

    def _on_grey_zone_item_clicked(self, item):
        """Handle click on grey zone item - show frame with that detection"""
        index = self.grey_zone_list.row(item)
        if index < 0 or index >= len(self.sandbox_current_detections):
            return
        
        detection = self.sandbox_current_detections[index]
        frame_num = detection.get('frame', 0)
        self._sandbox_display_frame(frame_num, highlight_detection=detection)

    def _on_flagged_item_clicked(self, item):
        """Handle click on flagged item - show frame with that detection"""
        index = self.flagged_list.row(item)
        if index < 0:
            return
        
        # Get flagged items from database
        db = StudioDatabaseManager()
        flagged_items = db.get_flagged_items()
        db.close()
        
        if index < len(flagged_items):
            flagged = flagged_items[index]
            # Parse detection data
            import json
            try:
                detection = json.loads(flagged['detection_data'])
                frame_num = detection.get('frame', 0)
                self._sandbox_display_frame(frame_num, highlight_detection=detection)
            except:
                pass

    def _sandbox_display_frame(self, frame_num, highlight_detection=None):
        """Display a specific frame from video with optional detection highlight"""
        if not self.sandbox_is_video or not self.sandbox_current_image:
            return
        
        try:
            import cv2
            
            # Get frame from cache or extract from video
            if frame_num in self.sandbox_video_frames:
                frame = self.sandbox_video_frames[frame_num]
            else:
                # Extract frame from video
                cap = cv2.VideoCapture(self.sandbox_current_image)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    return
                
                # Cache frame
                self.sandbox_video_frames[frame_num] = frame
            
            # Draw all detections from this frame
            frame_detections = [d for d in self.sandbox_current_detections if d.get('frame') == frame_num]
            
            for detection in frame_detections:
                bbox = detection.get('bbox', [0, 0, 100, 100])
                conf = detection.get('conf', 0)
                class_name = detection.get('class', 'unknown')
                
                # Color based on confidence
                grey_low = self.sandbox_grey_low_spin.value()
                grey_high = self.sandbox_grey_high_spin.value()
                
                if conf >= grey_high:
                    color = (0, 255, 0)  # Green
                elif conf >= grey_low:
                    color = (255, 165, 0)  # Orange
                else:
                    color = (255, 0, 0)  # Red
                
                # Highlight selected detection with thicker border
                thickness = 3 if highlight_detection and detection == highlight_detection else 2
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, thickness)
                
                # Draw label
                label = f"{class_name} {conf:.2f}"
                (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (bbox[0], bbox[1] - label_h - 10), (bbox[0] + label_w, bbox[1]), color, -1)
                cv2.putText(frame, label, (bbox[0], bbox[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Convert to QPixmap and display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, c = frame_rgb.shape
            bytes_per_line = 3 * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            
            # Store for popup
            self.sandbox_current_pixmap = pixmap
            
            # Display in frame viewer (scaled)
            label_size = self.sandbox_frame_label.size()
            scaled_pixmap = pixmap.scaled(
                label_size.width() - 4,
                label_size.height() - 4,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.sandbox_frame_label.setPixmap(scaled_pixmap)
            
            # Update current frame index for prev/next
            self.sandbox_current_frame_index = frame_num
            
        except Exception as e:
            QMessageBox.critical(self, "Frame Display Error", f"Failed to display frame: {e}")

    def _sandbox_prev_frame(self):
        """Display previous frame"""
        if self.sandbox_current_frame_index > 0:
            self._sandbox_display_frame(self.sandbox_current_frame_index - 1)

    def _sandbox_next_frame(self):
        """Display next frame"""
        # Get max frame from detections
        if self.sandbox_current_detections:
            max_frame = max(d.get('frame', 0) for d in self.sandbox_current_detections)
            if self.sandbox_current_frame_index < max_frame:
                self._sandbox_display_frame(self.sandbox_current_frame_index + 1)

    def _sandbox_show_popup_frame(self, label):
        """Show full resolution image in popup window"""
        # Use stored pixmap if available
        if not self.sandbox_current_pixmap:
            QMessageBox.warning(self, "No Image", "No image to display")
            return
        
        try:
            # Create popup window
            popup = QWidget()
            popup.setWindowTitle("Frame Preview - Press ESC to close")
            popup.resize(1000, 800)
            popup.setStyleSheet("background: #111;")
            
            layout = QVBoxLayout(popup)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Create scroll area for large images
            scroll = QScrollArea()
            scroll.setStyleSheet("background: #111;")
            scroll.setWidgetResizable(True)
            
            # Create a NEW label inside the popup (don't reuse the original label)
            img_label = QLabel()
            img_label.setPixmap(self.sandbox_current_pixmap)
            img_label.setAlignment(Qt.AlignCenter)
            scroll.setWidget(img_label)
            
            layout.addWidget(scroll)
            
            # Info label
            info = QLabel("Press ESC to close")
            info.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
            layout.addWidget(info)
            
            # Handle ESC key to close popup
            def handle_key(event):
                if event.key() == Qt.Key_Escape:
                    popup.close()
            
            popup.keyPressEvent = handle_key
            popup.setFocus()
            popup.show()
            
        except Exception as e:
            QMessageBox.critical(self, "Popup Error", f"Failed to show popup: {e}")

    def _confirm_detection(self, is_grey_zone=True):
        """Confirm a detection as correct"""
        list_widget = self.grey_zone_list if is_grey_zone else self.flagged_list
        current_item = list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select an item from the queue")
            return
        
        # Get the detection data
        index = list_widget.currentRow()
        if is_grey_zone and index < len(self.sandbox_current_detections):
            detection = self.sandbox_current_detections[index]
            
            # Store feedback in database
            db = StudioDatabaseManager()
            model_version = self.sandbox_model_combo.currentText()
            db.add_sandbox_feedback(
                image_path=self.sandbox_current_image,
                model_version=model_version,
                detection_data=detection,
                confidence=detection['conf'],
                user_label='confirmed',
                feedback='confirmed',
                flagged=0,
                reviewed_by='current_user',
                notes='User confirmed detection'
            )
            db.close()
            
            # Remove from grey zone queue
            list_widget.takeItem(index)
            self.sandbox_current_detections.pop(index)
            
            # Refresh stats
            self._refresh_feedback_stats()
            
            QMessageBox.information(self, "Confirmed", "Detection confirmed and saved for training")

    def _reject_detection(self, is_grey_zone=True):
        """Reject a detection as incorrect"""
        list_widget = self.grey_zone_list if is_grey_zone else self.flagged_list
        current_item = list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select an item from the queue")
            return
        
        # Get the detection data
        index = list_widget.currentRow()
        if is_grey_zone and index < len(self.sandbox_current_detections):
            detection = self.sandbox_current_detections[index]
            
            # Store feedback in database
            db = StudioDatabaseManager()
            model_version = self.sandbox_model_combo.currentText()
            db.add_sandbox_feedback(
                image_path=self.sandbox_current_image,
                model_version=model_version,
                detection_data=detection,
                confidence=detection['conf'],
                user_label='rejected',
                feedback='rejected',
                flagged=0,
                reviewed_by='current_user',
                notes='User rejected detection'
            )
            db.close()
            
            # Remove from grey zone queue
            list_widget.takeItem(index)
            self.sandbox_current_detections.pop(index)
            
            # Refresh stats
            self._refresh_feedback_stats()
            
            QMessageBox.information(self, "Rejected", "Detection rejected and saved for training")

    def _flag_detection(self, is_grey_zone=True):
        """Flag a detection for manual annotation"""
        list_widget = self.grey_zone_list if is_grey_zone else self.flagged_list
        current_item = list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select an item from the queue")
            return
        
        # Get the detection data
        index = list_widget.currentRow()
        if is_grey_zone and index < len(self.sandbox_current_detections):
            detection = self.sandbox_current_detections[index]
            
            # Store feedback in database with flagged status
            db = StudioDatabaseManager()
            model_version = self.sandbox_model_combo.currentText()
            db.add_sandbox_feedback(
                image_path=self.sandbox_current_image,
                model_version=model_version,
                detection_data=detection,
                confidence=detection['conf'],
                user_label='flagged',
                feedback='flagged_for_review',
                flagged=1,
                reviewed_by='current_user',
                notes='Flagged for manual annotation'
            )
            db.close()
            
            # Move to flagged list
            self.flagged_list.addItem(current_item.text())
            list_widget.takeItem(index)
            self.sandbox_current_detections.pop(index)
            
            # Refresh stats
            self._refresh_feedback_stats()
            
            QMessageBox.information(self, "Flagged", "Detection flagged for manual annotation")

    def _resolve_flagged_item(self):
        """Resolve a flagged item"""
        current_item = self.flagged_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a flagged item")
            return
        
        # Remove from flagged list
        self.flagged_list.takeItem(self.flagged_list.currentRow())
        self._refresh_feedback_stats()
        QMessageBox.information(self, "Resolved", "Flagged item resolved")

    def _annotate_flagged_item(self):
        """Open annotation tool for flagged item"""
        current_item = self.flagged_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a flagged item to annotate")
            return
        
        QMessageBox.information(self, "Annotate", "Annotation tool integration coming soon!\n\nThis will open the annotation tool to manually label the detection.")

    def _refresh_feedback_stats(self):
        """Refresh feedback statistics"""
        try:
            db = StudioDatabaseManager()
            total_feedback = db.get_feedback_count()
            flagged_items = db.get_flagged_items()
            db.close()
            
            grey_zone_count = self.grey_zone_list.count()
            flagged_count = len(flagged_items)
            
            self.feedback_stats_label.setText(
                f"Total Feedback: {total_feedback}\n"
                f"Grey Zone: {grey_zone_count}\n"
                f"Flagged: {flagged_count}"
            )
        except Exception as e:
            self.feedback_stats_label.setText(f"Error loading stats: {e}")


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
        self.classes_tree = None
        self._classes_dict = None
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

        settings_tabs = QTabWidget()

        # --- General Tab ---
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # Workspace settings
        ws_group = QGroupBox("Workspace Configuration")
        ws_layout = QFormLayout()

        training_dir = QLabel("./workspace_data/training_data")
        ws_layout.addRow("Training Data Directory:", training_dir)

        models_dir = QLabel("./workspace_data/models")
        ws_layout.addRow("Models Directory:", models_dir)

        ws_group.setLayout(ws_layout)
        general_layout.addWidget(ws_group)

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
        general_layout.addWidget(about_group)

        general_layout.addStretch()
        settings_tabs.addTab(general_tab, "General")

        # --- Classes Tab ---
        classes_tab = QWidget()
        classes_layout = QVBoxLayout(classes_tab)
        classes_layout.setContentsMargins(6, 6, 6, 6)
        classes_layout.setSpacing(6)

        classes_label = QLabel("Manage class and subclass taxonomy used by annotation and training:")
        classes_layout.addWidget(classes_label)

        refresh_bar = QWidget()
        refresh_layout = QHBoxLayout(refresh_bar)
        refresh_layout.setContentsMargins(0, 4, 0, 4)
        refresh_layout.setSpacing(8)
        open_manager_icon = QToolButton()
        open_manager_icon.setText("ⓘ")
        open_manager_icon.setToolTip("Open manager")
        open_manager_icon.setStyleSheet("font-size: 18px;")
        open_manager_icon.setFixedSize(32, 32)
        open_manager_icon.clicked.connect(self.show_master_class_config)
        refresh_layout.addWidget(open_manager_icon)
        import_icon = QToolButton()
        import_icon.setText("⬇")
        import_icon.setToolTip("Import classes")
        import_icon.setStyleSheet("font-size: 18px;")
        import_icon.setFixedSize(32, 32)
        import_icon.clicked.connect(self._import_classes_package)
        refresh_layout.addWidget(import_icon)
        export_icon = QToolButton()
        export_icon.setText("⬆")
        export_icon.setToolTip("Export classes")
        export_icon.setStyleSheet("font-size: 18px;")
        export_icon.setFixedSize(32, 32)
        export_icon.clicked.connect(self._export_classes_package)
        refresh_layout.addWidget(export_icon)
        refresh_layout.addStretch(1)
        refresh_btn = QToolButton()
        refresh_btn.setText("⟳")
        refresh_btn.setToolTip("Refresh class list")
        refresh_btn.setStyleSheet("font-size: 18px;")
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.clicked.connect(self._refresh_classes_tree)
        refresh_layout.addWidget(refresh_btn)
        classes_layout.addWidget(refresh_bar)

        self.classes_tree = QTreeWidget()
        self.classes_tree.setHeaderLabels(["Class", "Subclasses"])
        self.classes_tree.setColumnWidth(0, 260)
        self.classes_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        classes_layout.addWidget(self.classes_tree)

        settings_tabs.addTab(classes_tab, "Classes")

        # --- Models Tab ---
        models_tab = QWidget()
        models_layout = QVBoxLayout(models_tab)
        models_layout.setContentsMargins(6, 6, 6, 6)
        models_layout.setSpacing(6)

        models_label = QLabel("Import and Manage YOLO Models:")
        models_layout.addWidget(models_label)

        import_model_btn = QPushButton("📥 Import Model (.pt/.zip)")
        import_model_btn.setToolTip("Import a YOLO .pt model or Studio-exported .zip package into the workspace")
        import_model_btn.clicked.connect(self._import_model)
        models_layout.addWidget(import_model_btn)

        models_info_label = QLabel("Available Models:")
        models_layout.addWidget(models_info_label)

        self.models_list = QTextEdit()
        self.models_list.setReadOnly(True)
        self.models_list.setPlaceholderText("Imported models will appear here...\n\nModels are stored in: workspace_data/models/")
        models_layout.addWidget(self.models_list)

        settings_tabs.addTab(models_tab, "Models")

        layout.addWidget(settings_tabs)
        layout.addStretch()
        self.setLayout(layout)

        self._refresh_classes_tree()
        self._refresh_models_list()

    def show_master_class_config(self):
        """Open the master class configuration dialog and refresh classes on save."""
        try:
            from master_class_config_dialog import MasterClassConfigDialog
            from embereye.core.class_config import load_master_classes

            dlg = MasterClassConfigDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                self._classes_dict = load_master_classes()
                self._refresh_classes_tree()
                QMessageBox.information(self, "Updated", "Classes updated successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Class Manager: {e}")

    def _refresh_classes_tree(self):
        if self.classes_tree is None:
            return
        try:
            from embereye.core.class_config import load_master_classes
            self._classes_dict = load_master_classes()
        except Exception:
            self._classes_dict = {}

        self.classes_tree.clear()
        if "IncidentEnvironment" in self._classes_dict:
            root_item = self._build_tree_item(self.classes_tree, "IncidentEnvironment", None)
            root_item.setExpanded(True)
        else:
            for main_class in self._classes_dict:
                item = self._build_tree_item(self.classes_tree, main_class, None)
                item.setExpanded(True)

    def _export_classes_package(self):
        try:
            default_path = os.path.join(os.path.expanduser("~"), "classes_export.json")
            path, _ = QFileDialog.getSaveFileName(self, "Export Classes", default_path, "JSON (*.json)")
            if not path:
                return
            from embereye.app.training_sync import export_classes_v2
            result = export_classes_v2(path, origin="ui")
            QMessageBox.information(
                self,
                "Export Classes",
                f"Written: {result.get('written')}\nCategories: {result['counts']['categories']}\nClasses: {result['counts']['classes']}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Classes", f"Error: {e}")

    def _import_classes_package(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Import Classes", "", "JSON (*.json)")
            if not path:
                return
            modes = ["merge", "override"]
            mode, ok = QInputDialog.getItem(self, "Import Mode", "Choose import mode", modes, 0, False)
            if not ok:
                return
            from embereye.app.training_sync import import_classes_v2
            from embereye.app.conflict_review_dialog import ConflictReviewDialog
            report = import_classes_v2(path, mode=mode, dry_run=True)
            conflicts = report.get('report', {}).get('conflicts', {})
            dlg = ConflictReviewDialog(self, class_conflicts=conflicts, ann_conflicts={})
            if dlg.exec_() == QDialog.Accepted:
                if mode == "override":
                    confirm = QMessageBox.warning(
                        self,
                        "Override Confirmation",
                        "Override will replace current class hierarchy. Continue?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if confirm != QMessageBox.Yes:
                        return
                resolutions = dlg.get_resolutions()
                applied = import_classes_v2(path, mode=mode, dry_run=False, resolutions=resolutions)
                moved = len(conflicts.get('moved', []))
                deleted = len(conflicts.get('deleted_in_incoming', []))
                backup_msg = f"\nBackup: {applied.get('backup') or 'n/a'}" if mode == 'override' else ""
                QMessageBox.information(
                    self,
                    "Import Classes",
                    f"Applied: {applied.get('applied')}\nMoved: {moved}\nDeleted (incoming): {deleted}{backup_msg}"
                )
                self._refresh_classes_tree()
        except Exception as e:
            QMessageBox.critical(self, "Import Classes", f"Error: {e}")

    def _build_tree_item(self, parent, class_name, parent_path):
        if isinstance(parent, QTreeWidget):
            item = QTreeWidgetItem(parent, [class_name, ""])
        else:
            item = QTreeWidgetItem(parent, [class_name, ""])

        if parent_path:
            full_path = f"{parent_path}:{class_name}"
        else:
            full_path = class_name
        item.setData(0, Qt.UserRole, full_path)

        children = self._classes_dict.get(class_name, []) if self._classes_dict else []
        if children:
            item.setText(1, f"{len(children)} items")
            for child in children:
                child_item = self._build_tree_item(item, child, full_path)
                child_item.setExpanded(True)
        return item

    def _import_model(self):
        """Import a YOLO .pt model file or Studio-exported .zip package"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Import Model",
                os.path.expanduser("~"),
                "Model Files (*.pt *.zip);;PyTorch Models (*.pt);;Model Packages (*.zip);;All Files (*)"
            )
            if not file_path:
                return
            
            # Create models directory if it doesn't exist
            models_dir = Path("./workspace_data/models")
            models_dir.mkdir(parents=True, exist_ok=True)
            
            source_path = Path(file_path)

            if source_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(str(source_path), "r") as zipf:
                    names = zipf.namelist()
                    pt_candidates = [name for name in names if name.lower().endswith(".pt")]

                    if not pt_candidates:
                        raise ValueError("Selected ZIP does not contain any .pt model file")

                    preferred_name = next((name for name in pt_candidates if Path(name).name.lower() == "best.pt"), pt_candidates[0])
                    extracted_model_name = Path(preferred_name).name
                    if extracted_model_name.lower() == "best.pt":
                        extracted_model_name = f"{source_path.stem}.pt"

                    dest_path = models_dir / extracted_model_name

                    if dest_path.exists():
                        reply = QMessageBox.question(
                            self,
                            "File Exists",
                            f"Model '{dest_path.name}' already exists. Overwrite?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No
                        )
                        if reply != QMessageBox.Yes:
                            return

                    with zipf.open(preferred_name, "r") as src, dest_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

                registered_version = self._register_imported_model_version(dest_path)

                QMessageBox.information(
                    self,
                    "Model Imported",
                    f"Model package '{source_path.name}' imported successfully.\n\n"
                    f"Extracted model: {dest_path.name}\n"
                    f"Location: {dest_path}\n"
                    f"Registered for Training/Sandbox as: {registered_version}"
                )
                self._refresh_models_list()
                self._refresh_main_window_model_views()
                return

            # Copy .pt model file to workspace
            model_name = source_path.name
            dest_path = models_dir / model_name
            
            # Check if file already exists
            if dest_path.exists():
                reply = QMessageBox.question(
                    self,
                    "File Exists",
                    f"Model '{model_name}' already exists. Overwrite?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            
            shutil.copy2(file_path, dest_path)
            registered_version = self._register_imported_model_version(dest_path)
            QMessageBox.information(
                self,
                "Model Imported",
                f"Model '{model_name}' has been imported successfully.\n\n"
                f"Location: {dest_path}\n"
                f"Registered for Training/Sandbox as: {registered_version}"
            )
            self._refresh_models_list()
            self._refresh_main_window_model_views()
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import model:\n{e}")

    def _refresh_main_window_model_views(self):
        """Refresh model-dependent views owned by StudioMainWindow."""
        try:
            main_window = self.window()
            if hasattr(main_window, "_refresh_model_versions"):
                main_window._refresh_model_versions()
            if hasattr(main_window, "_refresh_sandbox_models"):
                main_window._refresh_sandbox_models()
        except Exception:
            pass

    def _register_imported_model_version(self, model_pt_path: Path) -> str:
        """Register imported model into yolo_versions so Training/Sandbox can use it."""
        models_root = Path(get_data_path("models"))
        versions_dir = models_root / "yolo_versions"
        versions_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_version = f"v{timestamp}_import"
        version_name = base_version
        version_dir = versions_dir / version_name

        suffix = 1
        while version_dir.exists():
            version_name = f"{base_version}_{suffix}"
            version_dir = versions_dir / version_name
            suffix += 1

        version_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_pt_path, version_dir / "best.pt")

        source_info = version_dir / "source_model.txt"
        source_info.write_text(str(model_pt_path), encoding="utf-8")

        return version_name

    def _refresh_models_list(self):
        """Refresh the list of available models"""
        try:
            models_dir = Path("./workspace_data/models")
            if not models_dir.exists():
                self.models_list.setText("No models directory. Models will be created on import.")
                return
            
            model_files = list(models_dir.glob("*.pt"))
            
            if not model_files:
                self.models_list.setText("No models imported yet.\n\nClick 'Import Model (.pt/.zip)' to add your first model.")
                return
            
            # Display model information
            model_info = "Available Models:\n" + "=" * 50 + "\n\n"
            for idx, model_file in enumerate(sorted(model_files), 1):
                size_mb = model_file.stat().st_size / (1024 * 1024)
                mod_time = datetime.fromtimestamp(model_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                model_info += f"{idx}. {model_file.name}\n"
                model_info += f"   Size: {size_mb:.2f} MB\n"
                model_info += f"   Modified: {mod_time}\n\n"
            
            self.models_list.setText(model_info)
        except Exception as e:
            self.models_list.setText(f"Error loading models list:\n{e}")


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
        self.training_tab = TrainingTab(self)
        tabs.addTab(self.training_tab, "Training (ForgeLab)")
        try:
            from annotation_tab import AnnotationTab
            tabs.addTab(AnnotationTab(self), "🖊️ Annotation")
        except Exception as e:
            print(f"Could not load annotation tab: {e}")
        try:
            sandbox_widget = self.training_tab.create_sandbox_tab()
            tabs.addTab(sandbox_widget, "🧪 Sandbox")
        except Exception as e:
            print(f"Could not load sandbox tab: {e}")
        tabs.addTab(DatasetTab(), "Datasets (EmberArchive)")
        tabs.addTab(SettingsTab(), "Settings")

        layout.addWidget(tabs)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.status_label = QLabel("Device: checking...")
        self.status_label.setStyleSheet("color: #ddd;")
        self.statusBar().showMessage("Ready")
        self.statusBar().addPermanentWidget(self.status_label)
        
        # Delay device detection slightly to ensure everything is initialized
        QTimer.singleShot(100, self._init_device_status)

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

    def set_status_message(self, message: str):
        self.statusBar().showMessage(message)

    def set_device_status(self, device: str):
        if hasattr(self, "status_label") and self.status_label is not None:
            self.status_label.setText(f"Device: {device}")

    def _init_device_status(self):
        """Initialize device status display on startup"""
        try:
            # Import here to ensure DLL paths are set up
            from forgelab import DeviceManager

            # Log device info and update UI status from detected device
            devices = DeviceManager.get_available_devices()
            if devices.get('gpu'):
                gpu_name = devices.get('gpu_name', 'Unknown')
                self.set_device_status("gpu")
                print(f"EmberEye Studio: Using GPU - {gpu_name}")
                self.statusBar().showMessage(f"GPU ready: {gpu_name}", 5000)
                self._write_startup_log(f"GPU ready: {gpu_name}")
            elif devices.get('mps'):
                self.set_device_status("mps")
                print("EmberEye Studio: Using MPS (Apple Metal)")
                self.statusBar().showMessage("MPS ready", 5000)
                self._write_startup_log("MPS ready")
            else:
                self.set_device_status("cpu")
                print("EmberEye Studio: Using CPU (no GPU detected)")
                self.statusBar().showMessage("Using CPU (no GPU detected)", 5000)
                self._write_startup_log("CPU mode: no GPU detected")
                
        except Exception as e:
            print(f"Warning: Device detection failed: {e}")
            self.set_device_status("cpu")
            import traceback
            traceback.print_exc()
            self._write_startup_log(f"Device detection failed: {e}")

    def _write_startup_log(self, message: str):
        try:
            log_dir = Path(__file__).parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "startup.log"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_path.write_text(f"[{timestamp}] {message}\n", encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    window = StudioMainWindow("admin")
    window.show()
    sys.exit(app.exec_())
