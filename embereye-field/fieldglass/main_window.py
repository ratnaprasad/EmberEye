import os
import time
import shutil
import logging
import numpy as np
import websockets
import json
import asyncio
import cv2
import sys
from typing import List
from pathlib import Path
from threading import Thread, Event
import subprocess

# Prefer fieldglass modules first, then parent directory for root-level utilities
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stream_config import StreamConfig
from resource_helper import get_resource_path, get_data_path, ensure_runtime_folders
from tcp_server_logger import log_info as log_server_info, log_error as log_server_error
from debug_config import debug_print, is_debug_enabled, set_debug_enabled
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTabWidget, QMessageBox,
    QToolButton, QMenu, QStyle, QFileDialog, QGridLayout, QPushButton, QDialog, QLineEdit,
    QListWidget, QListWidgetItem, QProgressBar, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QSlider, QGroupBox, QCompleter, QCheckBox, QDoubleSpinBox, QFormLayout, QInputDialog,
    QProgressDialog, QApplication
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QMutex, QObject, QTimer, QUrl, QThread
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
from embereye.core.sensor_fusion import SensorFusion
from embereye.core.pipeline_logs import VISION_LOG, FUSION_LOG, log_fusion_event
from baseline_manager import BaselineManager
from hawkcore.emberhawk_manager import EmberHawkManager, is_valid_ip
from embereye.core.class_config import load_master_classes, get_leaf_classes
from master_class_config_dialog import MasterClassConfigDialog
from incidents import (
    ThermalROIExtractor,
    IncidentRecord,
    IncidentsManager,
    ThermalVisionAnalyzer
)
from embersync import IncidentExporter, IncidentExportMetadata, DetectionFrame
from embereye.core.vision_detector import VisionDetector, SEVERITY_RANK

logger = logging.getLogger(__name__)


class WebSocketClient(QObject):
    data_received = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
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
        self.connect_event.wait(5)

    def run_client(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.client_main())
        finally:
            self.loop.close()

    async def client_main(self):
        uri = "ws://localhost:8765"
        try:
            async with websockets.connect(uri) as ws:
                self.mutex.lock()
                self.websocket = ws
                self.connect_event.set()
                self.mutex.unlock()

                while self.running:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(message)
                        self.data_received.emit(data)
                    except asyncio.TimeoutError:
                        continue
        except Exception as e:
            print(f"WebSocket error: {str(e)}")
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
                future = asyncio.run_coroutine_threadsafe(self._close_websocket(), self.loop)
                future.result(timeout=2)
            except Exception as e:
                print(f"WebSocket close error: {e}")

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

    def _fallback_dispatch_emberhawk_command(self, *args, **kwargs):
        """Fallback for EmberHawk device commands when manager unavailable."""
        try:
            print(f"[FALLBACK] EmberHawk command: {args} {kwargs}")
        except Exception:
            pass

    def _fallback_update_rtsp_grid(self, *args, **kwargs):
        """Fallback for RTSP grid updates."""
        try:
            pass
        except Exception:
            pass

    def _fallback_handle_sensor_data(self, *args, **kwargs):
        """Fallback for sensor data handling."""
        try:
            pass
        except Exception:
            pass

    def _fallback_group_changed(self, *args, **kwargs):
        """Fallback for group changed events."""
        try:
            pass
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
        if name == 'dispatch_emberhawk_command':
            return self._fallback_dispatch_emberhawk_command
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

    def _on_screen_geometry_changed(self, *args, **kwargs):
        """Adjust window when screen resolution changes.
        If maximized, re-maximize to fit new available area; otherwise resize to available geometry.
        """
        try:
            from PyQt5.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            avail = screen.availableGeometry()
            if self.isMaximized():
                self.showMaximized()
            else:
                self.setGeometry(avail)
        except Exception:
            pass
    
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
                try:
                    log_fusion_event(str(loc_id), f"source=vision_only vision_score={float(score):.3f} alarm={fusion_result.get('alarm')} confidence={float(fusion_result.get('confidence', 0.0)):.3f} reason={fusion_result.get('alarm_reason', '-')}")
                except Exception:
                    pass
                try:
                    key = str(loc_id) if loc_id is not None else "_broadcast"
                    self._fusion_by_loc_id[key] = fusion_result
                    self._fusion_ts_by_loc_id[key] = time.time()
                except Exception:
                    pass
                if hasattr(widget, 'update_fire_alarm'):
                    try:
                        widget.update_fire_alarm(fusion_result['alarm'])
                    except Exception as e:
                        print(f"Alarm update error (vision): {e}")
                break

    def _evaluate_rule_alarm(self, detections, yolo_score=0.0, fusion_result=None):
        """Evaluate rule-based alarm from detection classes."""
        result = {
            'rule_alarm': False,
            'severity': 'NORMAL',
            'reasons': [],
            'score': 0,
        }
        if not detections or not self._rule_engine:
            return result
        try:
            threat = self._rule_engine._classify_detections(detections, context=None)
            severity = threat.get('severity', 'NORMAL')
            reasons = threat.get('reasons', []) or []
            score = threat.get('score', 0)
            rule_alarm = False

            if severity == 'CRITICAL':
                rule_alarm = True
            elif severity == 'HIGH':
                if yolo_score >= self._rule_min_yolo_conf:
                    rule_alarm = True
                elif fusion_result and float(fusion_result.get('confidence', 0.0)) >= self._rule_min_fusion_conf:
                    rule_alarm = True

            result.update({
                'rule_alarm': rule_alarm,
                'severity': severity,
                'reasons': reasons,
                'score': score,
            })
        except Exception as e:
            print(f"Rule evaluation error: {e}")
        return result

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

            # Incidents settings (accept legacy anomaly keys)
            self.incident_threshold = float(settings.get('incident_threshold', settings.get('anomaly_threshold', self.incident_threshold)))
            self._incident_max_items = int(settings.get('incident_max_items', settings.get('anomaly_max_items', self._incident_max_items)))
            self.incident_save_enabled = bool(settings.get('incident_save_enabled', settings.get('anomaly_save_enabled', self.incident_save_enabled)))
            import os
            self.incident_save_dir = settings.get('incident_save_dir', settings.get('anomaly_save_dir', self.incident_save_dir)) or self.incident_save_dir
            self.incident_retention_days = int(settings.get('incident_retention_days', settings.get('anomaly_retention_days', self.incident_retention_days)))

            # Backward-compatible mirrors
            self.anomaly_threshold = self.incident_threshold
            self._anomaly_max_items = self._incident_max_items
            self.anomaly_save_enabled = self.incident_save_enabled
            self.anomaly_save_dir = self.incident_save_dir
            self.anomaly_retention_days = self.incident_retention_days

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
                 emberhawk=None, async_loop=None, async_thread=None):
        """
        Initialize MainWindow with optional server reuse for efficiency.
        
        Args:
            theme_manager: Theme manager instance
            tcp_server: Existing TCP server to reuse (avoids port conflicts)
            tcp_sensor_server: Alias for tcp_server
            emberhawk: Existing EmberHawk manager instance
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
        # Incidents config defaults
        import os
        self.incident_threshold = 0.4
        self.incident_save_enabled = False
        self.incident_save_dir = os.path.join(os.path.dirname(__file__), 'incidents')
        self.incident_retention_days = 7
        self._last_incident_cleanup = 0
        self._incident_max_items = 200
        # EEPROM calibration tracking
        self.eeprom_last_update = None  # Track when EEPROM was last fetched
        self.eeprom_offset = 0.0  # Current calibration offset
        
        # Reusable async infrastructure
        self._async_loop = async_loop
        self._async_thread = async_thread
        self._emberhawk = emberhawk  # Reuse EmberHawk manager if provided
        
        # --- Sensor Fusion ---
        # Initialize SensorFusion BEFORE initUI to avoid AttributeError
        smoke_thr = float(self.config.get('smoke_threshold_pct', 25.0))
        flame_thr = float(self.config.get('flame_threshold_pct', 25.0))
        temp_thr = float(self.config.get('temp_threshold', 40.0))
        gas_thr = float(self.config.get('gas_ppm_threshold', 400))
        vision_thr = float(self.config.get('vision_threshold', 0.7))
        vision_weight = float(self.config.get('vision_confidence_weight', 0.5))
        self.sensor_fusion = SensorFusion(temp_threshold=temp_thr,
                          gas_ppm_threshold=gas_thr,
                          smoke_threshold_pct=smoke_thr,
                  flame_threshold_pct=flame_thr,
                  vision_threshold=vision_thr,
                  vision_confidence_weight=vision_weight)
        print(f"Loaded fusion thresholds: Smoke={smoke_thr}%, Flame={flame_thr}%, Temp={temp_thr}°C, Gas={gas_thr}ppm, VisionThr={vision_thr}, VisionWeight={vision_weight}")
        # Hybrid alarm support (rules + fusion)
        self._fusion_by_loc_id = {}
        self._fusion_ts_by_loc_id = {}
        try:
            self._rule_engine = VisionDetector(yolo_model_path="__no_model__")
        except Exception:
            self._rule_engine = None
        self.heuristic_threshold = float(self.config.get('heuristic_threshold', 0.20))
        self.force_yolo_every_n_frames = int(self.config.get('force_yolo_every_n_frames', 10))
        self.yolo_conf_threshold = float(self.config.get('yolo_conf_threshold', 0.05))
        self.possible_conf_threshold = float(self.config.get('possible_conf_threshold', 0.60))
        self.confirmed_conf_threshold = float(self.config.get('confirmed_conf_threshold', 0.80))
        if self.confirmed_conf_threshold <= self.possible_conf_threshold:
            self.confirmed_conf_threshold = min(1.0, self.possible_conf_threshold + 0.05)
        self._rule_min_fusion_conf = float(self.config.get('rule_min_fusion_conf', 0.3))
        self._rule_min_yolo_conf = float(self.config.get('rule_min_yolo_conf', 0.6))
        self.detection_box_mode = str(self.config.get('detection_box_mode', 'all')).strip().lower()
        if self.detection_box_mode not in ('all', 'specific'):
            self.detection_box_mode = 'all'
        raw_box_classes = self.config.get('detection_box_classes', [])
        if not isinstance(raw_box_classes, list):
            raw_box_classes = []
        self.detection_box_classes = [str(class_name).strip() for class_name in raw_box_classes if str(class_name).strip()]
        os.environ['EMBEREYE_BBOX_MODE'] = self.detection_box_mode
        os.environ['EMBEREYE_BBOX_CLASSES'] = ';'.join(self.detection_box_classes)
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
        
        # EmberHawk manager + scheduler (reuse if provided)
        if self._emberhawk is not None:
            self.emberhawk = self._emberhawk
            print("Reusing existing EmberHawk manager")
        else:
            self.emberhawk = EmberHawkManager()
            self.emberhawk.set_dispatcher(self.dispatch_emberhawk_command)
            self.emberhawk.start_scheduler()
        
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
                    from embereye.core.tcp_async_server import TCPAsyncSensorServer
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
                    from embereye.core.tcp_sensor_server import TCPSensorServer
                    self.tcp_server = TCPSensorServer(port=self.tcp_server_port, packet_callback=self._emit_tcp_packet)
                    self.tcp_sensor_server = self.tcp_server  # Alias for pfds_manager commands
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
            pkt_type = packet.get('type') if isinstance(packet, dict) else 'unknown'
            print(f"📡 TCP PACKET RECEIVED: type={pkt_type}, keys={list(packet.keys()) if isinstance(packet, dict) else 'N/A'}")
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
                print(f"🔥 THERMAL FRAME: loc_id={loc_id}, widgets_available={len(self.video_widgets)}, target_widgets={len(target_widgets)}, matrix_shape={np.array(packet['matrix']).shape if packet['matrix'] else None}")
                for widget in target_widgets:
                    if widget and hasattr(widget, 'set_thermal_overlay'):
                        try:
                            widget.set_thermal_overlay(packet['matrix'])
                            print(f"  ✅ Thermal overlay set on widget")
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
                try:
                    log_fusion_event(
                        str(loc_id),
                        f"source=sensor_packet args={','.join(sorted(fusion_args.keys()))} alarm={fusion_result.get('alarm')} confidence={float(fusion_result.get('confidence', 0.0)):.3f} reason={fusion_result.get('alarm_reason', '-')}")
                except Exception:
                    pass
                try:
                    key = str(loc_id) if loc_id is not None else "_broadcast"
                    self._fusion_by_loc_id[key] = fusion_result
                    self._fusion_ts_by_loc_id[key] = time.time()
                except Exception:
                    pass
                
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
                                hot_cells = fusion_result['hot_cells']
                                widget.set_hot_cells(hot_cells)
                                print(f"  🔥 Hot cells set: {len(hot_cells)} cells detected, alarm={fusion_result.get('alarm')}, reason={fusion_result.get('alarm_reason')}")
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
            # Adapt initial size to current screen resolution
            try:
                from PyQt5.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
                avail = screen.availableGeometry()
                self.setGeometry(avail)
            except Exception:
                self.setGeometry(100, 100, 1024, 768)
            if is_modern:
                self.showMaximized()
            # React to resolution changes (monitor switch or scaling changes)
            try:
                from PyQt5.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
                screen.geometryChanged.connect(self._on_screen_geometry_changed)
                try:
                    screen.availableGeometryChanged.connect(self._on_screen_geometry_changed)
                except Exception:
                    pass
            except Exception:
                pass
            
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
            
            # Tab Widget with centered tabs
            self.tabs = QTabWidget()
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
            
            main_layout.addWidget(self.tabs)
            
            self.init_rtsp_tab()
            # Conditionally initialize Grafana metrics tab if enabled in config
            if self.config.get('enable_grafana', False):
                self.init_grafana_tab()
            # Always initialize Incidents tab
            self.init_incidents_tab()
            # Training Manager removed - Studio-only feature
            # Field Edition focuses on monitoring and detection
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
                # Reduce mouse move events from status bar to avoid hover flicker
                try:
                    status_bar.setMouseTracking(False)
                except Exception:
                    pass
                # Track hover zone transitions to avoid rapid toggling
                self._was_in_bottom_zone = False
                self._was_in_top_zone = False
                # Timer-based hide for status bar to prevent thrashing
                self.status_hide_timer = None
            
            # Initialize TCP status indicator
            self.init_tcp_status_indicator()
            self.statusBar().showMessage("System Ready")
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Initialization failed: {str(e)}")

    def init_incidents_tab(self):
        """Create an Incidents tab showing captured frames as thumbnails."""
        from PyQt5.QtWidgets import QListWidget, QListWidgetItem
        from PyQt5.QtCore import QSize
        incidents_tab = QWidget()
        layout = QVBoxLayout(incidents_tab)
        # Controls row
        controls = QHBoxLayout()
        self.incident_count_label = QLabel("Captured: 0")
        # Toggle capture button
        self.incident_capture_btn = QPushButton("⏸ Pause Capture")
        self.incident_capture_btn.setCheckable(True)
        self.incident_capture_enabled = True
        def toggle_capture():
            self.incident_capture_enabled = not self.incident_capture_btn.isChecked()
            self.incident_capture_btn.setText("▶ Resume Capture" if self.incident_capture_btn.isChecked() else "⏸ Pause Capture")
            print(f"Incident capture {'enabled' if self.incident_capture_enabled else 'disabled'}")
        self.incident_capture_btn.clicked.connect(toggle_capture)
        clear_btn = QPushButton("Clear All")
        open_btn = QPushButton("Open Folder")
        export_btn = QPushButton("Export Incidents")
        controls.addWidget(self.incident_count_label)
        controls.addStretch()
        controls.addWidget(self.incident_capture_btn)
        controls.addWidget(export_btn)
        controls.addWidget(open_btn)
        controls.addWidget(clear_btn)
        layout.addLayout(controls)
        # Thumbnails list
        self.incident_list = QListWidget()
        self.incident_list.setViewMode(self.incident_list.IconMode)
        self.incident_list.setIconSize(QSize(160, 120))
        self.incident_list.setResizeMode(self.incident_list.Adjust)
        self.incident_list.setSpacing(10)
        self.incident_list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.incident_list)

        # Storage for full images and metadata
        self._incidents_store = []  # list of dicts {pixmap, loc_id, score, ts}
        if not hasattr(self, '_incident_max_items'):
            self._incident_max_items = 200

        def on_clear():
            self._incidents_store.clear()
            self.incident_list.clear()
            self._update_incident_count()
        clear_btn.clicked.connect(on_clear)

        def on_open_folder():
            try:
                from PyQt5.QtGui import QDesktopServices
                from PyQt5.QtCore import QUrl
                import os
                path = getattr(self, 'incident_save_dir', '')
                if not path:
                    path = os.path.join(os.path.dirname(__file__), 'incidents')
                os.makedirs(path, exist_ok=True)
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except Exception as e:
                print(f"Open folder error: {e}")
        open_btn.clicked.connect(on_open_folder)

        def on_export():
            try:
                if self.incident_list.selectedItems():
                    self.export_selected_incidents_bundle()
                else:
                    self.export_incidents_bundle()
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Incident export failed: {e}")
        export_btn.clicked.connect(on_export)

        def on_open_preview(item):
            try:
                idx = item.data(Qt.UserRole)
                if idx is None or idx < 0 or idx >= len(self._incidents_store):
                    return
                entry = self._incidents_store[idx]
                # Show simple preview dialog
                dlg = QDialog(self)
                dlg.setWindowTitle(f"Incident • {entry['loc_id']} • {entry['score']:.2f}")
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
                print(f"Incident preview error: {e}")
        self.incident_list.itemDoubleClicked.connect(on_open_preview)

        # Determine tab label based on theme
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
        self.tabs.addTab(incidents_tab, "INCIDENTS" if is_modern else "Incidents")

    def init_training_manager_tab(self):
        """DISABLED: Training Manager tab is not available in Field Edition.
        
        Training functionality is reserved for EmberEye Studio.
        Field Edition focuses on monitoring and detection only.
        """
        # This method is intentionally disabled - training is a Studio-only feature
        pass

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

        # Verify / Export / Import on one line for alignment
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        verify_btn = QPushButton("Verify")
        verify_btn.setMaximumWidth(110)
        verify_btn.clicked.connect(self._sandbox_verify_model)
        actions_row.addWidget(verify_btn)
        
        export_btn = QPushButton("📦 Export")
        export_btn.setMaximumWidth(110)
        export_btn.clicked.connect(self._sandbox_export_model)
        actions_row.addWidget(export_btn)
        
        import_btn = QPushButton("📥 Import")
        import_btn.setMaximumWidth(110)
        import_btn.clicked.connect(self._sandbox_import_model)
        actions_row.addWidget(import_btn)
        actions_row.addStretch(1)
        
        model_layout.addLayout(actions_row)
        
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
        
        # Result image with overlay stats
        results_inner = QHBoxLayout()
        results_inner.setSpacing(6)
        
        self.sandbox_results_label = QLabel("Results appear here")
        self.sandbox_results_label.setAlignment(Qt.AlignCenter)
        self.sandbox_results_label.setStyleSheet("border: 1px solid #333; background: #111;")
        self.sandbox_results_label.setScaledContents(False)
        self.sandbox_results_label.setFixedHeight(380)
        self.sandbox_results_label.setMinimumWidth(420)
        self.sandbox_results_label.setMaximumWidth(500)
        results_inner.addWidget(self.sandbox_results_label)

        # Overlay stats on top-left of result frame (transparent, compact)
        self.sandbox_stats_overlay = QLabel("Waiting for inference...", self.sandbox_results_label)
        self.sandbox_stats_overlay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.sandbox_stats_overlay.setWordWrap(True)
        self.sandbox_stats_overlay.setFixedWidth(210)
        self.sandbox_stats_overlay.setMinimumHeight(150)
        self.sandbox_stats_overlay.move(10, 10)
        self.sandbox_stats_overlay.setStyleSheet(
            "background: rgba(0, 0, 0, 0.65); color: #f1f1f1; padding: 8px;"
            "font-family: monospace; font-size: 10px; border-radius: 5px;"
        )
        self.sandbox_stats_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.sandbox_stats_overlay.raise_()
        
        results_layout.addLayout(results_inner)
        results_group.setLayout(results_layout)
        previews_row.addWidget(results_group)

        previews_column.addLayout(previews_row)

        # Stats and detections below previews (more compact)
        self.sandbox_stats_label = QLabel("Detections: - | Time: -")
        self.sandbox_stats_label.setStyleSheet("font-size: 10px; font-family: monospace; padding: 2px 0; color: #ccc;")
        previews_column.addWidget(self.sandbox_stats_label)
        self.sandbox_detections_list = QListWidget()
        self.sandbox_detections_list.setMaximumHeight(70)
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
        """Export selected model version as Studio-compatible ZIP package for Field app."""
        version = self.sandbox_model_combo.currentText()
        if not version or version in ["No models available", "Error loading models"]:
            QMessageBox.warning(self, "Export Model", "Select a model version first.")
            return
        
        try:
            from embereye.core.model_versioning import ModelVersionManager
            import zipfile
            import json
            from datetime import datetime
            
            manager = ModelVersionManager()
            # Prefer selected version's weights; support both EmberEye.pt and best.pt
            weights_dir = manager.models_dir / version / "weights"
            weight_path = weights_dir / "EmberEye.pt"
            if not weight_path.exists():
                alt_path = weights_dir / "best.pt"
                if alt_path.exists():
                    weight_path = alt_path
                else:
                    # Fall back to current_best if present
                    fallback = manager.get_current_best()
                    weight_path = fallback if fallback and fallback.exists() else None
            
            if not weight_path or not weight_path.exists():
                QMessageBox.warning(self, "Export Model", f"Model weights not found for {version}")
                return
            
            # Save as Studio-compatible ZIP
            version_name = version.split(" ")[0]
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Model Package",
                f"{version_name}_model.zip",
                "ZIP Files (*.zip);;All Files (*.*)"
            )
            
            if not save_path:
                return
            
            export_path = Path(save_path)
            if export_path.suffix.lower() != '.zip':
                export_path = export_path.with_suffix('.zip')
            
            # Show progress dialog
            progress = QProgressDialog("Exporting model package...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            QApplication.processEvents()
            
            # Create metadata with class versioning (matches Studio format)
            from embereye.core.class_config import get_leaf_classes, get_classes_hash, load_master_classes
            classes_dict = load_master_classes()
            leaf_classes = get_leaf_classes(classes_dict)
            classes_hash = get_classes_hash(leaf_classes)

            metadata = {
                "model_version": version_name,
                "export_date": datetime.now().isoformat(),
                "model_type": "YOLOv8",
                "model_name": "best.pt",
                "app": "EmberEye Field",
                "compatible_apps": ["EmberEye Field", "EmberEye Studio"],
                "class_count": len(leaf_classes),
                "class_hash": classes_hash,
                "class_names": leaf_classes,
                "instructions": [
                    "1. Extract the ZIP file",
                    "2. Copy 'best.pt' to EmberEye Field's models directory",
                    "3. Restart EmberEye Field",
                    "4. Select the model from the model list"
                ]
            }

            # Create ZIP package compatible with Studio importer/exporter expectations
            with zipfile.ZipFile(str(export_path), 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(str(weight_path), arcname="best.pt")
                zipf.writestr("master_classes.json", json.dumps(classes_dict, indent=2))
                zipf.writestr("metadata.json", json.dumps(metadata, indent=2))

                readme = f"""# EmberEye Model Export

Model Version: {version_name}
Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Installation Instructions

### For EmberEye Field App:

1. Extract this ZIP file
2. Copy `best.pt` to the Field models directory
3. Copy `master_classes.json` if class definitions differ
4. Restart EmberEye Field application

## Files Included

- `best.pt`: Trained YOLOv8 model weights
- `master_classes.json`: Class definitions used during training/export
- `metadata.json`: Model information and compatibility details
- `README.md`: Installation guide
"""
                zipf.writestr("README.md", readme)

            # Verify ZIP contents
            with zipfile.ZipFile(str(export_path), 'r') as zipf:
                file_list = set(zipf.namelist())
                required_files = {'best.pt', 'master_classes.json', 'metadata.json', 'README.md'}
                missing = required_files - file_list
                if missing:
                    progress.close()
                    QMessageBox.critical(self, "Export Error", f"ZIP package incomplete. Missing: {', '.join(sorted(missing))}")
                    try:
                        export_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return
            
            progress.close()
            QMessageBox.information(
                self,
                "Export Complete",
                f"✓ Model package exported:\n{export_path}\n\n"
                f"File size: {export_path.stat().st_size / (1024 * 1024):.2f} MB"
            )
            
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
            
            # Save metadata in current schema
            metadata_file = version_dir / "metadata.json"
            metadata.save(metadata_file)
            
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
        self.sandbox_stats_overlay.setText(stats_text)

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
            
            # Scale to fit enlarged result frame
            scaled = pixmap.scaled(520, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

    def _update_anomaly_count(self):
        self._update_incident_count()

    def _update_incident_count(self):
        try:
            if hasattr(self, 'incident_count_label'):
                self.incident_count_label.setText(f"Captured: {len(self._incidents_store)}")
        except Exception:
            pass

    @pyqtSlot(str, object, float, float, object)
    def handle_incident_frame_from_widget(self, loc_id, qimage, score, yolo_score=0.0, detections=None):
        """Add a captured incident to the Incidents tab."""
        try:
            debug_print(f"[INCIDENT] Received incident: loc_id={loc_id}, score={score:.3f}, detections={len(detections or [])}")
            # Hybrid alarm evaluation
            key = str(loc_id) if loc_id is not None else "_broadcast"
            fusion_result = self._fusion_by_loc_id.get(key) or self._fusion_by_loc_id.get("_broadcast")
            fusion_alarm = bool(fusion_result.get('alarm')) if fusion_result else False
            rule_result = self._evaluate_rule_alarm(detections or [], yolo_score, fusion_result)
            rule_alarm = bool(rule_result.get('rule_alarm'))
            final_alarm = fusion_alarm or rule_alarm
            alarm_reason = []
            if fusion_alarm:
                alarm_reason.append(f"Fusion: {fusion_result.get('alarm_reason', 'alarm')}")
            if rule_alarm:
                reasons = rule_result.get('reasons', []) or []
                if reasons:
                    alarm_reason.append(f"Rules: {reasons[0]}")
                else:
                    alarm_reason.append("Rules: alarm")

            # Update alarm indicator for this widget
            for widget in self.get_video_widgets():
                if getattr(widget, 'loc_id', None) == loc_id:
                    try:
                        widget.update_fire_alarm(final_alarm)
                    except Exception:
                        pass
                    break
            # Check if capture is enabled
            if not getattr(self, 'incident_capture_enabled', True):
                debug_print(f"[INCIDENT] Capture disabled, skipping")
                return
            from PyQt5.QtGui import QPixmap, QIcon
            from PyQt5.QtWidgets import QListWidgetItem
            import time, os
            from datetime import datetime
            # Convert to pixmap in GUI thread
            pixmap = QPixmap.fromImage(qimage)
            # Maintain max items by removing oldest
            if len(self._incidents_store) >= getattr(self, '_incident_max_items', 200):
                self._incidents_store.pop(0)
                # Also remove first list item if exists
                if self.incident_list.count() > 0:
                    self.incident_list.takeItem(0)

            ts = time.time()
            entry = {
                'pixmap': pixmap,
                'loc_id': str(loc_id),
                'score': float(score),
                'yolo_score': float(yolo_score),
                'ts': ts,
                'detections': detections or [],
                'rule_severity': rule_result.get('severity'),
                'rule_alarm': rule_alarm,
                'fusion_alarm': fusion_alarm,
                'alarm': final_alarm,
                'alarm_reason': " | ".join(alarm_reason).strip()
            }
            self._incidents_store.append(entry)

            # Save to disk if enabled
            if getattr(self, 'incident_save_enabled', False):
                try:
                    save_dir = getattr(self, 'incident_save_dir', '')
                    if save_dir:
                        date_str = datetime.fromtimestamp(ts).strftime('%Y%m%d')
                        date_path = os.path.join(save_dir, date_str)
                        os.makedirs(date_path, exist_ok=True)
                        fname = datetime.fromtimestamp(ts).strftime('%H%M%S') + f"_{loc_id}_{score:.2f}.png"
                        full_path = os.path.join(date_path, fname)
                        pixmap.save(full_path)
                except Exception as e:
                    print(f"Incident disk save error: {e}")

            # Create thumbnail item
            item = QListWidgetItem()
            # index used as reference back into store
            idx = len(self._incidents_store) - 1
            item.setData(Qt.UserRole, idx)
            # Set icon and label
            icon = QIcon(pixmap.scaled(160, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            item.setIcon(icon)
            ts_str = datetime.fromtimestamp(entry['ts']).strftime('%H:%M:%S')
            item.setText(f"{entry['loc_id']}\n{ts_str} • {entry['score']:.2f}")
            self.incident_list.addItem(item)
            debug_print(f"[INCIDENT] Added to list: total={self.incident_list.count()}, store={len(self._incidents_store)}")
            self._update_incident_count()

            # Periodic retention cleanup (every 60 sec)
            now = time.time()
            if getattr(self, 'incident_save_enabled', False) and (now - getattr(self, '_last_incident_cleanup', 0) > 60):
                self._last_incident_cleanup = now
                self._cleanup_old_incidents()
        except Exception as e:
            print(f"Incident add error: {e}")

    def _cleanup_old_incidents(self):
        """Remove incident files older than retention_days."""
        try:
            import os, time
            save_dir = getattr(self, 'incident_save_dir', '')
            days = getattr(self, 'incident_retention_days', 7)
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
            print(f"Incident cleanup error: {e}")

    def export_incidents_bundle(self):
        """Export all captured incidents into a ZIP bundle."""
        if not getattr(self, '_incidents_store', None):
            QMessageBox.information(self, "No Incidents", "No incidents captured to export.")
            return
        self._export_incidents_bundle_from_entries(self._incidents_store, "Export Complete")

    def export_selected_incidents_bundle(self):
        """Export selected incidents into a ZIP bundle."""
        selected_items = self.incident_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Select one or more incidents to export.")
            return
        entries = []
        for item in selected_items:
            idx = item.data(Qt.UserRole)
            if idx is None:
                continue
            if 0 <= idx < len(self._incidents_store):
                entries.append(self._incidents_store[idx])
        if not entries:
            QMessageBox.information(self, "No Incidents", "No valid incidents selected.")
            return
        self._export_incidents_bundle_from_entries(entries, "Export Selected Complete")

    def _export_incidents_bundle_from_entries(self, entries, title):
        import tempfile
        import time
        import shutil
        from datetime import datetime
        from PyQt5.QtWidgets import QProgressDialog

        exporter = IncidentExporter()
        temp_dir = tempfile.mkdtemp(prefix="incident_export_")

        frame_paths = []
        detection_frames = []

        timestamps = [e.get('ts', time.time()) for e in entries]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        duration_seconds = max(0.0, max_ts - min_ts)

        progress = QProgressDialog("Exporting incidents...", "Cancel", 0, len(entries), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        for idx, entry in enumerate(entries):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            ts = entry.get('ts', time.time())
            ts_iso = datetime.fromtimestamp(ts).isoformat()
            frame_name = f"frame_{idx:04d}.png"
            frame_path = os.path.join(temp_dir, frame_name)
            try:
                entry['pixmap'].save(frame_path)
            except Exception:
                continue

            frame_paths.append(frame_path)
            detection_frames.append(DetectionFrame(
                frame_path=frame_path,
                timestamp=ts_iso,
                detections=entry.get('detections', []) or [{
                    'class': 'incident',
                    'confidence': float(entry.get('score', 0.0)),
                    'bbox': []
                }],
                frame_index=idx
            ))

        progress.setValue(len(entries))

        if not frame_paths:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            QMessageBox.warning(self, "Export Failed", "No frames could be exported.")
            return

        incident_id = datetime.now().strftime("INC%Y%m%d_%H%M%S")
        location = str(entries[0].get('loc_id', 'Unknown'))
        metadata = IncidentExportMetadata(
            incident_id=incident_id,
            location=location,
            timestamp=datetime.fromtimestamp(min_ts).isoformat(),
            duration_seconds=duration_seconds,
            detection_count=len(detection_frames),
            frame_count=len(frame_paths)
        )

        zip_path = exporter.create_incident_bundle(
            incident_id=incident_id,
            location=location,
            timestamp=metadata.timestamp,
            frame_paths=frame_paths,
            detection_frames=detection_frames,
            metadata=metadata
        )

        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        QMessageBox.information(self, title, f"Incident bundle saved to:\n{zip_path}")

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
        settings_menu.addAction("🌐 IP→Loc Mappings", self.show_ip_loc_mappings_dialog)
        settings_menu.addSeparator()
        # Model Management (Import & Export)
        settings_menu.addAction("📥 Import Model", self.import_deployment_model)
        export_model_menu = settings_menu.addMenu("📤 Export Model")
        export_model_menu.addAction("Export to ONNX", lambda: self.export_model('onnx'))
        export_model_menu.addAction("Export to TorchScript", lambda: self.export_model('torchscript'))
        export_model_menu.addAction("Export to CoreML", lambda: self.export_model('coreml'))
        export_model_menu.addAction("Export to TensorFlow Lite", lambda: self.export_model('tflite'))
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

        # Tray-like icon strip (Windows system tray style)
        self.status_tray_widget = QWidget()
        tray_layout = QHBoxLayout(self.status_tray_widget)
        tray_layout.setContentsMargins(0, 0, 0, 0)
        tray_layout.setSpacing(4)

        def _make_tray_icon(standard_icon, tooltip):
            icon_label = QLabel()
            icon_label.setFixedSize(16, 16)
            icon_label.setPixmap(self.style().standardIcon(standard_icon).pixmap(14, 14))
            icon_label.setToolTip(tooltip)
            return icon_label

        # Copies existing status items as icons
        self.tray_tcp_icon = _make_tray_icon(QStyle.SP_DriveNetIcon, "TCP Server")
        self.tray_device_icon = _make_tray_icon(QStyle.SP_DesktopIcon, "Inference Device")
        self.tray_model_icon = _make_tray_icon(QStyle.SP_FileIcon, "Model Status")
        self.tray_detection_icon = _make_tray_icon(QStyle.SP_DialogApplyButton, "Detections")
        # Proposed new system icon
        self.tray_system_icon = _make_tray_icon(QStyle.SP_ComputerIcon, "System")

        tray_layout.addWidget(self.tray_tcp_icon)
        tray_layout.addWidget(self.tray_device_icon)
        tray_layout.addWidget(self.tray_model_icon)
        tray_layout.addWidget(self.tray_detection_icon)
        tray_layout.addWidget(self.tray_system_icon)
        status_layout.addWidget(self.status_tray_widget)
        
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
        self.tcp_status_label.setStyleSheet("QLabel { color: #00bcd4; font-size: 11px; }")
        status_layout.addWidget(self.tcp_status_label)

        # Device indicator (resolved from active DetectionWorker)
        self.device_status_label = QLabel("Device: Detecting...")
        self.device_status_label.setStyleSheet("QLabel { color: #00bcd4; font-size: 11px; }")
        status_layout.addWidget(self.device_status_label)

        # Model load indicator
        self.model_status_label = QLabel("Model: Loading...")
        self.model_status_label.setStyleSheet("QLabel { color: #00bcd4; font-size: 11px; }")
        status_layout.addWidget(self.model_status_label)

        # Detection counter
        self.detection_count_label = QLabel("Detections: 0")
        self.detection_count_label.setStyleSheet("QLabel { color: #00bcd4; font-size: 11px; }")
        status_layout.addWidget(self.detection_count_label)
        
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

        # Initial tooltip sync for tray icons
        self._refresh_status_tray_icons(tcp_running=False)

        # Periodically update model load state
        try:
            if not hasattr(self, '_model_status_timer') or self._model_status_timer is None:
                self._model_status_timer = QTimer(self)
                self._model_status_timer.timeout.connect(self._refresh_model_status)
                self._model_status_timer.start(2000)
            self._refresh_model_status()
        except Exception:
            pass

    def _refresh_status_tray_icons(self, tcp_running=None):
        """Sync tray icon appearance/tooltips with existing status labels."""
        try:
            if hasattr(self, 'tray_system_icon'):
                self.tray_system_icon.setToolTip(f"System | PID: {os.getpid()}")

            if hasattr(self, 'tray_tcp_icon'):
                tcp_text = self.tcp_status_label.text() if hasattr(self, 'tcp_status_label') else "TCP Server"
                self.tray_tcp_icon.setToolTip(tcp_text)
                if tcp_running is True:
                    self.tray_tcp_icon.setPixmap(self.style().standardIcon(QStyle.SP_DialogApplyButton).pixmap(14, 14))
                elif tcp_running is False:
                    self.tray_tcp_icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(14, 14))

            if hasattr(self, 'tray_device_icon') and hasattr(self, 'device_status_label'):
                self.tray_device_icon.setToolTip(self.device_status_label.text())

            if hasattr(self, 'tray_model_icon') and hasattr(self, 'model_status_label'):
                model_text = self.model_status_label.text()
                self.tray_model_icon.setToolTip(model_text)
                if "Loaded" in model_text:
                    self.tray_model_icon.setPixmap(self.style().standardIcon(QStyle.SP_DialogApplyButton).pixmap(14, 14))
                elif "Error" in model_text:
                    self.tray_model_icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(14, 14))
                else:
                    self.tray_model_icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(14, 14))

            if hasattr(self, 'tray_detection_icon') and hasattr(self, 'detection_count_label'):
                self.tray_detection_icon.setToolTip(self.detection_count_label.text())
        except Exception:
            pass
    
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
            self._refresh_status_tray_icons(tcp_running=is_running)
            
        except Exception as e:
            print(f"TCP status update error: {e}")

    def _refresh_model_status(self):
        """Update model load status label based on DetectionWorker state."""
        if not hasattr(self, 'model_status_label'):
            return
        try:
            from embereye.core.detection_worker import get_detection_worker
            worker = get_detection_worker()
            if not worker:
                self.model_status_label.setText("Model: Unavailable")
                return
            stats = worker.get_stats()
            if hasattr(self, 'device_status_label'):
                inferred_device = str(stats.get('inference_device', '') or '').strip().lower()
                if inferred_device in ("0", "cuda", "gpu"):
                    self.device_status_label.setText("Device: GPU")
                elif inferred_device:
                    self.device_status_label.setText(f"Device: {inferred_device.upper()}")
                else:
                    self.device_status_label.setText("Device: Detecting...")
            if stats.get('model_loaded'):
                self.model_status_label.setText("Model: Loaded")
                self.model_status_label.setToolTip("")
            else:
                model_error = stats.get('model_error')
                if model_error:
                    self.model_status_label.setText("Model: Error")
                    self.model_status_label.setToolTip(model_error)
                else:
                    self.model_status_label.setText("Model: Not Loaded")
                    self.model_status_label.setToolTip("")
            if hasattr(self, 'detection_count_label'):
                self.detection_count_label.setText(f"Detections: {stats.get('detections_confirmed', 0)}")
            self._refresh_status_tray_icons()
        except Exception:
            self.model_status_label.setText("Model: Error")
            self._refresh_status_tray_icons()

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
                from embereye.core.tcp_sensor_server import TCPSensorServer
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
            'smoke_threshold_pct': float(getattr(self.sensor_fusion, 'smoke_threshold_pct', self.config.get('smoke_threshold_pct', 25.0))),
            'flame_threshold_pct': float(getattr(self.sensor_fusion, 'flame_threshold_pct', self.config.get('flame_threshold_pct', 25.0))),
            'min_sources': self.sensor_fusion.min_sources,
            
            # Gas sensor calibration
            'gas_r0': getattr(self.gas_sensor, 'r0', 76.63),
            'gas_rl': getattr(self.gas_sensor, 'rl', 1.0),
            'gas_vcc': getattr(self.gas_sensor, 'vcc', 5.0),
            
            # Display settings
            'hot_cell_decay_time': 5.0,
            'freeze_on_alarm': True,
            'show_fusion_overlay': True,
            'vision_threshold': float(getattr(self.sensor_fusion, 'vision_threshold', self.config.get('vision_threshold', getattr(self, 'vision_threshold', 0.7)))),
            'vision_confidence_weight': float(getattr(self.sensor_fusion, 'vision_confidence_weight', self.config.get('vision_confidence_weight', 0.5))),

            # Hybrid detection
            'heuristic_threshold': float(self.config.get('heuristic_threshold', getattr(self, 'heuristic_threshold', 0.20))),
            'force_yolo_every_n_frames': int(self.config.get('force_yolo_every_n_frames', getattr(self, 'force_yolo_every_n_frames', 10))),
            'yolo_conf_threshold': float(self.config.get('yolo_conf_threshold', getattr(self, 'yolo_conf_threshold', 0.05))),
            'possible_conf_threshold': float(self.config.get('possible_conf_threshold', getattr(self, 'possible_conf_threshold', 0.60))),
            'confirmed_conf_threshold': float(self.config.get('confirmed_conf_threshold', getattr(self, 'confirmed_conf_threshold', 0.80))),
            'rule_min_fusion_conf': float(self.config.get('rule_min_fusion_conf', getattr(self, '_rule_min_fusion_conf', 0.30))),
            'rule_min_yolo_conf': float(self.config.get('rule_min_yolo_conf', getattr(self, '_rule_min_yolo_conf', 0.60))),
            'detection_box_mode': self.detection_box_mode,
            'detection_box_classes': list(self.detection_box_classes),
            'detection_available_classes': sorted(set(get_leaf_classes() or [])),
            'detection_selected_preset': str(self.config.get('detection_selected_preset', 'Custom')),
            'detection_default_profile': self.config.get('detection_default_profile', {}),
            
            # Anomalies
            'anomaly_threshold': getattr(self, 'anomaly_threshold', 0.4),
            'anomaly_max_items': getattr(self, '_anomaly_max_items', 200),
            'anomaly_save_enabled': getattr(self, 'anomaly_save_enabled', False),
            'anomaly_save_dir': getattr(self, 'anomaly_save_dir', ''),
            'anomaly_retention_days': getattr(self, 'anomaly_retention_days', 7),
            'debug_enabled': is_debug_enabled()
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
            applied = dialog.get_settings()
            if applied.get('restart_app', False):
                confirm = QMessageBox.question(
                    self,
                    "Restart Application",
                    "Settings have been applied. Restart EmberEye Field now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    self._restart_application()
                    return
            QMessageBox.information(self, "Settings Applied", "Sensor configuration has been updated (no restart required).")

    def _restart_application(self):
        """Restart current application process."""
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable] + sys.argv)
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "Restart Failed", f"Could not restart application: {e}")
    
    def apply_sensor_config(self, settings):
        """Apply sensor configuration settings."""
        # Update sensor fusion
        self.sensor_fusion.temp_threshold = settings['temp_threshold']
        self.sensor_fusion.gas_ppm_threshold = settings['gas_ppm_threshold']
        self.sensor_fusion.smoke_threshold_pct = float(settings.get('smoke_threshold_pct', getattr(self.sensor_fusion, 'smoke_threshold_pct', 25.0)))
        self.sensor_fusion.flame_threshold_pct = float(settings.get('flame_threshold_pct', getattr(self.sensor_fusion, 'flame_threshold_pct', 25.0)))
        self.sensor_fusion.vision_threshold = float(settings.get('vision_threshold', getattr(self.sensor_fusion, 'vision_threshold', 0.7)))
        self.sensor_fusion.vision_confidence_weight = float(settings.get('vision_confidence_weight', getattr(self.sensor_fusion, 'vision_confidence_weight', 0.5)))
        self.sensor_fusion.flame_active_value = int(settings.get('flame_active_value', getattr(self.sensor_fusion, 'flame_active_value', 1)))
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
        
        # Update threshold for all video workers
        anomaly_threshold = settings.get('anomaly_threshold', 0.4)
        debug_print(f"[CONFIG] Applying anomaly_threshold={anomaly_threshold} to {len(self.video_widgets)} video workers")

        # Hybrid thresholds (apply live where possible)
        self.heuristic_threshold = float(settings.get('heuristic_threshold', getattr(self, 'heuristic_threshold', 0.20)))
        self.force_yolo_every_n_frames = int(settings.get('force_yolo_every_n_frames', getattr(self, 'force_yolo_every_n_frames', 10)))
        self.yolo_conf_threshold = float(settings.get('yolo_conf_threshold', getattr(self, 'yolo_conf_threshold', 0.05)))
        self.possible_conf_threshold = float(settings.get('possible_conf_threshold', getattr(self, 'possible_conf_threshold', 0.60)))
        self.confirmed_conf_threshold = float(settings.get('confirmed_conf_threshold', getattr(self, 'confirmed_conf_threshold', 0.80)))
        if self.confirmed_conf_threshold <= self.possible_conf_threshold:
            self.confirmed_conf_threshold = min(1.0, self.possible_conf_threshold + 0.05)

        self._rule_min_fusion_conf = float(settings.get('rule_min_fusion_conf', self._rule_min_fusion_conf))
        self._rule_min_yolo_conf = float(settings.get('rule_min_yolo_conf', self._rule_min_yolo_conf))
        mode_value = str(settings.get('detection_box_mode', self.detection_box_mode)).strip().lower()
        self.detection_box_mode = mode_value if mode_value in ('all', 'specific') else 'all'
        classes_value = settings.get('detection_box_classes', self.detection_box_classes)
        if not isinstance(classes_value, list):
            classes_value = []
        self.detection_box_classes = [str(class_name).strip() for class_name in classes_value if str(class_name).strip()]

        os.environ['EMBEREYE_YOLO_CONF'] = str(self.yolo_conf_threshold)
        os.environ['EMBEREYE_HEURISTIC_THRESHOLD'] = str(self.heuristic_threshold)
        os.environ['EMBEREYE_FORCE_YOLO_EVERY_N'] = str(self.force_yolo_every_n_frames)
        os.environ['EMBEREYE_BBOX_MODE'] = self.detection_box_mode
        os.environ['EMBEREYE_BBOX_CLASSES'] = ';'.join(self.detection_box_classes)

        # Update global detection worker if running
        try:
            from embereye.core.detection_worker import get_detection_worker
            detection_worker = get_detection_worker()
            if detection_worker and getattr(detection_worker, 'detector', None):
                detector = detection_worker.detector
                detector.heuristic_threshold = self.heuristic_threshold
                detector.yolo_conf_threshold = self.yolo_conf_threshold
                detector.possible_threshold = self.possible_conf_threshold
                detector.confirmed_threshold = self.confirmed_conf_threshold
        except Exception as e:
            debug_print(f"[CONFIG] Detection worker update skipped: {e}")

        for widget in self.video_widgets.values():
            if hasattr(widget, 'worker') and widget.worker:
                widget.worker.anomaly_threshold = anomaly_threshold
                widget.worker.heuristic_threshold = self.heuristic_threshold
                widget.worker.force_yolo_every_n_frames = self.force_yolo_every_n_frames
                widget.worker.detection_box_mode = self.detection_box_mode
                widget.worker.detection_box_classes = set(self.detection_box_classes)
                debug_print(f"[CONFIG] Set worker {widget.loc_id} threshold to {widget.worker.anomaly_threshold}")
        
        # Update display settings for all video widgets
        for widget in self.video_widgets.values():
            widget.hot_cells_decay_time = settings['hot_cell_decay_time']
            widget.freeze_on_alarm = settings['freeze_on_alarm']
            widget.show_fusion_overlay = settings['show_fusion_overlay']

        # Debug logging toggle
        set_debug_enabled(bool(settings.get('debug_enabled', False)))
        
        # Update anomaly settings in main window
        self.anomaly_threshold = settings.get('anomaly_threshold', 0.4)
        self._anomaly_max_items = settings.get('anomaly_max_items', 200)
        self.anomaly_save_enabled = settings.get('anomaly_save_enabled', False)
        self.anomaly_save_dir = settings.get('anomaly_save_dir', '')
        self.anomaly_retention_days = settings.get('anomaly_retention_days', 7)

        # Persist settings to stream config
        self.config['smoke_threshold_pct'] = self.sensor_fusion.smoke_threshold_pct
        self.config['flame_threshold_pct'] = self.sensor_fusion.flame_threshold_pct
        self.config['temp_threshold'] = self.sensor_fusion.temp_threshold
        self.config['gas_ppm_threshold'] = self.sensor_fusion.gas_ppm_threshold
        self.config['vision_threshold'] = settings.get('vision_threshold', getattr(self, 'vision_threshold', 0.7))
        self.config['vision_confidence_weight'] = self.sensor_fusion.vision_confidence_weight
        self.config['anomaly_threshold'] = self.anomaly_threshold
        self.config['anomaly_max_items'] = self._anomaly_max_items
        self.config['anomaly_save_enabled'] = self.anomaly_save_enabled
        self.config['anomaly_save_dir'] = self.anomaly_save_dir
        self.config['anomaly_retention_days'] = self.anomaly_retention_days
        self.config['heuristic_threshold'] = self.heuristic_threshold
        self.config['force_yolo_every_n_frames'] = self.force_yolo_every_n_frames
        self.config['yolo_conf_threshold'] = self.yolo_conf_threshold
        self.config['possible_conf_threshold'] = self.possible_conf_threshold
        self.config['confirmed_conf_threshold'] = self.confirmed_conf_threshold
        self.config['rule_min_fusion_conf'] = self._rule_min_fusion_conf
        self.config['rule_min_yolo_conf'] = self._rule_min_yolo_conf
        self.config['detection_box_mode'] = self.detection_box_mode
        self.config['detection_box_classes'] = list(self.detection_box_classes)
        self.config['detection_selected_preset'] = str(settings.get('detection_selected_preset', self.config.get('detection_selected_preset', 'Custom')))
        profile_value = settings.get('detection_default_profile', self.config.get('detection_default_profile', {}))
        self.config['detection_default_profile'] = profile_value if isinstance(profile_value, dict) else {}
        try:
            StreamConfig.save_config(self.config)
        except Exception as e:
            debug_print(f"[CONFIG] Save config failed: {e}")
        
        print(
            f"Sensor config updated: Temp={settings['temp_threshold']}, Gas={settings['gas_ppm_threshold']}, "
            f"Smoke={self.sensor_fusion.smoke_threshold_pct}%, Flame={self.sensor_fusion.flame_threshold_pct}%, "
            f"VisionThr={self.sensor_fusion.vision_threshold}, VisionWeight={self.sensor_fusion.vision_confidence_weight}, "
            f"R0={settings['gas_r0']}, MinSources={settings['min_sources']}, AnomalyThr={self.anomaly_threshold}, "
            f"Heuristic={self.heuristic_threshold}, ForceEveryN={self.force_yolo_every_n_frames}, YOLOConf={self.yolo_conf_threshold}, "
            f"Bands=({self.possible_conf_threshold}/{self.confirmed_conf_threshold}), "
            f"Rule(yolo/fusion)=({self._rule_min_yolo_conf}/{self._rule_min_fusion_conf}), "
            f"BoxMode={self.detection_box_mode}, BoxClasses={len(self.detection_box_classes)}"
        )

    def show_master_class_config(self):
        """Open the master class configuration dialog and refresh classes on save."""
        try:
            from master_class_config_dialog import MasterClassConfigDialog
            from embereye.core.class_config import load_master_classes, get_leaf_classes
            
            dlg = MasterClassConfigDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                # Reload taxonomy and refresh dependent UI controls
                self._master_classes = load_master_classes()
                self.training_video_classes = get_leaf_classes()
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
        ip_edit = QLineEdit(); ip_edit.setPlaceholderText("IP:Port (e.g., 127.0.0.1:5000)")
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
                QMessageBox.warning(dlg, "Missing Data", "Please enter device name and IP:Port.")
                return
            # Parse IP:Port format
            if ':' in ip:
                try:
                    ip_part, port_part = ip.rsplit(':', 1)
                    port = int(port_part)
                    if not is_valid_ip(ip_part):
                        QMessageBox.warning(dlg, "Invalid IP", "Please enter a valid IP:Port (e.g., 127.0.0.1:5000).")
                        return
                    ip_address = f"{ip_part}:{port}"  # Store in IP:Port format
                except (ValueError, Exception):
                    QMessageBox.warning(dlg, "Invalid Format", "Please enter IP:Port format (e.g., 127.0.0.1:5000).")
                    return
            else:
                if not is_valid_ip(ip):
                    QMessageBox.warning(dlg, "Invalid IP", "Please enter a valid IP:Port (e.g., 127.0.0.1:5000).")
                    return
                ip_address = f"{ip}:9001"  # Default port
            try:
                self.emberhawk.add_device(name, ip_address, loc if loc else None, mode, int(poll))
                QMessageBox.information(dlg, "Saved", f"EmberHawk device '{name}' saved.\nIP: {ip_address}\nLocation: {loc or 'N/A'}\nMode: {mode}\nPoll: {poll}s")
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
                devices = self.emberhawk.list_devices()
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
                self.emberhawk.remove_device(did)
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

        # --- Vision Detection Log Tab ---
        vision_tab = QDialog(dlg)
        vision_layout = QVBoxLayout(vision_tab)
        vision_ctrl_row = QHBoxLayout()
        vision_stage_combo = QComboBox(); vision_stage_combo.addItems(["All", "HEURISTIC", "YOLO"])
        vision_ctrl_row.addWidget(QLabel("Stage:"))
        vision_ctrl_row.addWidget(vision_stage_combo)
        vision_layout.addLayout(vision_ctrl_row)
        vision_view = QTextEdit(); vision_view.setReadOnly(True)
        vision_layout.addWidget(vision_view)

        def load_vision_log():
            path = VISION_LOG
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-1500:]
                    stage = vision_stage_combo.currentText()
                    if stage != 'All':
                        lines = [ln for ln in lines if f"\t{stage}\t" in ln]
                    vision_view.setPlainText(''.join(lines))
                except Exception as e:
                    vision_view.setPlainText(f"Error loading Vision Detection log: {e}")
            else:
                vision_view.setPlainText(f"Log file not found: {path}")

        vision_timer = QTimer(vision_tab)
        vision_timer.setInterval(2000)
        vision_timer.timeout.connect(load_vision_log)
        vision_timer.start()
        vision_stage_combo.currentIndexChanged.connect(load_vision_log)
        load_vision_log()
        tabs.addTab(vision_tab, "Vision Detection")

        # --- Fusion Algorithm Log Tab ---
        fusion_tab = QDialog(dlg)
        fusion_layout = QVBoxLayout(fusion_tab)
        fusion_ctrl_row = QHBoxLayout()
        fusion_loc_combo = QComboBox(); fusion_loc_combo.addItem("All Locations")
        try:
            loc_ids = set()
            for g in self.config.get('groups', []):
                streams = self.config.get('streams', {}).get(g, [])
                for s in streams:
                    lid = s.get('location_id') or s.get('loc_id') or s.get('name')
                    if lid:
                        loc_ids.add(str(lid))
            for lid in sorted(loc_ids):
                fusion_loc_combo.addItem(lid)
        except Exception:
            pass
        fusion_ctrl_row.addWidget(QLabel("Location:"))
        fusion_ctrl_row.addWidget(fusion_loc_combo)
        fusion_layout.addLayout(fusion_ctrl_row)
        fusion_view = QTextEdit(); fusion_view.setReadOnly(True)
        fusion_layout.addWidget(fusion_view)

        def load_fusion_log():
            path = FUSION_LOG
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-1500:]
                    sel = fusion_loc_combo.currentText()
                    if sel != 'All Locations':
                        lines = [ln for ln in lines if f"\t{sel}\t" in ln]
                    fusion_view.setPlainText(''.join(lines))
                except Exception as e:
                    fusion_view.setPlainText(f"Error loading Fusion Algorithm log: {e}")
            else:
                fusion_view.setPlainText(f"Log file not found: {path}")

        fusion_timer = QTimer(fusion_tab)
        fusion_timer.setInterval(2000)
        fusion_timer.timeout.connect(load_fusion_log)
        fusion_timer.start()
        fusion_loc_combo.currentIndexChanged.connect(load_fusion_log)
        load_fusion_log()
        tabs.addTab(fusion_tab, "Fusion Algorithm")

        dlg.resize(900, 600)
        dlg.exec_()

    def show_ip_loc_mappings_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem

        dlg = QDialog(self)
        dlg.setWindowTitle("IP→Loc Mappings")
        layout = QVBoxLayout(dlg)

        map_table = QTableWidget(0, 2)
        map_table.setHorizontalHeaderLabels(["IP", "Location Id"])
        layout.addWidget(map_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add/Update Mapping")
        del_btn = QPushButton("Delete Selected")
        refresh_btn = QPushButton("Refresh")
        import_btn = QPushButton("Import…")
        export_btn = QPushButton("Export…")
        close_btn = QPushButton("Close")
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(import_btn)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

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
                    r = map_table.rowCount()
                    map_table.insertRow(r)
                    map_table.setItem(r, 0, QTableWidgetItem(ip))
                    map_table.setItem(r, 1, QTableWidgetItem(loc))
            except Exception as e:
                QMessageBox.critical(dlg, "Load Failed", f"Could not load mappings: {e}")

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

        add_btn.clicked.connect(add_update_mapping)
        del_btn.clicked.connect(delete_selected_mapping)
        refresh_btn.clicked.connect(load_mappings)
        import_btn.clicked.connect(do_import)
        export_btn.clicked.connect(do_export)
        close_btn.clicked.connect(dlg.accept)

        load_mappings()
        dlg.resize(780, 500)
        dlg.exec_()

    def import_deployment_model(self):
        """Import a trained model from Studio for deployment in Field app."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog, QProgressDialog
        from PyQt5.QtCore import Qt
        from pathlib import Path
        import shutil
        
        # Create import dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Import Deployment Model")
        dlg.setModal(True)
        dlg.resize(600, 250)
        
        layout = QVBoxLayout(dlg)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Import Model from EmberEye Studio")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00bcd4;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel(
            "Select a trained model exported from Studio to use for real-time detection.\n"
            "After import, you can choose whether to activate it immediately for all video streams."
        )
        desc.setStyleSheet("color: #aaa; margin-bottom: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Model file selection
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Model File:"))
        self._import_model_path_label = QLabel("No file selected")
        self._import_model_path_label.setStyleSheet("color: #888; font-style: italic;")
        file_layout.addWidget(self._import_model_path_label, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_model_file(dlg))
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)
        
        # Model type selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Model Type:"))
        self._import_model_type_combo = QComboBox()
        self._import_model_type_combo.addItems([
            "PyTorch (.pt) - Default",
            "ONNX (.onnx)",
            "TensorFlow Lite (.tflite)",
            "CoreML (.mlmodel)"
        ])
        self._import_model_type_combo.setCurrentIndex(0)
        type_layout.addWidget(self._import_model_type_combo, 1)
        layout.addLayout(type_layout)
        
        # Info box
        info = QLabel(
            "ℹ️ The model is imported first.\n"
            "You will be asked to confirm activation at runtime after import completes."
        )
        info.setStyleSheet(
            "background-color: rgba(0, 188, 212, 0.1); "
            "border: 1px solid rgba(0, 188, 212, 0.3); "
            "border-radius: 4px; "
            "padding: 10px; "
            "color: #bbb; "
            "font-size: 12px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        import_btn = QPushButton("Import Model")
        import_btn.setStyleSheet(
            "background-color: #00bcd4; color: white; "
            "padding: 8px 20px; font-weight: bold; border-radius: 4px;"
        )
        import_btn.clicked.connect(lambda: self._execute_model_import(dlg))
        button_layout.addWidget(import_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        dlg.exec_()
    
    def _browse_model_file(self, parent_dlg):
        """Open file browser for model selection."""
        file_path, _ = QFileDialog.getOpenFileName(
            parent_dlg,
            "Select Model File",
            "",
            "Model Files (*.zip *.pt *.onnx *.tflite *.mlmodel);;Model Package (*.zip);;PyTorch (*.pt);;ONNX (*.onnx);;TFLite (*.tflite);;CoreML (*.mlmodel);;All Files (*)"
        )
        
        if file_path:
            self._selected_model_path = file_path
            from pathlib import Path
            self._import_model_path_label.setText(Path(file_path).name)
            self._import_model_path_label.setStyleSheet("color: #00bcd4; font-weight: bold;")
            
            # Auto-detect model type from extension
            ext = Path(file_path).suffix.lower()
            type_map = {
                '.zip': 0,
                '.pt': 0,
                '.onnx': 1,
                '.tflite': 2,
                '.mlmodel': 3
            }
            if ext in type_map:
                self._import_model_type_combo.setCurrentIndex(type_map[ext])
    
    def _execute_model_import(self, dialog):
        """Execute model import and activation."""
        from PyQt5.QtWidgets import QProgressDialog, QMessageBox
        from PyQt5.QtCore import Qt
        from pathlib import Path
        import shutil
        
        if not hasattr(self, '_selected_model_path') or not self._selected_model_path:
            QMessageBox.warning(dialog, "No File Selected", "Please select a model file to import.")
            return
        
        model_path = Path(self._selected_model_path)
        if not model_path.exists():
            QMessageBox.critical(dialog, "File Not Found", f"Model file not found:\n{model_path}")
            return
        
        # Get model type
        type_index = self._import_model_type_combo.currentIndex()
        type_names = ['pytorch', 'onnx', 'tflite', 'coreml']
        model_type = type_names[type_index]
        
        # Show progress
        progress = QProgressDialog("Importing and activating model...", None, 0, 0, dialog)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle("Importing Model")
        progress.show()
        QApplication.processEvents()
        
        try:
            from embereye.core.model_versioning import ModelVersionManager, ModelMetadata
            import datetime
            
            manager = ModelVersionManager()
            
            # Create deployment version directory
            version_name = f"deployment_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            version_dir = manager.models_dir / version_name
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # Create weights subdirectory
            weights_dir = version_dir / "weights"
            weights_dir.mkdir(exist_ok=True)
            
            # Resolve source model: direct file or ZIP package
            import tempfile
            import zipfile

            source_model_path = model_path
            zip_metadata = {}
            temp_extract_dir = None

            if model_path.suffix.lower() == '.zip':
                temp_extract_dir = tempfile.TemporaryDirectory(prefix="embereye_model_import_")
                extract_dir = Path(temp_extract_dir.name)

                with zipfile.ZipFile(str(model_path), 'r') as zipf:
                    zipf.extractall(str(extract_dir))
                    if 'metadata.json' in zipf.namelist():
                        try:
                            with zipf.open('metadata.json') as f:
                                zip_metadata = json.load(f)
                        except Exception:
                            zip_metadata = {}

                candidate_names = ['EmberEye.pt', 'best.pt', 'EmberEye_gpu.pt', 'EmberEye_mps.pt']
                source_model_path = None
                for name in candidate_names:
                    matches = list(extract_dir.rglob(name))
                    if matches:
                        source_model_path = matches[0]
                        break

                if source_model_path is None:
                    pt_matches = list(extract_dir.rglob('*.pt'))
                    if pt_matches:
                        source_model_path = pt_matches[0]

                if source_model_path is None:
                    raise ValueError("No deployable model file found inside ZIP (expected EmberEye.pt or *.pt)")

                model_type = 'pytorch' if source_model_path.suffix.lower() == '.pt' else model_type

            # Copy model file into version weights directory
            if source_model_path.suffix.lower() == '.pt':
                dest_path = weights_dir / "EmberEye.pt"
            else:
                dest_path = weights_dir / f"best.{source_model_path.suffix.lstrip('.')}"
            shutil.copy2(source_model_path, dest_path)

            # Build metadata using current schema
            training_meta = zip_metadata.get('training_metadata', {}) if isinstance(zip_metadata, dict) else {}
            metadata = ModelMetadata(
                version=version_name,
                timestamp=datetime.datetime.now().isoformat(),
                training_images=int(training_meta.get('training_images', training_meta.get('total_images', 0)) or 0),
                new_images=int(training_meta.get('new_images', 0) or 0),
                total_epochs=int(training_meta.get('total_epochs', training_meta.get('epochs', 0)) or 0),
                best_accuracy=float(training_meta.get('best_accuracy', 0.0) or 0.0),
                loss=float(training_meta.get('loss', 0.0) or 0.0),
                training_time_hours=float(training_meta.get('training_time_hours', 0.0) or 0.0),
                base_model=str(training_meta.get('base_model', 'imported')),
                config_snapshot={
                    "imgsz": 640,
                    "device": "auto",
                    "imported_file": model_path.name,
                    "resolved_model": source_model_path.name,
                    "format": model_type,
                },
                previous_version=training_meta.get('previous_version'),
                notes=f"Imported from {model_path.name}",
                training_strategy="imported",
            )
            metadata.save(version_dir / "metadata.json")
            
            # Validate class hash if metadata includes it
            try:
                from embereye.core.class_config import load_master_classes, get_classes_hash, get_leaf_classes
                
                # Check if imported ZIP had class hash in its metadata
                import zipfile
                class_hash_warning = ""
                
                if model_path.suffix.lower() == '.zip':
                    try:
                        with zipfile.ZipFile(str(model_path), 'r') as zipf:
                            if 'metadata.json' in zipf.namelist():
                                with zipf.open('metadata.json') as f:
                                    imported_meta = json.load(f)
                                    imported_hash = imported_meta.get('class_hash')
                                    
                                    if imported_hash:
                                        current_classes = get_leaf_classes()
                                        current_hash = get_classes_hash(current_classes)
                                        
                                        if imported_hash != current_hash:
                                            class_hash_warning = (
                                                f"\n\n⚠️ CLASS CONFIGURATION MISMATCH:\n"
                                                f"Model trained with {imported_meta.get('class_count', '?')} classes\n"
                                                f"Current system has {len(current_classes)} classes\n\n"
                                                f"Detection labels may be incorrect. "
                                                f"Consider updating master_classes.json."
                                            )
                    except Exception as e:
                        logger.debug(f"Could not read class hash from ZIP: {e}")
                
            except Exception as e:
                logger.debug(f"Class hash validation skipped: {e}")
                class_hash_warning = ""
            
            if temp_extract_dir is not None:
                temp_extract_dir.cleanup()

            progress.close()
            dialog.accept()

            activate_now = QMessageBox.question(
                self,
                "Activate Imported Model?",
                f"✓ Model imported successfully.\n\n"
                f"Model: {model_path.name}\n"
                f"Type: {model_type.upper()}\n"
                f"Version: {version_name}\n\n"
                f"Do you want to activate this model now for all video streams?"
                + class_hash_warning,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )

            if activate_now == QMessageBox.Yes:
                activated, activate_msg = manager.promote_to_best(version_name)
                if not activated:
                    raise RuntimeError(f"Model imported but activation failed: {activate_msg}")

                # Reload detection models in video workers at runtime
                self._reload_detection_models()

                QMessageBox.information(
                    self,
                    "Activation Complete",
                    f"✓ Model imported and activated at runtime.\n\n"
                    f"Version: {version_name}\n"
                    f"All video streams are now using this model."
                )
            else:
                QMessageBox.information(
                    self,
                    "Import Complete",
                    f"✓ Model imported but not activated.\n\n"
                    f"Version: {version_name}\n"
                    f"Current active model remains unchanged."
                )
            
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                dialog,
                "Import Failed",
                f"Failed to import model:\n\n{str(e)}\n\n"
                f"Please check the model file and try again."
            )
    
    def _reload_detection_models(self):
        """Reload detection models in all active video workers."""
        try:
            from embereye.core.detection_worker import stop_detection_worker

            # Hard restart global detection worker so new current_best model is loaded
            stop_detection_worker()

            rebound = 0
            for _, worker in self.video_workers.items():
                if hasattr(worker, 'init_detection_worker'):
                    worker.init_detection_worker()
                    rebound += 1

            # Force immediate status refresh (do not wait for timer)
            self._refresh_model_status()

            print(f"[MODEL_IMPORT] Detection worker restarted; callbacks rebound for {rebound} streams")
        except Exception as e:
            print(f"[MODEL_IMPORT] Warning: Could not reload models in workers: {e}")

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

        # Normalize endpoint: allow configured values like "127.0.0.1:4888"
        target_ip = str(ip).strip()
        if ':' in target_ip:
            target_ip = target_ip.split(':', 1)[0].strip()
        
        # Send command through existing TCP server connection
        if self.tcp_sensor_server and hasattr(self.tcp_sensor_server, 'send_command_to_client'):
            success = self.tcp_sensor_server.send_command_to_client(target_ip, command)
            if success:
                log_raw_packet(loc, f"PFDS_CMD {command} to {target_ip} ({name}) | sent via active connection")
                return True
            else:
                log_error_packet(loc, f"PFDS_CMD_FAIL {command} to {target_ip} ({name}) | no active connection")
                return False
        else:
            log_error_packet(loc, f"PFDS_CMD_FAIL {command} to {ip} ({name}) | TCP server not available")
            return False

    def dispatch_emberhawk_command(self, cmd: dict) -> bool:
        """Dispatch EmberHawk device commands via PFDS command interface.
        Called by EmberHawk manager to send PERIOD_ON, PERIOD_OFF, EEPROM1, REQUEST1, etc.
        
        Args:
            cmd: Command dict with keys: command, ip, name, location_id, device_id, etc.
        
        Returns:
            bool: True if command was sent successfully
        """
        try:
            command = cmd.get('command')
            ip = cmd.get('ip') or cmd.get('IP')  # Support both cases
            
            if not command or not ip:
                print(f"❌ dispatch_emberhawk_command: missing command={command} or IP={ip}")
                return False

            # Normalize endpoint: allow configured values like "127.0.0.1:4888"
            target_ip = str(ip).strip()
            if ':' in target_ip:
                target_ip = target_ip.split(':', 1)[0].strip()
            
            # Map EmberHawk commands to PFDS format
            # PFDS expects raw command strings like "PERIOD_ON", "EEPROM1", "REQUEST1", "PERIOD_OFF"
            if self.tcp_sensor_server and hasattr(self.tcp_sensor_server, 'send_command_to_client'):
                print(f"🔲 [dispatch_emberhawk_command] Sending '{command}' to IP={target_ip} via tcp_sensor_server")
                success = self.tcp_sensor_server.send_command_to_client(target_ip, command)
                
                if success:
                    print(f"✅ dispatch_emberhawk_command: '{command}' sent to {target_ip}")
                    return True
                else:
                    print(f"⚠️  dispatch_emberhawk_command: '{command}' failed for {target_ip} (no active connection)")
                    return False
            else:
                print(f"❌ dispatch_emberhawk_command: TCP server unavailable, cannot send '{command}'")
                return False
                
        except Exception as e:
            print(f"❌ dispatch_emberhawk_command exception: {e}")
            import traceback
            traceback.print_exc()
            return False

    def toggle_all_numeric_grids(self, enabled):
        """Enable or disable numbers-only thermal grid view on all video streams."""
        for widget in self.get_video_widgets():
            try:
                if hasattr(widget, 'set_display_mode'):
                    widget.set_display_mode("grid" if enabled else "default")
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
            from PyQt5.QtWidgets import QApplication
            
            if event.type() == QEvent.MouseMove:
                # Reset cursor hide timer on any mouse movement
                if hasattr(self, 'cursor_hide_timer'):
                    self.cursor_hide_timer.stop()
                    self._show_cursor()
                    self.cursor_hide_timer.start(self.cursor_hide_seconds * 1000)

                # If hovering directly over the status bar or its children, skip X-ray toggling
                try:
                    widget_under_cursor = QApplication.widgetAt(QCursor.pos())
                except Exception:
                    widget_under_cursor = None

                def _is_in_status_bar(w):
                    try:
                        sb = self.statusBar() if hasattr(self, 'statusBar') else None
                        if not sb or w is None:
                            return False
                        # Walk up the parent chain to see if widget belongs to status bar
                        curr = w
                        while curr is not None:
                            if curr == sb:
                                return True
                            curr = getattr(curr, 'parentWidget', lambda: None)()
                        return False
                    except Exception:
                        return False

                hovering_status_bar = _is_in_status_bar(widget_under_cursor)
                
                # X-ray effect: Show header (overlay_header) when mouse near edges
                # Skip when hovering status bar to avoid flicker
                if not hovering_status_bar and hasattr(self, 'overlay_header') and hasattr(self, 'header_visible'):
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
                # Skip toggling when cursor is over the status bar itself
                if not hovering_status_bar and hasattr(self, 'statusBar') and hasattr(self, 'statusbar_visible'):
                    from PyQt5.QtCore import QTimer
                    cursor_pos = QCursor.pos()
                    window_pos = self.mapFromGlobal(cursor_pos)
                    window_height = self.height()

                    enter_thresh = 30  # px from bottom to enter zone
                    exit_thresh = 80   # px from bottom to consider leaving (hysteresis)
                    in_bottom_zone = window_pos.y() > window_height - enter_thresh

                    if in_bottom_zone:
                        # Cancel pending hide and ensure bar is visible when entering zone
                        if hasattr(self, 'status_hide_timer') and self.status_hide_timer:
                            try:
                                self.status_hide_timer.stop()
                            except Exception:
                                pass
                            self.status_hide_timer = None
                        if not self.statusbar_visible:
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
                        self._was_in_bottom_zone = True
                    else:
                        # Debounce hide with hysteresis to reduce flicker near boundary
                        if window_pos.y() < window_height - exit_thresh and self.statusbar_visible:
                            if not hasattr(self, 'status_hide_timer') or self.status_hide_timer is None:
                                self.status_hide_timer = QTimer(self)
                                self.status_hide_timer.setSingleShot(True)
                                self.status_hide_timer.timeout.connect(self._hide_status_bar)
                                self.status_hide_timer.start(550)  # slightly longer debounce
                        self._was_in_bottom_zone = False
            
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

    def _hide_status_bar(self):
        """Hide the status bar via debounced timer."""
        try:
            if hasattr(self, 'statusBar') and self.statusbar_visible:
                self.statusBar().hide()
                self.statusbar_visible = False
        except Exception:
            pass
        finally:
            # Clear timer reference
            if hasattr(self, 'status_hide_timer'):
                self.status_hide_timer = None
    
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
            if hasattr(self, 'emberhawk') and self.emberhawk:
                self.emberhawk.stop_scheduler()
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
            from PyQt5.QtWidgets import QSizePolicy
            app = QApplication.instance()
            is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
            
            # Grid is already cleared by cleanup_old_widgets when called via schedule
            # Reset any maximized state when rebuilding grid
            self.maximized_widget = None
            self.original_layout = None

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
            
            # Clear previous row/column stretches to prevent layout issues when switching grid sizes
            for r in range(10):  # Clear up to 10 rows (more than max 5x5)
                self.rtsp_grid.setRowStretch(r, 0)
            for c in range(10):  # Clear up to 10 columns
                self.rtsp_grid.setColumnStretch(c, 0)
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
                    try:
                        video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    except Exception:
                        pass
                    # Default to camera view with fusion overlay
                    try:
                        if hasattr(video_widget, "set_display_mode"):
                            video_widget.set_display_mode("default")
                        elif hasattr(video_widget, "toggle_thermal_grid_view"):
                            video_widget.toggle_thermal_grid_view(False)
                    except Exception:
                        pass
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

            # Ensure equal stretch for rows and columns so cells fill available space
            try:
                for r in range(rows):
                    self.rtsp_grid.setRowStretch(r, 1)
                for c in range(cols):
                    self.rtsp_grid.setColumnStretch(c, 1)
            except Exception:
                pass

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

            # Get current grid dimensions
            rows, cols = map(int, self.grid_size.currentText().replace("×", "x").split("x"))

            # Store original state and grid position BEFORE modifying anything
            self.original_layout = {
                'visible': [],
                'hidden': [],
                'grid_items': []
            }

            # FIRST: Capture all widget positions BEFORE any modifications
            grid_count = self.rtsp_grid.count()
            
            for i in range(grid_count):
                item = self.rtsp_grid.itemAt(i)
                if item and (widget := item.widget()):
                    try:
                        # Store original grid position NOW, before any changes
                        pos = self.rtsp_grid.getItemPosition(i)
                        self.original_layout['grid_items'].append({
                            'widget': widget,
                            'row': pos[0],
                            'col': pos[1],
                            'rowspan': pos[2],
                            'colspan': pos[3]
                        })
                    except Exception as e:
                        print(f"Error capturing widget position: {e}")
                        continue

            # Update button visibility
            try:
                if hasattr(sender, 'maximize_btn'):
                    sender.maximize_btn.setVisible(False)  # Hide maximize
                if hasattr(sender, 'minimize_btn'):
                    sender.minimize_btn.setVisible(True)   # Show minimize
            except Exception as e:
                print(f"Button visibility error in maximize: {e}")

            # SECOND: Now modify the grid - hide non-sender widgets and maximize sender
            for item_data in self.original_layout['grid_items']:
                widget = item_data['widget']
                try:
                    if widget == sender:
                        # Remove from grid and re-add spanning entire grid
                        self.rtsp_grid.removeWidget(widget)
                        self.rtsp_grid.addWidget(widget, 0, 0, rows, cols)
                        widget.raise_()
                        self.maximized_widget = widget
                        self.original_layout['visible'].append(widget)
                    else:
                        widget.hide()
                        self.original_layout['hidden'].append(widget)
                except Exception as e:
                    print(f"Error modifying widget in maximize: {e}")
                    continue
            
            self.rtsp_grid.setContentsMargins(0, 0, 0, 0)
            self.rtsp_grid.setSpacing(0)
            sender.setFocus()
            self.rtsp_grid.update()

        except Exception as e:
            print(f"Maximize error: {str(e)}")
            import traceback
            traceback.print_exc()

    def handle_minimize(self):
        """Restore to grid view - show all hidden widgets"""
        try:
            if not self.maximized_widget or not self.original_layout:
                return
            
            # Restore button visibility for the previously maximized widget
            try:
                if hasattr(self.maximized_widget, 'maximize_btn'):
                    self.maximized_widget.maximize_btn.setVisible(True)  # Show maximize
                if hasattr(self.maximized_widget, 'minimize_btn'):
                    self.maximized_widget.minimize_btn.setVisible(False)  # Hide minimize
            except Exception as e:
                print(f"Button visibility error: {e}")

            # Remove the maximized widget from grid
            try:
                self.rtsp_grid.removeWidget(self.maximized_widget)
            except Exception as e:
                print(f"Remove widget error: {e}")

            # Restore all widgets to their original grid positions
            for item in self.original_layout.get('grid_items', []):
                widget = item.get('widget')
                if not widget:
                    continue
                    
                try:
                    # Check if widget still has a parent and is valid
                    if not widget.parent():
                        continue
                        
                    # Re-add to original position
                    self.rtsp_grid.addWidget(
                        widget,
                        item['row'],
                        item['col'],
                        item['rowspan'],
                        item['colspan']
                    )
                    widget.show()
                except Exception as e:
                    print(f"Restore widget error: {e}")
                    continue

            self.maximized_widget = None
            self.original_layout = None
            self.rtsp_grid.setContentsMargins(0, 0, 0, 0)
            self.rtsp_grid.setSpacing(0)
            self.rtsp_grid.update()

        except Exception as e:
            print(f"Minimize error: {str(e)}")
            import traceback
            traceback.print_exc()
            # Force reset state even on error
            self.maximized_widget = None
            self.original_layout = None

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
        """Perform non-blocking shutdown before closing and returning to login."""
        print("Logout initiated - starting async shutdown...")
        
        def _shutdown_in_thread():
            """Perform shutdown in background thread to avoid blocking UI."""
            try:
                # Stop video widgets (non-blocking with timeout)
                self.shutdown_video_widgets()
                
                # Stop WebSocket client (with timeout)
                if hasattr(self, 'ws_client'):
                    try:
                        print("Stopping WebSocket client...")
                        self.ws_client.stop()
                    except Exception as e:
                        print(f"WebSocket stop error: {e}")
                
                # Stop TCP sensor server (with timeout)
                if hasattr(self, 'tcp_server') and self.tcp_server:
                    try:
                        print("Stopping TCP sensor server...")
                        self.tcp_server.stop()
                    except Exception as e:
                        print(f"TCP server stop error: {e}")
                
                # Stop baseline manager sensor server if it exists
                if hasattr(self.parent(), 'server') and getattr(self.parent(), 'server'):
                    try:
                        print("Stopping parent sensor server...")
                        self.parent().server.stop()
                    except Exception as e:
                        print(f"Parent sensor server stop error: {e}")
                
                print("Cleanup complete, returning to login...")
            except Exception as e:
                print(f"Shutdown error: {e}")
            finally:
                # Schedule close on main thread
                self.close()
                from ee_loginwindow import EELoginWindow
                login_window = EELoginWindow()
                login_window.show()
        
        # Run shutdown in daemon thread (won't block UI)
        import threading
        shutdown_thread = threading.Thread(target=_shutdown_in_thread, daemon=True)
        shutdown_thread.start()

    def shutdown_video_widgets(self):
        """Iterate all video widgets and ensure their worker threads stop (with timeout)."""
        for widget in self.get_video_widgets():
            if hasattr(widget, 'stop'):
                try:
                    widget.stop()
                except Exception as e:
                    print(f"Error stopping video widget ({getattr(widget, 'loc_id', 'unknown')}): {e}")
