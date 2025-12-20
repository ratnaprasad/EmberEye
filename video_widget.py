from video_worker import VideoWorker
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer, QObject, QMutexLocker
from PyQt5.QtGui import QColor
from PyQt5.QtCore import QSettings
import os, json, tempfile

class SensorHandler(QObject):
    data_received = pyqtSignal(dict)  # Signal to emit sensor data  

class VideoWidget(QWidget):
    maximize_requested = pyqtSignal()
    minimize_requested = pyqtSignal()
    thermal_data_received = pyqtSignal(list)  # Signal for thermal matrix from background thread

    def __init__(self, rtsp_url, name, loc_id, parent=None):
        super().__init__(parent)
        self.rtsp_url = rtsp_url
        self.name = name
        self.loc_id = loc_id
        self.last_error_message = None
        self.cached_thermal_overlay = None  # Store last thermal overlay QPixmap
        self.hot_cells = []  # List of (row, col) tuples for detected hot cells
        self.hot_cells_history = []  # Persistent history of hot cells
        self.hot_cells_decay_time = 5.0  # Seconds to keep hot cells visible
        self.hot_cells_timestamps = {}  # Timestamp for each hot cell
        
        # Thermal grid configuration
        self.thermal_grid_enabled = True
        self.thermal_grid_rows = 24
        self.thermal_grid_cols = 32
        self.thermal_grid_color = QColor(255, 0, 0, 180)  # Semi-transparent red
        self.thermal_grid_border = QColor(255, 255, 0, 200)  # Yellow border
        # Numbers-only Thermal Grid View toggle (user opt-in per stream)
        self.thermal_grid_view_enabled = False  # loaded below
        self._last_thermal_matrix = None
        # Cached numeric grid rendering (pixmap + signature)
        self._cached_grid_pixmap = None
        self._cached_grid_matrix_sig = None
        # Cache for thermal grid overlay to prevent flickering
        self._cached_thermal_overlay = None
        self._last_overlay_matrix_hash = None
        self._last_thermal_update_time = 0
        self._thermal_update_interval = 0.2  # Minimum 200ms between thermal updates
        
        # Alarm state and frame freeze
        self.alarm_active = False
        self.frozen_frame = None
        self.freeze_on_alarm = True
        self.current_temp = 22.5
        
        # Fusion data display
        self.fusion_data = None
        self.show_fusion_overlay = True

        # Expand to fill grid cell
        self.setMinimumSize(160, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label = QLabel(self)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border: none;
            }
        """)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.sensor_handler = SensorHandler()
        self.sensor_handler.data_received.connect(self.update_sensor_display)

        self.create_controls()
        # Load persisted preference before wiring signals
        try:
            self.thermal_grid_view_enabled = self._load_grid_pref()
        except Exception:
            self.thermal_grid_view_enabled = False
        self.maximize_requested.connect(self.handle_maximize_state)
        self.minimize_requested.connect(self.handle_minimize_state)
        self.thermal_data_received.connect(self._handle_thermal_data)
        self.init_worker()
        self.top_left_controls.raise_()
        self.bottom_right_status.raise_()
        # Reflect loaded state in button without triggering handler twice
        if hasattr(self, 'thermal_view_btn'):
            self.thermal_view_btn.blockSignals(True)
            self.thermal_view_btn.setChecked(self.thermal_grid_view_enabled)
            self.thermal_view_btn.blockSignals(False)
            if self.thermal_grid_view_enabled and self._last_thermal_matrix is not None:
                try:
                    self._render_temperature_grid(self._last_thermal_matrix)
                except Exception:
                    pass

    def set_thermal_overlay(self, matrix):
        """Thread-safe method to set thermal overlay from any thread."""
        self.thermal_data_received.emit(matrix)

    def _handle_thermal_data(self, matrix):
        """Receive thermal data and render either overlay or grid view based on toggle."""
        try:
            import time
            current_time = time.time()
            
            # Throttle thermal updates to reduce flickering
            if current_time - self._last_thermal_update_time < self._thermal_update_interval:
                # Store the data but don't trigger redraw yet
                self._last_thermal_matrix = matrix
                return
            
            self._last_thermal_update_time = current_time
            self._last_thermal_matrix = matrix
            
            # Update cache signature / invalidate cached grid if matrix changed
            try:
                import numpy as np
                arr = np.array(matrix)
                sig = hash(arr.tobytes())
                if sig != self._cached_grid_matrix_sig:
                    self._cached_grid_matrix_sig = sig
                    # Invalidate overlay cache when data changes
                    self._cached_thermal_overlay = None
                    self._last_overlay_matrix_hash = None
                
                # Extract and display target temperature (max value in grid)
                target_temp = arr.max()
                self.set_temperature(target_temp)
            except Exception as e:
                print(f"Temperature extraction error: {e}")
            
            # Grid view mode: full temperature grid is handled in update_frame
            # Non-grid view mode: hot cells and fusion overlay are handled in update_frame via _redraw_with_grid
            # No need to call any rendering here, just store the data
        except Exception as e:
            print(f"Thermal handler error: {e}")

    def set_hot_cells(self, hot_cells):
        """Set the list of hot cells detected by sensor fusion."""
        import time
        current_time = time.time()
        
        # Update hot cells with timestamps
        if hot_cells:
            self.hot_cells = hot_cells
            for cell in hot_cells:
                self.hot_cells_timestamps[cell] = current_time
        else:
            self.hot_cells = []
        
        # Clean up expired hot cells from history
        expired_cells = [cell for cell, ts in self.hot_cells_timestamps.items() 
                        if current_time - ts > self.hot_cells_decay_time]
        for cell in expired_cells:
            del self.hot_cells_timestamps[cell]
        
        # Get all active hot cells (current + recent history)
        self.hot_cells_history = list(self.hot_cells_timestamps.keys())
        
        # Trigger redraw if we have a current frame and grid view is OFF
        if not self.thermal_grid_view_enabled and self.video_label.pixmap() and not self.video_label.pixmap().isNull():
            self._redraw_with_grid()

    def _redraw_with_grid(self):
        """Redraw current frame with thermal grid overlay on hot cells and fusion data."""
        try:
            base_pixmap = self.video_label.pixmap()
            if not base_pixmap or base_pixmap.isNull():
                return
            
            from PyQt5.QtGui import QPainter, QPen, QFont, QBrush
            from PyQt5.QtCore import Qt, QRect
            import time
            
            # Create a copy to draw on
            result = base_pixmap.copy()
            painter = QPainter(result)
            
            # Draw thermal grid if enabled and hot cells exist
            if self.thermal_grid_enabled and self.hot_cells_history:
                # Calculate cell dimensions
                widget_width = base_pixmap.width()
                widget_height = base_pixmap.height()
                cell_width = widget_width / self.thermal_grid_cols
                cell_height = widget_height / self.thermal_grid_rows
                
                current_time = time.time()
                
                # Draw each hot cell with age-based opacity
                for row, col in self.hot_cells_history:
                    if 0 <= row < self.thermal_grid_rows and 0 <= col < self.thermal_grid_cols:
                        x = int(col * cell_width)
                        y = int(row * cell_height)
                        w = int(cell_width)
                        h = int(cell_height)
                        
                        # Calculate opacity based on age
                        age = current_time - self.hot_cells_timestamps.get((row, col), current_time)
                        opacity = max(0.3, 1.0 - (age / self.hot_cells_decay_time))
                        
                        # Adjust color alpha based on age
                        color = QColor(self.thermal_grid_color)
                        color.setAlpha(int(color.alpha() * opacity))
                        
                        # Fill cell with semi-transparent color
                        painter.fillRect(x, y, w, h, color)
                        
                        # Draw border
                        border_color = QColor(self.thermal_grid_border)
                        border_color.setAlpha(int(border_color.alpha() * opacity))
                        pen = QPen(border_color, 2)
                        painter.setPen(pen)
                        painter.drawRect(x, y, w, h)
            
            # Draw fusion data overlay if enabled
            if self.show_fusion_overlay and self.fusion_data:
                self._draw_fusion_overlay(painter, base_pixmap.width(), base_pixmap.height())
            
            painter.end()
            self.video_label.setPixmap(result)
            
        except Exception as e:
            print(f"Grid overlay error: {e}")
            from error_logger import get_error_logger
            get_error_logger().log('ThermalGrid', f'Redraw error: {e}')

    def _apply_thermal_overlay_internal(self, matrix):
        """Process thermal matrix (no longer applies visual overlay in grid view mode)."""
        # This method is kept for compatibility but no longer applies color overlay
        # Hot cells and fusion data are rendered via _redraw_with_grid in update_frame
        pass

    def _value_to_celsius(self, v, vmax):
        """Approximate conversion from raw thermal value to Celsius.
        Heuristic scaling maps raw range to 0..100°C depending on max value.
        """
        try:
            vmax = max(1.0, float(vmax))
            v = float(v)
            if vmax <= 255:
                return (v / 255.0) * 100.0
            if vmax <= 4095:
                return (v / 4095.0) * 100.0
            return (v / 65535.0) * 100.0
        except Exception:
            return float(v)

    def _overlay_thermal_grid_on_frame(self, base_pixmap):
        """Overlay thermal grid with temperature values on top of camera frame."""
        try:
            if self._last_thermal_matrix is None:
                return
            
            import numpy as np
            from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QFont
            from PyQt5.QtCore import Qt, QRect
            import hashlib

            # Check if we need to regenerate the overlay
            matrix_hash = hashlib.md5(str(self._last_thermal_matrix).encode()).hexdigest()
            size_key = f"{base_pixmap.width()}x{base_pixmap.height()}"
            cache_key = f"{matrix_hash}_{size_key}"
            
            # If cached overlay exists and matches, reuse it
            if self._cached_thermal_overlay is not None and self._last_overlay_matrix_hash == cache_key:
                # Just composite the cached overlay on top of the new frame
                result = base_pixmap.copy()
                painter = QPainter(result)
                painter.drawPixmap(0, 0, self._cached_thermal_overlay)
                painter.end()
                self.video_label.setPixmap(result)
                return

            arr = np.array(self._last_thermal_matrix)
            # Try to match configured dimensions
            if arr.ndim != 2 or arr.shape != (self.thermal_grid_rows, self.thermal_grid_cols):
                if arr.size == self.thermal_grid_rows * self.thermal_grid_cols:
                    arr = arr.reshape((self.thermal_grid_rows, self.thermal_grid_cols))
                else:
                    return

            w = base_pixmap.width()
            h = base_pixmap.height()
            
            # Create transparent overlay pixmap
            overlay = QPixmap(w, h)
            overlay.fill(Qt.transparent)
            painter = QPainter(overlay)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)

            cell_w = w / self.thermal_grid_cols
            cell_h = h / self.thermal_grid_rows
            cell_min = min(cell_w, cell_h)

            # Grid pen
            grid_color = QColor(200, 200, 200, 180)  # Semi-transparent white
            pen_width = 2 if cell_min > 30 else 1
            grid_pen = QPen(grid_color)
            grid_pen.setWidth(pen_width)
            painter.setPen(grid_pen)

            vmax = float(arr.max()) if arr.size else 1.0

            # Font size
            base_font_size = int(cell_min * 0.4)
            base_font_size = max(8, min(base_font_size, 24))
            font = QFont("Arial", base_font_size, QFont.Bold)
            painter.setFont(font)

            show_text = cell_min >= 10
            precise = cell_min >= 26

            # Draw grid lines and temperature values
            for r in range(self.thermal_grid_rows):
                for c in range(self.thermal_grid_cols):
                    x = int(c * cell_w)
                    y = int(r * cell_h)
                    rect = QRect(x, y, int(cell_w), int(cell_h))
                    
                    # Draw grid cell border
                    painter.setPen(grid_pen)
                    painter.drawRect(rect)

                    if not show_text:
                        continue

                    val = float(arr[r, c])
                    # Matrix is already in Celsius from thermal_frame_parser
                    temp_c = val

                    # Temperature color with background for readability
                    if temp_c >= 60:
                        tcolor = QColor(255, 70, 70)
                        bg_color = QColor(0, 0, 0, 180)
                    elif temp_c >= 45:
                        tcolor = QColor(255, 150, 60)
                        bg_color = QColor(0, 0, 0, 160)
                    elif temp_c >= 32:
                        tcolor = QColor(255, 250, 120)
                        bg_color = QColor(0, 0, 0, 140)
                    else:
                        tcolor = QColor(200, 220, 255)
                        bg_color = QColor(0, 0, 0, 120)
                    
                    # Draw semi-transparent background for text
                    painter.fillRect(rect.adjusted(2, 2, -2, -2), bg_color)
                    
                    # Draw temperature text
                    painter.setPen(tcolor)
                    txt = f"{temp_c:.2f}"
                    painter.drawText(rect, Qt.AlignCenter, txt)

            painter.end()
            
            # Cache the overlay
            self._cached_thermal_overlay = overlay
            self._last_overlay_matrix_hash = cache_key
            
            # Composite overlay on frame
            result = base_pixmap.copy()
            painter = QPainter(result)
            painter.drawPixmap(0, 0, overlay)
            painter.end()
            self.video_label.setPixmap(result)
        except Exception as e:
            print(f"Thermal grid overlay error: {e}")

    def _render_temperature_grid(self, matrix):
        """Render a 32x24 grid with temperature text in each cell (numbers only) with adaptive scaling."""
        try:
            import numpy as np
            from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QFont
            from PyQt5.QtCore import Qt, QRect

            arr = np.array(matrix)
            # Try to match configured dimensions
            if arr.ndim != 2 or arr.shape != (self.thermal_grid_rows, self.thermal_grid_cols):
                if arr.size == self.thermal_grid_rows * self.thermal_grid_cols:
                    arr = arr.reshape((self.thermal_grid_rows, self.thermal_grid_cols))
                else:
                    return

            w = max(1, self.video_label.width())
            h = max(1, self.video_label.height())
            pix = QPixmap(w, h)
            pix.fill(QColor(0, 0, 0))

            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)

            cell_w = w / self.thermal_grid_cols
            cell_h = h / self.thermal_grid_rows
            cell_min = min(cell_w, cell_h)

            # Adaptive grid pen (thinner on tiny cells, thicker on large)
            grid_color = QColor(60, 60, 60)
            pen_width = 1
            if cell_min > 40:
                pen_width = 2
            if cell_min > 70:
                pen_width = 3
            grid_pen = QPen(grid_color)
            grid_pen.setWidth(pen_width)
            painter.setPen(grid_pen)

            vmax = float(arr.max()) if arr.size else 1.0

            # Adaptive font size range 6..32
            base_font_size = int(cell_min * (0.42 if cell_min < 30 else 0.48))
            base_font_size = max(6, min(base_font_size, 32))
            font = QFont("Arial", base_font_size)
            painter.setFont(font)

            # Decide text format: hide if cell extremely small
            show_text = cell_min >= 6
            precise = cell_min >= 26  # show one decimal if large cells

            for r in range(self.thermal_grid_rows):
                for c in range(self.thermal_grid_cols):
                    x = int(c * cell_w)
                    y = int(r * cell_h)
                    rect = QRect(x, y, int(cell_w), int(cell_h))
                    painter.drawRect(rect)

                    if not show_text:
                        continue

                    val = float(arr[r, c])
                    # Matrix is already in Celsius from thermal_frame_parser
                    temp_c = val

                    # Temperature color bands
                    if temp_c >= 60:
                        tcolor = QColor(255, 70, 70)
                    elif temp_c >= 45:
                        tcolor = QColor(255, 150, 60)
                    elif temp_c >= 32:
                        tcolor = QColor(255, 250, 120)
                    else:
                        tcolor = QColor(200, 220, 255)
                    painter.setPen(tcolor)
                    txt = f"{temp_c:.2f}"
                    painter.drawText(rect, Qt.AlignCenter, txt)

            painter.end()
            self.video_label.setPixmap(pix)
            # Cache pixmap for fast resize reuse
            try:
                self._cached_grid_pixmap = pix
            except Exception:
                pass
        except Exception as e:
            print(f"Thermal grid render error: {e}")

    def create_controls(self):
        """Create and position control widgets with theme-aware styling"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app else False
        
        # Top-left controls (minimize, maximize, reload) - always visible but transparent
        self.top_left_controls = QWidget(self)
        if is_modern:
            self.top_left_controls.setObjectName("video_controls")
            self.top_left_controls.setStyleSheet("""
                QWidget#video_controls {
                    background-color: transparent;
                    border: none;
                }
            """)
        else:
            self.top_left_controls.setStyleSheet("background-color: transparent;")
        
        top_left_layout = QHBoxLayout(self.top_left_controls)
        top_left_layout.setContentsMargins(2, 2, 2, 2)
        top_left_layout.setSpacing(2)

        self.minimize_btn = self.create_control_button("−", "Restore to grid")
        self.maximize_btn = self.create_control_button("⛶", "Maximize view")
        # Thermal Grid View toggle button (numbers-only grid view)
        self.thermal_view_btn = self.create_control_button("⌗", "Toggle thermal grid view")
        self.thermal_view_btn.setCheckable(True)
        self.reload_btn = self.create_control_button("⟳", "Reload stream")
        self.minimize_btn.setVisible(False)
        top_left_layout.addWidget(self.minimize_btn)
        top_left_layout.addWidget(self.maximize_btn)
        # Place new button between maximize and reload
        top_left_layout.addWidget(self.thermal_view_btn)
        top_left_layout.addWidget(self.reload_btn)

        # Bottom-right status (fire alarm, temperature) - always visible but transparent
        self.bottom_right_status = QWidget(self)
        if is_modern:
            self.bottom_right_status.setObjectName("video_status")
            self.bottom_right_status.setStyleSheet("""
                QWidget#video_status {
                    background-color: transparent;
                    border: none;
                }
            """)
        else:
            self.bottom_right_status.setStyleSheet("background-color: transparent;")
        
        bottom_right_layout = QHBoxLayout(self.bottom_right_status)
        bottom_right_layout.setContentsMargins(4, 2, 4, 2)
        bottom_right_layout.setSpacing(4)

        self.fire_alarm_status = QLabel()
        self.fire_alarm_status.setFixedSize(16, 16)
        self.update_fire_alarm(False)
        
        self.temp_label = QLabel("--°C")
        if is_modern:
            self.temp_label.setObjectName("temp_normal")
            self.temp_label.setStyleSheet("""
                QLabel {
                    color: #00bcd4;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 2px 6px;
                    background-color: transparent;
                    border: none;
                }
            """)
        else:
            self.temp_label.setStyleSheet("color: white; font: 10pt;")
        
        # Backward-compat alias to avoid AttributeError from older code paths
        # that may reference a misspelled name 'temo_label'.
        self.temo_label = self.temp_label

        bottom_right_layout.addWidget(self.fire_alarm_status)
        bottom_right_layout.addWidget(self.temp_label)

        # Position controls initially
        self.position_controls()

    def handle_maximize_state(self):
        """Show minimize button when maximized"""
        self.minimize_btn.setVisible(True)
        self.maximize_btn.setEnabled(False)

    def handle_minimize_state(self):
        """Hide minimize button when minimized"""
        self.minimize_btn.setVisible(False)
        self.maximize_btn.setEnabled(True)

    maximize_requested = pyqtSignal()
    minimize_requested = pyqtSignal()

    def create_control_button(self, text, tooltip=""):
        """Create styled control button with theme awareness"""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app else False
        
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        if tooltip:
            btn.setToolTip(tooltip)
        
        if is_modern:
            btn.setObjectName("icon-btn")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    color: rgba(0, 188, 212, 0.9);
                    font-weight: 600;
                    font-size: 16px;
                    padding: 4px;
                }
                QPushButton:hover {
                    background-color: transparent;
                    border: none;
                    color: #00bcd4;
                }
                QPushButton:pressed {
                    background-color: transparent;
                    border: none;
                    color: #00acc1;
                }
                QPushButton:checked {
                    background-color: transparent;
                    border: none;
                    color: #00bcd4;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 150);
                    border: 1px solid gray;
                    border-radius: 15px;
                    color: black;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 200);
                }
            """)
        return btn

    def position_controls(self):
        """Position control widgets correctly with theme-aware margins"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app else False
        
        margin = 10 if is_modern else 25
        
        # Top-left controls
        self.top_left_controls.adjustSize()
        self.top_left_controls.move(margin, margin)

        # Bottom-right status
        self.bottom_right_status.adjustSize()
        br_x = self.width() - self.bottom_right_status.width() - margin
        br_y = self.height() - self.bottom_right_status.height() - margin
        self.bottom_right_status.move(br_x, br_y)

        # Setup opacity effect for top-left controls (fade support)
        try:
            from PyQt5.QtWidgets import QGraphicsOpacityEffect
            self._controls_opacity_effect = QGraphicsOpacityEffect(self.top_left_controls)
            self.top_left_controls.setGraphicsEffect(self._controls_opacity_effect)
            self._controls_opacity_effect.setOpacity(1.0)
        except Exception:
            self._controls_opacity_effect = None

    def resizeEvent(self, event):
        """Handle widget resizing"""
        self.video_label.resize(event.size())
        self.position_controls()
        # Fast path: scale cached numeric grid if available
        if getattr(self, 'thermal_grid_view_enabled', False) and self._last_thermal_matrix is not None:
            try:
                if self._cached_grid_pixmap and not self._cached_grid_pixmap.isNull():
                    scaled = self._cached_grid_pixmap.scaled(self.video_label.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
                    self.video_label.setPixmap(scaled)
                else:
                    self._render_temperature_grid(self._last_thermal_matrix)
            except Exception:
                try:
                    self._render_temperature_grid(self._last_thermal_matrix)
                except Exception:
                    pass
    
    def mouseMoveEvent(self, event):
        """Fade in/out controls on mouse movement for cleaner UI"""
        try:
            if hasattr(self, '_controls_opacity_effect') and self._controls_opacity_effect is not None:
                current = float(self._controls_opacity_effect.opacity())
                new_opacity = 0.8 if current < 0.5 else 1.0
                self._controls_opacity_effect.setOpacity(new_opacity)
        except Exception:
            pass
        super().mouseMoveEvent(event)
        super().resizeEvent(event)

    def _start_worker_timer(self):
        """Slot to safely start the worker's timer from main thread"""
        if self.worker and hasattr(self.worker, 'timer') and self.worker.timer:
            self.worker.timer.start()

    def _stop_worker_timer(self):
        """Slot to safely stop the worker's timer from main thread"""
        if self.worker and hasattr(self.worker, 'timer') and self.worker.timer:
            self.worker.timer.stop()

    def _set_worker_timer_interval(self, interval_ms):
        """Slot to safely set the worker's timer interval from main thread"""
        self.worker.timer.setInterval(interval_ms)

    def init_worker(self):
        """Initialize video streaming components"""
        self.worker = VideoWorker(self.rtsp_url, stream_id=self.loc_id)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        # Connect signals
        self.worker.frame_ready.connect(self.update_frame, Qt.QueuedConnection)
        self.worker.error_occurred.connect(self.handle_error, Qt.QueuedConnection)   
        self.worker.connection_status.connect(self.handle_connection_status)
        self.worker.timer.timeout.connect(self.worker.update_frame, Qt.QueuedConnection)
        self.worker.start_timer_requested.connect(self._start_worker_timer, Qt.QueuedConnection)
        self.worker.stop_timer_requested.connect(self._stop_worker_timer, Qt.QueuedConnection)
        self.worker.set_interval_requested.connect(self._set_worker_timer_interval, Qt.QueuedConnection)

        # Vision score signal
        self.worker.vision_score_ready.connect(self.handle_vision_score, Qt.QueuedConnection)
        # Anomaly frame signal (QImage, score, stream_id)
        if hasattr(self.worker, 'anomaly_frame_ready'):
            self.worker.anomaly_frame_ready.connect(self.handle_anomaly_frame, Qt.QueuedConnection)

        # Connect buttons
        self.reload_btn.clicked.connect(self.reload_stream)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.minimize_btn.clicked.connect(self.toggle_minimize)
        # Thermal grid view toggle
        if hasattr(self, 'thermal_view_btn'):
            try:
                self.thermal_view_btn.toggled.connect(self.toggle_thermal_grid_view)
            except Exception:
                pass

        # Start thread
        self.worker_thread.started.connect(self.worker.start_stream)
        self.worker_thread.start()

    def handle_vision_score(self, score):
        """Forward vision score to main window for fusion."""
        # Find main window and call fusion handler
        mw = self.window()
        if hasattr(mw, 'handle_vision_score_from_widget'):
            mw.handle_vision_score_from_widget(self.loc_id, score)

    def handle_anomaly_frame(self, qimage, score, stream_id, yolo_score=0.0):
        """Forward anomaly frame to main window with metadata."""
        try:
            mw = self.window()
            if hasattr(mw, 'handle_anomaly_frame_from_widget'):
                mw.handle_anomaly_frame_from_widget(self.loc_id, qimage, float(score))
        except Exception as e:
            from error_logger import get_error_logger
            get_error_logger().log(self.name, f"Anomaly forward error: {e}")

    def update_frame(self, pixmap):
        if pixmap is None or pixmap.isNull():
            from error_logger import get_error_logger
            get_error_logger().log(self.name, "Null pixmap received")
            self.last_error_message = "Null pixmap received"
            self.video_label.setText("No video feed\n" + self.rtsp_url)
            self.video_label.setStyleSheet("color: yellow; background-color: black; padding: 5px;")
            return
        try:
            # Freeze frame on alarm if enabled
            if self.alarm_active and self.freeze_on_alarm:
                if self.frozen_frame is None:
                    # Freeze current frame
                    self.frozen_frame = pixmap.copy()
                # Use frozen frame
                pixmap = self.frozen_frame
            else:
                # Clear frozen frame when alarm clears
                self.frozen_frame = None
            
            # Scale video frame to label size
            scaled_video = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Apply thermal grid view overlay (full grid with temperature values)
            if self.thermal_grid_view_enabled and self._last_thermal_matrix is not None:
                self._overlay_thermal_grid_on_frame(scaled_video)
            # Apply hot cells and fusion overlay ONLY when grid view is OFF
            elif not self.thermal_grid_view_enabled and ((self.thermal_grid_enabled and self.hot_cells_history) or (self.show_fusion_overlay and self.fusion_data)):
                # Set base video frame first
                self.video_label.setPixmap(scaled_video)
                self._redraw_with_grid()
            else:
                # Just set the video frame
                self.video_label.setPixmap(scaled_video)
            
            # Analyze frame luminance to adjust control colors for contrast
            self._update_controls_color_for_contrast(scaled_video)
            
            self.last_error_message = None
        except Exception as e:
            self.handle_error(str(e))

    def handle_error(self, message):
        from error_logger import get_error_logger
        get_error_logger().log(self.name, message)
        self.last_error_message = message
        self.video_label.setText(f"ERROR: {message}\n{self.rtsp_url}")
        self.video_label.setStyleSheet("color: red; background-color: black; padding: 5px;")

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        if self.last_error_message:
            menu.addAction("Copy Error Text")
        menu.addAction("Open Error Log")
        action = menu.exec_(event.globalPos())
        if not action:
            return
        if action.text() == "Copy Error Text" and self.last_error_message:
            QApplication.clipboard().setText(self.last_error_message)
        elif action.text() == "Open Error Log":
            mw = self.window()
            if hasattr(mw, 'show_error_log_dialog'):
                mw.show_error_log_dialog()

    def handle_connection_status(self, connected):
        """Update connection status display"""
        if connected:
            self.video_label.setText("")
            self.video_label.setStyleSheet("background-color: black;")
        else:
            self.video_label.setText("Reconnecting...\n" + self.rtsp_url)
            self.video_label.setStyleSheet("""
                color: yellow; 
                background-color: black; 
                padding: 5px;
            """)

    def update_sensor_display(self, data):
        """Update UI with new sensor data"""
        if data['loc_id'] == self.loc_id:
            # Temperature is now updated from thermal matrix in _handle_thermal_data
            # Don't use sensor-provided temperature values
            
            # Update fire alarm if available
            if 'fire_alarm' in data:
                self.update_fire_alarm(data['fire_alarm'])


    def update_fire_alarm(self, alarm_active):
        """Update fire alarm indicator with theme-aware styling"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app else False
        
        self.alarm_active = alarm_active  # Store alarm state
        
        if is_modern:
            if alarm_active:
                self.fire_alarm_status.setObjectName("led_offline")  # Red LED
                self.fire_alarm_status.setStyleSheet("""
                    QLabel {
                        background-color: #ff5252;
                        border-radius: 8px;
                        border: 2px solid #ffffff;
                        min-width: 16px;
                        min-height: 16px;
                        max-width: 16px;
                        max-height: 16px;
                    }
                """)
            else:
                self.fire_alarm_status.setObjectName("led_online")  # Green LED
                self.fire_alarm_status.setStyleSheet("""
                    QLabel {
                        background-color: #69f0ae;
                        border-radius: 8px;
                        border: 2px solid rgba(105, 240, 174, 0.5);
                        min-width: 16px;
                        min-height: 16px;
                        max-width: 16px;
                        max-height: 16px;
                    }
                """)
        else:
            # Classic theme
            color = "red" if alarm_active else "#444"
            self.fire_alarm_status.setStyleSheet(f"""
                background-color: {color};
                border-radius: 10px;
                border: 2px solid {'#fff' if alarm_active else '#666'};
            """)
        
        # Update temperature color to sync with alarm state
        self._update_temp_color()

    def set_fusion_data(self, fusion_data):
        """Set fusion data for overlay display."""
        self.fusion_data = fusion_data
        # Trigger redraw if we have a current frame and grid view is OFF
        if not self.thermal_grid_view_enabled and self.video_label.pixmap() and not self.video_label.pixmap().isNull():
            self._redraw_with_grid()
    
    def _draw_fusion_overlay(self, painter, width, height):
        """Draw fusion data overlay on the frame."""
        try:
            from PyQt5.QtGui import QFont, QColor, QBrush, QPen
            from PyQt5.QtCore import Qt, QRect
            
            # Semi-transparent background for overlay panel
            panel_height = 180
            panel_rect = QRect(10, height - panel_height - 10, 320, panel_height)
            painter.fillRect(panel_rect, QColor(0, 0, 0, 200))
            
            # Border
            painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
            painter.drawRect(panel_rect)
            
            # Title
            font_title = QFont("Arial", 12, QFont.Bold)
            painter.setFont(font_title)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(panel_rect.x() + 10, panel_rect.y() + 20, "Multi-Sensor Fusion")
            
            # Alarm status
            alarm_status = "\ud83d\udd25 ALARM ACTIVE" if self.fusion_data.get('alarm') else "\u2713 Normal"
            alarm_color = QColor(255, 0, 0) if self.fusion_data.get('alarm') else QColor(0, 255, 0)
            font_status = QFont("Arial", 11, QFont.Bold)
            painter.setFont(font_status)
            painter.setPen(alarm_color)
            painter.drawText(panel_rect.x() + 10, panel_rect.y() + 45, alarm_status)
            
            # Confidence/Accuracy
            confidence = self.fusion_data.get('confidence', 0.0)
            accuracy = min(100, int(confidence * 100))
            painter.setPen(QColor(255, 255, 255))
            font_data = QFont("Arial", 10)
            painter.setFont(font_data)
            painter.drawText(panel_rect.x() + 10, panel_rect.y() + 70, f"Prediction Accuracy: {accuracy}%")
            
            # Confidence bar
            bar_width = 280
            bar_height = 15
            bar_x = panel_rect.x() + 20
            bar_y = panel_rect.y() + 75
            
            # Background bar
            painter.fillRect(bar_x, bar_y, bar_width, bar_height, QColor(60, 60, 60))
            
            # Confidence fill
            fill_width = int(bar_width * confidence)
            if confidence < 0.5:
                bar_color = QColor(0, 255, 0)
            elif confidence < 0.7:
                bar_color = QColor(255, 255, 0)
            else:
                bar_color = QColor(255, 0, 0)
            painter.fillRect(bar_x, bar_y, fill_width, bar_height, bar_color)
            
            # Active sources
            sources = self.fusion_data.get('sources', [])
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(panel_rect.x() + 10, panel_rect.y() + 110, "Active Sensors:")
            
            y_offset = 125
            sensor_icons = {
                'thermal': '\ud83c\udf21\ufe0f Thermal',
                'gas': '\ud83d\udca8 Gas',
                'flame': '\ud83d\udd25 Flame',
                'vision': '\ud83d\udc41\ufe0f Vision'
            }
            
            for source in sensor_icons:
                color = QColor(0, 255, 0) if source in sources else QColor(100, 100, 100)
                painter.setPen(color)
                painter.drawText(panel_rect.x() + 20, panel_rect.y() + y_offset, sensor_icons[source])
                y_offset += 18
            
            # Hot cells count
            hot_cells_count = len(self.fusion_data.get('hot_cells', []))
            painter.setPen(QColor(255, 255, 0))
            painter.drawText(panel_rect.x() + 180, panel_rect.y() + 110, f"Hot Cells: {hot_cells_count}")
            
            # Sensor readings - Right column
            right_col_x = panel_rect.x() + 180
            reading_y = panel_rect.y() + 110
            
            # Thermal
            if 'thermal_max' in self.fusion_data:
                # thermal_max is already in Celsius (from sensor_fusion)
                temp_c = float(self.fusion_data['thermal_max'])
                painter.setPen(QColor(255, 200, 0))
                painter.drawText(right_col_x, reading_y, f"Thermal: {temp_c:.1f}°C")
                reading_y += 18
            
            # Gas (ADC1)
            if 'gas_ppm' in self.fusion_data:
                gas_ppm = self.fusion_data['gas_ppm']
                aqi = self.fusion_data.get('adc1_aqi', '')
                painter.setPen(QColor(100, 255, 100))
                if gas_ppm < 1000:
                    painter.drawText(right_col_x, reading_y, f"Gas: {gas_ppm:.0f}PPM")
                else:
                    painter.drawText(right_col_x, reading_y, f"Gas: {gas_ppm/1000:.1f}K")
                if aqi:
                    painter.drawText(right_col_x, reading_y + 12, f"({aqi})")
                    reading_y += 12
                reading_y += 18
            
            # ADC1 Raw
            if 'adc1_raw' in self.fusion_data:
                painter.setPen(QColor(150, 150, 150))
                painter.drawText(right_col_x, reading_y, f"ADC1: {self.fusion_data['adc1_raw']}")
                reading_y += 18
            
            # Smoke (ADC2)
            if 'smoke_level' in self.fusion_data:
                smoke = self.fusion_data['smoke_level']
                smoke_color = QColor(255, 100, 100) if smoke > 50 else QColor(100, 200, 255)
                painter.setPen(smoke_color)
                painter.drawText(right_col_x, reading_y, f"Smoke: {smoke:.0f}%")
                reading_y += 18
            
            # ADC2 Raw
            if 'adc2_raw' in self.fusion_data:
                painter.setPen(QColor(150, 150, 150))
                painter.drawText(right_col_x, reading_y, f"ADC2: {self.fusion_data['adc2_raw']}")
                reading_y += 18
            
            # Flame (MPY30)
            if 'flame_raw' in self.fusion_data:
                flame_active = self.fusion_data['flame_raw'] == 1
                flame_color = QColor(255, 0, 0) if flame_active else QColor(100, 100, 100)
                painter.setPen(flame_color)
                flame_text = "FLAME!" if flame_active else "No Flame"
                painter.drawText(right_col_x, reading_y, flame_text)
                reading_y += 18
            
        except Exception as e:
            print(f"Fusion overlay draw error: {e}")

    def set_temperature(self, temp):
        """Set temperature display with current value and appropriate color."""
        self.current_temp = temp  # Store current temperature
        if not hasattr(self, 'temp_label'):
            return  # Label not created yet, skip update
        print(f"DEBUG: set_temperature called with {temp:.1f}°C")
        self.temp_label.setText(f"Temp: {temp:.1f}°C")
        self._update_temp_color()

    def _update_temp_color(self):
        """Update temperature label color based on alarm state and temperature value."""
        if not hasattr(self, 'current_temp') or not hasattr(self, 'temp_label'):
            return  # Not ready yet
        
        # Color syncs with fusion alarm state for consistency
        if self.alarm_active:
            # Alarm active: red color with bold text
            print(f"DEBUG: Temp color → RED (alarm active), temp={self.current_temp:.1f}°C")
            self.temp_label.setStyleSheet("color: red; font-weight: bold;")
        elif self.current_temp > 35:
            # Elevated temperature but no alarm: orange warning
            print(f"DEBUG: Temp color → ORANGE (elevated), temp={self.current_temp:.1f}°C")
            self.temp_label.setStyleSheet("color: orange;")
        else:
            # Normal temperature: white
            self.temp_label.setStyleSheet("color: white;")

    def toggle_maximize(self):
        """Handle maximize with button state"""
        if not self.maximize_btn.isEnabled():
            return  # Prevent re-entry while maximized

        try:
            if QThread.currentThread() != self.thread():
                self.maximize_requested.emit()
                return
                
            self.maximize_requested.emit()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("Widget already deleted, ignoring operation")

    def toggle_minimize(self):
        """Safe minimize implementation"""
        try:
            if self.isMinimized() or not self.worker_thread.isRunning():
                return

            # Use queued connection
            self.minimize_requested.emit()

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("Widget already deleted, ignoring operation")
            else:
                raise

    def reload_stream(self):
        """Restart video stream"""
        # Use signal to safely stop the timer from main thread
        self.worker.stop_timer_requested.emit()
        # Give time for timer to stop
        QApplication.processEvents()
        # Then stop the stream (releases capture, etc.)
        if self.worker:
            with QMutexLocker(self.worker.mutex):
                if self.worker.cap and self.worker.cap.isOpened():
                    self.worker.cap.release()
            self.worker.connection_status.emit(False)
        self.worker_thread.quit()
        self.worker_thread.wait(1000)
        self.init_worker()

    def toggle_thermal_grid_view(self, enabled):
        """Toggle thermal grid view overlay for this stream."""
        self.thermal_grid_view_enabled = bool(enabled)
        try:
            self._save_grid_pref(self.thermal_grid_view_enabled)
        except Exception:
            pass
        # Clear cache when toggling off
        if not enabled:
            self._cached_thermal_overlay = None
            self._last_overlay_matrix_hash = None
        # Force frame redraw to apply or remove grid overlay
        # The next frame update will handle the overlay automatically

    def stop(self):
        """Safe thread cleanup"""
        try:
            if self.worker_thread.isRunning():
                # Request the worker to stop safely using signal
                try:
                    self.worker.stop_timer_requested.emit()
                    QApplication.processEvents()
                except Exception:
                    pass
                try:
                    if self.worker:
                        with QMutexLocker(self.worker.mutex):
                            if self.worker.cap and self.worker.cap.isOpened():
                                self.worker.cap.release()
                        self.worker.connection_status.emit(False)
                except Exception:
                    pass
                try:
                    self.worker_thread.quit()
                except Exception:
                    pass
                # Use a short wait to avoid freezing the UI
                self.worker_thread.wait(300)
                # If still running, terminate without blocking
                if self.worker_thread.isRunning():
                    try:
                        self.worker_thread.terminate()
                    except Exception:
                        pass
        except Exception as e:
            print(f"Stop error: {str(e)}")

    def deleteLater(self):
        """Safe cleanup with thread management"""
        try:
            # Stop worker first
            if self.worker_thread.isRunning():
                # Use signal-based stop for thread safety
                try:
                    self.worker.stop_timer_requested.emit()
                    QApplication.processEvents()
                except Exception:
                    pass
                try:
                    if self.worker:
                        with QMutexLocker(self.worker.mutex):
                            if self.worker.cap and self.worker.cap.isOpened():
                                self.worker.cap.release()
                        self.worker.connection_status.emit(False)
                except Exception:
                    pass
                self.worker_thread.quit()
                self.worker_thread.wait(2000)
                
            # Then delete
            super().deleteLater()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                pass  # Already deleted
            else:
                raise

    # ------------------------------------------------------------------
    # Persistence helpers for thermal grid view preference
    # ------------------------------------------------------------------
    def _prefs_path(self):
        return os.path.join(os.path.dirname(__file__), 'grid_prefs.json')

    def _load_grid_pref(self):
        """Load persisted grid view toggle (False if missing) using QSettings fallback to JSON."""
        try:
            settings = QSettings("EmberEye", "EmberEyeApp")
            key = f"thermalGrid/{self.loc_id or self.name}"
            val = settings.value(key, False, type=bool)
            return bool(val)
        except Exception:
            # Fallback JSON
            path = self._prefs_path()
            if not os.path.exists(path):
                return False
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                key = str(self.loc_id or self.name)
                return bool(data.get(key, False))
            except Exception:
                return False

    def _save_grid_pref(self, value):
        """Persist grid view toggle using QSettings with JSON fallback."""
        try:
            settings = QSettings("EmberEye", "EmberEyeApp")
            key = f"thermalGrid/{self.loc_id or self.name}"
            settings.setValue(key, bool(value))
            settings.sync()
            return
        except Exception:
            pass
        # Fallback JSON
    
    def _update_controls_color_for_contrast(self, pixmap):
        """Analyze frame luminance and adjust control colors for visibility"""
        try:
            if not pixmap or pixmap.isNull():
                return
            
            # Sample center region of frame for luminance calculation
            sample_rect = pixmap.rect()
            center_x = sample_rect.width() // 2
            center_y = sample_rect.height() // 2
            sample_size = min(50, sample_rect.width() // 4)
            sample_region = pixmap.copy(center_x - sample_size, center_y - sample_size, sample_size * 2, sample_size * 2)
            
            # Convert to image and sample pixels
            image = sample_region.toImage()
            total_luminance = 0
            pixel_count = 0
            
            for y in range(0, image.height(), max(1, image.height() // 10)):
                for x in range(0, image.width(), max(1, image.width() // 10)):
                    color = image.pixelColor(x, y)
                    # Calculate luminance using standard formula
                    luminance = (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255.0
                    total_luminance += luminance
                    pixel_count += 1
            
            avg_luminance = total_luminance / max(1, pixel_count)
            
            # Determine if background is bright or dark
            if avg_luminance > 0.5:
                # Bright background - use dark cyan/blue for better contrast
                btn_color = "rgba(0, 100, 120, 0.9)"  # Dark cyan
                hover_color = "rgba(0, 150, 170, 0.9)"
            else:
                # Dark background - use bright cyan for visibility
                btn_color = "rgba(0, 188, 212, 0.9)"  # Bright cyan
                hover_color = "rgba(100, 220, 255, 0.9)"  # Brighter cyan
            
            # Update all control button styles
            for btn in [self.minimize_btn, self.maximize_btn, self.thermal_view_btn, self.reload_btn]:
                if btn:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: transparent;
                            border: none;
                            color: {btn_color};
                            font-weight: 600;
                            font-size: 16px;
                            padding: 4px;
                        }}
                        QPushButton:hover {{
                            color: {hover_color};
                        }}
                        QPushButton:pressed {{
                            color: #ffffff;
                        }}
                        QPushButton:checked {{
                            color: #ffffff;
                        }}
                    """)
        except Exception as e:
            pass  # Silently ignore errors in contrast detection
