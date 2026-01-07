"""
Quality Control Review Dialog for EmberEye Training Data.
Review and edit annotations before moving to training dataset.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QComboBox, QListWidget, QListWidgetItem, QMessageBox, QFrame, QSlider, QCheckBox
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont
import os
import cv2
import numpy as np
from pathlib import Path
from master_class_config import load_master_classes, get_hierarchical_class_labels


class QCReviewDialog(QDialog):
    """Dialog for reviewing and editing annotations before training."""
    
    def __init__(self, annotations_dir: str, image_dir: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QC Review - Annotation Quality Control")
        self.resize(1200, 800)
        
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
        
        self.init_ui()
        self.load_current_frame()
    
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
        self.frame_slider.setFixedWidth(320)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        top_layout.addWidget(self.frame_slider)
        
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(self.next_frame)
        top_layout.addWidget(next_btn)
        
        layout.addLayout(top_layout)
        
        # Main area: Image + Annotations list
        main_layout = QHBoxLayout()
        
        # Left: Image display
        image_frame = QFrame()
        image_frame.setFrameStyle(QFrame.Box | QFrame.Sunken)
        image_layout = QVBoxLayout(image_frame)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setStyleSheet("background-color: #2b2b2b;")
        image_layout.addWidget(self.image_label)
        
        main_layout.addWidget(image_frame, 3)
        
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
        
        main_layout.addLayout(right_panel, 1)
        
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
    
    def load_current_frame(self):
        """Load and display current frame with annotations."""
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
        
        # Scale to fit label
        scaled = q_pixmap.scaled(
            self.image_label.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        
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
        # Slider is 1-based for users
        idx = int(value) - 1
        if 0 <= idx < len(self.annotation_files):
            self.current_index = idx
            self.load_current_frame()
    
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
