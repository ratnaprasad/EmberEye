"""
Quality Control Review Dialog for EmberEye Training Data.
Review and edit annotations before moving to training dataset.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QComboBox, QListWidget, QListWidgetItem, QMessageBox, QFrame
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
        
        # Load all annotation files
        self.annotation_files = sorted(list(self.annotations_dir.glob("*.txt")))
        if not self.annotation_files:
            QMessageBox.warning(self, "No Annotations", "No annotation files found in directory.")
            self.reject()
            return
        
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
        
        prev_btn = QPushButton("◀ Previous")
        prev_btn.clicked.connect(self.prev_frame)
        top_layout.addWidget(prev_btn)
        
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
                if len(parts) == 5:
                    self.current_annotations.append([
                        int(parts[0]),
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                        float(parts[4])
                    ])
        
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
        self.refresh_annotation_list()
        self.selected_annotation_idx = None
    
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
        """Draw bounding boxes on image."""
        h, w = image.shape[:2]
        
        for idx, (class_id, xc, yc, bw, bh) in enumerate(self.current_annotations):
            # Convert normalized to pixel coordinates
            x1 = int((xc - bw/2) * w)
            y1 = int((yc - bh/2) * h)
            x2 = int((xc + bw/2) * w)
            y2 = int((yc + bh/2) * h)
            
            # Color: green if selected, red otherwise
            color = (0, 255, 0) if idx == self.selected_annotation_idx else (255, 100, 100)
            thickness = 3 if idx == self.selected_annotation_idx else 2
            
            cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
            
            # Draw class label
            class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
            label = f"{class_name} #{idx+1}"
            
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            font_thickness = 2
            (text_w, text_h), _ = cv2.getTextSize(label, font, font_scale, font_thickness)
            
            cv2.rectangle(image, (x1, y1 - text_h - 8), (x1 + text_w + 4, y1), color, -1)
            cv2.putText(image, label, (x1 + 2, y1 - 4), font, font_scale, (255, 255, 255), font_thickness)
        
        return image
    
    def refresh_annotation_list(self):
        """Refresh annotations list widget."""
        self.ann_list.clear()
        for idx, (class_id, xc, yc, bw, bh) in enumerate(self.current_annotations):
            class_name = self.flat_classes[class_id] if class_id < len(self.flat_classes) else f"class_{class_id}"
            item = QListWidgetItem(f"#{idx+1}: {class_name} ({xc:.3f}, {yc:.3f})")
            self.ann_list.addItem(item)
    
    def on_annotation_selected(self, item):
        """Handle annotation selection from list."""
        self.selected_annotation_idx = self.ann_list.row(item)
        
        # Update class combo
        if 0 <= self.selected_annotation_idx < len(self.current_annotations):
            class_id = self.current_annotations[self.selected_annotation_idx][0]
            if class_id < len(self.flat_classes):
                self.class_combo.setCurrentIndex(class_id)
        
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
            
            # Remove from list
            del self.annotation_files[self.current_index]
            
            if not self.annotation_files:
                QMessageBox.information(self, "Complete", "All frames deleted.")
                self.reject()
                return
            
            # Adjust index
            if self.current_index >= len(self.annotation_files):
                self.current_index = len(self.annotation_files) - 1
            
            self.load_current_frame()
            self.update_stats()
    
    def save_current_annotations(self):
        """Save current annotations to file."""
        ann_file = self.annotation_files[self.current_index]
        with open(ann_file, 'w') as f:
            for class_id, xc, yc, bw, bh in self.current_annotations:
                f.write(f"{class_id} {xc} {yc} {bw} {bh}\n")
    
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
