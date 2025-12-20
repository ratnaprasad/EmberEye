from video_worker import VideoWorker
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer, QObject
from PyQt5.QtGui import QColor

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
        
        # Alarm state and frame freeze
        self.alarm_active = False
        self.frozen_frame = None
        self.freeze_on_alarm = True
        
        # Fusion data display
        self.fusion_data = None
        self.show_fusion_overlay = True

        self.setMinimumSize(320, 240)
        self.video_label = QLabel(self)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.sensor_handler = SensorHandler()
        self.sensor_handler.data_received.connect(self.update_sensor_display)

        self.create_controls()
        self.maximize_requested.connect(self.handle_maximize_state)
        self.minimize_requested.connect(self.handle_minimize_state)
        self.thermal_data_received.connect(self._apply_thermal_overlay_internal)
        self.init_worker()
        self.top_left_controls.raise_()
        self.bottom_right_status.raise_()

    def set_thermal_overlay(self, matrix):
        """Thread-safe method to set thermal overlay from any thread."""
        self.thermal_data_received.emit(matrix)

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
        
        # Trigger redraw if we have a current frame
        if self.video_label.pixmap() and not self.video_label.pixmap().isNull():
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
        """Apply thermal overlay (runs in main Qt thread via signal)."""
        try:
            import numpy as np
            from PyQt5.QtGui import QImage, QPainter, QPixmap
            from PyQt5.QtCore import Qt
            import cv2
            
            # Convert matrix to numpy array
            arr = np.array(matrix, dtype=np.float32)
            arr_norm = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX)
            arr_uint8 = arr_norm.astype(np.uint8)
            
            # Apply colormap
            color_img = cv2.applyColorMap(arr_uint8, cv2.COLORMAP_JET)
            
            # Convert BGR to RGB
            color_img_rgb = cv2.cvtColor(color_img, cv2.COLOR_BGR2RGB)
            
            # Get widget dimensions
            h, w = self.video_label.height(), self.video_label.width()
            if h <= 0 or w <= 0:
                return
            
            # Resize overlay to match video label
            overlay = cv2.resize(color_img_rgb, (w, h), interpolation=cv2.INTER_LINEAR)
            
            # Create QImage with copied data to avoid memory issues
            bytes_per_line = 3 * w
            qimg = QImage(overlay.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888).copy()
            
            # Cache thermal overlay for reuse
            self.cached_thermal_overlay = QPixmap.fromImage(qimg)
            
            # Get base pixmap
            base_pixmap = self.video_label.pixmap()
            if base_pixmap and not base_pixmap.isNull():
                # Blend with existing frame
                base_img = base_pixmap.toImage().convertToFormat(QImage.Format_RGB888)
                painter = QPainter(base_img)
                painter.setOpacity(0.5)
                painter.drawImage(0, 0, qimg)
                painter.end()
                self.video_label.setPixmap(QPixmap.fromImage(base_img))
            else:
                # No base frame, show thermal only
                self.video_label.setPixmap(self.cached_thermal_overlay)
        except Exception as e:
            print(f"Thermal overlay error: {e}")
            from error_logger import get_error_logger
            get_error_logger().log('ThermalOverlay', f'Apply error: {e}')

    def create_controls(self):
        """Create and position control widgets"""
        # Top-left controls (minimize, maximize, reload)
        self.top_left_controls = QWidget(self)
        self.top_left_controls.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        top_left_layout = QHBoxLayout(self.top_left_controls)
        top_left_layout.setContentsMargins(5, 2, 5, 2)
        top_left_layout.setSpacing(5)

        self.minimize_btn = self.create_control_button("—")
        self.maximize_btn = self.create_control_button("□")
        self.reload_btn = self.create_control_button("⟳")
        self.minimize_btn.setVisible(False)
        top_left_layout.addWidget(self.minimize_btn)
        top_left_layout.addWidget(self.maximize_btn)
        top_left_layout.addWidget(self.reload_btn)

        # Bottom-right status (fire alarm, temperature)
        self.bottom_right_status = QWidget(self)
        self.bottom_right_status.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        bottom_right_layout = QHBoxLayout(self.bottom_right_status)
        bottom_right_layout.setContentsMargins(10, 5, 10, 5)
        bottom_right_layout.setSpacing(15)

        self.fire_alarm_status = QLabel()
        self.fire_alarm_status.setFixedSize(20, 20)
        self.update_fire_alarm(False)
        
        self.temp_label = QLabel("Temp: --°C")
        self.temp_label.setStyleSheet("color: white; font: 10pt;")

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

    def create_control_button(self, text):
        """Create styled control button"""
        btn = QPushButton(text)
        btn.setFixedSize(30, 30)
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
        """Position control widgets correctly"""
        # Top-left controls
        self.top_left_controls.adjustSize()
        self.top_left_controls.move(25, 25)

        # Bottom-right status
        self.bottom_right_status.adjustSize()
        br_x = self.width() - self.bottom_right_status.width() - 5
        br_y = self.height() - self.bottom_right_status.height() - 5
        self.bottom_right_status.move(br_x, br_y)

    def resizeEvent(self, event):
        """Handle widget resizing"""
        self.video_label.resize(event.size())
        self.position_controls()
        super().resizeEvent(event)

    def init_worker(self):
        """Initialize video streaming components"""
        self.worker = VideoWorker(self.rtsp_url)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        # Connect signals
        self.worker.frame_ready.connect(self.update_frame, Qt.QueuedConnection)
        self.worker.error_occurred.connect(self.handle_error, Qt.QueuedConnection)   
        self.worker.connection_status.connect(self.handle_connection_status)
        self.worker.timer.timeout.connect(self.worker.update_frame)

        # Vision score signal
        self.worker.vision_score_ready.connect(self.handle_vision_score, Qt.QueuedConnection)

        # Connect buttons
        self.reload_btn.clicked.connect(self.reload_stream)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.minimize_btn.clicked.connect(self.toggle_minimize)

        # Start thread
        self.worker_thread.started.connect(self.worker.start_stream)
        self.worker_thread.start()

    def handle_vision_score(self, score):
        """Forward vision score to main window for fusion."""
        # Find main window and call fusion handler
        mw = self.window()
        if hasattr(mw, 'handle_vision_score_from_widget'):
            mw.handle_vision_score_from_widget(self.loc_id, score)

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
            
            # Set base video frame
            self.video_label.setPixmap(scaled_video)
            
            # Apply thermal grid overlay and fusion data
            if (self.thermal_grid_enabled and self.hot_cells_history) or (self.show_fusion_overlay and self.fusion_data):
                self._redraw_with_grid()
            
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
            # Update temperature if available
            if 'temperature' in data:
                self.set_temperature(data['temperature'])
            elif 'matrix' in data:
                # Calculate max temperature from thermal matrix
                import numpy as np
                matrix = np.array(data['matrix'])
                max_temp = matrix.max()
                # Convert 0-255 scale to Celsius (approximate)
                temp_c = max_temp * 100 / 255
                self.set_temperature(temp_c)
            
            # Update fire alarm if available
            if 'fire_alarm' in data:
                self.update_fire_alarm(data['fire_alarm'])


    def update_fire_alarm(self, alarm_active):
        """Update fire alarm indicator"""
        self.alarm_active = alarm_active  # Store alarm state
        color = "red" if alarm_active else "#444"
        self.fire_alarm_status.setStyleSheet(f"""
            background-color: {color};
            border-radius: 10px;
            border: 2px solid {'#fff' if alarm_active else '#666'};
        """)

    def set_fusion_data(self, fusion_data):
        """Set fusion data for overlay display."""
        self.fusion_data = fusion_data
        # Trigger redraw if we have a current frame
        if self.video_label.pixmap() and not self.video_label.pixmap().isNull():
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
                temp_c = self.fusion_data['thermal_max'] * 100 / 255  # Convert to Celsius
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
        self.temp_label.setText(f"Temp: {temp:.1f}°C")
        # Add color coding based on temperature
        if temp > 40:
            self.temp_label.setStyleSheet("color: red;")
        elif temp > 30:
            self.temp_label.setStyleSheet("color: orange;")
        else:
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
        self.worker.stop_stream()
        self.worker_thread.quit()
        self.worker_thread.wait(1000)
        self.init_worker()

    def stop(self):
        """Safe thread cleanup"""
        try:
            if self.worker_thread.isRunning():
                self.worker.stop_stream()
                self.worker_thread.quit()
                self.worker_thread.wait(2000)
                if self.worker_thread.isRunning():
                    self.worker_thread.terminate()
        except Exception as e:
            print(f"Stop error: {str(e)}")

    def deleteLater(self):
        """Safe cleanup with thread management"""
        try:
            # Stop worker first
            if self.worker_thread.isRunning():
                self.worker.stop_stream()
                self.worker_thread.quit()
                self.worker_thread.wait(2000)
                
            # Then delete
            super().deleteLater()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                pass  # Already deleted
            else:
                raise
