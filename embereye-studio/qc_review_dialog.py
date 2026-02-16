"""
Quality Control Review Dialog for EmberEye Training Data.
Review and edit annotations before moving to training dataset.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QComboBox, QListWidget, QListWidgetItem, QMessageBox, QFrame, QSlider, QCheckBox, QApplication
)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtCore import Qt, QRectF, QSize, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont
import os
import cv2
import numpy as np
from pathlib import Path
from master_class_config import load_master_classes, get_hierarchical_class_labels


class _FixedImageLabel(QLabel):
    def sizeHint(self):
        return QSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)


class QCReviewDialog(QDialog):
    """Dialog for reviewing and editing annotations before training."""
    
    def __init__(self, annotations_dir: str, image_dir: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QC Review - Annotation Quality Control")
        self.resize(1000, 700)
        self.setWindowState(Qt.WindowMaximized)
        
        self.annotations_dir = Path(annotations_dir)
        self.image_dir = Path(image_dir) if image_dir else None
        
        # Load class hierarchy
        self.classes_dict = load_master_classes()
        self.hierarchical_labels = get_hierarchical_class_labels()
        self.flat_classes = self._get_flat_class_list()
        
        # Load all annotation files (recursive to support multi-base QC review)
        self.all_annotation_files = sorted(list(self.annotations_dir.rglob("*.txt")))
        if not self.all_annotation_files:
            QMessageBox.warning(self, "No Annotations", "No annotation files found in directory.")
            self.reject()
            return
        # Current view defaults to all files
        self.annotation_files = list(self.all_annotation_files)
        # Compute media bases and quick-jump indices from the full set
        self.file_bases = []
        base_first_index = {}
        for i, fpath in enumerate(self.all_annotation_files):
            try:
                rel = fpath.relative_to(self.annotations_dir)
            except Exception:
                rel = Path(fpath)
            parts = rel.parts
            if len(parts) > 1:
                base = parts[0]
            else:
                base = self.annotations_dir.name
            self.file_bases.append(base)
            if base not in base_first_index:
                base_first_index[base] = i
        self.media_bases = sorted(base_first_index.keys())
        self.base_first_index = base_first_index
        # Counts per base for quick stats
        from collections import Counter
        self.base_counts = dict(Counter(self.file_bases))
        self.filter_base_enabled = False
        
        self.current_index = 0
        self.current_annotations = []  # List of (class_id, x_center, y_center, width, height)
        self.selected_annotation_idx = None
        self.image_cache = {}
        self._last_pixmap = None
        self._last_fast_mode = False
        self._pending_pixmap_update = False
        self._fixed_dialog_size = None
        
        self.init_ui()
        QTimer.singleShot(0, self._post_layout_sync)
        self._constrain_to_screen()
        self.load_current_frame()

    def showEvent(self, event):
        super().showEvent(event)
        self._clamp_to_screen()
        self._lock_image_frame_size()

    def _clamp_to_screen(self):
        # Ensure dialog never exceeds available screen size
        screen = None
        if self.windowHandle() and self.windowHandle().screen():
            screen = self.windowHandle().screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        max_w = avail.width()
        max_h = avail.height()
        if self.width() > max_w or self.height() > max_h:
            self.resize(min(self.width(), max_w), min(self.height(), max_h))
    
    def _get_flat_class_list(self):
        """Get flat list of all leaf classes."""
        flat = []
        for category in self.classes_dict.get("IncidentEnvironment", []):
            for leaf_class in self.classes_dict.get(category, []):
                flat.append(leaf_class)
        return flat
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Top controls
        top_layout = QHBoxLayout()
        self.frame_label = QLabel(f"Frame 1 / {len(self.annotation_files)}")
        self.frame_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        top_layout.addWidget(self.frame_label)
        top_layout.addStretch()

        # Media base jump control
        top_layout.addWidget(QLabel("Media base:"))
        self.base_combo = QComboBox()
        self.base_combo.addItem("All bases")
        for b in self.media_bases:
            self.base_combo.addItem(b)
        self.base_combo.currentIndexChanged.connect(self._on_base_changed)
        top_layout.addWidget(self.base_combo)

        # Toggle to filter the list to only the selected base
        self.filter_checkbox = QCheckBox("Show only this base")
        self.filter_checkbox.stateChanged.connect(self._on_filter_toggled)
        top_layout.addWidget(self.filter_checkbox)

        # Base stats label
        self.base_stats_label = QLabel()
        self.base_stats_label.setStyleSheet("color: #888;")
        top_layout.addWidget(self.base_stats_label)
        
        prev_btn = QPushButton("◀ Previous")
        prev_btn.clicked.connect(self.prev_frame)
        top_layout.addWidget(prev_btn)
        
        # Slider to scrub through frames quickly
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(1)
        self.frame_slider.setMaximum(max(1, len(self.annotation_files)))
        self.frame_slider.setValue(1)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(10)
        self.frame_slider.setFixedWidth(200)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        top_layout.addWidget(self.frame_slider)
        
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(self.next_frame)
        top_layout.addWidget(next_btn)
        
        layout.addLayout(top_layout)
        
        # Main area: Image + Annotations list
        main_layout = QHBoxLayout()
        
        # Left: Image display
        self.image_frame = QFrame()
        self.image_frame.setFrameStyle(QFrame.Box | QFrame.Sunken)
        from PyQt5.QtWidgets import QSizePolicy
        self.image_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        image_layout = QVBoxLayout(self.image_frame)
        image_layout.setContentsMargins(0, 0, 0, 0)
        
        self.image_label = _FixedImageLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #2b2b2b;")
        self.image_label.setScaledContents(False)
        self.image_label.setMinimumSize(1, 1)
        # Set maximum size to prevent label from expanding beyond screen
        self.image_label.setMaximumSize(1920, 1080)
        from PyQt5.QtWidgets import QSizePolicy
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        image_layout.addWidget(self.image_label)

        main_layout.addWidget(self.image_frame, 4)
        
        # Right: Annotations list + controls
        right_panel = QVBoxLayout()
        
        ann_label = QLabel("Annotations:")
        ann_label.setStyleSheet("font-weight: bold;")
        right_panel.addWidget(ann_label)
        
        self.ann_list = QListWidget()
        self.ann_list.itemClicked.connect(self.on_annotation_selected)
        right_panel.addWidget(self.ann_list)
        
        # Annotation controls
        control_layout = QVBoxLayout()
        
        class_layout = QHBoxLayout()
        class_layout.addWidget(QLabel("Class:"))
        self.class_combo = QComboBox()
        self.class_combo.addItems(self.flat_classes)
        self.class_combo.currentIndexChanged.connect(self.on_class_changed)
        class_layout.addWidget(self.class_combo)
        control_layout.addLayout(class_layout)
        
        delete_ann_btn = QPushButton("🗑 Delete Selected Annotation")
        delete_ann_btn.clicked.connect(self.delete_selected_annotation)
        control_layout.addWidget(delete_ann_btn)
        
        delete_frame_btn = QPushButton("🗑 Delete Entire Frame")
        delete_frame_btn.clicked.connect(self.delete_current_frame)
        control_layout.addWidget(delete_frame_btn)
        
        right_panel.addLayout(control_layout)
        right_panel.addStretch()
        
        right_frame = QFrame()
        right_frame.setLayout(right_panel)
        right_frame.setMaximumWidth(350)
        main_layout.addWidget(right_frame, 1)
        
        layout.addLayout(main_layout)
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #888;")
        bottom_layout.addWidget(self.stats_label)
        bottom_layout.addStretch()
        
        save_close_btn = QPushButton("💾 Save All & Close")
        save_close_btn.clicked.connect(self.save_and_close)
        save_close_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        bottom_layout.addWidget(save_close_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        
        layout.addLayout(bottom_layout)
        
        self.update_stats()
        self._update_base_stats()
    
    def load_current_frame(self, fast_mode=False):
        """Load and display current frame with annotations.
        
        Args:
            fast_mode: If True, use faster (lower quality) scaling for performance
        """
        if not (0 <= self.current_index < len(self.annotation_files)):
            return
        
        ann_file = self.annotation_files[self.current_index]
        image_file = self._find_image_for_annotation(ann_file)
        
        if not image_file or not image_file.exists():
            self.image_label.setText(f"Image not found:\n{image_file}")
            self.current_annotations = []
            self.refresh_annotation_list()
            return
        
        # Load image
        if str(image_file) in self.image_cache:
            image = self.image_cache[str(image_file)]
        else:
            image = cv2.imread(str(image_file))
            if image is None:
                self.image_label.setText(f"Failed to load:\n{image_file}")
                return
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            self.image_cache[str(image_file)] = image
        
        # Load annotations
        self.current_annotations = []
        with open(ann_file, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    # Check if rectangle (5 values) or polygon (odd number >= 5)
                    if len(parts) == 5:
                        # Rectangle: class_id xc yc width height
                        self.current_annotations.append([
                            int(parts[0]),
                            float(parts[1]),
                            float(parts[2]),
                            float(parts[3]),
                            float(parts[4])
                        ])
                    elif len(parts) % 2 == 1:  # Polygon: odd number of values (class_id x1 y1 x2 y2 ... xn yn)
                        annotation = [int(parts[0])]
                        for i in range(1, len(parts)):
                            annotation.append(float(parts[i]))
                        self.current_annotations.append(annotation)
        
        # Draw annotations on image
        display_image = self._draw_annotations(image.copy())
        
        # Convert to QPixmap
        from PyQt5.QtGui import QImage
        height, width, channel = display_image.shape
        bytes_per_line = 3 * width
        q_image = QImage(display_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
        q_pixmap = QPixmap.fromImage(q_image)
        
        # Store pixmap and apply scaling to current dialog size
        self._last_pixmap = q_pixmap
        self._sync_image_label_size()
        self._apply_pixmap(fast_mode=fast_mode)
        
        # Update UI
        self.frame_label.setText(f"Frame {self.current_index + 1} / {len(self.annotation_files)}")
        # Keep slider in sync with current index
        if hasattr(self, 'frame_slider') and self.frame_slider:
            try:
                self.frame_slider.blockSignals(True)
                self.frame_slider.setMaximum(max(1, len(self.annotation_files)))
                self.frame_slider.setValue(self.current_index + 1)
            finally:
                self.frame_slider.blockSignals(False)
        self.refresh_annotation_list()
        self.selected_annotation_idx = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._constrain_to_screen()
        self._sync_image_label_size()
        # Rescale to current dialog size without changing the dialog itself
        if self._last_pixmap is not None:
            self._apply_pixmap(fast_mode=True)
        self._clamp_to_screen()

    def _sync_image_label_size(self):
        # Keep image label locked to the image frame's content area
        if not hasattr(self, "image_frame") or self.image_frame is None:
            return
        content_size = self.image_frame.contentsRect().size()
        if content_size.width() > 10 and content_size.height() > 10:
            self.image_label.setFixedSize(content_size)

    def _lock_image_frame_size(self):
        # Lock the image frame to its current size after initial layout
        if not hasattr(self, "image_frame") or self.image_frame is None:
            return
        content_size = self.image_frame.contentsRect().size()
        if content_size.width() < 10 or content_size.height() < 10:
            return
        self.image_frame.setMinimumSize(content_size)
        self.image_frame.setMaximumSize(content_size)

    def _post_layout_sync(self):
        self._sync_image_label_size()
        if self._last_pixmap is not None:
            self._apply_pixmap(fast_mode=True)
        if self._fixed_dialog_size is None:
            self._fixed_dialog_size = self.size()
            self.setFixedSize(self._fixed_dialog_size)

    def _constrain_to_screen(self):
        # Ensure the dialog never exceeds the current screen's available geometry
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        max_w = max(800, available.width())
        max_h = max(600, available.height())
        self.setMaximumSize(max_w, max_h)
        if self.width() > max_w or self.height() > max_h:
            self.resize(min(self.width(), max_w), min(self.height(), max_h))

    def _apply_pixmap(self, fast_mode=False):
        if self._last_pixmap is None:
            return
        # Target size is the image frame's content area
        target_size = self.image_frame.contentsRect().size()
        if target_size.width() < 10 or target_size.height() < 10:
            if not self._pending_pixmap_update:
                self._pending_pixmap_update = True
                QTimer.singleShot(0, self._retry_apply_pixmap)
            return

        safe_width = max(1, target_size.width() - 10)
        safe_height = max(1, target_size.height() - 10)
        target_size = QSize(safe_width, safe_height)

        transform_mode = Qt.FastTransformation if fast_mode else Qt.SmoothTransformation
        scaled = self._last_pixmap.scaled(
            target_size,
            Qt.KeepAspectRatio,
            transform_mode
        )
        self.image_label.setPixmap(scaled)

    def _retry_apply_pixmap(self):
        self._pending_pixmap_update = False
        self._sync_image_label_size()
        self._apply_pixmap(fast_mode=True)

    def _on_base_changed(self, index: int):
        # Apply filter if enabled; otherwise just jump
        if self.filter_checkbox.isChecked() and index > 0:
            self._apply_base_filter(self.base_combo.currentText())
            return
        # If 'All bases' selected or filter disabled, restore full list and jump
        if index <= 0:
            # Restore full set
            self.annotation_files = list(self.all_annotation_files)
            self.current_index = 0
            self.load_current_frame()
            return
        # Jump to first frame of selected base within the current list
        base = self.base_combo.currentText()
        # Find first index of this base in current list
        target_path = None
        # Use full mapping to locate first overall, then map into current view
        first_overall_idx = self.base_first_index.get(base)
        if first_overall_idx is not None:
            target_path = self.all_annotation_files[first_overall_idx]
        if target_path is not None:
            try:
                self.save_current_annotations()
            except Exception:
                pass
            # Find target in current (possibly filtered) list
            try:
                self.current_index = self.annotation_files.index(target_path)
            except ValueError:
                # Not in current view; reload full view to ensure jump is visible
                self.annotation_files = list(self.all_annotation_files)
                self.current_index = first_overall_idx
            self.load_current_frame()

    def _on_filter_toggled(self, state: int):
        checked = state == Qt.Checked
        self.filter_base_enabled = checked
        if checked and self.base_combo.currentIndex() > 0:
            self._apply_base_filter(self.base_combo.currentText())
        else:
            # Restore all files
            try:
                self.save_current_annotations()
            except Exception:
                pass
            self.annotation_files = list(self.all_annotation_files)
            self.current_index = 0
            self.load_current_frame()
        self._update_base_stats()

    def _apply_base_filter(self, base: str):
        # Filter current view to only files belonging to the given base
        try:
            self.save_current_annotations()
        except Exception:
            pass
        filtered = [f for f, b in zip(self.all_annotation_files, self.file_bases) if b == base]
        if not filtered:
            return
        self.annotation_files = filtered
        self.current_index = 0
        self.load_current_frame()
        self._update_base_stats()

    def _update_base_stats(self):
        # Update the base stats label depending on selection and filter state
        total_all = len(self.all_annotation_files)
        if self.base_combo.currentIndex() <= 0:
            # All bases selected
            if self.filter_base_enabled:
                # Should not occur (filter requires a specific base), but handle gracefully
                self.base_stats_label.setText(f"All bases • Frames: {len(self.annotation_files)} of {total_all}")
            else:
                self.base_stats_label.setText(f"All bases • Frames: {total_all}")
            return
        base = self.base_combo.currentText()
        count = self.base_counts.get(base, 0)
        if self.filter_base_enabled:
            self.base_stats_label.setText(f"Base '{base}' • Frames: {len(self.annotation_files)} of {count}")
        else:
            self.base_stats_label.setText(f"Base '{base}' • Frames: {count} (unfiltered)")

    def _on_slider_changed(self, value: int):
        """Handle slider value changes."""
        # Slider is 1-based for users
        idx = int(value) - 1
        if 0 <= idx < len(self.annotation_files):
            self.current_index = idx
            # Use fast loading for slider scrubbing
            self.load_current_frame(fast_mode=True)
    
    def _find_image_for_annotation(self, ann_file: Path) -> Path:
        """Find corresponding image file for annotation."""
        stem = ann_file.stem
        
        # Try same directory first
        exts = ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']
        for ext in exts:
            img = ann_file.parent / f"{stem}{ext}"
            if img.exists():
                return img
        
        # Try image_dir if provided
        if self.image_dir and self.image_dir.exists():
            for ext in exts:
                img = self.image_dir / f"{stem}{ext}"
                if img.exists():
                    return img
        
        return None
    
    def _draw_annotations(self, image: np.ndarray) -> np.ndarray:
        """Draw bounding boxes and polygons on image."""
        h, w = image.shape[:2]
        
        for idx, annotation in enumerate(self.current_annotations):
            class_id = annotation[0]
            
            # Color: green if selected, red otherwise
            color = (0, 255, 0) if idx == self.selected_annotation_idx else (255, 100, 100)
            thickness = 3 if idx == self.selected_annotation_idx else 2
            
            # Determine if rectangle or polygon
            if len(annotation) == 5:
                # Rectangle: class_id xc yc width height
                _, xc, yc, bw, bh = annotation
                # Convert normalized to pixel coordinates
                x1 = int((xc - bw/2) * w)
                y1 = int((yc - bh/2) * h)
                x2 = int((xc + bw/2) * w)
                y2 = int((yc + bh/2) * h)
                
                cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
                
                # Label position for rectangle
                label_x, label_y = x1, y1
                
            else:
                # Polygon: class_id x1 y1 x2 y2 ... xn yn
                points = []
                for i in range(1, len(annotation), 2):
                    if i + 1 < len(annotation):
                        px = int(annotation[i] * w)
                        py = int(annotation[i + 1] * h)
                        points.append([px, py])
                
                if len(points) >= 3:
                    pts = np.array(points, dtype=np.int32)
                    cv2.polylines(image, [pts], True, color, thickness)
                    
                    # Fill with semi-transparent overlay
                    overlay = image.copy()
                    cv2.fillPoly(overlay, [pts], color)
                    alpha = 0.15 if idx != self.selected_annotation_idx else 0.25
                    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
                    
                    # Label position for polygon (at first point)
                    label_x, label_y = points[0]
                else:
                    continue
            
            # Draw class label
            class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
            label = f"{class_name} #{idx+1}"
            
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            font_thickness = 2
            (text_w, text_h), _ = cv2.getTextSize(label, font, font_scale, font_thickness)
            
            cv2.rectangle(image, (label_x, label_y - text_h - 8), (label_x + text_w + 4, label_y), color, -1)
            cv2.putText(image, label, (label_x + 2, label_y - 4), font, font_scale, (255, 255, 255), font_thickness)
        
        return image
    
    def refresh_annotation_list(self):
        """Refresh annotations list widget."""
        self.ann_list.clear()
        for idx, annotation in enumerate(self.current_annotations):
            class_id = annotation[0]
            class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
            
            if len(annotation) == 5:
                # Rectangle
                xc, yc = annotation[1], annotation[2]
                item = QListWidgetItem(f"#{idx+1}: {class_name} (Box at {xc:.3f}, {yc:.3f})")
            else:
                # Polygon
                num_points = (len(annotation) - 1) // 2
                item = QListWidgetItem(f"#{idx+1}: {class_name} (Polygon, {num_points} points)")
            
            self.ann_list.addItem(item)
    
    def on_annotation_selected(self, item):
        """Handle annotation selection from list."""
        self.selected_annotation_idx = self.ann_list.row(item)
        
        # Update class combo
        if 0 <= self.selected_annotation_idx < len(self.current_annotations):
            class_id = self.current_annotations[self.selected_annotation_idx][0]
            if class_id < len(self.flat_classes):
                self.class_combo.blockSignals(True)
                self.class_combo.setCurrentIndex(class_id)
                self.class_combo.blockSignals(False)
        
        self.load_current_frame()  # Redraw with selection
    
    def on_class_changed(self, index):
        """Handle class change for selected annotation."""
        if self.selected_annotation_idx is not None and 0 <= self.selected_annotation_idx < len(self.current_annotations):
            self.current_annotations[self.selected_annotation_idx][0] = index
            self.refresh_annotation_list()
            self.load_current_frame()
    
    def delete_selected_annotation(self):
        """Delete currently selected annotation."""
        if self.selected_annotation_idx is None:
            QMessageBox.warning(self, "No Selection", "Please select an annotation to delete.")
            return
        
        if 0 <= self.selected_annotation_idx < len(self.current_annotations):
            del self.current_annotations[self.selected_annotation_idx]
            self.selected_annotation_idx = None
            self.save_current_annotations()
            self.load_current_frame()
            self.update_stats()
    
    def delete_current_frame(self):
        """Delete current frame and its annotation file."""
        reply = QMessageBox.question(
            self, 
            "Delete Frame",
            f"Delete this frame and its annotation file?\n\n{self.annotation_files[self.current_index].name}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            ann_file = self.annotation_files[self.current_index]
            image_file = self._find_image_for_annotation(ann_file)
            
            # Delete files
            ann_file.unlink()
            if image_file and image_file.exists():
                image_file.unlink()
            
            # Remove from list(s)
            removed = self.annotation_files[self.current_index]
            del self.annotation_files[self.current_index]
            # Also remove from master list
            try:
                idx_master = self.all_annotation_files.index(removed)
                removed_base = self.file_bases[idx_master]
                # Update master lists
                self.all_annotation_files.pop(idx_master)
                self.file_bases.pop(idx_master)
                # Update counts for this base
                if removed_base in self.base_counts:
                    self.base_counts[removed_base] = max(0, self.base_counts[removed_base] - 1)
            except ValueError:
                pass
            
            if not self.annotation_files:
                QMessageBox.information(self, "Complete", "All frames deleted.")
                self.reject()
                return
            
            # Adjust index
            if self.current_index >= len(self.annotation_files):
                self.current_index = len(self.annotation_files) - 1
            
            self.load_current_frame()
            self.update_stats()
            self._update_base_stats()
    
    def save_current_annotations(self):
        """Save current annotations to file, preserving polygons and boxes."""
        ann_file = self.annotation_files[self.current_index]
        with open(ann_file, 'w') as f:
            for ann in self.current_annotations:
                if len(ann) == 5:
                    # Rectangle
                    class_id, xc, yc, bw, bh = ann
                    f.write(f"{class_id} {xc} {yc} {bw} {bh}\n")
                else:
                    # Polygon: class_id x1 y1 ... xn yn
                    line = " ".join([str(ann[0])] + [f"{v}" for v in ann[1:]])
                    f.write(line + "\n")
    
    def prev_frame(self):
        """Navigate to previous frame."""
        if self.current_index > 0:
            self.save_current_annotations()
            self.current_index -= 1
            self.load_current_frame()
    
    def next_frame(self):
        """Navigate to next frame."""
        if self.current_index < len(self.annotation_files) - 1:
            self.save_current_annotations()
            self.current_index += 1
            self.load_current_frame()
    
    def update_stats(self):
        """Update statistics label."""
        total_annotations = sum(len(self._load_annotations(f)) for f in self.annotation_files)
        self.stats_label.setText(f"Total: {len(self.annotation_files)} frames, {total_annotations} annotations")
    
    def _load_annotations(self, ann_file: Path):
        """Load annotations from file."""
        annotations = []
        if ann_file.exists():
            with open(ann_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 5:
                        annotations.append(parts)
        return annotations
    
    def save_and_close(self):
        """Save all changes and close dialog."""
        self.save_current_annotations()
        QMessageBox.information(
            self, 
            "Saved", 
            f"QC Review complete!\n\n"
            f"Frames: {len(self.annotation_files)}\n"
            f"Ready to move to training."
        )
        self.accept()
