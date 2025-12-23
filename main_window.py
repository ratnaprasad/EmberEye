import os
import time
import shutil
import numpy as np
import websockets
import json
import asyncio
import cv2
from typing import List
from pathlib import Path
from threading import Thread, Event
from stream_config import StreamConfig
from resource_helper import get_resource_path, get_data_path, ensure_runtime_folders
from tcp_server_logger import log_info as log_server_info, log_error as log_server_error
from debug_config import debug_print, is_debug_enabled, set_debug_enabled
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTabWidget, QMessageBox,
                             QToolButton, QMenu, QStyle, QFileDialog, QGridLayout, QPushButton, QDialog, QLineEdit,
                             QListWidget, QListWidgetItem, QProgressBar, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem, QSlider, QGroupBox, QCompleter,
                             QCheckBox, QDoubleSpinBox, QFormLayout, QInputDialog
                             )
from PyQt5.QtCore import (
    Qt, pyqtSignal, QMutex, QObject, QTimer, QUrl, QThread
)
from PyQt5.QtGui import (
    QPixmap, QImage
)
# Optional import: QWebEngineView may not be available in minimal builds
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:
    HAS_WEBENGINE = False
from datetime import datetime
from streamconfig_dialog import StreamConfigDialog
from video_widget import VideoWidget
from sensor_fusion import SensorFusion
from baseline_manager import BaselineManager
from pfds_manager import PFDSManager, is_valid_ip
from master_class_config import load_master_classes, flatten_classes
from master_class_config_dialog import MasterClassConfigDialog
# Thermal vision and anomalies modules
from anomalies import (
    ThermalROIExtractor,
    AnomalyRecord,
    AnomaliesManager,
    ThermalVisionAnalyzer,
    YOLOTrainer,
    YOLOTrainingProgress
)

# Global callback wrapper for TCP packets - persists across MainWindow instances
class GlobalTCPCallbackWrapper:
    """Wrapper that allows safe callback updates when MainWindow instances change."""
    def __init__(self):
        self.callback = None
        self.lock = QMutex()
    
    def set_callback(self, callback):
        """Update the callback (thread-safe)."""
        self.lock.lock()
        try:
            self.callback = callback
        finally:
            self.lock.unlock()
    
    def __call__(self, packet):
        """Call the current callback if it exists (thread-safe)."""
        self.lock.lock()
        try:
            callback = self.callback
        finally:
            self.lock.unlock()
        
        if callback:
            try:
                callback(packet)
            except Exception as e:
                print(f"TCP callback error: {e}")

# Single global instance
_global_tcp_callback = GlobalTCPCallbackWrapper()

# bem_main_window.py
class WebSocketClient(QObject):
    data_received = pyqtSignal(dict)
    
    def __init__(self, theme_manager=None):
        super().__init__()
        # Optional theme manager support for Modern/Classic themes
        self.theme_manager = theme_manager
        try:
            if self.theme_manager is not None:
                from PyQt5.QtWidgets import QApplication
                app = QApplication.instance()
                if app is not None:
                    # Apply the selected theme to the application
                    self.theme_manager.apply_theme(app)
        except Exception as _theme_err:
            print(f"Theme apply error (non-fatal): {_theme_err}")
        self.websocket = None
        self.running = False
        self.loop = None
        self.thread = None
        self.connect_event = Event()
        self.mutex = QMutex()

    def start(self):
        self.running = True
        self.thread = Thread(target=self.run_client, daemon=True)
        self.thread.start()
        # Wait for connection attempt but don't block app startup indefinitely
        self.connect_event.wait(6)  # 6 seconds (5s connect + 1s buffer)

    def run_client(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.client_main())
        finally:
            # Only close loop if it's not running
            if self.loop and not self.loop.is_running():
                try:
                    self.loop.close()
                except Exception as e:
                    print(f"Loop close error in run_client: {e}")

    async def client_main(self):
        uri = "ws://localhost:8765"
        try:
            # Try to connect with timeout - don't block app if server unavailable
            async with asyncio.timeout(5):  # 5 second connection timeout
                async with websockets.connect(uri) as ws:
                    self.mutex.lock()
                    self.websocket = ws
                    self.connect_event.set()
                    self.mutex.unlock()
                    print("WebSocket connected successfully")
                    
                    while self.running:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=1)
                            data = json.loads(message)
                            self.data_received.emit(data)
                        except asyncio.TimeoutError:
                            continue
        except asyncio.TimeoutError:
            print("WebSocket connection timeout - continuing without WebSocket")
            self.connect_event.set()  # Release waiting thread
        except Exception as e:
            print(f"WebSocket error: {str(e)} - continuing without WebSocket")
            self.connect_event.set()  # Release waiting thread
        finally:
            self.connect_event.clear()

    def stop(self):
        """Stop the WebSocket client properly."""
        self.mutex.lock()
        self.running = False
        self.mutex.unlock()
        
        # Close websocket properly in the event loop
        if self.websocket and self.loop:
            try:
                # Schedule the close coroutine in the event loop
                future = asyncio.run_coroutine_threadsafe(self._close_websocket(), self.loop)
                future.result(timeout=2)  # Wait up to 2 seconds
            except Exception as e:
                print(f"WebSocket close error: {e}")
            # Ensure loop is stopped before thread join to avoid 'running loop' close errors
            try:
                if self.loop.is_running():
                    self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception as e:
                print(f"Loop stop error: {e}")
        
        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
    
    async def _close_websocket(self):
        """Async helper to close websocket properly."""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                print(f"WebSocket close exception: {e}")

class BEMainWindow(QMainWindow):
    # Signal used to marshal TCP packets from background threads to the GUI thread
    tcp_packet_signal = pyqtSignal(dict)
    # Signal for thermal vision training progress updates
    training_progress_updated = pyqtSignal(dict)  # Emits YOLOTrainingProgress.to_dict()

    # --- Safe fallbacks for runtime-missing handlers ---
    def _fallback_group_changed(self, group):
        try:
            # Minimal behavior: update current group and redraw grid
            self.current_group = group
            self.current_rtsp_page = 1
            if hasattr(self, 'schedule_grid_rebuild'):
                self.schedule_grid_rebuild()
            elif hasattr(self, 'update_rtsp_grid'):
                self.update_rtsp_grid()
        except Exception as e:
            print(f"group_changed fallback error: {e}")

    def _fallback_dispatch_pfds_command(self, cmd: dict) -> bool:
        try:
            ip = cmd.get('ip')
            name = cmd.get('name') or ''
            command = cmd.get('command')
            print(f"PFDS dispatcher missing; cannot send '{command}' to {ip} ({name})")
        except Exception:
            pass
        return False

    def _fallback_update_rtsp_grid(self):
        try:
            print("update_rtsp_grid missing; skipping grid rebuild")
        except Exception:
            pass

    def _fallback_handle_sensor_data(self, data):
        try:
            print(f"handle_sensor_data missing; dropping packet: {data}")
        except Exception:
            pass

    def _fallback_init_header_actions(self, header_layout):
        try:
            spacer = QWidget()
            header_layout.addWidget(spacer)
        except Exception:
            pass

    def _fallback_init_rtsp_tab(self):
        try:
            # Minimal placeholder: create empty tab if tabs exist
            if hasattr(self, 'tabs'):
                from PyQt5.QtWidgets import QWidget
                placeholder = QWidget()
                self.tabs.addTab(placeholder, "VIDEOWALL")
        except Exception:
            pass

    def _fallback_init_tcp_status_indicator(self):
        try:
            # Minimal no-op to satisfy callers; optionally set a default status text
            if hasattr(self, 'statusBar'):
                try:
                    self.statusBar().showMessage("TCP: status unavailable (fallback)")
                except Exception:
                    pass
        except Exception:
            pass

    def _fallback_update_tcp_status(self, is_running, message):
        try:
            # Fallback: just print or update status bar text if available
            if hasattr(self, 'statusBar'):
                try:
                    self.statusBar().showMessage(message)
                except Exception:
                    pass
            else:
                print(message)
        except Exception:
            pass

    def __getattr__(self, name):
        """Provide safe fallbacks for expected handlers if they are missing at runtime."""
        if name == 'update_rtsp_grid':
            return self._fallback_update_rtsp_grid
        if name == 'handle_sensor_data':
            return self._fallback_handle_sensor_data
        if name == 'group_changed':
            return self._fallback_group_changed
        if name == 'dispatch_pfds_command':
            return self._fallback_dispatch_pfds_command
        if name == 'init_header_actions':
            return self._fallback_init_header_actions
        if name == 'init_rtsp_tab':
            return self._fallback_init_rtsp_tab
        if name == 'init_tcp_status_indicator':
            return self._fallback_init_tcp_status_indicator
        if name == 'update_tcp_status':
            return self._fallback_update_tcp_status
        if name == 'tcp_sensor_server' or name == 'ws_client':
            return None  # Return None for missing server instances
        raise AttributeError(f"{self.__class__.__name__!s} object has no attribute {name!s}")
    
    def show_pending_baseline_changes(self):
        """Display notification panel for all pending baseline candidates with thumbnail and timestamp."""
        if not hasattr(self, 'notification_panel'):
            self.notification_panel = QWidget()
            self.notification_layout = QVBoxLayout(self.notification_panel)
            self.notification_panel.setStyleSheet("background-color: #fffbe6; border: 1px solid #e6c200; padding: 8px;")
            self.centralWidget().layout().insertWidget(0, self.notification_panel)
        self.notification_layout.setSpacing(6)
        # Clear previous
        while self.notification_layout.count():
            item = self.notification_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # Add new candidates
        for loc_id, cand in self.baseline_manager.candidates.items():
            # Thumbnail
            import cv2
            from PyQt5.QtGui import QImage, QPixmap
            frame = cand['frame']
            # Convert to RGB if needed
            if len(frame.shape) == 2:
                frame_rgb = cv2.cvtColor(frame.astype('uint8'), cv2.COLOR_GRAY2RGB)
            else:
                frame_rgb = frame.astype('uint8')
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            thumb = QPixmap.fromImage(q_img).scaled(64, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb_label = QLabel()
            thumb_label.setPixmap(thumb)
            # Timestamp
            import datetime
            ts = datetime.datetime.fromtimestamp(cand['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            ts_label = QLabel(f"Detected: {ts}")
            # Approve button
            approve_btn = QPushButton("Approve")
            approve_btn.clicked.connect(lambda checked, lid=loc_id: self.approve_and_refresh(lid))
            # Adaptive feedback placeholder
            feedback_btn = QPushButton("Mark as Nuisance")
            feedback_btn.setEnabled(False)  # Placeholder for future logic
            # Layout
            row = QHBoxLayout()
            row.addWidget(thumb_label)
            row.addWidget(QLabel(f"Pending baseline change for {loc_id}"))
            row.addWidget(ts_label)
            row.addWidget(approve_btn)
            row.addWidget(feedback_btn)
            row_widget = QWidget()
            row_widget.setLayout(row)
            self.notification_layout.addWidget(row_widget)
        if self.baseline_manager.candidates:
            self.notification_panel.show()
        else:
            self.notification_panel.hide()

    def approve_and_refresh(self, loc_id):
        self.approve_baseline_candidate(loc_id)
        self.show_pending_baseline_changes()

    def handle_vision_score_from_widget(self, loc_id, score):
        """Run fusion for this loc_id with vision score and update alarm indicator."""
        # Find widget for loc_id
        for widget in self.get_video_widgets():
            if getattr(widget, 'loc_id', None) == loc_id:
                # Run fusion with only vision score (other sources can be cached for full fusion)
                fusion_result = self.sensor_fusion.fuse(vision_score=score)
                if hasattr(widget, 'update_fire_alarm'):
                    try:
                        widget.update_fire_alarm(fusion_result['alarm'])
                    except Exception as e:
                        print(f"Alarm update error (vision): {e}")
                break

    def apply_sensor_config(self, settings: dict):
        """Apply sensor configuration settings from dialog to runtime objects.
        Expects keys: temp_threshold, gas_ppm_threshold, smoke_threshold_pct, flame_threshold_pct,
        vision_threshold, anomaly settings, etc.
        """
        try:
            # Update SensorFusion thresholds
            if 'temp_threshold' in settings:
                self.sensor_fusion.temp_threshold = float(settings['temp_threshold'])
            if 'gas_ppm_threshold' in settings:
                self.sensor_fusion.gas_ppm_threshold = float(settings['gas_ppm_threshold'])
            if 'smoke_threshold_pct' in settings:
                self.sensor_fusion.smoke_threshold_pct = float(settings['smoke_threshold_pct'])
            if 'flame_threshold_pct' in settings:
                self.sensor_fusion.flame_threshold_pct = float(settings['flame_threshold_pct'])
            # Vision threshold reference
            self.vision_threshold = float(settings.get('vision_threshold', getattr(self, 'vision_threshold', 0.7)))

            # Anomalies settings
            self.anomaly_threshold = float(settings.get('anomaly_threshold', self.anomaly_threshold))
            self._anomaly_max_items = int(settings.get('anomaly_max_items', self._anomaly_max_items))
            self.anomaly_save_enabled = bool(settings.get('anomaly_save_enabled', self.anomaly_save_enabled))
            import os
            self.anomaly_save_dir = settings.get('anomaly_save_dir', self.anomaly_save_dir) or self.anomaly_save_dir
            self.anomaly_retention_days = int(settings.get('anomaly_retention_days', self.anomaly_retention_days))

            # Persist thresholds to stream config
            self.config['smoke_threshold_pct'] = self.sensor_fusion.smoke_threshold_pct
            self.config['flame_threshold_pct'] = self.sensor_fusion.flame_threshold_pct
            self.config['temp_threshold'] = self.sensor_fusion.temp_threshold
            self.config['gas_ppm_threshold'] = self.sensor_fusion.gas_ppm_threshold
            try:
                StreamConfig.save_config(self.config)
            except Exception as e:
                print(f"Config save error: {e}")

            print(f"Applied sensor config & persisted: smoke_threshold={self.sensor_fusion.smoke_threshold_pct}%, flame_threshold={self.sensor_fusion.flame_threshold_pct}%")
        except Exception as e:
            print(f"apply_sensor_config error: {e}")

    def __init__(self, theme_manager=None, tcp_server=None, tcp_sensor_server=None, 
                 pfds=None, async_loop=None, async_thread=None):
        """
        Initialize MainWindow with optional server reuse for efficiency.
        
        Args:
            theme_manager: Theme manager instance
            tcp_server: Existing TCP server to reuse (avoids port conflicts)
            tcp_sensor_server: Alias for tcp_server
            pfds: Existing PFDS manager instance
            async_loop: Shared asyncio event loop
            async_thread: Shared async thread
        """
        super().__init__()
        # Optional theme manager support for Modern/Classic themes
        self.theme_manager = theme_manager
        try:
            if self.theme_manager is not None:
                from PyQt5.QtWidgets import QApplication
                app = QApplication.instance()
                if app is not None:
                    self.theme_manager.apply_theme(app)
        except Exception as _theme_err:
            print(f"Theme apply error (non-fatal): {_theme_err}")
        
        # X-ray Effect: Cursor auto-hide configuration
        self.cursor_hide_seconds = 3  # Hide cursor after 3 seconds of inactivity
        self.cursor_visible = True
        self.cursor_hide_timer = QTimer()
        self.cursor_hide_timer.timeout.connect(self._hide_cursor)
        self.cursor_hide_timer.setSingleShot(True)
        
        # X-ray Effect: Header/status bar auto-hide state
        self.header_visible = True
        self.statusbar_visible = True
        
        self.maximized_widget = None
        self.original_layout = None
        self.original_grid_size = None
        self.config = StreamConfig.load_config()
        self.video_widgets = {}  # loc_id -> VideoWidget
        self.tcp_server = tcp_server  # Reuse existing or create new
        self.tcp_sensor_server = tcp_sensor_server or tcp_server
        self.current_group = "Default"
        self.current_rtsp_page = 1
        self.current_graph_page = 1
        self.grid_rebuild_pending = False  # Track if rebuild is scheduled
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        # Anomalies config defaults
        import os
        self.anomaly_threshold = 0.4
        self.anomaly_save_enabled = False
        self.anomaly_save_dir = os.path.join(os.path.dirname(__file__), 'anomalies')
        self.anomaly_retention_days = 7
        self._last_anomaly_cleanup = 0
        self._anomaly_max_items = 200
        # EEPROM calibration tracking
        self.eeprom_last_update = None  # Track when EEPROM was last fetched
        self.eeprom_offset = 0.0  # Current calibration offset
        
        # Reusable async infrastructure
        self._async_loop = async_loop
        self._async_thread = async_thread
        self._pfds = pfds  # Reuse PFDS manager if provided
        
        # --- Sensor Fusion ---
        # Initialize SensorFusion BEFORE initUI to avoid AttributeError
        smoke_thr = float(self.config.get('smoke_threshold_pct', 25.0))
        flame_thr = float(self.config.get('flame_threshold_pct', 25.0))
        temp_thr = float(self.config.get('temp_threshold', 40.0))
        gas_thr = float(self.config.get('gas_ppm_threshold', 400))
        self.sensor_fusion = SensorFusion(temp_threshold=temp_thr,
                          gas_ppm_threshold=gas_thr,
                          smoke_threshold_pct=smoke_thr,
                          flame_threshold_pct=flame_thr)
        print(f"Loaded fusion thresholds: Smoke={smoke_thr}%, Flame={flame_thr}%, Temp={temp_thr}°C, Gas={gas_thr}ppm")
        self.baseline_manager = BaselineManager()
        self.baseline_manager.load_from_disk()
        
        # --- Gas Sensor ---
        from gas_sensor import MQ135GasSensor
        self.gas_sensor = MQ135GasSensor()
        # TODO: Load R0 calibration from config or calibrate on startup
        
        # Initialize UI after sensor fusion to prevent AttributeError
        self.initUI()
        self.ws_client = WebSocketClient()
        if self.ws_client:
            self.ws_client.data_received.connect(self.handle_sensor_data)
            self.ws_client.start()
        
        # Start TCP sensor server (supports 'threaded' or 'async' via config key 'tcp_mode')
        self.tcp_server = None
        self.tcp_server_port = self.config.get('tcp_port', 9001)
        self.tcp_message_count = 0
        
        # Start Prometheus metrics server
        self.metrics_server = None
        metrics_port = self.config.get('metrics_port', 9090)
        try:
            from metrics import get_metrics, MetricsServer
            self.metrics_server = MetricsServer(get_metrics(), port=metrics_port)
            if self.metrics_server:
                self.metrics_server.start()
                print(f"Metrics endpoint available at http://0.0.0.0:{metrics_port}/metrics")
        except Exception as e:
            print(f"Metrics server start failed: {e}")
        
        # PFDS manager + scheduler (reuse if provided)
        if self._pfds is not None:
            self.pfds = self._pfds
            print("Reusing existing PFDS manager")
        else:
            self.pfds = PFDSManager()
            self.pfds.set_dispatcher(self.dispatch_pfds_command)
            self.pfds.start_scheduler()
        
        # Connect TCP packet signal to handler (QueuedConnection ensures execution on GUI thread)
        self.tcp_packet_signal.connect(self.handle_tcp_packet, Qt.QueuedConnection)
        
        # TCP Server initialization (reuse if provided, otherwise create new)
        if self.tcp_server is not None:
            print(f"Reusing existing TCP server on port {self.tcp_server_port}")
            self.update_tcp_status(True, f"TCP Server: Running on port {self.tcp_server_port} (reused)")
        else:
            tcp_mode = self.config.get('tcp_mode', 'threaded')
            try:
                if tcp_mode == 'async':
                    from tcp_async_server import TCPAsyncSensorServer
                    import asyncio, threading
                    # Create dedicated event loop thread if not already present
                    if self._async_loop is None:
                        self._async_loop = asyncio.new_event_loop()
                        def _run_loop(loop):
                            asyncio.set_event_loop(loop)
                            loop.run_forever()
                        self._async_thread = threading.Thread(target=_run_loop, args=(self._async_loop,), daemon=True)
                        self._async_thread.start()
                    self.tcp_server = TCPAsyncSensorServer(port=self.tcp_server_port, packet_callback=self._emit_tcp_packet)
                    self.tcp_sensor_server = self.tcp_server  # Alias for pfds_manager commands
                    if self.tcp_server:
                        asyncio.run_coroutine_threadsafe(self.tcp_server.start(), self._async_loop)
                else:
                    from tcp_sensor_server import TCPSensorServer
                    self.tcp_server = TCPSensorServer(port=self.tcp_server_port, packet_callback=self._emit_tcp_packet)
                    if self.tcp_server:
                        self.tcp_server.start()
                self.update_tcp_status(True, f"TCP Server: Running on port {self.tcp_server_port} ({tcp_mode})")
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                log_server_error(f"TCP server start failed: {e}\n{error_detail}")
                self.update_tcp_status(False, f"TCP Server: Failed to start - {e}")
        
        # Install X-ray effect event filter for global mouse tracking
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                print("✨ X-ray effect event filter installed")
                # Start cursor auto-hide timer
                self.cursor_hide_timer.start(self.cursor_hide_seconds * 1000)
        except Exception as e:
            print(f"Event filter installation error: {e}")
    
    def _emit_tcp_packet(self, packet):
        """Thread-safe wrapper to emit TCP packet signal."""
        try:
            self.tcp_packet_signal.emit(packet)
        except Exception as e:
            print(f"TCP packet signal emit error: {e}")
    def handle_frame_for_baseline(self, loc_id, frame):
        """Send frame to baseline manager, handle candidate changes."""
        candidate = self.baseline_manager.update(loc_id, frame)
        if candidate:
            print(f"Candidate baseline change detected for {loc_id}")
            self.show_pending_baseline_changes()

    def approve_baseline_candidate(self, loc_id):
        """Approve candidate change for loc_id."""
        success = self.baseline_manager.approve_candidate(loc_id)
        if success:
            print(f"Baseline for {loc_id} updated.")
        else:
            print(f"No candidate to approve for {loc_id}.")

    def handle_tcp_packet(self, packet):
        """Route parsed TCP sensor packets to sensor data handler, overlay, and fusion."""
        # Increment message counter and update status
        self.tcp_message_count += 1
        self.update_tcp_status(True, f"TCP Server: Running on port {self.tcp_server_port} | Messages: {self.tcp_message_count}")
        
        if isinstance(packet, dict):
            fusion_args = {}
            loc_id = packet.get('loc_id')  # Extract loc_id from packet
            
            # Handle EEPROM calibration packets
            if packet.get('type') == 'eeprom':
                from datetime import datetime
                self.eeprom_last_update = datetime.now()
                self.eeprom_offset = packet.get('offset', 0.0)
                print(f"✅ EEPROM1 CALIBRATION RECEIVED:")
                print(f"   ├─ Device: {loc_id or packet.get('client_ip')}")
                print(f"   ├─ Frame ID: {packet.get('frame_id')}")
                print(f"   ├─ Blocks: {packet.get('blocks')}")
                print(f"   ├─ Offset: {self.eeprom_offset:.2f}°C")
                print(f"   ├─ Timestamp: {self.eeprom_last_update.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   └─ Next update: In ~1 hour")
                return
            
            # Overlay for #frame packets
            if packet.get('type') == 'frame':
                fusion_args['thermal_matrix'] = packet['matrix']
                # Route to specific widget by loc_id, or broadcast to all
                target_widgets = [self.video_widgets.get(loc_id)] if loc_id and loc_id in self.video_widgets else self.get_video_widgets()
                for widget in target_widgets:
                    if widget and hasattr(widget, 'set_thermal_overlay'):
                        try:
                            widget.set_thermal_overlay(packet['matrix'])
                        except Exception as e:
                            print(f"Overlay error: {e}")
            elif packet.get('type') == 'sensor':
                # Store raw sensor values
                adc1 = packet.get('ADC1')
                adc2 = packet.get('ADC2')
                mpy30 = packet.get('MPY30')
                
                # ADC1 = Smoke Sensor (MQ-2/MQ-135) - 12-bit ADC (0-4095)
                if adc1:
                    try:
                        # Calculate smoke percentage: (adc1 * 100) / 4095
                        smoke_pct = (adc1 * 100.0) / 4095.0
                        fusion_args['adc1_raw'] = adc1
                        fusion_args['smoke_pct'] = smoke_pct
                        fusion_args['smoke_level'] = smoke_pct
                        print(f"Smoke (ADC1): {adc1} -> {smoke_pct:.1f}%")
                    except Exception as e:
                        print(f"Smoke calculation error: {e}")
                
                # ADC2 = Flame Sensor (Analog) - 12-bit ADC (0-4095)
                if adc2:
                    try:
                        # Calculate flame percentage: (adc2 * 100) / 4095
                        flame_pct = (adc2 * 100.0) / 4095.0
                        fusion_args['adc2_raw'] = adc2
                        fusion_args['flame_analog_pct'] = flame_pct
                        print(f"Flame (ADC2): {adc2} -> {flame_pct:.1f}%")
                    except Exception as e:
                        print(f"Flame ADC2 calculation error: {e}")
                
                # Digital Flame sensor (DI/MPY30)
                fusion_args['flame_digital'] = mpy30
                if mpy30 is not None:
                    fusion_args['flame_digital_raw'] = mpy30
                    print(f"Flame Digital (DI): {mpy30} -> {'DETECTED' if mpy30 == 1 else 'Clear'}")
            elif packet.get('type') == 'locid':
                # Store loc_id mapping for future reference
                print(f"Sensor registered for loc_id: {packet.get('loc_id')}")
                return
            
            # Run fusion if any relevant data
            if fusion_args:
                fusion_result = self.sensor_fusion.fuse(**fusion_args)
                
                # Update alarm status and hot cells on target widget(s)
                target_widgets = [self.video_widgets.get(loc_id)] if loc_id and loc_id in self.video_widgets else self.get_video_widgets()
                for widget in target_widgets:
                    if widget:
                        # Update fire alarm status
                        if hasattr(widget, 'update_fire_alarm'):
                            try:
                                widget.update_fire_alarm(fusion_result['alarm'])
                            except Exception as e:
                                print(f"Alarm update error: {e}")
                        
                        # Update thermal grid overlay with hot cells
                        if hasattr(widget, 'set_hot_cells') and 'hot_cells' in fusion_result:
                            try:
                                widget.set_hot_cells(fusion_result['hot_cells'])
                            except Exception as e:
                                print(f"Hot cells update error: {e}")
                        
                        # Update fusion data overlay
                        if hasattr(widget, 'set_fusion_data'):
                            try:
                                widget.set_fusion_data(fusion_result)
                            except Exception as e:
                                print(f"Fusion data update error: {e}")
            
            # Forward other packets to sensor handler
            self.handle_sensor_data(packet)

    def initUI(self):
        try:
            # Suppress Qt warnings during UI initialization
            import warnings
            import os
            os.environ['QT_LOGGING_RULES'] = '*=false'
            warnings.filterwarnings('ignore')
            
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            # Force modern layout to match expected UI (compact header with gear/profile)
            is_modern = True
            
            self.setWindowTitle("Ember Eye Command Center" if is_modern else "Main")
            self.setGeometry(100, 100, 1024, 768)
            if is_modern:
                self.showMaximized()
            
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)
            
            # Compact Modern Header (50px) as Transparent Overlay or Classic Title Bar
            if is_modern:
                header = QWidget()
                header.setStyleSheet("""
                    QWidget {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(26, 26, 26, 200), stop:0.5 rgba(37, 37, 37, 200), stop:1 rgba(26, 26, 26, 200));
                    }
                """)
                header.setFixedHeight(50)
                # Pin UI visible by default to ensure controls are accessible
                try:
                    self._pin_ui_visible = True
                except Exception:
                    self._pin_ui_visible = True
                if self._pin_ui_visible:
                    header.show()
                else:
                    header.hide()
                self.overlay_header = header
                self.header_hide_timer = None
                
                header_layout = QHBoxLayout(header)
                header_layout.setContentsMargins(15, 8, 15, 8)
                header_layout.setSpacing(12)
                
                # Logo + Brand (compact) - LEFT SIDE
                if hasattr(self, 'init_logo_compact') and callable(getattr(self, 'init_logo_compact')):
                    self.init_logo_compact(header_layout)
                else:
                    # Fallback: minimal brand if compact logo method unavailable
                    logo_container = QWidget()
                    lc = QHBoxLayout(logo_container)
                    lc.setContentsMargins(0, 0, 0, 0)
                    lc.setSpacing(8)
                    brand = QLabel("EMBER EYE")
                    brand.setStyleSheet("""
                        font-size: 14px;
                        font-weight: 700;
                        color: #00bcd4;
                        letter-spacing: 2px;
                        background: transparent;
                    """)
                    lc.addWidget(brand)
                    header_layout.addWidget(logo_container)
                
                # Group dropdown (without label)
                self.group_combo = QComboBox()
                self.group_combo.addItems(self.config["groups"])
                # Guard: connect to fallback if handler missing
                handler = getattr(self, 'group_changed', None)
                self.group_combo.currentTextChanged.connect(handler or self._fallback_group_changed)
                self.group_combo.setFixedWidth(140)
                self.group_combo.setStyleSheet("""
                    QComboBox {
                        background-color: #2d2d2d;
                        color: #e0e0e0;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 10px;
                        font-weight: 600;
                        font-size: 12px;
                    }
                    QComboBox:hover {
                        background-color: #353535;
                    }
                """)
                header_layout.addWidget(self.group_combo)
                
                # Grid size dropdown (without label)
                self.grid_size = QComboBox()
                self.grid_size.addItems(["2×2", "3×3", "4×4", "5×5"])
                self.grid_size.currentIndexChanged.connect(self.update_rtsp_grid)
                self.grid_size.setFixedWidth(90)
                self.grid_size.setStyleSheet("""
                    QComboBox {
                        background-color: #2d2d2d;
                        color: #e0e0e0;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 10px;
                        font-weight: 600;
                        font-size: 12px;
                    }
                    QComboBox:hover {
                        background-color: #353535;
                    }
                """)
                header_layout.addWidget(self.grid_size)
                
                header_layout.addStretch()
                
                # Settings and Profile icons - RIGHT SIDE (guarded)
                header_actions = getattr(self, 'init_header_actions', None) or self._fallback_init_header_actions
                header_actions(header_layout)
                
                main_layout.addWidget(header)
                
                # Enable mouse tracking for hover detection
                self.setMouseTracking(True)
            else:
                # Classic Title Bar
                title_bar = QHBoxLayout()
                self.init_logo(title_bar)
                
                self.group_combo = QComboBox()
                self.group_combo.addItems(self.config["groups"])
                self.group_combo.currentTextChanged.connect(self.group_changed)
                title_bar.addWidget(self.group_combo)
                
                # Grid size for classic mode
                self.grid_size = QComboBox()
                self.grid_size.addItems(["2x2", "3x3", "4x4"])
                self.grid_size.currentIndexChanged.connect(self.update_rtsp_grid)
                title_bar.addWidget(QLabel("Grid:"))
                title_bar.addWidget(self.grid_size)
                
                title_bar.addStretch()
                self.init_settings_menu(title_bar)
                main_layout.addLayout(title_bar)
            
            # Tab Widget with centered tabs
            self.tabs = QTabWidget()
            if is_modern:
                self.tabs.setDocumentMode(True)
                self.tabs.setStyleSheet("""
                    QTabWidget::pane {
                        border: none;
                        background: #1a1a1a;
                    }
                    QTabBar {
                        background: #1a1a1a;
                        alignment: center;
                    }
                    QTabBar::tab {
                        background: #252525;
                        color: #9e9e9e;
                        padding: 12px 40px;
                        margin: 0px 4px;
                        border: none;
                        border-top: 3px solid transparent;
                        font-weight: 600;
                        font-size: 12px;
                        letter-spacing: 2px;
                        min-width: 140px;
                    }
                    QTabBar::tab:selected {
                        background: #1a1a1a;
                        color: #00bcd4;
                        border-top-color: #00bcd4;
                    }
                    QTabBar::tab:hover:!selected {
                        background: #2d2d2d;
                        color: #b0b0b0;
                    }
                """)
                # Set tab bar to not expand and center align
                from PyQt5.QtCore import Qt
                tab_bar = self.tabs.tabBar()
                tab_bar.setExpanding(False)
                tab_bar.setDrawBase(False)
            else:
                # Tab styling for classic mode
                pass
            
            main_layout.addWidget(self.tabs)
            
            self.init_rtsp_tab()
            # Conditionally initialize Grafana metrics tab if enabled in config
            if self.config.get('enable_grafana', False):
                self.init_grafana_tab()
            # Always initialize Anomalies tab
            self.init_anomalies_tab()
            # Initialize Training Manager tab
            self.init_training_manager_tab()
            # Initialize Failed Devices tab if available
            if hasattr(self, 'device_status_manager'):
                try:
                    from failed_devices_tab import FailedDevicesTab
                    self.failed_devices_tab = FailedDevicesTab(self.device_status_manager, parent=self)
                    self.tabs.addTab(self.failed_devices_tab, "DEVICES")
                except Exception as e:
                    print(f"Failed Devices tab init error: {e}")
            
            # Modern status bar
            if is_modern:
                status_bar = self.statusBar()
                status_bar.setStyleSheet("""
                    QStatusBar {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #1a1a1a, stop:0.5 #252525, stop:1 #1a1a1a);
                        color: #00bcd4;
                        border-top: 1px solid #00bcd4;
                        font-weight: 600;
                        font-size: 10px;
                    }
                """)
            
            # Initialize TCP status indicator
            self.init_tcp_status_indicator()
            self.statusBar().showMessage("System Ready")
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Initialization failed: {str(e)}")

    def init_anomalies_tab(self):
        """Create an Anomalies tab showing captured frames as thumbnails."""
        from PyQt5.QtWidgets import QListWidget, QListWidgetItem
        from PyQt5.QtCore import QSize
        anomalies_tab = QWidget()
        layout = QVBoxLayout(anomalies_tab)
        # Controls row
        controls = QHBoxLayout()
        self.anomaly_count_label = QLabel("Captured: 0")
        # Toggle capture button
        self.anomaly_capture_btn = QPushButton("⏸ Pause Capture")
        self.anomaly_capture_btn.setCheckable(True)
        self.anomaly_capture_enabled = True
        def toggle_capture():
            self.anomaly_capture_enabled = not self.anomaly_capture_btn.isChecked()
            self.anomaly_capture_btn.setText("▶ Resume Capture" if self.anomaly_capture_btn.isChecked() else "⏸ Pause Capture")
            print(f"Anomaly capture {'enabled' if self.anomaly_capture_enabled else 'disabled'}")
        self.anomaly_capture_btn.clicked.connect(toggle_capture)
        clear_btn = QPushButton("Clear All")
        open_btn = QPushButton("Open Folder")
        controls.addWidget(self.anomaly_count_label)
        controls.addStretch()
        controls.addWidget(self.anomaly_capture_btn)
        controls.addWidget(open_btn)
        controls.addWidget(clear_btn)
        layout.addLayout(controls)
        # Thumbnails list
        self.anomaly_list = QListWidget()
        self.anomaly_list.setViewMode(self.anomaly_list.IconMode)
        self.anomaly_list.setIconSize(QSize(160, 120))
        self.anomaly_list.setResizeMode(self.anomaly_list.Adjust)
        self.anomaly_list.setSpacing(10)
        layout.addWidget(self.anomaly_list)

        # Storage for full images and metadata
        self._anomalies_store = []  # list of dicts {pixmap, loc_id, score, ts}
        if not hasattr(self, '_anomaly_max_items'):
            self._anomaly_max_items = 200

        def on_clear():
            self._anomalies_store.clear()
            self.anomaly_list.clear()
            self._update_anomaly_count()
        clear_btn.clicked.connect(on_clear)

        def on_open_folder():
            try:
                from PyQt5.QtGui import QDesktopServices
                from PyQt5.QtCore import QUrl
                import os
                path = getattr(self, 'anomaly_save_dir', '')
                if not path:
                    path = os.path.join(os.path.dirname(__file__), 'anomalies')
                os.makedirs(path, exist_ok=True)
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except Exception as e:
                print(f"Open folder error: {e}")
        open_btn.clicked.connect(on_open_folder)

        def on_open_preview(item):
            try:
                idx = item.data(Qt.UserRole)
                if idx is None or idx < 0 or idx >= len(self._anomalies_store):
                    return
                entry = self._anomalies_store[idx]
                # Show simple preview dialog
                dlg = QDialog(self)
                dlg.setWindowTitle(f"Anomaly • {entry['loc_id']} • {entry['score']:.2f}")
                v = QVBoxLayout(dlg)
                lbl = QLabel()
                lbl.setPixmap(entry['pixmap'].scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                v.addWidget(lbl)
                btn = QPushButton("Close")
                btn.clicked.connect(dlg.accept)
                v.addWidget(btn)
                dlg.resize(820, 640)
                dlg.exec_()
            except Exception as e:
                print(f"Anomaly preview error: {e}")
        self.anomaly_list.itemDoubleClicked.connect(on_open_preview)

        # Determine tab label based on theme
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
        self.tabs.addTab(anomalies_tab, "ANOMALIES" if is_modern else "Anomalies")

    def init_training_manager_tab(self):
        """Create Training Manager tab for YOLO model training."""
        from PyQt5.QtWidgets import (QFileDialog, QProgressBar, QSpinBox, QCheckBox, 
                                     QDateEdit, QTextEdit, QPushButton)
        from PyQt5.QtCore import QDate
        
        training_tab = QWidget()
        main_layout = QVBoxLayout(training_tab)
        
        # Header with training stats
        header_layout = QHBoxLayout()
        self.training_completed_label = QLabel("Completed Training: 0")
        self.training_active_label = QLabel("Training: 0")
        header_layout.addWidget(self.training_completed_label)
        header_layout.addWidget(self.training_active_label)
        header_layout.addStretch(1)
        main_layout.addLayout(header_layout)
        
        # Sub-tabs: Training and Sandbox
        training_subtabs = QTabWidget()
        
        # --- Training Sub-tab ---
        training_widget = QWidget()
        training_layout = QHBoxLayout(training_widget)
        
        # Left panel: Class selection and data management
        left_panel = QVBoxLayout()
        
        class_layout = QHBoxLayout()
        class_layout.addWidget(QLabel("Class"))
        self.training_class_combo = QComboBox()
        self.training_class_combo.setMinimumWidth(300)
        self.training_class_combo.setEditable(True)
        self.training_class_combo.setInsertPolicy(QComboBox.NoInsert)
        # Populate from master classes using hierarchical labels: root → category → class
        try:
            from master_class_config import get_hierarchical_class_labels
            self.training_classes = get_hierarchical_class_labels()
            self.training_class_combo.addItems(self.training_classes)
            # Add search filter with QCompleter
            completer = QCompleter(self.training_classes)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self.training_class_combo.setCompleter(completer)
        except Exception:
            pass
        class_layout.addWidget(self.training_class_combo)
        class_layout.addStretch(1)
        left_panel.addLayout(class_layout)
        
        # Import and Annotate buttons
        btn_layout = QHBoxLayout()
        import_btn = QPushButton("Import Video → Training")
        self.import_training_btn = import_btn
        import_btn.clicked.connect(self.import_training_video)
        btn_layout.addWidget(import_btn)
        
        annotate_btn = QPushButton("📹 Annotate Video")
        self.annotate_btn = annotate_btn
        annotate_btn.clicked.connect(self.open_annotation_tool)
        btn_layout.addWidget(annotate_btn)
        btn_layout.addStretch(1)
        left_panel.addLayout(btn_layout)
        
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
        self.training_ready_label = QLabel("📦 Ready for Training")
        self.training_ready_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4; border: none; background: transparent;")
        training_ready_layout.addWidget(self.training_ready_label)
        
        self.training_ready_count_label = QLabel("0 annotation files")
        self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; border: none; background: transparent;")
        training_ready_layout.addWidget(self.training_ready_count_label)
        
        left_panel.addWidget(training_ready_group)

        # Track if training just completed (to prevent refresh from resetting display)
        self.training_just_completed = False

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
        
        # Move to Training and Delete buttons
        action_btn_layout = QHBoxLayout()
        move_btn = QPushButton("→ Move to Training")
        move_btn.clicked.connect(self.move_to_training)
        action_btn_layout.addWidget(move_btn)
        
        delete_btn = QPushButton("🗑 Delete")
        delete_btn.clicked.connect(self.delete_training_data)
        action_btn_layout.addWidget(delete_btn)
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
        rollback_btn = QPushButton("↶ Rollback to Selected")
        rollback_btn.clicked.connect(self.rollback_model_version)
        version_btn_layout.addWidget(rollback_btn)
        
        delete_version_btn = QPushButton("🗑 Delete Version")
        delete_version_btn.clicked.connect(self.delete_model_version)
        version_btn_layout.addWidget(delete_version_btn)
        version_btn_layout.addStretch(1)
        right_panel.addLayout(version_btn_layout)
        
        right_panel.addStretch(1)
        training_layout.addLayout(right_panel, 1)
        # Initial refresh of dataset stats
        try:
            self._refresh_dataset_stats()
        except Exception:
            pass
        
        # Populate versions on load
        self._refresh_model_versions()
        
        training_subtabs.addTab(training_widget, "Training")
        
        # --- Sandbox Sub-tab ---
        sandbox_widget = self._create_sandbox_tab()
        training_subtabs.addTab(sandbox_widget, "Sandbox")
        
        main_layout.addWidget(training_subtabs)
        
        # Determine tab label based on theme
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
        self.tabs.addTab(training_tab, "TRAINING" if is_modern else "Training")
        
        # Store reference
        self.training_manager_tab = training_tab
        self._training_video_path = None
        self.training_selected_video_path = None
        self.training_has_annotations = False
        
        # Initial count update
        self._refresh_training_ready_count()

    # Training Manager methods
    def import_training_video(self):
        """Import or register a training video.

        If annotations already exist for the selected video, we skip re-import
        and treat it as an "Add existing annotated frames" operation.
        """
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Training Video", "", "Videos (*.mp4 *.avi *.mov)")
        if file_path:
            # Store for annotation tool use
            self.training_selected_video_path = file_path
            annotations_dir = self._annotations_dir_for_video(file_path)
            has_ann = self._has_annotations(annotations_dir)
            self.training_has_annotations = has_ann

            if has_ann:
                # Switch button label to reflect we're registering existing annotations
                if hasattr(self, 'import_training_btn'):
                    self.import_training_btn.setText("Register Annotated Frames")
                QMessageBox.information(
                    self,
                    "Annotations Found",
                    f"Annotations already exist for this video.\n\n"
                    f"Video: {file_path}\n"
                    f"Annotations folder: {annotations_dir}\n\n"
                    "You can now add them directly to the training set or open the annotation tool to review."
                )
                # Update status label if available
                if hasattr(self, 'training_status_label'):
                    self.training_status_label.setText("Ready: annotated frames detected")
            else:
                if hasattr(self, 'import_training_btn'):
                    self.import_training_btn.setText("Import Video → Training")
                QMessageBox.information(
                    self,
                    "Import",
                    f"Video imported:\n{file_path}\n\nClick 'Annotate Video' to label frames."
                )
                if hasattr(self, 'training_status_label'):
                    self.training_status_label.setText("Ready: import complete, needs annotation")
    
    def open_annotation_tool(self):
        """Open annotation tool for labeling frames."""
        try:
            # Build class label sets
            from master_class_config import get_hierarchical_class_labels, load_master_classes
            classes = load_master_classes()
            hierarchical = get_hierarchical_class_labels()
            leaf_classes = []
            # Collect leaf class names from categories
            for category in classes.get("IncidentEnvironment", []) or []:
                for leaf in classes.get(category, []) or []:
                    leaf_classes.append(leaf)

            from annotation_tool import AnnotationToolDialog
            video_path = getattr(self, 'training_selected_video_path', None)
            print(f"[DEBUG] Opening annotation tool with video_path: {video_path}")
            if not video_path:
                QMessageBox.warning(self, "Annotation", "Please import a video first.")
                return
            dlg = AnnotationToolDialog(self, video_path=video_path, class_labels=hierarchical, leaf_classes=leaf_classes)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Annotation", f"Failed to open annotation tool: {e}")
    
    def move_to_training(self):
        """Register annotated frames into training_data/annotations for training."""
        if not getattr(self, 'training_selected_video_path', None):
            QMessageBox.warning(self, "Training", "Select or import a video first.")
            return
        annotations_dir = self._annotations_dir_for_video(self.training_selected_video_path)
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
            QMessageBox.information(
                self,
                "Training",
                f"Registered annotated frames for training.\n"
                f"Annotations: {ann_count} files\n"
                f"Copied to: {target_dir}"
            )
        else:
            QMessageBox.warning(self, "Training", "Failed to copy annotations to training_data.")
            QMessageBox.warning(self, "Training", "Failed to copy annotations to training_data.")

    def delete_training_data(self):
        """Delete selected training data."""
        reply = QMessageBox.question(self, "Delete", "Delete selected training data?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            QMessageBox.information(self, "Delete", "Training data deleted.")

    def start_model_training(self):
        """Start YOLO model training using training_pipeline."""
        training_ann_base = get_data_path(os.path.join("training_data", "annotations"))
        ann_total = self._count_annotation_files(training_ann_base)
        if ann_total == 0:
            QMessageBox.warning(self, "Training", "No annotations found in training_data/annotations. Import/register annotated frames first.")
            return

        from training_pipeline import TrainingConfig
        project_name = f"embereye_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        config = TrainingConfig(
            project_name=project_name,
            epochs=self.epochs_spin.value(),
            batch_size=self.batch_size_spin.value(),
            imgsz=640,
            device="auto",
        )

        self.start_training_btn.setEnabled(False)
        self.cancel_training_btn.setEnabled(False)
        self.training_status_label.setText("Training…")
        self.training_progress.setValue(0)
        self.training_just_completed = False  # Reset completion flag for new training

        self.training_worker = TrainingWorker(config)
        self.training_worker.finished_signal.connect(self._on_training_finished)
        self.training_worker.progress_signal.connect(self._on_training_progress)
        self.training_worker.epoch_progress_signal.connect(self._on_epoch_progress)
        self.training_worker.start()

    def cancel_model_training(self):
        """Cancel ongoing training (not supported in pipeline yet)."""
        QMessageBox.information(self, "Training", "Cancel is not supported in this pipeline yet.")
        self.start_training_btn.setEnabled(True)
        self.cancel_training_btn.setEnabled(False)
    
    def rollback_model_version(self):
        """Rollback/Activate selected model version."""
        selected = self.model_versions_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Select a model version to activate.")
            return
        
        try:
            # Parse version from label (format: "v1 | mAP: 0.8734 | Time: 1.23h" or "✓ v1 ...")
            label_text = selected[0].text()
            version = label_text.split('|')[0].strip().replace('✓', '').strip()
            if '[ACTIVE]' in label_text:
                QMessageBox.information(self, "Activate", f"{version} is already active.")
                return
            
            reply = QMessageBox.question(
                self, "Activate Model",
                f"Activate {version} as the production model?\n\n"
                f"This will update current_best.pt to point to this version.",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                from embereye.core.model_versioning import ModelVersionManager
                manager = ModelVersionManager()
                ok, msg = manager.promote_to_best(version)
                if ok:
                    QMessageBox.information(self, "Success", f"✓ {version} is now active.\n{msg}")
                    self._refresh_model_versions()
                    self._refresh_sandbox_models()  # Update Sandbox dropdown
                else:
                    QMessageBox.warning(self, "Activation Failed", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to activate version: {e}")
    
    def delete_model_version(self):
        """Delete selected model version with safeguards."""
        selected = self.model_versions_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Select a model version to delete.")
            return
        
        try:
            label_text = selected[0].text()
            version = label_text.split('|')[0].strip().replace('✓', '').strip()
            
            if '[ACTIVE]' in label_text:
                QMessageBox.warning(
                    self, "Cannot Delete",
                    f"{version} is the active model.\n\n"
                    f"Activate a different version before deleting this one."
                )
                return
            
            reply = QMessageBox.question(
                self, "Delete Model Version",
                f"Permanently delete {version}?\n\n"
                f"This will remove all weights and cannot be undone.",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                from embereye.core.model_versioning import ModelVersionManager
                manager = ModelVersionManager()
                ok, msg = manager.delete_version(version)
                if ok:
                    QMessageBox.information(self, "Deleted", f"✓ {version} deleted successfully.")
                    self._refresh_model_versions()
                    self._refresh_sandbox_models()  # Update Sandbox dropdown
                else:
                    QMessageBox.warning(self, "Deletion Failed", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete version: {e}")

    # Helpers for training manager
    def _annotations_dir_for_video(self, video_path: str) -> str:
        """Return workspace-relative annotations directory for a video."""
        base = os.path.splitext(os.path.basename(video_path or "video"))[0]
        return get_data_path(os.path.join("annotations", base))

    def _has_annotations(self, annotations_dir: str) -> bool:
        try:
            if not annotations_dir or not os.path.exists(annotations_dir):
                return False
            for fname in os.listdir(annotations_dir):
                if fname.endswith(".txt"):
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
            return 0

    def _create_sandbox_tab(self) -> QWidget:
        """Create sandbox testing UI for model evaluation."""
        from PyQt5.QtWidgets import QScrollArea
        
        # Main container with scroll area
        sandbox_widget = QWidget()
        main_layout = QVBoxLayout(sandbox_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scrollable content area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        sandbox_layout = QVBoxLayout(scroll_content)
        sandbox_layout.setSpacing(5)
        
        # Compact header
        header = QLabel("🧪 Sandbox - Test models safely")
        header.setStyleSheet("font-weight: bold; padding: 5px;")
        sandbox_layout.addWidget(header)
        
        # Horizontal layout for compact space usage
        top_section = QHBoxLayout()
        
        # Model selection (left column)
        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout()
        model_layout.setSpacing(3)
        
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
        
        # Model info display
        self.sandbox_model_info = QLabel("No model")
        self.sandbox_model_info.setStyleSheet("font-size: 10px; color: #666;")
        self.sandbox_model_info.setWordWrap(True)
        model_layout.addWidget(self.sandbox_model_info)

        verify_btn = QPushButton("Verify model")
        verify_btn.setMaximumWidth(120)
        verify_btn.clicked.connect(self._sandbox_verify_model)
        model_layout.addWidget(verify_btn)
        
        # Export/Import buttons
        export_import_layout = QHBoxLayout()
        export_import_layout.setSpacing(5)
        
        export_btn = QPushButton("📦 Export")
        export_btn.setMaximumWidth(120)
        export_btn.clicked.connect(self._sandbox_export_model)
        export_import_layout.addWidget(export_btn)
        
        import_btn = QPushButton("📥 Import")
        import_btn.setMaximumWidth(120)
        import_btn.clicked.connect(self._sandbox_import_model)
        export_import_layout.addWidget(import_btn)
        
        model_layout.addLayout(export_import_layout)
        
        model_group.setLayout(model_layout)
        top_section.addWidget(model_group)
        
        # Inference controls (right column)
        control_group = QGroupBox("Settings")
        control_layout = QVBoxLayout()
        control_layout.setSpacing(3)
        
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Conf:"))
        self.sandbox_conf_spin = QDoubleSpinBox()
        self.sandbox_conf_spin.setRange(0.0, 1.0)
        self.sandbox_conf_spin.setSingleStep(0.05)
        self.sandbox_conf_spin.setValue(0.15)
        self.sandbox_conf_spin.setDecimals(2)
        self.sandbox_conf_spin.setMaximumWidth(70)
        conf_layout.addWidget(self.sandbox_conf_spin)
        control_layout.addLayout(conf_layout)
        
        iou_layout = QHBoxLayout()
        iou_layout.addWidget(QLabel("IoU:"))
        self.sandbox_iou_spin = QDoubleSpinBox()
        self.sandbox_iou_spin.setRange(0.0, 1.0)
        self.sandbox_iou_spin.setSingleStep(0.05)
        self.sandbox_iou_spin.setValue(0.45)
        self.sandbox_iou_spin.setDecimals(2)
        self.sandbox_iou_spin.setMaximumWidth(70)
        iou_layout.addWidget(self.sandbox_iou_spin)
        control_layout.addLayout(iou_layout)
        
        control_group.setLayout(control_layout)
        top_section.addWidget(control_group)
        
        sandbox_layout.addLayout(top_section)

        # --- Compact body: icons left, previews right ---
        body_layout = QHBoxLayout()
        body_layout.setSpacing(8)

        # Left: stacked icon buttons
        icon_column = QVBoxLayout()
        icon_column.setSpacing(6)

        def _make_icon_btn(text, slot, tip):
            btn = QPushButton(text)
            btn.setFixedSize(44, 44)
            btn.setStyleSheet("font-size: 16px;")
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            return btn

        icon_column.addWidget(_make_icon_btn("🖼", self._sandbox_upload_image, "Select image"))
        icon_column.addWidget(_make_icon_btn("🎥", self._sandbox_upload_video, "Select video (first frame)"))
        icon_column.addWidget(_make_icon_btn("📸", self._sandbox_select_annotated_frame, "Pick from annotations"))
        # Keep a reference for external access
        self.sandbox_run_btn = _make_icon_btn("▶", self._sandbox_run_inference, "Run inference")
        icon_column.addWidget(self.sandbox_run_btn)
        icon_column.addStretch(1)
        body_layout.addLayout(icon_column)

        # Right: input + output previews on one line
        previews_column = QVBoxLayout()
        previews_column.setSpacing(6)

        previews_row = QHBoxLayout()
        previews_row.setSpacing(6)

        input_group = QGroupBox("Input")
        input_layout = QVBoxLayout()
        input_layout.setSpacing(3)
        self.sandbox_input_label = QLabel("No input")
        self.sandbox_input_label.setAlignment(Qt.AlignCenter)
        self.sandbox_input_label.setStyleSheet("border: 1px dashed #ccc; background: #f9f9f9;")
        self.sandbox_input_label.setScaledContents(False)
        self.sandbox_input_label.setFixedHeight(350)
        input_layout.addWidget(self.sandbox_input_label)
        input_group.setLayout(input_layout)
        previews_row.addWidget(input_group)

        results_group = QGroupBox("Result")
        results_group.setMaximumWidth(700)
        results_layout = QVBoxLayout()
        results_layout.setSpacing(3)
        self.sandbox_progress = QProgressBar()
        self.sandbox_progress.setVisible(False)
        self.sandbox_progress.setMaximumHeight(16)
        results_layout.addWidget(self.sandbox_progress)
        
        # Horizontal layout for image + stats
        results_inner = QHBoxLayout()
        results_inner.setSpacing(6)
        
        self.sandbox_results_label = QLabel("Results appear here")
        self.sandbox_results_label.setAlignment(Qt.AlignCenter)
        self.sandbox_results_label.setStyleSheet("border: 1px solid #ccc; background: #fff;")
        self.sandbox_results_label.setScaledContents(False)
        self.sandbox_results_label.setFixedHeight(350)
        self.sandbox_results_label.setMaximumWidth(300)
        results_inner.addWidget(self.sandbox_results_label)
        
        # Real-time stats panel
        self.sandbox_stats_panel = QLabel("Waiting for inference...")
        self.sandbox_stats_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.sandbox_stats_panel.setStyleSheet("border: 1px solid #ddd; background: #f5f5f5; padding: 8px; font-family: monospace; font-size: 11px;")
        self.sandbox_stats_panel.setFixedHeight(350)
        self.sandbox_stats_panel.setMaximumWidth(350)
        self.sandbox_stats_panel.setWordWrap(True)
        results_inner.addWidget(self.sandbox_stats_panel)
        
        results_layout.addLayout(results_inner)
        results_group.setLayout(results_layout)
        previews_row.addWidget(results_group)

        previews_column.addLayout(previews_row)

        # Stats and detections below previews
        self.sandbox_stats_label = QLabel("Detections: - | Time: -")
        self.sandbox_stats_label.setStyleSheet("font-size: 10px; font-family: monospace;")
        previews_column.addWidget(self.sandbox_stats_label)
        self.sandbox_detections_list = QListWidget()
        self.sandbox_detections_list.setMaximumHeight(90)
        previews_column.addWidget(self.sandbox_detections_list)

        body_layout.addLayout(previews_column)
        sandbox_layout.addLayout(body_layout)
        
        # Set scroll content
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Initialize with available models
        self._refresh_sandbox_models()
        
        return sandbox_widget
    
    def _refresh_sandbox_models(self):
        """Refresh available model versions in sandbox."""
        try:
            from embereye.core.model_versioning import ModelVersionManager
            version_mgr = ModelVersionManager()
            versions = version_mgr.list_versions()
            
            self.sandbox_model_combo.clear()
            if not versions:
                self.sandbox_model_combo.addItem("No models available")
                self.sandbox_model_info.setText("Train a model first in the Training tab")
                return
            
            for version in reversed(versions):  # Show newest first
                self.sandbox_model_combo.addItem(version)
            
            # Update info for first model
            self._update_sandbox_model_info()
            self.sandbox_model_combo.currentIndexChanged.connect(self._update_sandbox_model_info)
            
        except Exception as e:
            self.sandbox_model_combo.clear()
            self.sandbox_model_combo.addItem("Error loading models")
            self.sandbox_model_info.setText(f"Error: {e}")
    
    def _update_sandbox_model_info(self):
        """Update model info display when selection changes."""
        try:
            version = self.sandbox_model_combo.currentText()
            if not version or version in ["No models available", "Error loading models"]:
                return
            
            from embereye.core.model_versioning import ModelVersionManager
            version_mgr = ModelVersionManager()
            metadata_path = version_mgr.models_dir / version / "metadata.json"
            
            if metadata_path.exists():
                from model_versioning import ModelMetadata
                metadata = ModelMetadata.load(metadata_path)
                info_text = (f"📊 Training Images: {metadata.training_images} | "
                           f"Accuracy: {metadata.best_accuracy:.2%} | "
                           f"Epochs: {metadata.total_epochs} | "
                           f"Time: {metadata.training_time_hours:.1f}h")
                self.sandbox_model_info.setText(info_text)
            else:
                self.sandbox_model_info.setText(f"Model: {version} (metadata not found)")
        except Exception as e:
            self.sandbox_model_info.setText(f"Error: {e}")
    
    def _sandbox_upload_image(self):
        """Upload an image for testing."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Test Image", "", 
            "Image Files (*.jpg *.jpeg *.png *.bmp)"
        )
        if file_path:
            self._load_sandbox_input(file_path)
    
    def _sandbox_upload_video(self):
        """Upload a video for testing (will process multiple frames)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Test Video", "", 
            "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        if file_path:
            # Store video path for frame sampling during inference
            self.sandbox_input_path = file_path
            self.sandbox_is_video = True
            
            # Show preview thumbnail (first frame)
            try:
                cap = cv2.VideoCapture(file_path)
                ret, frame = cap.read()
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
                
                if ret:
                    # Save temp preview
                    temp_path = get_data_path("temp_sandbox_preview.jpg")
                    cv2.imwrite(temp_path, frame)
                    
                    # Display with info about video
                    pixmap = QPixmap(temp_path)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(520, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.sandbox_input_label.setPixmap(scaled)
                        self.sandbox_input_label.setText("")
                    
                    # Update label with video info
                    video_name = os.path.basename(file_path)
                    self.sandbox_model_info.setText(f"Video: {video_name} ({total_frames} frames)")
                else:
                    QMessageBox.warning(self, "Error", "Could not read video")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Video loading error: {e}")

    def _sandbox_verify_model(self):
        """Show quick info about the selected model weights and classes."""
        version = self.sandbox_model_combo.currentText()
        if not version or version in ["No models available", "Error loading models"]:
            QMessageBox.information(self, "Verify Model", "Select a model version first.")
            return
        try:
            from embereye.core.model_versioning import ModelVersionManager
            from ultralytics import YOLO
            mgr = ModelVersionManager()
            weights_dir = mgr.models_dir / version / "weights"
            weight_path = weights_dir / "best.pt"
            if not weight_path.exists():
                alt_path = weights_dir / "EmberEye.pt"
                if alt_path.exists():
                    weight_path = alt_path
                else:
                    QMessageBox.warning(self, "Verify Model", f"Weights not found for {version}")
                    return
            size_mb = weight_path.stat().st_size / (1024 * 1024)
            size_note = "OK" if size_mb >= 7 else "Small (likely base yolov8n, training may not have run)"
            model = YOLO(str(weight_path))
            names = model.names
            if isinstance(names, dict):
                class_list = list(names.values())
            else:
                class_list = names if isinstance(names, list) else []
            msg = (
                f"Version: {version}\n"
                f"Path: {weight_path}\n"
                f"Size: {size_mb:.2f} MB ({size_note})\n"
                f"Classes ({len(class_list)}): {', '.join(class_list) if class_list else 'None'}"
            )
            QMessageBox.information(self, "Verify Model", msg)
        except Exception as e:
            QMessageBox.warning(self, "Verify Model", f"Error: {e}")
    
    def _sandbox_export_model(self):
        """Export current model to deployment format (ONNX, TorchScript, CoreML, TFLite)."""
        version = self.sandbox_model_combo.currentText()
        if not version or version in ["No models available", "Error loading models"]:
            QMessageBox.warning(self, "Export Model", "Select a model version first.")
            return
        
        try:
            from embereye.core.model_versioning import ModelVersionManager
            
            manager = ModelVersionManager()
            best_model_path = manager.get_current_best()
            
            if not best_model_path or not best_model_path.exists():
                QMessageBox.warning(self, "Export Model", f"Model weights not found for {version}")
                return
            
            # Format selection dialog
            formats = ["ONNX (.onnx)", "TorchScript (.pt)", "CoreML (.mlmodel)", "TFLite (.tflite)"]
            format_keys = ["onnx", "torchscript", "coreml", "tflite"]
            
            format_text, ok = QInputDialog.getItem(
                self, "Export Format", "Select export format:", formats, 0, False
            )
            
            if not ok:
                return
            
            fmt = format_keys[formats.index(format_text)]
            
            # File save dialog
            default_name = f"EmberEye_{version}_{fmt}.{format_text.split('.')[-1]}"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Export Model", default_name, 
                f"{format_text} Files (*.{format_text.split('.')[-1]})"
            )
            
            if not save_path:
                return
            
            # Show progress dialog
            progress = QProgressDialog(f"Exporting to {fmt.upper()}...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            QApplication.processEvents()
            
            # Export
            from ultralytics import YOLO
            model = YOLO(str(best_model_path))
            export_path = model.export(format=fmt, imgsz=640)
            
            # Copy to requested location
            import shutil
            shutil.copy(str(export_path), save_path)
            
            progress.close()
            QMessageBox.information(self, "Export Complete", f"✓ Model exported to:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export model:\n{e}")
    
    def _sandbox_import_model(self):
        """Import a model file from development center (maintenance/upgrade scenario)."""
        try:
            # File browser to select model
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Import Model from Development Center",
                "", 
                "Model Files (*.pt *.onnx *.mlmodel *.tflite);;PyTorch (*.pt);;ONNX (*.onnx);;CoreML (*.mlmodel);;TFLite (*.tflite);;All Files (*)"
            )
            
            if not file_path:
                return
            
            # Get version name from user
            version_name, ok = QInputDialog.getText(
                self, "Import Model", 
                "Enter version name (e.g., v4, v4_updated):",
                text="v4"
            )
            
            if not ok or not version_name.strip():
                return
            
            version_name = version_name.strip()
            
            # Create version directory
            from embereye.core.model_versioning import ModelVersionManager, ModelMetadata
            manager = ModelVersionManager()
            version_dir = manager.models_dir / version_name
            weights_dir = version_dir / "weights"
            weights_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy model file
            import shutil
            from pathlib import Path
            source = Path(file_path)
            
            # Determine destination filename
            if source.suffix == ".pt":
                dest_name = "best.pt"
            elif source.suffix == ".onnx":
                dest_name = "model.onnx"
            elif source.suffix == ".mlmodel":
                dest_name = "model.mlmodel"
            elif source.suffix == ".tflite":
                dest_name = "model.tflite"
            else:
                dest_name = source.name
            
            dest_path = weights_dir / dest_name
            shutil.copy(file_path, dest_path)
            
            # Create metadata for imported model
            metadata = ModelMetadata(
                version=version_name,
                timestamp=datetime.utcnow().isoformat(),
                training_images=0,
                new_images=0,
                total_epochs=0,
                best_accuracy=0.0,
                loss=0.0,
                training_time_hours=0.0,
                base_model="imported",
                config_snapshot={},
                previous_version=None,
                notes=f"Imported from {source.name} (from development center)",
                training_strategy="imported",
            )
            
            # Save metadata
            metadata_file = version_dir / "metadata.json"
            import json
            with open(metadata_file, 'w') as f:
                json.dump({
                    'version': metadata.version,
                    'created_at': metadata.timestamp,
                    'best_accuracy': metadata.best_accuracy,
                    'training_time_hours': metadata.training_time_hours,
                    'notes': metadata.notes,
                }, f, indent=2)
            
            # Refresh dropdown
            self._refresh_sandbox_models()
            
            # Select the newly imported version
            for i in range(self.sandbox_model_combo.count()):
                if version_name in self.sandbox_model_combo.itemText(i):
                    self.sandbox_model_combo.setCurrentIndex(i)
                    break
            
            QMessageBox.information(
                self, "Import Complete",
                f"✓ Model imported successfully!\n\n"
                f"Version: {version_name}\n"
                f"Location: {dest_path}\n\n"
                f"The model is now available in the Sandbox dropdown."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import model:\n{e}")
    
    def _sandbox_select_annotated_frame(self):
        """Select a frame from existing annotations."""
        annotations_dir = get_data_path("annotations")
        if not os.path.exists(annotations_dir):
            QMessageBox.information(self, "No Annotations", 
                                   "No annotated frames found. Create annotations first.")
            return
        
        # Find image files
        image_files = []
        for root, dirs, files in os.walk(annotations_dir):
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_files.append(os.path.join(root, f))
        
        if not image_files:
            QMessageBox.information(self, "No Images", "No image files found in annotations")
            return
        
        # Show selection dialog
        from PyQt5.QtWidgets import QInputDialog
        items = [os.path.basename(f) for f in image_files]
        item, ok = QInputDialog.getItem(self, "Select Frame", 
                                       "Choose annotated frame:", items, 0, False)
        if ok and item:
            selected_path = image_files[items.index(item)]
            self._load_sandbox_input(selected_path)
    
    def _load_sandbox_input(self, image_path: str):
        """Load image into sandbox input display."""
        try:
            self.sandbox_input_path = image_path
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                # Scale to fit label constraints (~350px tall)
                scaled = pixmap.scaled(520, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.sandbox_input_label.setPixmap(scaled)
                self.sandbox_input_label.setText("")
            else:
                self.sandbox_input_label.setText("Failed to load")
        except Exception as e:
            self.sandbox_input_label.setText(f"Error: {e}")
    
    def _sandbox_run_inference(self):
        """Run inference on selected image or video with selected model."""
        # Validate inputs
        if not hasattr(self, 'sandbox_input_path') or not os.path.exists(self.sandbox_input_path):
            QMessageBox.warning(self, "No Input", "Please select an input image or video first")
            return
        
        version = self.sandbox_model_combo.currentText()
        if not version or version in ["No models available", "Error loading models"]:
            QMessageBox.warning(self, "No Model", "Please select a valid model version")
            return
        
        # Run inference in background thread
        self.sandbox_run_btn.setEnabled(False)
        self.sandbox_progress.setVisible(True)
        self.sandbox_progress.setRange(0, 0)  # Indeterminate
        
        # Start inference worker
        from PyQt5.QtCore import QThread, pyqtSignal
        
        class InferenceWorker(QThread):
            finished = pyqtSignal(bool, object, str)  # success, results_dict, message
            progress = pyqtSignal(int, int, int, int, str)  # current_frame, total_frames, detections_so_far, elapsed_ms, frame_path
            
            def __init__(self, model_version, input_path, conf, iou, is_video=False):
                super().__init__()
                self.model_version = model_version
                self.input_path = input_path
                self.conf = conf
                self.iou = iou
                self.is_video = is_video
            
            def run(self):
                try:
                    from embereye.core.model_versioning import ModelVersionManager
                    from ultralytics import YOLO
                    import time
                    import cv2
                    
                    # Load model
                    version_mgr = ModelVersionManager()
                    model_path = version_mgr.models_dir / self.model_version / "weights" / "best.pt"
                    
                    if not model_path.exists():
                        self.finished.emit(False, None, f"Model weights not found: {model_path}")
                        return
                    
                    model = YOLO(str(model_path))
                    
                    # Performance tracking
                    perf_metrics = {
                        'model_version': self.model_version,
                        'conf_threshold': self.conf,
                        'iou_threshold': self.iou,
                        'total_inference_time': 0.0,
                        'frame_times': [],
                        'avg_fps': 0.0,
                        'min_fps': 0.0,
                        'max_fps': 0.0,
                        'avg_latency_ms': 0,
                    }
                    
                    if not self.is_video:
                        # Single image inference
                        start_time = time.time()
                        results = model.predict(
                            self.input_path,
                            conf=self.conf,
                            iou=self.iou,
                            verbose=False
                        )
                        inference_time = time.time() - start_time
                        
                        # Performance metrics
                        perf_metrics['total_inference_time'] = inference_time
                        perf_metrics['avg_latency_ms'] = int(inference_time * 1000)
                        perf_metrics['avg_fps'] = 1.0 / inference_time if inference_time > 0 else 0
                        
                        # Parse results
                        if results and len(results) > 0:
                            result = results[0]
                            result_dict = {
                                'inference_time': inference_time,
                                'detections': [],
                                'annotated_image': result.plot(),
                                'frame_count': 1,
                                'total_detections': 0,
                                'performance': perf_metrics
                            }
                            
                            # Extract detections
                            if result.boxes:
                                for box in result.boxes:
                                    det = {
                                        'class_id': int(box.cls[0]),
                                        'class_name': result.names[int(box.cls[0])],
                                        'confidence': float(box.conf[0]),
                                        'bbox': box.xyxy[0].tolist()
                                    }
                                    result_dict['detections'].append(det)
                            
                            result_dict['total_detections'] = len(result_dict['detections'])
                            self.finished.emit(True, result_dict, "Inference completed")
                        else:
                            self.finished.emit(False, None, "No results returned from model")
                    else:
                        # Video inference - process all frames
                        cap = cv2.VideoCapture(self.input_path)
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        
                        # Process all frames
                        sample_indices = list(range(total_frames))
                        
                        # Process sampled frames
                        all_detections = []
                        best_result = None
                        best_frame_img = None
                        max_detections = 0
                        start_time = time.time()
                        processed_frames = 0
                        frame_times = []
                        
                        for frame_idx in sample_indices:
                            try:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                                ret, frame = cap.read()
                                
                                if not ret:
                                    print(f"[Sandbox] Failed to read frame {frame_idx}")
                                    continue
                                
                                # Save temp frame
                                temp_path = get_data_path(f"temp_sandbox_frame_{frame_idx}.jpg")
                                success = cv2.imwrite(temp_path, frame)
                                if not success:
                                    continue
                                
                                # Run inference on this frame with timing
                                frame_start = time.time()
                                results = model.predict(temp_path, conf=self.conf, iou=self.iou, verbose=False)
                                frame_time = time.time() - frame_start
                                frame_times.append(frame_time)
                                
                                processed_frames += 1
                                num_boxes = len(results[0].boxes) if results and results[0].boxes else 0
                                print(f"[Sandbox] Frame {frame_idx}: {num_boxes} detections (conf={self.conf}, {frame_time*1000:.1f}ms)")
                                
                                # Emit progress signal (includes frame preview path)
                                elapsed_ms = int((time.time() - start_time) * 1000)
                                self.progress.emit(processed_frames, total_frames, len(all_detections), elapsed_ms, temp_path)
                                
                                if results and len(results) > 0:
                                    result = results[0]
                                    frame_detections = []
                                    
                                    if result.boxes:
                                        for box in result.boxes:
                                            det = {
                                                'class_id': int(box.cls[0]),
                                                'class_name': result.names[int(box.cls[0])],
                                                'confidence': float(box.conf[0]),
                                                'frame': frame_idx
                                            }
                                            frame_detections.append(det)
                                            all_detections.append(det)
                                    
                                    # Track frame with most detections
                                    if len(frame_detections) > max_detections:
                                        max_detections = len(frame_detections)
                                        best_result = result
                                        best_frame_img = result.plot()
                                
                                # Clean up temp file
                                try:
                                    os.remove(temp_path)
                                except:
                                    pass
                            except Exception as frame_error:
                                # Continue processing other frames even if one fails
                                continue
                        
                        cap.release()
                        inference_time = time.time() - start_time
                        
                        # Calculate performance metrics
                        if frame_times:
                            fps_values = [1.0 / t for t in frame_times if t > 0]
                            perf_metrics['total_inference_time'] = inference_time
                            perf_metrics['frame_times'] = frame_times
                            perf_metrics['avg_fps'] = sum(fps_values) / len(fps_values) if fps_values else 0
                            perf_metrics['min_fps'] = min(fps_values) if fps_values else 0
                            perf_metrics['max_fps'] = max(fps_values) if fps_values else 0
                            perf_metrics['avg_latency_ms'] = int((sum(frame_times) / len(frame_times)) * 1000)
                        
                        if processed_frames == 0:
                            self.finished.emit(False, None, f"Could not process any frames from video")
                            return
                        
                        result_dict = {
                            'inference_time': inference_time,
                            'detections': all_detections,
                            'annotated_image': best_frame_img if best_frame_img is not None else None,
                            'frame_count': processed_frames,
                            'total_detections': len(all_detections),
                            'performance': perf_metrics
                        }
                        
                        if best_frame_img is not None:
                            self.finished.emit(True, result_dict, f"Video analyzed ({processed_frames} frames processed, {len(all_detections)} detections)")
                        else:
                            self.finished.emit(False, None, f"No detections found in {processed_frames} frames")
                        
                except Exception as e:
                    import traceback
                    self.finished.emit(False, None, f"Error: {str(e)}\n{traceback.format_exc()}")
        
        is_video = getattr(self, 'sandbox_is_video', False)
        self.sandbox_worker = InferenceWorker(
            version, 
            self.sandbox_input_path,
            self.sandbox_conf_spin.value(),
            self.sandbox_iou_spin.value(),
            is_video=is_video
        )
        self.sandbox_worker.finished.connect(self._on_sandbox_inference_finished)
        self.sandbox_worker.progress.connect(self._on_sandbox_progress)
        self.sandbox_worker.start()

    def _on_sandbox_progress(self, current_frame: int, total_frames: int, detections_so_far: int, elapsed_ms: int, frame_path: str):
        """Update real-time progress statistics during inference."""
        percent = int((current_frame / total_frames) * 100) if total_frames else 0
        elapsed_sec = elapsed_ms / 1000.0 if elapsed_ms else 0.0
        fps = current_frame / elapsed_sec if elapsed_sec > 0 else 0
        remaining = (elapsed_sec / current_frame * (total_frames - current_frame)) if current_frame > 0 else 0

        stats_text = (
            f"Processing: {current_frame}/{total_frames}\n"
            f"Progress: {percent}%\n\n"
            f"Detections: {detections_so_far}\n"
            f"Elapsed: {elapsed_sec:.1f}s\n"
            f"FPS: {fps:.1f}\n\n"
            f"Est. Remaining: {remaining:.1f}s"
        )
        self.sandbox_stats_panel.setText(stats_text)

        # Show the current frame being processed in the input preview
        if frame_path and os.path.exists(frame_path):
            pixmap = QPixmap(frame_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(520, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.sandbox_input_label.setPixmap(scaled)

    def _on_sandbox_inference_finished(self, success: bool, results: dict, message: str):
        """Handle inference completion."""
        self.sandbox_run_btn.setEnabled(True)
        self.sandbox_progress.setVisible(False)
        
        if not success:
            QMessageBox.warning(self, "Inference Error", message)
            self.sandbox_stats_label.setText("Inference failed")
            return
        
        try:
            # Display annotated image (constrained size)
            annotated_img = results['annotated_image']
            height, width, channel = annotated_img.shape
            bytes_per_line = 3 * width
            q_img = QImage(annotated_img.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img.rgbSwapped())
            
            # Scale to fit label constraints (max 200px height set earlier)
            scaled = pixmap.scaled(420, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.sandbox_results_label.setPixmap(scaled)
            self.sandbox_results_label.setText("")
            
            # Update stats with performance metrics
            num_detections = results['total_detections']
            frame_count = results.get('frame_count', 1)
            inference_time = results['inference_time'] * 1000  # Convert to ms
            perf = results.get('performance', {})
            
            if frame_count > 1:
                # Video analysis stats with performance
                avg_fps = perf.get('avg_fps', 0.0)
                min_fps = perf.get('min_fps', 0.0)
                max_fps = perf.get('max_fps', 0.0)
                avg_latency = perf.get('avg_latency_ms', 0)
                
                self.sandbox_stats_label.setText(
                    f"Frames: {frame_count} | Detections: {num_detections} | Total: {inference_time:.1f}ms\n"
                    f"FPS: {avg_fps:.1f} avg ({min_fps:.1f}-{max_fps:.1f}) | Latency: {avg_latency}ms avg"
                )
                
                # Log performance to metrics file
                try:
                    from embereye.utils.metrics import log_performance_metric
                    log_performance_metric(
                        metric_type='sandbox_video_inference',
                        model_version=perf.get('model_version', 'unknown'),
                        fps_avg=avg_fps,
                        fps_min=min_fps,
                        fps_max=max_fps,
                        latency_ms=avg_latency,
                        frame_count=frame_count,
                        detections=num_detections,
                        conf=perf.get('conf_threshold', 0.25),
                        iou=perf.get('iou_threshold', 0.45)
                    )
                except Exception:
                    pass
            else:
                # Image analysis stats with performance
                fps = perf.get('avg_fps', 0.0)
                latency = perf.get('avg_latency_ms', 0)
                
                self.sandbox_stats_label.setText(
                    f"Detections: {num_detections} | Time: {inference_time:.1f}ms | FPS: {fps:.1f} | Latency: {latency}ms"
                )
                
                # Log performance to metrics file
                try:
                    from embereye.utils.metrics import log_performance_metric
                    log_performance_metric(
                        metric_type='sandbox_image_inference',
                        model_version=perf.get('model_version', 'unknown'),
                        fps_avg=fps,
                        latency_ms=latency,
                        frame_count=1,
                        detections=num_detections,
                        conf=perf.get('conf_threshold', 0.25),
                        iou=perf.get('iou_threshold', 0.45)
                    )
                except Exception:
                    pass
            
            # Populate detections list
            self.sandbox_detections_list.clear()
            if frame_count > 1:
                # Group by class for videos
                from collections import defaultdict
                by_class = defaultdict(int)
                for det in results['detections']:
                    by_class[det['class_name']] += 1
                
                for class_name, count in sorted(by_class.items()):
                    self.sandbox_detections_list.addItem(f"{class_name}: {count} detections")
            else:
                # Individual detections for images
                for det in results['detections']:
                    item_text = f"{det['class_name']} ({det['confidence']:.2f})"
                    self.sandbox_detections_list.addItem(item_text)
            
            if num_detections == 0:
                self.sandbox_detections_list.addItem("No objects detected")
                
        except Exception as e:
            QMessageBox.warning(self, "Display Error", f"Error displaying results: {e}")


    def _copy_annotations_to_training(self, source_dir: str) -> str:
        """Copy annotated frames (images + txt) into training_data/annotations."""
        try:
            if not source_dir or not os.path.exists(source_dir):
                return ""
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

    def _refresh_model_versions(self):
        """Reload model versions list from disk."""
        try:
            from embereye.core.model_versioning import ModelVersionManager
            manager = ModelVersionManager()
            versions = manager.list_versions()
            current_best = manager.get_current_best()
            current_version = None
            if current_best:
                parts = Path(current_best).parts
                for p in parts:
                    if p.startswith('v') and p[1:].isdigit():
                        current_version = p
                        break
            self.model_versions_list.clear()
            for v in versions:
                label = v
                # Try to load metadata for accuracy/time
                try:
                    meta = manager.get_version_metadata(v)
                    if meta:
                        acc = getattr(meta, 'best_accuracy', 0.0) or 0.0
                        train_hrs = getattr(meta, 'training_time_hours', 0.0) or 0.0
                        label = f"{v} | mAP: {float(acc):.4f} | Time: {float(train_hrs):.2f}h"
                except Exception:
                    pass
                if current_version == v:
                    label = f"✓ {label} [ACTIVE]"
                self.model_versions_list.addItem(label)
        except Exception as e:
            self.model_versions_list.clear()
            self.model_versions_list.addItem(f"Error loading versions: {e}")

    def _refresh_training_ready_count(self):
        """Update the 'Ready for Training' count display."""
        # Don't update if training just completed (preserve completion message)
        if getattr(self, 'training_just_completed', False):
            return
        
        try:
            training_ann_base = get_data_path(os.path.join("training_data", "annotations"))
            total = self._count_annotation_files(training_ann_base)
            if total == 0:
                self.training_ready_count_label.setText("0 annotation files")
                self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #888; border: none; background: transparent;")
            else:
                self.training_ready_count_label.setText(f"{total} annotation files")
                self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50; border: none; background: transparent;")
        except Exception:
            self.training_ready_count_label.setText("Error")
            self.training_ready_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #f44336; border: none; background: transparent;")

    def _refresh_dataset_stats(self):
        """Update Dataset Stats panel using DatasetInspector."""
        try:
            from embereye.utils import DatasetInspector
            inspector = DatasetInspector(base_dir="training_data")
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
            top_txt = ", ".join([f"{k}:{v}" for k, v in top]) if top else "—"
            self.dataset_classes_label.setText(f"Classes: {total_cls} ({top_txt})")
        except Exception:
            self.dataset_images_counts_label.setText("Images: —")
            self.dataset_classes_label.setText("Classes: —")

    def _on_training_progress(self, percent: int, message: str):
        """Update overall training progress bar."""
        self.training_progress.setValue(max(0, min(100, percent)))
        if message:
            self.training_status_label.setText(message)
    
    def _on_epoch_progress(self, current: int, total: int):
        """Update epoch counter display."""
        self.training_epoch_label.setText(f"Epoch: {current}/{total}")

    def _on_training_finished(self, ok: bool, msg: str, payload):
        """Handle training completion.
        payload: either string best_model path or dict with keys
            - best_model: str
            - metrics: dict
            - train_seconds: int
        """
        # Re-enable UI
        self.start_training_btn.setEnabled(True)
        self.cancel_training_btn.setEnabled(False)
        self.training_progress.setValue(100 if ok else 0)
        
        if not ok:
            self.training_status_label.setText(f"Error: {msg}")
            self.training_epoch_label.setText("Epoch: 0/0")
            QMessageBox.critical(self, "Training", msg or "Training failed")
            return
        
        # Training successful
        self.training_status_label.setText("✓ Training Complete")

        # Create model version
        try:
            from embereye.core.model_versioning import ModelVersionManager, ModelMetadata
            from training_pipeline import TrainingConfig
            manager = ModelVersionManager()
            version = manager.get_next_version()

            training_images = self._count_annotation_files(get_data_path(os.path.join("training_data", "annotations")))
            config_snapshot = getattr(self, 'training_worker', None)
            if config_snapshot and hasattr(config_snapshot, 'config'):
                cfg = config_snapshot.config
            else:
                cfg = TrainingConfig()
            
            # Update Ready for Training section to show completion status
            self.training_ready_label.setText("✓ Training Complete")
            self.training_ready_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #4CAF50; border: none; background: transparent;")
            self.training_ready_count_label.setText(f"Model {version} created")
            self.training_ready_count_label.setStyleSheet(
                "font-size: 18px; font-weight: bold; color: #4CAF50; border: none; background: transparent;"
            )
            self.training_just_completed = True  # Prevent refresh from overwriting
            
            # Resolve best model path and metrics from payload
            best_model_path = None
            metrics = {}
            train_seconds = 0
            try:
                if isinstance(payload, dict):
                    best_model_path = payload.get('best_model')
                    metrics = payload.get('metrics', {}) or {}
                    train_seconds = int(payload.get('train_seconds', 0) or 0)
                elif isinstance(payload, str):
                    best_model_path = payload
            except Exception:
                pass

            weights_dir = Path(best_model_path).parent if best_model_path else None
            metadata = ModelMetadata(
                version=version,
                timestamp=datetime.utcnow().isoformat(),
                training_images=training_images,
                new_images=training_images,
                total_epochs=cfg.epochs,
                best_accuracy=float(metrics.get('map50') or metrics.get('map') or 0.0),
                loss=0.0,
                training_time_hours=round((train_seconds or 0) / 3600.0, 3),
                base_model=f"yolov8{cfg.model_size}",
                config_snapshot=cfg.to_dict(),
                previous_version=None,
                notes="Trained via UI",
                training_strategy="full_retrain",
            )
            if weights_dir and weights_dir.exists():
                manager.create_version(metadata, weights_dir)
                self._refresh_model_versions()
                self._refresh_sandbox_models()  # Update Sandbox dropdown with new version
            else:
                QMessageBox.warning(self, "Versioning", "Training complete, but best weights not found. Version not created.")
        except Exception as e:
            QMessageBox.warning(self, "Versioning", f"Training done, but versioning failed: {e}")

    def _update_anomaly_count(self):
        pass

    def handle_anomaly_frame_from_widget(self, loc_id, qimage, score):
        """Add a captured anomaly to the Anomalies tab."""
        try:
            # Check if capture is enabled
            if not getattr(self, 'anomaly_capture_enabled', True):
                return
            from PyQt5.QtGui import QPixmap, QIcon
            from PyQt5.QtWidgets import QListWidgetItem
            import time, os
            from datetime import datetime
            # Convert to pixmap in GUI thread
            pixmap = QPixmap.fromImage(qimage)
            # Maintain max items by removing oldest
            if len(self._anomalies_store) >= getattr(self, '_anomaly_max_items', 200):
                self._anomalies_store.pop(0)
                # Also remove first list item if exists
                if self.anomaly_list.count() > 0:
                    self.anomaly_list.takeItem(0)

            ts = time.time()
            entry = {
                'pixmap': pixmap,
                'loc_id': str(loc_id),
                'score': float(score),
                'ts': ts
            }
            self._anomalies_store.append(entry)

            # Save to disk if enabled
            if getattr(self, 'anomaly_save_enabled', False):
                try:
                    save_dir = getattr(self, 'anomaly_save_dir', '')
                    if save_dir:
                        date_str = datetime.fromtimestamp(ts).strftime('%Y%m%d')
                        date_path = os.path.join(save_dir, date_str)
                        os.makedirs(date_path, exist_ok=True)
                        fname = datetime.fromtimestamp(ts).strftime('%H%M%S') + f"_{loc_id}_{score:.2f}.png"
                        full_path = os.path.join(date_path, fname)
                        pixmap.save(full_path)
                except Exception as e:
                    print(f"Anomaly disk save error: {e}")

            # Create thumbnail item
            item = QListWidgetItem()
            # index used as reference back into store
            idx = len(self._anomalies_store) - 1
            item.setData(Qt.UserRole, idx)
            # Set icon and label
            icon = QIcon(pixmap.scaled(160, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            item.setIcon(icon)
            ts_str = datetime.fromtimestamp(entry['ts']).strftime('%H:%M:%S')
            item.setText(f"{entry['loc_id']}\n{ts_str} • {entry['score']:.2f}")
            self.anomaly_list.addItem(item)
            self._update_anomaly_count()

            # Periodic retention cleanup (every 60 sec)
            now = time.time()
            if getattr(self, 'anomaly_save_enabled', False) and (now - getattr(self, '_last_anomaly_cleanup', 0) > 60):
                self._last_anomaly_cleanup = now
                self._cleanup_old_anomalies()
        except Exception as e:
            print(f"Anomaly add error: {e}")

    def _cleanup_old_anomalies(self):
        """Remove anomaly files older than retention_days."""
        try:
            import os, time
            save_dir = getattr(self, 'anomaly_save_dir', '')
            days = getattr(self, 'anomaly_retention_days', 7)
            if not save_dir or not os.path.isdir(save_dir):
                return
            cutoff = time.time() - (days * 86400)
            for root, dirs, files in os.walk(save_dir):
                for f in files:
                    path = os.path.join(root, f)
                    try:
                        if os.path.getmtime(path) < cutoff:
                            os.remove(path)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Anomaly cleanup error: {e}")

    def init_logo(self, title_bar):
        self.logo = QLabel()
        self.logo.setFixedSize(50, 50)
        
        # Try to load logo.png first, then fallback to phoenix symbol
        logo_loaded = False
        try:
            from pathlib import Path
            logo_path = get_resource_path("logo.png")
            if Path(logo_path).exists():
                pixmap = QPixmap(logo_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.logo.setPixmap(scaled_pixmap)
                    logo_loaded = True
        except Exception as e:
            print(f"Logo loading error: {e}")
        
        # Fallback to phoenix symbol
        if not logo_loaded:
            self.logo.setText("🦅")  # Phoenix/Eagle symbol
            self.logo.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff6b35, stop:0.5 #ff8c42, stop:1 #ffa600);
                border: 2px solid #ff4500;
                border-radius: 25px;
                font-size: 28px;
                color: #fff;
                qproperty-alignment: AlignCenter;
            """)
        
        title_bar.addWidget(self.logo)

    def init_logo_compact(self, header_layout):
        """Compact logo for modern theme (36px)"""
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(8)
        
        self.logo = QLabel()
        self.logo.setFixedSize(36, 36)
        
        logo_loaded = False
        try:
            from pathlib import Path
            logo_path = get_resource_path("logo.png")
            if Path(logo_path).exists():
                pixmap = QPixmap(logo_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.logo.setPixmap(scaled_pixmap)
                    logo_loaded = True
        except Exception as e:
            print(f"Logo loading error: {e}")
        
        if not logo_loaded:
            self.logo.setText("🔥")
            self.logo.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff6b35, stop:1 #ffa600);
                border: 2px solid #ff4500;
                border-radius: 18px;
                font-size: 18px;
                color: #fff;
                qproperty-alignment: AlignCenter;
            """)
        
        logo_layout.addWidget(self.logo)
        
        brand = QLabel("EMBER EYE")
        brand.setStyleSheet("""
            font-size: 14px;
            font-weight: 700;
            color: #00bcd4;
            letter-spacing: 2px;
            background: transparent;
        """)
        logo_layout.addWidget(brand)
        
        header_layout.addWidget(logo_container)
        
        # Countdown timer label (initially hidden)
        self.header_countdown_label = QLabel()
        self.header_countdown_label.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #ff9800;
            background: rgba(255, 152, 0, 0.1);
            border: 1px solid rgba(255, 152, 0, 0.3);
            border-radius: 10px;
            padding: 4px 12px;
        """)
        self.header_countdown_label.hide()
        header_layout.addWidget(self.header_countdown_label)
    
    def init_header_actions(self, header_layout):
        """Create Settings gear icon and Profile icon with dropdown overlays"""
        
        # Settings Gear Icon
        settings_btn = QToolButton()
        settings_btn.setText("⚙ SETTINGS")
        settings_btn.setFixedHeight(38)
        settings_btn.setMinimumWidth(110)
        settings_btn.setPopupMode(QToolButton.InstantPopup)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(0, 188, 212, 0.25);
                border: 1px solid rgba(0, 188, 212, 0.6);
                border-radius: 18px;
                color: #00bcd4;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QToolButton:hover {
                background-color: rgba(0, 188, 212, 0.4);
                border-color: #00e5ff;
            }
            QToolButton::menu-indicator { image: none; }
        """)
        
        settings_menu = QMenu()
        settings_menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #00bcd4;
                border-radius: 8px;
                padding: 8px 0;
            }
            QMenu::item {
                padding: 8px 20px;
                color: #e0e0e0;
                font-size: 12px;
                font-weight: 500;
            }
            QMenu::item:selected {
                background-color: rgba(0, 188, 212, 0.2);
                color: #00bcd4;
            }
            QMenu::separator {
                height: 1px;
                background-color: #404040;
                margin: 4px 12px;
            }
        """)
        settings_menu.addAction("🎥 Configure Streams", self.configure_streams)
        settings_menu.addAction("🔄 Reset Streams", self.reset_streams)
        settings_menu.addSeparator()
        settings_menu.addAction("💾 Backup Configuration", self.backup_config)
        settings_menu.addAction("📂 Restore Configuration", self.restore_config)
        settings_menu.addSeparator()
        settings_menu.addAction("🔌 TCP Server Port", self.show_tcp_port_dialog)
        settings_menu.addAction("🌡 Thermal Grid Settings", self.show_thermal_grid_config)
        self.global_grid_action = settings_menu.addAction("📊 Numeric Grid (All)")
        self.global_grid_action.setCheckable(True)
        self.global_grid_action.toggled.connect(self.toggle_all_numeric_grids)
        settings_menu.addAction("🎛 Sensor Configuration", self.show_sensor_config)
        # Master taxonomy manager
        settings_menu.addAction("📚 Class & Subclass Manager", self.show_master_class_config)
        settings_menu.addAction("📋 Log Viewer", self.show_log_viewer_dialog)
        settings_menu.addSeparator()
        # Model Export submenu
        export_menu = settings_menu.addMenu("📦 Export Model")
        export_menu.addAction("🔹 Export to ONNX", lambda: self.export_model('onnx'))
        export_menu.addAction("🔹 Export to TorchScript", lambda: self.export_model('torchscript'))
        export_menu.addAction("🔹 Export to CoreML", lambda: self.export_model('coreml'))
        export_menu.addAction("🔹 Export to TensorFlow Lite", lambda: self.export_model('tflite'))
        settings_menu.addSeparator()
        pfds_menu = settings_menu.addMenu("🔥 PFDS Devices")
        pfds_menu.addAction("➕ Add Device", self.show_pfds_add_dialog)
        pfds_menu.addAction("👁 View Devices", self.show_pfds_view_dialog)
        settings_menu.addSeparator()
        settings_menu.addAction("🧪 Test Error", self.inject_test_stream_error)
        
        settings_btn.setMenu(settings_menu)
        settings_btn.setToolTip("Settings")
        header_layout.addWidget(settings_btn)
        
        # Profile Icon
        profile_btn = QToolButton()
        profile_btn.setText("👤 PROFILE")
        profile_btn.setFixedHeight(38)
        profile_btn.setMinimumWidth(110)
        profile_btn.setPopupMode(QToolButton.InstantPopup)
        profile_btn.setCursor(Qt.PointingHandCursor)
        profile_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(0, 188, 212, 0.25);
                border: 1px solid rgba(0, 188, 212, 0.6);
                border-radius: 18px;
                color: #00bcd4;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QToolButton:hover {
                background-color: rgba(0, 188, 212, 0.4);
                border-color: #00e5ff;
            }
            QToolButton::menu-indicator { image: none; }
        """)
        
        profile_menu = QMenu()
        profile_menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #00bcd4;
                border-radius: 8px;
                padding: 8px 0;
            }
            QMenu::item {
                padding: 8px 20px;
                color: #e0e0e0;
                font-size: 12px;
                font-weight: 500;
            }
            QMenu::item:selected {
                background-color: rgba(0, 188, 212, 0.2);
                color: #00bcd4;
            }
            QMenu::separator {
                height: 1px;
                background-color: #404040;
                margin: 4px 12px;
            }
        """)
        profile_menu.addAction("👤 My Profile", self.show_profile)
        profile_menu.addSeparator()
        profile_menu.addAction("🚪 Logout", self.logout)
        
        profile_btn.setMenu(profile_menu)
        profile_btn.setToolTip("Profile")
        header_layout.addWidget(profile_btn)

    def init_settings_menu(self, title_bar):
        menu_btn = QToolButton()
        menu_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu()
        menu.addAction("Profile", self.show_profile)
        menu.addAction("Configure Streams", self.configure_streams)
        menu.addAction("Reset Streams", self.reset_streams)
        # Add backup/restore actions
        menu.addSeparator()
        menu.addAction("Backup Configuration", self.backup_config)
        menu.addAction("Restore Configuration", self.restore_config)
        menu.addSeparator()
        menu.addAction("TCP Server Port...", self.show_tcp_port_dialog)
        menu.addAction("Thermal Grid Settings...", self.show_thermal_grid_config)
        # Global numeric thermal grid toggle (all streams)
        self.global_grid_action = menu.addAction("Numeric Thermal Grid (All Streams)")
        self.global_grid_action.setCheckable(True)
        self.global_grid_action.toggled.connect(self.toggle_all_numeric_grids)
        menu.addAction("Sensor Configuration...", self.show_sensor_config)
        menu.addAction("Log Viewer...", self.show_log_viewer_dialog)
        # Configure PFDS Device submenu
        pfds_menu = QMenu("Configure PFDS Device", menu)
        pfds_menu.addAction("Add Device...", self.show_pfds_add_dialog)
        pfds_menu.addAction("View Devices...", self.show_pfds_view_dialog)
        menu.addMenu(pfds_menu)
        menu.addAction("Inject Test Stream Error", self.inject_test_stream_error)
        menu.addSeparator()
        menu.addAction("Logout", self.logout)
        menu_btn.setMenu(menu)
        title_bar.addWidget(menu_btn)

    def init_tcp_status_indicator(self):
        """Initialize TCP server status indicator in status bar."""
        from PyQt5.QtWidgets import QLabel, QPushButton, QWidget, QHBoxLayout
        from PyQt5.QtCore import Qt
        
        # Create a container widget for the status indicator
        status_widget = QWidget()
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(5, 0, 5, 0)
        status_layout.setSpacing(8)
        
        # LED indicator (colored circle)
        self.tcp_led = QLabel()
        self.tcp_led.setFixedSize(12, 12)
        self.tcp_led.setStyleSheet("""
            QLabel {
                background-color: #ff0000;
                border-radius: 6px;
                border: 1px solid #333;
            }
        """)
        status_layout.addWidget(self.tcp_led)
        
        # Status text label
        self.tcp_status_label = QLabel("TCP Server: Initializing...")
        self.tcp_status_label.setStyleSheet("QLabel { color: #333; font-size: 11px; }")
        status_layout.addWidget(self.tcp_status_label)
        
        # Restart button
        restart_btn = QPushButton("↻ Restart")
        restart_btn.setFixedHeight(20)
        restart_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        restart_btn.clicked.connect(self.show_tcp_port_dialog)
        status_layout.addWidget(restart_btn)
        
        status_widget.setLayout(status_layout)
        
        # Add to status bar (permanent widget on the left)
        self.statusBar().addPermanentWidget(status_widget, 0)
    
    def update_tcp_status(self, is_running, message):
        """Update TCP server status indicator.
        
        Args:
            is_running (bool): True if server is running, False otherwise
            message (str): Status message to display
        """
        if not hasattr(self, 'tcp_led') or not hasattr(self, 'tcp_status_label'):
            return
        
        try:
            # Update LED color
            if is_running:
                self.tcp_led.setStyleSheet("""
                    QLabel {
                        background-color: #00ff00;
                        border-radius: 6px;
                        border: 1px solid #333;
                    }
                """)
            else:
                self.tcp_led.setStyleSheet("""
                    QLabel {
                        background-color: #ff0000;
                        border-radius: 6px;
                        border: 1px solid #333;
                    }
                """)
            
            # Update status text
            self.tcp_status_label.setText(message)
            
        except Exception as e:
            print(f"TCP status update error: {e}")

    def show_tcp_port_dialog(self):
        from PyQt5.QtWidgets import QInputDialog
        current_port = self.config.get('tcp_port', 9001)
        port, ok = QInputDialog.getInt(self, "TCP Server Port", "Enter TCP server port:", value=current_port, min=1024, max=65535)
        if ok and port != current_port:
            # Stop existing server
            if hasattr(self, 'tcp_server') and self.tcp_server:
                try:
                    self.tcp_server.stop()
                    self.update_tcp_status(False, "TCP Server: Stopped for restart")
                except Exception as e:
                    print(f"TCP server stop error: {e}")
            
            # Update config
            self.config['tcp_port'] = port
            self.tcp_server_port = port
            from stream_config import StreamConfig
            StreamConfig.save_config(self.config)
            
            # Restart with new port
            try:
                from tcp_sensor_server import TCPSensorServer
                self.tcp_message_count = 0
                # Always connect the signal (PyQt5 does not duplicate connections)
                self.tcp_packet_signal.connect(self.handle_tcp_packet, Qt.QueuedConnection)
                self.tcp_server = TCPSensorServer(port=port, packet_callback=self._emit_tcp_packet)
                self.tcp_server.start()
                self.update_tcp_status(True, f"TCP Server: Running on port {port}")
                QMessageBox.information(self, "TCP Server Restarted", f"TCP server successfully restarted on port {port}.")
            except Exception as e:
                error_msg = str(e)
                self.update_tcp_status(False, f"TCP Server: Failed - {error_msg}")
                if "Address already in use" in error_msg or "already in use" in error_msg:
                    QMessageBox.critical(self, "Port Already in Use", f"Port {port} is already in use by another application. Please choose a different port.")
                else:
                    QMessageBox.critical(self, "TCP Server Error", f"Failed to start TCP server on port {port}:\n{error_msg}")

    def show_thermal_grid_config(self):
        """Show thermal grid configuration dialog."""
        from thermal_grid_config import ThermalGridConfigDialog
        
        # Get current settings from first widget (all widgets will share same config)
        current_settings = None
        if self.video_widgets:
            first_widget = next(iter(self.video_widgets.values()))
            current_settings = {
                'enabled': first_widget.thermal_grid_enabled,
                'rows': first_widget.thermal_grid_rows,
                'cols': first_widget.thermal_grid_cols,
                'cell_color': first_widget.thermal_grid_color,
                'border_color': first_widget.thermal_grid_border,
                'border_width': 2,  # Add border width to VideoWidget if needed
                'temp_threshold': self.sensor_fusion.temp_threshold,
                'critical_temp_threshold': getattr(self.sensor_fusion, 'critical_temp_threshold', 60.0)
            }
        
        dialog = ThermalGridConfigDialog(self, current_settings)
        dialog.settings_changed.connect(self.apply_thermal_grid_settings)
        
        if dialog.exec_():
            # Settings already applied via signal
            QMessageBox.information(self, "Settings Applied", "Thermal grid configuration has been updated.")
    
    def apply_thermal_grid_settings(self, settings):
        """Apply thermal grid settings to all video widgets and sensor fusion."""
        # Update sensor fusion thresholds
        self.sensor_fusion.temp_threshold = settings['temp_threshold']
        self.sensor_fusion.critical_temp_threshold = settings.get('critical_temp_threshold', 60.0)
        
        # Update all video widgets
        for widget in self.video_widgets.values():
            widget.thermal_grid_enabled = settings['enabled']
            widget.thermal_grid_rows = settings['rows']
            widget.thermal_grid_cols = settings['cols']
            widget.thermal_grid_color = settings['cell_color']
            widget.thermal_grid_border = settings['border_color']
            # Trigger redraw if hot cells exist
            if widget.hot_cells:
                widget._redraw_with_grid()

    def show_sensor_config(self):
        """Show sensor configuration dialog."""
        from sensor_config_dialog import SensorConfigDialog
        
        # Get current settings
        current_settings = {
            # Fusion parameters
            'temp_threshold': self.sensor_fusion.temp_threshold,
            'gas_ppm_threshold': self.sensor_fusion.gas_ppm_threshold,
            'flame_active_value': self.sensor_fusion.flame_active_value,
            'min_sources': self.sensor_fusion.min_sources,
            
            # Gas sensor calibration
            'gas_r0': getattr(self.gas_sensor, 'r0', 76.63),
            'gas_rl': getattr(self.gas_sensor, 'rl', 1.0),
            'gas_vcc': getattr(self.gas_sensor, 'vcc', 5.0),
            
            # Display settings
            'hot_cell_decay_time': 5.0,
            'freeze_on_alarm': True,
            'show_fusion_overlay': True,
            'vision_threshold': 0.7,
            'vision_confidence_weight': 0.5,
            
            # Anomalies
            'anomaly_threshold': getattr(self, 'anomaly_threshold', 0.4),
            'anomaly_max_items': getattr(self, '_anomaly_max_items', 200),
            'anomaly_save_enabled': getattr(self, 'anomaly_save_enabled', False),
            'anomaly_save_dir': getattr(self, 'anomaly_save_dir', ''),
            'anomaly_retention_days': getattr(self, 'anomaly_retention_days', 7)
        }
        
        # Get display settings from first widget if available
        if self.video_widgets:
            first_widget = next(iter(self.video_widgets.values()))
            current_settings['hot_cell_decay_time'] = first_widget.hot_cells_decay_time
            current_settings['freeze_on_alarm'] = first_widget.freeze_on_alarm
            current_settings['show_fusion_overlay'] = first_widget.show_fusion_overlay
        
        dialog = SensorConfigDialog(self, current_settings)
        dialog.settings_changed.connect(self.apply_sensor_config)
        
        if dialog.exec_():
            QMessageBox.information(self, "Settings Applied", "Sensor configuration has been updated.")
    
    def apply_sensor_config(self, settings):
        """Apply sensor configuration settings."""
        # Update sensor fusion
        self.sensor_fusion.temp_threshold = settings['temp_threshold']
        self.sensor_fusion.gas_ppm_threshold = settings['gas_ppm_threshold']
        self.sensor_fusion.flame_active_value = settings['flame_active_value']
        self.sensor_fusion.min_sources = settings['min_sources']
        
        # Update gas sensor calibration
        if hasattr(self.gas_sensor, 'set_calibration'):
            self.gas_sensor.set_calibration(
                r0=settings['gas_r0'],
                rl=settings['gas_rl'],
                vcc=settings['gas_vcc']
            )
        else:
            # Update attributes directly
            self.gas_sensor.r0 = settings['gas_r0']
            self.gas_sensor.rl = settings['gas_rl']
            self.gas_sensor.vcc = settings['gas_vcc']
        
        # Update display settings for all video widgets
        for widget in self.video_widgets.values():
            widget.hot_cells_decay_time = settings['hot_cell_decay_time']
            widget.freeze_on_alarm = settings['freeze_on_alarm']
            widget.show_fusion_overlay = settings['show_fusion_overlay']
            # Update worker anomaly threshold if worker exists
            if hasattr(widget, 'worker') and widget.worker:
                widget.worker.anomaly_threshold = settings.get('anomaly_threshold', 0.4)
        
        # Update anomaly settings in main window
        self.anomaly_threshold = settings.get('anomaly_threshold', 0.4)
        self._anomaly_max_items = settings.get('anomaly_max_items', 200)
        self.anomaly_save_enabled = settings.get('anomaly_save_enabled', False)
        self.anomaly_save_dir = settings.get('anomaly_save_dir', '')
        self.anomaly_retention_days = settings.get('anomaly_retention_days', 7)
        
        print(f"Sensor config updated: Temp={settings['temp_threshold']}, Gas={settings['gas_ppm_threshold']}, "
              f"R0={settings['gas_r0']}, MinSources={settings['min_sources']}, AnomalyThr={self.anomaly_threshold}")

    def show_master_class_config(self):
        """Open the master class configuration dialog and refresh classes on save."""
        try:
            from master_class_config_dialog import MasterClassConfigDialog
            from master_class_config import load_master_classes, flatten_classes
            
            dlg = MasterClassConfigDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                # Reload taxonomy and refresh dependent UI controls
                self._master_classes = load_master_classes()
                self.training_video_classes = flatten_classes(self._master_classes)
                if hasattr(self, 'training_video_class_combo') and self.training_video_class_combo:
                    self.training_video_class_combo.clear()
                    self.training_video_class_combo.addItems(self.training_video_classes)
                # Update ingestion class list
                if hasattr(self, 'anomalies_manager') and self.anomalies_manager:
                    try:
                        self.anomalies_manager.set_yolo_classes(self.training_video_classes)
                    except Exception:
                        pass
                QMessageBox.information(self, "Updated", "Classes updated. New training will use the latest taxonomy. Existing model versions remain unchanged.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Class Manager: {e}")


    def show_pfds_add_dialog(self):
        """Stub dialog for adding a PFDS device. Will be wired to SQLite and scheduler."""
        from PyQt5.QtWidgets import QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox, QDialogButtonBox, QMessageBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Add PFDS Device")
        layout = QFormLayout(dlg)

        name_edit = QLineEdit(); name_edit.setPlaceholderText("Device Name")
        ip_edit = QLineEdit(); ip_edit.setPlaceholderText("IP Address (e.g., 192.168.1.50)")
        loc_combo = QComboBox(); loc_combo.addItem("")
        # Populate location IDs from stream config
        try:
            loc_ids = set()
            for g in self.config.get('groups', []):
                streams = self.config.get('streams', {}).get(g, []) if isinstance(self.config.get('streams'), dict) else self.config.get('streams', [])
                for s in streams:
                    lid = s.get('location_id') or s.get('loc_id') or s.get('name')
                    if lid:
                        loc_ids.add(lid)
            for lid in sorted(loc_ids):
                loc_combo.addItem(lid)
        except Exception:
            pass

        mode_combo = QComboBox(); mode_combo.addItems(["Continuous", "On Demand"])
        poll_spin = QSpinBox(); poll_spin.setRange(1, 3600); poll_spin.setValue(10)
        poll_spin.setSuffix(" s")

        layout.addRow("Name", name_edit)
        layout.addRow("IP Address", ip_edit)
        layout.addRow("Location Id", loc_combo)
        layout.addRow("Mode", mode_combo)
        layout.addRow("Poll Frequency", poll_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(buttons)

        def on_ok():
            name = name_edit.text().strip()
            ip = ip_edit.text().strip()
            loc = loc_combo.currentText().strip()
            mode = mode_combo.currentText()
            poll = poll_spin.value()
            if not name or not ip:
                QMessageBox.warning(dlg, "Missing Data", "Please enter device name and IP address.")
                return
            if not is_valid_ip(ip):
                QMessageBox.warning(dlg, "Invalid IP", "Please enter a valid IP address.")
                return
            try:
                self.pfds.add_device(name, ip, loc if loc else None, mode, int(poll))
                QMessageBox.information(dlg, "Saved", f"PFDS device '{name}' saved.\nIP: {ip}\nLocation: {loc or 'N/A'}\nMode: {mode}\nPoll: {poll}s")
            except Exception as e:
                QMessageBox.critical(dlg, "Save Failed", f"Could not save device: {e}")
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        dlg.exec_()

    def show_pfds_view_dialog(self):
        """View configured PFDS devices (loaded from SQLite)."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHBoxLayout, QPushButton, QMessageBox
        dlg = QDialog(self)
        dlg.setWindowTitle("PFDS Devices")
        layout = QVBoxLayout(dlg)

        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["ID", "Name", "IP", "Location Id", "Mode", "Poll (s)"])
        layout.addWidget(table)

        def load_rows():
            table.setRowCount(0)
            try:
                devices = self.pfds.list_devices()
                for d in devices:
                    row = table.rowCount()
                    table.insertRow(row)
                    vals = [d['id'], d['name'], d['ip'], d.get('location_id') or '', d['mode'], d['poll_seconds']]
                    for c, val in enumerate(vals):
                        table.setItem(row, c, QTableWidgetItem(str(val)))
            except Exception as e:
                QMessageBox.critical(dlg, "Load Failed", f"Could not load devices: {e}")

        load_rows()

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        remove_btn = QPushButton("Remove Selected")
        close_btn = QPushButton("Close")
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        refresh_btn.clicked.connect(load_rows)
        def remove_selected():
            row = table.currentRow()
            if row < 0:
                QMessageBox.information(dlg, "No Selection", "Select a device row to remove.")
                return
            did_item = table.item(row, 0)
            if not did_item:
                return
            did = int(did_item.text())
            try:
                self.pfds.remove_device(did)
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Remove Failed", f"Could not remove device: {e}")
        remove_btn.clicked.connect(remove_selected)
        close_btn.clicked.connect(dlg.accept)
        dlg.resize(700, 400)
        dlg.exec_()

    def show_log_viewer_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QFileDialog, QLineEdit, QComboBox
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QTabWidget
        from error_logger import get_error_logger
        dlg = QDialog(self)
        dlg.setWindowTitle("Log Viewer")
        layout = QVBoxLayout(dlg)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- App Error Log Tab ---
        app_tab = QDialog(dlg)
        app_layout = QVBoxLayout(app_tab)

        # Search and filter row
        filter_row = QHBoxLayout()
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search message...")
        source_combo = QComboBox()
        source_combo.addItem("All Sources")
        # Populate sources
        sources = {e['source'] for e in get_error_logger().get_entries()}
        for s in sorted(sources):
            source_combo.addItem(s)
        filter_row.addWidget(search_edit)
        filter_row.addWidget(source_combo)
        app_layout.addLayout(filter_row)

        list_widget = QListWidget()
        app_layout.addWidget(list_widget)

        def refresh():
            entries = get_error_logger().get_entries()
            # Dynamic source update
            existing_sources = set(source_combo.itemText(i) for i in range(source_combo.count()))
            new_sources = {e['source'] for e in entries}
            if not new_sources.issubset(existing_sources):
                current_sel = source_combo.currentText()
                source_combo.clear()
                source_combo.addItem('All Sources')
                for s in sorted(new_sources):
                    source_combo.addItem(s)
                # Restore selection if possible
                idx = source_combo.findText(current_sel)
                if idx >= 0:
                    source_combo.setCurrentIndex(idx)
            list_widget.clear()
            term = search_edit.text().strip().lower()
            sel_source = source_combo.currentText()
            for e in entries:
                if sel_source != 'All Sources' and e['source'] != sel_source:
                    continue
                line = f"{e['timestamp']} | {e['source']} | {e['message']}"
                if term and term not in line.lower():
                    continue
                list_widget.addItem(line)

        # Initial load
        refresh()

        # Auto-refresh timer
        timer = QTimer(app_tab)
        timer.setInterval(2000)
        timer.timeout.connect(refresh)
        timer.start()

        search_edit.textChanged.connect(refresh)
        source_combo.currentIndexChanged.connect(refresh)

        btn_row = QHBoxLayout()
        export_btn = QPushButton("Export")
        clear_btn = QPushButton("Clear")
        copy_btn = QPushButton("Copy Selected")
        close_btn = QPushButton("Close")

        def do_export():
            path, _ = QFileDialog.getSaveFileName(dlg, "Export Error Log", "error_log_export.json", "JSON Files (*.json)")
            if path:
                if get_error_logger().export(path):
                    QMessageBox.information(dlg, "Export", "Error log exported successfully")
                else:
                    QMessageBox.critical(dlg, "Export", "Failed to export log")

        def do_clear():
            get_error_logger().clear()
            refresh()

        def do_copy():
            items = list_widget.selectedItems()
            if items:
                from PyQt5.QtWidgets import QApplication
                QApplication.clipboard().setText('\n'.join(i.text() for i in items))
                QMessageBox.information(dlg, "Copied", "Selected entries copied to clipboard")

        export_btn.clicked.connect(do_export)
        clear_btn.clicked.connect(do_clear)
        copy_btn.clicked.connect(do_copy)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        app_layout.addLayout(btn_row)

        tabs.addTab(app_tab, "App Error Log")

        # --- TCP Log Viewer Tab ---
        tcp_tab = QDialog(dlg)
        from PyQt5.QtWidgets import QTextEdit, QLabel
        tcp_layout = QVBoxLayout(tcp_tab)
        # Controls: Mode + Location Id filter
        ctrl_row = QHBoxLayout()
        mode_combo = QComboBox(); mode_combo.addItems(["Debug", "Error"])
        loc_combo = QComboBox(); loc_combo.addItem("All Locations")
        # Populate location IDs from stream config
        try:
            loc_ids = set()
            for g in self.config.get('groups', []):
                streams = self.config.get('streams', {}).get(g, [])
                for s in streams:
                    lid = s.get('location_id') or s.get('loc_id') or s.get('name')
                    if lid:
                        loc_ids.add(lid)
            for lid in sorted(loc_ids):
                loc_combo.addItem(lid)
        except Exception:
            pass
        ctrl_row.addWidget(QLabel("Mode:")); ctrl_row.addWidget(mode_combo)
        ctrl_row.addWidget(QLabel("Location:")); ctrl_row.addWidget(loc_combo)
        tcp_layout.addLayout(ctrl_row)

        tcp_view = QTextEdit(); tcp_view.setReadOnly(True)
        tcp_layout.addWidget(tcp_view)

        # Load logs periodically
        import os
        from tcp_logger import DEBUG_LOG, ERROR_LOG
        def load_tcp_log():
            path = DEBUG_LOG if mode_combo.currentText() == 'Debug' else ERROR_LOG
            print(f"Loading TCP log from: {path}")  # Debug output
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-1000:]
                    print(f"Loaded {len(lines)} lines from TCP log")  # Debug output
                    sel = loc_combo.currentText()
                    if sel == 'All Locations':
                        tcp_view.setPlainText(''.join(lines))
                    else:
                        filtered = []
                        for ln in lines:
                            parts = ln.split('\t')
                            # ts \t loc \t type \t ...
                            if len(parts) >= 2 and parts[1].strip() == sel:
                                filtered.append(ln)
                        print(f"Filtered to {len(filtered)} lines for location: {sel}")  # Debug output
                        tcp_view.setPlainText(''.join(filtered))
                except Exception as e:
                    error_msg = f"Error loading TCP log: {e}"
                    print(error_msg)  # Debug output
                    tcp_view.setPlainText(error_msg)
            else:
                msg = f"Log file not found: {path}"
                print(msg)  # Debug output
                tcp_view.setPlainText(msg)
        tcp_timer = QTimer(tcp_tab); tcp_timer.setInterval(2000); tcp_timer.timeout.connect(load_tcp_log); tcp_timer.start()
        mode_combo.currentIndexChanged.connect(load_tcp_log)
        loc_combo.currentIndexChanged.connect(load_tcp_log)
        load_tcp_log()

        tabs.addTab(tcp_tab, "TCP Log Viewer")

        # --- IP→Loc Mappings Admin Tab ---
        map_tab = QDialog(dlg)
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem
        map_layout = QVBoxLayout(map_tab)
        map_table = QTableWidget(0, 2)
        map_table.setHorizontalHeaderLabels(["IP", "Location Id"])
        map_layout.addWidget(map_table)

        btn_row2 = QHBoxLayout()
        add_btn = QPushButton("Add/Update Mapping")
        del_btn = QPushButton("Delete Selected")
        refresh_btn2 = QPushButton("Refresh")
        import_btn = QPushButton("Import…")
        export_btn2 = QPushButton("Export…")
        btn_row2.addWidget(add_btn)
        btn_row2.addWidget(del_btn)
        btn_row2.addWidget(refresh_btn2)
        btn_row2.addWidget(import_btn)
        btn_row2.addWidget(export_btn2)
        map_layout.addLayout(btn_row2)

        def load_mappings():
            try:
                from ip_loc_resolver import _db_conn, _json_load
                rows = []
                conn = _db_conn()
                if conn:
                    for ip, loc in conn.execute("SELECT ip, loc_id FROM mappings").fetchall():
                        rows.append((ip, loc))
                    conn.close()
                else:
                    for ip, loc in _json_load().items():
                        rows.append((ip, loc))
                map_table.setRowCount(0)
                for ip, loc in rows:
                    r = map_table.rowCount(); map_table.insertRow(r)
                    map_table.setItem(r, 0, QTableWidgetItem(ip))
                    map_table.setItem(r, 1, QTableWidgetItem(loc))
            except Exception as e:
                print(f"Load mappings error: {e}")

        def add_update_mapping():
            from PyQt5.QtWidgets import QInputDialog
            ip, ok1 = QInputDialog.getText(dlg, "IP", "Enter IP:")
            if not ok1 or not ip:
                return
            loc, ok2 = QInputDialog.getText(dlg, "Location Id", "Enter Location Id:")
            if not ok2 or not loc:
                return
            try:
                from ip_loc_resolver import set_mapping
                set_mapping(ip.strip(), loc.strip())
                load_mappings()
            except Exception as e:
                QMessageBox.critical(dlg, "Save Failed", f"Could not save mapping: {e}")

        def delete_selected_mapping():
            r = map_table.currentRow()
            if r < 0:
                QMessageBox.information(dlg, "No Selection", "Select a mapping row to delete.")
                return
            ip_item = map_table.item(r, 0)
            if not ip_item:
                return
            ip = ip_item.text()
            try:
                from ip_loc_resolver import clear_mapping
                clear_mapping(ip)
                load_mappings()
            except Exception as e:
                QMessageBox.critical(dlg, "Delete Failed", f"Could not delete mapping: {e}")

        add_btn.clicked.connect(add_update_mapping)
        del_btn.clicked.connect(delete_selected_mapping)
        refresh_btn2.clicked.connect(load_mappings)
        def do_import():
            path, _ = QFileDialog.getOpenFileName(dlg, "Import Mappings", "", "JSON (*.json);;CSV (*.csv)")
            if not path:
                return
            try:
                from ip_loc_resolver import import_json, import_csv
                ok = import_json(path) if path.lower().endswith('.json') else import_csv(path)
                if ok:
                    load_mappings()
                    QMessageBox.information(dlg, "Import", "Mappings imported successfully.")
                else:
                    QMessageBox.critical(dlg, "Import", "Failed to import mappings.")
            except Exception as e:
                QMessageBox.critical(dlg, "Import", f"Error: {e}")

        def do_export():
            path, _ = QFileDialog.getSaveFileName(dlg, "Export Mappings", "ip_loc_mappings.json", "JSON (*.json);;CSV (*.csv)")
            if not path:
                return
            try:
                from ip_loc_resolver import export_json, export_csv
                ok = export_json(path) if path.lower().endswith('.json') else export_csv(path)
                if ok:
                    QMessageBox.information(dlg, "Export", "Mappings exported successfully.")
                else:
                    QMessageBox.critical(dlg, "Export", "Failed to export mappings.")
            except Exception as e:
                QMessageBox.critical(dlg, "Export", f"Error: {e}")
        import_btn.clicked.connect(do_import)
        export_btn2.clicked.connect(do_export)
        load_mappings()

        tabs.addTab(map_tab, "IP→Loc Mappings")

        dlg.resize(900, 600)
        dlg.exec_()

    def export_model(self, format: str):
        """Export current best model to deployment format (ONNX, TorchScript, CoreML, TFLite)."""
        try:
            from embereye.core.model_versioning import ModelVersionManager
            from PyQt5.QtWidgets import QFileDialog, QProgressDialog
            from PyQt5.QtCore import Qt
            
            manager = ModelVersionManager()
            current_best = manager.get_current_best()
            
            if not current_best or not current_best.exists():
                QMessageBox.warning(
                    self, "No Model",
                    "No trained model found.\n\n"
                    "Train a model first in the Training tab."
                )
                return
            
            # Determine which version is active
            active_version = None
            try:
                parts = current_best.parts
                for p in parts:
                    if p.startswith('v') and p[1:].isdigit():
                        active_version = p
                        break
            except Exception:
                pass
            
            # File dialog for export location
            format_exts = {
                'onnx': 'ONNX Files (*.onnx)',
                'torchscript': 'TorchScript Files (*.torchscript *.pt)',
                'coreml': 'CoreML Files (*.mlmodel)',
                'tflite': 'TFLite Files (*.tflite)'
            }
            
            default_name = f"EmberEye_{active_version or 'model'}.{format if format != 'torchscript' else 'pt'}"
            save_path, _ = QFileDialog.getSaveFileName(
                self, f"Export Model to {format.upper()}",
                default_name,
                format_exts.get(format, "All Files (*.*)")
            )
            
            if not save_path:
                return
            
            # Progress dialog
            progress = QProgressDialog(f"Exporting to {format.upper()}...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("Exporting")
            progress.show()
            QApplication.processEvents()
            
            try:
                from ultralytics import YOLO
                model = YOLO(str(current_best))
                export_path = model.export(format=format, imgsz=640)
                
                progress.close()
                
                # Copy to user-specified location if different
                import shutil
                if str(export_path) != save_path:
                    shutil.copy(export_path, save_path)
                
                QMessageBox.information(
                    self, "Export Complete",
                    f"✓ Model exported successfully!\n\n"
                    f"Format: {format.upper()}\n"
                    f"Saved to: {save_path}\n"
                    f"Source: {active_version or 'current_best'}"
                )
            except Exception as e:
                progress.close()
                QMessageBox.critical(
                    self, "Export Failed",
                    f"Failed to export model:\n\n{str(e)}\n\n"
                    f"Ensure ultralytics and required dependencies are installed."
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export error: {e}")

    def dispatch_pfds_command(self, cmd: dict) -> bool:
        """Dispatch PFDS commands over existing TCP connection to device IP.
        Sends command on the active client connection (not a new connection).
        Logs success/failure to TCP logs.
        
        Returns:
            bool: True if command was sent successfully, False otherwise
        """
        from tcp_logger import log_raw_packet, log_error_packet
        ip = cmd.get('ip')
        loc = cmd.get('location_id') or ''
        name = cmd.get('name') or ''
        command = cmd.get('command')
        if not ip or not command:
            return False
        
        # Send command through existing TCP server connection
        if self.tcp_sensor_server and hasattr(self.tcp_sensor_server, 'send_command_to_client'):
            success = self.tcp_sensor_server.send_command_to_client(ip, command)
            if success:
                log_raw_packet(loc, f"PFDS_CMD {command} to {ip} ({name}) | sent via active connection")
                return True
            else:
                log_error_packet(loc, f"PFDS_CMD_FAIL {command} to {ip} ({name}) | no active connection")
                return False
        else:
            log_error_packet(loc, f"PFDS_CMD_FAIL {command} to {ip} ({name}) | TCP server not available")
            return False

    def toggle_all_numeric_grids(self, enabled):
        """Enable or disable numbers-only thermal grid view on all video streams."""
        for widget in self.get_video_widgets():
            try:
                if hasattr(widget, 'thermal_view_btn'):
                    widget.thermal_view_btn.blockSignals(True)
                    widget.thermal_view_btn.setChecked(enabled)
                    widget.thermal_view_btn.blockSignals(False)
                    # Manually invoke handler to ensure redraw/persist
                    if hasattr(widget, 'toggle_thermal_grid_view'):
                        widget.toggle_thermal_grid_view(enabled)
            except Exception as e:
                print(f"Global grid toggle error: {e}")

    def inject_test_stream_error(self):
        # Force a test error on first available video widget
        from error_logger import get_error_logger
        get_error_logger().log('TEST', 'Injected test stream error')
        # Attempt to locate a VideoWidget and call its handle_error
        for w in self.findChildren(QWidget):
            if w.__class__.__name__ == 'VideoWidget' and hasattr(w, 'handle_error'):
                w.handle_error('Injected test stream error')
                break

    def backup_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backup",
            f"stream_config_backup_{datetime.now().strftime('%Y%m%d')}.json",
            "JSON Files (*.json)"
        )
        if path:
            if StreamConfig.export_config(path):
                QMessageBox.information(self, "Success", "Configuration backup created successfully!")
            else:
                QMessageBox.critical(self, "Error", "Failed to create backup")
    
    def restore_config(self):
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            "This will overwrite current configuration. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            "",
            "JSON Files (*.json)"
        )
        if path:
            if StreamConfig.import_config(path):
                # Reload configuration
                self.config = StreamConfig.load_config()
                self.group_combo.clear()
                self.group_combo.addItems(self.config["groups"])
                self.schedule_grid_rebuild()
                QMessageBox.information(self, "Success", "Configuration restored successfully!")
            else:
                QMessageBox.critical(self, "Error", "Invalid backup file or restore failed")

    def start_websocket_client(self):
        """Start WebSocket client in background thread"""
        def run_loop():
            asyncio.run(self.websocket_client())

        self.ws_thread = Thread(target=run_loop, daemon=True)
        if self.ws_thread:
            self.ws_thread.start()

    async def websocket_client(self):
        uri = "ws://localhost:8765"
        async with websockets.connect(uri) as websocket:
            self.ws_client = websocket
            try:
                async for message in websocket:
                    data = json.loads(message)
                    self.handle_sensor_data(data)
            except Exception as e:
                print(f"WebSocket error: {str(e)}")

    def handle_sensor_data(self, data):
        """Route sensor data to appropriate VideoWidget"""
        print("Received sensor data:", data)
        loc_id = data.get('loc_id')
        if not loc_id:
            # Try resolving via client_ip mapping
            client_ip = data.get('client_ip')
            if client_ip:
                try:
                    from ip_loc_resolver import get_loc_id
                    resolved = get_loc_id(client_ip)
                    if resolved:
                        loc_id = resolved
                except Exception as e:
                    print(f"IP→loc resolve error: {e}")
        print("Camera id:", loc_id)
        if not loc_id:
            return
            
        for widget in self.get_video_widgets():
            if widget.loc_id == loc_id:
                print(f"Updating widget {loc_id} with data: {data}")
                
                # Temperature is now updated from thermal matrix via set_thermal_overlay
                # in handle_tcp_sensor_data when frame packets are received
                
                # Update fire alarm if available
                if 'fire_alarm' in data:
                    widget.update_fire_alarm(data['fire_alarm'])
                
                break

    def get_video_widgets(self):
        """Get all VideoWidget instances in the grid"""
        widgets = []
        for i in range(self.rtsp_grid.count()):
            item = self.rtsp_grid.itemAt(i)
            if item and (widget := item.widget()):
                if isinstance(widget, VideoWidget):
                    widgets.append(widget)
        return widgets
    
    def init_rtsp_tab(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
        
        rtsp_tab = QWidget()
        if is_modern:
            rtsp_tab.setStyleSheet("background: #1a1a1a;")
        layout = QVBoxLayout(rtsp_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Container with position: relative for absolute positioning of nav buttons
        grid_container = QWidget()
        grid_container.setObjectName("gridContainer")
        if is_modern:
            grid_container.setStyleSheet("""
                #gridContainer {
                    background: #0a0a0a;
                }
            """)
        container_layout = QVBoxLayout(grid_container)
        container_layout.setContentsMargins(60, 10, 60, 10)  # Side margins for nav buttons
        container_layout.setSpacing(0)
        
        # Grid layout with minimal spacing for seamless look
        self.rtsp_grid = QGridLayout()
        self.rtsp_grid.setSpacing(0)  # No spacing between cells
        self.rtsp_grid.setContentsMargins(0, 0, 0, 0)
        
        grid_widget = QWidget()
        if is_modern:
            grid_widget.setStyleSheet("""
                QWidget {
                    background: transparent;
                }
            """)
        grid_widget.setLayout(self.rtsp_grid)
        container_layout.addWidget(grid_widget, 1)  # Stretch factor = 1 to expand
        
        # Page label at bottom center
        page_info_layout = QHBoxLayout()
        page_info_layout.addStretch()
        self.page_label = QLabel()
        self.page_label.setVisible(False)  # Hide page label
        if is_modern:
            self.page_label.setStyleSheet("""
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                padding: 8px 0;
                background: transparent;
            """)
        page_info_layout.addWidget(self.page_label)
        
        # Hide/Unhide toggle button for header and tabs (DISABLED FOR NOW)
        # TODO: Re-enable after fixing layout expansion issues
        # self.toggle_ui_btn = QPushButton("⊤")
        # page_info_layout.addWidget(self.toggle_ui_btn)
        
        page_info_layout.addStretch()
        container_layout.addLayout(page_info_layout)
        
        layout.addWidget(grid_container)
        
        # Edge-mounted navigation buttons (positioned absolutely via parent)
        # Left edge - Previous button
        self.prev_rtsp = QPushButton("◀", grid_container)
        self.prev_rtsp.clicked.connect(self.prev_rtsp_page)
        self.prev_rtsp.setFixedSize(50, 50)
        self.prev_rtsp.setCursor(Qt.PointingHandCursor)
        if is_modern:
            self.prev_rtsp.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 0, 0, 0.7);
                    border: 2px solid rgba(0, 188, 212, 0.5);
                    border-radius: 25px;
                    color: #00bcd4;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(0, 188, 212, 0.3);
                    border-color: #00bcd4;
                }
                QPushButton:pressed {
                    background-color: rgba(0, 188, 212, 0.5);
                }
            """)
        # Position at left edge, centered vertically
        self.prev_rtsp.move(10, grid_container.height() // 2 - 25)
        
        # Right edge - Next button
        self.next_rtsp = QPushButton("▶", grid_container)
        self.next_rtsp.clicked.connect(self.next_rtsp_page)
        self.next_rtsp.setFixedSize(50, 50)
        self.next_rtsp.setCursor(Qt.PointingHandCursor)
        if is_modern:
            self.next_rtsp.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 0, 0, 0.7);
                    border: 2px solid rgba(0, 188, 212, 0.5);
                    border-radius: 25px;
                    color: #00bcd4;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(0, 188, 212, 0.3);
                    border-color: #00bcd4;
                }
                QPushButton:pressed {
                    background-color: rgba(0, 188, 212, 0.5);
                }
            """)
        # Position at right edge, centered vertically
        def position_nav_buttons():
            if hasattr(self, 'prev_rtsp') and hasattr(self, 'next_rtsp'):
                self.prev_rtsp.move(10, grid_container.height() // 2 - 25)
                self.next_rtsp.move(grid_container.width() - 60, grid_container.height() // 2 - 25)
        
        # Store positioning function for resize events
        grid_container.resizeEvent = lambda e: position_nav_buttons()
        
        self.tabs.addTab(rtsp_tab, "VIDEOWALL" if is_modern else "Camera Feeds")
        self.update_rtsp_grid()

    def init_grafana_tab(self):
        """Initialize Grafana dashboard tab with embedded web view"""
        grafana_tab = QWidget()
        layout = QVBoxLayout(grafana_tab)
        
        # Control bar
        control_layout = QHBoxLayout()
        
        # URL input for Grafana server
        url_label = QLabel("Grafana URL:")
        self.grafana_url_input = QLineEdit()
        grafana_url = self.config.get('grafana_url', 'http://localhost:3000')
        self.grafana_url_input.setText(grafana_url)
        self.grafana_url_input.setPlaceholderText("http://localhost:3000/d/emberye-metrics")
        
        load_btn = QPushButton("Load Dashboard")
        refresh_btn = QPushButton("↻ Refresh")
        
        control_layout.addWidget(url_label)
        control_layout.addWidget(self.grafana_url_input)
        control_layout.addWidget(load_btn)
        control_layout.addWidget(refresh_btn)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # Web view for Grafana (only if WebEngine is available)
        if HAS_WEBENGINE:
            try:
                self.grafana_webview = QWebEngineView()
                self.grafana_webview.setMinimumHeight(600)
                # Load initial URL
                if grafana_url:
                    self.grafana_webview.setUrl(QUrl(grafana_url))
                layout.addWidget(self.grafana_webview)
                # Connect buttons
                load_btn.clicked.connect(self.load_grafana_dashboard)
                refresh_btn.clicked.connect(lambda: self.grafana_webview.reload())
            except Exception as e:
                HAS_WEBENGINE = False
        if not HAS_WEBENGINE:
            # Fallback if QWebEngineView is not available
            error_label = QLabel(
                f"Grafana Dashboard\n\n"
                f"QWebEngine not available.\n\n"
                f"To view metrics:\n"
                f"1. Install Grafana: https://grafana.com/grafana/download\n"
                f"2. Configure Prometheus datasource: http://localhost:9090\n"
                f"3. Import dashboard JSON from ADAPTIVE_FPS_METRICS_GUIDE.md\n"
                f"4. Access at: http://localhost:3000"
            )
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet("color: #666; font-size: 12px; padding: 20px;")
            layout.addWidget(error_label)
        
        self.tabs.addTab(grafana_tab, "📊 Metrics Dashboard")

    def load_grafana_dashboard(self):
        """Load Grafana dashboard from URL input"""
        try:
            url = self.grafana_url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "Invalid URL", "Please enter a valid Grafana URL")
                return
            
            if not url.startswith('http'):
                url = 'http://' + url
            
            # Save to config
            self.config['grafana_url'] = url
            StreamConfig.save_config(self.config)
            
            # Load in webview
            if hasattr(self, 'grafana_webview'):
                self.grafana_webview.setUrl(QUrl(url))
                self.statusBar().showMessage(f"Loading Grafana dashboard: {url}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load Grafana dashboard:\n{str(e)}")

    def init_graph_tab(self):
        graph_tab = QWidget()
        layout = QVBoxLayout(graph_tab)
        self.graph_stack = QVBoxLayout()
        layout.addLayout(self.graph_stack)
        
        page_layout = QHBoxLayout()
        self.prev_graph = QPushButton("Previous", clicked=self.prev_graph_page)
        self.next_graph = QPushButton("Next", clicked=self.next_graph_page)
        self.graph_label = QLabel()
        page_layout.addWidget(self.prev_graph)
        page_layout.addWidget(self.graph_label)
        page_layout.addWidget(self.next_graph)
        layout.addLayout(page_layout)
        
        self.tabs.addTab(graph_tab, "Analytics")
        self.update_graph()

    def showEvent(self, event):
        """Start WebSocket client when window is shown"""
        super().showEvent(event)
        if self.ws_client and hasattr(self.ws_client, 'start'):
            self.ws_client.start()

    def mouseMoveEvent(self, event):
        """Handle mouse hover to show/hide overlay header in Modern mode."""
        try:
            if hasattr(self, 'overlay_header') and self.overlay_header is not None:
                # Get cursor position relative to main window
                cursor_pos = event.pos()
                
                # Check if mouse is in header area (top 60px including header height)
                in_header_zone = cursor_pos.y() < 60
                
                if in_header_zone:
                    # Show header and cancel any hide timer
                    if not self.overlay_header.isVisible():
                        self.overlay_header.show()
                        self.overlay_header.raise_()
                        print("🔼 Header shown")
                    
                    # Cancel hide timer if active
                    if hasattr(self, 'header_hide_timer') and self.header_hide_timer:
                        self.header_hide_timer.stop()
                        self.header_hide_timer = None
                        self.header_countdown_seconds = 0
                        if hasattr(self, 'header_countdown_label'):
                            self.header_countdown_label.hide()
                        print("⏱️ Timer cancelled")
                else:
                    # Mouse outside header zone - start timer if header is visible
                    if self.overlay_header.isVisible():
                        if not hasattr(self, 'header_hide_timer') or self.header_hide_timer is None:
                            from PyQt5.QtCore import QTimer
                            self.header_countdown_seconds = 5
                            self.header_hide_timer = QTimer(self)
                            self.header_hide_timer.timeout.connect(self._update_header_countdown)
                            self.header_hide_timer.start(1000)  # Update every second
                            if hasattr(self, 'header_countdown_label'):
                                self.header_countdown_label.setText(f"⏱ Hiding in {self.header_countdown_seconds}s")
                                self.header_countdown_label.show()
                            print("⏱️ Timer started (5 seconds)")
        except Exception as e:
            print(f"❌ Mouse event error: {e}")
        
        super().mouseMoveEvent(event)
    
    def _update_header_countdown(self):
        """Update countdown timer and hide header when it reaches 0."""
        try:
            self.header_countdown_seconds -= 1
            
            if self.header_countdown_seconds <= 0:
                # Time's up - hide header
                if hasattr(self, 'overlay_header') and self.overlay_header:
                    self.overlay_header.hide()
                if hasattr(self, 'header_countdown_label'):
                    self.header_countdown_label.hide()
                if hasattr(self, 'header_hide_timer') and self.header_hide_timer:
                    self.header_hide_timer.stop()
                    self.header_hide_timer = None
                print("🔽 Header hidden (timer expired)")
            else:
                # Update countdown display
                if hasattr(self, 'header_countdown_label'):
                    self.header_countdown_label.setText(f"⏱ Hiding in {self.header_countdown_seconds}s")
        except Exception as e:
            print(f"❌ Countdown update error: {e}")
            pass

    
    # ==================== X-RAY EFFECT FEATURES ====================
    
    def eventFilter(self, obj, event):
        """
        Global event filter for X-ray effect:
        - Tracks mouse movement to auto-show/hide header and status bar
        - Implements cursor auto-hide after inactivity
        """
        try:
            from PyQt5.QtCore import QEvent
            from PyQt5.QtGui import QCursor
            
            if event.type() == QEvent.MouseMove:
                # Reset cursor hide timer on any mouse movement
                if hasattr(self, 'cursor_hide_timer'):
                    self.cursor_hide_timer.stop()
                    self._show_cursor()
                    self.cursor_hide_timer.start(self.cursor_hide_seconds * 1000)
                
                # X-ray effect: Show header (overlay_header) when mouse near edges
                if hasattr(self, 'overlay_header') and hasattr(self, 'header_visible'):
                    cursor_pos = QCursor.pos()
                    window_pos = self.mapFromGlobal(cursor_pos)

                    # Show header if mouse within 50px of top OR bottom zone is active
                    if (window_pos.y() < 50 or window_pos.y() > (self.height() - 50)) and not self.header_visible:
                        try:
                            self.overlay_header.show()
                            self.overlay_header.raise_()
                        except Exception:
                            pass
                        self.header_visible = True
                    # Hide header if mouse moves away and not in maximized view
                    elif window_pos.y() > 150 and self.header_visible and self.maximized_widget is None:
                        try:
                            self.overlay_header.hide()
                        except Exception:
                            pass
                        self.header_visible = False
                
                # X-ray effect: Show status bar when mouse near bottom (also show header)
                if hasattr(self, 'statusBar') and hasattr(self, 'statusbar_visible'):
                    cursor_pos = QCursor.pos()
                    window_pos = self.mapFromGlobal(cursor_pos)
                    window_height = self.height()
                    
                    # Show status bar if mouse within 50px of bottom
                    if window_pos.y() > window_height - 50 and not self.statusbar_visible:
                        self.statusBar().show()
                        self.statusbar_visible = True
                        # Also ensure header is visible when bottom bar shows
                        if hasattr(self, 'overlay_header') and hasattr(self, 'header_visible') and not self.header_visible:
                            try:
                                self.overlay_header.show()
                                self.overlay_header.raise_()
                            except Exception:
                                pass
                            self.header_visible = True
                    # Hide status bar if mouse moves away
                    elif window_pos.y() < window_height - 100 and self.statusbar_visible:
                        self.statusBar().hide()
                        self.statusbar_visible = False
            
            elif event.type() == QEvent.KeyPress:
                # Any key press resets cursor timer
                if hasattr(self, 'cursor_hide_timer'):
                    self.cursor_hide_timer.stop()
                    self._show_cursor()
                    self.cursor_hide_timer.start(self.cursor_hide_seconds * 1000)
        
        except Exception as e:
            print(f"Event filter error: {e}")
        
        # Always pass event to parent handler
        return super().eventFilter(obj, event)
    
    def _show_cursor(self):
        """Show cursor if currently hidden."""
        if not self.cursor_visible:
            self.unsetCursor()
            self.cursor_visible = True
    
    def _hide_cursor(self):
        """Hide cursor after inactivity (X-ray effect)."""
        from PyQt5.QtCore import Qt
        self.setCursor(Qt.BlankCursor)
        self.cursor_visible = False
    
    def cleanup_all_workers(self):
        """
        Comprehensive cleanup of all background workers and threads.
        Used for resource cleanup before window destruction.
        """
        print("Starting comprehensive resource cleanup...")
        
        # Stop video widgets
        try:
            self.shutdown_video_widgets()
        except Exception as e:
            print(f"Video widget cleanup error: {e}")
        
        # Stop WebSocket client
        try:
            if hasattr(self, 'ws_client') and self.ws_client:
                self.ws_client.stop()
        except Exception as e:
            print(f"WebSocket cleanup error: {e}")
        
        # Stop TCP server
        try:
            if hasattr(self, 'tcp_server') and self.tcp_server:
                tcp_mode = self.config.get('tcp_mode', 'threaded')
                if tcp_mode == 'async':
                    import asyncio
                    if hasattr(self, '_async_loop') and self._async_loop:
                        fut = asyncio.run_coroutine_threadsafe(self.tcp_server.stop(), self._async_loop)
                        try:
                            fut.result(timeout=2)
                        except Exception:
                            pass
                else:
                    self.tcp_server.stop()
        except Exception as e:
            print(f"TCP server cleanup error: {e}")
        
        # Stop PFDS scheduler
        try:
            if hasattr(self, 'pfds') and self.pfds:
                self.pfds.stop_scheduler()
        except Exception as e:
            print(f"PFDS cleanup error: {e}")
        
        # Stop metrics server
        try:
            if hasattr(self, 'metrics_server') and self.metrics_server:
                self.metrics_server.stop()
        except Exception as e:
            print(f"Metrics server cleanup error: {e}")
        
        # Stop cursor hide timer
        try:
            if hasattr(self, 'cursor_hide_timer'):
                self.cursor_hide_timer.stop()
        except Exception as e:
            print(f"Cursor timer cleanup error: {e}")
        
        print("Resource cleanup complete")
    
    def __del__(self):
        """Destructor: Ensure all resources released when object is destroyed."""
        try:
            self.cleanup_all_workers()
        except Exception as e:
            print(f"Destructor cleanup error: {e}")
    
    # ==================== END X-RAY EFFECT FEATURES ====================

    def closeEvent(self, event):
        """Ensure all background threads and resources stop cleanly before window closes"""
        # Use comprehensive cleanup first
        try:
            self.cleanup_all_workers()
        except Exception as e:
            print(f"Comprehensive cleanup error: {e}")
        
        # Save baselines/events
        try:
            self.baseline_manager.save_to_disk()
        except Exception as e:
            print(f"Baseline save error: {e}")
        
        super().closeEvent(event)


    def schedule_grid_rebuild(self):
        """Schedule grid rebuild using QTimer to prevent UI blocking."""
        if not self.grid_rebuild_pending:
            self.grid_rebuild_pending = True
            # Clean up old widgets asynchronously first
            QTimer.singleShot(0, self.cleanup_old_widgets)
    
    def cleanup_old_widgets(self):
        """Asynchronously clean up old video widgets before rebuild."""
        try:
            while self.rtsp_grid.count():
                item = self.rtsp_grid.takeAt(0)
                widget = item.widget()
                if widget:
                    # Non-blocking stop (already optimized in video_widget.py)
                    if hasattr(widget, 'stop'):
                        try:
                            widget.stop()
                        except Exception as e:
                            print(f"Error stopping widget: {e}")
                    widget.deleteLater()
            # Schedule actual rebuild after cleanup completes
            QTimer.singleShot(100, self.do_grid_rebuild)
        except Exception as e:
            print(f"Cleanup error: {e}")
            self.grid_rebuild_pending = False
    
    def do_grid_rebuild(self):
        """Perform the actual grid rebuild after cleanup."""
        try:
            self.update_rtsp_grid()
        finally:
            self.grid_rebuild_pending = False

    def update_rtsp_grid(self):
        try:
            # Check theme for styling
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
            
            # Grid is already cleared by cleanup_old_widgets when called via schedule

            filtered_streams = [
                s for s in self.config["streams"]
                if s["group"] == self.current_group
            ]
            
            if not filtered_streams:
                no_streams_label = QLabel(f"No streams in {self.current_group} group")
                no_streams_label.setAlignment(Qt.AlignCenter)
                self.rtsp_grid.addWidget(no_streams_label, 0, 0)
                self.page_label.setText("Page 0 of 0")
                return

            rows, cols = map(int, self.grid_size.currentText().replace("×", "x").split("x"))
            feeds_per_page = rows * cols
            total_streams = len(filtered_streams)
            total_pages = max(1, (total_streams + feeds_per_page - 1) // feeds_per_page)
            self.current_rtsp_page = max(1, min(self.current_rtsp_page, total_pages))
            start = (self.current_rtsp_page - 1) * feeds_per_page
            end = min(start + feeds_per_page, total_streams)

            for idx in range(start, end):
                stream = filtered_streams[idx]
                position = idx - start
                row = position // cols
                col = position % cols
                
                try:
                    video_widget = VideoWidget(stream["url"], stream['name'], stream['loc_id'])
                    self.video_widgets[stream['loc_id']] = video_widget
                    video_widget.setToolTip(f"{stream['name']}\n{stream['url']}")
                    
                    # Modern: Cleaner name label overlay
                    name_label = QLabel(stream["name"], video_widget)
                    if is_modern:
                        name_label.setStyleSheet("""
                            background-color: rgba(0, 0, 0, 0.65);
                            color: #00bcd4;
                            padding: 4px 8px;
                            border-radius: 4px;
                            font-weight: 600;
                            font-size: 11px;
                            border: 1px solid rgba(0, 188, 212, 0.3);
                        """)
                    else:
                        name_label.setStyleSheet("""
                            background-color: rgba(0, 0, 0, 150);
                            color: white;
                            padding: 2px;
                            border-radius: 3px;
                        """)
                    name_label.move(5, 5)

                    # Connect signals
                    # video_widget.maximize_requested.connect(self.handle_maximize)
                    # video_widget.minimize_requested.connect(self.handle_minimize)
                    video_widget.maximize_requested.connect(
                        self.handle_maximize, 
                        Qt.QueuedConnection
                    )
                    video_widget.minimize_requested.connect(
                        self.handle_minimize, 
                        Qt.QueuedConnection
                    )
                    # Update status
                    video_widget.update_fire_alarm(True)
                    video_widget.set_temperature(22.5)


                    self.rtsp_grid.addWidget(video_widget, row, col)
                except Exception as e:
                    error_label = QLabel(f"{stream['name']}\nError: {str(e)}")
                    error_label.setAlignment(Qt.AlignCenter)
                    error_label.setStyleSheet("color: red; background-color: black;")
                    self.rtsp_grid.addWidget(error_label, row, col)

            self.page_label.setText(f"Page {self.current_rtsp_page} of {total_pages}")
            self.prev_rtsp.setEnabled(self.current_rtsp_page > 1)
            self.next_rtsp.setEnabled(end < total_streams)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Grid update failed: {str(e)}")
            self.current_rtsp_page = 1
            self.update_rtsp_grid()

    def update_graph(self):
        try:
            # Lazy import matplotlib only when needed
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            import matplotlib.pyplot as plt
            
            for i in reversed(range(self.graph_stack.count())): 
                self.graph_stack.itemAt(i).widget().deleteLater()
            
            figure = plt.figure()
            canvas = FigureCanvas(figure)
            ax = figure.add_subplot(111)
            
            if self.current_graph_page == 1:
                x = np.linspace(0, 10, 100)
                ax.plot(x, np.sin(x))
                ax.set_title("Sine Wave")
            else:
                categories = ["A", "B", "C"]
                values = np.random.randint(1, 10, 3)
                ax.bar(categories, values)
                ax.set_title("Random Data")
            
            canvas.draw()
            self.graph_stack.addWidget(canvas)
            self.graph_label.setText(f"Graph {self.current_graph_page}/2")
            self.prev_graph.setEnabled(self.current_graph_page > 1)
            self.next_graph.setEnabled(self.current_graph_page < 2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Graph update failed: {str(e)}")

    def handle_maximize(self):
        """Handle maximize with button state management - use full grid space"""
        try:
            sender = self.sender()
            if not sender or not isinstance(sender, VideoWidget):
                return

            # If a different widget is maximized, restore it first
            if self.maximized_widget and self.maximized_widget != sender:
                self.handle_minimize()

            # If already maximized, don't toggle back - stay maximized
            if self.maximized_widget == sender:
                return

            # Store original state
            self.original_layout = {
                'visible': [],
                'hidden': []
            }

            # Update button visibility
            sender.maximize_btn.setVisible(False)  # Hide maximize
            sender.minimize_btn.setVisible(True)   # Show minimize

            # Hide other widgets and store state
            for i in range(self.rtsp_grid.count()):
                item = self.rtsp_grid.itemAt(i)
                if item and (widget := item.widget()):
                    if widget == sender:
                        widget.raise_()
                        self.maximized_widget = widget
                    else:
                        widget.hide()
                        self.original_layout['hidden'].append(widget)
                    self.original_layout['visible'].append(widget)

            self.rtsp_grid.setContentsMargins(0, 0, 0, 0)
            self.rtsp_grid.setSpacing(0)
            sender.setFocus()
            self.rtsp_grid.update()

        except Exception as e:
            print(f"Maximize error: {str(e)}")

    def handle_minimize(self):
        """Restore to grid view - show all hidden widgets"""
        try:
            if not self.maximized_widget:
                return

            # Restore button visibility for the previously maximized widget
            self.maximized_widget.maximize_btn.setVisible(True)  # Show maximize
            self.maximized_widget.minimize_btn.setVisible(False)  # Hide minimize

            # Restore visibility of all hidden widgets
            for widget in self.original_layout.get('hidden', []):
                if widget and widget.parent():
                    widget.show()

            self.maximized_widget = None
            self.rtsp_grid.setContentsMargins(0, 0, 0, 0)
            self.rtsp_grid.setSpacing(0)
            self.rtsp_grid.update()

        except Exception as e:
            print(f"Minimize error: {str(e)}")

    def restore_layout(self):
        """Restore layout without deleting widgets"""
        try:
            # Show all widgets that were hidden
            for i in range(self.rtsp_grid.count()):
                item = self.rtsp_grid.itemAt(i)
                if item and (widget := item.widget()):
                    if widget != self.maximized_widget:
                        widget.show()
            
            self.maximized_widget = None
            self.rtsp_grid.update()
        except Exception as e:
            print(f"Restore layout error: {str(e)}")

    def toggle_ui_visibility(self):
        """Toggle visibility of overlay header and tabs widget"""
        try:
            self.ui_hidden = not self.ui_hidden
            
            # Toggle overlay header
            if hasattr(self, 'overlay_header'):
                self.overlay_header.setVisible(not self.ui_hidden)
            
            # Toggle tabs widget
            if hasattr(self, 'tabs'):
                self.tabs.setVisible(not self.ui_hidden)
            
            # Force layout to recalculate and expand grid to fill space
            central = self.centralWidget()
            if central and central.layout():
                central.layout().update()
            
            if hasattr(self, 'rtsp_grid'):
                self.rtsp_grid.update()
            
            # Update button icon based on state
            if self.ui_hidden:
                self.toggle_ui_btn.setText("⊥")  # Down arrow when hidden
                self.toggle_ui_btn.setToolTip("Show header and tabs (Click to restore)")
            else:
                self.toggle_ui_btn.setText("⊤")  # Up arrow when visible
                self.toggle_ui_btn.setToolTip("Hide header and tabs (Click to maximize view)")
                
        except Exception as e:
            print(f"Toggle UI visibility error: {str(e)}")






    def group_changed(self, group):
        self.current_group = group
        self.current_rtsp_page = 1
        # Use scheduled rebuild for smoother group switching
        if hasattr(self, 'grid_rebuild_pending'):
            self.schedule_grid_rebuild()
        else:
            self.update_rtsp_grid()

    def configure_streams(self):
        dialog = StreamConfigDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            self.config = dialog.get_config()
            StreamConfig.save_config(self.config)
            self.group_combo.clear()
            self.group_combo.addItems(self.config["groups"])
            # Defer grid rebuild to avoid blocking UI during cleanup
            self.schedule_grid_rebuild()

    def reset_streams(self):
        """Clear all configured streams and reset to default group layout."""
        reply = QMessageBox.question(
            self,
            "Reset Streams",
            "This will remove all configured streams and reset to a blank default configuration. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        # Build default empty configuration
        default_config = {"groups": ["Default"], "streams": [], "tcp_port": self.config.get("tcp_port", 9000)}
        if StreamConfig.save_config(default_config):
            self.config = default_config
            self.group_combo.clear()
            self.group_combo.addItems(self.config["groups"])
            self.current_group = "Default"
            self.current_rtsp_page = 1
            self.schedule_grid_rebuild()
            QMessageBox.information(self, "Streams Reset", "Stream configuration has been cleared.")
        else:
            QMessageBox.critical(self, "Error", "Failed to reset stream configuration.")

    def show_profile(self):
        profile_dialog = QDialog(self)
        profile_dialog.setWindowTitle("User Profile")
        profile_dialog.setFixedSize(300, 200)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Username: admin"))
        layout.addWidget(QLabel("Email: admin@example.com"))
        close_btn = QPushButton("Close", clicked=profile_dialog.close)
        layout.addWidget(close_btn)
        profile_dialog.setLayout(layout)
        profile_dialog.exec_()

    def prev_rtsp_page(self):
        self.current_rtsp_page = max(1, self.current_rtsp_page - 1)
        self.update_rtsp_grid()

    def next_rtsp_page(self):
        self.current_rtsp_page += 1
        self.update_rtsp_grid()

    def prev_graph_page(self):
        self.current_graph_page = max(1, self.current_graph_page - 1)
        self.update_graph()

    def next_graph_page(self):
        self.current_graph_page = min(2, self.current_graph_page + 1)
        self.update_graph()

    def logout(self):
        """Perform orderly shutdown before closing and returning to login."""
        print("Logout initiated - shutting down components...")
        
        # Stop video widgets first
        self.shutdown_video_widgets()
        
        # Stop WebSocket client
        if hasattr(self, 'ws_client'):
            try:
                print("Stopping WebSocket client...")
                self.ws_client.stop()
            except Exception as e:
                print(f"WebSocket stop during logout error: {e}")
        
        # Stop TCP sensor server
        if hasattr(self, 'tcp_server') and self.tcp_server:
            try:
                print("Stopping TCP sensor server...")
                self.tcp_server.stop()
            except Exception as e:
                print(f"TCP server stop during logout error: {e}")
        
        # Stop baseline manager sensor server if it exists
        if hasattr(self.parent(), 'server') and getattr(self.parent(), 'server'):
            try:
                print("Stopping parent sensor server...")
                self.parent().server.stop()
            except Exception as e:
                print(f"Parent sensor server stop during logout error: {e}")
        
        print("Cleanup complete, returning to login...")
        self.close()
        
        # Show login window
        from ee_loginwindow import EELoginWindow
        login_window = EELoginWindow()
        login_window.show()

    def shutdown_video_widgets(self):
        """Iterate all video widgets and ensure their worker threads stop."""
        for widget in self.get_video_widgets():
            if hasattr(widget, 'stop'):
                try:
                    widget.stop()
                except Exception as e:
                    print(f"Error stopping video widget ({getattr(widget, 'loc_id', 'unknown')}): {e}")


# Training worker thread
class TrainingWorker(QThread):
    finished_signal = pyqtSignal(bool, str, object)
    progress_signal = pyqtSignal(int, str)  # (progress_percent, message)
    epoch_progress_signal = pyqtSignal(int, int)  # (current_epoch, total_epochs)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            self.progress_signal.emit(5, "Preparing dataset…")
            self.epoch_progress_signal.emit(0, self.config.epochs)
            
            from training_pipeline import YOLOTrainingPipeline
            pipeline = YOLOTrainingPipeline(base_dir="training_data", config=self.config)
            
            # Set up epoch progress callback
            def epoch_callback(current, total):
                """Called after each epoch completes."""
                self.epoch_progress_signal.emit(current, total)
                # Update progress bar based on epoch completion
                progress_pct = int((current / total) * 90) + 5  # 5-95% range during training
                self.progress_signal.emit(progress_pct, f"Training epoch {current}/{total}")
            
            pipeline.set_epoch_callback(epoch_callback)
            
            # Set up rich progress callback (loss/mAP/ETA) if available
            try:
                def on_progress(p):
                    # p is TrainingProgress from pipeline; compute progress percent
                    total = getattr(p, 'total_epochs', self.config.epochs) or self.config.epochs
                    current = getattr(p, 'current_epoch', 0)
                    progress_pct = int((current / total) * 90) + 5 if total else 5
                    # Build concise status message with metrics when present
                    loss = getattr(p, 'loss', 0.0) or 0.0
                    map50 = getattr(p, 'map50', 0.0) or 0.0
                    eta = getattr(p, 'eta_seconds', 0) or 0
                    # Format ETA mm:ss
                    eta_txt = f", ETA {int(eta//60)}m {int(eta%60)}s" if eta else ""
                    msg = getattr(p, 'message', '') or f"Epoch {current}/{total} - loss {loss:.4f}, mAP50 {map50:.4f}{eta_txt}"
                    self.progress_signal.emit(progress_pct, msg)
                pipeline.set_progress_callback(on_progress)
            except Exception:
                pass
            
            # Start training with periodic progress updates
            ok, msg = pipeline.run_full_pipeline()
            best_model = pipeline.get_best_model_path()
            
            # Get final epoch count from pipeline
            final_epochs = getattr(pipeline.progress, 'current_epoch', self.config.epochs)
            self.epoch_progress_signal.emit(final_epochs, self.config.epochs)
            
            # Emit final progress
            status_msg = f"Training complete - {final_epochs} epochs" if ok else "Training failed"
            self.progress_signal.emit(100 if ok else 0, status_msg)
            result_payload = {
                'best_model': str(best_model) if best_model else None,
                'metrics': getattr(pipeline, 'final_metrics', {}) or {},
                'train_seconds': getattr(pipeline, 'train_seconds', 0) or 0,
            }
            self.finished_signal.emit(ok, msg, result_payload)
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"TrainingWorker error: {error_detail}")
            self.finished_signal.emit(False, str(e), None)
