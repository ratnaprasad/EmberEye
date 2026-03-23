"""
EmberEye Studio - Integrated Annotation Tab
Full-featured annotation interface embedded directly in studio main window
Eliminates dialog sizing issues with responsive fullscreen layout
"""

import os
import sys
import cv2
import json
from datetime import datetime
from pathlib import Path
import logging

# Import SAM Segmenter
_sam_available = False
SAMSegmenter = None
try:
    from embereye.app.sam_segmentation import SAMSegmenter
    _sam_available = True
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"SAM Segmentation not available: {e}")
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QMessageBox, QSplitter, QSlider, QListWidget,
    QSizePolicy, QRadioButton, QButtonGroup, QScrollArea, QGroupBox,
    QStackedLayout, QGraphicsBlurEffect, QCompleter
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, QPointF, QEvent
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QPolygonF, QBrush, QIcon
import logging

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Try to import SAM
try:
    from embereye.app.sam_segmentation import SAMSegmenter
    _sam_available = True
except:
    _sam_available = False
    SAMSegmenter = None

# Import centralized get_data_path
sys.path.insert(0, str(Path(__file__).parent.parent / "embereye"))
from embereye.utils.resource_helper import get_data_path
from embereye.core.class_config import (
    get_leaf_classes,
    get_classes_hash,
    load_master_classes,
    get_leaf_classes_for_category,
)


class AnnotationCanvas(QLabel):
    """A QLabel-based canvas to display frames and draw rectangles/polygons with labels."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Responsive canvas - fills available space completely
        self.setMinimumSize(QSize(640, 480))
        # No maximum size - let it fill the available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Enable keyboard focus to receive ESC key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._source_pixmap = None  # original pixmap
        self._display_pixmap = None  # scaled to fit
        self._drawing = False
        self._start = QPoint()
        self._end = QPoint()
        # list of dicts: {'rect': QRect, 'polygon': List[(x,y)], 'class': Optional[str], 'type': 'box'|'polygon'}
        self.shapes = []
        self.on_shapes_changed = None  # callback
        # Class → QColor mapping (assigned by dialog)
        self.class_colors = {}
        # Annotation mode: 'box', 'polygon', or 'manual_polygon'
        self.annotation_mode = 'box'
        # Reference to current frame BGR for SAM
        self.current_frame_bgr = None
        # Manual polygon drawing state
        self._polygon_points = []  # List of QPoint for current polygon
        self._drawing_polygon = False

    def set_frame(self, frame_bgr, fast_mode=False):
        """Set frame and update display
        
        Args:
            frame_bgr: BGR frame from OpenCV
            fast_mode: If True, use faster (lower quality) scaling for playback
        """
        h, w, _ = frame_bgr.shape
        self.current_frame_bgr = frame_bgr  # Don't copy during playback
        
        # During fast playback, downscale frame before converting to QImage
        if fast_mode and max(h, w) > 1280:
            # Downscale to max 1280px for faster processing
            scale = 1280.0 / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame_bgr = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            h, w = new_h, new_w
        
        # Convert BGR to RGB using numpy (faster than cv2.cvtColor)
        rgb = frame_bgr[:, :, ::-1].copy()
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self._source_pixmap = QPixmap.fromImage(qimg)
        self.shapes = []
        self._update_display_pixmap(fast_mode=fast_mode)
        self.update()

    def _update_display_pixmap(self, fast_mode=False):
        if self._source_pixmap is None:
            return
        target_size = self.size()
        # Use fast transformation during playback, smooth for still frames
        transform_mode = Qt.TransformationMode.FastTransformation if fast_mode else Qt.TransformationMode.SmoothTransformation
        self._display_pixmap = self._source_pixmap.scaled(
            target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, transform_mode
        )
        self.update()

    def _pixmap_geometry(self):
        """Get centered pixmap geometry"""
        if self._display_pixmap is None:
            return None
        x = (self.width() - self._display_pixmap.width()) // 2
        y = (self.height() - self._display_pixmap.height()) // 2
        return QRect(x, y, self._display_pixmap.width(), self._display_pixmap.height())

    def resizeEvent(self, event):
        """Update display on resize"""
        super().resizeEvent(event)
        self._update_display_pixmap()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        if self._display_pixmap:
            geom = self._pixmap_geometry()
            if geom:
                painter.drawPixmap(geom.topLeft(), self._display_pixmap)
                # Draw existing shapes (offset by geometry position)
                for shape in self.shapes:
                    label = shape.get('class')
                    saved = bool(shape.get('saved', False))
                    shape_type = shape.get('type', 'box')
                    
                    # Choose color based on classification
                    if label:
                        color = self.class_colors.get(label, Qt.GlobalColor.green)
                    else:
                        color = Qt.GlobalColor.red
                    
                    # Visual style: solid line for saved, dashed for unsaved
                    pen_style = Qt.PenStyle.SolidLine if saved else Qt.PenStyle.DashLine
                    pen_width = 3 if saved else 2
                    pen = QPen(color, pen_width, pen_style)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(pen)
                    
                    if shape_type == 'polygon' and 'polygon' in shape:
                        # Draw polygon
                        poly = shape['polygon']
                        qpoly = QPolygonF()
                        for px, py in poly:
                            # Scale polygon points to display size
                            disp_x = px * self._display_pixmap.width()
                            disp_y = py * self._display_pixmap.height()
                            qpoly.append(QPointF(disp_x + geom.left(), disp_y + geom.top()))
                        painter.drawPolygon(qpoly)
                        # Fill with semi-transparent color
                        # Get RGB values properly from QColor
                        if isinstance(color, QColor):
                            r, g, b = color.red(), color.green(), color.blue()
                        else:
                            # Handle Qt.GlobalColor
                            qc = QColor(color)
                            r, g, b = qc.red(), qc.green(), qc.blue()
                        brush = QBrush(QColor(r, g, b, 30))
                        painter.setBrush(brush)
                        painter.drawPolygon(qpoly)
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        # Get bounding rect for label positioning
                        draw_rect = qpoly.boundingRect().toRect()
                    else:
                        # Draw rectangle
                        r = shape['rect']
                        draw_rect = QRect(r)
                        draw_rect.translate(geom.topLeft())
                        painter.drawRect(draw_rect)
                    
                    # Draw label text with small offset and background for readability
                    if label:
                        painter.setFont(painter.font())
                        label_text = str(label)
                        text_rect = painter.fontMetrics().boundingRect(label_text)
                        text_pos = draw_rect.topLeft() + QPoint(3, 15)
                        # Semi-transparent background for text
                        bg_rect = text_rect.translated(text_pos.x() - 2, text_pos.y() - 10)
                        painter.fillRect(bg_rect, QColor(0, 0, 0, 150))
                        painter.setPen(QPen(Qt.GlobalColor.white))
                        painter.drawText(text_pos, label_text)
                # Draw preview while drawing box (also needs offset)
                if self._drawing:
                    pen = QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    current_rect = QRect(self._start, self._end).normalized()
                    current_rect.translate(geom.topLeft())
                    painter.drawRect(current_rect)
                
                # Draw manual polygon in progress
                if self._drawing_polygon and len(self._polygon_points) > 0:
                    pen = QPen(Qt.GlobalColor.cyan, 2, Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    # Draw lines between points
                    for i in range(len(self._polygon_points) - 1):
                        p1 = self._polygon_points[i] + geom.topLeft()
                        p2 = self._polygon_points[i + 1] + geom.topLeft()
                        painter.drawLine(p1, p2)
                    # Draw line from last point to first to show closure preview
                    if len(self._polygon_points) >= 2:
                        p_last = self._polygon_points[-1] + geom.topLeft()
                        p_first = self._polygon_points[0] + geom.topLeft()
                        pen.setStyle(Qt.PenStyle.DashLine)
                        painter.setPen(pen)
                        painter.drawLine(p_last, p_first)
                    # Draw points as circles
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(Qt.GlobalColor.cyan))
                    for pt in self._polygon_points:
                        painter.drawEllipse(pt + geom.topLeft(), 4, 4)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            super().paintEvent(event)

    def mousePressEvent(self, event):
        # Handle mouse press for annotation
        if self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            if geom and geom.contains(event.position().toPoint()):
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.annotation_mode == 'manual_polygon':
                        # Manual polygon: add point on each click (MUST come before other modes)
                        rel_pos = event.position().toPoint() - geom.topLeft()
                        self._polygon_points.append(rel_pos)
                        self._drawing_polygon = True
                        # Grab keyboard focus so ESC key works
                        self.setFocus()
                        self.update()
                        return  # Exit early to prevent triggering other modes
                    elif self.annotation_mode == 'polygon':
                        # AI Segmentation mode: single click triggers SAM
                        self._handle_sam_click(event.position().toPoint(), geom)
                    else:
                        # Box mode: start rectangle drawing
                        self._drawing = True
                        self._start = event.position().toPoint() - geom.topLeft()
                        self._end = self._start
                        self.update()
                elif event.button() == Qt.MouseButton.RightButton and self.annotation_mode == 'manual_polygon':
                    # Right click completes polygon
                    if len(self._polygon_points) >= 3:
                        self._finish_manual_polygon()
                    else:
                        QMessageBox.warning(self, "Polygon", "Need at least 3 points to create a polygon")
                    self._polygon_points = []
                    self._drawing_polygon = False
                    self.update()
        super().mousePressEvent(event)
    
    def keyPressEvent(self, event):
        """Handle keyboard events"""
        if event.key() == Qt.Key.Key_Escape:
            # ESC key clears current polygon drawing
            if self._drawing_polygon and len(self._polygon_points) > 0:
                self._polygon_points = []
                self._drawing_polygon = False
                self.update()
                event.accept()
                return
        super().keyPressEvent(event)
    
    def _finish_manual_polygon(self):
        """Convert manual polygon points to normalized coordinates and add to shapes."""
        if self._display_pixmap is None or len(self._polygon_points) < 3:
            return
        
        w = self._display_pixmap.width()
        h = self._display_pixmap.height()
        
        # Convert QPoint list to normalized coordinates
        normalized_polygon = []
        for pt in self._polygon_points:
            norm_x = pt.x() / w
            norm_y = pt.y() / h
            normalized_polygon.append((norm_x, norm_y))
        
        # Add to shapes
        self.shapes.append({
            'polygon': normalized_polygon,
            'class': None,
            'saved': False,
            'type': 'polygon'
        })
        
        if self.on_shapes_changed:
            self.on_shapes_changed(self.shapes)
        
        logger.info(f"Manual polygon created with {len(normalized_polygon)} points")
    
    def _handle_sam_click(self, click_pos, geom):
        """Handle SAM segmentation click"""
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            
            # Check if frame is available
            if self.current_frame_bgr is None:
                logger.error("current_frame_bgr is None - cannot segment")
                QMessageBox.warning(
                    self,
                    "No Frame",
                    "No frame loaded for segmentation. Please load a frame first."
                )
                return
            
            # Get click position relative to pixmap
            rel_pos = click_pos - geom.topLeft()
            x = rel_pos.x()
            y = rel_pos.y()
            
            logger.info(f"SAM click at ({x}, {y})")
            
            # Show wait cursor
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            
            # Check if SAM segmenter is available
            if not _sam_available or SAMSegmenter is None:
                logger.warning("AI Segmentation not available")
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "AI Segmentation Unavailable",
                    "AI Segmentation requires torch/CUDA.\n\n"
                    "Available modes:\n"
                    "  • Rectangle: Draw boxes manually\n"
                    "  • Manual Polygon: Draw polygons point-by-point"
                )
                return
            
            # Run SAM segmentation
            try:
                sam = SAMSegmenter()
                sam.set_frame(self.current_frame_bgr)
            except Exception as e:
                logger.error(f"Failed to create SAMSegmenter: {e}")
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "Segmentation Error",
                    f"Failed to initialize segmentation:\n{str(e)}"
                )
                return
            
            logger.info(f"Running segmentation...")
            
            # Get polygon in normalized coordinates [0-1]
            polygon = sam.segment_at_point(
                x, y,
                self._display_pixmap.width(),
                self._display_pixmap.height()
            )
            
            # Restore cursor
            QApplication.restoreOverrideCursor()
            
            if polygon and len(polygon) >= 3:
                logger.info(f"SAM generated polygon with {len(polygon)} points")
                # Add polygon shape
                self.shapes.append({
                    'polygon': polygon,
                    'class': None,
                    'saved': False,
                    'type': 'polygon'
                })
                if self.on_shapes_changed:
                    self.on_shapes_changed(self.shapes)
                self.update()
            else:
                logger.warning("SAM failed to generate valid polygon")
                QMessageBox.warning(
                    self,
                    "Segmentation Failed",
                    "Could not segment object at click point.\n\n"
                    "Tips:\n"
                    "• Click directly on the CENTER of the object\n"
                    "• Ensure object has clear contrast with background\n"
                    "• Try clicking on a different part of the object\n"
                    "• For small objects, use Rectangle mode instead"
                )
        except Exception as e:
            from PyQt6.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()
            logger.error(f"SAM segmentation error: {e}", exc_info=True)

    def mouseMoveEvent(self, event):
        if self._drawing and self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            if geom:
                pos = event.position().toPoint() - geom.topLeft()
                pos = QPoint(
                    max(0, min(pos.x(), self._display_pixmap.width())),
                    max(0, min(pos.y(), self._display_pixmap.height()))
                )
                self._end = pos
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drawing and self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            if geom:
                pos = event.position().toPoint() - geom.topLeft()
                pos = QPoint(
                    max(0, min(pos.x(), self._display_pixmap.width())),
                    max(0, min(pos.y(), self._display_pixmap.height()))
                )
                self._end = pos
                rect = QRect(self._start, self._end).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    # New shapes are unsaved and unlabeled by default
                    self.shapes.append({'rect': rect, 'class': None, 'saved': False, 'type': 'box'})
                    if self.on_shapes_changed:
                        self.on_shapes_changed(self.shapes)
            self._drawing = False
            self.update()
        super().mouseReleaseEvent(event)

    def clear_rectangles(self):
        """Clear all shapes"""
        self.shapes = []
        self.update()
        if self.on_shapes_changed:
            self.on_shapes_changed(self.shapes)

    def assign_class_to_unlabeled(self, cls_name):
        """Assign class to all unlabeled shapes"""
        any_changed = False
        for shape in self.shapes:
            if not shape.get('class'):
                shape['class'] = cls_name
                shape['saved'] = False
                any_changed = True
        if any_changed:
            self.update()
            if self.on_shapes_changed:
                self.on_shapes_changed(self.shapes)

    def delete_shape(self, index):
        if 0 <= index < len(self.shapes):
            self.shapes.pop(index)
            self.update()
            if self.on_shapes_changed:
                self.on_shapes_changed(self.shapes)

    def get_yolo_annotations(self, class_id_map):
        """Convert shapes to YOLO format"""
        if not self._display_pixmap:
            return []
        w = self._display_pixmap.width()
        h = self._display_pixmap.height()
        items = []
        for shape in self.shapes:
            cls = shape.get('class')
            if cls not in class_id_map:
                continue
            class_id = class_id_map[cls]
            if shape.get('type') == 'box' and 'rect' in shape:
                r = shape['rect']
                x_center = (r.x() + r.width() / 2.0) / w
                y_center = (r.y() + r.height() / 2.0) / h
                nw = r.width() / w
                nh = r.height() / h
                items.append(('box', cls, x_center, y_center, nw, nh))
        return items

    def get_normalized_shapes(self):
        """Return list of items: either ('box', class, x, y, w, h) or ('polygon', class, [points])."""
        if self._display_pixmap is None:
            return []
        w = self._display_pixmap.width()
        h = self._display_pixmap.height()
        items = []
        for shape in self.shapes:
            cls = shape.get('class')
            shape_type = shape.get('type', 'box')
            if shape_type == 'polygon' and 'polygon' in shape:
                # Polygon is already normalized in [0-1]
                items.append(('polygon', cls, shape['polygon']))
            else:
                r = shape['rect']
                x = r.x(); y = r.y(); bw = r.width(); bh = r.height()
                x_center = (x + bw / 2) / float(w)
                y_center = (y + bh / 2) / float(h)
                nw = bw / float(w)
                nh = bh / float(h)
                items.append(('box', cls, x_center, y_center, nw, nh))
        return items


class AnnotationTab(QWidget):
    """Integrated annotation tab for studio main window"""
    
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self.cap = None
        self.frame_index = 0
        self.total_frames = 0
        self.fps = 0.0
        self.current_frame = None
        self.playing = False
        self.media_mode = 'none'
        self.video_path = None
        self.image_paths = []
        self.class_labels = {}
        self.leaf_classes = []
        self.class_id_map = {}
        self.class_colors = {}
        self.recent_classes = []
        self.media_base = ""
        
        self._play_timer = QTimer()
        self._play_timer.timeout.connect(self._play_next_frame)
        self._play_timer.setTimerType(Qt.TimerType.PreciseTimer)  # More accurate timing
        self._updating_slider = False
        self._last_frame_time = 0  # Track time for frame skipping
        
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top: Media import buttons
        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: #333; padding: 10px;")
        top_bar_layout = QHBoxLayout(top_bar)
        
        import_video_btn = QPushButton("📹 Import Video")
        import_video_btn.clicked.connect(self.import_video)
        top_bar_layout.addWidget(import_video_btn)
        
        import_images_btn = QPushButton("🖼 Import Images")
        import_images_btn.clicked.connect(self.import_images)
        top_bar_layout.addWidget(import_images_btn)
        
        self.media_status_label = QLabel("No media loaded")
        self.media_status_label.setStyleSheet("color: #ccc; margin-left: 20px;")
        top_bar_layout.addWidget(self.media_status_label)
        
        top_bar_layout.addStretch(1)
        main_layout.addWidget(top_bar)
        
        # Main content: Canvas + Controls
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        
        # Left: Video container with overlay controls
        self.canvas = AnnotationCanvas()
        self.canvas.on_shapes_changed = lambda _: self.refresh_box_list()
        self.canvas.setMouseTracking(True)

        self._blur_effect = None

        self.video_container = QWidget()
        self.video_container.setObjectName("video_container")
        self.video_container.setMouseTracking(True)

        # Use simple vertical layout - canvas on top, controls at bottom
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
        
        # Canvas fills most of the space
        video_layout.addWidget(self.canvas, 1)

        # Bottom controls bar (all controls together)
        self.bottom_bar = QWidget()
        self.bottom_bar.setObjectName("bottom_bar")
        self.bottom_bar.setStyleSheet(
            "QWidget#bottom_bar { background-color: rgba(0,0,0,140); "
            "border: 1px solid rgba(255,255,255,80); border-radius: 8px; margin: 8px; }"
        )
        bottom_row = QHBoxLayout(self.bottom_bar)
        bottom_row.setContentsMargins(10, 6, 10, 6)
        bottom_row.setSpacing(8)

        self.play_btn = QPushButton("▶")
        self.play_btn.setEnabled(False)
        self.play_btn.setFixedSize(80, 30)
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setStyleSheet(
            "QPushButton { background-color: rgba(0,0,0,120); color: white; "
            "border: 1px solid rgba(255,255,255,140); border-radius: 4px; font-size: 14px; }"
            "QPushButton:hover { background-color: rgba(60,60,60,160); }"
        )
        bottom_row.addWidget(self.play_btn)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setEnabled(False)
        self.prev_btn.setFixedSize(80, 30)
        self.prev_btn.clicked.connect(self.prev_frame)
        self.prev_btn.setStyleSheet(
            "QPushButton { background-color: rgba(0,0,0,120); color: white; "
            "border: 1px solid rgba(255,255,255,140); border-radius: 4px; }"
        )
        bottom_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setEnabled(False)
        self.next_btn.setFixedSize(80, 30)
        self.next_btn.clicked.connect(self.next_frame)
        self.next_btn.setStyleSheet(
            "QPushButton { background-color: rgba(0,0,0,120); color: white; "
            "border: 1px solid rgba(255,255,255,140); border-radius: 4px; }"
        )
        bottom_row.addWidget(self.next_btn)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self.on_slider_changed)
        self.frame_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: rgba(255,255,255,80); height: 6px; }"
            "QSlider::handle:horizontal { width: 12px; margin: -3px 0; background: white; border-radius: 6px; }"
        )
        bottom_row.addWidget(self.frame_slider, 1)
        
        # Time labels in bottom bar
        time_layout = QHBoxLayout()
        self.time_left_label = QLabel("00:00")
        self.time_left_label.setStyleSheet("color: rgba(255,255,255,220); font-size: 10px;")
        time_layout.addWidget(self.time_left_label)
        time_layout.addStretch(1)
        self.time_right_label = QLabel("00:00")
        self.time_right_label.setStyleSheet("color: rgba(255,255,255,220); font-size: 10px;")
        time_layout.addWidget(self.time_right_label)
        bottom_row.addLayout(time_layout)

        video_layout.addWidget(self.bottom_bar)
        
        splitter.addWidget(self.video_container)
        
        # Right: Controls (fixed width, scrollable)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)
        
        # Annotation mode
        mode_group = QGroupBox("Mode")
        mode_layout = QVBoxLayout()
        self.box_mode_radio = QRadioButton("📦 Rectangle")
        self.box_mode_radio.setChecked(True)
        self.box_mode_radio.toggled.connect(lambda checked: self.set_annotation_mode('box') if checked else None)
        self.seg_mode_radio = QRadioButton("🤖 AI Segment")
        self.seg_mode_radio.toggled.connect(lambda checked: self.set_annotation_mode('polygon') if checked else None)
        self.manual_poly_radio = QRadioButton("✏️ Manual Polygon")
        self.manual_poly_radio.toggled.connect(lambda checked: self.set_annotation_mode('manual_polygon') if checked else None)
        mode_layout.addWidget(self.box_mode_radio)
        mode_layout.addWidget(self.seg_mode_radio)
        mode_layout.addWidget(self.manual_poly_radio)
        mode_group.setLayout(mode_layout)
        right_layout.addWidget(mode_group)
        
        # Class selection
        right_layout.addWidget(QLabel("Class Label"))
        self.class_combo = QComboBox()
        self.class_combo.setEditable(True)
        self.class_combo.setInsertPolicy(QComboBox.NoInsert)
        right_layout.addWidget(self.class_combo)
        
        # Assign button
        assign_btn = QPushButton("Assign Class to Boxes")
        assign_btn.clicked.connect(self.assign_class)
        right_layout.addWidget(assign_btn)
        
        # Box list
        right_layout.addWidget(QLabel("Boxes in Frame"))
        self.box_list = QListWidget()
        self.box_list.setMaximumHeight(110)
        right_layout.addWidget(self.box_list)
        
        # Actions
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.canvas.clear_rectangles)
        right_layout.addWidget(clear_btn)

        clear_selected_btn = QPushButton("Clear Selected")
        clear_selected_btn.clicked.connect(self.delete_selected_box)
        right_layout.addWidget(clear_selected_btn)
        
        save_frame_btn = QPushButton("💾 Save Frame")
        save_frame_btn.clicked.connect(self.save_current_frame)
        right_layout.addWidget(save_frame_btn)

        export_labels_btn = QPushButton("Export labels.txt")
        export_labels_btn.clicked.connect(self.export_labels)
        right_layout.addWidget(export_labels_btn)
        
        save_all_btn = QPushButton("💾 Save All")
        save_all_btn.clicked.connect(self.save_all)
        right_layout.addWidget(save_all_btn)
        
        right_layout.addStretch(1)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidget(right_panel)
        right_scroll.setMinimumWidth(300)
        right_scroll.setMaximumWidth(360)
        right_scroll.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 90)
        splitter.setStretchFactor(1, 10)
        splitter.setSizes([1200, 320])
        
        main_layout.addWidget(splitter, 1)
        
        self.setLayout(main_layout)
        self._load_classes()

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure bottom bar is visible
        if hasattr(self, "bottom_bar"):
            self.bottom_bar.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Canvas auto-resizes via layout

    def _set_overlay_visible(self, hovering: bool):
        # Controls always visible now - no hover behavior
        pass

    def eventFilter(self, obj, event):
        # No event filtering needed - layout handles everything
        return super().eventFilter(obj, event)

    def set_annotation_mode(self, mode):
        """Set annotation mode: 'box', 'segment', or 'polygon'"""
        self.canvas.annotation_mode = mode
        logger.info(f"Annotation mode set to: {mode}")

    def _build_class_colors(self, names):
        """Build deterministic, vibrant color palette for each class."""
        palette = [
            "#FF1744",  # Bright Red
            "#2196F3",  # Bright Blue
            "#4CAF50",  # Bright Green
            "#FFC107",  # Bright Amber
            "#9C27B0",  # Bright Purple
            "#00BCD4",  # Bright Cyan
            "#FF5722",  # Deep Orange
            "#E91E63",  # Hot Pink
            "#8BC34A",  # Light Green
            "#009688",  # Teal
            "#3F51B5",  # Indigo
            "#FF6F00",  # Dark Orange
            "#00E676",  # Bright Green 2
            "#D32F2F",  # Dark Red
            "#1565C0",  # Dark Blue
            "#0097A7",  # Dark Cyan
        ]
        colors = {}
        for name in (names or []):
            hash_val = hash(name) & 0x7FFFFFFF
            color_idx = hash_val % len(palette)
            colors[name] = QColor(palette[color_idx])
        colors["Unclassified"] = QColor("#9E9E9E")
        colors["Unclassified Fire/Smoke"] = QColor("#9E9E9E")
        return colors

    def _refresh_class_combo_items(self):
        all_classes = list(self.leaf_classes or self.class_labels)
        ordered = []
        for r in self.recent_classes:
            if r in all_classes and r not in ordered:
                ordered.append(r)
        for c in all_classes:
            if c not in ordered:
                ordered.append(c)
        self.class_combo.clear()
        for class_name in ordered:
            color = self.class_colors.get(class_name, Qt.GlobalColor.gray)
            icon_pixmap = QPixmap(16, 16)
            icon_pixmap.fill(color)
            self.class_combo.addItem(QIcon(icon_pixmap), class_name)

    def _rebuild_class_map(self, class_list):
        self.leaf_classes = list(class_list or [])
        self.class_id_map = {cls: idx for idx, cls in enumerate(self.leaf_classes)}

        # Build class colors and set on canvas
        self.class_colors = self._build_class_colors(self.leaf_classes)
        self.canvas.class_colors = self.class_colors

        # Configure class combo with completer and color indicators
        completer = QCompleter(self.leaf_classes)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.class_combo.setCompleter(completer)
        if self.class_combo.lineEdit():
            self.class_combo.lineEdit().setPlaceholderText("Type to search classes…")
            self.class_combo.setCurrentIndex(-1)

        self._refresh_class_combo_items()

    def _load_labels_list(self, labels_path: Path):
        try:
            lines = labels_path.read_text(encoding="utf-8").splitlines()
            return [line.strip() for line in lines if line.strip()]
        except Exception:
            return []

    def _apply_media_class_mapping(self):
        if not self.media_base:
            return
        out_dir = Path(get_data_path(f"annotations/{self.media_base}"))
        labels_path = out_dir / "labels.txt"
        if not labels_path.exists():
            return

        labels = self._load_labels_list(labels_path)
        if not labels:
            return

        if labels != self.leaf_classes:
            QMessageBox.warning(
                self,
                "Class Mapping",
                "labels.txt does not match the current class list.\n"
                "Using labels.txt for this media to prevent ID drift."
            )
        self._rebuild_class_map(labels)

    def _write_labels_files(self, out_dir: Path, class_list):
        labels_path = out_dir / "labels.txt"
        labels_path.write_text("\n".join(class_list) + "\n", encoding="utf-8")

        meta = {
            "class_count": len(class_list),
            "class_hash": get_classes_hash(class_list),
            "classes": list(class_list),
        }
        meta_path = out_dir / "labels_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    def _load_classes(self):
        """Load class configuration"""
        try:
            category = self._get_active_analytics_category()
            classes_dict = load_master_classes()
            class_list = get_leaf_classes_for_category(category, classes_dict)
            if not class_list:
                class_list = get_leaf_classes(classes_dict)
            self._rebuild_class_map(class_list)
        except Exception:
            self._rebuild_class_map(["Fire", "Smoke", "Person"])

    def _get_active_analytics_category(self):
        """Read active analytics category from shared stream_config.json."""
        stream_cfg_path = Path(__file__).resolve().parent.parent / "stream_config.json"
        try:
            with stream_cfg_path.open("r", encoding="utf-8") as fh:
                stream_cfg = json.load(fh) or {}
            category = str(stream_cfg.get("active_analytics_category", "fire") or "fire").strip().lower()
        except Exception:
            category = "fire"
        if category not in {"fire", "ppe"}:
            category = "fire"
        return category

    def import_video(self):
        """Import video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Videos (*.mp4 *.avi *.mov)"
        )
        if file_path:
            self.load_video(file_path)

    def import_images(self):
        """Import image files"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if files:
            self.load_images(files)

    def load_video(self, path):
        """Load video file"""
        try:
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(path)
            if not self.cap.isOpened():
                QMessageBox.critical(self, "Error", "Failed to open video.")
                return
            
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 25.0)
            self.frame_index = 0
            self.media_mode = 'video'
            self.video_path = path
            self.media_base = Path(path).stem

            self._apply_media_class_mapping()
            
            self.frame_slider.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.prev_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.frame_slider.setMaximum(max(0, self.total_frames - 1))
            self.frame_slider.setValue(0)
            
            # Set timer to slightly faster than target FPS to allow for processing time
            # The frame skip logic will handle maintaining proper timing
            timer_fps = min(self.fps * 1.2, 60)  # Max 60 FPS timer
            self._play_timer.setInterval(int(1000.0 / timer_fps))
            
            self.read_frame()
            self.media_status_label.setText(f"Video: {Path(path).name} ({self.total_frames} frames)")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load video: {e}")

    def load_images(self, paths):
        """Load image sequence"""
        try:
            self.image_paths = sorted(paths)
            self.cap = None
            self.media_mode = 'images'
            self.fps = 0.0
            self.frame_index = 0
            self.total_frames = len(self.image_paths)
            self.media_base = Path(self.image_paths[0]).parent.name

            self._apply_media_class_mapping()
            
            self.frame_slider.setEnabled(True)
            self.prev_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.frame_slider.setMaximum(max(0, self.total_frames - 1))
            self.frame_slider.setValue(0)
            
            self.read_frame()
            self.media_status_label.setText(f"Images: {len(paths)} files")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load images: {e}")

    def read_frame(self, seek=True, fast_mode=False):
        """Read and display current frame
        
        Args:
            seek: If True, seek to frame_index. If False, read next frame sequentially (faster for playback)
            fast_mode: If True, use faster rendering (for playback)
        """
        try:
            if self.media_mode == 'video' and self.cap:
                if seek:
                    # Seeking is slow but necessary for random access (slider, prev/next buttons)
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
                # Read the frame (either after seek or sequentially)
                ret, frame = self.cap.read()
                if ret:
                    self.current_frame = frame
                    self.canvas.set_frame(frame, fast_mode=fast_mode)
            elif self.media_mode == 'images' and self.image_paths:
                if 0 <= self.frame_index < len(self.image_paths):
                    frame = cv2.imread(self.image_paths[self.frame_index])
                    if frame is not None:
                        self.current_frame = frame
                        self.canvas.set_frame(frame, fast_mode=fast_mode)
        except Exception as e:
            print(f"Error reading frame: {e}")

    def toggle_play(self):
        """Toggle playback"""
        if self.playing:
            self._play_timer.stop()
            self.play_btn.setText("▶")
            self.playing = False
            # Update slider to exact position when stopping
            self.frame_slider.setValue(self.frame_index)
        else:
            # Ensure video is at correct position before starting playback
            if self.media_mode == 'video' and self.cap:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
            import time
            self._last_frame_time = time.time()
            self._play_timer.start()
            self.play_btn.setText("⏸")
            self.playing = True
        self._set_overlay_visible(False)

    def _play_next_frame(self):
        """Play next frame (optimized for sequential playback with frame skip)"""
        if self.frame_index < self.total_frames - 1:
            # Calculate how many frames to advance based on elapsed time
            import time
            current_time = time.time()
            elapsed = current_time - self._last_frame_time
            target_frame_time = 1.0 / self.fps if self.fps > 0 else 0.033
            
            # If we're falling behind, skip frames to maintain timing
            frames_to_advance = max(1, int(elapsed / target_frame_time))
            frames_to_advance = min(frames_to_advance, 3)  # Don't skip more than 3 frames
            
            self.frame_index = min(self.frame_index + frames_to_advance, self.total_frames - 1)
            self._last_frame_time = current_time
            
            # Update slider only every 5 frames to reduce UI overhead
            if self.frame_index % 5 == 0:
                self.frame_slider.setValue(self.frame_index)
            # Don't seek during playback - read sequentially with fast rendering
            self.read_frame(seek=False, fast_mode=True)
        else:
            self.toggle_play()

    def prev_frame(self):
        """Go to previous frame"""
        if self.frame_index > 0:
            self.frame_index -= 1
            self.frame_slider.setValue(self.frame_index)
            self.read_frame()

    def next_frame(self):
        """Go to next frame"""
        if self.frame_index < self.total_frames - 1:
            self.frame_index += 1
            self.frame_slider.setValue(self.frame_index)
            self.read_frame()

    def on_slider_changed(self, value):
        """Handle slider change"""
        if not self._updating_slider:
            self.frame_index = value
            self.read_frame()

    def assign_class(self):
        """Assign selected class to unlabeled boxes"""
        cls = self.class_combo.currentText().strip()
        if not cls:
            QMessageBox.warning(self, "Class", "Please select a class first.")
            return
        self.canvas.assign_class_to_unlabeled(cls)
        if cls:
            if cls in self.recent_classes:
                self.recent_classes.remove(cls)
            self.recent_classes.insert(0, cls)
            self.recent_classes = self.recent_classes[:5]
            self._refresh_class_combo_items()
        self.refresh_box_list()

    def refresh_box_list(self):
        """Refresh box list"""
        self.box_list.clear()
        for i, shape in enumerate(self.canvas.shapes):
            cls = shape.get('class', 'Unlabeled')
            self.box_list.addItem(f"Box {i+1}: {cls}")

    def delete_selected_box(self):
        """Delete currently selected box from list/canvas."""
        if not hasattr(self, 'box_list') or self.box_list is None:
            return
        sel = self.box_list.currentRow()
        if sel >= 0:
            self.canvas.delete_shape(sel)
            self.refresh_box_list()

    def export_labels(self):
        """Export labels.txt in the annotations folder."""
        try:
            base = self.media_base or os.path.splitext(os.path.basename(self.video_path or "media"))[0]
            out_dir = get_data_path(os.path.join("annotations", base))
            os.makedirs(out_dir, exist_ok=True)
            labels_path = os.path.join(out_dir, "labels.txt")
            with open(labels_path, 'w') as f:
                for name in (self.leaf_classes or []):
                    f.write(name + "\n")
            QMessageBox.information(self, "Exported", f"labels.txt written to:\n{labels_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"labels.txt export failed: {e}")

    def save_current_frame(self):
        """Save current frame annotations"""
        try:
            if not self.current_frame is not None:
                QMessageBox.warning(self, "Save", "No frame loaded.")
                return
            
            items = self.canvas.get_normalized_shapes()
            labeled = [item for item in items if item[1]]
            if not labeled:
                QMessageBox.warning(self, "Save", "No annotations to save.")
                return
            
            # Save annotation file
            out_dir = Path(get_data_path(f"annotations/{self.media_base}"))
            out_dir.mkdir(parents=True, exist_ok=True)
            
            frame_name = f"frame_{self.frame_index:06d}"
            txt_path = out_dir / f"{frame_name}.txt"
            img_path = out_dir / f"{frame_name}.jpg"
            
            with open(txt_path, 'w') as f:
                for item in labeled:
                    shape_type = item[0]
                    cls = item[1]
                    cls_id = self.class_id_map.get(cls, 0)
                    if shape_type == 'polygon':
                        polygon = item[2]
                        coords = ' '.join([f"{x:.6f} {y:.6f}" for x, y in polygon])
                        f.write(f"{cls_id} {coords}\n")
                    else:
                        x, y, w, h = item[2], item[3], item[4], item[5]
                        f.write(f"{cls_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
            
            cv2.imwrite(str(img_path), self.current_frame)
            
            # Persist labels.txt and labels_meta.json for class consistency validation
            self._write_labels_files(out_dir, self.leaf_classes)
            
            # Mark shapes as saved
            for shape in self.canvas.shapes:
                if shape.get('class'):
                    shape['saved'] = True
            self.canvas.update()
            
            QMessageBox.information(self, "Success", f"Saved frame {self.frame_index} annotations.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def save_all(self):
        """Save all annotated frames"""
        QMessageBox.information(self, "Save All", "Saving all frames... This may take a moment.")
        self.save_current_frame()
