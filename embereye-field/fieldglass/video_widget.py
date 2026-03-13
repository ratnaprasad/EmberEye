import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'vigilstream'))

from video_worker import VideoWorker
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy, QApplication
from PyQt5.QtCore import Qt, QRect, QRectF, pyqtSignal, QThread, QTimer, QObject, QMutexLocker, pyqtSlot
from PyQt5.QtGui import QColor, QImage
from debug_config import debug_print, is_debug_enabled
from PyQt5.QtCore import QSettings
from util.fusionbanner import draw_fusion_overlay as render_fusion_overlay
import json
import tempfile

class SensorHandler(QObject):
    data_received = pyqtSignal(dict)  # Signal to emit sensor data  

class VideoWidget(QWidget):
    maximize_requested = pyqtSignal()
    minimize_requested = pyqtSignal()
    thermal_data_received = pyqtSignal(list)  # Signal for thermal matrix from background thread
    alarm_raise_requested = pyqtSignal(str)
    alarm_ack_requested = pyqtSignal(str)

    def __init__(self, rtsp_url, name, loc_id, parent=None, start_worker=True):
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
        self._last_overlay_size = None  # Track last overlay size for invalidation
        self._last_thermal_update_time = 0
        self._thermal_update_interval = 0.2  # Minimum 200ms between thermal updates
        self._thermal_last_packet_ts = 0.0
        self.thermal_render_mode = "fixed_scale_inferno"
        self.thermal_emissivity = 0.95
        self.thermal_auto_window = True
        self.thermal_window_min = 20.0
        self.thermal_window_max = 120.0
        self._prev_thermal_matrix = None
        self._thermal_debug_line = "Thermal: waiting for data"
        
        # Alarm state and frame freeze
        self.alarm_active = False
        self._remote_alarm_active = False
        self._manual_alarm_override = None
        self._alarm_silenced = False
        self.alarm_acknowledged = False
        self.frozen_frame = None
        self.freeze_on_alarm = False
        self.current_temp = 22.5

        # Detection highlight (border) for live grid tiles
        self._detection_highlight_ms = 1200
        self._detection_highlight_timer = QTimer(self)
        self._detection_highlight_timer.setSingleShot(True)
        self._detection_highlight_timer.timeout.connect(self._clear_detection_highlight)
        self._tile_border_px = 4
        self._tile_border_inset = 0
        self._latest_detections = []
        self._latest_detection_ts = 0.0
        self._latest_detection_frame_size = None
        self._detection_overlay_ttl_ms = 1500
        self._last_frame_size_from_pixmap = None
        self._alarm_highlight_color = "#ff5252"
        
        # Fusion data display
        self.fusion_data = None
        self._fusion_last_packet_ts = 0.0
        self._sensor_stale_timeout_s = 3.0
        self.show_fusion_overlay = True
        self.fusion_advanced_view = False
        self.fusion_drawer_collapsed = False
        self._manual_action_state = None  # None | normal | raised
        self._ack_count = 0
        self._action_card_rect = None
        # Legacy view-state flags referenced by overlay layout paths.
        self.is_minimized = False
        self.maximized = False
        self.grid_view = False
        # Display mode: default (camera), thermal (heatmap), grid (numeric)
        self.display_mode = "default"
        self._last_base_pixmap = None  # Keep an unpainted base frame for stable overlay redraws.
        self._rtsp_connected = False
        self.setFocusPolicy(Qt.StrongFocus)

        # Expand to fill grid cell
        self.setMinimumSize(160, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("videoTile")
        self._apply_tile_border()

        self.video_label = QLabel(self)
        self._apply_video_label_style()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.detection_overlay = QLabel(self)
        self.detection_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.detection_overlay.setStyleSheet("QLabel { background-color: transparent; border: none; }")
        self.detection_overlay.hide()

        self.sensor_handler = SensorHandler()
        self.sensor_handler.data_received.connect(self.update_sensor_display)

        self.create_controls()
        # Restore persisted display preference (camera/grid) after controls exist.
        try:
            self.set_display_mode("grid" if self._load_grid_pref() else "default")
        except Exception:
            self.set_display_mode("default")
        self.maximize_requested.connect(self.handle_maximize_state)
        self.minimize_requested.connect(self.handle_minimize_state)
        self.thermal_data_received.connect(self._handle_thermal_data)
        if start_worker:
            self.init_worker()
        else:
            self.worker = None
            self.worker_thread = None
        self.detection_overlay.raise_()
        self.top_left_controls.raise_()
        self.right_overlay_controls.raise_()
        self.fusion_drawer_toggle_btn.raise_()
        self.fusion_alarm_btn.raise_()
        self.bottom_right_status.raise_()
        # Reflect loaded state in overlay buttons without double-triggering
        self._sync_overlay_buttons_from_state(initial=True)
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
            self._thermal_last_packet_ts = current_time
            
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
                corrected = self._apply_emissivity_compensation(arr)
                target_temp = corrected.max()
                self.set_temperature(target_temp)
            except Exception as e:
                print(f"Temperature extraction error: {e}")
            
            # Grid view mode: full temperature grid is handled in update_frame
            # Non-grid view mode: hot cells and fusion overlay are handled in update_frame via _redraw_with_grid
            # No need to call any rendering here, just store the data
        except Exception as e:
            print(f"Thermal handler error: {e}")

    def _sanitize_thermal_mode(self, mode):
        mode_value = str(mode or "").strip().lower()
        allowed = {
            "fixed_scale_inferno",
            "hot_mask_temporal_delta",
            "grayscale_valid_hotspots",
        }
        return mode_value if mode_value in allowed else "fixed_scale_inferno"

    def _apply_emissivity_compensation(self, arr):
        try:
            import numpy as np
            emissivity = max(0.10, min(1.00, float(getattr(self, 'thermal_emissivity', 0.95))))
            ambient_c = 25.0
            corrected = ambient_c + ((np.array(arr, dtype=np.float32) - ambient_c) / emissivity)
            return corrected
        except Exception:
            return arr

    def _compute_thermal_window(self, arr, mode):
        import numpy as np

        scene_min = float(np.percentile(arr, 2))
        scene_max = float(np.percentile(arr, 98))
        scene_span = scene_max - scene_min

        if mode == "fixed_scale_inferno":
            fixed_min = float(getattr(self, 'thermal_window_min', 20.0))
            fixed_max = float(getattr(self, 'thermal_window_max', 120.0))
            if fixed_max <= fixed_min:
                fixed_max = fixed_min + 1.0
            auto_window = bool(getattr(self, 'thermal_auto_window', True))
            if not auto_window:
                return fixed_min, fixed_max, "manual"
            if scene_span < 12.0:
                window_min = scene_min - 1.0
                window_max = scene_max + 1.0
                if window_max - window_min < 4.0:
                    center = float(np.mean(arr))
                    window_min = center - 2.0
                    window_max = center + 2.0
                return window_min, window_max, "adaptive"
            return fixed_min, fixed_max, "fixed"

        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        if max_val <= min_val:
            max_val = min_val + 1.0
        return min_val, max_val, "dynamic"

    def _update_thermal_debug_line(self, arr, mode):
        import numpy as np

        arr_min = float(np.min(arr))
        arr_max = float(np.max(arr))
        arr_span = arr_max - arr_min
        window_min, window_max, window_kind = self._compute_thermal_window(arr, mode)
        mode_short = str(mode).replace("_", "")[:10]
        self._thermal_debug_line = (
            f"Tdbg {mode_short} | val {arr_min:.1f}-{arr_max:.1f}C Δ{arr_span:.1f} | "
            f"win {window_min:.1f}-{window_max:.1f} ({window_kind})"
        )

    def apply_thermal_runtime_config(self, mode=None, emissivity=None, auto_window=None, window_min=None, window_max=None):
        if mode is not None:
            self.thermal_render_mode = self._sanitize_thermal_mode(mode)
        if emissivity is not None:
            try:
                self.thermal_emissivity = max(0.10, min(1.00, float(emissivity)))
            except Exception:
                self.thermal_emissivity = 0.95
        if auto_window is not None:
            self.thermal_auto_window = bool(auto_window)
        if window_min is not None:
            try:
                self.thermal_window_min = float(window_min)
            except Exception:
                self.thermal_window_min = 20.0
        if window_max is not None:
            try:
                self.thermal_window_max = float(window_max)
            except Exception:
                self.thermal_window_max = 120.0
        if self.thermal_window_max <= self.thermal_window_min:
            self.thermal_window_max = self.thermal_window_min + 1.0

        self._cached_thermal_overlay = None
        self._last_overlay_matrix_hash = None
        self._cached_grid_pixmap = None

        try:
            if self._last_thermal_matrix is not None:
                if self.display_mode == "thermal":
                    pix = self._build_thermal_heatmap_pixmap(self._last_thermal_matrix)
                    if pix:
                        self.video_label.setPixmap(pix)
                    self._redraw_with_grid()
                elif self.display_mode == "grid":
                    self._render_temperature_grid(self._last_thermal_matrix)
        except Exception as e:
            print(f"Thermal runtime config apply error: {e}")

    def set_hot_cells(self, hot_cells):
        """Thermal hot-cell grid overlay has been removed (no-op kept for compatibility)."""
        self.hot_cells = []
        self.hot_cells_history = []
        self.hot_cells_timestamps = {}

    def _redraw_with_grid(self):
        """Redraw current frame with fusion data overlay only."""
        try:
            self._expire_stale_sensor_overlay()
            base_pixmap = self._last_base_pixmap or self.video_label.pixmap()
            if not base_pixmap or base_pixmap.isNull():
                return
            
            from PyQt5.QtGui import QPainter, QPen, QFont, QBrush
            from PyQt5.QtCore import Qt, QRect
            from PyQt5.QtGui import QPixmap
            import time
            
            # Create a copy to draw on
            # CRITICAL: Scale result pixmap to CURRENT label size for responsive scaling
            label_width = max(1, self.video_label.width())
            label_height = max(1, self.video_label.height())
            
            # If label size is invalid, use base_pixmap size
            if label_width < 50 or label_height < 50:
                label_width = base_pixmap.width()
                label_height = base_pixmap.height()
            
            # Scale base_pixmap to label size for display
            result = base_pixmap.scaled(label_width, label_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # If scaled result is smaller than label, pad it
            if result.width() < label_width or result.height() < label_height:
                padded = QPixmap(label_width, label_height)
                padded.fill(Qt.black)
                painter_tmp = QPainter(padded)
                x_offset = (label_width - result.width()) // 2
                y_offset = (label_height - result.height()) // 2
                painter_tmp.drawPixmap(x_offset, y_offset, result)
                painter_tmp.end()
                result = padded

            painter = QPainter(result)
            
            # Draw fusion overlay using the rendered tile dimensions so banner
            # stays consistent across stream resolutions and grid changes.
            if self.show_fusion_overlay:
                self._draw_fusion_overlay(painter, result.width(), result.height())
            
            painter.end()
            self.video_label.setPixmap(result)
            
        except Exception as e:
            print(f"Grid overlay error: {e}")
            from error_logger import get_error_logger
            get_error_logger().log('ThermalGrid', f'Redraw error: {e}')

    def _render_no_video_fallback(self):
        """Render thermal/fusion overlay even when RTSP frame is unavailable."""
        try:
            self._expire_stale_sensor_overlay()
            from PyQt5.QtGui import QPixmap

            base = None
            if self.display_mode == "grid" and self._last_thermal_matrix is not None:
                base = self._build_temperature_grid_pixmap(self._last_thermal_matrix)
            elif self.display_mode == "thermal" and self._last_thermal_matrix is not None:
                # Thermal mode may continue with heatmap when camera feed is down.
                base = self._build_thermal_heatmap_pixmap(self._last_thermal_matrix)

            if not base or base.isNull():
                w = max(1, self.video_label.width())
                h = max(1, self.video_label.height())
                base = QPixmap(w, h)
                base.fill(Qt.black)

            self._last_base_pixmap = base
            self.video_label.setPixmap(base)
            if self.show_fusion_overlay:
                self._redraw_with_grid()
        except Exception as e:
            print(f"No-video fallback render error: {e}")

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

    def _compute_grid_temp_bounds(self, arr):
        """Return robust low/high temperature bounds for grid coloring."""
        import numpy as np

        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return 20.0, 40.0

        lo = float(np.percentile(finite, 5.0))
        hi = float(np.percentile(finite, 95.0))

        # If scene is nearly flat, fall back to absolute extrema.
        if (hi - lo) < 2.0:
            lo = float(np.min(finite))
            hi = float(np.max(finite))

        # Keep a non-zero range so normalization remains stable.
        if (hi - lo) < 0.5:
            hi = lo + 0.5

        return lo, hi

    def _temperature_to_grid_colors(self, temp_c, temp_lo, temp_hi, alpha=215):
        """Map a temperature to cell/text colors for numeric grid readability."""
        ratio = 0.0
        if temp_hi > temp_lo:
            ratio = (float(temp_c) - temp_lo) / (temp_hi - temp_lo)
        ratio = max(0.0, min(1.0, ratio))

        # HSV ramp: cool blue -> warm yellow/orange -> hot red.
        hue = int(210 - (210 * ratio))
        bg_color = QColor.fromHsv(hue, 230, 215, alpha)

        # Contrast-aware text color based on luminance.
        luminance = (
            0.2126 * bg_color.red()
            + 0.7152 * bg_color.green()
            + 0.0722 * bg_color.blue()
        )
        text_color = QColor(250, 250, 250) if luminance < 145 else QColor(20, 20, 20)
        return bg_color, text_color

    def _overlay_thermal_grid_on_frame(self, base_pixmap):
        """Overlay thermal grid with temperature values on top of camera frame."""
        try:
            if self._last_thermal_matrix is None:
                return
            
            import numpy as np
            from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QFont
            from PyQt5.QtCore import Qt, QRect
            import hashlib

            # Always regenerate overlay to ensure proper scaling - disable caching for responsiveness
            # This ensures overlays scale correctly when switching between grid and maximized views

            arr = np.array(self._last_thermal_matrix)
            # Try to match configured dimensions
            if arr.ndim != 2 or arr.shape != (self.thermal_grid_rows, self.thermal_grid_cols):
                if arr.size == self.thermal_grid_rows * self.thermal_grid_cols:
                    arr = arr.reshape((self.thermal_grid_rows, self.thermal_grid_cols))
                else:
                    return

            # Use CURRENT label size - this ensures responsive scaling on resize
                w = max(1, self.video_label.width())
                h = max(1, self.video_label.height())
            
                # If dimensions are invalid, use fallback
                if w < 50 or h < 50:
                    w = base_pixmap.width()
                    h = base_pixmap.height()
            
                # Create transparent overlay pixmap
                overlay = QPixmap(w, h)
                overlay.fill(Qt.transparent)
                painter = QPainter(overlay)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # If dimensions are invalid, use fallback
            if w < 50 or h < 50:
                w = base_pixmap.width()
                h = base_pixmap.height()

            # Size/data-aware cache to avoid redraw flicker
            cache_key_size = (w, h)
            cache_key_sig = hashlib.sha1(arr.tobytes()).hexdigest()
            use_cache = (
                self._cached_thermal_overlay is not None
                and self._last_overlay_size == cache_key_size
                and self._cached_grid_matrix_sig == cache_key_sig
            )

            if use_cache:
                overlay = self._cached_thermal_overlay
                painter = None
            else:
                overlay = QPixmap(w, h)
                overlay.fill(Qt.transparent)
                painter = QPainter(overlay)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.TextAntialiasing, True)

            # Compute stable cell rects to avoid rounding drift
            def _iter_cell_rects(cols, rows, width, height):
                # Accumulate rounded edges so the last row/col fills perfectly
                x_edges = [round(i * (width / cols)) for i in range(cols + 1)]
                y_edges = [round(j * (height / rows)) for j in range(rows + 1)]
                for r in range(rows):
                    for c in range(cols):
                        x = x_edges[c]
                        y = y_edges[r]
                        w_ = x_edges[c + 1] - x
                        h_ = y_edges[r + 1] - y
                        yield r, c, x, y, w_, h_

            cell_w = w / self.thermal_grid_cols
            cell_h = h / self.thermal_grid_rows
            cell_min = min(cell_w, cell_h)

            if painter is not None:
                # Adaptive grid pen based on cell size
                grid_color = QColor(200, 200, 200, 180)  # Semi-transparent white
                if cell_min < 15:
                    pen_width = 1
                elif cell_min < 30:
                    pen_width = 2
                else:
                    pen_width = 3
                grid_pen = QPen(grid_color)
                grid_pen.setWidth(pen_width)
                painter.setPen(grid_pen)

                # Font size based on cell dimensions
                if cell_min < 15:
                    base_font_size = max(6, int(cell_min * 0.35))
                elif cell_min < 25:
                    base_font_size = int(cell_min * 0.40)
                else:
                    base_font_size = int(cell_min * 0.45)
                base_font_size = max(6, min(base_font_size, 24))
                font = QFont("Arial", base_font_size, QFont.Bold)
                painter.setFont(font)

                show_text = cell_min >= 8  # Show text if cells are large enough
                temp_lo, temp_hi = self._compute_grid_temp_bounds(arr)

                # Draw grid lines and temperature values
                for r, c, x, y, rw, rh in _iter_cell_rects(self.thermal_grid_cols, self.thermal_grid_rows, w, h):
                    rect = QRect(x, y, rw, rh)

                    val = float(arr[r, c])
                    temp_c = val
                    bg_color, tcolor = self._temperature_to_grid_colors(temp_c, temp_lo, temp_hi, alpha=160)

                    # Fill the cell to preserve hotspot contrast in numeric overlay mode.
                    painter.fillRect(rect.adjusted(1, 1, -1, -1), bg_color)

                    # Draw grid cell border
                    painter.setPen(grid_pen)
                    painter.drawRect(rect)

                    if not show_text:
                        continue

                    # Draw temperature text
                    painter.setPen(tcolor)
                    txt = f"{temp_c:.2f}"
                    painter.drawText(rect, Qt.AlignCenter, txt)

                painter.end()

                # Cache overlay for this size/signature to prevent flicker
                try:
                    self._cached_thermal_overlay = overlay
                    self._last_overlay_size = (w, h)
                    self._cached_grid_matrix_sig = cache_key_sig
                except Exception:
                    pass
            
            # Display the overlay on the frame
            # CRITICAL: Use actual display size (w, h from label), not base_pixmap size
            # This ensures overlay scales responsively with tile size
            scaled_frame = base_pixmap.scaledToWidth(w, Qt.SmoothTransformation)
            result = QPixmap(w, h)
            result.fill(Qt.black)
            
            # Center the scaled frame on result
            frame_painter = QPainter(result)
            x_offset = (w - scaled_frame.width()) // 2
            y_offset = (h - scaled_frame.height()) // 2
            frame_painter.drawPixmap(x_offset, y_offset, scaled_frame)
            frame_painter.drawPixmap(0, 0, overlay)
            frame_painter.end()
            self.video_label.setPixmap(result)
        except Exception as e:
            print(f"Thermal grid overlay error: {e}")

    def _build_temperature_grid_pixmap(self, matrix):
        """Build a 32x24 grid pixmap with temperature values."""
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
                    print(f"[GRID] Matrix shape mismatch: got {arr.shape}, expected {self.thermal_grid_rows}x{self.thermal_grid_cols}")
                    return None

            # Use CURRENT label size - ensure we get real-time dimensions
            w = max(1, self.video_label.width())
            h = max(1, self.video_label.height())

            # If dimensions are invalid, use fallback
            if w < 50 or h < 50:
                print(f"[GRID] Label size too small ({w}x{h}), using fallback 640x480")
                w = 640
                h = 480

            pix = QPixmap(w, h)
            pix.fill(QColor(0, 0, 0))

            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)

            # Compute stable cell rects to avoid rounding drift
            def _iter_cell_rects(cols, rows, width, height):
                x_edges = [round(i * (width / cols)) for i in range(cols + 1)]
                y_edges = [round(j * (height / rows)) for j in range(rows + 1)]
                for r in range(rows):
                    for c in range(cols):
                        x = x_edges[c]
                        y = y_edges[r]
                        w_ = x_edges[c + 1] - x
                        h_ = y_edges[r + 1] - y
                        yield r, c, x, y, w_, h_

            cell_w = w / self.thermal_grid_cols
            cell_h = h / self.thermal_grid_rows
            cell_min = min(cell_w, cell_h)

            # Adaptive grid pen based on cell size
            grid_color = QColor(60, 60, 60)
            if cell_min < 20:
                pen_width = 1
            elif cell_min < 40:
                pen_width = 2
            elif cell_min < 70:
                pen_width = 3
            else:
                pen_width = 4
            grid_pen = QPen(grid_color)
            grid_pen.setWidth(pen_width)
            painter.setPen(grid_pen)

            # Font size based on cell dimensions
            if cell_min < 15:
                base_font_size = max(6, int(cell_min * 0.35))
            elif cell_min < 25:
                base_font_size = int(cell_min * 0.42)
            else:
                base_font_size = int(cell_min * 0.48)
            base_font_size = max(6, min(base_font_size, 32))
            font = QFont("Arial", base_font_size)
            painter.setFont(font)

            # Decide text format based on cell size
            show_text = cell_min >= 8  # Hide if extremely small
            temp_lo, temp_hi = self._compute_grid_temp_bounds(arr)

            for r, c, x, y, rw, rh in _iter_cell_rects(self.thermal_grid_cols, self.thermal_grid_rows, w, h):
                rect = QRect(x, y, rw, rh)

                val = float(arr[r, c])
                temp_c = val
                bg_color, tcolor = self._temperature_to_grid_colors(temp_c, temp_lo, temp_hi)

                # Fill each cell so hotspots remain immediately visible in numeric mode.
                painter.fillRect(rect.adjusted(1, 1, -1, -1), bg_color)
                painter.drawRect(rect)

                if not show_text:
                    continue
                painter.setPen(tcolor)
                txt = f"{temp_c:.2f}"
                painter.drawText(rect, Qt.AlignCenter, txt)

            painter.end()
            # Cache pixmap for fast resize reuse
            try:
                self._cached_grid_pixmap = pix
            except Exception:
                pass
            return pix
        except Exception as e:
            print(f"Thermal grid render error: {e}")
        return None

    def _render_temperature_grid(self, matrix):
        """Render numeric thermal grid into the label."""
        pix = self._build_temperature_grid_pixmap(matrix)
        if pix is not None:
            self.video_label.setPixmap(pix)

    def _build_thermal_heatmap_pixmap(self, matrix):
        """Build a thermal heatmap pixmap from the matrix."""
        try:
            import numpy as np
            import cv2
            from PyQt5.QtGui import QImage, QPixmap

            arr = np.array(matrix, dtype=np.float32)
            if arr.ndim != 2:
                return None

            arr = self._apply_emissivity_compensation(arr)
            mode = self._sanitize_thermal_mode(getattr(self, 'thermal_render_mode', 'fixed_scale_inferno'))
            self._update_thermal_debug_line(arr, mode)

            if mode == "fixed_scale_inferno":
                window_min, window_max, _ = self._compute_thermal_window(arr, mode)
                norm = np.clip((arr - window_min) / (window_max - window_min) * 255.0, 0, 255).astype(np.uint8)
                color_bgr = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)

            elif mode == "hot_mask_temporal_delta":
                min_val = float(np.min(arr))
                max_val = float(np.max(arr))
                if max_val <= min_val:
                    max_val = min_val + 1.0
                base_norm = ((arr - min_val) / (max_val - min_val) * 255.0).astype(np.uint8)
                color_bgr = cv2.cvtColor(base_norm, cv2.COLOR_GRAY2BGR)

                hot_threshold = max(45.0, float(np.percentile(arr, 90)))
                hot_mask = arr >= hot_threshold
                color_bgr[hot_mask] = (0, 0, 255)

                prev = self._prev_thermal_matrix
                if prev is not None and prev.shape == arr.shape:
                    delta = np.abs(arr - prev)
                    delta_mask = delta >= 1.5
                    color_bgr[delta_mask] = (255, 255, 0)

            else:  # grayscale_valid_hotspots
                window_min, window_max, _ = self._compute_thermal_window(arr, mode)
                base_norm = ((arr - window_min) / (window_max - window_min) * 255.0).astype(np.uint8)
                color_bgr = cv2.cvtColor(base_norm, cv2.COLOR_GRAY2BGR)

                valid_mask = np.isfinite(arr)
                color_bgr[valid_mask] = np.clip(color_bgr[valid_mask] * 0.75 + np.array([0, 80, 0]), 0, 255).astype(np.uint8)

                flat = arr.flatten()
                if flat.size > 0:
                    top_count = min(3, flat.size)
                    top_idx = np.argpartition(flat, -top_count)[-top_count:]
                    cols = arr.shape[1]
                    for idx in top_idx:
                        row = int(idx // cols)
                        col = int(idx % cols)
                        cv2.circle(color_bgr, (col, row), 1, (0, 0, 255), 1)

            self._prev_thermal_matrix = arr.copy()
            color_rgb = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)

            h, w = color_rgb.shape[:2]
            q_img = QImage(color_rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(q_img)

            label_w = max(1, self.video_label.width())
            label_h = max(1, self.video_label.height())
            return pix.scaled(label_w, label_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as e:
            print(f"Thermal heatmap render error: {e}")
        return None

    def _build_thermal_screen_pixmap(self, matrix):
        """Build an enhanced thermal screen pixmap from the matrix."""
        try:
            import numpy as np
            import cv2
            from PyQt5.QtGui import QImage, QPixmap

            arr = np.array(matrix, dtype=np.float32)
            if arr.ndim != 2:
                return None

            min_val = float(np.min(arr))
            max_val = float(np.max(arr))
            if max_val <= min_val:
                max_val = min_val + 1.0

            norm = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX)
            norm = norm.astype(np.uint8)
            norm = cv2.equalizeHist(norm)
            color_bgr = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
            color_rgb = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)

            h, w = color_rgb.shape[:2]
            q_img = QImage(color_rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(q_img)

            label_w = max(1, self.video_label.width())
            label_h = max(1, self.video_label.height())
            return pix.scaled(label_w, label_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as e:
            print(f"Thermal screen render error: {e}")
        return None

    def create_controls(self):
        """Create and position control widgets with theme-aware styling"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app else False
        
        # Top controls (minimize, maximize, reload) aligned on the right
        self.top_left_controls = QWidget(self)
        self.top_left_controls.setObjectName("video_controls")
        self.top_left_controls.setStyleSheet("""
            QWidget#video_controls {
                background-color: transparent;
                border: none;
            }
        """)
        
        top_left_layout = QVBoxLayout(self.top_left_controls)
        top_left_layout.setContentsMargins(2, 2, 2, 2)
        top_left_layout.setSpacing(2)

        self.minimize_btn = self.create_control_button("−", "Restore to grid")
        self.maximize_btn = self.create_control_button("⛶", "Maximize view")
        self.reload_btn = self.create_control_button("⟳", "Reload stream")
        self.minimize_btn.setVisible(False)
        top_left_layout.addWidget(self.minimize_btn)
        top_left_layout.addWidget(self.maximize_btn)
        top_left_layout.addWidget(self.reload_btn)

        # Integrated view-mode toolbar (glassmorphism style)
        self.right_overlay_controls = QWidget(self)
        self.right_overlay_controls.setObjectName("overlay_controls")
        self.right_overlay_controls.setStyleSheet("""
            QWidget#overlay_controls {
                background-color: rgba(18, 24, 32, 0.56);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)
        overlay_layout = QHBoxLayout(self.right_overlay_controls)
        overlay_layout.setContentsMargins(6, 4, 6, 4)
        overlay_layout.setSpacing(4)

        self.default_view_btn = self.create_control_button("📷", "Camera mode (hotkey: D)")
        self.default_view_btn.setCheckable(True)
        self.thermal_view_btn = self.create_control_button("🌡", "Thermal mode (hotkey: T)")
        self.thermal_view_btn.setCheckable(True)
        self.grid_view_btn = self.create_control_button("▦", "Thermal grid mode (hotkey: #)")
        self.grid_view_btn.setCheckable(True)

        overlay_layout.addWidget(self.default_view_btn)
        overlay_layout.addWidget(self.thermal_view_btn)
        overlay_layout.addWidget(self.grid_view_btn)
        # Hover & reveal: keep mode toolbar hidden until operator focuses this tile.
        self.right_overlay_controls.setVisible(False)

        # Left-edge drawer handle for fusion overlay
        self.fusion_drawer_toggle_btn = self.create_control_button("▴", "Collapse sensor banner")
        self.fusion_drawer_toggle_btn.setFixedSize(20, 20)
        self.fusion_drawer_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.fusion_drawer_toggle_btn.clicked.connect(self._toggle_fusion_drawer)
        self.fusion_drawer_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 40, 40, 0.74);
                border: 1px solid rgba(255, 255, 255, 0.14);
                color: #eaf1f9;
                font-weight: 700;
                font-size: 15px;
                border-radius: 10px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: rgba(52, 52, 52, 0.84);
                border: 1px solid rgba(255, 255, 255, 0.24);
                color: #ffffff;
            }
        """)
        self._sync_fusion_drawer_toggle()

        self.fusion_alarm_btn = QPushButton("Raise Alarm", self)
        self.fusion_alarm_btn.setFixedHeight(28)
        self.fusion_alarm_btn.setMinimumWidth(108)
        self.fusion_alarm_btn.setEnabled(True)
        self.fusion_alarm_btn.setToolTip("Raise alarm for this PFDS-mapped location")
        self.fusion_alarm_btn.clicked.connect(self._toggle_local_alarm_override)
        self.fusion_alarm_btn.setStyleSheet("""
            QPushButton {
                color: #FFDC00;
                background-color: rgba(34, 40, 50, 0.92);
                border: 1px solid rgba(255, 210, 0, 0.72);
                border-radius: 9px;
                padding: 0 10px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton:disabled {
                color: rgba(210, 218, 224, 0.60);
                background-color: rgba(44, 52, 62, 0.80);
                border: 1px solid rgba(255, 210, 0, 0.28);
            }
            QPushButton:hover {
                background-color: rgba(50, 58, 72, 0.96);
                border: 1px solid rgba(255, 220, 0, 0.92);
            }
            QPushButton:pressed {
                background-color: rgba(255, 220, 0, 0.18);
            }
        """)
        self.fusion_alarm_btn.setVisible(True)

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

        # Initialize alarm UI after fusion controls exist.
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

        bottom_right_layout.addWidget(self.temp_label)
        # Temperature is shown inside fusion cards; hide legacy corner label to avoid duplicate stray text.
        self.temp_label.setVisible(False)
        self.bottom_right_status.setVisible(False)

        # Position controls initially
        self.position_controls()

    def handle_maximize_state(self):
        """Show minimize button when maximized"""
        self.maximized = True
        self.is_minimized = False
        self.minimize_btn.setVisible(True)
        self.maximize_btn.setEnabled(False)
        # Trigger layout update to adjust fusion panel to new size
        self.position_controls()
        self.update()

    def handle_minimize_state(self):
        """Hide minimize button when minimized"""
        self.maximized = False
        self.is_minimized = True
        self.minimize_btn.setVisible(False)
        self.maximize_btn.setEnabled(True)
        # Trigger layout update to adjust fusion panel to new size
        self.position_controls()
        self.update()

    maximize_requested = pyqtSignal()
    minimize_requested = pyqtSignal()

    def create_control_button(self, text, tooltip=""):
        """Create styled control button with theme awareness"""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        app = QApplication.instance()
        
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        if tooltip:
            btn.setToolTip(tooltip)
        
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
        return btn

    def _ui_scale(self):
        """Compute a bounded UI scale factor from current tile size."""
        try:
            w = max(1, int(self.width()))
            h = max(1, int(self.height()))
            base = min(w / 640.0, h / 360.0)
            return max(0.65, min(1.35, float(base)))
        except Exception:
            return 1.0

    def position_controls(self):
        """Position control widgets correctly with theme-aware margins"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        
        margin = 10
        
        # Top controls (right aligned)
        self.top_left_controls.adjustSize()
        tl_x = self.width() - self.top_left_controls.width() - margin
        self.top_left_controls.move(tl_x, margin)

        # Integrated toolbar: centered at bottom edge to avoid collision with fusion banner at top.
        def _resize_overlay_buttons(size, spacing):
            self.right_overlay_controls.layout().setSpacing(spacing)
            for btn in [self.default_view_btn, self.thermal_view_btn, self.grid_view_btn]:
                if btn:
                    btn.setFixedSize(size, size)

        _resize_overlay_buttons(24, 4)
        self.right_overlay_controls.adjustSize()
        if self.right_overlay_controls.width() > max(90, self.width() - (margin * 2)):
            _resize_overlay_buttons(22, 2)
            self.right_overlay_controls.adjustSize()
        if self.right_overlay_controls.width() > max(90, self.width() - (margin * 2)):
            _resize_overlay_buttons(20, 1)
            self.right_overlay_controls.adjustSize()

        ro_x = int((self.width() - self.right_overlay_controls.width()) / 2)
        ro_y = self.height() - self.right_overlay_controls.height() - margin
        self.right_overlay_controls.move(max(margin, ro_x), max(margin, ro_y))

        # Resolve drawer geometry once for both handle and action controls.
        drawer_rect, drawer_collapsed = self._fusion_drawer_rect_for_layout()

        # Fusion banner toggle centered at top of the strip
        self.fusion_drawer_toggle_btn.adjustSize()
        btn_w = self.fusion_drawer_toggle_btn.width()
        btn_h = self.fusion_drawer_toggle_btn.height()
        if drawer_collapsed:
            fd_x = drawer_rect.center().x() - int(btn_w / 2)
            fd_y = drawer_rect.y() + max(1, int((drawer_rect.height() - btn_h) / 2))
        else:
            fd_x = drawer_rect.center().x() - int(btn_w / 2)
            fd_y = drawer_rect.y() - int(btn_h * 0.45)
        fd_x = max(0, min(fd_x, max(0, self.width() - btn_w)))
        fd_y = max(margin, min(fd_y, max(margin, self.height() - btn_h - margin)))
        self.fusion_drawer_toggle_btn.move(fd_x, fd_y)

        # Action controls inside fusion banner
        self._position_action_controls()

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
        self._update_video_label_geometry(event.size())
        self.position_controls()
        
        # Invalidate caches on resize to force regeneration with proper scaling
        self._cached_grid_pixmap = None
        self._cached_thermal_overlay = None
        self._last_overlay_size = None  # Invalidate size tracking
        self._cached_grid_matrix_sig = None
        
        # Regenerate overlays with new dimensions
        if self.display_mode == "grid" and self._last_thermal_matrix is not None:
            try:
                self._render_temperature_grid(self._last_thermal_matrix)
            except Exception:
                pass
        elif self.display_mode == "thermal" and self._last_thermal_matrix is not None:
            try:
                pix = self._build_thermal_heatmap_pixmap(self._last_thermal_matrix)
                if pix:
                    self.video_label.setPixmap(pix)
                self._redraw_with_grid()
            except Exception:
                pass
        else:
            # Redraw fusion overlay or hot cells with new size
            try:
                self._redraw_with_grid()
            except Exception:
                pass
    
    def mouseMoveEvent(self, event):
        """Handle mouse move without forcing repaints to avoid flicker."""
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        """Claim focus on click so D/T/# hotkeys reliably target this tile."""
        try:
            if event.button() == Qt.LeftButton:
                self.setFocus(Qt.MouseFocusReason)
        except Exception:
            pass
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """Reveal local mode toolbar when operator focuses this feed."""
        if hasattr(self, 'right_overlay_controls'):
            self.right_overlay_controls.setVisible(True)
            self.right_overlay_controls.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Hide local mode toolbar to reduce visual clutter."""
        if hasattr(self, 'right_overlay_controls'):
            self.right_overlay_controls.setVisible(False)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        """Fast operator shortcuts for display modes: D, T, and #."""
        try:
            key = int(event.key())
            text = (event.text() or "").strip()
            if key == Qt.Key_D:
                self._activate_default_view()
                event.accept()
                return
            if key == Qt.Key_T:
                self._activate_thermal_view()
                event.accept()
                return
            if text == "#" or key in (Qt.Key_NumberSign,):
                self._activate_grid_view()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click the fusion banner area to collapse/expand it quickly."""
        try:
            if event.button() == Qt.LeftButton and bool(self.show_fusion_overlay):
                drawer_rect, _ = self._fusion_drawer_rect_for_layout()
                if drawer_rect.contains(event.pos()):
                    self._toggle_fusion_drawer()
                    event.accept()
                    return
        except Exception:
            pass
        super().mouseDoubleClickEvent(event)

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
        if self.worker and hasattr(self.worker, 'timer') and self.worker.timer:
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
        # Anomaly frame signal (QImage, score, stream_id, yolo_score, detections)
        if hasattr(self.worker, 'anomaly_frame_ready'):
            result = self.worker.anomaly_frame_ready.connect(self.handle_anomaly_frame, Qt.QueuedConnection)
            print(f"[VIDEO_WIDGET_INIT] Connected anomaly_frame_ready: {result}", flush=True)
        if hasattr(self.worker, 'detection_event'):
            result = self.worker.detection_event.connect(self.handle_detection_event, Qt.QueuedConnection)
            print(f"[VIDEO_WIDGET_INIT] Connected detection_event: {result}", flush=True)
        else:
            print(f"[VIDEO_WIDGET_INIT] Worker does NOT have anomaly_frame_ready signal!", flush=True)

        # Connect buttons
        self.reload_btn.clicked.connect(self.reload_stream)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.minimize_btn.clicked.connect(self.toggle_minimize)
        self.default_view_btn.clicked.connect(self._activate_default_view)
        self.thermal_view_btn.clicked.connect(self._activate_thermal_view)
        self.grid_view_btn.clicked.connect(self._activate_grid_view)

        # Start thread
        self.worker_thread.started.connect(self.worker.start_stream)
        self.worker_thread.start()

    def handle_vision_score(self, score):
        """Forward vision score to main window for fusion."""
        # Find main window and call fusion handler
        mw = self.window()
        if hasattr(mw, 'handle_vision_score_from_widget'):
            mw.handle_vision_score_from_widget(self.loc_id, score)

    @pyqtSlot(QImage, float, str, float, object)
    def handle_anomaly_frame(self, qimage, score, stream_id, yolo_score, detections):
        """Forward anomaly/incident frame to main window with metadata."""
        import time
        self._set_detection_highlight("#00ff00")
        try:
            self._latest_detections = detections or []
            self._latest_detection_frame_size = (qimage.width(), qimage.height())
            self._latest_detection_ts = time.time() * 1000
        except Exception:
            pass
        if is_debug_enabled():
            import sys
            sys.stderr.write(f"[HANDLER_CALLED] qimage={type(qimage).__name__}, score={score}, stream_id={stream_id}, yolo={yolo_score}, det={len(detections or [])}\n")
            sys.stderr.flush()
            debug_print(f"[VIDEO_WIDGET] handle_anomaly_frame called: stream_id={stream_id}, score={score:.3f}, yolo={yolo_score:.3f}, detections={len(detections or [])}")
        try:
            mw = self.window()
            if hasattr(mw, 'handle_incident_frame_from_widget'):
                debug_print(f"[VIDEO_WIDGET] Calling handle_incident_frame_from_widget")
                mw.handle_incident_frame_from_widget(self.loc_id, qimage, float(score), float(yolo_score), detections or [])
            elif hasattr(mw, 'handle_anomaly_frame_from_widget'):
                print(f"[VIDEO_WIDGET] Fallback to handle_anomaly_frame_from_widget", flush=True)
                mw.handle_anomaly_frame_from_widget(self.loc_id, qimage, float(score))
        except Exception as e:
            from error_logger import get_error_logger
            get_error_logger().log(self.name, f"Anomaly forward error: {e}")
            print(f"[VIDEO_WIDGET] Exception: {e}", flush=True)

    @pyqtSlot(str, float, object, object)
    def handle_detection_event(self, status, yolo_score, detections, frame_size):
        """Highlight tile when YOLO returns any detection."""
        import time
        color = "#00ff00" if status in ("CONFIRMED", "POSSIBLE") else "#ffa500"
        self._set_detection_highlight(color)
        self._latest_detections = detections or []
        if frame_size and len(frame_size) == 2:
            self._latest_detection_frame_size = frame_size
        elif self._last_frame_size_from_pixmap:
            self._latest_detection_frame_size = self._last_frame_size_from_pixmap
        self._latest_detection_ts = time.time() * 1000

    def _apply_video_label_style(self):
        """Apply base style to video label."""
        self.video_label.setStyleSheet(
            "QLabel { background-color: #04080c; border: none; }"
        )

    def _apply_tile_border(self, border_color=None):
        """Apply optional detection border to the tile container."""
        alarm_color = str(getattr(self, '_alarm_highlight_color', '#ff5252')).lower()
        border_color_norm = str(border_color or "").lower()
        if border_color:
            border = f"{self._tile_border_px}px solid {border_color}"
            self._tile_border_inset = self._tile_border_px
            bg_color = "#1a0d10" if border_color_norm == alarm_color else "#121417"
        else:
            border = "1px solid rgba(74, 114, 138, 0.55)"
            self._tile_border_inset = 1
            bg_color = "#121417"
        self.setStyleSheet(
            f"QWidget#videoTile {{ border: {border}; background-color: {bg_color}; }}"
        )
        self._update_video_label_geometry()

    def _set_detection_highlight(self, color):
        """Highlight the tile briefly when a detection is received."""
        # Alarm highlight takes precedence over detection colors.
        if bool(getattr(self, 'alarm_active', False)):
            color = getattr(self, '_alarm_highlight_color', '#ff5252')
        self._apply_tile_border(color)
        self._apply_detection_overlay(color)
        self._detection_highlight_timer.start(self._detection_highlight_ms)

    def _clear_detection_highlight(self):
        """Clear detection highlight border."""
        self._refresh_tile_highlight()

    def _refresh_tile_highlight(self):
        """Apply persistent tile highlight for alarm state, otherwise restore default style."""
        if bool(getattr(self, 'alarm_active', False)):
            color = getattr(self, '_alarm_highlight_color', '#ff5252')
            self._apply_tile_border(color)
            self._apply_detection_overlay(color)
        else:
            self._apply_tile_border()
            self._clear_detection_overlay()

    def _update_video_label_geometry(self, size=None):
        """Keep the video label inset when a border is shown."""
        if not hasattr(self, "video_label"):
            return
        if size is None:
            size = self.size()
        inset = self._tile_border_inset
        width = max(1, size.width() - (inset * 2))
        height = max(1, size.height() - (inset * 2))
        self.video_label.setGeometry(inset, inset, width, height)
        self._update_detection_overlay_geometry(size)

    def _update_detection_overlay_geometry(self, size=None):
        if not hasattr(self, "detection_overlay"):
            return
        if size is None:
            size = self.size()
        self.detection_overlay.setGeometry(0, 0, max(1, size.width()), max(1, size.height()))

    def _apply_detection_overlay(self, color):
        if not hasattr(self, "detection_overlay"):
            return
        border = f"{self._tile_border_px}px solid {color}"
        self.detection_overlay.setStyleSheet(
            f"QLabel {{ background-color: transparent; border: {border}; }}"
        )
        self.detection_overlay.show()
        self.detection_overlay.raise_()
        self.top_left_controls.raise_()
        self.right_overlay_controls.raise_()
        self.fusion_drawer_toggle_btn.raise_()
        self.fusion_alarm_btn.raise_()
        self.bottom_right_status.raise_()

    def _clear_detection_overlay(self):
        if not hasattr(self, "detection_overlay"):
            return
        self.detection_overlay.hide()

    def update_frame(self, pixmap):
        if pixmap is None or pixmap.isNull():
            from error_logger import get_error_logger
            get_error_logger().log(self.name, "Null pixmap received")
            self.last_error_message = "Null pixmap received"
            self._render_no_video_fallback()
            if not (self._last_thermal_matrix is not None or self.fusion_data):
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
            
            self._last_frame_size_from_pixmap = (pixmap.width(), pixmap.height())

            # Scale video frame to fully fill the tile (allow slight crop to avoid letterboxing)
            scaled_video = pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            
            # Render based on selected display mode
            if self.display_mode == "grid" and self._last_thermal_matrix is not None:
                grid_pixmap = self._build_temperature_grid_pixmap(self._last_thermal_matrix)
                if grid_pixmap:
                    self._last_base_pixmap = grid_pixmap
                    self.video_label.setPixmap(grid_pixmap)
                    self._redraw_with_grid()
                else:
                    self._last_base_pixmap = scaled_video
                    self.video_label.setPixmap(scaled_video)
            elif self.display_mode == "thermal" and self._last_thermal_matrix is not None:
                thermal_pixmap = self._build_thermal_heatmap_pixmap(self._last_thermal_matrix)
                if thermal_pixmap:
                    self._last_base_pixmap = thermal_pixmap
                    self.video_label.setPixmap(thermal_pixmap)
                    self._redraw_with_grid()
                else:
                    self._last_base_pixmap = scaled_video
                    self.video_label.setPixmap(scaled_video)
            elif self.show_fusion_overlay:
                # Default camera view with fusion overlay
                overlay_pixmap = self._overlay_detection_boxes(scaled_video)
                self._last_base_pixmap = overlay_pixmap
                self.video_label.setPixmap(overlay_pixmap)
                self._redraw_with_grid()
            else:
                overlay_pixmap = self._overlay_detection_boxes(scaled_video)
                self._last_base_pixmap = overlay_pixmap
                self.video_label.setPixmap(overlay_pixmap)
            
            # Analyze frame luminance to adjust control colors for contrast
            self._update_controls_color_for_contrast(scaled_video)
            
            self.last_error_message = None
        except Exception as e:
            self.handle_error(str(e))

    def _overlay_detection_boxes(self, base_pixmap):
        """Overlay detection boxes on the pixmap when recent detections exist."""
        try:
            import time
            from PyQt5.QtGui import QPainter, QPen, QColor

            frame_size = self._latest_detection_frame_size or self._last_frame_size_from_pixmap
            if not self._latest_detections or not frame_size:
                return base_pixmap

            age_ms = (time.time() * 1000) - self._latest_detection_ts
            if age_ms > self._detection_overlay_ttl_ms:
                return base_pixmap

            frame_w, frame_h = frame_size
            if not frame_w or not frame_h:
                return base_pixmap

            target_w = base_pixmap.width()
            target_h = base_pixmap.height()
            scale = max(target_w / frame_w, target_h / frame_h)

            scaled_w = frame_w * scale
            scaled_h = frame_h * scale
            x_offset = (scaled_w - target_w) / 2.0
            y_offset = (scaled_h - target_h) / 2.0

            result = base_pixmap.copy()
            painter = QPainter(result)
            pen = QPen(QColor(0, 200, 255))
            pen.setWidth(2)
            painter.setPen(pen)

            for det in self._latest_detections:
                bbox = det.get("bbox") if isinstance(det, dict) else None
                if not bbox or len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = [float(v) for v in bbox]
                sx1 = int(x1 * scale - x_offset)
                sy1 = int(y1 * scale - y_offset)
                sx2 = int(x2 * scale - x_offset)
                sy2 = int(y2 * scale - y_offset)
                painter.drawRect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))

            painter.end()
            return result
        except Exception:
            return base_pixmap

    def handle_error(self, message):
        from error_logger import get_error_logger
        get_error_logger().log(self.name, message)
        self.last_error_message = message
        self.video_label.setText(f"ERROR: {message}\n{self.rtsp_url}")
        self.video_label.setStyleSheet("color: red; background-color: black; padding: 5px;")

    def contextMenuEvent(self, event):
        """Disable per-tile context menu to prevent white popup overlays."""
        event.accept()

    def handle_connection_status(self, connected):
        """Update connection status display"""
        self._rtsp_connected = bool(connected)
        if connected:
            self.video_label.setText("")
            self.video_label.setStyleSheet("background-color: black;")
        else:
            self._render_no_video_fallback()
            if not (self._last_thermal_matrix is not None or self.fusion_data):
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
                self.update_fire_alarm(data['fire_alarm'], source="remote")


    def update_fire_alarm(self, alarm_active, source="remote"):
        """Update fire alarm indicator with theme-aware styling"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        was_alarm_active = bool(getattr(self, 'alarm_active', False))

        if source == "manual":
            self._manual_alarm_override = bool(alarm_active)
            effective_alarm = bool(alarm_active)
        else:
            remote_alarm_active = bool(alarm_active)
            # Do not clear an active alarm from remote updates until operator ACK/Silence.
            if (not remote_alarm_active) and was_alarm_active and (not bool(getattr(self, 'alarm_acknowledged', False))):
                remote_alarm_active = True
            self._remote_alarm_active = remote_alarm_active
            if self._manual_alarm_override is not None:
                effective_alarm = bool(self._manual_alarm_override)
            else:
                effective_alarm = self._remote_alarm_active

        self.alarm_active = effective_alarm  # Store currently rendered alarm state

        # Alarm clear always resets local silence latch.
        if not effective_alarm:
            self._alarm_silenced = False

        if self._manual_alarm_override is None:
            self.fusion_alarm_btn.setToolTip("Sensor-driven alarm state. Click to toggle demo override")
        else:
            self.fusion_alarm_btn.setToolTip("Demo override active. Click to return to sensor-driven state")
        
        # Update temperature color to sync with alarm state
        self._update_temp_color()
        if effective_alarm and not was_alarm_active:
            self._ack_count = 0
            self.alarm_acknowledged = False
        if not effective_alarm:
            self.set_alarm_acknowledged(False)
            self._manual_action_state = 'normal'
            self._ack_count = 0
        self._sync_alarm_ack_button()
        self._update_action_pill_visual()
        self._refresh_tile_highlight()
        self.position_controls()

    def _toggle_local_alarm_override(self):
        """Tactical single-button flow: EMERGENCY -> SILENCE (visual threat remains)."""
        if bool(getattr(self, 'alarm_active', False)):
            # Active alarm click silences audible channel but keeps visual threat active.
            if not bool(getattr(self, '_alarm_silenced', False)):
                self.alarm_ack_requested.emit(str(self.loc_id))
                self._alarm_silenced = True
                self._manual_action_state = 'silenced'
        else:
            # Secure click raises emergency alarm.
            self._alarm_silenced = False
            self._manual_action_state = 'raised'
            self.update_fire_alarm(True, source="manual")
            self.alarm_raise_requested.emit(str(self.loc_id))
        self._update_action_pill_visual()
        self._sync_alarm_ack_button()

    def _emit_alarm_ack(self):
        """Emit an ACK request for this tile/device."""
        if not bool(getattr(self, 'alarm_active', False)):
            return
        self.alarm_ack_requested.emit(str(self.loc_id))
        self._ack_count = int(getattr(self, '_ack_count', 0) or 0) + 1
        self.set_alarm_acknowledged(True)
        self._sync_alarm_ack_button()
        self._update_action_pill_visual()

    def set_alarm_acknowledged(self, acknowledged):
        """Update UI ACK state for the active alarm on this tile."""
        self.alarm_acknowledged = bool(acknowledged)
        self._sync_alarm_ack_button()

    def _sync_alarm_ack_button(self):
        if not hasattr(self, 'fusion_alarm_btn'):
            return
        should_show = bool(self.show_fusion_overlay) and (not bool(getattr(self, 'fusion_drawer_collapsed', False)))
        self.fusion_alarm_btn.setVisible(should_show)
        if not should_show:
            return
        self.fusion_alarm_btn.setEnabled(True)

    def _update_action_pill_visual(self):
        if not hasattr(self, 'fusion_alarm_btn'):
            return
        from math import sin
        from time import time as now_time
        label = 'SILENCED' if (self.alarm_active and bool(getattr(self, '_alarm_silenced', False))) else ('SILENCE' if self.alarm_active else 'EMERGENCY')

        if self.alarm_active:
            pulse_alpha = int(156 + 76 * ((sin(now_time() * 7.0) + 1.0) * 0.5))
            self.fusion_alarm_btn.setStyleSheet("""
                QPushButton {
                    color: #ffffff;
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(68, 0, 0, 0.94),
                        stop:0.35 rgba(88, 0, 0, 0.94),
                        stop:0.5 rgba(110, 12, 12, 0.94),
                        stop:0.65 rgba(88, 0, 0, 0.94),
                        stop:1 rgba(68, 0, 0, 0.94));
                    border: 1px solid rgba(255, 0, 0, %d);
                    border-radius: 9px;
                    padding: 0 10px;
                    font-size: 14px;
                    font-weight: 700;
                    font-family: 'Roboto Mono';
                }
                QPushButton:hover {
                    background-color: rgba(110, 0, 0, 0.96);
                }
            """ % pulse_alpha)
        else:
            self.fusion_alarm_btn.setStyleSheet("""
                QPushButton {
                    color: #FFD700;
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(32, 36, 46, 0.94),
                        stop:0.33 rgba(40, 44, 56, 0.94),
                        stop:0.5 rgba(56, 62, 76, 0.94),
                        stop:0.66 rgba(40, 44, 56, 0.94),
                        stop:1 rgba(32, 36, 46, 0.94));
                    border: 1px solid rgba(255, 210, 0, 0.82);
                    border-radius: 9px;
                    padding: 0 10px;
                    font-size: 14px;
                    font-weight: 700;
                    font-family: 'Roboto Mono';
                }
                QPushButton:hover {
                    background-color: rgba(48, 54, 66, 0.96);
                }
            """)
        self.fusion_alarm_btn.setText(label)
        if self.alarm_active:
            self.fusion_alarm_btn.setToolTip("Alarm active. Click SILENCE to mute audible alarm while visual threat stays active")
        else:
            self.fusion_alarm_btn.setToolTip("SECURE state. Click EMERGENCY to trigger alarm")

    def _position_action_controls(self):
        if not hasattr(self, 'fusion_alarm_btn'):
            return
        card = getattr(self, '_action_card_rect', None)
        expanded = bool(self.show_fusion_overlay) and (not bool(getattr(self, 'fusion_drawer_collapsed', False)))
        if (not expanded) or (card is None):
            self.fusion_alarm_btn.setVisible(False)
            return

        scale = self._ui_scale()
        pad_x = max(6, int(8 * scale))
        top_y = card.y() + max(24, int(26 * scale))
        available_w = max(60, card.width() - (2 * pad_x))

        compact = bool(getattr(self, 'is_minimized', False)) or card.width() < int(155 * scale)
        btn_h = max(24, min(34, int(card.height() * (0.30 if compact else 0.26))))
        self.fusion_alarm_btn.setFixedHeight(btn_h)

        if compact:
            alarm_w = max(56, int(available_w * 0.94))
            row_y = min(card.bottom() - btn_h - 2, top_y + max(2, int(2 * scale)))
            self.fusion_alarm_btn.setFixedWidth(alarm_w)
            self.fusion_alarm_btn.move(card.x() + pad_x, row_y)
        else:
            # Keep Raise Alarm centered so painted Normal/Ack rows can sit above/below.
            alarm_w = max(92, available_w)
            self.fusion_alarm_btn.setFixedWidth(alarm_w)
            row1_y = card.y() + int((card.height() - btn_h) * 0.52)
            row1_y = max(top_y, min(card.bottom() - btn_h - 2, row1_y))
            x = card.x() + pad_x
            self.fusion_alarm_btn.move(x, row1_y)

        self.fusion_alarm_btn.setVisible(True)
        self.fusion_alarm_btn.raise_()

    def _fusion_drawer_rect_for_layout(self):
        scale = self._ui_scale()
        width = max(1, self.width())
        height = max(1, self.height())
        margin = int(8 * scale)
        collapsed = bool(getattr(self, 'fusion_drawer_collapsed', False))
        mode_gain = 1.12 if bool(getattr(self, 'maximized', False)) else (0.90 if bool(getattr(self, 'is_minimized', False)) else 1.0)
        strip_h = max(64, int(108 * scale * mode_gain))
        strip_h = min(strip_h, max(64, int(height * 0.36)))
        strip_w = max(140, width - (2 * margin))
        if collapsed:
            rail_w = max(138, int(196 * scale * (1.06 if bool(getattr(self, 'maximized', False)) else 1.0)))
            rail_h = max(30, int(38 * scale))
            return QRect(margin, margin, rail_w, rail_h), collapsed
        return QRect(margin, margin, strip_w, strip_h), collapsed

    def set_fusion_data(self, fusion_data):
        """Set fusion data for overlay display."""
        import time
        self.fusion_data = fusion_data
        if isinstance(fusion_data, dict):
            self._fusion_last_packet_ts = time.time()
        self._record_fusion_trends(fusion_data)
        # Trigger redraw whether or not RTSP frame is currently available.
        if self.video_label.pixmap() and not self.video_label.pixmap().isNull():
            self._redraw_with_grid()
        elif self.show_fusion_overlay:
            self._render_no_video_fallback()

    def _expire_stale_sensor_overlay(self):
        """Clear stale fusion/thermal state when no fresh packets arrive."""
        try:
            import time
            now = time.time()
            timeout_s = float(getattr(self, '_sensor_stale_timeout_s', 3.0) or 3.0)

            fusion_ts = float(getattr(self, '_fusion_last_packet_ts', 0.0) or 0.0)
            thermal_ts = float(getattr(self, '_thermal_last_packet_ts', 0.0) or 0.0)

            stale_fusion = bool(self.fusion_data) and fusion_ts > 0.0 and (now - fusion_ts) > timeout_s
            stale_thermal = self._last_thermal_matrix is not None and thermal_ts > 0.0 and (now - thermal_ts) > timeout_s

            if stale_fusion:
                self.fusion_data = None
                self._fusion_trends = {}
                # Reflect no-active-sensor state in alarm/ack widgets.
                self._remote_alarm_active = False
                self.update_fire_alarm(False, source="remote")

            if stale_thermal:
                self._last_thermal_matrix = None
                self._cached_thermal_overlay = None
                self._cached_grid_pixmap = None
                self._cached_grid_matrix_sig = None
        except Exception:
            pass

    def _record_fusion_trends(self, fusion_data):
        if not isinstance(fusion_data, dict):
            return
        self._append_trend_value('accuracy', float(fusion_data.get('confidence', 0.0) or 0.0))
        for trend_key, field_key in (
            ('thermal', 'thermal_max'),
            ('gas', 'gas_ppm'),
            ('smoke', 'smoke_level'),
            ('flame', 'flame_raw'),
        ):
            value = fusion_data.get(field_key)
            if value is not None:
                self._append_trend_value(trend_key, float(value or 0.0))

    def _append_trend_value(self, key, value, max_len=18):
        if not hasattr(self, '_fusion_trends') or not isinstance(getattr(self, '_fusion_trends', None), dict):
            self._fusion_trends = {}
        series = self._fusion_trends.setdefault(str(key), [])
        series.append(float(value))
        if len(series) > int(max_len):
            del series[0:len(series) - int(max_len)]

    def _trend_direction(self, key):
        series = (getattr(self, '_fusion_trends', {}) or {}).get(str(key), [])
        if len(series) < 2:
            return '='
        delta = float(series[-1]) - float(series[-2])
        if delta > 0:
            return '^'
        if delta < 0:
            return 'v'
        return '='

    def _draw_sparkline(self, painter, rect, key, color):
        try:
            from PyQt5.QtGui import QPen
            from PyQt5.QtCore import QPointF
            series = (getattr(self, '_fusion_trends', {}) or {}).get(str(key), [])
            if len(series) < 2:
                return
            mn = min(series)
            mx = max(series)
            span = (mx - mn) if mx != mn else 1.0
            step = rect.width() / max(1, (len(series) - 1))
            pts = []
            for idx, val in enumerate(series):
                x = rect.x() + (idx * step)
                norm = (float(val) - mn) / span
                y = rect.y() + rect.height() - (norm * rect.height())
                pts.append(QPointF(x, y))
            painter.setPen(QPen(color, 1))
            for i in range(1, len(pts)):
                painter.drawLine(pts[i - 1], pts[i])
        except Exception:
            pass
    
    def _draw_fusion_overlay(self, painter, width, height):
        """Delegate fusion banner rendering to util/fusionbanner.py."""
        render_fusion_overlay(self, painter, width, height)

    def set_temperature(self, temp):
        """Set temperature display with current value and appropriate color."""
        self.current_temp = temp  # Store current temperature
        if not hasattr(self, 'temp_label'):
            return  # Label not created yet, skip update
        # Update temperature display
        self.temp_label.setText(f"Temp: {temp:.1f}°C")
        self._update_temp_color()

    def _update_temp_color(self):
        """Update temperature label color based on alarm state and temperature value."""
        if not hasattr(self, 'current_temp') or not hasattr(self, 'temp_label'):
            return  # Not ready yet
        
        # Color syncs with fusion alarm state for consistency
        if self.alarm_active:
            # Alarm active: red color with bold text
            # Temperature alarm active - red color
            self.temp_label.setStyleSheet("color: red; font-weight: bold;")
        elif self.current_temp > 35:
            # Elevated temperature but no alarm: orange warning
            # Elevated temperature - orange color
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
            if self.isMinimized() or not self.worker_thread or not self.worker_thread.isRunning():
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
        """Backward-compatible toggle for numeric grid mode."""
        if enabled:
            self.set_display_mode("grid")
        else:
            self.set_display_mode("default")

    def set_display_mode(self, mode):
        """Set display mode: default, thermal, or grid."""
        mode = (mode or "default").strip().lower()
        if mode not in ("default", "thermal", "grid"):
            mode = "default"
        self.display_mode = mode
        self.thermal_grid_view_enabled = (mode == "grid")
        self.grid_view = (mode == "grid")
        self.show_fusion_overlay = True
        self._cached_thermal_overlay = None
        self._last_overlay_matrix_hash = None
        try:
            self._save_grid_pref(mode == "grid")
        except Exception:
            pass
        # Render immediately when switching modes to avoid waiting on next frame.
        try:
            if self._last_thermal_matrix is not None:
                if mode == "grid":
                    self._render_temperature_grid(self._last_thermal_matrix)
                elif mode == "thermal":
                    pix = self._build_thermal_heatmap_pixmap(self._last_thermal_matrix)
                    if pix:
                        self.video_label.setPixmap(pix)
                    self._redraw_with_grid()
        except Exception as e:
            print(f"Display mode render error: {e}")
        try:
            self._sync_overlay_buttons_from_state()
        except Exception:
            pass

    def _sync_overlay_buttons_from_state(self, initial=False):
        """Keep overlay buttons in sync with current display mode."""
        if not hasattr(self, 'default_view_btn') or not hasattr(self, 'thermal_view_btn') or not hasattr(self, 'grid_view_btn'):
            return
        for mode, btn in (
            ("default", self.default_view_btn),
            ("thermal", self.thermal_view_btn),
            ("grid", self.grid_view_btn),
        ):
            btn.blockSignals(True)
            btn.setChecked(mode == self.display_mode)
            btn.blockSignals(False)
        if initial:
            self.show_fusion_overlay = True

    def _activate_default_view(self):
        """Select default camera view with fusion overlay."""
        self.set_display_mode("default")

    def _activate_thermal_view(self):
        """Select thermal heatmap view with fusion overlay."""
        self.set_display_mode("thermal")

    def _activate_grid_view(self):
        """Select thermal numeric grid view with fusion overlay."""
        self.set_display_mode("grid")

    def _sync_fusion_drawer_toggle(self):
        if not hasattr(self, 'fusion_drawer_toggle_btn'):
            return
        collapsed = bool(getattr(self, 'fusion_drawer_collapsed', False))
        self.fusion_drawer_toggle_btn.setText("▾" if collapsed else "▴")
        self.fusion_drawer_toggle_btn.setToolTip(
            "Bring down Fusion cards" if collapsed else "Move Fusion cards up"
        )

    def _toggle_fusion_drawer(self):
        self.fusion_drawer_collapsed = not bool(getattr(self, 'fusion_drawer_collapsed', False))
        self._sync_fusion_drawer_toggle()
        self._sync_alarm_ack_button()
        self.position_controls()
        if self.video_label.pixmap() and not self.video_label.pixmap().isNull():
            self._redraw_with_grid()
        elif self.show_fusion_overlay:
            self._render_no_video_fallback()

    def stop(self):
        """Safe thread cleanup"""
        try:
            if self.worker_thread and self.worker_thread.isRunning():
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
            if self.worker_thread and self.worker_thread.isRunning():
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
            for btn in [
                self.minimize_btn,
                self.maximize_btn,
                self.default_view_btn,
                self.thermal_view_btn,
                self.grid_view_btn,
                self.reload_btn,
            ]:
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
