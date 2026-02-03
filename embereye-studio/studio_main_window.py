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
            items = ["All media bases"] + bases
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
            ann_count = self._count_annotation_files(annotations_dir)
            QMessageBox.information(
                self,
                "QC Review Complete",
                f"Review complete!\n\n"
                f"Annotations: {ann_count} files\n\n"
                f"Click 'Move to Training' to proceed."
            )

    def move_to_training(self):
        """Register annotated frames into training_data/annotations for training."""
        has_video = bool(getattr(self, 'training_selected_video_path', None))
        has_images = bool(getattr(self, 'training_selected_image_paths', []))
        has_imported_zip = bool(getattr(self, 'imported_zip_bases', []))
        
        # Check workspace annotations if no media selected
        workspace_annotations = get_data_path("annotations")
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
            annotations_dir = self._annotations_dir_for_video(self.training_selected_video_path)
        elif has_images:
            annotations_dir = self._annotations_dir_for_images(self.training_selected_image_paths)
        else:
            from PyQt5.QtWidgets import QInputDialog
            # Use workspace bases if no media selected, otherwise use imported ZIP bases
            bases = workspace_bases if workspace_bases else getattr(self, 'imported_zip_bases', [])
            items = ["All media bases"] + bases
            selected, ok = QInputDialog.getItem(
                self,
                "Move to Training",
                "Select which media to move:",
                items,
                0,
                False
            )
            if not ok:
                return
            
            if selected == "All media bases":
                total_moved = 0
                for base in bases:
                    annotations_dir = get_data_path(os.path.join("annotations", base))
                    target_dir = self._copy_annotations_to_training(annotations_dir)
                    if target_dir:
                        total_moved += self._count_annotation_files(annotations_dir)
                
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
                annotations_dir = get_data_path(os.path.join("annotations", selected))
        
        ann_count = self._count_annotation_files(annotations_dir)
        if ann_count == 0:
            QMessageBox.warning(self, "Training", "No annotations found. Annotate or ensure labels exist before moving to training.")
            return
        
        target_dir = self._copy_annotations_to_training(annotations_dir)
        if target_dir:
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
                f"Registered annotated frames for training.\n"
                f"Annotations: {ann_count} files\n"
                f"Copied to: {target_dir}\n\n"
                "Ready for next batch. Click 'Import Media' to add more."
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

    def _get_files_grouped_by_class(self, annotations_dir: str) -> dict:
        """Group annotation files by detected classes."""
        try:
            from master_class_config import load_master_classes
            
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

    def _on_training_progress(self, percent: int, message: str):
        """Update progress during training."""
        if hasattr(self, 'training_progress'):
            self.training_progress.setValue(percent)
        if hasattr(self, 'training_status_label'):
            self.training_status_label.setText(message)

    def _on_training_finished(self, ok: bool, msg: str, payload):
        """Handle training completion."""
        self.training_active = False
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
            self._refresh_model_versions()
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
        """Update Dataset Stats panel using DatasetInspector."""
        try:
            from embereye.utils import DatasetInspector
            inspector = DatasetInspector(base_dir=get_data_path(""))
            if not inspector.exists():
                self.dataset_images_counts_label.setText("Images: dataset not prepared")
                self.dataset_classes_label.setText("Classes: —")
                return
            summary = inspector.summary()
            imgs = summary.get('images', {})
            self.dataset_images_counts_label.setText(
                f"Images: train {imgs.get('train',0)}, val {imgs.get('val',0)}, test {imgs.get('test',0)}"
            )
            classes = summary.get('classes', {})
            total_cls = len(classes)
            top = sorted(classes.items(), key=lambda kv: kv[1], reverse=True)[:5]
            top_txt = ", ".join([f"{k} ({v})" for k, v in top]) if top else "—"
            self.dataset_classes_label.setText(f"Classes: {total_cls} ({top_txt})")
        except Exception:
            self.dataset_images_counts_label.setText("Images: —")
            self.dataset_classes_label.setText("Classes: —")

    def _refresh_model_versions(self):
        """Refresh model versions list"""
        self.model_versions_list.clear()
        models_dir = Path(get_data_path("models")) / "yolo_versions"
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

        layout.addWidget(settings_tabs)
        layout.addStretch()
        self.setLayout(layout)

        self._refresh_classes_tree()

    def show_master_class_config(self):
        """Open the master class configuration dialog and refresh classes on save."""
        try:
            from master_class_config_dialog import MasterClassConfigDialog
            from master_class_config import load_master_classes

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
            from master_class_config import load_master_classes
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
        training_tab = TrainingTab(self)
        tabs.addTab(training_tab, "Training (ForgeLab)")
        try:
            from annotation_tab import AnnotationTab
            tabs.addTab(AnnotationTab(self), "🖊️ Annotation")
        except Exception as e:
            print(f"Could not load annotation tab: {e}")
        try:
            sandbox_widget = training_tab.create_sandbox_tab()
            tabs.addTab(sandbox_widget, "🧪 Sandbox")
        except Exception as e:
            print(f"Could not load sandbox tab: {e}")
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
