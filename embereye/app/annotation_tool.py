import os
import cv2
from resource_helper import get_data_path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QMessageBox, QSplitter, QCompleter, QSlider, QStackedLayout,
    QWidget, QListWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor


class ImageCanvas(QLabel):
    """A QLabel-based canvas to display frames and draw rectangles with labels."""
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
        # list of dicts: {'rect': QRect, 'class': Optional[str]}
        self.shapes = []
        self.on_shapes_changed = None  # callback
        # Class → QColor mapping (assigned by dialog)
        self.class_colors = {}

    def set_frame(self, frame_bgr):
        """Set the current frame and reset drawn shapes."""
        h, w, _ = frame_bgr.shape
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
                    r = shape['rect']
                    label = shape.get('class')
                    saved = bool(shape.get('saved', False))
                    # Offset rect to widget coordinates
                    draw_rect = QRect(r)
                    draw_rect.translate(geom.topLeft())
                    
                    # Choose color based on classification
                    # Priority: class-assigned color > labeled green > unlabeled red
                    if label:
                        # Use class color from palette (consistent for same class)
                        color = self.class_colors.get(label, Qt.green)
                    else:
                        # Unlabeled boxes are red
                        color = Qt.red
                    
                    # Visual style: solid line for saved, dashed for unsaved
                    pen_style = Qt.SolidLine if saved else Qt.DashLine
                    pen_width = 3 if saved else 2
                    pen = QPen(color, pen_width, pen_style)
                    pen.setCapStyle(Qt.RoundCap)
                    pen.setJoinStyle(Qt.RoundJoin)
                    painter.setPen(pen)
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
                # Draw preview while drawing (also needs offset)
                if self._drawing:
                    pen = QPen(Qt.yellow, 2, Qt.DashLine)
                    painter.setPen(pen)
                    current_rect = QRect(self._start, self._end).normalized()
                    current_rect.translate(geom.topLeft())
                    painter.drawRect(current_rect)
        else:
            super().paintEvent(event)

    def mousePressEvent(self, event):
        print(f"[DEBUG] Canvas mousePressEvent: button={event.button()}, pos={event.pos()}")
        if event.button() == Qt.LeftButton and self._display_pixmap is not None:
            geom = self._pixmap_geometry()
            print(f"[DEBUG] Pixmap geom: {geom}")
            if geom and geom.contains(event.pos()):
                print(f"[DEBUG] Position is in geom, starting draw")
                self._drawing = True
                # Store absolute coordinates (will be stored in pixmap space)
                self._start = event.pos() - geom.topLeft()
                self._end = self._start
                print(f"[DEBUG] Start: {self._start}, End: {self._end}")
                self.update()
            else:
                print(f"[DEBUG] Position NOT in geom or no pixmap")
        super().mousePressEvent(event)

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
                    self.shapes.append({'rect': rect, 'class': None, 'saved': False})
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
        """Return list of (class, x,y,w,h) normalized to [0,1]."""
        if self._display_pixmap is None:
            return []
        w = self._display_pixmap.width()
        h = self._display_pixmap.height()
        items = []
        for shape in self.shapes:
            r = shape['rect']
            cls = shape.get('class')
            x = r.x(); y = r.y(); bw = r.width(); bh = r.height()
            x_center = (x + bw / 2) / float(w)
            y_center = (y + bh / 2) / float(h)
            nw = bw / float(w)
            nh = bh / float(h)
            items.append((cls, x_center, y_center, nw, nh))
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
    """Simple video annotation tool supporting bounding boxes and YOLO format saving."""
    def __init__(self, parent=None, video_path=None, class_labels=None, leaf_classes=None):
        super().__init__(parent)
        self.setWindowTitle("Annotation Tool")
        # Increase dialog size to accommodate taller canvas
        self.resize(1200, 900)
        self.video_path = video_path
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
        self.canvas.on_shapes_changed = lambda _: self.refresh_box_list()
        self.canvas.setMouseTracking(True)
        # Assign class color palette (consistent across all rendering)
        self.class_colors = self._build_class_colors(self.leaf_classes or self.class_labels)
        self.canvas.class_colors = self.class_colors

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

        # Right: video selection and annotation controls
        right = QVBoxLayout()
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setMaximumWidth(400)

        right.addWidget(QLabel("Video File"))
        self.video_label = QLabel(self.video_path or "No video selected")
        self.video_label.setWordWrap(True)
        self.video_label.setStyleSheet("color: #aaa; font-size: 11px;")
        right.addWidget(self.video_label)
        
        select_btn = QPushButton("Select Video…")
        select_btn.setStyleSheet("padding: 8px; font-size: 12px;")
        select_btn.clicked.connect(self.select_video)
        right.addWidget(select_btn)

        right.addSpacing(10)
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

        add_box_btn = QPushButton("Assign Class to New Boxes")
        add_box_btn.setStyleSheet("padding: 8px; font-size: 11px;")
        add_box_btn.clicked.connect(self.add_box_for_class)
        right.addWidget(add_box_btn)

        # Boxes list and actions
        right.addWidget(QLabel("Boxes in Frame"))
        self.box_list = QListWidget()
        self.box_list.setMaximumHeight(120)
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
        splitter.addWidget(right_widget)
        
        # Set stretch factors: 70% for video (left), 30% for controls (right)
        splitter.setStretchFactor(0, 70)
        splitter.setStretchFactor(1, 30)

        # Bottom: Controls and Close
        bottom = QHBoxLayout()
        
        # Control bar at bottom
        control_bar = QWidget()
        control_bar.setStyleSheet("background-color: rgba(0,0,0,220); color: white;")
        control_bar.setFixedHeight(60)
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(12, 6, 12, 6)
        control_layout.setSpacing(12)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setStyleSheet("color: white; font-size: 12px; font-weight: bold; padding: 6px 12px; border: 1px solid white; border-radius: 4px;")
        self.play_btn.setFixedWidth(80)
        self.play_btn.setFixedHeight(40)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setStyleSheet("color: white; font-size: 12px; font-weight: bold; padding: 6px 12px; border: 1px solid white; border-radius: 4px;")
        self.prev_btn.setFixedWidth(80)
        self.prev_btn.setFixedHeight(40)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self.prev_frame)
        control_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setStyleSheet("color: white; font-size: 12px; font-weight: bold; padding: 6px 12px; border: 1px solid white; border-radius: 4px;")
        self.next_btn.setFixedWidth(80)
        self.next_btn.setFixedHeight(40)
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.next_frame)
        control_layout.addWidget(self.next_btn)

        self.time_left_label = QLabel("00:00")
        self.time_left_label.setStyleSheet("color: white; font-size: 11px; font-weight: bold; min-width: 50px;")
        control_layout.addWidget(self.time_left_label)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.setTickPosition(QSlider.TicksBelow)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setStyleSheet("QSlider::groove:horizontal { background: rgba(255,255,255,100); height: 6px; margin: 0px; } QSlider::handle:horizontal { width: 12px; margin: -3px 0; background: white; border-radius: 6px; }")
        self.frame_slider.valueChanged.connect(self.on_slider_value_changed)
        self.frame_slider.sliderMoved.connect(self.on_slider_moved)
        control_layout.addWidget(self.frame_slider, 1)

        self.time_right_label = QLabel("00:00")
        self.time_right_label.setStyleSheet("color: white; font-size: 11px; font-weight: bold; min-width: 50px;")
        control_layout.addWidget(self.time_right_label)
        
        bottom.addWidget(control_bar)
        bottom.addStretch(1)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        main.addLayout(bottom)
        
        # Auto-load video if provided in constructor
        if self.video_path:
            print(f"[DEBUG] Auto-loading video from constructor: {self.video_path}")
            self.load_video(self.video_path)
            self.video_label.setText(self.video_path)

        # Track mouse for overlay show/hide (not needed, controls are at bottom)
        self.canvas.installEventFilter(self)
        video_container.installEventFilter(self)

    def select_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Videos (*.mp4 *.avi *.mov)")
        if path:
            self.video_label.setText(path)
            self.load_video(path)

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
            # Show where annotations will be stored for this video
            base = os.path.splitext(os.path.basename(self.video_path or "video"))[0]
            out_dir = get_data_path(os.path.join("annotations", base))
            self.video_label.setToolTip(f"Annotations folder: {out_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Video load failed: {e}")

    def read_frame(self):
        if not self.cap:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
        ok, frame = self.cap.read()
        if not ok:
            QMessageBox.warning(self, "End", "No more frames.")
            return

        self.current_frame = frame
        self.canvas.set_frame(frame)

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
        labeled = [(cls, x, y, w, h) for (cls, x, y, w, h) in items if cls]
        if not labeled:
            QMessageBox.information(self, "No Boxes", "No boxes to save for this frame.")
            return
        # build output dir
        base = os.path.splitext(os.path.basename(self.video_path or "video"))[0]
        out_dir = get_data_path(os.path.join("annotations", base))
        os.makedirs(out_dir, exist_ok=True)
        
        # Save frame image
        frame_name = f"frame_{self.frame_index:05d}.jpg"
        frame_path = os.path.join(out_dir, frame_name)
        cv2.imwrite(frame_path, self.current_frame)
        
        # Save annotations
        out_file = os.path.join(out_dir, f"frame_{self.frame_index:05d}.txt")
        try:
            with open(out_file, "w") as f:
                for cls, x, y, w, h in labeled:
                    class_id = self.class_id_map.get(cls, 0)
                    # YOLO format: class x_center y_center width height
                    f.write(f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
            # Mark current labeled shapes as saved
            for shape in self.canvas.shapes:
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
            r = shape['rect']
            cls = shape.get('class') or '(unlabeled)'
            state = "saved" if shape.get('saved') else "unsaved"
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
            base = os.path.splitext(os.path.basename(self.video_path or "video"))[0]
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
