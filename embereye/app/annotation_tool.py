import os
import cv2
import json
from datetime import datetime
from resource_helper import get_data_path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QMessageBox, QSplitter, QCompleter, QSlider, QStackedLayout,
    QWidget, QListWidget, QSizePolicy, QRadioButton, QButtonGroup, QScrollArea
)
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QTimer, QEvent, QPointF
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QPolygonF, QBrush
import logging

logger = logging.getLogger(__name__)

# Try to import SAMSegmenter; gracefully disable if torch unavailable
try:
    from embereye.app.sam_segmentation import SAMSegmenter
    _sam_available = True
except Exception as e:
    logger.warning(f"Failed to import SAMSegmenter: {e}. AI segmentation will be disabled.")
    _sam_available = False
    SAMSegmenter = None


class ImageCanvas(QLabel):
    """A QLabel-based canvas to display frames and draw rectangles/polygons with labels."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        # Increase default canvas height for better visibility
        self.setMinimumSize(QSize(900, 650))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

    def set_frame(self, frame_bgr):
        """Set the current frame and reset drawn shapes."""
        h, w, _ = frame_bgr.shape
        self.current_frame_bgr = frame_bgr.copy()  # Store for SAM
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        self._source_pixmap = QPixmap.fromImage(qimg)
        self.shapes = []
        self._update_display_pixmap()
        self.update()

    def _update_display_pixmap(self):
        if self._source_pixmap is None:
            return
        target_size = self.size()
        self._display_pixmap = self._source_pixmap.scaled(
            target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.update()

    def _pixmap_geometry(self):
        if self._display_pixmap is None:
            return None
        x = (self.width() - self._display_pixmap.width()) // 2
        y = (self.height() - self._display_pixmap.height()) // 2
        return QRect(x, y, self._display_pixmap.width(), self._display_pixmap.height())

    def _clamp_to_pixmap(self, pos, geom):
        x = max(geom.left(), min(pos.x(), geom.right()))
        y = max(geom.top(), min(pos.y(), geom.bottom()))
        return QPoint(x, y)

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
                        color = self.class_colors.get(label, Qt.green)
                    else:
                        color = Qt.red
                    
                    # Visual style: solid line for saved, dashed for unsaved
                    pen_style = Qt.SolidLine if saved else Qt.DashLine
                    pen_width = 3 if saved else 2
                    pen = QPen(color, pen_width, pen_style)
                    pen.setCapStyle(Qt.RoundCap)
                    pen.setJoinStyle(Qt.RoundJoin)
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
                        painter.setBrush(Qt.NoBrush)
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
                        painter.setPen(QPen(Qt.white))
                        painter.drawText(text_pos, label_text)
                # Draw preview while drawing box (also needs offset)
                if self._drawing:
                    pen = QPen(Qt.yellow, 2, Qt.DashLine)
                    painter.setPen(pen)
                    current_rect = QRect(self._start, self._end).normalized()
                    current_rect.translate(geom.topLeft())
                    painter.drawRect(current_rect)
                
                # Draw manual polygon in progress
                if self._drawing_polygon and len(self._polygon_points) > 0:
                    pen = QPen(Qt.cyan, 2, Qt.SolidLine)
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
                        pen.setStyle(Qt.DashLine)
                        painter.setPen(pen)
                        painter.drawLine(p_last, p_first)
                    # Draw points as circles
                    pen.setStyle(Qt.SolidLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(Qt.cyan))
                    for pt in self._polygon_points:
                        painter.drawEllipse(pt + geom.topLeft(), 4, 4)
                    painter.setBrush(Qt.NoBrush)
        else:
            super().paintEvent(event)

    def mousePressEvent(self, event):
        # Handle mouse press for annotation
        if self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            if geom and geom.contains(event.pos()):
                if event.button() == Qt.LeftButton:
                    if self.annotation_mode == 'manual_polygon':
                        # Manual polygon: add point on each click (MUST come before other modes)
                        rel_pos = event.pos() - geom.topLeft()
                        self._polygon_points.append(rel_pos)
                        self._drawing_polygon = True
                        self.update()
                        return  # Exit early to prevent triggering other modes
                    elif self.annotation_mode == 'polygon':
                        # AI Segmentation mode: single click triggers SAM
                        self._handle_sam_click(event.pos(), geom)
                    else:
                        # Box mode: start rectangle drawing
                        self._drawing = True
                        self._start = event.pos() - geom.topLeft()
                        self._end = self._start
                        self.update()
                elif event.button() == Qt.RightButton and self.annotation_mode == 'manual_polygon':
                    # Right click completes polygon
                    if len(self._polygon_points) >= 3:
                        self._finish_manual_polygon()
                    else:
                        QMessageBox.warning(self, "Polygon", "Need at least 3 points to create a polygon")
                    self._polygon_points = []
                    self._drawing_polygon = False
                    self.update()
        super().mousePressEvent(event)
    
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
        """Handle SAM segmentation click."""
        from PyQt5.QtWidgets import QApplication, QMessageBox
        from PyQt5.QtCore import QTimer
        
        try:
            # Check if frame is available
            if self.current_frame_bgr is None:
                logger.error("current_frame_bgr is None - cannot segment")
                QApplication.restoreOverrideCursor()
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
            
            logger.info(f"SAM click at display coords ({x}, {y}), frame shape: {self.current_frame_bgr.shape}, display size: {self._display_pixmap.width()}x{self._display_pixmap.height()}")
            
            # Show wait cursor while processing
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            # Show status message
            if hasattr(self, 'parent') and hasattr(self.parent(), 'statusBar'):
                status_bar = self.parent().statusBar()
                status_bar.showMessage("Segmenting object...", 5000)
            
            QApplication.processEvents()
            
            # Check if SAM segmenter is available
            if not _sam_available or SAMSegmenter is None:
                logger.warning("AI Segmentation not available (torch/CUDA not accessible)")
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "AI Segmentation Unavailable",
                    "AI Segmentation requires torch/CUDA which is not accessible.\n\n"
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
                    f"Failed to initialize segmentation:\n{str(e)}\n\n"
                    "Use Rectangle or Manual Polygon modes."
                )
                return
            
            logger.info(f"Running segmentation at ({x}, {y})...")
            
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
                    "The segmentation tried both FastSAM and GrabCut methods but couldn't\n"
                    "find a clear object boundary at this location.\n\n"
                    "Tips:\n"
                    "• Click directly on the CENTER of the object (not edges/background)\n"
                    "• Ensure object has clear contrast with background\n"
                    "• Avoid clicking on shadows or reflections\n"
                    "• Try clicking on a different part of the object\n"
                    "• For small or complex objects, use Rectangle mode instead"
                )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            logger.error(f"SAM segmentation error: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Segmentation Error",
                f"An error occurred during segmentation:\n{str(e)}\n\n"
                "Try switching to Rectangle mode if this persists."
            )

    def mouseMoveEvent(self, event):
        if self._drawing and self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            if geom:
                pos = event.pos() - geom.topLeft()
                pos = QPoint(
                    max(0, min(pos.x(), self._display_pixmap.width())),
                    max(0, min(pos.y(), self._display_pixmap.height()))
                )
                self._end = pos
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        print(f"[DEBUG] Canvas mouseReleaseEvent: button={event.button()}")
        if event.button() == Qt.LeftButton and self._drawing and self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            if geom:
                pos = event.pos() - geom.topLeft()
                pos = QPoint(
                    max(0, min(pos.x(), self._display_pixmap.width())),
                    max(0, min(pos.y(), self._display_pixmap.height()))
                )
                self._end = pos
                rect = QRect(self._start, self._end).normalized()
                print(f"[DEBUG] Final rect: {rect}, size: {rect.width()}x{rect.height()}")
                if rect.width() > 5 and rect.height() > 5:
                    print(f"[DEBUG] Adding shape: {rect}")
                    # New shapes are unsaved and unlabeled by default
                    self.shapes.append({'rect': rect, 'class': None, 'saved': False, 'type': 'box'})
                    if self.on_shapes_changed:
                        self.on_shapes_changed(self.shapes)
            self._drawing = False
            self.update()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display_pixmap()

    def clear_rectangles(self):
        self.shapes = []
        self.update()
        if self.on_shapes_changed:
            self.on_shapes_changed(self.shapes)

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
                # Box format
                r = shape['rect']
                x = r.x(); y = r.y(); bw = r.width(); bh = r.height()
                x_center = (x + bw / 2) / float(w)
                y_center = (y + bh / 2) / float(h)
                nw = bw / float(w)
                nh = bh / float(h)
                items.append(('box', cls, x_center, y_center, nw, nh))
        return items

    def assign_class_to_unlabeled(self, cls_name):
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


class AnnotationToolDialog(QDialog):
    """Annotation tool supporting videos and image sequences with YOLO saving."""
    def __init__(self, parent=None, video_path=None, image_paths=None, class_labels=None, leaf_classes=None):
        super().__init__(parent)
        self.setWindowTitle("Annotation Tool")
        # Increase dialog size to accommodate taller canvas
        self.resize(1200, 900)
        self.video_path = video_path
        self.image_paths = image_paths or []
        self.class_labels = class_labels or []
        self.leaf_classes = leaf_classes or []
        # Map label text → class id. Prefer leaf classes for YOLO ids.
        self.class_id_map = {}
        if self.leaf_classes:
            for idx, name in enumerate(self.leaf_classes):
                self.class_id_map[name] = idx
        else:
            for idx, name in enumerate(self.class_labels):
                self.class_id_map[name] = idx

        self.cap = None
        self.frame_index = 0
        self.total_frames = 0
        self.fps = 0.0
        self.current_frame = None
        self.playing = False
        self.media_mode = 'video' if (self.video_path and not self.image_paths) else ('images' if self.image_paths else 'none')
        self.media_base = None
        
        # Initialize undo/redo stacks for annotations
        self.undo_stack = []  # List of frame annotation snapshots
        self.redo_stack = []
        self.current_sensitivity = 5  # 1-10 scale
        
        # Initialize timers EARLY (before any video loading)
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._play_tick)
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.timeout.connect(self._apply_pending_scrub)
        self._pending_scrub_index = None
        self._updating_slider = False

        # UI
        main = QVBoxLayout(self)
        
        # TOP: Media controls (moved from bottom)
        top_control_bar = QWidget()
        top_control_bar.setStyleSheet("background-color: rgba(0,0,0,220); color: white;")
        top_control_bar.setFixedHeight(60)
        top_control_layout = QHBoxLayout(top_control_bar)
        top_control_layout.setContentsMargins(12, 6, 12, 6)
        top_control_layout.setSpacing(12)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setStyleSheet("color: white; font-size: 12px; font-weight: bold; padding: 6px 12px; border: 1px solid white; border-radius: 4px;")
        self.play_btn.setFixedWidth(80)
        self.play_btn.setFixedHeight(40)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.toggle_play)
        top_control_layout.addWidget(self.play_btn)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setStyleSheet("color: white; font-size: 12px; font-weight: bold; padding: 6px 12px; border: 1px solid white; border-radius: 4px;")
        self.prev_btn.setFixedWidth(80)
        self.prev_btn.setFixedHeight(40)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self.prev_frame)
        top_control_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setStyleSheet("color: white; font-size: 12px; font-weight: bold; padding: 6px 12px; border: 1px solid white; border-radius: 4px;")
        self.next_btn.setFixedWidth(80)
        self.next_btn.setFixedHeight(40)
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.next_frame)
        top_control_layout.addWidget(self.next_btn)

        self.time_left_label = QLabel("00:00")
        self.time_left_label.setStyleSheet("color: white; font-size: 11px; font-weight: bold; min-width: 50px;")
        top_control_layout.addWidget(self.time_left_label)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.setTickPosition(QSlider.TicksBelow)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setStyleSheet("QSlider::groove:horizontal { background: rgba(255,255,255,100); height: 6px; margin: 0px; } QSlider::handle:horizontal { width: 12px; margin: -3px 0; background: white; border-radius: 6px; }")
        self.frame_slider.valueChanged.connect(self.on_slider_value_changed)
        self.frame_slider.sliderMoved.connect(self.on_slider_moved)
        top_control_layout.addWidget(self.frame_slider, 1)

        self.time_right_label = QLabel("00:00")
        self.time_right_label.setStyleSheet("color: white; font-size: 11px; font-weight: bold; min-width: 50px;")
        top_control_layout.addWidget(self.time_right_label)
        
        main.addWidget(top_control_bar)
        
        splitter = QSplitter()
        splitter.setOrientation(Qt.Horizontal)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        main.addWidget(splitter)

        # Left: canvas + overlay controls
        left = QVBoxLayout()
        left_widget = QWidget()
        left_widget.setLayout(left)
        self.canvas = ImageCanvas()
        self.canvas.on_shapes_changed = lambda _: (self._save_undo_point(), self.refresh_box_list())
        self.canvas.setMouseTracking(True)
        # Assign class color palette (consistent across all rendering)
        self.class_colors = self._build_class_colors(self.leaf_classes or self.class_labels)
        self.canvas.class_colors = self.class_colors
        
        # Initialize SAM segmenter (may be None if torch unavailable)
        self.sam_segmenter = None
        if _sam_available and SAMSegmenter is not None:
            try:
                self.sam_segmenter = SAMSegmenter()
            except Exception as e:
                logger.error(f"Failed to initialize SAMSegmenter: {e}")
                self.sam_segmenter = None

        # Video container with overlay controls (YouTube-style)
        video_container = QWidget()
        video_container.setObjectName("video_container")
        video_container.setMouseTracking(True)
        video_container.setAttribute(Qt.WA_StyledBackground, True)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
        video_layout.addWidget(self.canvas, 1)

        left.addWidget(video_container)
        splitter.addWidget(left_widget)

        # Right: annotation controls (Select Media removed, now scrollable)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setMinimumWidth(300)
        right_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        right_widget = QWidget()
        right_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right = QVBoxLayout()
        right.setSpacing(8)
        right.setContentsMargins(10, 5, 10, 5)
        right_widget.setLayout(right)
        right_scroll.setWidget(right_widget)

        right.addWidget(QLabel("Media"))
        self.video_label = QLabel(self.video_path or (f"{len(self.image_paths)} image(s) selected" if self.image_paths else "No media selected"))
        self.video_label.setWordWrap(True)
        self.video_label.setStyleSheet("color: #aaa; font-size: 11px;")
        right.addWidget(self.video_label)

        right.addSpacing(5)
        right.addWidget(QLabel("Label Class"))
        self.class_combo = QComboBox()
        self.class_combo.setEditable(True)
        self.class_combo.setInsertPolicy(QComboBox.NoInsert)
        # Populate with recently used classes first (initially empty list)
        self.recent_classes = []
        self._refresh_class_combo_items()
        completer = QCompleter(self.leaf_classes or self.class_labels)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.class_combo.setCompleter(completer)
        # Start with empty edit text and a helpful placeholder
        if self.class_combo.lineEdit():
            self.class_combo.lineEdit().setPlaceholderText("Type to search classes…")
            self.class_combo.setCurrentIndex(-1)
        right.addWidget(self.class_combo)
        
        # Annotation mode toggle
        right.addSpacing(10)
        right.addWidget(QLabel("Annotation Mode"))
        mode_layout = QVBoxLayout()
        self.mode_button_group = QButtonGroup()
        self.box_mode_radio = QRadioButton("Rectangle (drag to draw)")
        self.seg_mode_radio = QRadioButton("AI Segmentation (click object)")
        self.manual_poly_radio = QRadioButton("Manual Polygon (click points, right-click to finish)")
        self.box_mode_radio.setChecked(True)
        self.mode_button_group.addButton(self.box_mode_radio, 0)
        self.mode_button_group.addButton(self.seg_mode_radio, 1)
        self.mode_button_group.addButton(self.manual_poly_radio, 2)
        # Connect all radio buttons to mode change handler
        self.box_mode_radio.toggled.connect(self._on_mode_changed)
        self.seg_mode_radio.toggled.connect(self._on_mode_changed)
        self.manual_poly_radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.box_mode_radio)
        mode_layout.addWidget(self.seg_mode_radio)
        mode_layout.addWidget(self.manual_poly_radio)
        right.addLayout(mode_layout)
        
        # Mode instructions
        self.mode_instruction_label = QLabel()
        self.mode_instruction_label.setWordWrap(True)
        self.mode_instruction_label.setStyleSheet("color: #666; font-size: 10px; padding: 5px; background: #f0f0f0; border-radius: 3px;")
        self._update_mode_instructions()
        right.addWidget(self.mode_instruction_label)
        
        # Segmentation sensitivity slider
        right.addWidget(QLabel("Segmentation Sensitivity"))
        sensitivity_layout = QHBoxLayout()
        self.sensitivity_slider = QSlider(Qt.Horizontal)
        self.sensitivity_slider.setMinimum(1)
        self.sensitivity_slider.setMaximum(10)
        self.sensitivity_slider.setValue(5)  # Default middle
        self.sensitivity_slider.setTickPosition(QSlider.TicksBelow)
        self.sensitivity_slider.setTickInterval(1)
        self.sensitivity_label = QLabel("5 (Medium)")
        self.sensitivity_label.setMaximumWidth(80)
        self.sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        sensitivity_layout.addWidget(self.sensitivity_label)
        right.addLayout(sensitivity_layout)
        
        # Undo/Redo buttons
        undo_redo_layout = QHBoxLayout()
        undo_btn = QPushButton("↶ Undo")
        undo_btn.setMaximumWidth(80)
        undo_btn.setToolTip("Ctrl+Z")
        undo_btn.clicked.connect(self.undo)
        redo_btn = QPushButton("↷ Redo")
        redo_btn.setMaximumWidth(80)
        redo_btn.setToolTip("Ctrl+Y")
        redo_btn.clicked.connect(self.redo)
        undo_redo_layout.addWidget(undo_btn)
        undo_redo_layout.addWidget(redo_btn)
        right.addLayout(undo_redo_layout)

        add_box_btn = QPushButton("Assign Class to New Boxes")
        add_box_btn.setStyleSheet("padding: 8px; font-size: 11px;")
        add_box_btn.clicked.connect(self.add_box_for_class)
        right.addWidget(add_box_btn)

        # Boxes list and actions
        right.addWidget(QLabel("Boxes in Frame"))
        self.box_list = QListWidget()
        self.box_list.setMinimumHeight(80)
        self.box_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right.addWidget(self.box_list)

        clear_btn = QPushButton("Clear Boxes")
        clear_btn.setStyleSheet("padding: 6px; font-size: 11px;")
        clear_btn.clicked.connect(self.canvas.clear_rectangles)
        right.addWidget(clear_btn)

        del_btn = QPushButton("Delete Selected Box")
        del_btn.setStyleSheet("padding: 6px; font-size: 11px;")
        del_btn.clicked.connect(self.delete_selected_box)
        right.addWidget(del_btn)

        save_frame_btn = QPushButton("Save Frame Annotations")
        save_frame_btn.setStyleSheet("padding: 8px; font-size: 11px;")
        save_frame_btn.clicked.connect(self.save_current_frame)
        right.addWidget(save_frame_btn)

        exp_labels_btn = QPushButton("Export labels.txt")
        exp_labels_btn.setStyleSheet("padding: 8px; font-size: 11px;")
        exp_labels_btn.clicked.connect(self.export_labels)
        right.addWidget(exp_labels_btn)

        save_all_btn = QPushButton("Save All")
        save_all_btn.setStyleSheet("padding: 8px; font-size: 11px;")
        save_all_btn.clicked.connect(self.save_all)
        right.addWidget(save_all_btn)

        right.addStretch(1)
        splitter.addWidget(right_scroll)
        
        # Set stretch factors: 65% for video (left), 35% for controls (right) - more flexible
        splitter.setStretchFactor(0, 65)
        splitter.setStretchFactor(1, 35)

        # Bottom: Close button only
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        main.addLayout(bottom)
        
        # Auto-load media if provided in constructor
        if self.image_paths:
            print(f"[DEBUG] Auto-loading images from constructor: {len(self.image_paths)} items")
            self.load_images(self.image_paths)
            self.video_label.setText(f"{len(self.image_paths)} image(s) selected")
        elif self.video_path:
            print(f"[DEBUG] Auto-loading video from constructor: {self.video_path}")
            self.load_video(self.video_path)
            self.video_label.setText(self.video_path)

        # Track mouse for overlay show/hide (not needed, controls are at bottom)
        self.canvas.installEventFilter(self)
        video_container.installEventFilter(self)

    def select_media(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media",
            "",
            "Videos (*.mp4 *.avi *.mov);;Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )
        if not files:
            return
        video_exts = {".mp4", ".avi", ".mov"}
        image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
        exts = {os.path.splitext(p.lower())[1] for p in files}
        if len(files) == 1 and (exts & video_exts):
            path = files[0]
            self.video_label.setText(path)
            self.load_video(path)
        elif (exts & image_exts) and not (exts & video_exts):
            files_sorted = sorted(files)
            self.video_label.setText(f"{len(files_sorted)} image(s) selected")
            self.load_images(files_sorted)
        else:
            QMessageBox.warning(self, "Media", "Please select either one video or one/more image files.")

    def _build_class_colors(self, names):
        """Build deterministic, vibrant color palette for each class."""
        # Vibrant, distinct color palette (hex)
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
        from PyQt5.QtGui import QColor
        colors = {}
        # Hash-based color assignment: each class ALWAYS gets unique color (deterministic)
        for name in (names or []):
            # Hash class name to get deterministic index (independent of list order!)
            hash_val = hash(name) & 0x7FFFFFFF  # Ensure positive
            color_idx = hash_val % len(palette)
            hex_color = palette[color_idx]
            colors[name] = QColor(hex_color)
            print(f"[COLOR] Class '{name}' → Palette #{color_idx} ({hex_color})")
        # Special fallbacks
        colors["Unclassified"] = QColor("#9E9E9E")  # Gray
        colors["Unclassified Fire/Smoke"] = QColor("#9E9E9E")  # Gray
        return colors

    def _refresh_class_combo_items(self):
        # Put recent classes on top, then remaining
        all_classes = list(self.leaf_classes or self.class_labels)
        ordered = []
        for r in self.recent_classes:
            if r in all_classes and r not in ordered:
                ordered.append(r)
        for c in all_classes:
            if c not in ordered:
                ordered.append(c)
        self.class_combo.clear()
        # Add items with color indicators
        from PyQt5.QtGui import QPixmap, QIcon
        for class_name in ordered:
            # Get the color for this class
            color = self.class_colors.get(class_name, Qt.gray)
            # Create a small colored square icon
            icon_pixmap = QPixmap(16, 16)
            icon_pixmap.fill(color)
            icon = QIcon(icon_pixmap)
            # Add item with icon
            self.class_combo.addItem(icon, class_name)

    def load_video(self, path):
        try:
            print(f"[DEBUG] load_video called with path: {path}")
            if not path or not os.path.exists(path):
                print(f"[DEBUG] Video path invalid or doesn't exist: {path}")
                QMessageBox.critical(self, "Error", f"Video file not found: {path}")
                return
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(path)
            print(f"[DEBUG] VideoCapture created, isOpened={self.cap.isOpened()}")
            if not self.cap.isOpened():
                QMessageBox.critical(self, "Error", "Failed to open video.")
                return
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
            if fps <= 0.0:
                fps = 25.0
            self.fps = fps
            self.frame_index = 0
            self.media_mode = 'video'
            self.video_path = path
            # base for annotations
            self.media_base = os.path.splitext(os.path.basename(self.video_path or "video"))[0]
            # Configure slider range and ticks
            self._updating_slider = True
            try:
                self.frame_slider.setEnabled(True)
                self.play_btn.setEnabled(True)
                self.prev_btn.setEnabled(True)
                self.next_btn.setEnabled(True)
                self.frame_slider.setMinimum(0)
                self.frame_slider.setMaximum(max(0, self.total_frames - 1))
                tick_every = int(self.fps * 5) if self.fps > 0 else 50
                self.frame_slider.setTickInterval(max(1, tick_every))
                self.frame_slider.setValue(0)
                self.update_time_labels()
            finally:
                self._updating_slider = False
            # configure play timer interval
            interval_ms = int(1000.0 / self.fps) if self.fps > 0 else 40
            self._play_timer.setInterval(max(10, interval_ms))
            self.read_frame()
            # Show where annotations will be stored
            out_dir = get_data_path(os.path.join("annotations", self.media_base))
            self.video_label.setToolTip(f"Annotations folder: {out_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Video load failed: {e}")

    def load_images(self, paths):
        try:
            if not paths:
                QMessageBox.warning(self, "Images", "No images selected.")
                return
            # Validate files exist
            valid = [p for p in paths if os.path.exists(p)]
            if not valid:
                QMessageBox.warning(self, "Images", "Selected images do not exist.")
                return
            self.image_paths = valid
            self.cap = None
            self.media_mode = 'images'
            self.fps = 0.0
            self.frame_index = 0
            self.total_frames = len(self.image_paths)
            # Base from common directory (for multiple) or stem (single)
            try:
                common_dir = os.path.commonpath(self.image_paths)
                if os.path.isfile(common_dir):
                    common_dir = os.path.dirname(common_dir)
            except Exception:
                common_dir = os.path.dirname(self.image_paths[0])
            if len(self.image_paths) == 1:
                self.media_base = os.path.splitext(os.path.basename(self.image_paths[0]))[0]
            else:
                self.media_base = os.path.basename(common_dir) or "images"
            # Configure controls
            self._updating_slider = True
            try:
                self.frame_slider.setEnabled(True)
                self.play_btn.setEnabled(False)  # disable play for images
                self.prev_btn.setEnabled(True)
                self.next_btn.setEnabled(True)
                self.frame_slider.setMinimum(0)
                self.frame_slider.setMaximum(max(0, self.total_frames - 1))
                self.frame_slider.setTickInterval(max(1, 1))
                self.frame_slider.setValue(0)
                self.update_time_labels()
            finally:
                self._updating_slider = False
            # Load first image
            self.read_frame()
            out_dir = get_data_path(os.path.join("annotations", self.media_base))
            self.video_label.setToolTip(f"Annotations folder: {out_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Image load failed: {e}")

    def read_frame(self):
        if self.media_mode == 'images':
            if not (0 <= self.frame_index < self.total_frames):
                QMessageBox.warning(self, "End", "No more frames.")
                return
            img_path = self.image_paths[self.frame_index]
            frame = cv2.imread(img_path)
            if frame is None:
                QMessageBox.warning(self, "Image", f"Failed to load: {img_path}")
                return
            self.current_frame = frame
            self.canvas.set_frame(frame)
            # Load existing annotations for this image
            self._load_existing_annotations()
        else:
            if not self.cap:
                return
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
            ok, frame = self.cap.read()
            if not ok:
                QMessageBox.warning(self, "End", "No more frames.")
                return
            self.current_frame = frame
            self.canvas.set_frame(frame)
            # Load existing annotations for this frame
            self._load_existing_annotations()

        if not self._updating_slider:
            self._updating_slider = True
            try:
                self.frame_slider.blockSignals(True)
                self.frame_slider.setValue(self.frame_index)
                self.frame_slider.blockSignals(False)
            finally:
                self._updating_slider = False
        self.update_time_labels()
        self.refresh_box_list()
        self._show_overlay()

    def _load_existing_annotations(self):
        """Load existing annotations from disk for the current frame."""
        try:
            import os
            from pathlib import Path
            
            base = self.media_base or os.path.splitext(os.path.basename(self.video_path or "media"))[0]
            ann_dir = get_data_path(os.path.join("annotations", base))
            
            # Determine annotation filename
            if self.media_mode == 'images':
                img_name = os.path.basename(self.image_paths[self.frame_index])
                ann_stem = os.path.splitext(img_name)[0]
                ann_file = os.path.join(ann_dir, f"{ann_stem}.txt")
            else:
                ann_file = os.path.join(ann_dir, f"frame_{self.frame_index:05d}.txt")
            
            # Check if annotation file exists
            if not os.path.exists(ann_file):
                logger.info(f"No existing annotations found at {ann_file}")
                return
            
            # Load annotations
            logger.info(f"Loading annotations from {ann_file}")
            with open(ann_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    
                    try:
                        class_id = int(parts[0])
                        
                        # Find class name from id
                        class_name = None
                        for name, cid in self.class_id_map.items():
                            if cid == class_id:
                                class_name = name
                                break
                        
                        if class_name is None:
                            class_name = f"class_{class_id}"
                        
                        # Check if box or polygon format
                        # Box format: class x_center y_center width height (exactly 5 parts)
                        # Polygon format: class x1 y1 x2 y2 x3 y3 ... (odd number of parts, >= 7)
                        if len(parts) == 5:
                            # Box format: class x_center y_center width height
                            x_center = float(parts[1])
                            y_center = float(parts[2])
                            width = float(parts[3])
                            height = float(parts[4])
                            
                            # Convert to pixel coordinates
                            w = self.canvas._display_pixmap.width() if self.canvas._display_pixmap else self.current_frame.shape[1]
                            h = self.canvas._display_pixmap.height() if self.canvas._display_pixmap else self.current_frame.shape[0]
                            
                            x1 = int((x_center - width / 2) * w)
                            y1 = int((y_center - height / 2) * h)
                            x2 = int((x_center + width / 2) * w)
                            y2 = int((y_center + height / 2) * h)
                            
                            rect = QRect(x1, y1, x2 - x1, y2 - y1)
                            self.canvas.shapes.append({
                                'rect': rect,
                                'class': class_name,
                                'saved': True,
                                'type': 'box'
                            })
                            logger.info(f"Loaded box annotation: {class_name}")
                        elif len(parts) >= 7 and (len(parts) - 1) % 2 == 0:
                            # Polygon format: class x1 y1 x2 y2 ... (even number of coordinates)
                            polygon = []
                            for i in range(1, len(parts), 2):
                                if i + 1 < len(parts):
                                    x = float(parts[i])
                                    y = float(parts[i + 1])
                                    polygon.append((x, y))
                            
                            if len(polygon) >= 3:
                                self.canvas.shapes.append({
                                    'polygon': polygon,
                                    'class': class_name,
                                    'saved': True,
                                    'type': 'polygon'
                                })
                                logger.info(f"Loaded polygon annotation: {class_name} with {len(polygon)} points")
                            else:
                                logger.warning(f"Polygon has fewer than 3 points, skipping")
                        else:
                            logger.warning(f"Unknown annotation format with {len(parts)} parts: {line.strip()}")
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse annotation line: {line.strip()} - {e}")
                        continue
            
            logger.info(f"Loaded {len(self.canvas.shapes)} annotations")
        except Exception as e:
            logger.error(f"Failed to load existing annotations: {e}", exc_info=True)

    def prev_frame(self):
        if self.frame_index > 0:
            if not self._maybe_handle_unsaved_unclassified():
                return
            self.frame_index -= 1
            self.read_frame()

    def next_frame(self):
        if self.frame_index + 1 < self.total_frames:
            if not self._maybe_handle_unsaved_unclassified():
                return
            self.frame_index += 1
            self.read_frame()

    def toggle_play(self):
        if not self.cap or self.total_frames <= 0:
            return
        self.playing = not self.playing
        if self.playing:
            self.play_btn.setText("⏸")
            self._play_timer.start()
        else:
            self.play_btn.setText("▶")
            self._play_timer.stop()

    def _play_tick(self):
        if self.frame_index + 1 >= self.total_frames:
            self.playing = False
            self.play_btn.setText("▶")
            self._play_timer.stop()
            return
        self.frame_index += 1
        self.read_frame()

    def on_slider_value_changed(self, val):
        if self._updating_slider:
            return
        # Update time label immediately for responsiveness and queue scrub
        self.update_time_labels(current_index=val)
        self._queue_scrub(val)

    def on_slider_moved(self, val):
        # Coalesce rapid movements
        self._queue_scrub(val)

    def _queue_scrub(self, val):
        self._pending_scrub_index = int(val)
        self._scrub_timer.start(30)

    def _apply_pending_scrub(self):
        if self._pending_scrub_index is None:
            return
        idx = max(0, min(self._pending_scrub_index, max(0, self.total_frames - 1)))
        self.frame_index = idx
        self.read_frame()
        self._pending_scrub_index = None

    def update_time_labels(self, current_index=None):
        idx = self.frame_index if current_index is None else int(current_index)
        if self.media_mode == 'images':
            # Show frame count for images
            self.time_left_label.setText(f"{idx+1:02d}")
            self.time_right_label.setText(f"{self.total_frames:02d}")
        else:
            fps = self.fps if self.fps > 0 else 25.0
            cur_secs = idx / fps
            total_secs = (self.total_frames / fps) if self.total_frames > 0 else 0
            self.time_left_label.setText(self._format_time(cur_secs))
            self.time_right_label.setText(self._format_time(total_secs))

    @staticmethod
    def _format_time(seconds):
        seconds = max(0, float(seconds))
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _show_overlay(self):
        pass

    def _hide_overlay(self):
        pass

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def add_box_for_class(self):
        label_text = self.class_combo.currentText().strip()
        if not label_text:
            QMessageBox.warning(self, "Label", "Select a class label first.")
            return
        # assign selected class to all unlabeled boxes
        self.canvas.assign_class_to_unlabeled(self._get_leaf_from_label(label_text))
        # Track recent classes for quick access
        leaf = self._get_leaf_from_label(label_text)
        if leaf:
            if leaf in self.recent_classes:
                self.recent_classes.remove(leaf)
            self.recent_classes.insert(0, leaf)
            # cap to last 5 recent
            self.recent_classes = self.recent_classes[:5]
            self._refresh_class_combo_items()
        if not any(shape.get('class') for shape in self.canvas.shapes):
            QMessageBox.warning(self, "Box", "Draw boxes on the frame, then assign class.")
            return
        self.refresh_box_list()
    
    def _on_mode_changed(self):
        """Handle annotation mode toggle."""
        # Clear any in-progress drawing state
        if hasattr(self.canvas, '_polygon_points'):
            self.canvas._polygon_points = []
        if hasattr(self.canvas, '_drawing_polygon'):
            self.canvas._drawing_polygon = False
        if hasattr(self.canvas, '_drawing'):
            self.canvas._drawing = False
        
        # Update the annotation mode
        if self.box_mode_radio.isChecked():
            self.canvas.annotation_mode = 'box'
            logger.info("Annotation mode: Rectangle")
        elif self.seg_mode_radio.isChecked():
            self.canvas.annotation_mode = 'polygon'
            logger.info("Annotation mode: AI Segmentation (SAM)")
        else:
            self.canvas.annotation_mode = 'manual_polygon'
            logger.info("Annotation mode: Manual Polygon")
        
        # Force canvas update to clear any visual artifacts
        self.canvas.update()
        self._update_mode_instructions()
    
    def _update_mode_instructions(self):
        """Update instruction text based on current mode."""
        if self.box_mode_radio.isChecked():
            text = "📦 Click and drag to draw a bounding box"
        elif self.seg_mode_radio.isChecked():
            text = "🤖 Click on object to auto-segment (AI-powered)"
        else:
            text = "✏️ Click to add points, Right-click to finish polygon. ESC to cancel."
        
        if hasattr(self, 'mode_instruction_label'):
            self.mode_instruction_label.setText(text)
    
    def _on_sensitivity_changed(self, value):
        """Handle segmentation sensitivity slider change."""
        self.current_sensitivity = value
        # Map 1-10 to descriptive labels
        labels = {
            1: "Very Low", 2: "Low", 3: "Low", 4: "Low-Medium",
            5: "Medium", 6: "Medium", 7: "Medium-High", 8: "High",
            9: "High", 10: "Very High"
        }
        self.sensitivity_label.setText(f"{value} ({labels[value]})")
        logger.info(f"Segmentation sensitivity set to {value}/10 ({labels[value]})")
    
    def _save_undo_point(self):
        """Save current frame annotations to undo stack."""
        if hasattr(self, 'undo_stack') and self.canvas.shapes:
            # Store deep copy of current shapes
            import copy
            self.undo_stack.append(copy.deepcopy(self.canvas.shapes))
            self.redo_stack.clear()  # Clear redo on new action
            # Keep undo history limited to 20 actions
            if len(self.undo_stack) > 20:
                self.undo_stack.pop(0)
    
    def undo(self):
        """Undo last annotation."""
        if self.undo_stack:
            import copy
            # Save current state to redo
            self.redo_stack.append(copy.deepcopy(self.canvas.shapes))
            # Restore previous state
            self.canvas.shapes = self.undo_stack.pop()
            self.canvas.update()
            self.refresh_box_list()
            logger.info("Undo: Restored previous annotation state")
        else:
            QMessageBox.information(self, "Undo", "Nothing to undo")
    
    def redo(self):
        """Redo last undone annotation."""
        if self.redo_stack:
            import copy
            # Save current state to undo
            self.undo_stack.append(copy.deepcopy(self.canvas.shapes))
            # Restore next state
            self.canvas.shapes = self.redo_stack.pop()
            self.canvas.update()
            self.refresh_box_list()
            logger.info("Redo: Restored next annotation state")
        else:
            QMessageBox.information(self, "Redo", "Nothing to redo")

    def _get_leaf_from_label(self, label_text):
        # If hierarchical, leaf is after last arrow
        if "→" in label_text:
            return label_text.split("→")[-1].strip()
        return label_text

    def save_current_frame(self):
        if self.current_frame is None:
            QMessageBox.warning(self, "Frame", "No frame loaded.")
            return
        items = self.canvas.get_normalized_shapes()
        # Filter only labeled items
        labeled = [item for item in items if item[1]]  # item[1] is class
        if not labeled:
            QMessageBox.information(self, "No Boxes", "No annotations to save for this frame.")
            return
        # build output dir
        base = self.media_base or os.path.splitext(os.path.basename(self.video_path or "media"))[0]
        out_dir = get_data_path(os.path.join("annotations", base))
        os.makedirs(out_dir, exist_ok=True)
        
        # Save frame image (copy original for images mode)
        if self.media_mode == 'images':
            src_path = self.image_paths[self.frame_index]
            img_name = os.path.basename(src_path)
            frame_path = os.path.join(out_dir, img_name)
            try:
                import shutil
                if not os.path.exists(frame_path):
                    shutil.copy2(src_path, frame_path)
            except Exception:
                # Fallback to write via cv2
                cv2.imwrite(frame_path, self.current_frame)
            ann_stem = os.path.splitext(img_name)[0]
            out_file = os.path.join(out_dir, f"{ann_stem}.txt")
        else:
            frame_name = f"frame_{self.frame_index:05d}.jpg"
            frame_path = os.path.join(out_dir, frame_name)
            cv2.imwrite(frame_path, self.current_frame)
            out_file = os.path.join(out_dir, f"frame_{self.frame_index:05d}.txt")
        
        # Save annotations (YOLO format supports both boxes and polygons)
        try:
            with open(out_file, "w") as f:
                for item in labeled:
                    shape_type = item[0]
                    cls = item[1]
                    class_id = self.class_id_map.get(cls, 0)
                    
                    if shape_type == 'polygon':
                        # YOLO segmentation format: class x1 y1 x2 y2 x3 y3 ...
                        polygon = item[2]
                        coords = ' '.join([f"{x:.6f} {y:.6f}" for x, y in polygon])
                        f.write(f"{class_id} {coords}\n")
                    else:
                        # YOLO box format: class x_center y_center width height
                        x, y, w, h = item[2], item[3], item[4], item[5]
                        f.write(f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")

            # Also save per-frame metadata snapshot for class consistency across taxonomy changes
            meta = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "media_base": base,
                "frame_index": int(self.frame_index),
                # class_id_map is name->id at annotation time
                "class_mapping": self.class_id_map.copy(),
                # leaf_classes order used by tool (ids derived from this ordering)
                "leaf_classes": list(self.leaf_classes or []),
            }
            if self.media_mode == 'images':
                meta["image_file"] = os.path.basename(self.image_paths[self.frame_index])
                meta_file = os.path.join(out_dir, f"{os.path.splitext(os.path.basename(frame_path))[0]}.json")
            else:
                meta_file = os.path.join(out_dir, f"frame_{self.frame_index:05d}.json")
            with open(meta_file, "w") as mf:
                json.dump(meta, mf, indent=2)
            # Mark all saved shapes with a class as saved
            for shape in self.canvas.shapes:
                # Only mark labeled shapes as saved
                if shape.get('class'):
                    shape['saved'] = True
            self.canvas.update()
            self.refresh_box_list()
            QMessageBox.information(self, "Saved", f"Saved:\n{frame_path}\n{out_file}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")

    def save_all(self):
        # For this minimal tool, saving current frame is supported. Save-all can be extended.
        QMessageBox.information(self, "Info", "Use 'Save Frame Annotations' for each labeled frame.")

    def refresh_box_list(self):
        if not hasattr(self, 'box_list') or self.box_list is None:
            return
        self.box_list.clear()
        for idx, shape in enumerate(self.canvas.shapes):
            cls = shape.get('class') or '(unlabeled)'
            state = "saved" if shape.get('saved') else "unsaved"
            shape_type = shape.get('type', 'box')
            
            if shape_type == 'polygon':
                poly_pts = len(shape.get('polygon', []))
                self.box_list.addItem(f"#{idx+1} [{state}] {cls} - polygon ({poly_pts} pts)")
            else:
                r = shape['rect']
                self.box_list.addItem(f"#{idx+1} [{state}] {cls} - x:{r.x()} y:{r.y()} w:{r.width()} h:{r.height()}")

    def delete_selected_box(self):
        if not hasattr(self, 'box_list') or self.box_list is None:
            return
        sel = self.box_list.currentRow()
        if sel >= 0:
            self.canvas.delete_shape(sel)
            self.refresh_box_list()

    def export_labels(self):
        """Export labels.txt in the annotations folder using provided leaf_classes order."""
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

    def _maybe_handle_unsaved_unclassified(self) -> bool:
        """Check for unclassified or unsaved annotations and prompt user.
        Returns True if navigation can proceed, False to cancel.
        """
        shapes = self.canvas.shapes or []
        has_unclassified = any(not s.get('class') for s in shapes)
        has_unsaved = any(s.get('class') and not s.get('saved') for s in shapes)
        # Nothing to do
        if not has_unclassified and not has_unsaved:
            return True

        # Handle unclassified first
        if has_unclassified:
            reply = QMessageBox.question(
                self,
                "Unclassified Annotations",
                "There are unclassified boxes. Assign them to 'Unclassified'?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Cancel:
                return False
            if reply == QMessageBox.Yes:
                # Ensure class exists in mappings and colors
                if "Unclassified" not in self.class_id_map:
                    self.class_id_map["Unclassified"] = max(self.class_id_map.values() or [0]) + 1
                    # Add to combos and colors
                    if "Unclassified" not in (self.leaf_classes or self.class_labels):
                        self.leaf_classes = list(self.leaf_classes or self.class_labels)
                        self.leaf_classes.append("Unclassified")
                        self.class_colors["Unclassified"] = self.class_colors.get("Unclassified") or self._build_class_colors(["Unclassified"]).get("Unclassified")
                        self._refresh_class_combo_items()
                self.canvas.assign_class_to_unlabeled("Unclassified")
                has_unsaved = True  # these are now unsaved labeled boxes
                self.refresh_box_list()

        # Handle unsaved labeled annotations
        if has_unsaved:
            reply = QMessageBox.question(
                self,
                "Unsaved Annotations",
                "You have unsaved annotations for this frame. Save before leaving?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Cancel:
                return False
            if reply == QMessageBox.Yes:
                self.save_current_frame()
        return True

    # Keyboard shortcuts
    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        
        # Ctrl+Z: Undo
        if key == Qt.Key_Z and (modifiers & Qt.ControlModifier):
            self.undo()
            event.accept()
            return
        
        # Ctrl+Y or Ctrl+Shift+Z: Redo
        if (key == Qt.Key_Y and (modifiers & Qt.ControlModifier)) or \
           (key == Qt.Key_Z and (modifiers & Qt.ControlModifier) and (modifiers & Qt.ShiftModifier)):
            self.redo()
            event.accept()
            return
        
        # ESC cancels polygon drawing
        if key == Qt.Key_Escape and hasattr(self.canvas, '_drawing_polygon') and self.canvas._drawing_polygon:
            self.canvas._polygon_points = []
            self.canvas._drawing_polygon = False
            self.canvas.update()
            event.accept()
            return
        if key in (Qt.Key_J, Qt.Key_Left):
            self.prev_frame()
            event.accept()
            return
        if key in (Qt.Key_K, Qt.Key_Right):
            self.next_frame()
            event.accept()
            return
        if key in (Qt.Key_Space,):
            self.toggle_play()
            event.accept()
            return
        super().keyPressEvent(event)
