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
import webbrowser
import urllib.request
import urllib.error
from urllib.parse import urlparse
from typing import List
from pathlib import Path
from threading import Thread, Event
import subprocess

# Prefer fieldglass modules first, then parent directory for root-level utilities
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from embereye_base.core.stream_config import StreamConfig
from embereye_base.core.marketplace import PluginManager, validate_eapkg
from embereye_base.utils.tcp_server_logger import log_info as log_server_info, log_error as log_server_error
from embereye_base.utils.resource_helper import get_resource_path, get_data_path, ensure_runtime_folders
from embereye_base.utils.debug_config import debug_print, is_debug_enabled, set_debug_enabled
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTabWidget, QMessageBox,
    QToolButton, QMenu, QStyle, QFileDialog, QGridLayout, QPushButton, QDialog, QLineEdit,
    QListWidget, QListWidgetItem, QProgressBar, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QSlider, QGroupBox, QCompleter, QCheckBox, QDoubleSpinBox, QFormLayout, QInputDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QScrollArea, QListView, QAbstractItemView,
    QProgressDialog, QApplication, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QDialogButtonBox
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QMutex, QObject, QTimer, QUrl, QThread, QPropertyAnimation, QEasingCurve, QMetaObject, QSize, QAbstractAnimation
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor
)
# Optional import: QWebEngineView may not be available in minimal builds
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:
    HAS_WEBENGINE = False
from datetime import datetime, timezone
from embereye_base.app.streamconfig_dialog import StreamConfigDialog
from analytics_cards_view import AnalyticsCardsView
from video_widget import VideoWidget
from embereye_base.core.fusion import FusionOrchestrator, DetectionSource
from embereye_base.core.configuration.fusion_config import fusion_config
from embereye_base.core.configuration.hybrid_detection_config import hybrid_detection_config
from embereye_base.core.pipeline_logs import VISION_LOG, FUSION_LOG, log_fusion_event
from embereye_base.core.baseline_manager import BaselineManager
from hawkcore.emberhawk_manager import EmberHawkManager, is_valid_ip
from embereye_base.core.class_config import load_master_classes, get_leaf_classes
from embereye_base.core.analytics import (
    ANALYTICS_CATEGORY_NAMES,
    DEFAULT_ANALYTICS_CATEGORY,
    get_model_hint,
    get_fusion_cards,
)
from incidents import (
    ThermalROIExtractor,
    IncidentRecord,
    IncidentsManager,
    ThermalVisionAnalyzer
)
from embersync import IncidentExporter, IncidentExportMetadata, DetectionFrame
from embereye_base.core.vision_detector import VisionDetector, SEVERITY_RANK

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
                from PyQt6.QtWidgets import QWidget
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
        """Handle monitor geometry changes without forcing window state transitions."""
        if bool(getattr(self, '_screen_geometry_change_in_progress', False)):
            return
        if self.isMinimized():
            return
        self._screen_geometry_change_in_progress = True
        try:
            # Avoid calling showMaximized()/setGeometry() here: those can re-trigger
            # geometry callbacks and fight user-initiated maximize/restore actions.
            self._apply_responsive_dashboard_scaling()
        except Exception:
            pass
        finally:
            self._screen_geometry_change_in_progress = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_dashboard_scaling()

    def _build_status_chip_style(self, tone="neutral"):
        palette = {
            "neutral": ("#8edff0", "#13222d", "#2f5062"),
            "ok": ("#b8f4dd", "#153026", "#2f7f62"),
            "warn": ("#ffe2a8", "#352812", "#7f5f2f"),
            "error": ("#ffd0d0", "#391919", "#8d3d3d"),
        }
        fg, bg, bd = palette.get(tone, palette["neutral"])
        return (
            "QLabel { "
            f"color: {fg}; "
            f"background: {bg}; "
            f"border: 1px solid {bd}; "
            "border-radius: 5px; "
            "padding: 2px 7px; "
            "font-size: 11px; "
            "font-family: \"Avenir Next\", \"Segoe UI\", \"Helvetica Neue\", sans-serif; "
            "}"
        )

    def _set_status_chip_state(self, label, tone="neutral"):
        if label is None:
            return
        try:
            label.setStyleSheet(self._build_status_chip_style(tone))
        except Exception:
            pass

    def _apply_responsive_dashboard_scaling(self):
        """Adjust high-frequency UI dimensions for laptop/desktop resolutions."""
        try:
            width = max(640, int(self.width()))
            if width < 1200:
                header_height = 46
                group_width = 122
                grid_width = 82
                nav_size = 44
            elif width > 1800:
                header_height = 56
                group_width = 156
                grid_width = 96
                nav_size = 54
            else:
                header_height = 50
                group_width = 140
                grid_width = 90
                nav_size = 50

            if hasattr(self, 'overlay_header') and self.overlay_header:
                self.overlay_header.setFixedHeight(header_height)
            if hasattr(self, 'group_combo') and self.group_combo:
                self.group_combo.setFixedWidth(group_width)
            if hasattr(self, 'grid_size') and self.grid_size:
                self.grid_size.setFixedWidth(grid_width)

            # Keep nav buttons proportional and re-centered as window changes.
            if hasattr(self, 'prev_rtsp') and hasattr(self, 'next_rtsp') and hasattr(self, 'tabs'):
                for btn in (self.prev_rtsp, self.next_rtsp):
                    btn.setFixedSize(nav_size, nav_size)
                    btn.setStyleSheet(
                        "QPushButton {"
                        "background-color: rgba(11, 21, 29, 0.92);"
                        "border: 1px solid #3f6a82;"
                        f"border-radius: {nav_size // 2}px;"
                        "color: #7fd6e6;"
                        "font-size: 18px;"
                        "font-weight: bold;"
                        "}"
                        "QPushButton:hover {"
                        "background-color: rgba(26, 44, 57, 0.95);"
                        "border-color: #66b4c8;"
                        "}"
                        "QPushButton:pressed {"
                        "background-color: rgba(41, 64, 79, 0.95);"
                        "}"
                    )
        except Exception:
            pass

    def _animate_dashboard_entry(self):
        """Fade in the main tab surface once at startup for a smoother first paint."""
        try:
            if not hasattr(self, 'tabs') or self.tabs is None:
                return
            if bool(self.config.get('reduced_motion', False)):
                self.tabs.setGraphicsEffect(None)
                return
            effect = QGraphicsOpacityEffect(self.tabs)
            self.tabs.setGraphicsEffect(effect)
            effect.setOpacity(0.0)

            self._entry_fade_animation = QPropertyAnimation(effect, b"opacity", self)
            self._entry_fade_animation.setDuration(320)
            self._entry_fade_animation.setStartValue(0.0)
            self._entry_fade_animation.setEndValue(1.0)
            self._entry_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._entry_fade_animation.start()
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
            from PyQt6.QtGui import QImage, QPixmap
            frame = cand['frame']
            # Convert to RGB if needed
            if len(frame.shape) == 2:
                frame_rgb = cv2.cvtColor(frame.astype('uint8'), cv2.COLOR_GRAY2RGB)
            else:
                frame_rgb = frame.astype('uint8')
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            thumb = QPixmap.fromImage(q_img).scaled(64, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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

    def _current_fusion_config(self):
        return {
            'temp_threshold': float(getattr(self, 'fusion_temp_threshold', fusion_config.temp_threshold)),
            'gas_ppm_threshold': float(getattr(self, 'fusion_gas_ppm_threshold', fusion_config.gas_ppm_threshold)),
            'flame_active_value': int(getattr(self, 'fusion_flame_active_value', 1)),
            'min_sources': int(getattr(self, 'fusion_min_sources', 2)),
            'critical_temp_threshold': float(getattr(self, 'fusion_critical_temp_threshold', fusion_config.critical_temp_threshold)),
            'smoke_threshold_pct': float(getattr(self, 'fusion_smoke_threshold_pct', fusion_config.smoke_threshold_pct)),
            'flame_threshold_pct': float(getattr(self, 'fusion_flame_threshold_pct', fusion_config.flame_threshold_pct)),
            'vision_threshold': float(getattr(self, 'fusion_vision_threshold', fusion_config.vision_threshold)),
            'vision_confidence_weight': float(getattr(self, 'fusion_vision_confidence_weight', fusion_config.vision_confidence_weight)),
            'enable_temporal_fusion': bool(getattr(self, 'fusion_enable_temporal', False)),
        }

    def _normalize_analytics_category(self, value):
        category = str(value or '').strip().lower()
        if category in ANALYTICS_CATEGORY_NAMES:
            return category
        return DEFAULT_ANALYTICS_CATEGORY

    def _normalize_enabled_analytics_categories(self, value):
        """Normalize configured analytics categories to a non-empty valid list."""
        categories = []
        if isinstance(value, list):
            categories = [str(item).strip().lower() for item in value]
        elif isinstance(value, str):
            categories = [part.strip().lower() for part in value.split(',') if part.strip()]

        valid = []
        for category in categories:
            if category in ANALYTICS_CATEGORY_NAMES and category not in valid:
                valid.append(category)

        if not valid:
            active = self._normalize_analytics_category(
                getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)
            )
            valid = [active]
        return valid

    def _default_fusion_card_selection(self):
        return {
            category: list(get_fusion_cards(category))
            for category in ANALYTICS_CATEGORY_NAMES
        }

    def _normalize_fusion_card_selection(self, value):
        """Normalize manual fusion card selection map from config."""
        normalized = self._default_fusion_card_selection()
        if not isinstance(value, dict):
            return normalized

        for category in ANALYTICS_CATEGORY_NAMES:
            raw = value.get(category)
            allowed = list(get_fusion_cards(category))
            if isinstance(raw, list):
                filtered = []
                for card_key in raw:
                    key = str(card_key).strip().lower()
                    if key in allowed and key not in filtered:
                        filtered.append(key)
                if filtered:
                    normalized[category] = filtered
        return normalized

    def _load_analytics_banner_preferences(self):
        self.enabled_analytics_categories = self._normalize_enabled_analytics_categories(
            self.config.get('enabled_analytics_categories', [])
        )
        self.fusion_banner_enabled = bool(self.config.get('fusion_banner_enabled', True))
        mode = str(self.config.get('fusion_banner_mode', 'auto') or 'auto').strip().lower()
        self.fusion_banner_mode = 'manual' if mode == 'manual' else 'auto'
        self.fusion_banner_manual_cards = self._normalize_fusion_card_selection(
            self.config.get('fusion_banner_manual_cards', {})
        )

    def _persist_analytics_banner_preferences(self):
        """Persist analytics/banner selection and keep runtime category valid."""
        selected = self._normalize_enabled_analytics_categories(
            getattr(self, 'enabled_analytics_categories', [])
        )
        self.enabled_analytics_categories = selected

        active = self._normalize_analytics_category(
            getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)
        )
        if active not in selected:
            active = selected[0]
            self.active_analytics_category = active

        self.config['enabled_analytics_categories'] = list(selected)
        self.config['fusion_banner_enabled'] = bool(getattr(self, 'fusion_banner_enabled', True))
        self.config['fusion_banner_mode'] = str(getattr(self, 'fusion_banner_mode', 'auto'))
        self.config['fusion_banner_manual_cards'] = self._normalize_fusion_card_selection(
            getattr(self, 'fusion_banner_manual_cards', {})
        )
        self.config['active_analytics_category'] = active
        StreamConfig.save_config(self.config)

    def _apply_banner_preferences_to_widgets(self):
        """Push banner preferences into existing tile fusion payloads for immediate redraw."""
        for widget in self.get_video_widgets():
            try:
                payload = dict(widget.fusion_data or {})
                if payload:
                    payload['enabled_analytics_categories'] = list(self.enabled_analytics_categories)
                    payload['fusion_banner_enabled'] = bool(self.fusion_banner_enabled)
                    payload['fusion_banner_mode'] = str(self.fusion_banner_mode)
                    payload['fusion_banner_manual_cards'] = dict(self.fusion_banner_manual_cards)
                    payload['analytics_category'] = str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
                    payload['fusion_display_category'] = str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
                    widget.set_fusion_data(payload)
                else:
                    widget.update()
            except Exception:
                continue

    def _resolve_model_path_for_category(self, category):
        """Resolve a model path for the active analytics category.

        Priority:
        1. Explicit override from stream_config.json analytics_model_paths[category]
        2. Legacy override from <category>_model_path
        3. Newest .pt file whose filename matches the category hint
        """
        config = getattr(self, 'config', {}) or {}
        category = self._normalize_analytics_category(category)

        raw_model_paths = config.get('analytics_model_paths', {})
        if isinstance(raw_model_paths, dict):
            explicit_path = str(raw_model_paths.get(category, '') or '').strip()
            if explicit_path:
                explicit_candidate = Path(explicit_path).expanduser()
                if not explicit_candidate.is_absolute():
                    explicit_candidate = Path.cwd() / explicit_candidate
                if explicit_candidate.exists():
                    return str(explicit_candidate)

        legacy_path = str(config.get(f'{category}_model_path', '') or '').strip()
        if legacy_path:
            legacy_candidate = Path(legacy_path).expanduser()
            if not legacy_candidate.is_absolute():
                legacy_candidate = Path.cwd() / legacy_candidate
            if legacy_candidate.exists():
                return str(legacy_candidate)

        hint = str(get_model_hint(category) or '').strip().lower()
        if not hint:
            return None
        model_dirs = []
        try:
            model_dirs.append(Path(get_data_path('models')))
        except Exception:
            pass
        try:
            model_dirs.append(Path(get_resource_path('models')))
        except Exception:
            pass
        # Local-dev fallback
        model_dirs.append(Path.cwd() / 'models')

        candidates = []
        seen_dirs = set()
        for model_dir in model_dirs:
            try:
                resolved_dir = model_dir.resolve()
            except Exception:
                continue
            if not resolved_dir.exists() or resolved_dir in seen_dirs:
                continue
            seen_dirs.add(resolved_dir)
            try:
                for pt_path in resolved_dir.glob('*.pt'):
                    name = pt_path.name.lower()
                    if hint in name:
                        try:
                            mtime = pt_path.stat().st_mtime
                        except Exception:
                            mtime = 0.0
                        candidates.append((mtime, str(pt_path)))
            except Exception:
                continue

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _reload_rule_engine_for_active_category(self):
        """Reload vision inference model based on active analytics category."""
        self.active_analytics_category = self._normalize_analytics_category(
            getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)
        )
        model_path = self._resolve_model_path_for_category(self.active_analytics_category)
        try:
            if model_path:
                self._rule_engine = VisionDetector(yolo_model_path=model_path)
                self._rule_engine_model_path = model_path
                print(f"[ANALYTICS] Category={self.active_analytics_category} using model: {model_path}")
            else:
                self._rule_engine = VisionDetector(yolo_model_path="__no_model__")
                self._rule_engine_model_path = None
                print(f"[ANALYTICS] Category={self.active_analytics_category} has no matching model; heuristic-only mode")
        except Exception as e:
            self._rule_engine = None
            self._rule_engine_model_path = None
            print(f"[ANALYTICS] Rule engine init failed for category={self.active_analytics_category}: {e}")

    def _update_fusion_engine_config(self):
        if hasattr(self, 'fusion_orchestrator') and self.fusion_orchestrator is not None:
            self.fusion_orchestrator.update_config(self._current_fusion_config())

    def _run_fusion(self, thermal_matrix=None, gas_ppm=None, flame=None, vision_score=None, **kwargs):
        self._update_fusion_engine_config()
        cfg = self._current_fusion_config()

        frame_data = {}
        if thermal_matrix is not None:
            frame_data['thermal'] = thermal_matrix
        if gas_ppm is not None:
            frame_data['gas_ppm'] = gas_ppm
        if flame is not None:
            frame_data['flame_digital'] = flame
        if vision_score is not None:
            frame_data['vision_score'] = vision_score

        if 'vision_detections' in kwargs:
            frame_data['vision_detections'] = kwargs.get('vision_detections')
        if 'smoke_pct' in kwargs:
            frame_data['smoke_pct'] = kwargs.get('smoke_pct')
        if 'flame_analog_pct' in kwargs:
            frame_data['flame_analog_pct'] = kwargs.get('flame_analog_pct')
        if 'flame_digital' in kwargs:
            frame_data['flame_digital'] = kwargs.get('flame_digital')
        if 'mpy30' in kwargs:
            frame_data['flame_digital'] = kwargs.get('mpy30')

        fusion_result = self.fusion_orchestrator.process_frame(frame_data)

        source_names = []
        for detection in fusion_result.detections:
            if detection.source in (DetectionSource.FLAME_ANALOG, DetectionSource.FLAME_DIGITAL):
                source_names.append('flame')
            else:
                source_names.append(detection.source.name.lower())

        thermal_detection = next((item for item in fusion_result.detections if item.source == DetectionSource.THERMAL), None)
        hot_cells = thermal_detection.metadata.get('hot_cells', []) if thermal_detection else []
        thermal_max = float(thermal_detection.metadata.get('max_temp', 0.0)) if thermal_detection else 0.0

        result = {
            'alarm': bool(fusion_result.alarm),
            'alarm_reason': fusion_result.metadata.get('reason'),
            'confidence': float(fusion_result.confidence),
            'analytics_category': str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)),
            'fusion_display_category': str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)),
            'enabled_analytics_categories': list(
                getattr(
                    self,
                    'enabled_analytics_categories',
                    [getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)],
                )
            ),
            'fusion_banner_enabled': bool(getattr(self, 'fusion_banner_enabled', True)),
            'fusion_banner_mode': str(getattr(self, 'fusion_banner_mode', 'auto')),
            'fusion_banner_manual_cards': dict(
                getattr(self, 'fusion_banner_manual_cards', self._default_fusion_card_selection())
            ),
            'sources': source_names,
            'hot_cells': hot_cells,
            'thermal_max': thermal_max,
            'gas_ppm': float(gas_ppm) if gas_ppm is not None else 0.0,
            'smoke_pct': float(kwargs.get('smoke_pct', 0.0) or 0.0),
            'smoke_level': float(kwargs.get('smoke_level', kwargs.get('smoke_pct', 0.0)) or 0.0),
            'flame_analog_pct': float(kwargs.get('flame_analog_pct', 0.0) or 0.0),
            'flame_digital': int(kwargs.get('flame_digital', frame_data.get('flame_digital', 0)) or 0),
            # PPE analytics keys (ignored in fire mode; consumed by PPE fusion banner).
            'helmet_count': int(kwargs.get('helmet_count', 0) or 0),
            'no_helmet_count': int(kwargs.get('no_helmet_count', 0) or 0),
            'vest_count': int(kwargs.get('vest_count', 0) or 0),
            'no_vest_count': int(kwargs.get('no_vest_count', 0) or 0),
            'total_persons': int(kwargs.get('total_persons', 0) or 0),
            'temp_threshold': float(cfg.get('temp_threshold', fusion_config.temp_threshold)),
            'critical_temp_threshold': float(cfg.get('critical_temp_threshold', fusion_config.critical_temp_threshold)),
            'gas_ppm_threshold': float(cfg.get('gas_ppm_threshold', fusion_config.gas_ppm_threshold)),
            'smoke_threshold_pct': float(cfg.get('smoke_threshold_pct', fusion_config.smoke_threshold_pct)),
            'flame_threshold_pct': float(cfg.get('flame_threshold_pct', fusion_config.flame_threshold_pct)),
            'severity': fusion_result.severity.name,
        }
        result.update(kwargs)
        return result

    def handle_vision_score_from_widget(self, loc_id, score):
        """Run fusion for this loc_id with vision score and update alarm indicator."""
        try:
            self._record_incident_vision_event(loc_id, score)
        except Exception:
            pass
        loc_key = str(loc_id) if loc_id is not None else None
        now_ts = time.time()
        last_sensor_ts = float(self._sensor_last_packet_ts_by_loc_id.get(loc_key, 0.0)) if loc_key else 0.0
        has_recent_sensor = bool(last_sensor_ts > 0.0 and (now_ts - last_sensor_ts) <= float(self._sensor_overlay_stale_timeout_s))

        # Find widget for loc_id
        for widget in self.get_video_widgets():
            if getattr(widget, 'loc_id', None) == loc_id:
                if not has_recent_sensor:
                    # No fresh PFDS sensor input for this tile.
                    # Keep alarm latched until explicit ACK/Silence.
                    try:
                        if hasattr(widget, 'set_fusion_data'):
                            widget.set_fusion_data(None)
                        self._handle_alarm_transition(loc_id, False, source='sensor_stale')
                        if hasattr(widget, 'update_fire_alarm'):
                            effective_alarm = bool(self._alarm_state_by_loc_id.get(str(loc_id), False))
                            widget.update_fire_alarm(effective_alarm)
                    except Exception:
                        pass
                    break

                # Run fusion with only vision score (other sources can be cached for full fusion)
                ppe_kwargs = {}
                try:
                    if str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)).strip().lower() == 'ppe':
                        loc_key = str(loc_id) if loc_id is not None else '_broadcast'
                        cache = getattr(self, '_ppe_stats_by_loc_id', {}) or {}
                        ppe_kwargs.update(cache.get(loc_key, {}))

                        # Prefer freshest stats from the active rule engine when available.
                        details = getattr(getattr(self, '_rule_engine', None), 'last_details', None)
                        if isinstance(details, dict):
                            stats = details.get('ppe_stats', {})
                            if isinstance(stats, dict):
                                ppe_kwargs.update({
                                    'helmet_count': int(stats.get('helmet_count', ppe_kwargs.get('helmet_count', 0)) or 0),
                                    'no_helmet_count': int(stats.get('no_helmet_count', ppe_kwargs.get('no_helmet_count', 0)) or 0),
                                    'vest_count': int(stats.get('vest_count', ppe_kwargs.get('vest_count', 0)) or 0),
                                    'no_vest_count': int(stats.get('no_vest_count', ppe_kwargs.get('no_vest_count', 0)) or 0),
                                    'total_persons': int(stats.get('total_persons', ppe_kwargs.get('total_persons', 0)) or 0),
                                })
                                cache[loc_key] = dict(ppe_kwargs)
                                self._ppe_stats_by_loc_id = cache
                except Exception:
                    ppe_kwargs = {}

                fusion_result = self._run_fusion(vision_score=score, **ppe_kwargs)
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
                        self._handle_alarm_transition(loc_id, bool(fusion_result.get('alarm')), source='vision_only')
                        effective_alarm = bool(self._alarm_state_by_loc_id.get(str(loc_id), bool(fusion_result.get('alarm'))))
                        widget.update_fire_alarm(effective_alarm)
                        if hasattr(widget, 'set_alarm_acknowledged'):
                            acked = bool(self._alarm_ack_by_loc_id.get(str(loc_id), False))
                            widget.set_alarm_acknowledged(acked)
                        self._record_incident_fusion_event(loc_id, fusion_result, source='vision_only')
                    except Exception as e:
                        print(f"Alarm update error (vision): {e}")
                break

    def _normalize_loc_key(self, loc_id):
        if loc_id is None:
            return None
        key = str(loc_id).strip()
        return key or None

    def _normalize_serial_key(self, serial_number):
        if serial_number is None:
            return None
        key = str(serial_number).strip()
        return key or None

    def _parse_seen_timestamp(self, value):
        """Parse DB/packet timestamps into epoch seconds."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc).timestamp()
            return value.timestamp()

        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            pass
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            return None

    def _get_device_lifecycle_state(self, device: dict, now_ts: float = None) -> str:
        """Classify configured devices into operational lifecycle states."""
        if not isinstance(device, dict):
            return 'pending_identity'

        serial = self._normalize_serial_key(device.get('serial_number'))
        if not serial:
            return 'pending_identity'

        is_authorized = bool(device.get('is_authorized', True))
        is_linked = bool(device.get('is_linked', True))
        if not is_authorized:
            return 'unauthorized'
        if not is_linked:
            return 'unlinked'

        now_val = float(now_ts if now_ts is not None else time.time())
        ghost_after_s = float(getattr(self, '_device_ghost_after_s', 120.0))
        last_seen_ts = self._parse_seen_timestamp(device.get('last_seen_at'))
        if last_seen_ts is not None and (now_val - last_seen_ts) > ghost_after_s:
            return 'ghost'
        return 'active'

    def _get_pending_identity_state(self, pending_info: dict, now_ts: float = None) -> str:
        """Classify pending identity sightings as pending/unlinked/location-pending/ghost."""
        if not isinstance(pending_info, dict):
            return 'pending_identity'
        explicit_state = str(pending_info.get('state') or '').strip()
        if explicit_state in ('unlinked', 'pending_location', 'unauthorized'):
            return explicit_state
        now_val = float(now_ts if now_ts is not None else time.time())
        ghost_after_s = float(getattr(self, '_device_ghost_after_s', 120.0))
        last_seen_ts = self._parse_seen_timestamp(pending_info.get('last_seen'))
        if last_seen_ts is not None and (now_val - last_seen_ts) > ghost_after_s:
            return 'ghost'
        return 'pending_identity'

    def _emit_device_telemetry(self, event: str, **fields):
        """Emit serial-centric telemetry for device lifecycle and routing decisions."""
        payload = {'event': str(event)}
        for key, value in fields.items():
            if value is not None:
                payload[str(key)] = value
        try:
            from metrics import get_metrics
            metrics = get_metrics()
            event_name = str(event)
            state = str(payload.get('state') or 'unknown')
            drop_reason = str(payload.get('drop_reason') or 'unknown')
            command = str(payload.get('command') or 'unknown')

            metrics.record_device_lifecycle_event(event_name, state=state)
            if event_name == 'packet_dropped':
                metrics.record_device_packet_drop(drop_reason=drop_reason, state=state)
            if event_name in ('command_sent', 'command_failed'):
                metrics.record_device_command(event=event_name, command=command)
            if event_name == 'command_failed':
                metrics.record_device_command_failure(drop_reason=drop_reason, command=command)
        except Exception:
            pass
        try:
            from embereye_base.utils.tcp_logger import log_device_telemetry
            log_device_telemetry(event=str(event), payload=payload)
        except Exception:
            pass
        try:
            should_print = True
            event_name = str(payload.get('event') or '')
            drop_reason = str(payload.get('drop_reason') or '')
            if event_name == 'command_failed' and drop_reason in ('tcp_server_unavailable', 'no_active_connection'):
                # Preserve structured telemetry, but suppress repetitive console output.
                should_print = False

            if should_print:
                print(f"[DEVICE_TELEMETRY] {json.dumps(payload, sort_keys=True, default=str)}")
        except Exception:
            print(f"[DEVICE_TELEMETRY] {payload}")

    def _operator_actor(self) -> str:
        operator_id = str(getattr(self, '_operator_id', '') or '').strip()
        if operator_id:
            return f"ui:{operator_id}"
        return f"ui:{os.getenv('USER', 'unknown')}"

    def _ensure_operator_identity(self, parent=None, action: str = "device mutation") -> bool:
        """Require an explicit operator identity before sensitive PFDS mutations."""
        existing = str(getattr(self, '_operator_id', '') or '').strip()
        if existing:
            return True

        prompt_parent = parent or self
        text, ok = QInputDialog.getText(
            prompt_parent,
            "Operator Identity Required",
            f"Enter operator id for {action}:",
        )
        operator_id = str(text or '').strip()
        if not ok or not operator_id:
            QMessageBox.warning(prompt_parent, "Operator Required", "Operation canceled: operator id is required.")
            return False

        self._operator_id = operator_id
        try:
            self.config['operator_id'] = operator_id
            StreamConfig.save_config(self.config)
        except Exception:
            pass
        return True

    @staticmethod
    def _sum_counter_delta(previous: dict, current: dict) -> int:
        prev = previous or {}
        curr = current or {}
        delta = 0
        for key, value in curr.items():
            try:
                delta += max(0, int(value) - int(prev.get(key, 0)))
            except Exception:
                continue
        return int(delta)

    def _snapshot_device_alert_counters(self):
        try:
            from metrics import get_metrics
            metrics = get_metrics()
            return {
                'packet_drops': dict(getattr(metrics, 'device_packet_drops_total', {}) or {}),
                'command_failures': dict(getattr(metrics, 'device_command_failures_total', {}) or {}),
            }
        except Exception:
            return {'packet_drops': {}, 'command_failures': {}}

    def _start_device_alert_monitor(self):
        """Start periodic operational alert checks from device telemetry counters."""
        if getattr(self, '_device_alert_timer', None):
            return
        self._device_alert_last_snapshot = self._snapshot_device_alert_counters()
        self._device_alert_last_ts = time.time()
        self._device_alert_timer = QTimer(self)
        self._device_alert_timer.timeout.connect(self._check_device_alerts)
        self._device_alert_timer.start(max(1000, int(self._device_alert_window_ms)))

    def _start_scheduled_reconcile(self):
        """Start periodic pending-identity reconciliation job with safety guards."""
        if not bool(getattr(self, '_reconcile_schedule_enabled', False)):
            return
        if getattr(self, '_reconcile_timer', None):
            return
        self._reconcile_timer = QTimer(self)
        self._reconcile_timer.timeout.connect(self._run_scheduled_reconcile)
        self._reconcile_timer.start(max(1000, int(self._reconcile_interval_s * 1000)))

    def _disable_scheduled_reconcile(self, reason: str):
        self._reconcile_schedule_enabled = False
        try:
            self.config['reconcile_schedule_enabled'] = False
            StreamConfig.save_config(self.config)
        except Exception:
            pass
        try:
            if self._reconcile_timer:
                self._reconcile_timer.stop()
                self._reconcile_timer = None
        except Exception:
            pass
        try:
            from metrics import get_metrics
            get_metrics().record_scheduled_reconcile_disabled()
        except Exception:
            pass
        self._emit_device_telemetry(
            'scheduled_reconcile_disabled',
            state='warning',
            drop_reason='failure_guard',
            reason=reason,
        )

    def _run_scheduled_reconcile(self):
        if not bool(getattr(self, '_reconcile_schedule_enabled', False)):
            return
        now = time.time()
        if now - float(getattr(self, '_reconcile_last_run_ts', 0.0) or 0.0) < float(self._reconcile_cooldown_s):
            return

        pending = dict(getattr(self, '_pending_device_by_serial', {}) or {})
        if not pending:
            return

        try:
            summary = self.emberhawk.bulk_reconcile_pending_serials(
                pending,
                auto_link=True,
                actor='system:scheduled_reconcile',
                dry_run=False,
            )
            self._reconcile_last_run_ts = now
            self._reconcile_last_summary = dict(summary)

            bound_serials = summary.get('bound_serials', []) or []
            for serial in bound_serials:
                self._pending_device_by_serial.pop(serial, None)

            bound = int(summary.get('bound', 0))
            unmatched = int(summary.get('unmatched', 0))
            errors = int(summary.get('errors', 0))

            try:
                from metrics import get_metrics
                outcome = 'success' if errors == 0 else 'partial_error'
                get_metrics().record_scheduled_reconcile_run(
                    outcome=outcome,
                    bound=bound,
                    unmatched=unmatched,
                    errors=errors,
                )
            except Exception:
                pass

            if errors > 0:
                self._reconcile_consecutive_errors += 1
            else:
                self._reconcile_consecutive_errors = 0

            if bound > 0 or unmatched > 0 or errors > 0:
                msg = (
                    f"Scheduled Reconcile: bound={bound}, unmatched={unmatched}, errors={errors}"
                )
                print(f"ℹ️  {msg}")
                try:
                    self.statusBar().showMessage(msg, 4000)
                except Exception:
                    pass

            self._emit_device_telemetry(
                'scheduled_reconcile_run',
                state='active',
                command='scheduled_reconcile',
                attempted=int(summary.get('attempted', 0)),
                bound=bound,
                unmatched=unmatched,
                errors=errors,
            )

            if self._reconcile_consecutive_errors >= int(self._reconcile_max_consecutive_errors):
                self._disable_scheduled_reconcile(
                    reason=f"consecutive_errors={self._reconcile_consecutive_errors}"
                )
        except Exception as e:
            self._reconcile_consecutive_errors += 1
            try:
                from metrics import get_metrics
                get_metrics().record_scheduled_reconcile_run(
                    outcome='exception',
                    bound=0,
                    unmatched=0,
                    errors=1,
                )
            except Exception:
                pass
            self._emit_device_telemetry(
                'scheduled_reconcile_error',
                state='warning',
                drop_reason='exception',
                error=str(e),
                consecutive_errors=int(self._reconcile_consecutive_errors),
            )
            if self._reconcile_consecutive_errors >= int(self._reconcile_max_consecutive_errors):
                self._disable_scheduled_reconcile(
                    reason=f"exception_threshold:{self._reconcile_consecutive_errors}"
                )

    def _check_device_alerts(self):
        now = time.time()
        prev_snapshot = getattr(self, '_device_alert_last_snapshot', None)
        prev_ts = float(getattr(self, '_device_alert_last_ts', 0.0) or 0.0)

        current_snapshot = self._snapshot_device_alert_counters()
        self._device_alert_last_snapshot = current_snapshot
        self._device_alert_last_ts = now

        if not prev_snapshot or prev_ts <= 0:
            return

        elapsed = now - prev_ts
        if elapsed <= 0:
            return

        drop_delta = self._sum_counter_delta(prev_snapshot.get('packet_drops'), current_snapshot.get('packet_drops'))
        fail_delta = self._sum_counter_delta(prev_snapshot.get('command_failures'), current_snapshot.get('command_failures'))

        drop_rate_per_min = (drop_delta * 60.0) / elapsed
        fail_rate_per_min = (fail_delta * 60.0) / elapsed

        should_alert = (
            drop_rate_per_min >= float(self._device_drop_alert_per_min)
            or fail_rate_per_min >= float(self._device_command_fail_alert_per_min)
        )
        if not should_alert:
            return

        last_emit = float(getattr(self, '_device_alert_last_emit_ts', 0.0) or 0.0)
        if now - last_emit < float(self._device_alert_cooldown_s):
            return

        self._device_alert_last_emit_ts = now
        message = (
            f"Device Ops Alert: drop_rate={drop_rate_per_min:.1f}/min "
            f"fail_rate={fail_rate_per_min:.1f}/min"
        )
        print(f"⚠️  {message}")
        try:
            self.statusBar().showMessage(message, 5000)
        except Exception:
            pass
        self._emit_device_telemetry(
            'ops_alert',
            state='warning',
            drop_reason='high_rate',
            drop_rate_per_min=round(drop_rate_per_min, 2),
            command_fail_rate_per_min=round(fail_rate_per_min, 2),
        )

    def _register_device_identity_packet(self, packet: dict) -> None:
        """Track identity handshake packets and bind serials to configured devices."""
        if not isinstance(packet, dict):
            return

        serial = self._normalize_serial_key(packet.get('serial_number') or packet.get('serialno'))
        client_ip = self._normalize_loc_key(packet.get('client_ip'))
        if not serial:
            return

        if client_ip:
            self._serial_by_client_ip[client_ip] = serial

        device = None
        try:
            if getattr(self, 'emberhawk', None):
                device = self.emberhawk.bind_serial_to_existing_device(serial, client_ip)
                if not device:
                    device = self.emberhawk.get_device_by_serial(serial)
        except Exception as e:
            print(f"Identity bind failed for serial={serial}: {e}")
            device = None

        if device:
            mapped_loc = self._normalize_loc_key(device.get('location_id'))
            if mapped_loc:
                self._loc_by_serial[serial] = mapped_loc

            is_linked = bool(device.get('is_linked', True))
            is_authorized = bool(device.get('is_authorized', True))
            if mapped_loc and is_linked and is_authorized:
                self._pending_device_by_serial.pop(serial, None)
                self.emberhawk.touch_device_seen(serial, client_ip)
                print(f"🔐 Identity mapped: serial={serial} -> device_id={device.get('id')} loc_id={device.get('location_id')}")
                self._emit_device_telemetry(
                    'identity_mapped',
                    serial=serial,
                    client_ip=client_ip,
                    location_id=device.get('location_id'),
                    state=self._get_device_lifecycle_state(device),
                )
                return

            if not mapped_loc:
                pending_state = 'pending_location'
            elif not is_linked:
                pending_state = 'unlinked'
            else:
                pending_state = 'unauthorized'
            self._pending_device_by_serial[serial] = {
                'serial_number': serial,
                'client_ip': client_ip,
                'last_seen': time.time(),
                'state': pending_state,
                'device_id': device.get('id'),
            }
            print(f"⏳ Identity pending: serial={serial} state={pending_state}")
            self._emit_device_telemetry(
                'identity_pending',
                serial=serial,
                client_ip=client_ip,
                location_id=device.get('location_id'),
                state=pending_state,
            )
            return

        self._pending_device_by_serial[serial] = {
            'serial_number': serial,
            'client_ip': client_ip,
            'last_seen': time.time(),
        }
        print(f"⏳ Identity pending: serial={serial} (no linked device yet)")
        self._emit_device_telemetry(
            'identity_pending',
            serial=serial,
            client_ip=client_ip,
            state='pending_identity',
        )

    def _resolve_packet_identity(self, packet: dict):
        """Resolve packet to serial and managed device, preferring serial-first identity."""
        if not isinstance(packet, dict):
            return None, None

        client_ip = self._normalize_loc_key(packet.get('client_ip'))
        serial = self._normalize_serial_key(packet.get('serial_number') or packet.get('serialno'))
        if not serial:
            # Some packet parsers populate loc_id with the hardware serial (e.g. EHWK005001)
            # but may omit serial_number. Use loc_id as a safe serial fallback.
            loc_token = self._normalize_serial_key(packet.get('loc_id'))
            if loc_token and loc_token.upper().startswith('EHWK'):
                serial = loc_token
                packet['serial_number'] = serial
        if not serial and client_ip:
            serial = self._normalize_serial_key(self._serial_by_client_ip.get(client_ip))
            if serial:
                packet['serial_number'] = serial

        device = None
        try:
            if serial and getattr(self, 'emberhawk', None):
                device = self.emberhawk.get_device_by_serial(serial)
                if not device:
                    device = self.emberhawk.bind_serial_to_existing_device(serial, client_ip)
                if device and client_ip:
                    self.emberhawk.touch_device_seen(serial, client_ip)
        except Exception as e:
            print(f"Packet identity resolve error: {e}")

        if device and serial:
            mapped_loc = self._normalize_loc_key(device.get('location_id'))
            if mapped_loc:
                self._loc_by_serial[serial] = mapped_loc

        return serial, device

    def _is_packet_authorized_and_linked(self, packet: dict) -> bool:
        """Allow only authorized/linked devices into fusion/UI pipeline."""
        serial, device = self._resolve_packet_identity(packet)
        pkt_type = packet.get('type') if isinstance(packet, dict) else 'unknown'
        client_ip = self._normalize_loc_key(packet.get('client_ip')) if isinstance(packet, dict) else None
        packet_loc = self._normalize_loc_key(packet.get('loc_id')) if isinstance(packet, dict) else None

        def _touch_pending_identity(state_name: str = 'pending_identity', device_id=None):
            if not serial:
                return
            prior = dict(self._pending_device_by_serial.get(serial) or {})
            prior['serial_number'] = serial
            prior['client_ip'] = client_ip or prior.get('client_ip') or ''
            prior['last_seen'] = time.time()
            prior['state'] = state_name
            if device_id is not None:
                prior['device_id'] = device_id
            self._pending_device_by_serial[serial] = prior

        if serial:
            packet['serial_number'] = serial

        if not serial:
            peer = client_ip or 'unknown'
            if not self._pending_warned_tokens.get(f"missing:{peer}"):
                print(f"⛔ Dropping packet from {peer}: missing device serial identity")
                self._pending_warned_tokens[f"missing:{peer}"] = time.time()
            self._emit_device_telemetry(
                'packet_dropped',
                packet_type=pkt_type,
                client_ip=peer,
                state='pending_identity',
                drop_reason='missing_serial',
            )
            return False

        if not device and packet_loc:
            # Best-effort fallback: allow packets that match a linked+authorized location,
            # but never override an already bound, different serial for that location.
            loc_device = self._resolve_emberhawk_device_for_loc_id(packet_loc)
            if loc_device:
                loc_serial = self._normalize_serial_key(loc_device.get('serial_number'))
                if loc_serial and loc_serial != serial:
                    _touch_pending_identity('pending_identity')
                    if not self._pending_warned_tokens.get(f"loc-serial-mismatch:{serial}:{packet_loc}"):
                        print(
                            f"⛔ Dropping packet for serial={serial}: "
                            f"loc_id={packet_loc} is already bound to serial={loc_serial}"
                        )
                        self._pending_warned_tokens[f"loc-serial-mismatch:{serial}:{packet_loc}"] = time.time()
                    self._emit_device_telemetry(
                        'packet_dropped',
                        packet_type=pkt_type,
                        serial=serial,
                        client_ip=client_ip,
                        location_id=packet_loc,
                        state='pending_identity',
                        drop_reason='serial_mismatch_for_location',
                    )
                    return False

                if bool(loc_device.get('is_authorized', True)) and bool(loc_device.get('is_linked', True)):
                    device = loc_device
                    self._loc_by_serial[serial] = packet_loc
                    packet['loc_id'] = packet_loc
                    # Keep normal serial-first flow up to date when possible.
                    try:
                        rebound = self.emberhawk.bind_serial_to_existing_device(serial, client_ip)
                        if rebound:
                            device = rebound
                    except Exception:
                        pass

        if not device:
            _touch_pending_identity('pending_identity')
            if not self._pending_warned_tokens.get(f"pending:{serial}"):
                print(f"⏳ Dropping packet for serial={serial}: device not linked in dashboard")
                self._pending_warned_tokens[f"pending:{serial}"] = time.time()
            self._emit_device_telemetry(
                'packet_dropped',
                packet_type=pkt_type,
                serial=serial,
                client_ip=client_ip,
                state='pending_identity',
                drop_reason='device_not_linked',
            )
            return False

        is_authorized = bool(device.get('is_authorized', True))
        is_linked = bool(device.get('is_linked', True))
        state = self._get_device_lifecycle_state(device)
        if not is_authorized or not is_linked:
            pending_state = 'unauthorized' if not is_authorized else 'unlinked'
            _touch_pending_identity(pending_state, device_id=device.get('id'))
            if not self._pending_warned_tokens.get(f"blocked:{serial}"):
                print(
                    f"⛔ Dropping packet for serial={serial}: "
                    f"authorized={is_authorized}, linked={is_linked}"
                )
                self._pending_warned_tokens[f"blocked:{serial}"] = time.time()
            self._emit_device_telemetry(
                'packet_dropped',
                packet_type=pkt_type,
                serial=serial,
                client_ip=client_ip,
                state=state,
                authorized=is_authorized,
                linked=is_linked,
                drop_reason='access_blocked',
            )
            return False

        mapped_loc = self._normalize_loc_key(device.get('location_id')) or self._loc_by_serial.get(serial)
        if mapped_loc:
            # Device mapping is the source of truth once identity is linked.
            packet['loc_id'] = mapped_loc
        self._emit_device_telemetry(
            'packet_accepted',
            packet_type=pkt_type,
            serial=serial,
            client_ip=client_ip,
            location_id=packet.get('loc_id'),
            state=state,
            authorized=True,
            linked=True,
        )
        return True

    def _resolve_emberhawk_device_for_loc_id(self, loc_id):
        """Resolve location id to a configured EmberHawk device record."""
        key = self._normalize_loc_key(loc_id)
        if not key or not getattr(self, 'emberhawk', None):
            return None
        try:
            devices = self.emberhawk.list_devices()
        except Exception as e:
            print(f"EmberHawk lookup failed for loc_id={key}: {e}")
            return None

        for device in devices:
            if str(device.get('location_id') or '').strip() == key:
                return device
        for device in devices:
            if str(device.get('name') or '').strip() == key:
                return device
        # Fallback: match any registered device whose serial has an active TCP connection.
        # This handles the case where the device's registered location_id differs from
        # the stream/widget loc_id (e.g. device registered as "TEST", stream configured
        # as "DemoRoom1").
        try:
            tcp = self.tcp_sensor_server
            if tcp is not None and hasattr(tcp, '_serial_to_client'):
                active_serials = set(tcp._serial_to_client.keys())
                for device in devices:
                    device_serial = str(device.get('serial_number') or '').strip()
                    if device_serial and device_serial in active_serials:
                        return device
        except Exception:
            pass
        return None

    def _send_emberhawk_command_for_loc(self, loc_id, command, reason=''):
        """Send an EmberHawk command to device mapped to a location id."""
        key = self._normalize_loc_key(loc_id)
        if not key:
            return False

        device = self._resolve_emberhawk_device_for_loc_id(key)
        if not device:
            print(f"No EmberHawk device mapping for loc_id={key}; cannot send {command}")
            return False

        cmd = {
            'command': command,
            'ip': device.get('ip'),
            'name': device.get('name') or key,
            'location_id': device.get('location_id') or key,
            'device_id': device.get('id'),
            'serial_number': device.get('serial_number'),
        }
        success = self.dispatch_emberhawk_command(cmd)
        if success:
            msg_reason = f" ({reason})" if reason else ""
            print(f"✅ {command} sent for loc_id={key}{msg_reason}")
        return bool(success)

    def _set_loc_alarm_ack_state(self, loc_id, acknowledged):
        key = self._normalize_loc_key(loc_id)
        if not key:
            return
        self._alarm_ack_by_loc_id[key] = bool(acknowledged)
        widget = self.video_widgets.get(key)
        if widget and hasattr(widget, 'set_alarm_acknowledged'):
            try:
                widget.set_alarm_acknowledged(bool(acknowledged))
            except Exception as e:
                print(f"ACK state UI update failed for loc_id={key}: {e}")

    def _handle_alarm_transition(self, loc_id, alarm_active, source='fusion'):
        """Track alarm transitions and send ALARM_ON once per active cycle.

        Alarm UI is latched until explicit ACK/Silence from operator.
        Incident recording stops when live fusion clears.
        """
        key = self._normalize_loc_key(loc_id)
        if not key:
            return

        now = time.time()
        active = bool(alarm_active)
        prev_active = bool(self._alarm_state_by_loc_id.get(key, False))

        if not active:
            # Stop capture when fusion clears, but keep the visible alarm latched
            # until the operator explicitly acknowledges/silences it.
            if prev_active:
                self._finalize_incident_session(key, feedback='pending', acked=False, end_reason='fusion_clear')

            if prev_active and not bool(self._alarm_ack_by_loc_id.get(key, False)):
                self._alarm_state_by_loc_id[key] = True
                return

            self._alarm_state_by_loc_id[key] = False
            self._alarm_on_sent_by_loc_id[key] = False
            self._alarm_on_retry_ts_by_loc_id[key] = 0.0
            self._set_loc_alarm_ack_state(key, False)
            return

        self._alarm_state_by_loc_id[key] = True

        if not prev_active:
            self._alarm_on_sent_by_loc_id[key] = False
            self._alarm_on_retry_ts_by_loc_id[key] = 0.0
            self._set_loc_alarm_ack_state(key, False)
            self._start_incident_session(key, reason=source)
        elif key not in self._active_incident_sessions:
            self._start_incident_session(key, reason=source)

        if self._alarm_on_sent_by_loc_id.get(key, False):
            return

        retry_every_s = 2.0
        last_retry = float(self._alarm_on_retry_ts_by_loc_id.get(key, 0.0))
        if now - last_retry < retry_every_s:
            return

        self._alarm_on_retry_ts_by_loc_id[key] = now
        sent = self._send_emberhawk_command_for_loc(key, 'ALARM_ON', reason=source)
        if sent:
            self._alarm_on_sent_by_loc_id[key] = True

    def handle_alarm_ack_from_widget(self, loc_id):
        """Handle per-tile triggered action by sending ACK_ON to the mapped device."""
        key = self._normalize_loc_key(loc_id)
        if not key:
            return

        if not bool(self._alarm_state_by_loc_id.get(key, False)):
            self._set_loc_alarm_ack_state(key, False)
            print(f"Ignoring ACK for loc_id={key}: alarm is not active")
            return

        success = self._send_emberhawk_command_for_loc(key, 'ACK_ON', reason='ui_ack')
        if not success:
            # Keep UI responsive even when PFDS transport is temporarily unavailable.
            print(f"ACK_ON failed for loc_id={key}; forcing local stop and finalizing incident")

        self._alarm_state_by_loc_id[key] = False
        self._alarm_on_sent_by_loc_id[key] = False
        self._alarm_on_retry_ts_by_loc_id[key] = 0.0
        self._set_loc_alarm_ack_state(key, True)
        self._finalize_incident_session(key, feedback='pending', acked=True, end_reason='operator_ack')
        widget = self.video_widgets.get(key)
        if widget and hasattr(widget, 'update_fire_alarm'):
            try:
                widget.update_fire_alarm(False, source='manual')
            except Exception:
                pass

    def handle_alarm_raise_from_widget(self, loc_id):
        """Handle per-tile raise action by sending ALARM_ON and starting incident capture."""
        key = self._normalize_loc_key(loc_id)
        if not key:
            return
        self._handle_alarm_transition(key, True, source='ui_raise')

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

    def _extract_ppe_counts_from_detections(self, detections):
        """Extract PPE summary counters from raw detection events."""
        stats = {
            'helmet_count': 0,
            'no_helmet_count': 0,
            'vest_count': 0,
            'no_vest_count': 0,
            'total_persons': 0,
        }
        try:
            for det in detections or []:
                raw_name = ''
                if isinstance(det, dict):
                    raw_name = str(det.get('class', '') or '').strip().lower().replace(' ', '_').replace('-', '_')
                elif det is not None:
                    raw_name = str(det).strip().lower().replace(' ', '_').replace('-', '_')

                if raw_name in {'person', 'worker'}:
                    stats['total_persons'] += 1
                elif raw_name in {'helmet', 'hardhat', 'safety_helmet'}:
                    stats['helmet_count'] += 1
                elif raw_name in {'no_helmet', 'without_helmet', 'head', 'head_no_helmet'}:
                    stats['no_helmet_count'] += 1
                elif raw_name in {'vest', 'safety_vest', 'high_visibility_vest'}:
                    stats['vest_count'] += 1
                elif raw_name in {'no_vest', 'without_vest'}:
                    stats['no_vest_count'] += 1

            if stats['total_persons'] == 0:
                stats['total_persons'] = max(
                    stats['helmet_count'] + stats['no_helmet_count'],
                    stats['vest_count'] + stats['no_vest_count'],
                )
        except Exception:
            return {
                'helmet_count': 0,
                'no_helmet_count': 0,
                'vest_count': 0,
                'no_vest_count': 0,
                'total_persons': 0,
            }
        return stats

    def apply_sensor_config(self, settings: dict):
        """Apply sensor configuration settings from dialog to runtime objects.
        Expects keys: temp_threshold, gas_ppm_threshold, smoke_threshold_pct, flame_threshold_pct,
        vision_threshold, anomaly settings, etc.
        """
        try:
            # Update SensorFusion thresholds
            if 'temp_threshold' in settings:
                self.fusion_temp_threshold = float(settings['temp_threshold'])
            if 'gas_ppm_threshold' in settings:
                self.fusion_gas_ppm_threshold = float(settings['gas_ppm_threshold'])
            if 'smoke_threshold_pct' in settings:
                self.fusion_smoke_threshold_pct = float(settings['smoke_threshold_pct'])
            if 'flame_threshold_pct' in settings:
                self.fusion_flame_threshold_pct = float(settings['flame_threshold_pct'])
            # Vision threshold reference
            self.fusion_vision_threshold = float(settings.get('vision_threshold', getattr(self, 'fusion_vision_threshold', 0.7)))
            self.vision_threshold = self.fusion_vision_threshold
            self._update_fusion_engine_config()

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
            self.config['smoke_threshold_pct'] = self.fusion_smoke_threshold_pct
            self.config['flame_threshold_pct'] = self.fusion_flame_threshold_pct
            self.config['temp_threshold'] = self.fusion_temp_threshold
            self.config['gas_ppm_threshold'] = self.fusion_gas_ppm_threshold
            try:
                StreamConfig.save_config(self.config)
            except Exception as e:
                print(f"Config save error: {e}")

            print(f"Applied sensor config & persisted: smoke_threshold={self.fusion_smoke_threshold_pct}%, flame_threshold={self.fusion_flame_threshold_pct}%")
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
                from PyQt6.QtWidgets import QApplication
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
        self._xray_header_fade_anim = None
        self._xray_status_fade_anim = None
        self._xray_header_opacity_effect = None
        self._xray_status_opacity_effect = None
        
        self.maximized_widget = None
        self.original_layout = None
        self.original_grid_size = None
        self._live_pfds_transition_inflight = False
        self._live_pfds_refresh_inflight = False
        self._live_pfds_deferred_filter = None
        self.config = StreamConfig.load_config()
        self.active_analytics_category = self._normalize_analytics_category(self.config.get('active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
        self._load_analytics_banner_preferences()
        self.video_widgets = {}  # loc_id -> VideoWidget
        self.tcp_server = tcp_server  # Reuse existing or create new
        self.tcp_sensor_server = tcp_sensor_server or tcp_server
        self.current_group = "Default"
        self.current_rtsp_page = 1
        self.current_graph_page = 1
        self.marketplace_plugin_manager = None
        self.analytics_cards_view = None
        self.marketplace_dir = Path(str(
            self.config.get(
                'marketplace_folder',
                Path.home() / 'EmberEye' / 'Marketplace',
            )
        )).expanduser()
        self.grid_rebuild_pending = False  # Track if rebuild is scheduled
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
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
        # Initialize FusionOrchestrator BEFORE initUI to avoid AttributeError
        smoke_thr = float(self.config.get('smoke_threshold_pct', 25.0))
        flame_thr = float(self.config.get('flame_threshold_pct', 25.0))
        temp_thr = float(self.config.get('temp_threshold', 40.0))
        gas_thr = float(self.config.get('gas_ppm_threshold', 400))
        vision_thr = float(self.config.get('vision_threshold', 0.7))
        vision_weight = float(self.config.get('vision_confidence_weight', 0.5))
        self.fusion_temp_threshold = temp_thr
        self.fusion_gas_ppm_threshold = gas_thr
        self.fusion_smoke_threshold_pct = smoke_thr
        self.fusion_flame_threshold_pct = flame_thr
        self.fusion_vision_threshold = vision_thr
        self.fusion_vision_confidence_weight = vision_weight
        self.fusion_flame_active_value = int(self.config.get('flame_active_value', 1))
        self.fusion_min_sources = int(self.config.get('min_sources', 2))
        self.fusion_critical_temp_threshold = float(self.config.get('critical_temp_threshold', fusion_config.critical_temp_threshold))
        self.vision_threshold = self.fusion_vision_threshold
        self.fusion_orchestrator = FusionOrchestrator(self._current_fusion_config())
        print(f"Loaded fusion thresholds: Smoke={smoke_thr}%, Flame={flame_thr}%, Temp={temp_thr}°C, Gas={gas_thr}ppm, VisionThr={vision_thr}, VisionWeight={vision_weight}")
        # Hybrid alarm support (rules + fusion)
        self._fusion_by_loc_id = {}
        self._fusion_ts_by_loc_id = {}
        self._sensor_last_packet_ts_by_loc_id = {}
        self._last_thermal_matrix_by_loc_id = {}
        self._sensor_overlay_stale_timeout_s = float(self.config.get('sensor_overlay_stale_timeout_s', 5.0))
        self._alarm_state_by_loc_id = {}
        self._alarm_ack_by_loc_id = {}
        self._alarm_on_sent_by_loc_id = {}
        self._alarm_on_retry_ts_by_loc_id = {}
        self._active_incident_sessions = {}
        self._incident_rows_by_token = {}
        self._incident_video_save_interval_s = 0.8
        self._incident_thermal_save_interval_s = 0.8
        self._incident_video_record_fps = 2.0
        self._incident_record_timer = QTimer(self)
        self._incident_record_timer.setInterval(500)
        self._incident_record_timer.timeout.connect(self._tick_active_incident_recording)
        self._incident_record_timer.start()
        self._serial_by_client_ip = {}
        self._loc_by_serial = {}
        self._pending_device_by_serial = {}
        self._pending_warned_tokens = {}
        self._device_ghost_after_s = int(self.config.get('device_ghost_after_s', 120))
        raw_pending_from_telemetry = self.config.get('pending_from_telemetry_enabled', False)
        if isinstance(raw_pending_from_telemetry, str):
            self._pending_from_telemetry_enabled = raw_pending_from_telemetry.strip().lower() in (
                '1',
                'true',
                'yes',
                'on',
            )
        else:
            self._pending_from_telemetry_enabled = bool(raw_pending_from_telemetry)
        self._pending_telemetry_retention_s = int(self.config.get('pending_telemetry_retention_s', 24 * 60 * 60))
        self._device_alert_window_ms = int(self.config.get('device_alert_window_ms', 30000))
        self._device_drop_alert_per_min = float(self.config.get('device_drop_alert_per_min', 20.0))
        self._device_command_fail_alert_per_min = float(self.config.get('device_command_fail_alert_per_min', 10.0))
        self._device_alert_cooldown_s = float(self.config.get('device_alert_cooldown_s', 60.0))
        self._device_alert_last_snapshot = None
        self._device_alert_last_ts = 0.0
        self._device_alert_last_emit_ts = 0.0
        self._device_alert_timer = None
        self._reconcile_schedule_enabled = bool(self.config.get('reconcile_schedule_enabled', False))
        self._reconcile_interval_s = float(self.config.get('reconcile_interval_s', 300.0))
        self._reconcile_cooldown_s = float(self.config.get('reconcile_cooldown_s', 120.0))
        self._reconcile_max_consecutive_errors = int(self.config.get('reconcile_max_consecutive_errors', 3))
        self._reconcile_last_run_ts = 0.0
        self._reconcile_consecutive_errors = 0
        self._reconcile_last_summary = {}
        self._reconcile_timer = None
        self._operator_id = str(self.config.get('operator_id', '')).strip()
        self._rule_engine = None
        self._rule_engine_model_path = None
        self._reload_rule_engine_for_active_category()
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
        self._sync_shared_configs()
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
        self._start_device_alert_monitor()
        self._start_scheduled_reconcile()
        
        # EmberHawk manager + scheduler (reuse if provided)
        if self._emberhawk is not None:
            self.emberhawk = self._emberhawk
            print("Reusing existing EmberHawk manager")
        else:
            self.emberhawk = EmberHawkManager()
            self.emberhawk.set_dispatcher(self.dispatch_emberhawk_command)
            self.emberhawk.start_scheduler()
        
        # Connect TCP packet signal to handler (QueuedConnection ensures execution on GUI thread)
        self.tcp_packet_signal.connect(self.handle_tcp_packet, Qt.ConnectionType.QueuedConnection)
        
        # TCP Server initialization (reuse if provided, otherwise create new)
        if self.tcp_server is not None:
            print(f"Reusing existing TCP server on port {self.tcp_server_port}")
            self.update_tcp_status(True, f"TCP Server: Running on port {self.tcp_server_port} (reused)")
        else:
            tcp_mode = self.config.get('tcp_mode', 'async')  # async is the default; threaded is DEPRECATED
            binding_mode = self._get_tcp_binding_mode()
            try:
                if tcp_mode == 'async':
                    from embereye_base.core.tcp_async_server import TCPAsyncSensorServer
                    import asyncio, threading
                    # Create dedicated event loop thread if not already present
                    if self._async_loop is None:
                        self._async_loop = asyncio.new_event_loop()
                        def _run_loop(loop):
                            asyncio.set_event_loop(loop)
                            loop.run_forever()
                        self._async_thread = threading.Thread(target=_run_loop, args=(self._async_loop,), daemon=True)
                        self._async_thread.start()
                    self.tcp_server = TCPAsyncSensorServer(
                        port=self.tcp_server_port,
                        packet_callback=self._emit_tcp_packet,
                        binding_mode=binding_mode,
                    )
                    self.tcp_sensor_server = self.tcp_server  # Alias for pfds_manager commands
                    if self.tcp_server:
                        fut = asyncio.run_coroutine_threadsafe(self.tcp_server.start(), self._async_loop)
                        fut.result(timeout=5)
                else:
                    # DEPRECATED: threaded mode causes IP-keyed identity collisions for
                    # multi-device localhost setups (e.g. simulators). Set tcp_mode=async.
                    log_server_error(
                        "[DEPRECATED] tcp_mode='threaded' is retired. "
                        "Switch stream_config.json tcp_mode to 'async' to prevent device routing failures."
                    )
                    from embereye_base.core.tcp_sensor_server import TCPSensorServer
                    self.tcp_server = TCPSensorServer(port=self.tcp_server_port, packet_callback=self._emit_tcp_packet)
                    self.tcp_sensor_server = self.tcp_server  # Alias for pfds_manager commands
                    if self.tcp_server:
                        self.tcp_server.start()
                self.update_tcp_status(True, f"TCP Server: Running on port {self.tcp_server_port} ({tcp_mode}, {binding_mode})")
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                log_server_error(f"TCP server start failed: {e}\n{error_detail}")
                self.update_tcp_status(False, f"TCP Server: Failed to start - {e}")
        
        # Install X-ray effect event filter for global mouse tracking
        try:
            from PyQt6.QtWidgets import QApplication
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
            pkt_type = packet.get('type')

            if pkt_type in ('device_id', 'serialno'):
                self._register_device_identity_packet(packet)
                return

            fusion_args = {}
            loc_id = packet.get('loc_id')  # Extract loc_id from packet
            now_ts = time.time()

            if pkt_type in ('frame', 'sensor', 'eeprom') and not self._is_packet_authorized_and_linked(packet):
                return

            loc_id = packet.get('loc_id')
            
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
                if loc_id:
                    self._sensor_last_packet_ts_by_loc_id[str(loc_id)] = now_ts
                # Route to specific widget by loc_id, or broadcast to all
                target_widgets = [self.video_widgets.get(loc_id)] if loc_id and loc_id in self.video_widgets else self.get_video_widgets()
                matrix = packet.get('matrix')
                print(f"🔥 THERMAL FRAME: loc_id={loc_id}, widgets_available={len(self.video_widgets)}, target_widgets={len(target_widgets)}, matrix_shape={np.array(matrix).shape if matrix else None}")
                self._record_incident_thermal_frame(loc_id, matrix)
                for widget in target_widgets:
                    if widget and hasattr(widget, 'set_thermal_overlay'):
                        try:
                            widget.set_thermal_overlay(matrix)
                            print(f"  ✅ Thermal overlay set on widget")
                        except Exception as e:
                            print(f"Overlay error: {e}")
                # Feed the thermal matrix into fusion so thermal_max is populated
                # on the banner card. Without this, _run_fusion is only called by
                # sensor packets and thermal_max stays 0.0 permanently.
                if matrix is not None:
                    if loc_id:
                        self._last_thermal_matrix_by_loc_id[str(loc_id)] = matrix
                    self._last_thermal_matrix_by_loc_id['_broadcast'] = matrix
                    fusion_args['thermal_matrix'] = matrix
            elif packet.get('type') == 'sensor':
                if loc_id:
                    self._sensor_last_packet_ts_by_loc_id[str(loc_id)] = now_ts
                self._record_incident_sensor_packet(loc_id, packet)
                # Keep thermal context during sensor packets so banner thermal card
                # does not get overwritten with thermal_max=0.0 between frame packets.
                try:
                    widget_for_loc = self.video_widgets.get(loc_id) if loc_id else None
                    latest_matrix = getattr(widget_for_loc, '_last_thermal_matrix', None) if widget_for_loc else None
                    if latest_matrix is None and loc_id:
                        latest_matrix = self._last_thermal_matrix_by_loc_id.get(str(loc_id))
                    if latest_matrix is None:
                        latest_matrix = self._last_thermal_matrix_by_loc_id.get('_broadcast')
                    if latest_matrix is not None and 'thermal_matrix' not in fusion_args:
                        fusion_args['thermal_matrix'] = latest_matrix
                except Exception:
                    pass
                # Store raw sensor values
                adc1 = packet.get('ADC1')
                adc2 = packet.get('ADC2')
                mpy30 = packet.get('MPY30', packet.get('MPY_IN'))
                gas_ppm_raw = packet.get('GAS_PPM')
                
                # ADC1 = Flame Sensor (Analog) - 12-bit ADC (0-4095)
                if adc1 is not None:
                    try:
                        # Calculate flame percentage: (adc1 * 100) / 4095
                        flame_pct = (adc1 * 100.0) / 4095.0
                        fusion_args['adc1_raw'] = adc1
                        fusion_args['flame_analog_pct'] = flame_pct
                        print(f"Flame (ADC1): {adc1} -> {flame_pct:.1f}%")
                    except Exception as e:
                        print(f"Flame ADC1 calculation error: {e}")

                if gas_ppm_raw is not None:
                    try:
                        fusion_args['gas_ppm'] = float(gas_ppm_raw)
                    except Exception:
                        pass
                
                # ADC2 = Smoke Sensor (MQ-2/MQ-135) - 12-bit ADC (0-4095)
                if adc2 is not None:
                    try:
                        # Calculate smoke percentage: (adc2 * 100) / 4095
                        smoke_pct = (adc2 * 100.0) / 4095.0
                        fusion_args['adc2_raw'] = adc2
                        fusion_args['smoke_pct'] = smoke_pct
                        fusion_args['smoke_level'] = smoke_pct
                        # Keep GAS card fed from the same MQ channel when explicit gas ppm is unavailable.
                        if gas_ppm_raw is None:
                            fusion_args['gas_ppm'] = (adc2 * 1500.0) / 4095.0
                        print(f"Smoke (ADC2): {adc2} -> {smoke_pct:.1f}%")
                    except Exception as e:
                        print(f"Smoke ADC2 calculation error: {e}")
                
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
                fusion_result = self._run_fusion(**fusion_args)
                self._record_incident_fusion_event(loc_id, fusion_result, source='sensor_packet')
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
                        widget_loc_id = getattr(widget, 'loc_id', None) or loc_id
                        self._handle_alarm_transition(widget_loc_id, bool(fusion_result.get('alarm')), source='sensor_packet')
                        # Update fire alarm status
                        if hasattr(widget, 'update_fire_alarm'):
                            try:
                                effective_alarm = bool(self._alarm_state_by_loc_id.get(str(widget_loc_id), bool(fusion_result.get('alarm'))))
                                widget.update_fire_alarm(effective_alarm)
                                if hasattr(widget, 'set_alarm_acknowledged'):
                                    acked = bool(self._alarm_ack_by_loc_id.get(str(widget_loc_id), False))
                                    widget.set_alarm_acknowledged(acked)
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
                                widget_fusion = dict(fusion_result or {})
                                widget_thermal = float(widget_fusion.get('thermal_max', 0.0) or 0.0)
                                if widget_thermal <= 0.0:
                                    try:
                                        latest_matrix = getattr(widget, '_last_thermal_matrix', None)
                                        if latest_matrix is None and widget_loc_id:
                                            latest_matrix = self._last_thermal_matrix_by_loc_id.get(str(widget_loc_id))
                                        if latest_matrix is None:
                                            latest_matrix = self._last_thermal_matrix_by_loc_id.get('_broadcast')
                                        if latest_matrix is not None:
                                            arr = np.array(latest_matrix, dtype=float)
                                            if arr.size > 0:
                                                widget_thermal = float(np.max(arr))
                                    except Exception:
                                        pass
                                if widget_thermal <= 0.0:
                                    try:
                                        widget_thermal = float(getattr(widget, 'current_temp', 0.0) or 0.0)
                                    except Exception:
                                        pass
                                if widget_thermal > 0.0:
                                    widget_fusion['thermal_max'] = widget_thermal

                                widget.set_fusion_data(widget_fusion)
                            except Exception as e:
                                print(f"Fusion data update error: {e}")
                        self._record_incident_widget_snapshot(widget_loc_id, widget)
            
            # Forward other packets to sensor handler
            self.handle_sensor_data(packet)

    def initUI(self):
        try:
            # Suppress Qt warnings during UI initialization
            import warnings
            import os
            os.environ['QT_LOGGING_RULES'] = '*=false'
            warnings.filterwarnings('ignore')
            
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            # Force modern layout to match expected UI (compact header with gear/profile)
            is_modern = True
            
            self.setWindowTitle("Ember Eye Command Center" if is_modern else "Main")
            # Adapt initial size to current screen resolution
            try:
                from PyQt6.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
                avail = screen.availableGeometry()
                self.setGeometry(avail)
            except Exception:
                self.setGeometry(100, 100, 1024, 768)
            if is_modern:
                self.showMaximized()
            # React to resolution changes (monitor switch or scaling changes)
            try:
                from PyQt6.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
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
                            stop:0 rgba(24, 30, 36, 226), stop:0.5 rgba(34, 40, 48, 226), stop:1 rgba(24, 30, 36, 226));
                        border-bottom: 1px solid rgba(210, 216, 224, 0.30);
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
                        color: #FFDC00;
                        letter-spacing: 2px;
                        background: transparent;
                    """)
                    lc.addWidget(brand)
                    header_layout.addWidget(logo_container)
                
                # Group dropdown (without label)
                self.group_combo = QComboBox()
                self.group_combo.addItems(self.config["groups"])
                for i in range(self.group_combo.count()):
                    self.group_combo.setItemIcon(i, self._make_tactical_combo_icon("sensor"))
                # Guard: connect to fallback if handler missing
                handler = getattr(self, 'group_changed', None)
                self.group_combo.currentTextChanged.connect(handler or self._fallback_group_changed)
                self.group_combo.setFixedWidth(140)
                self.group_combo.setStyleSheet("""
                    QComboBox {
                        background-color: rgba(0, 0, 0, 0);
                        color: #d2d8e0;
                        border: 1px solid #d2d8e0;
                        border-radius: 4px;
                        padding: 5px 10px;
                        font-weight: 600;
                        font-size: 12px;
                        font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
                    }
                    QComboBox:hover {
                        border-color: #ffdc00;
                        color: #ffdc00;
                    }
                    QComboBox::drop-down {
                        border: none;
                        width: 18px;
                    }
                    QComboBox::down-arrow {
                        image: none;
                    }
                """)
                header_layout.addWidget(self.group_combo)
                
                # Grid size dropdown (without label)
                self.grid_size = QComboBox()
                self.grid_size.addItems(["2×2", "3×3", "4×4", "5×5"])
                for i in range(self.grid_size.count()):
                    self.grid_size.setItemIcon(i, self._make_tactical_combo_icon("grid"))
                self.grid_size.currentIndexChanged.connect(self.update_rtsp_grid)
                self.grid_size.setFixedWidth(90)
                self.grid_size.setStyleSheet("""
                    QComboBox {
                        background-color: rgba(0, 0, 0, 0);
                        color: #d2d8e0;
                        border: 1px solid #d2d8e0;
                        border-radius: 4px;
                        padding: 5px 10px;
                        font-weight: 600;
                        font-size: 12px;
                        font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
                    }
                    QComboBox:hover {
                        border-color: #ffdc00;
                        color: #ffdc00;
                    }
                    QComboBox::drop-down {
                        border: none;
                        width: 18px;
                    }
                    QComboBox::down-arrow {
                        image: none;
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
                    background: #0f1820;
                }
                QTabBar {
                    background: #0f1820;
                    alignment: center;
                }
                QTabBar::tab {
                    background: #15232f;
                    color: #8fa7b6;
                    padding: 11px 34px;
                    margin: 0px 4px;
                    border: none;
                    border-top: 2px solid transparent;
                    border-bottom: 1px solid #223848;
                    font-weight: 600;
                    font-size: 12px;
                    letter-spacing: 1px;
                    min-width: 132px;
                    font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
                }
                QTabBar::tab:selected {
                    background: #1d3140;
                    color: #7fd6e6;
                    border-top-color: #3dc0d7;
                    border-bottom-color: #3dc0d7;
                }
                QTabBar::tab:hover:!selected {
                    background: #1b2d3b;
                    color: #c2d4de;
                }
            """)
            # Set tab bar to not expand and center align
            from PyQt6.QtCore import Qt
            tab_bar = self.tabs.tabBar()
            tab_bar.setExpanding(False)
            tab_bar.setDrawBase(False)
            # Re-activate the main window when the tab changes.  On macOS in
            # maximised mode Qt sometimes loses window-level activation during
            # tab switches; calling activateWindow() after a short delay
            # restores normal focus so the user doesn't have to click the Dock.
            self.tabs.currentChanged.connect(self._on_tab_changed)
            
            main_layout.addWidget(self.tabs)
            
            self.init_rtsp_tab()
            # Conditionally initialize Grafana metrics tab if enabled in config
            if self.config.get('enable_grafana', False):
                self.init_grafana_tab()
            # Always initialize Incidents tab
            self.init_incidents_tab()
            self.init_marketplace_tab()
            self.init_live_pfds_tab()
            # Training Manager removed - Studio-only feature
            # Field Edition focuses on monitoring and detection
            # Failed Devices tab retired; Live PFDS tab is the supported device view.
            
            # Modern status bar
            if is_modern:
                status_bar = self.statusBar()
                status_bar.setStyleSheet("""
                    QStatusBar {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(24, 30, 36, 230), stop:0.5 rgba(36, 42, 50, 230), stop:1 rgba(24, 30, 36, 230));
                        color: #D2D8E0;
                        border-top: 1px solid rgba(255, 220, 0, 0.40);
                        font-weight: 600;
                        font-size: 10px;
                        font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
                    }
                    QStatusBar::item {
                        border: none;
                        margin: 0px;
                        padding: 0px;
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
            self._apply_responsive_dashboard_scaling()
            self._animate_dashboard_entry()
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Initialization failed: {str(e)}")

    def init_incidents_tab(self):
        """Create a tactical Incidents tab for post-mission analysis."""
        from PyQt6.QtCore import QSize
        incidents_tab = QWidget()
        layout = QVBoxLayout(incidents_tab)

        # Header strip: breadcrumbs + global actions + filters/search.
        header_frame = QFrame()
        header_frame.setObjectName("IncidentHeader")
        header_frame.setStyleSheet("""
            QFrame#IncidentHeader {
                background-color: #151b22;
                border: 1px solid #4c5560;
                border-radius: 4px;
            }
            QLabel#IncidentBreadcrumb { color: #ffd24a; font-weight: 700; font-size: 13px; }
            QLabel#IncidentCount { color: #dce3ea; font-size: 12px; }
            QPushButton#PrimaryYellow {
                background-color: #ffd200;
                color: #1d2128;
                border: 1px solid #d8b100;
                border-radius: 8px;
                font-weight: 700;
                padding: 6px 12px;
            }
            QPushButton#PrimaryYellow:hover { background-color: #ffe061; }
            QPushButton#GhostButton {
                background-color: #38414d;
                color: #dce3ea;
                border: 1px solid #566170;
                border-radius: 8px;
                font-weight: 600;
                padding: 6px 10px;
            }
            QPushButton#GhostButton:hover { background-color: #435062; }
            QComboBox, QLineEdit {
                background-color: #1f252d;
                color: #dce3ea;
                border: 1px solid #596474;
                border-radius: 7px;
                padding: 5px 8px;
                min-height: 26px;
            }
            QCheckBox { color: #dce3ea; font-weight: 600; }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)

        self.incident_breadcrumb = QLabel("INCIDENTS > ARCHIVE")
        self.incident_breadcrumb.setObjectName("IncidentBreadcrumb")
        header_layout.addWidget(self.incident_breadcrumb)

        self.incident_count_label = QLabel("Showing 0 incidents")
        self.incident_count_label.setObjectName("IncidentCount")
        header_layout.addWidget(self.incident_count_label)
        header_layout.addStretch()

        self.incident_filter_severity = QComboBox()
        self.incident_filter_severity.addItems(["All Severity", "HIGH", "MEDIUM", "LOW"])
        self.incident_filter_severity.currentIndexChanged.connect(self._refresh_incident_cards)
        header_layout.addWidget(self.incident_filter_severity)

        self.incident_filter_sensor = QComboBox()
        self.incident_filter_sensor.addItems(["All Sensors", "thermal", "smoke", "gas", "flame", "vision"])
        self.incident_filter_sensor.currentIndexChanged.connect(self._refresh_incident_cards)
        header_layout.addWidget(self.incident_filter_sensor)

        self.incident_filter_feedback = QComboBox()
        self.incident_filter_feedback.addItems(["All Status", "pending", "valid_alarm", "false_positive", "nuisance"])
        self.incident_filter_feedback.currentIndexChanged.connect(self._refresh_incident_cards)
        header_layout.addWidget(self.incident_filter_feedback)

        self.incident_search = QLineEdit()
        self.incident_search.setPlaceholderText("Search ID / Location")
        self.incident_search.textChanged.connect(self._refresh_incident_cards)
        header_layout.addWidget(self.incident_search)

        self.incident_night_mode_toggle = QCheckBox("Vessel Mode")
        self.incident_night_mode_toggle.toggled.connect(self._toggle_incident_night_mode)
        header_layout.addWidget(self.incident_night_mode_toggle)

        export_all_btn = QPushButton("EXPORT ALL TO USB")
        export_all_btn.setObjectName("PrimaryYellow")
        export_all_btn.clicked.connect(self.export_incidents_bundle)
        header_layout.addWidget(export_all_btn)

        sync_usb_btn = QPushButton("Sync To USB")
        sync_usb_btn.setObjectName("GhostButton")
        sync_usb_btn.clicked.connect(self.export_incidents_bundle)
        header_layout.addWidget(sync_usb_btn)

        mission_btn = QPushButton("Mission Summary Report")
        mission_btn.setObjectName("GhostButton")
        mission_btn.clicked.connect(self._show_incident_mission_summary)
        header_layout.addWidget(mission_btn)

        clear_btn = QPushButton("CLEAR ALL")
        clear_btn.setObjectName("GhostButton")
        header_layout.addWidget(clear_btn)
        layout.addWidget(header_frame)

        # Tactical card body (3-column responsive grid in scroll area).
        self.incident_cards_scroll = QScrollArea()
        self.incident_cards_scroll.setWidgetResizable(True)
        self.incident_cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cards_host = QWidget()
        self.incident_cards_grid = QGridLayout(cards_host)
        self.incident_cards_grid.setContentsMargins(8, 8, 8, 8)
        self.incident_cards_grid.setHorizontalSpacing(18)
        self.incident_cards_grid.setVerticalSpacing(18)
        self.incident_cards_scroll.setWidget(cards_host)
        layout.addWidget(self.incident_cards_scroll, 1)

        # Footer pagination and storage strip.
        footer_frame = QFrame()
        footer_frame.setObjectName("IncidentFooter")
        footer_frame.setStyleSheet("""
            QFrame#IncidentFooter {
                background-color: #151b22;
                border: 1px solid #4c5560;
                border-radius: 4px;
            }
            QLabel { color: #cdd5dd; font-size: 12px; }
            QPushButton {
                background-color: #3a444f;
                color: #f0f2f5;
                border: 1px solid #5f6c7b;
                border-radius: 8px;
                font-weight: 700;
                padding: 8px 16px;
                min-width: 88px;
            }
            QPushButton:hover { background-color: #495868; }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(12, 8, 12, 8)

        self.incident_footer_range = QLabel("Showing 0-0 of 0 incidents")
        footer_layout.addWidget(self.incident_footer_range)
        footer_layout.addStretch()

        self.incident_prev_btn = QPushButton("PREV")
        self.incident_prev_btn.clicked.connect(lambda: self._change_incident_cards_page(-1))
        footer_layout.addWidget(self.incident_prev_btn)

        self.incident_next_btn = QPushButton("NEXT")
        self.incident_next_btn.clicked.connect(lambda: self._change_incident_cards_page(1))
        footer_layout.addWidget(self.incident_next_btn)

        footer_layout.addStretch()
        self.incident_storage_label = QLabel("Storage Capacity: 0% Used")
        footer_layout.addWidget(self.incident_storage_label)
        layout.addWidget(footer_frame)

        # Hidden legacy widgets kept for compatibility with existing capture/export logic.
        self.incident_table = QTableWidget(0, 9)
        self.incident_table.setVisible(False)
        self.incident_list = QListWidget()
        self.incident_list.setVisible(False)
        self.incident_list.setViewMode(QListView.ViewMode.IconMode)
        self.incident_list.setIconSize(QSize(160, 120))
        self.incident_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # Legacy capture toggle remains functional but no longer shown in tactical UI.
        self.incident_capture_btn = QPushButton("⏸ Pause Capture")
        self.incident_capture_btn.setCheckable(True)
        self.incident_capture_enabled = True

        def toggle_capture():
            self.incident_capture_enabled = not self.incident_capture_btn.isChecked()
            self.incident_capture_btn.setText("▶ Resume Capture" if self.incident_capture_btn.isChecked() else "⏸ Pause Capture")
            print(f"Incident capture {'enabled' if self.incident_capture_enabled else 'disabled'}")

        self.incident_capture_btn.clicked.connect(toggle_capture)

        # Tactical pagination state.
        self._incident_cards_page = 1
        self._incident_cards_page_size = 12

        # Storage for full images and metadata
        self._incidents_store = []  # list of dicts {pixmap, loc_id, score, ts}
        self._incident_rows_by_token = {}
        if not hasattr(self, '_incident_max_items'):
            self._incident_max_items = 200

        def on_clear():
            for _k, _session in list(getattr(self, '_active_incident_sessions', {}).items()):
                try:
                    self._close_incident_video_writer(_session)
                except Exception:
                    pass
            self._incidents_store.clear()
            self.incident_list.clear()
            self.incident_table.setRowCount(0)
            self._incident_rows_by_token.clear()
            self._active_incident_sessions.clear()
            self._update_incident_count()
            self._refresh_incident_cards()
        clear_btn.clicked.connect(on_clear)

        # Determine tab label based on theme
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
        self.tabs.addTab(incidents_tab, "INCIDENTS" if is_modern else "Incidents")
        self._refresh_incident_cards()

    def init_training_manager_tab(self):
        """DISABLED: Training Manager tab is not available in Field Edition.
        
        Training functionality is reserved for EmberEye Studio.
        Field Edition focuses on monitoring and detection only.
        """
        # This method is intentionally disabled - training is a Studio-only feature
        pass

    def _create_sandbox_tab(self) -> QWidget:
        """Create sandbox testing UI for model evaluation."""
        from PyQt6.QtWidgets import QScrollArea
        
        # Main container with scroll area
        sandbox_widget = QWidget()
        main_layout = QVBoxLayout(sandbox_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scrollable content area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        sandbox_layout = QVBoxLayout(scroll_content)
        sandbox_layout.setSpacing(5)
        
        # Compact header
        header = QLabel("🧪 Sandbox - Test models safely")
        header.setStyleSheet("font-weight: bold; padding: 5px; color: #e7c75f;")
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
        self.sandbox_model_info.setStyleSheet("font-size: 10px; color: rgba(200,175,90,0.65);")
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
        self.sandbox_input_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sandbox_input_label.setStyleSheet("border: 1px dashed #75602a; background: #141d2a; color: #c9a95a;")
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
        self.sandbox_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sandbox_results_label.setStyleSheet("border: 1px solid #333; background: #111;")
        self.sandbox_results_label.setScaledContents(False)
        self.sandbox_results_label.setFixedHeight(380)
        self.sandbox_results_label.setMinimumWidth(420)
        self.sandbox_results_label.setMaximumWidth(500)
        results_inner.addWidget(self.sandbox_results_label)

        # Overlay stats on top-left of result frame (transparent, compact)
        self.sandbox_stats_overlay = QLabel("Waiting for inference...", self.sandbox_results_label)
        self.sandbox_stats_overlay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.sandbox_stats_overlay.setWordWrap(True)
        self.sandbox_stats_overlay.setFixedWidth(210)
        self.sandbox_stats_overlay.setMinimumHeight(150)
        self.sandbox_stats_overlay.move(10, 10)
        self.sandbox_stats_overlay.setStyleSheet(
            "background: rgba(0, 0, 0, 0.65); color: #f1f1f1; padding: 8px;"
            "font-family: monospace; font-size: 10px; border-radius: 5px;"
        )
        self.sandbox_stats_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.sandbox_stats_overlay.raise_()
        
        results_layout.addLayout(results_inner)
        results_group.setLayout(results_layout)
        previews_row.addWidget(results_group)

        previews_column.addLayout(previews_row)

        # Stats and detections below previews (more compact)
        self.sandbox_stats_label = QLabel("Detections: - | Time: -")
        self.sandbox_stats_label.setStyleSheet("font-size: 10px; font-family: monospace; padding: 2px 0; color: #c9a95a;")
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
            from embereye_base.core.model_versioning import ModelVersionManager
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
            
            from embereye_base.core.model_versioning import ModelVersionManager
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
                        scaled = pixmap.scaled(520, 350, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
            from embereye_base.core.model_versioning import ModelVersionManager
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
            from embereye_base.core.model_versioning import ModelVersionManager
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
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            QApplication.processEvents()
            
            # Create metadata with class versioning (matches Studio format)
            from embereye_base.core.class_config import get_leaf_classes, get_classes_hash, load_master_classes
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
            from embereye_base.core.model_versioning import ModelVersionManager, ModelMetadata
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
        from PyQt6.QtWidgets import QInputDialog
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
                scaled = pixmap.scaled(520, 350, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
        from PyQt6.QtCore import QThread, pyqtSignal
        
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
                    from embereye_base.core.model_versioning import ModelVersionManager
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
                scaled = pixmap.scaled(520, 350, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
            q_img = QImage(annotated_img.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img.rgbSwapped())
            
            # Scale to fit enlarged result frame
            scaled = pixmap.scaled(520, 380, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
                    from embereye_base.utils.metrics import log_performance_metric
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
                    from embereye_base.utils.metrics import log_performance_metric
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
                self.incident_count_label.setText(f"Showing {len(self._incidents_store)} incidents")
        except Exception:
            pass

    def _show_incident_mission_summary(self):
        sessions = self._collect_incident_sessions()
        total = len(sessions)
        pending = sum(1 for s in sessions if str(s.get('feedback', 'pending')) == 'pending')
        valid = sum(1 for s in sessions if str(s.get('feedback', '')) == 'valid_alarm')
        nuisance = sum(1 for s in sessions if str(s.get('feedback', '')) == 'nuisance')
        false_pos = sum(1 for s in sessions if str(s.get('feedback', '')) == 'false_positive')
        msg = (
            f"Mission Incident Summary\n\n"
            f"Total Sessions: {total}\n"
            f"Pending Review: {pending}\n"
            f"Valid Alarm: {valid}\n"
            f"Nuisance: {nuisance}\n"
            f"False Alarm: {false_pos}"
        )
        QMessageBox.information(self, "Mission Summary Report", msg)

    def _toggle_incident_night_mode(self, enabled):
        try:
            active = bool(enabled)
            if hasattr(self, 'incident_cards_scroll'):
                self.incident_cards_scroll.setStyleSheet(
                    "QScrollArea { background-color: #140b0b; border: none; }" if active else
                    "QScrollArea { background-color: #1d2229; border: none; }"
                )
            self._refresh_incident_cards()
        except Exception:
            pass

    def _change_incident_cards_page(self, delta):
        page = int(getattr(self, '_incident_cards_page', 1) or 1)
        sessions = self._filter_incident_sessions(self._collect_incident_sessions())
        page_size = int(getattr(self, '_incident_cards_page_size', 12) or 12)
        max_page = max(1, int((len(sessions) + page_size - 1) / page_size))
        self._incident_cards_page = max(1, min(max_page, page + int(delta)))
        self._refresh_incident_cards()

    def _collect_incident_sessions(self):
        rows = getattr(self, '_incident_rows_by_token', {}) or {}
        sessions = []
        seen = set()
        for token, info in rows.items():
            session = (info or {}).get('session') if isinstance(info, dict) else None
            if not isinstance(session, dict):
                continue
            tok = str(session.get('token') or token or '').strip()
            if not tok or tok in seen:
                continue
            seen.add(tok)
            sessions.append(session)
        active = getattr(self, '_active_incident_sessions', {}) or {}
        for _k, session in active.items():
            if not isinstance(session, dict):
                continue
            tok = str(session.get('token') or '').strip()
            if not tok or tok in seen:
                continue
            seen.add(tok)
            sessions.append(session)
        sessions.sort(key=lambda s: float(s.get('start_ts', 0.0) or 0.0), reverse=True)
        return sessions

    def _infer_session_severity(self, session):
        reason = str((session or {}).get('reason', '')).lower()
        if any(x in reason for x in ('critical', 'high', 'flame', 'smoke')):
            return 'HIGH'
        if any(x in reason for x in ('thermal', 'gas', 'vision')):
            return 'MEDIUM'
        return 'LOW'

    def _infer_session_sensor_type(self, session):
        reason = str((session or {}).get('reason', '')).lower()
        for name in ('thermal', 'smoke', 'gas', 'flame', 'vision'):
            if name in reason:
                return name
        return 'vision'

    def _filter_incident_sessions(self, sessions):
        severity_filter = str(getattr(self, 'incident_filter_severity', QComboBox()).currentText() if hasattr(self, 'incident_filter_severity') else 'All Severity')
        sensor_filter = str(getattr(self, 'incident_filter_sensor', QComboBox()).currentText() if hasattr(self, 'incident_filter_sensor') else 'All Sensors')
        feedback_filter = str(getattr(self, 'incident_filter_feedback', QComboBox()).currentText() if hasattr(self, 'incident_filter_feedback') else 'All Status')
        search_value = str(getattr(self, 'incident_search', QLineEdit()).text() if hasattr(self, 'incident_search') else '').strip().lower()

        result = []
        for session in sessions:
            severity = self._infer_session_severity(session)
            sensor_type = self._infer_session_sensor_type(session)
            feedback = str(session.get('feedback', 'pending'))
            token = str(session.get('token', ''))
            loc_id = str(session.get('loc_id', ''))

            if severity_filter != 'All Severity' and severity != severity_filter:
                continue
            if sensor_filter != 'All Sensors' and sensor_type != sensor_filter:
                continue
            if feedback_filter != 'All Status' and feedback != feedback_filter:
                continue
            if search_value and search_value not in token.lower() and search_value not in loc_id.lower():
                continue
            result.append(session)
        return result

    def _clear_incident_cards_grid(self):
        if not hasattr(self, 'incident_cards_grid'):
            return
        while self.incident_cards_grid.count():
            item = self.incident_cards_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _sparkline_from_values(self, values, width=180, height=38):
        pix = QPixmap(max(1, int(width)), max(1, int(height)))
        pix.fill(Qt.GlobalColor.transparent)
        if not values:
            return pix
        try:
            v = [float(x) for x in values]
            mn, mx = min(v), max(v)
            span = (mx - mn) if mx != mn else 1.0
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor('#ffd200'), 2))
            count = len(v)
            prev_x = 0
            prev_y = int(height - ((v[0] - mn) / span) * (height - 4))
            for i in range(1, count):
                x = int((i / max(1, count - 1)) * (width - 1))
                y = int(height - ((v[i] - mn) / span) * (height - 4))
                painter.drawLine(prev_x, prev_y, x, y)
                prev_x, prev_y = x, y
            painter.end()
        except Exception:
            pass
        return pix

    def _load_session_preview_pixmaps(self, session):
        rgb = None
        therm = None
        try:
            thumb_path = str((session or {}).get('thumbnail_path', '') or '')
            if thumb_path and os.path.exists(thumb_path):
                rgb = QPixmap(thumb_path)
            if (rgb is None or rgb.isNull()) and isinstance(session, dict):
                vdir = os.path.join(str(session.get('dir', '')), 'video')
                if os.path.isdir(vdir):
                    files = sorted([f for f in os.listdir(vdir) if f.lower().endswith('.jpg')])
                    if files:
                        rgb = QPixmap(os.path.join(vdir, files[-1]))
            tdir = os.path.join(str((session or {}).get('dir', '')), 'thermal')
            if os.path.isdir(tdir):
                files = sorted([f for f in os.listdir(tdir) if f.lower().endswith('.png')])
                if files:
                    therm = QPixmap(os.path.join(tdir, files[-1]))
        except Exception:
            pass
        return rgb, therm

    def _extract_sensor_series(self, session):
        gas, smoke, thermal = [], [], []
        try:
            s_path = str((session or {}).get('sensor_log_path', '') or '')
            if s_path and os.path.exists(s_path):
                with open(s_path, 'r', encoding='utf-8') as fp:
                    for line in fp.readlines()[-32:]:
                        obj = json.loads(line)
                        pkt = obj.get('packet', {}) if isinstance(obj, dict) else {}
                        gas.append(float(pkt.get('GAS_PPM', pkt.get('ADC2', 0)) or 0))
                        smoke.append(float(pkt.get('ADC2', 0) or 0))
            t_path = str((session or {}).get('thermal_log_path', '') or '')
            if t_path and os.path.exists(t_path):
                with open(t_path, 'r', encoding='utf-8') as fp:
                    for line in fp.readlines()[-32:]:
                        obj = json.loads(line)
                        thermal.append(float(obj.get('max_temp', 0) or 0))
        except Exception:
            pass
        return gas, smoke, thermal

    def _set_incident_feedback_and_refresh(self, token, feedback):
        self._set_incident_feedback(token, feedback)
        self._refresh_incident_cards()

    def _open_incident_dual_view(self, session):
        try:
            session_dir = str((session or {}).get('dir', '') or '')
            vdir = os.path.join(session_dir, 'video')
            tdir = os.path.join(session_dir, 'thermal')
            video_files = sorted([f for f in os.listdir(vdir) if f.lower().endswith('.jpg')]) if os.path.isdir(vdir) else []
            thermal_files = sorted([f for f in os.listdir(tdir) if f.lower().endswith('.png')]) if os.path.isdir(tdir) else []
            if not video_files and not thermal_files:
                QMessageBox.information(self, 'Playback', 'No incident media available for playback.')
                return

            dlg = QDialog(self)
            dlg.setWindowTitle(f"Dual View Playback • {session.get('loc_id', '')}")
            dlg.resize(980, 620)
            root = QVBoxLayout(dlg)

            views = QHBoxLayout()
            rgb_lbl = QLabel('RGB')
            rgb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rgb_lbl.setMinimumSize(440, 300)
            rgb_lbl.setStyleSheet('background:#11161d; border:1px solid #4a5460;')
            therm_lbl = QLabel('THERMAL')
            therm_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            therm_lbl.setMinimumSize(440, 300)
            therm_lbl.setStyleSheet('background:#11161d; border:1px solid #4a5460;')
            views.addWidget(rgb_lbl)
            views.addWidget(therm_lbl)
            root.addLayout(views)

            max_frames = max(len(video_files), len(thermal_files), 1)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, max_frames - 1)
            root.addWidget(slider)

            controls = QHBoxLayout()
            play_btn = QPushButton('▶ Play')
            pause_btn = QPushButton('⏸ Pause')
            close_btn = QPushButton('Close')
            controls.addWidget(play_btn)
            controls.addWidget(pause_btn)
            controls.addStretch()
            controls.addWidget(close_btn)
            root.addLayout(controls)

            timer = QTimer(dlg)
            timer.setInterval(140)

            def _frame_path(files, idx, folder):
                if not files:
                    return ''
                ridx = int((idx / max(1, max_frames - 1)) * (len(files) - 1))
                ridx = max(0, min(len(files) - 1, ridx))
                return os.path.join(folder, files[ridx])

            def _render(idx):
                p1 = _frame_path(video_files, idx, vdir)
                p2 = _frame_path(thermal_files, idx, tdir)
                if p1 and os.path.exists(p1):
                    px1 = QPixmap(p1)
                    if not px1.isNull():
                        rgb_lbl.setPixmap(px1.scaled(rgb_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                if p2 and os.path.exists(p2):
                    px2 = QPixmap(p2)
                    if not px2.isNull():
                        therm_lbl.setPixmap(px2.scaled(therm_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

            def _tick():
                cur = slider.value()
                if cur >= slider.maximum():
                    timer.stop()
                    return
                slider.setValue(cur + 1)

            slider.valueChanged.connect(_render)
            timer.timeout.connect(_tick)
            play_btn.clicked.connect(lambda: timer.start())
            pause_btn.clicked.connect(lambda: timer.stop())
            close_btn.clicked.connect(dlg.accept)
            _render(0)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, 'Playback Error', f'Unable to open dual-view playback:\n{e}')

    def _build_incident_card(self, session):
        token = str(session.get('token', ''))
        loc = str(session.get('loc_id', ''))
        start_ts = float(session.get('start_ts', time.time()) or time.time())
        end_ts = float(session.get('end_ts', time.time()) or time.time())
        duration = max(0.0, end_ts - start_ts)
        severity = self._infer_session_severity(session)
        feedback = str(session.get('feedback', 'pending'))
        is_verified = feedback != 'pending'
        is_night = bool(getattr(self, 'incident_night_mode_toggle', QCheckBox()).isChecked() if hasattr(self, 'incident_night_mode_toggle') else False)

        card = QFrame()
        card.setObjectName('IncidentCard')
        card.setProperty('status', 'verified' if is_verified else 'pending')
        card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        bg = '#291414' if is_night else '#131920'
        border_color = '#ffd200' if is_verified else '#5c6672'
        border_style = 'solid' if is_verified else 'dashed'
        card.setStyleSheet(
            f"QFrame#IncidentCard {{ background-color: {bg}; border: 2px {border_style} {border_color}; border-radius: 4px; }}"
            "QFrame#IncidentCard:hover { border-color: #ffdc00; }"
            "QLabel { color: #e3e8ee; border: none; }"
            "QPushButton { background-color: #394451; color: #f0f2f6; border: 1px solid #5f6b79; border-radius: 6px; padding: 4px 8px; font-weight: 600; }"
            "QPushButton:hover { background-color: #495868; }"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        header = QHBoxLayout()
        sev_dot = QLabel('●')
        sev_dot.setStyleSheet('color:#ffd200; font-size:13px; border:none;')
        header.addWidget(sev_dot)
        header.addWidget(QLabel(f"{token[-16:]}  |  {datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M:%S')}"))
        header.addStretch()
        header.addWidget(QLabel(f"{severity}"))
        v.addLayout(header)

        timing = QHBoxLayout()
        timing.addWidget(QLabel(f"Start: {datetime.fromtimestamp(start_ts).strftime('%H:%M:%S')}"))
        timing.addStretch()
        timing.addWidget(QLabel(f"Duration: {duration:.1f}s"))
        v.addLayout(timing)

        rgb, therm = self._load_session_preview_pixmaps(session)
        media = QHBoxLayout()
        rgb_lbl = QLabel('RGB')
        rgb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rgb_lbl.setMinimumSize(150, 92)
        rgb_lbl.setStyleSheet('background:#0f141a; border:1px solid #4f5b67;')
        therm_lbl = QLabel('THERMAL')
        therm_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        therm_lbl.setMinimumSize(150, 92)
        therm_lbl.setStyleSheet('background:#0f141a; border:1px solid #4f5b67;')
        if rgb and not rgb.isNull():
            rgb_lbl.setPixmap(rgb.scaled(150, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        if therm and not therm.isNull():
            therm_lbl.setPixmap(therm.scaled(150, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        media.addWidget(rgb_lbl)
        media.addWidget(therm_lbl)
        v.addLayout(media)

        gas, smoke, thermal = self._extract_sensor_series(session)
        spark_row = QHBoxLayout()
        for title, series in (("GAS", gas), ("SMOKE", smoke), ("THERM", thermal)):
            box = QVBoxLayout()
            lbl = QLabel(title)
            lbl.setStyleSheet('color:#ffd200; font-weight:700; border:none;')
            graph = QLabel()
            graph.setPixmap(self._sparkline_from_values(series or [0.0], 96, 32))
            graph.setStyleSheet('background:#151b23; border:1px solid #4f5b67;')
            box.addWidget(lbl)
            box.addWidget(graph)
            spark_row.addLayout(box)
        v.addLayout(spark_row)

        hub = QHBoxLayout()
        play_btn = QPushButton('▶')
        play_btn.setToolTip('Play incident playback')
        play_btn.clicked.connect(lambda _=False, s=session: self._open_incident_dual_view(s))
        expand_btn = QPushButton('⤢')
        expand_btn.setToolTip('Expand dual-view playback')
        expand_btn.clicked.connect(lambda _=False, s=session: self._open_incident_dual_view(s))
        hub.addWidget(play_btn)
        hub.addWidget(expand_btn)
        hub.addStretch()
        v.addLayout(hub)

        feedback_row = QHBoxLayout()
        valid_btn = QPushButton('VALID ALARM')
        valid_btn.setStyleSheet('border:1px solid #ffd200;')
        valid_btn.clicked.connect(lambda _=False, t=token: self._set_incident_feedback_and_refresh(t, 'valid_alarm'))
        false_btn = QPushButton('FALSE ALARM')
        false_btn.clicked.connect(lambda _=False, t=token: self._set_incident_feedback_and_refresh(t, 'false_positive'))
        nuisance_btn = QPushButton('NUISANCE')
        nuisance_btn.clicked.connect(lambda _=False, t=token: self._set_incident_feedback_and_refresh(t, 'nuisance'))
        feedback_row.addWidget(valid_btn)
        feedback_row.addWidget(false_btn)
        feedback_row.addWidget(nuisance_btn)
        v.addLayout(feedback_row)

        return card

    def _refresh_incident_cards(self):
        if not hasattr(self, 'incident_cards_grid'):
            return
        sessions = self._filter_incident_sessions(self._collect_incident_sessions())
        self._clear_incident_cards_grid()

        page_size = int(getattr(self, '_incident_cards_page_size', 12) or 12)
        total = len(sessions)
        max_page = max(1, int((total + page_size - 1) / page_size))
        page = int(getattr(self, '_incident_cards_page', 1) or 1)
        page = max(1, min(max_page, page))
        self._incident_cards_page = page

        start = (page - 1) * page_size
        end = min(total, start + page_size)
        page_items = sessions[start:end]

        for idx, session in enumerate(page_items):
            row = idx // 3
            col = idx % 3
            self.incident_cards_grid.addWidget(self._build_incident_card(session), row, col)

        if hasattr(self, 'incident_footer_range'):
            self.incident_footer_range.setText(f"Showing {start + 1 if total else 0}-{end} of {total} incidents")
        if hasattr(self, 'incident_prev_btn'):
            self.incident_prev_btn.setEnabled(page > 1)
        if hasattr(self, 'incident_next_btn'):
            self.incident_next_btn.setEnabled(page < max_page)
        self._update_incident_storage_usage_label()
        self._update_incident_count()

    def _update_incident_storage_usage_label(self):
        if not hasattr(self, 'incident_storage_label'):
            return
        try:
            incident_root = str(getattr(self, 'incident_save_dir', '') or os.path.join(os.path.dirname(__file__), 'incidents'))
            total_bytes = 0
            if os.path.isdir(incident_root):
                for root, _dirs, files in os.walk(incident_root):
                    for f in files:
                        path = os.path.join(root, f)
                        try:
                            total_bytes += int(os.path.getsize(path))
                        except Exception:
                            pass
            # Tactical estimate for local archive budget (10 GB).
            used_pct = min(100.0, (float(total_bytes) / float(10 * 1024 * 1024 * 1024)) * 100.0)
            self.incident_storage_label.setText(f"Storage Capacity: {used_pct:.1f}% (Used)")
        except Exception:
            self.incident_storage_label.setText("Storage Capacity: N/A")

    def _incident_token_for_loc(self, loc_id):
        key = self._normalize_loc_key(loc_id) or "unknown"
        safe = "".join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in key)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return f"{ts}_{safe}"

    def _start_incident_session(self, loc_id, reason="alarm"):
        key = self._normalize_loc_key(loc_id)
        if not key:
            return None
        existing = self._active_incident_sessions.get(key)
        if existing and not existing.get('acked'):
            return existing

        base_dir = getattr(self, 'incident_save_dir', '') or os.path.join(os.path.dirname(__file__), 'incidents')
        token = self._incident_token_for_loc(key)
        session_dir = os.path.join(base_dir, "sessions", token)
        os.makedirs(session_dir, exist_ok=True)

        session = {
            'token': token,
            'loc_id': key,
            'reason': str(reason or 'alarm'),
            'start_ts': time.time(),
            'end_ts': None,
            'end_reason': None,
            'acked': False,
            'feedback': 'pending',
            'dir': session_dir,
            'video_frames': 0,
            'thermal_frames': 0,
            'sensor_packets': 0,
            'fusion_events': 0,
            'vision_events': 0,
            'last_video_ts': 0.0,
            'last_thermal_ts': 0.0,
            'thumbnail_path': '',
            'video_recording_path': os.path.join(session_dir, 'incident_capture.mp4'),
            'video_recording_fps': float(getattr(self, '_incident_video_record_fps', 8.0) or 8.0),
            'video_recording_frames': 0,
            'video_writer': None,
            'video_writer_size': None,
            'video_writer_last_ts': 0.0,
            'manifest_path': os.path.join(session_dir, 'manifest.json'),
            'sensor_log_path': os.path.join(session_dir, 'sensor.jsonl'),
            'fusion_log_path': os.path.join(session_dir, 'fusion.jsonl'),
            'vision_log_path': os.path.join(session_dir, 'vision.jsonl'),
            'video_log_path': os.path.join(session_dir, 'video.jsonl'),
            'thermal_log_path': os.path.join(session_dir, 'thermal.jsonl'),
        }
        self._active_incident_sessions[key] = session
        self._write_incident_manifest(session)
        return session

    def _write_incident_manifest(self, session):
        try:
            payload = {
                'token': session.get('token'),
                'location_id': session.get('loc_id'),
                'reason': session.get('reason'),
                'start_ts': session.get('start_ts'),
                'end_ts': session.get('end_ts'),
                'end_reason': session.get('end_reason'),
                'acked': bool(session.get('acked')),
                'feedback': session.get('feedback', 'pending'),
                'counts': {
                    'video_frames': int(session.get('video_frames', 0)),
                    'thermal_frames': int(session.get('thermal_frames', 0)),
                    'sensor_packets': int(session.get('sensor_packets', 0)),
                    'fusion_events': int(session.get('fusion_events', 0)),
                    'vision_events': int(session.get('vision_events', 0)),
                    'video_recording_frames': int(session.get('video_recording_frames', 0)),
                },
                'thumbnail_path': session.get('thumbnail_path', ''),
                'video_recording_path': session.get('video_recording_path', ''),
                'video_recording_fps': float(session.get('video_recording_fps', 0.0) or 0.0),
            }
            with open(session.get('manifest_path'), 'w', encoding='utf-8') as fp:
                json.dump(payload, fp, indent=2)
        except Exception as e:
            print(f"Incident manifest write error: {e}")

    def _ensure_incident_video_writer(self, session, qimage):
        if not isinstance(session, dict) or qimage is None:
            return False
        writer = session.get('video_writer')
        if writer is not None:
            return True
        try:
            w = int(qimage.width())
            h = int(qimage.height())
            if w <= 0 or h <= 0:
                return False
            video_path = str(session.get('video_recording_path') or '').strip()
            if not video_path:
                return False
            os.makedirs(os.path.dirname(video_path), exist_ok=True)
            fps = max(1.0, float(session.get('video_recording_fps', 8.0) or 8.0))
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            vw = cv2.VideoWriter(video_path, fourcc, fps, (w, h))
            if not vw or (hasattr(vw, 'isOpened') and not vw.isOpened()):
                return False
            session['video_writer'] = vw
            session['video_writer_size'] = (w, h)
            session['video_writer_last_ts'] = 0.0
            return True
        except Exception as e:
            print(f"Incident video writer init error: {e}")
            return False

    def _close_incident_video_writer(self, session):
        if not isinstance(session, dict):
            return
        writer = session.get('video_writer')
        try:
            if writer is not None:
                writer.release()
        except Exception as e:
            print(f"Incident video writer close error: {e}")
        session['video_writer'] = None

    def _append_incident_jsonl(self, path, payload):
        try:
            row = dict(payload or {})
            row['ts'] = time.time()
            with open(path, 'a', encoding='utf-8') as fp:
                fp.write(json.dumps(row, ensure_ascii=True) + "\n")
        except Exception as e:
            print(f"Incident log append error: {e}")

    def _record_incident_sensor_packet(self, loc_id, packet):
        key = self._normalize_loc_key(loc_id)
        session = self._active_incident_sessions.get(key)
        if not session or session.get('acked'):
            return
        session['sensor_packets'] = int(session.get('sensor_packets', 0)) + 1
        self._append_incident_jsonl(session['sensor_log_path'], {'location_id': key, 'packet': packet})

    def _record_incident_fusion_event(self, loc_id, fusion_result, source='fusion'):
        key = self._normalize_loc_key(loc_id)
        session = self._active_incident_sessions.get(key)
        if not session or session.get('acked'):
            return
        session['fusion_events'] = int(session.get('fusion_events', 0)) + 1
        self._append_incident_jsonl(
            session['fusion_log_path'],
            {
                'location_id': key,
                'source': str(source),
                'alarm': bool((fusion_result or {}).get('alarm')),
                'confidence': float((fusion_result or {}).get('confidence', 0.0) or 0.0),
                'severity': (fusion_result or {}).get('severity'),
                'reason': (fusion_result or {}).get('alarm_reason'),
                'sources': (fusion_result or {}).get('sources', []),
            },
        )

    def _record_incident_vision_event(self, loc_id, score):
        key = self._normalize_loc_key(loc_id)
        session = self._active_incident_sessions.get(key)
        if not session or session.get('acked'):
            return
        session['vision_events'] = int(session.get('vision_events', 0)) + 1
        self._append_incident_jsonl(session['vision_log_path'], {'location_id': key, 'vision_score': float(score or 0.0)})

    def _record_incident_thermal_frame(self, loc_id, matrix):
        key = self._normalize_loc_key(loc_id)
        session = self._active_incident_sessions.get(key)
        if not session or session.get('acked'):
            return
        if matrix is None:
            return
        now = time.time()
        if now - float(session.get('last_thermal_ts', 0.0)) < float(self._incident_thermal_save_interval_s):
            return
        session['last_thermal_ts'] = now
        session['thermal_frames'] = int(session.get('thermal_frames', 0)) + 1
        try:
            arr = np.array(matrix, dtype=np.float32)
            if arr.size == 0 or arr.ndim < 2:
                return
            thermal_dir = os.path.join(session['dir'], 'thermal')
            os.makedirs(thermal_dir, exist_ok=True)
            idx = int(session['thermal_frames'])
            npy_path = os.path.join(thermal_dir, f"thermal_{idx:05d}.npy")
            png_path = os.path.join(thermal_dir, f"thermal_{idx:05d}.png")
            np.save(npy_path, arr)
            norm = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            color = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
            cv2.imwrite(png_path, color)
            self._append_incident_jsonl(session['thermal_log_path'], {
                'location_id': key,
                'index': idx,
                'npy_path': npy_path,
                'png_path': png_path,
                'shape': list(arr.shape),
                'max_temp': float(np.max(arr)),
            })
        except Exception as e:
            print(f"Incident thermal record error: {e}")

    def _record_incident_video_frame(self, loc_id, qimage, score=0.0, yolo_score=0.0, detections=None):
        key = self._normalize_loc_key(loc_id)
        session = self._active_incident_sessions.get(key)
        if not session or session.get('acked'):
            return
        now = time.time()
        # Write continuous MP4 frames while incident session is active.
        if self._ensure_incident_video_writer(session, qimage):
            try:
                fps = max(1.0, float(session.get('video_recording_fps', 8.0) or 8.0))
                min_interval = 1.0 / fps
                last_ts = float(session.get('video_writer_last_ts', 0.0) or 0.0)
                if (now - last_ts) >= min_interval:
                    img = qimage.convertToFormat(QImage.Format.Format_RGB888)
                    w = int(img.width())
                    h = int(img.height())
                    frame_w, frame_h = session.get('video_writer_size') or (w, h)
                    ptr = img.bits()
                    ptr.setsize(img.sizeInBytes())
                    bpl = int(img.bytesPerLine())
                    row = np.frombuffer(ptr, np.uint8).reshape((h, bpl))
                    rgb = row[:, : (w * 3)].reshape((h, w, 3))
                    frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                    if (w, h) != (frame_w, frame_h):
                        frame = cv2.resize(frame, (int(frame_w), int(frame_h)), interpolation=cv2.INTER_LINEAR)
                    session['video_writer'].write(frame)
                    session['video_recording_frames'] = int(session.get('video_recording_frames', 0)) + 1
                    session['video_writer_last_ts'] = now
            except Exception as e:
                print(f"Incident video writer frame error: {e}")

        if now - float(session.get('last_video_ts', 0.0)) < float(self._incident_video_save_interval_s):
            return
        session['last_video_ts'] = now
        session['video_frames'] = int(session.get('video_frames', 0)) + 1
        try:
            video_dir = os.path.join(session['dir'], 'video')
            os.makedirs(video_dir, exist_ok=True)
            idx = int(session['video_frames'])
            jpg_path = os.path.join(video_dir, f"video_{idx:05d}.jpg")
            pix = QPixmap.fromImage(qimage)
            pix.save(jpg_path, 'JPG', quality=90)
            if not session.get('thumbnail_path'):
                session['thumbnail_path'] = jpg_path
            self._append_incident_jsonl(session['video_log_path'], {
                'location_id': key,
                'index': idx,
                'path': jpg_path,
                'score': float(score or 0.0),
                'yolo_score': float(yolo_score or 0.0),
                'detections': detections or [],
            })
        except Exception as e:
            print(f"Incident video record error: {e}")

    def _record_incident_widget_snapshot(self, loc_id, widget):
        try:
            if not widget or not hasattr(widget, 'video_label'):
                return
            pix = widget.video_label.pixmap()
            if not pix or pix.isNull():
                return
            self._record_incident_video_frame(loc_id, pix.toImage(), 0.0, 0.0, [])
        except Exception as e:
            print(f"Incident widget snapshot error: {e}")

    def _tick_active_incident_recording(self):
        """Continuously sample active incident tiles into session recording."""
        try:
            sessions = dict(getattr(self, '_active_incident_sessions', {}) or {})
            if not sessions:
                return
            widgets = getattr(self, 'video_widgets', {}) or {}
            for key, session in sessions.items():
                if not isinstance(session, dict) or session.get('acked'):
                    continue
                widget = widgets.get(key)
                if not widget:
                    continue
                self._record_incident_widget_snapshot(key, widget)
        except Exception as e:
            print(f"Incident record tick error: {e}")

    def _set_incident_feedback(self, token, feedback):
        token_key = str(token or '').strip()
        if not token_key:
            return
        feedback_value = str(feedback or 'pending').strip() or 'pending'
        row_info = self._incident_rows_by_token.get(token_key, {})
        session = row_info.get('session')
        if isinstance(session, dict):
            session['feedback'] = feedback_value
            self._write_incident_manifest(session)
        self._refresh_incident_cards()

    def _append_incident_session_row(self, session):
        if not hasattr(self, 'incident_table') or not isinstance(session, dict):
            return
        token = str(session.get('token') or '').strip()
        if not token:
            return
        row = self.incident_table.rowCount()
        self.incident_table.insertRow(row)
        start_ts = float(session.get('start_ts', time.time()) or time.time())
        end_ts = float(session.get('end_ts', time.time()) or time.time())
        dur = max(0.0, end_ts - start_ts)
        vals = [
            datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M:%S'),
            str(session.get('loc_id', '')),
            f"{dur:.1f}",
            str(int(session.get('video_frames', 0))),
            str(int(session.get('thermal_frames', 0))),
            str(int(session.get('sensor_packets', 0))),
            str(int(session.get('fusion_events', 0))),
            str(int(session.get('vision_events', 0))),
        ]
        for idx, value in enumerate(vals):
            self.incident_table.setItem(row, idx, QTableWidgetItem(value))

        feedback_combo = QComboBox()
        feedback_combo.addItems(['pending', 'valid_alarm', 'nuisance', 'false_positive'])
        feedback_combo.setCurrentText(str(session.get('feedback', 'pending')))
        feedback_combo.currentTextChanged.connect(lambda text, t=token: self._set_incident_feedback(t, text))
        self.incident_table.setCellWidget(row, 8, feedback_combo)
        self._incident_rows_by_token[token] = {'row': row, 'session': session}
        self._refresh_incident_cards()

    def _finalize_incident_session(self, loc_id, feedback='pending', acked=True, end_reason='operator_ack'):
        key = self._normalize_loc_key(loc_id)
        if not key:
            return
        session = self._active_incident_sessions.pop(key, None)
        if not session:
            return
        self._close_incident_video_writer(session)
        session['acked'] = bool(acked)
        session['feedback'] = str(feedback or 'pending')
        session['end_ts'] = time.time()
        session['end_reason'] = str(end_reason or '')
        self._write_incident_manifest(session)
        self._append_incident_session_row(session)

    @pyqtSlot(str, object, float, float, object)
    def handle_incident_frame_from_widget(self, loc_id, qimage, score, yolo_score=0.0, detections=None):
        """Add a captured incident to the Incidents tab."""
        try:
            debug_print(f"[INCIDENT] Received incident: loc_id={loc_id}, score={score:.3f}, detections={len(detections or [])}")
            # Cache PPE counters from detections so vision-only fusion updates can render PPE cards.
            try:
                if str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY)).strip().lower() == 'ppe':
                    loc_key = str(loc_id) if loc_id is not None else '_broadcast'
                    stats = self._extract_ppe_counts_from_detections(detections)
                    cache = getattr(self, '_ppe_stats_by_loc_id', {}) or {}
                    cache[loc_key] = stats
                    self._ppe_stats_by_loc_id = cache
            except Exception:
                pass

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

            if final_alarm:
                self._start_incident_session(loc_id, reason=(" | ".join(alarm_reason) or 'alarm'))
            self._record_incident_video_frame(loc_id, qimage, score, yolo_score, detections)

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
            from PyQt6.QtGui import QPixmap, QIcon
            from PyQt6.QtWidgets import QListWidgetItem
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
            item.setData(Qt.ItemDataRole.UserRole, idx)
            # Set icon and label
            icon = QIcon(pixmap.scaled(160, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            item.setIcon(icon)
            ts_str = datetime.fromtimestamp(entry['ts']).strftime('%H:%M:%S')
            item.setText(f"{entry['loc_id']}\n{ts_str} • {entry['score']:.2f}")
            self.incident_list.addItem(item)
            debug_print(f"[INCIDENT] Added to list: total={self.incident_list.count()}, store={len(self._incidents_store)}")
            self._update_incident_count()
            self._refresh_incident_cards()

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
            idx = item.data(Qt.ItemDataRole.UserRole)
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
        from PyQt6.QtWidgets import QProgressDialog

        exporter = IncidentExporter()
        temp_dir = tempfile.mkdtemp(prefix="incident_export_")

        frame_paths = []
        detection_frames = []

        timestamps = [e.get('ts', time.time()) for e in entries]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        duration_seconds = max(0.0, max_ts - min_ts)

        progress = QProgressDialog("Exporting incidents...", "Cancel", 0, len(entries), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
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
                    scaled_pixmap = pixmap.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
                    scaled_pixmap = pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.logo.setPixmap(scaled_pixmap)
                    try:
                        glow = QGraphicsDropShadowEffect(self.logo)
                        glow.setBlurRadius(12)
                        glow.setOffset(0, 0)
                        glow.setColor(QColor(255, 220, 0, 120))
                        self.logo.setGraphicsEffect(glow)
                    except Exception:
                        pass
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
            color: #FFDC00;
            letter-spacing: 2px;
            background: transparent;
            text-shadow: 0 0 6px rgba(255, 220, 0, 0.35);
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

    def _make_tactical_combo_icon(self, kind="grid"):
        """Return a compact icon for ghost-style header combos."""
        pix = QPixmap(14, 14)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#D2D8E0"), 1)
        painter.setPen(pen)
        if str(kind) == "grid":
            painter.drawRect(1, 1, 12, 12)
            painter.drawLine(5, 1, 5, 13)
            painter.drawLine(9, 1, 9, 13)
            painter.drawLine(1, 5, 13, 5)
            painter.drawLine(1, 9, 13, 9)
        else:
            painter.drawEllipse(2, 2, 10, 10)
            painter.drawLine(7, 2, 7, 12)
            painter.drawLine(2, 7, 12, 7)
        painter.end()
        from PyQt6.QtGui import QIcon
        return QIcon(pix)
    
    def init_header_actions(self, header_layout):
        """Create Settings gear icon and Profile icon with dropdown overlays"""
        
        # Settings Gear Icon
        settings_btn = QToolButton()
        settings_btn.setText("⚙")
        settings_btn.setFixedHeight(38)
        settings_btn.setFixedWidth(38)
        settings_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(210, 216, 224, 0.65);
                border-radius: 4px;
                color: #D2D8E0;
                font-size: 15px;
                font-weight: 700;
                padding: 0;
            }
            QToolButton:hover {
                border-color: #FFDC00;
                color: #FFDC00;
                background-color: rgba(255, 220, 0, 0.08);
            }
            QToolButton::menu-indicator { image: none; }
        """)
        
        settings_menu = QMenu()
        self._style_tactical_settings_menu(settings_menu)

        self._add_settings_menu_section(settings_menu, "STREAM MANAGEMENT")
        settings_menu.addAction("Configure Streams", self.configure_streams)
        settings_menu.addAction("Analytics & Banner Cards", self.show_analytics_banner_settings)
        settings_menu.addAction("Reset Streams", self.reset_streams)
        settings_menu.addAction("Observability", self.show_observability_settings)
        settings_menu.addSeparator()

        self._add_settings_menu_section(settings_menu, "SYSTEM CONFIGURATION")
        settings_menu.addAction("Backup Configuration", self.backup_config)
        settings_menu.addAction("Restore Configuration", self.restore_config)
        settings_menu.addAction("TCP Server Port", self._request_tcp_port_dialog)
        settings_menu.addAction("TCP Binding Mode", self.show_tcp_binding_mode_dialog)
        settings_menu.addSeparator()

        self._add_settings_menu_section(settings_menu, "SENSOR GRID")
        settings_menu.addAction("Thermal Grid Settings", self.show_thermal_grid_config)
        self.global_grid_action = settings_menu.addAction("Numeric Grid (All)")
        self.global_grid_action.setCheckable(True)
        self.global_grid_action.toggled.connect(self.toggle_all_numeric_grids)
        settings_menu.addAction("Sensor Configuration", self.show_sensor_config)
        settings_menu.addSeparator()

        self._add_settings_menu_section(settings_menu, "INVENTORY & MAPPINGS")
        settings_menu.addAction("Class Subclass Manager", self.show_master_class_config)
        settings_menu.addAction("Log Viewer", self.show_log_viewer_dialog)
        settings_menu.addAction("IP→Loc Mappings", self.show_ip_loc_mappings_dialog)
        settings_menu.addSeparator()

        self._add_settings_menu_section(settings_menu, "DATA OPERATIONS")
        settings_menu.addAction("Import Model", self.import_deployment_model)
        export_model_menu = settings_menu.addMenu("Export Model")
        self._style_tactical_settings_menu(export_model_menu)
        export_model_menu.addAction("Export to ONNX", lambda: self.export_model('onnx'))
        export_model_menu.addAction("Export to TorchScript", lambda: self.export_model('torchscript'))
        export_model_menu.addAction("Export to CoreML", lambda: self.export_model('coreml'))
        export_model_menu.addAction("Export to TensorFlow Lite", lambda: self.export_model('tflite'))
        settings_menu.addSeparator()

        self._add_settings_menu_section(settings_menu, "LIVE ASSETS")
        pfds_menu = settings_menu.addMenu("Live PFDS Devices")
        self._style_tactical_settings_menu(pfds_menu)
        pfds_menu.addAction("Add Device", self.show_pfds_add_dialog)
        pfds_menu.addAction("Live PFDS Devices", self._open_live_pfds_tab)
        settings_menu.addSeparator()

        self._add_settings_menu_section(settings_menu, "DIAGNOSTICS")
        settings_menu.addAction("Test Error", self.inject_test_stream_error)
        
        settings_btn.setMenu(settings_menu)
        settings_btn.setToolTip("Settings")
        header_layout.addWidget(settings_btn)
        
        # Profile Icon
        profile_btn = QToolButton()
        profile_btn.setText("👤 PROFILE")
        profile_btn.setFixedHeight(38)
        profile_btn.setMinimumWidth(110)
        profile_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        profile_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(210, 216, 224, 0.65);
                border-radius: 4px;
                color: #D2D8E0;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QToolButton:hover {
                border-color: #FFDC00;
                color: #FFDC00;
                background-color: rgba(255, 220, 0, 0.08);
            }
            QToolButton::menu-indicator { image: none; }
        """)
        
        profile_menu = QMenu()
        self._style_tactical_settings_menu(profile_menu)
        profile_menu.addAction("👤 My Profile", self.show_profile)
        profile_menu.addSeparator()
        profile_menu.addAction("🚪 Logout", self.logout)
        
        profile_btn.setMenu(profile_menu)
        profile_btn.setToolTip("Profile")
        header_layout.addWidget(profile_btn)

    def _style_tactical_settings_menu(self, menu):
        if menu is None:
            return
        menu.setStyleSheet("""
            QMenu {
                background-color: #141a22;
                border: 1px solid #d7aa1a;
                border-radius: 10px;
                padding: 8px 0;
            }
            QMenu::item {
                padding: 8px 20px;
                color: #e7c75f;
                font-size: 12px;
                font-weight: 600;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QMenu::item:selected {
                background-color: rgba(226, 184, 58, 0.22);
                color: #ffe38a;
                border-radius: 4px;
            }
            QMenu::item:disabled {
                color: #f0be2f;
                background: transparent;
                font-size: 10px;
                font-weight: 800;
                font-family: "Roboto Mono", "Menlo", "Consolas", monospace;
                letter-spacing: 0.6px;
                text-transform: uppercase;
                padding: 8px 16px 4px 16px;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(213, 171, 45, 0.36);
                margin: 6px 14px;
            }
        """)

    def _add_settings_menu_section(self, menu, title):
        if menu is None:
            return None
        action = menu.addAction(str(title).upper())
        action.setEnabled(False)
        return action

    def _style_tactical_dialog(self, dialog):
        if dialog is None:
            return
        dialog.setStyleSheet("""
            QDialog {
                background-color: #0f1722;
                color: #e7c75f;
                border: 1px solid #d7aa1a;
            }
            QLabel {
                color: #e7c75f;
                font-size: 12px;
                font-weight: 600;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QListWidget, QTableWidget, QTreeWidget {
                background-color: #141d2a;
                color: #ffe7a0;
                border: 1px solid #75602a;
                border-radius: 6px;
                padding: 6px 8px;
                selection-background-color: rgba(226, 184, 58, 0.30);
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
                border: 1px solid #e2b83a;
            }
            QPushButton {
                background-color: #273448;
                color: #f0d17c;
                border: 1px solid #7a6633;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QPushButton:hover {
                background-color: #344a67;
                border-color: #d7aa1a;
                color: #ffe9a6;
            }
            QPushButton:pressed {
                background-color: #1e2a3a;
            }
            QDialogButtonBox QPushButton {
                min-width: 96px;
            }
            QHeaderView::section {
                background-color: #1b2533;
                color: #f3cc6c;
                border: 1px solid #5f4f26;
                padding: 4px 6px;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: 1px solid #5f4f26;
                background-color: #0f1722;
            }
            QTabBar::tab {
                background-color: #1a2432;
                color: #c9a95a;
                border: 1px solid #5f4f26;
                padding: 6px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2b3a50;
                color: #ffe38a;
                border-color: #d7aa1a;
            }
        """)

    def _begin_live_pfds_modal_guard(self):
        if not self._is_live_pfds_tab_active():
            return None

        try:
            self._stabilize_live_pfds_surface()
        except Exception:
            pass

        anim = getattr(self, '_live_pfds_sidebar_anim', None)
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass

        guarded_widgets = []
        for attr_name in (
            'live_pfds_scroll',
            'live_pfds_grid_host',
            'live_pfds_sidebar',
            'live_pfds_pending_host',
        ):
            widget = getattr(self, attr_name, None)
            if widget is None:
                continue
            try:
                guarded_widgets.append((widget, widget.updatesEnabled()))
                widget.setUpdatesEnabled(False)
            except Exception:
                pass

            viewport_getter = getattr(widget, 'viewport', None)
            if callable(viewport_getter):
                try:
                    viewport = viewport_getter()
                except Exception:
                    viewport = None
                if viewport is not None:
                    try:
                        guarded_widgets.append((viewport, viewport.updatesEnabled()))
                        viewport.setUpdatesEnabled(False)
                    except Exception:
                        pass

        return guarded_widgets

    def _end_live_pfds_modal_guard(self, guarded_widgets):
        if not guarded_widgets:
            return

        for widget, was_enabled in reversed(guarded_widgets):
            try:
                widget.setUpdatesEnabled(was_enabled)
                if was_enabled:
                    widget.update()
                    # Do NOT call repaint() here — synchronous paint during unfreeze
                    # can cause macOS to momentarily release window activation.
            except Exception:
                pass

    def _run_live_pfds_modal(self, callback):
        guarded_widgets = self._begin_live_pfds_modal_guard()
        try:
            return callback()
        finally:
            self._end_live_pfds_modal_guard(guarded_widgets)

    def _exec_live_pfds_dialog(self, dialog):
        if dialog is None:
            return None
        return self._run_live_pfds_modal(lambda: dialog.exec())

    def init_settings_menu(self, title_bar):
        menu_btn = QToolButton()
        menu_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu()
        self._style_tactical_settings_menu(menu)
        menu.addAction("Profile", self.show_profile)
        menu.addAction("Configure Streams", self.configure_streams)
        menu.addAction("Analytics & Banner Cards", self.show_analytics_banner_settings)
        menu.addAction("Reset Streams", self.reset_streams)
        menu.addAction("Observability...", self.show_observability_settings)
        # Add backup/restore actions
        menu.addSeparator()
        menu.addAction("Backup Configuration", self.backup_config)
        menu.addAction("Restore Configuration", self.restore_config)
        menu.addSeparator()
        menu.addAction("TCP Server Port...", self._request_tcp_port_dialog)
        menu.addAction("TCP Binding Mode...", self.show_tcp_binding_mode_dialog)
        menu.addAction("Thermal Grid Settings...", self.show_thermal_grid_config)
        # Global numeric thermal grid toggle (all streams)
        self.global_grid_action = menu.addAction("Numeric Thermal Grid (All Streams)")
        self.global_grid_action.setCheckable(True)
        self.global_grid_action.toggled.connect(self.toggle_all_numeric_grids)
        menu.addAction("Sensor Configuration...", self.show_sensor_config)
        menu.addAction("Log Viewer...", self.show_log_viewer_dialog)
        # Configure PFDS Device submenu
        pfds_menu = QMenu("Configure Live PFDS Device", menu)
        pfds_menu.addAction("Add Device...", self.show_pfds_add_dialog)
        pfds_menu.addAction("View Live PFDS Devices...", self._open_live_pfds_tab)
        menu.addMenu(pfds_menu)
        menu.addAction("Inject Test Stream Error", self.inject_test_stream_error)
        menu.addSeparator()
        menu.addAction("Logout", self.logout)
        menu_btn.setMenu(menu)
        title_bar.addWidget(menu_btn)

    def _apply_tactical_status_module_style(self, frame, label, text, text_color="#D2D8E0", active=False, mono=True):
        """Apply consistent tactical styling to status-bar modules."""
        if frame is None or label is None:
            return
        border_color = "#FFDC00" if active else "#374552"
        font_family = '"Roboto Mono", "Menlo", "Consolas", monospace' if mono else '"Avenir Next", "Segoe UI", sans-serif'
        frame.setStyleSheet(
            "QFrame {"
            "background-color: rgba(15, 21, 29, 0.96);"
            f"border: 1px solid {border_color};"
            "border-radius: 2px;"
            "padding: 0px;"
            "}"
        )
        label.setStyleSheet(
            "QLabel {"
            f"color: {text_color};"
            f"font-family: {font_family};"
            "font-size: 11px;"
            "font-weight: 700;"
            "padding: 2px 8px;"
            "letter-spacing: 0.5px;"
            "}"
        )
        label.setText(str(text).upper())

    def _set_tcp_pulse_state(self, is_running):
        """Set pulse color/animation for high-visibility system health feedback."""
        if not hasattr(self, 'tcp_led') or self.tcp_led is None:
            return
        running = bool(is_running)
        glow_color = '#4CAF50' if running else '#8a2f2f'
        self.tcp_led.setStyleSheet(
            "QLabel {"
            f"background-color: {glow_color};"
            "border: 1px solid #1e242b;"
            "border-radius: 6px;"
            "}"
        )
        if hasattr(self, '_tcp_pulse_glow') and self._tcp_pulse_glow is not None:
            self._tcp_pulse_glow.setColor(QColor(glow_color))
        if hasattr(self, '_tcp_pulse_anim') and self._tcp_pulse_anim is not None:
            if running:
                if self._tcp_pulse_anim.state() != QAbstractAnimation.State.Running:
                    self._tcp_pulse_anim.start()
            else:
                self._tcp_pulse_anim.stop()
                if hasattr(self, '_tcp_pulse_glow') and self._tcp_pulse_glow is not None:
                    self._tcp_pulse_glow.setBlurRadius(2.0)

    def init_tcp_status_indicator(self):
        """Initialize TCP server status indicator in status bar."""
        from PyQt6.QtWidgets import QLabel, QPushButton, QWidget, QHBoxLayout, QFrame
        from PyQt6.QtCore import Qt

        # This can be called before tcp_server_port is initialized in some startup paths.
        cfg = getattr(self, 'config', {}) if isinstance(getattr(self, 'config', {}), dict) else {}
        port_value = int(getattr(self, 'tcp_server_port', cfg.get('tcp_port', 4888)))
        
        # Create a container widget for the status indicator
        status_widget = QWidget()
        status_widget.setObjectName("tacticalStatusStrip")
        status_widget.setStyleSheet("QWidget#tacticalStatusStrip { background: transparent; border: none; }")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(6, 0, 6, 0)
        status_layout.setSpacing(6)

        # SYSTEM HEALTH module with green pulse for peripheral awareness
        self.health_status_frame = QFrame()
        health_layout = QHBoxLayout(self.health_status_frame)
        health_layout.setContentsMargins(6, 1, 6, 1)
        health_layout.setSpacing(6)
        self.tcp_led = QLabel()
        self.tcp_led.setFixedSize(12, 12)
        health_layout.addWidget(self.tcp_led)
        self.health_status_label = QLabel("SYSTEM HEALTH: ONLINE")
        health_layout.addWidget(self.health_status_label)
        status_layout.addWidget(self.health_status_frame)
        self._apply_tactical_status_module_style(
            self.health_status_frame,
            self.health_status_label,
            "SYSTEM HEALTH: ONLINE",
            text_color="#CFF8D7",
            active=True,
            mono=True,
        )

        # CONNECTIVITY module
        self.tcp_status_frame = QFrame()
        tcp_layout = QHBoxLayout(self.tcp_status_frame)
        tcp_layout.setContentsMargins(0, 0, 0, 0)
        self.tcp_status_label = QLabel()
        tcp_layout.addWidget(self.tcp_status_label)
        status_layout.addWidget(self.tcp_status_frame)
        self._apply_tactical_status_module_style(
            self.tcp_status_frame,
            self.tcp_status_label,
            f"TCP SERVER: PORT {port_value}",
            text_color="#D2D8E0",
            active=False,
            mono=True,
        )

        # HARDWARE module
        self.device_status_frame = QFrame()
        device_layout = QHBoxLayout(self.device_status_frame)
        device_layout.setContentsMargins(0, 0, 0, 0)
        self.device_status_label = QLabel("DEVICE: CPU")
        device_layout.addWidget(self.device_status_label)
        status_layout.addWidget(self.device_status_frame)
        self._apply_tactical_status_module_style(
            self.device_status_frame,
            self.device_status_label,
            "DEVICE: CPU",
            text_color="#E5E9EF",
            active=False,
            mono=True,
        )

        # MODEL module
        self.model_status_frame = QFrame()
        model_layout = QHBoxLayout(self.model_status_frame)
        model_layout.setContentsMargins(0, 0, 0, 0)
        self.model_status_label = QLabel("MODEL: NOT LOADED")
        model_layout.addWidget(self.model_status_label)
        status_layout.addWidget(self.model_status_frame)
        self._apply_tactical_status_module_style(
            self.model_status_frame,
            self.model_status_label,
            "MODEL: NOT LOADED",
            text_color="#8B95A1",
            active=False,
            mono=True,
        )

        # Keep a compatibility label around for legacy references.
        self.detection_count_label = QLabel("DETECTIONS: 0")
        self.detection_count_label.hide()

        # Pulse animation setup (blur glow is more visible than opacity-only pulse).
        self._tcp_pulse_glow = QGraphicsDropShadowEffect(self.tcp_led)
        self._tcp_pulse_glow.setOffset(0, 0)
        self._tcp_pulse_glow.setColor(QColor("#4CAF50"))
        self._tcp_pulse_glow.setBlurRadius(3.0)
        self.tcp_led.setGraphicsEffect(self._tcp_pulse_glow)
        self._tcp_pulse_anim = QPropertyAnimation(self._tcp_pulse_glow, b"blurRadius", self)
        self._tcp_pulse_anim.setDuration(1000)
        self._tcp_pulse_anim.setKeyValueAt(0.0, 2.0)
        self._tcp_pulse_anim.setKeyValueAt(0.5, 14.0)
        self._tcp_pulse_anim.setKeyValueAt(1.0, 2.0)
        self._tcp_pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._tcp_pulse_anim.setLoopCount(-1)
        self._set_tcp_pulse_state(True)
        
        # Restart button
        restart_btn = QPushButton("RESTART")
        restart_btn.setFixedHeight(24)
        restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restart_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(17, 24, 33, 0.97);
                color: #FFDC00;
                border: 1px solid #FFDC00;
                border-radius: 2px;
                padding: 2px 14px;
                font-size: 11px;
                font-weight: 700;
                font-family: "Roboto Mono", "Menlo", "Consolas", monospace;
            }
            QPushButton:hover {
                background-color: rgba(38, 48, 62, 0.98);
            }
            QPushButton:pressed {
                background-color: rgba(56, 68, 84, 0.98);
            }
        """)
        # Defensive disconnect: ensures no stale callback (e.g., port dialog) is attached.
        try:
            restart_btn.clicked.disconnect()
        except Exception:
            pass
        restart_btn.clicked.connect(self._quick_restart_tcp_server)
        status_layout.addWidget(restart_btn)
        status_layout.addStretch()
        
        status_widget.setLayout(status_layout)
        
        # Add to status bar (permanent widget on the left)
        self.statusBar().addPermanentWidget(status_widget, 0)

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
        """Compatibility hook retained for older call sites (no tray icons)."""
        try:
            port = int(getattr(self, 'tcp_server_port', self.config.get('tcp_port', 4888)))
            if hasattr(self, 'tcp_status_label') and self.tcp_status_label is not None:
                self.tcp_status_label.setToolTip(f"TCP SERVER PORT {port}")
            if hasattr(self, 'device_status_label') and self.device_status_label is not None:
                self.device_status_label.setToolTip(self.device_status_label.text())
            if hasattr(self, 'model_status_label') and self.model_status_label is not None:
                self.model_status_label.setToolTip(self.model_status_label.text())
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
            self._set_tcp_pulse_state(is_running)

            port = int(getattr(self, 'tcp_server_port', self.config.get('tcp_port', 4888)))
            self._apply_tactical_status_module_style(
                self.health_status_frame,
                self.health_status_label,
                "SYSTEM HEALTH: ONLINE" if is_running else "SYSTEM HEALTH: OFFLINE",
                text_color="#CFF8D7" if is_running else "#E6B6B6",
                active=bool(is_running),
                mono=True,
            )
            self._apply_tactical_status_module_style(
                self.tcp_status_frame,
                self.tcp_status_label,
                f"TCP SERVER: PORT {port}",
                text_color="#D2D8E0" if is_running else "#9BA5B0",
                active=bool(is_running),
                mono=True,
            )
            self.tcp_status_label.setToolTip(str(message))
            self._refresh_status_tray_icons(tcp_running=is_running)
            
        except Exception as e:
            print(f"TCP status update error: {e}")

    def _refresh_model_status(self):
        """Update model load status label based on DetectionWorker state."""
        if not hasattr(self, 'model_status_label'):
            return
        try:
            from embereye_base.core.detection_worker import get_detection_worker
            worker = get_detection_worker()
            if not worker:
                self.model_status_label.setText("Model: Unavailable")
                self._set_status_chip_state(self.model_status_label, "warn")
                return
            stats = worker.get_stats()
            if hasattr(self, 'device_status_label'):
                inferred_device = str(stats.get('inference_device', '') or '').strip().lower()
                if inferred_device in ("0", "cuda", "gpu"):
                    self._apply_tactical_status_module_style(
                        self.device_status_frame,
                        self.device_status_label,
                        "DEVICE: GPU",
                        text_color="#D2D8E0",
                        active=True,
                        mono=True,
                    )
                elif inferred_device:
                    self._apply_tactical_status_module_style(
                        self.device_status_frame,
                        self.device_status_label,
                        f"DEVICE: {inferred_device.upper()}",
                        text_color="#D2D8E0",
                        active=False,
                        mono=True,
                    )
                else:
                    self._apply_tactical_status_module_style(
                        self.device_status_frame,
                        self.device_status_label,
                        "DEVICE: CPU",
                        text_color="#D2D8E0",
                        active=False,
                        mono=True,
                    )
            if stats.get('model_loaded'):
                model_name = str(stats.get('model_name') or '').strip()
                model_version = str(stats.get('model_version') or '').strip()
                if model_version:
                    model_text = f"MODEL: {model_version}"
                elif model_name:
                    model_text = f"MODEL: {model_name}"
                else:
                    model_text = "MODEL: LOADED"
                self._apply_tactical_status_module_style(
                    self.model_status_frame,
                    self.model_status_label,
                    model_text,
                    text_color="#FFDC00",
                    active=True,
                    mono=True,
                )
                self.model_status_label.setToolTip(str(stats.get('model_path') or model_text))
            else:
                model_error = stats.get('model_error')
                if model_error:
                    self._apply_tactical_status_module_style(
                        self.model_status_frame,
                        self.model_status_label,
                        "MODEL: ERROR",
                        text_color="#E6B6B6",
                        active=False,
                        mono=True,
                    )
                    self.model_status_label.setToolTip(model_error)
                else:
                    self._apply_tactical_status_module_style(
                        self.model_status_frame,
                        self.model_status_label,
                        "MODEL: NOT LOADED",
                        text_color="#8B95A1",
                        active=False,
                        mono=True,
                    )
                    self.model_status_label.setToolTip("")
            self._refresh_status_tray_icons()
        except Exception:
            self._apply_tactical_status_module_style(
                self.model_status_frame,
                self.model_status_label,
                "MODEL: ERROR",
                text_color="#E6B6B6",
                active=False,
                mono=True,
            )
            self._refresh_status_tray_icons()

    def _quick_restart_tcp_server(self):
        """One-click tactical restart for the TCP server using current config."""
        import inspect
        port = int(self.config.get('tcp_port', getattr(self, 'tcp_server_port', 4888)))
        tcp_mode = self.config.get('tcp_mode', 'async')  # async is the default; threaded is DEPRECATED
        binding_mode = self._get_tcp_binding_mode()
        self.tcp_server_port = port
        try:
            if hasattr(self, 'tcp_server') and self.tcp_server:
                try:
                    stop_result = self.tcp_server.stop()
                    if inspect.isawaitable(stop_result):
                        if self._async_loop is not None:
                            import asyncio
                            fut = asyncio.run_coroutine_threadsafe(stop_result, self._async_loop)
                            fut.result(timeout=5)
                        else:
                            import asyncio
                            asyncio.run(stop_result)
                except Exception:
                    pass
                finally:
                    self.tcp_server = None
                    self.tcp_sensor_server = None
            self.update_tcp_status(False, f"TCP SERVER: RESTARTING PORT {port}")

            self.tcp_message_count = 0
            if tcp_mode == 'async':
                from embereye_base.core.tcp_async_server import TCPAsyncSensorServer
                self.tcp_server = TCPAsyncSensorServer(
                    port=port,
                    packet_callback=self._emit_tcp_packet,
                    binding_mode=binding_mode,
                )
                self.tcp_sensor_server = self.tcp_server
                if self.tcp_server:
                    if self._async_loop is None:
                        import asyncio
                        import threading
                        self._async_loop = asyncio.new_event_loop()

                        def _run_loop(loop):
                            asyncio.set_event_loop(loop)
                            loop.run_forever()

                        self._async_thread = threading.Thread(target=_run_loop, args=(self._async_loop,), daemon=True)
                        self._async_thread.start()
                    import asyncio
                    fut = asyncio.run_coroutine_threadsafe(self.tcp_server.start(), self._async_loop)
                    fut.result(timeout=5)
            else:
                # DEPRECATED: threaded mode causes IP-keyed identity collisions for
                # multi-device localhost setups (e.g. simulators). Set tcp_mode=async.
                log_server_error(
                    "[DEPRECATED] tcp_mode='threaded' is retired. "
                    "Switch stream_config.json tcp_mode to 'async' to prevent device routing failures."
                )
                from embereye_base.core.tcp_sensor_server import TCPSensorServer
                self.tcp_server = TCPSensorServer(port=port, packet_callback=self._emit_tcp_packet)
                self.tcp_sensor_server = self.tcp_server
                if self.tcp_server:
                    self.tcp_server.start()

            self.update_tcp_status(True, f"TCP SERVER: RUNNING ON PORT {port} ({tcp_mode}, {binding_mode})")
        except Exception as e:
            self.update_tcp_status(False, f"TCP SERVER: RESTART FAILED - {e}")
            QMessageBox.critical(self, "TCP Server Error", f"Failed to restart TCP server on port {port}:\n{e}")

    def _get_tcp_binding_mode(self):
        mode = str(self.config.get('tcp_binding_mode', 'auto_bind')).strip().lower()
        if mode in ('handshake', 'device_id', 'device_id_handshake'):
            return 'handshake'
        return 'auto_bind'

    def show_tcp_binding_mode_dialog(self):
        from PyQt6.QtWidgets import QInputDialog

        current_mode = self._get_tcp_binding_mode()
        options = ['auto_bind', 'handshake']
        current_index = options.index(current_mode) if current_mode in options else 0
        selected_mode, ok = QInputDialog.getItem(
            self,
            "TCP Binding Mode",
            "Select device binding strategy:",
            options,
            current_index,
            False,
        )
        if not ok:
            return

        next_mode = str(selected_mode or '').strip().lower()
        if next_mode not in options:
            next_mode = 'auto_bind'
        if next_mode == current_mode:
            return

        self.config['tcp_binding_mode'] = next_mode
        from embereye_base.core.stream_config import StreamConfig
        StreamConfig.save_config(self.config)
        self._quick_restart_tcp_server()
        QMessageBox.information(
            self,
            "TCP Binding Mode Updated",
            f"TCP binding mode set to '{next_mode}'.",
        )

    def _request_tcp_port_dialog(self):
        """Allow TCP port prompt only for explicit menu actions."""
        self._port_dialog_requested = True
        self.show_tcp_port_dialog()

    def show_tcp_port_dialog(self):
        import inspect
        from PyQt6.QtWidgets import QInputDialog

        # Safety gate: non-menu invocations should perform direct restart,
        # never prompt for a port change.
        if not bool(getattr(self, '_port_dialog_requested', False)):
            self._quick_restart_tcp_server()
            return

        self._port_dialog_requested = False
        current_port = self.config.get('tcp_port', 9001)
        port, ok = QInputDialog.getInt(self, "TCP Server Port", "Enter TCP server port:", value=current_port, min=1024, max=65535)
        if ok and port != current_port:
            # Stop existing server
            if hasattr(self, 'tcp_server') and self.tcp_server:
                try:
                    stop_result = self.tcp_server.stop()
                    if inspect.isawaitable(stop_result):
                        if self._async_loop is not None:
                            import asyncio
                            fut = asyncio.run_coroutine_threadsafe(stop_result, self._async_loop)
                            fut.result(timeout=5)
                        else:
                            import asyncio
                            asyncio.run(stop_result)
                    self.update_tcp_status(False, "TCP Server: Stopped for restart")
                except Exception as e:
                    print(f"TCP server stop error: {e}")
                finally:
                    self.tcp_server = None
                    self.tcp_sensor_server = None
            
            # Update config
            self.config['tcp_port'] = port
            self.tcp_server_port = port
            from embereye_base.core.stream_config import StreamConfig
            StreamConfig.save_config(self.config)
            
            # Restart with new port
            try:
                tcp_mode = self.config.get('tcp_mode', 'async')  # async is the default; threaded is DEPRECATED
                binding_mode = self._get_tcp_binding_mode()
                self.tcp_message_count = 0
                # Always connect the signal (PyQt5 does not duplicate connections)
                self.tcp_packet_signal.connect(self.handle_tcp_packet, Qt.ConnectionType.QueuedConnection)
                if tcp_mode == 'async':
                    from embereye_base.core.tcp_async_server import TCPAsyncSensorServer
                    self.tcp_server = TCPAsyncSensorServer(
                        port=port,
                        packet_callback=self._emit_tcp_packet,
                        binding_mode=binding_mode,
                    )
                else:
                    # DEPRECATED: threaded mode causes IP-keyed identity collisions for
                    # multi-device localhost setups (e.g. simulators). Set tcp_mode=async.
                    log_server_error(
                        "[DEPRECATED] tcp_mode='threaded' is retired. "
                        "Switch stream_config.json tcp_mode to 'async' to prevent device routing failures."
                    )
                    from embereye_base.core.tcp_sensor_server import TCPSensorServer
                    self.tcp_server = TCPSensorServer(port=port, packet_callback=self._emit_tcp_packet)
                if tcp_mode == 'async':
                    if self._async_loop is None:
                        import asyncio
                        import threading
                        self._async_loop = asyncio.new_event_loop()

                        def _run_loop(loop):
                            asyncio.set_event_loop(loop)
                            loop.run_forever()

                        self._async_thread = threading.Thread(target=_run_loop, args=(self._async_loop,), daemon=True)
                        self._async_thread.start()
                    import asyncio
                    fut = asyncio.run_coroutine_threadsafe(self.tcp_server.start(), self._async_loop)
                    fut.result(timeout=5)
                else:
                    self.tcp_server.start()
                self.update_tcp_status(True, f"TCP Server: Running on port {port} ({tcp_mode}, {binding_mode})")
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
        from embereye_base.app.thermal_grid_config import ThermalGridConfigDialog
        
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
                'temp_threshold': self.fusion_temp_threshold,
                'critical_temp_threshold': self.fusion_critical_temp_threshold
            }
        
        dialog = ThermalGridConfigDialog(self, current_settings)
        dialog.settings_changed.connect(self.apply_thermal_grid_settings)
        
        if dialog.exec():
            # Settings already applied via signal
            QMessageBox.information(self, "Settings Applied", "Thermal grid configuration has been updated.")
    
    def apply_thermal_grid_settings(self, settings):
        """Apply thermal grid settings to all video widgets and sensor fusion."""
        # Update sensor fusion thresholds
        self.fusion_temp_threshold = float(settings['temp_threshold'])
        self.fusion_critical_temp_threshold = float(settings.get('critical_temp_threshold', fusion_config.critical_temp_threshold))
        self._update_fusion_engine_config()
        self._sync_shared_configs()
        
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
        from embereye_base.app.sensor_config_dialog import SensorConfigDialog

        available_pfds = sorted({str(getattr(widget, 'loc_id', '')).strip() for widget in self.get_video_widgets() if str(getattr(widget, 'loc_id', '')).strip()})
        saved_target_pfds = str(self.config.get('thermal_target_pfds', self.config.get('thermal_target_room', ''))).strip()
        if saved_target_pfds and saved_target_pfds not in available_pfds:
            available_pfds.append(saved_target_pfds)
            available_pfds = sorted(set(available_pfds))
        
        # Get current settings
        current_settings = {
            # Fusion parameters
            'temp_threshold': self.fusion_temp_threshold,
            'critical_temp_threshold': self.fusion_critical_temp_threshold,
            'gas_ppm_threshold': self.fusion_gas_ppm_threshold,
            'flame_active_value': self.fusion_flame_active_value,
            'smoke_threshold_pct': float(getattr(self, 'fusion_smoke_threshold_pct', self.config.get('smoke_threshold_pct', 25.0))),
            'flame_threshold_pct': float(getattr(self, 'fusion_flame_threshold_pct', self.config.get('flame_threshold_pct', 25.0))),
            'min_sources': self.fusion_min_sources,
            
            # Gas sensor calibration
            'gas_r0': getattr(self.gas_sensor, 'r0', 76.63),
            'gas_rl': getattr(self.gas_sensor, 'rl', 1.0),
            'gas_vcc': getattr(self.gas_sensor, 'vcc', 5.0),
            
            # Display settings
            'hot_cell_decay_time': 5.0,
            'freeze_on_alarm': True,
            'show_fusion_overlay': True,
            'vision_threshold': float(getattr(self, 'fusion_vision_threshold', self.config.get('vision_threshold', getattr(self, 'vision_threshold', 0.7)))),
            'vision_confidence_weight': float(getattr(self, 'fusion_vision_confidence_weight', self.config.get('vision_confidence_weight', 0.5))),
            'thermal_render_mode': str(self.config.get('thermal_render_mode', 'fixed_scale_inferno')),
            'thermal_emissivity': float(self.config.get('thermal_emissivity', 0.95)),
            'thermal_auto_window': bool(self.config.get('thermal_auto_window', True)),
            'thermal_window_min': float(self.config.get('thermal_window_min', 20.0)),
            'thermal_window_max': float(self.config.get('thermal_window_max', 120.0)),
            'thermal_apply_scope': str(self.config.get('thermal_apply_scope', 'all')),
            'thermal_target_pfds': saved_target_pfds,
            'thermal_available_pfds': available_pfds,
            'thermal_target_room': saved_target_pfds,
            'thermal_available_rooms': available_pfds,

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
        
        if dialog.exec():
            applied = dialog.get_settings()
            applied_scope = str(applied.get('thermal_apply_scope', 'all'))
            applied_pfds = str(applied.get('thermal_target_pfds', applied.get('thermal_target_room', ''))).strip()
            target_text = f"PFDS Device: {applied_pfds}" if applied_scope in ('per_pfds', 'per_camera') and applied_pfds else "All PFDS"
            if applied.get('restart_app', False):
                confirm = QMessageBox.question(
                    self,
                    "Restart Application",
                    "Settings have been applied. Restart EmberEye Field now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if confirm == QMessageBox.StandardButton.Yes:
                    self._restart_application()
                    return
            QMessageBox.information(self, "Settings Applied", f"Sensor configuration updated for {target_text} (no restart required).")

    def show_analytics_banner_settings(self):
        """Configure analytics selection and fusion banner card behavior."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Analytics & Fusion Banner")
        dialog.setMinimumSize(720, 560)
        self._style_tactical_dialog(dialog)

        root_layout = QVBoxLayout(dialog)
        intro = QLabel(
            "Select analytics categories and control fusion banner rendering. "
            "Banner cards are rendered from the active analytics context of each stream/frame."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        category_group = QGroupBox("Analytics Categories")
        category_layout = QVBoxLayout(category_group)

        category_list = QListWidget()
        category_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        category_items = {}
        for category in ANALYTICS_CATEGORY_NAMES:
            item = QListWidgetItem(category.upper())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = category in getattr(self, 'enabled_analytics_categories', [self.active_analytics_category])
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, category)
            category_list.addItem(item)
            category_items[category] = item
        category_layout.addWidget(category_list)

        primary_row = QHBoxLayout()
        primary_row.addWidget(QLabel("Primary runtime analytics"))
        primary_combo = QComboBox()
        for category in ANALYTICS_CATEGORY_NAMES:
            primary_combo.addItem(category.upper(), category)
        primary_idx = primary_combo.findData(
            self._normalize_analytics_category(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
        )
        if primary_idx >= 0:
            primary_combo.setCurrentIndex(primary_idx)
        primary_row.addWidget(primary_combo, 1)
        category_layout.addLayout(primary_row)
        root_layout.addWidget(category_group)

        banner_group = QGroupBox("Fusion Banner")
        banner_layout = QVBoxLayout(banner_group)
        banner_enabled_check = QCheckBox("Display fusion banner cards")
        banner_enabled_check.setChecked(bool(getattr(self, 'fusion_banner_enabled', True)))
        banner_layout.addWidget(banner_enabled_check)

        auto_mode_check = QCheckBox("Auto mode (layout chooses cards)")
        auto_mode_check.setChecked(str(getattr(self, 'fusion_banner_mode', 'auto')) == 'auto')
        banner_layout.addWidget(auto_mode_check)

        manual_cards = self._normalize_fusion_card_selection(
            getattr(self, 'fusion_banner_manual_cards', self._default_fusion_card_selection())
        )

        card_lists_row = QHBoxLayout()
        fire_box = QGroupBox("Fire Cards")
        fire_layout = QVBoxLayout(fire_box)
        fire_cards_list = QListWidget()
        fire_cards_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        fire_layout.addWidget(fire_cards_list)

        ppe_box = QGroupBox("PPE Cards")
        ppe_layout = QVBoxLayout(ppe_box)
        ppe_cards_list = QListWidget()
        ppe_cards_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        ppe_layout.addWidget(ppe_cards_list)

        card_lists_row.addWidget(fire_box, 1)
        card_lists_row.addWidget(ppe_box, 1)
        banner_layout.addLayout(card_lists_row)
        root_layout.addWidget(banner_group, 1)

        def _populate_cards(list_widget, category):
            list_widget.clear()
            selected = set(manual_cards.get(category, []))
            for key in get_fusion_cards(category):
                item = QListWidgetItem(key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, key)
                list_widget.addItem(item)

        def _selected_categories():
            selected = []
            for category in ANALYTICS_CATEGORY_NAMES:
                item = category_items.get(category)
                if item and item.checkState() == Qt.CheckState.Checked:
                    selected.append(category)
            return selected

        def _selected_card_keys(list_widget):
            keys = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item and item.checkState() == Qt.CheckState.Checked:
                    key = str(item.data(Qt.ItemDataRole.UserRole) or '').strip().lower()
                    if key:
                        keys.append(key)
            return keys

        def _refresh_enabled_state():
            selected = set(_selected_categories())
            manual_mode = bool(banner_enabled_check.isChecked() and (not auto_mode_check.isChecked()))
            fire_box.setEnabled(manual_mode and ('fire' in selected))
            ppe_box.setEnabled(manual_mode and ('ppe' in selected))

            active_primary = str(primary_combo.currentData() or '').strip().lower()
            if selected and active_primary not in selected:
                primary_combo.setCurrentIndex(primary_combo.findData(next(iter(selected))))

        _populate_cards(fire_cards_list, 'fire')
        _populate_cards(ppe_cards_list, 'ppe')
        _refresh_enabled_state()

        category_list.itemChanged.connect(lambda _item: _refresh_enabled_state())
        banner_enabled_check.toggled.connect(lambda _checked: _refresh_enabled_state())
        auto_mode_check.toggled.connect(lambda _checked: _refresh_enabled_state())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )

        def _save():
            selected = _selected_categories()
            if not selected:
                QMessageBox.warning(dialog, "Analytics Required", "Select at least one analytics category.")
                return

            self.enabled_analytics_categories = selected
            self.fusion_banner_enabled = bool(banner_enabled_check.isChecked())
            self.fusion_banner_mode = 'auto' if auto_mode_check.isChecked() else 'manual'

            updated_manual = self._normalize_fusion_card_selection(self.fusion_banner_manual_cards)
            updated_manual['fire'] = _selected_card_keys(fire_cards_list) or ['global']
            updated_manual['ppe'] = _selected_card_keys(ppe_cards_list) or ['global']
            self.fusion_banner_manual_cards = updated_manual

            new_primary = self._normalize_analytics_category(primary_combo.currentData())
            if new_primary not in selected:
                new_primary = selected[0]
            self.active_analytics_category = new_primary

            self._persist_analytics_banner_preferences()
            self._reload_rule_engine_for_active_category()
            self._sync_shared_configs()
            self._apply_banner_preferences_to_widgets()
            self.statusBar().showMessage("Analytics and fusion banner settings updated", 4000)
            dialog.accept()

        buttons.accepted.connect(_save)
        buttons.rejected.connect(dialog.reject)
        root_layout.addWidget(buttons)
        dialog.exec()

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

    def _sync_shared_configs(self):
        """Synchronize runtime values into module-level shared fusion/hybrid configs."""
        try:
            fusion_config.smoke_threshold_pct = float(getattr(self, 'fusion_smoke_threshold_pct', fusion_config.smoke_threshold_pct))
            fusion_config.flame_threshold_pct = float(getattr(self, 'fusion_flame_threshold_pct', fusion_config.flame_threshold_pct))
            fusion_config.gas_ppm_threshold = float(getattr(self, 'fusion_gas_ppm_threshold', fusion_config.gas_ppm_threshold))
            fusion_config.temp_threshold = float(getattr(self, 'fusion_temp_threshold', fusion_config.temp_threshold))
            fusion_config.critical_temp_threshold = float(getattr(self, 'fusion_critical_temp_threshold', fusion_config.critical_temp_threshold))
            fusion_config.vision_threshold = float(getattr(self, 'fusion_vision_threshold', fusion_config.vision_threshold))
            fusion_config.vision_confidence_weight = float(getattr(self, 'fusion_vision_confidence_weight', fusion_config.vision_confidence_weight))

            hybrid_detection_config.heuristic_threshold = float(getattr(self, 'heuristic_threshold', hybrid_detection_config.heuristic_threshold))
            hybrid_detection_config.force_yolo_every_n_frames = int(getattr(self, 'force_yolo_every_n_frames', hybrid_detection_config.force_yolo_every_n_frames))
            hybrid_detection_config.yolo_conf_threshold = float(getattr(self, 'yolo_conf_threshold', hybrid_detection_config.yolo_conf_threshold))
            hybrid_detection_config.possible_conf_threshold = float(getattr(self, 'possible_conf_threshold', hybrid_detection_config.possible_conf_threshold))
            hybrid_detection_config.confirmed_conf_threshold = float(getattr(self, 'confirmed_conf_threshold', hybrid_detection_config.confirmed_conf_threshold))
            hybrid_detection_config.rule_min_yolo_conf = float(getattr(self, '_rule_min_yolo_conf', hybrid_detection_config.rule_min_yolo_conf))
            hybrid_detection_config.rule_min_fusion_conf = float(getattr(self, '_rule_min_fusion_conf', hybrid_detection_config.rule_min_fusion_conf))
            os.environ['EMBEREYE_ANALYTICS_CATEGORY'] = str(getattr(self, 'active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))

            first_widget = next(iter(self.video_widgets.values()), None) if hasattr(self, 'video_widgets') else None
            if first_widget is not None:
                fusion_config.freeze_on_alarm = bool(getattr(first_widget, 'freeze_on_alarm', fusion_config.freeze_on_alarm))
                fusion_config.show_fusion_overlay = bool(getattr(first_widget, 'show_fusion_overlay', fusion_config.show_fusion_overlay))
                decay_value = float(getattr(first_widget, 'hot_cells_decay_time', fusion_config.hot_cell_decay_time))
                fusion_config.hot_cell_decay_time = int(round(decay_value))
            else:
                fusion_config.freeze_on_alarm = bool(self.config.get('freeze_on_alarm', fusion_config.freeze_on_alarm))
                fusion_config.show_fusion_overlay = bool(self.config.get('show_fusion_overlay', fusion_config.show_fusion_overlay))
                fusion_config.hot_cell_decay_time = int(round(float(self.config.get('hot_cell_decay_time', fusion_config.hot_cell_decay_time))))
        except Exception as e:
            debug_print(f"[CONFIG] Shared config sync skipped: {e}")
    
    def apply_sensor_config(self, settings):
        """Apply sensor configuration settings."""
        self._last_sensor_apply_warning_shown = False
        # Update sensor fusion
        self.fusion_temp_threshold = float(settings['temp_threshold'])
        self.fusion_critical_temp_threshold = float(settings.get('critical_temp_threshold', getattr(self, 'fusion_critical_temp_threshold', fusion_config.critical_temp_threshold)))
        self.fusion_gas_ppm_threshold = float(settings['gas_ppm_threshold'])
        self.fusion_smoke_threshold_pct = float(settings.get('smoke_threshold_pct', getattr(self, 'fusion_smoke_threshold_pct', 25.0)))
        self.fusion_flame_threshold_pct = float(settings.get('flame_threshold_pct', getattr(self, 'fusion_flame_threshold_pct', 25.0)))
        self.fusion_vision_threshold = float(settings.get('vision_threshold', getattr(self, 'fusion_vision_threshold', 0.7)))
        self.fusion_vision_confidence_weight = float(settings.get('vision_confidence_weight', getattr(self, 'fusion_vision_confidence_weight', 0.5)))
        self.fusion_flame_active_value = int(settings.get('flame_active_value', getattr(self, 'fusion_flame_active_value', 1)))
        self.fusion_min_sources = int(settings['min_sources'])
        self.vision_threshold = self.fusion_vision_threshold
        self._update_fusion_engine_config()
        
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
            from embereye_base.core.detection_worker import get_detection_worker
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

        thermal_mode = str(settings.get('thermal_render_mode', self.config.get('thermal_render_mode', 'fixed_scale_inferno')))
        thermal_emissivity = float(settings.get('thermal_emissivity', self.config.get('thermal_emissivity', 0.95)))
        thermal_auto_window = bool(settings.get('thermal_auto_window', self.config.get('thermal_auto_window', True)))
        thermal_window_min = float(settings.get('thermal_window_min', self.config.get('thermal_window_min', 20.0)))
        thermal_window_max = float(settings.get('thermal_window_max', self.config.get('thermal_window_max', 120.0)))
        if thermal_window_max <= thermal_window_min:
            thermal_window_max = thermal_window_min + 1.0
        thermal_scope = str(settings.get('thermal_apply_scope', self.config.get('thermal_apply_scope', 'all')))
        thermal_target_pfds = str(settings.get('thermal_target_pfds', settings.get('thermal_target_room', self.config.get('thermal_target_pfds', self.config.get('thermal_target_room', ''))))).strip()

        if thermal_scope in ('per_pfds', 'per_camera') and thermal_target_pfds:
            target_widgets = [widget for widget in self.get_video_widgets() if str(getattr(widget, 'loc_id', '')).strip() == thermal_target_pfds]
        else:
            target_widgets = list(self.get_video_widgets())

        if thermal_scope in ('per_pfds', 'per_camera') and thermal_target_pfds and not target_widgets:
            QMessageBox.warning(
                self,
                "PFDS Not Active",
                f"No active camera tile found for PFDS Device: {thermal_target_pfds}.\n"
                "Settings were saved and will apply when this PFDS becomes active.",
            )
            self._last_sensor_apply_warning_shown = True

        for widget in target_widgets:
            if hasattr(widget, 'apply_thermal_runtime_config'):
                widget.apply_thermal_runtime_config(
                    mode=thermal_mode,
                    emissivity=thermal_emissivity,
                    auto_window=thermal_auto_window,
                    window_min=thermal_window_min,
                    window_max=thermal_window_max,
                )

        try:
            target_text = f"PFDS Device: {thermal_target_pfds}" if thermal_scope in ('per_pfds', 'per_camera') and thermal_target_pfds else "All PFDS"
            self.statusBar().showMessage(f"Thermal settings applied to {target_text}", 5000)
        except Exception:
            pass

        # Debug logging toggle
        set_debug_enabled(bool(settings.get('debug_enabled', False)))
        
        # Update anomaly settings in main window
        self.anomaly_threshold = settings.get('anomaly_threshold', 0.4)
        self._anomaly_max_items = settings.get('anomaly_max_items', 200)
        self.anomaly_save_enabled = settings.get('anomaly_save_enabled', False)
        self.anomaly_save_dir = settings.get('anomaly_save_dir', '')
        self.anomaly_retention_days = settings.get('anomaly_retention_days', 7)

        # Persist settings to stream config
        self.config['smoke_threshold_pct'] = self.fusion_smoke_threshold_pct
        self.config['flame_threshold_pct'] = self.fusion_flame_threshold_pct
        self.config['temp_threshold'] = self.fusion_temp_threshold
        self.config['gas_ppm_threshold'] = self.fusion_gas_ppm_threshold
        self.config['vision_threshold'] = settings.get('vision_threshold', getattr(self, 'vision_threshold', 0.7))
        self.config['vision_confidence_weight'] = self.fusion_vision_confidence_weight
        self.config['flame_active_value'] = self.fusion_flame_active_value
        self.config['min_sources'] = self.fusion_min_sources
        self.config['critical_temp_threshold'] = self.fusion_critical_temp_threshold
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
        self.config['thermal_render_mode'] = thermal_mode
        self.config['thermal_emissivity'] = thermal_emissivity
        self.config['thermal_auto_window'] = thermal_auto_window
        self.config['thermal_window_min'] = thermal_window_min
        self.config['thermal_window_max'] = thermal_window_max
        self.config['thermal_apply_scope'] = thermal_scope
        self.config['thermal_target_pfds'] = thermal_target_pfds
        self.config['thermal_target_room'] = thermal_target_pfds
        profile_value = settings.get('detection_default_profile', self.config.get('detection_default_profile', {}))
        self.config['detection_default_profile'] = profile_value if isinstance(profile_value, dict) else {}
        try:
            StreamConfig.save_config(self.config)
        except Exception as e:
            debug_print(f"[CONFIG] Save config failed: {e}")
        
        print(
            f"Sensor config updated: Temp={settings['temp_threshold']}, Gas={settings['gas_ppm_threshold']}, "
            f"Smoke={self.fusion_smoke_threshold_pct}%, Flame={self.fusion_flame_threshold_pct}%, "
            f"VisionThr={self.fusion_vision_threshold}, VisionWeight={self.fusion_vision_confidence_weight}, "
            f"R0={settings['gas_r0']}, MinSources={settings['min_sources']}, AnomalyThr={self.anomaly_threshold}, "
            f"Heuristic={self.heuristic_threshold}, ForceEveryN={self.force_yolo_every_n_frames}, YOLOConf={self.yolo_conf_threshold}, "
            f"Bands=({self.possible_conf_threshold}/{self.confirmed_conf_threshold}), "
            f"Rule(yolo/fusion)=({self._rule_min_yolo_conf}/{self._rule_min_fusion_conf}), "
            f"BoxMode={self.detection_box_mode}, BoxClasses={len(self.detection_box_classes)}, "
            f"ThermalMode={thermal_mode}, Emissivity={thermal_emissivity}, AutoWindow={thermal_auto_window}, "
            f"Window=({thermal_window_min}-{thermal_window_max}), Scope={thermal_scope}, PFDS={thermal_target_pfds or 'ALL'}"
        )
        self._sync_shared_configs()

    def show_master_class_config(self):
        """Open the master class configuration dialog and refresh classes on save."""
        try:
            from embereye_base.app.master_class_config_dialog import MasterClassConfigDialog
            from embereye_base.core.class_config import load_master_classes, get_leaf_classes
            
            dlg = MasterClassConfigDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
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
        """Add PFDS/EmberHawk device with mandatory serial binding and access flags."""
        from PyQt6.QtWidgets import (
            QDialog,
            QFormLayout,
            QLineEdit,
            QComboBox,
            QSpinBox,
            QDialogButtonBox,
            QMessageBox,
            QCheckBox,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Live PFDS Device")
        self._style_tactical_dialog(dlg)
        layout = QFormLayout(dlg)

        name_edit = QLineEdit(); name_edit.setPlaceholderText("Device Name")
        ip_edit = QLineEdit(); ip_edit.setPlaceholderText("IP:Port (e.g., 127.0.0.1:5000)")
        serial_edit = QLineEdit(); serial_edit.setPlaceholderText("Required serial (DEVICE_ID)")
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
        authorized_check = QCheckBox("Authorized")
        authorized_check.setChecked(True)
        linked_check = QCheckBox("Linked")
        linked_check.setChecked(True)

        layout.addRow("Name", name_edit)
        layout.addRow("IP Address", ip_edit)
        layout.addRow("Serial Number *", serial_edit)
        layout.addRow("Location Id", loc_combo)
        layout.addRow("Mode", mode_combo)
        layout.addRow("Poll Frequency", poll_spin)
        layout.addRow("Access", authorized_check)
        layout.addRow("Link", linked_check)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)

        def on_ok():
            if not self._ensure_operator_identity(dlg, action="adding PFDS device"):
                return
            name = name_edit.text().strip()
            ip = ip_edit.text().strip()
            serial = self._normalize_serial_key(serial_edit.text())
            loc = loc_combo.currentText().strip()
            mode = mode_combo.currentText()
            poll = poll_spin.value()
            if not name or not ip:
                QMessageBox.warning(dlg, "Missing Data", "Please enter device name and IP:Port.")
                return
            if not serial:
                QMessageBox.warning(dlg, "Missing Data", "Serial Number is mandatory.")
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
                device_id = self.emberhawk.add_device(name, ip_address, loc if loc else None, mode, int(poll))
                effective_linked = linked_check.isChecked()
                self.emberhawk.set_device_access(
                    device_id,
                    is_authorized=authorized_check.isChecked(),
                    is_linked=effective_linked,
                    actor=self._operator_actor(),
                    reason="add_device_dialog",
                )
                if serial:
                    self.emberhawk.bind_serial_to_device(device_id, serial)
                    self._pending_device_by_serial.pop(serial, None)
                self._refresh_live_operations_views()
                QMessageBox.information(dlg, "Saved", f"EmberHawk device '{name}' saved.\nIP: {ip_address}\nLocation: {loc or 'N/A'}\nMode: {mode}\nPoll: {poll}s")
            except Exception as e:
                QMessageBox.critical(dlg, "Save Failed", f"Could not save device: {e}")
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _refresh_live_operations_views(self):
        self._refresh_live_pfds_tab()
        self._refresh_live_assets_tab()

    def _clear_dynamic_layout(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_dynamic_layout(child_layout)
            if widget is not None:
                # Hide removed widgets immediately so stale cards do not linger
                # during the same event loop turn. Do not detach them from the
                # parent here; on macOS that can momentarily promote them to a
                # top-level window and steal focus.
                try:
                    widget.hide()
                except Exception:
                    pass
                widget.deleteLater()

    def _responsive_card_columns(self, viewport_width: int, min_card_width: int = 320) -> int:
        width = max(int(viewport_width or 0), min_card_width)
        return max(1, width // max(220, int(min_card_width)))

    def _format_seen_text(self, value) -> str:
        ts = self._parse_seen_timestamp(value)
        if ts is None:
            return "NO SIGNAL"
        delta = max(0, int(time.time() - ts))
        if delta < 60:
            return f"{delta}s AGO"
        if delta < 3600:
            return f"{delta // 60}m AGO"
        if delta < 86400:
            return f"{delta // 3600}h AGO"
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')

    def _location_choices_for_live_devices(self):
        loc_ids = set()
        try:
            groups = self.config.get('groups', [])
            streams_block = self.config.get('streams', [])
            if isinstance(streams_block, dict):
                source_groups = groups or list(streams_block.keys())
                for group in source_groups:
                    for stream in streams_block.get(group, []):
                        lid = stream.get('location_id') or stream.get('loc_id') or stream.get('name')
                        if lid:
                            loc_ids.add(str(lid).strip())
            else:
                for stream in streams_block:
                    lid = stream.get('location_id') or stream.get('loc_id') or stream.get('name')
                    if lid:
                        loc_ids.add(str(lid).strip())
        except Exception:
            pass
        if not loc_ids:
            loc_ids.add('demo_room')
        return sorted(loc_ids)

    def _get_emberhawk_device_by_id(self, device_id):
        try:
            did = int(device_id)
        except Exception:
            return None
        try:
            for device in self.emberhawk.list_devices():
                if int(device.get('id', -1)) == did:
                    return device
        except Exception:
            return None
        return None

    def _pending_from_recent_telemetry(self, now_ts: float = None) -> dict:
        """Recover pending identities from recent telemetry so brief sightings remain visible in UI."""
        now_val = float(now_ts if now_ts is not None else time.time())
        retention_s = int(getattr(self, '_pending_telemetry_retention_s', 24 * 60 * 60) or 24 * 60 * 60)
        # Use tcp_logger's canonical path so source and frozen EXE modes agree.
        telemetry_path = os.path.join('logs', 'device_telemetry.jsonl')
        try:
            from embereye_base.utils.tcp_logger import DEVICE_TELEMETRY_LOG
            if DEVICE_TELEMETRY_LOG:
                telemetry_path = str(DEVICE_TELEMETRY_LOG)
        except Exception:
            pass
        telemetry_path = os.path.abspath(telemetry_path)
        if not os.path.exists(telemetry_path):
            return {}

        def _tail_lines(path: str, max_bytes: int = 256 * 1024):
            try:
                with open(path, 'rb') as fh:
                    fh.seek(0, os.SEEK_END)
                    size = fh.tell()
                    fh.seek(max(0, size - max_bytes), os.SEEK_SET)
                    chunk = fh.read().decode('utf-8', errors='ignore')
                return chunk.splitlines()
            except Exception:
                return []

        recovered = {}
        for raw in _tail_lines(telemetry_path):
            text = str(raw or '').strip()
            if not text or not text.startswith('{'):
                continue
            try:
                rec = json.loads(text)
            except Exception:
                continue
            event = str(rec.get('event') or '').strip()
            payload = rec.get('payload') or {}
            if not isinstance(payload, dict):
                continue
            serial = self._normalize_serial_key(payload.get('serial') or payload.get('serial_number'))
            if not serial:
                continue
            state = str(payload.get('state') or '').strip().lower()
            drop_reason = str(payload.get('drop_reason') or '').strip().lower()
            include = (
                event == 'identity_pending'
                or (event == 'packet_dropped' and state == 'pending_identity')
                or (event == 'packet_dropped' and drop_reason in ('device_not_linked', 'access_blocked', 'missing_serial'))
            )
            if not include:
                continue
            seen_ts = self._parse_seen_timestamp(rec.get('timestamp'))
            if seen_ts is None:
                continue
            if (now_val - float(seen_ts)) > float(retention_s):
                continue

            info = recovered.get(serial)
            if info is None or float(seen_ts) >= float(info.get('last_seen') or 0):
                recovered[serial] = {
                    'serial_number': serial,
                    'client_ip': str(payload.get('client_ip') or ''),
                    'last_seen': float(seen_ts),
                    'state': 'pending_identity',
                }
        return recovered

    def _exclude_active_serials_from_pending(self, pending: dict, devices, now_ts: float = None) -> dict:
        """Keep pending views mutually exclusive with active PFDS cards."""
        filtered = dict(pending or {})
        for device in (devices or []):
            serial = self._normalize_serial_key((device or {}).get('serial_number'))
            if not serial:
                continue
            if self._get_device_lifecycle_state(device, now_ts=now_ts) == 'active':
                filtered.pop(serial, None)
        return filtered

    def _collect_live_pfds_snapshot(self):
        now_ts = time.time()
        try:
            devices = list(self.emberhawk.list_devices())
        except Exception:
            devices = []

        pending = dict(getattr(self, '_pending_device_by_serial', {}) or {})
        if bool(getattr(self, '_pending_from_telemetry_enabled', False)):
            for serial, info in self._pending_from_recent_telemetry(now_ts=now_ts).items():
                pending.setdefault(serial, info)
        for device in devices:
            serial = self._normalize_serial_key(device.get('serial_number'))
            if not serial or serial in pending:
                continue
            missing_location = not self._normalize_loc_key(device.get('location_id'))
            not_linked = not bool(device.get('is_linked', True))
            not_authorized = not bool(device.get('is_authorized', True))
            if missing_location or not_linked or not_authorized:
                if missing_location:
                    pending_state = 'pending_location'
                elif not_linked:
                    pending_state = 'unlinked'
                else:
                    pending_state = 'unauthorized'
                pending[serial] = {
                    'serial_number': serial,
                    'client_ip': device.get('last_seen_ip') or '',
                    'last_seen': device.get('last_seen_at') or '',
                    'state': pending_state,
                    'device_id': device.get('id'),
                }

        pending = self._exclude_active_serials_from_pending(pending, devices, now_ts=now_ts)

        pending_list = []
        for serial, info in sorted(pending.items(), key=lambda item: item[0]):
            payload = dict(info)
            payload['serial_number'] = self._normalize_serial_key(payload.get('serial_number') or serial)
            payload['resolved_state'] = self._get_pending_identity_state(payload, now_ts=now_ts)
            pending_list.append(payload)

        offline_list = []
        try:
            if hasattr(self, 'device_status_manager') and self.device_status_manager:
                all_offline = list(self.device_status_manager.get_offline_devices())
                for status in all_offline:
                    dtype = str(getattr(status, 'device_type', '') or '').upper()
                    if (not dtype) or ('PFDS' in dtype) or ('EMBERHAWK' in dtype):
                        offline_list.append(status)
        except Exception:
            offline_list = []

        # Fallback source: derive offline PFDS cards directly from configured EmberHawk devices.
        # This covers deployments where device_status_manager is not actively registering PFDS devices.
        try:
            server = getattr(self, 'tcp_sensor_server', None) or getattr(self, 'tcp_server', None)
            serial_to_client = dict(getattr(server, '_serial_to_client', {}) or {}) if server else {}
            serial_to_ip = dict(getattr(server, '_serial_to_ip', {}) or {}) if server else {}
            connected_keys = set((getattr(server, '_client_writers', {}) or {}).keys()) if server else set()
            if not connected_keys and server:
                connected_keys = set((getattr(server, '_client_sockets', {}) or {}).keys())

            existing_keys = set()
            for entry in offline_list:
                key = str(getattr(entry, 'ip', '') or getattr(entry, 'device_id', '') or '').strip()
                if key:
                    existing_keys.add(key)

            for device in devices:
                serial = self._normalize_serial_key(device.get('serial_number'))
                ip_endpoint = str(device.get('ip') or '').strip()
                host_ip = ip_endpoint.split(':', 1)[0] if ':' in ip_endpoint else ip_endpoint
                state = self._get_device_lifecycle_state(device, now_ts=now_ts)

                has_live_socket = False
                if serial and serial in serial_to_client:
                    mapped_key = str(serial_to_client.get(serial) or '').strip()
                    has_live_socket = bool(mapped_key and mapped_key in connected_keys)
                elif serial and serial in serial_to_ip:
                    mapped_ip = str(serial_to_ip.get(serial) or '').strip()
                    has_live_socket = bool(mapped_ip and (
                        mapped_ip in connected_keys or
                        any(str(key).startswith(f"{mapped_ip}:") for key in connected_keys)
                    ))
                elif host_ip:
                    has_live_socket = bool(
                        host_ip in connected_keys or
                        any(str(key).startswith(f"{host_ip}:") for key in connected_keys)
                    )

                should_mark_offline = bool(serial and not has_live_socket)
                if state in {'ghost'}:
                    should_mark_offline = True

                if not should_mark_offline:
                    continue

                key = str(device.get('id') or ip_endpoint or serial or '').strip()
                if key and key in existing_keys:
                    continue

                offline_list.append({
                    'device_id': device.get('id'),
                    'device_name': device.get('name') or f"PFDS {device.get('id')}",
                    'ip': ip_endpoint or '--',
                    'loc_id': device.get('location_id') or '--',
                    'device_type': 'PFDS',
                    'connection_attempts': 0,
                    'failure_reason': 'No active socket connection' if serial else 'Missing serial binding',
                })
                if key:
                    existing_keys.add(key)
        except Exception:
            pass

        return devices, pending_list, offline_list, now_ts

    def _notify_live_ops_action(self, message: str, timeout_ms: int = 2500):
        msg = str(message or '').strip()
        if not msg:
            return
        try:
            self.statusBar().showMessage(msg, int(timeout_ms))
        except Exception:
            pass
        try:
            print(f"[LIVE_OPS] {msg}")
        except Exception:
            pass

    def _reconnect_offline_device(self, ip: str, parent=None):
        target_ip = str(ip or '').strip()
        if not target_ip:
            return
        if not hasattr(self, 'device_status_manager') or not self.device_status_manager:
            QMessageBox.warning(parent or self, 'Unavailable', 'Device status manager is not available.')
            self._notify_live_ops_action('Reconnect unavailable: device status manager is not initialized', 3000)
            return
        try:
            self._notify_live_ops_action(f"Reconnect requested for {target_ip}", 2500)
            ok = bool(self.device_status_manager.manual_reconnect(target_ip))
            if ok:
                self._run_live_pfds_modal(
                    lambda: QMessageBox.information(parent or self, 'Reconnect', f'Reconnect initiated for {target_ip}.')
                )
                self._notify_live_ops_action(f"Reconnect initiated for {target_ip}", 3000)
            else:
                self._run_live_pfds_modal(
                    lambda: QMessageBox.warning(parent or self, 'Reconnect Failed', f'Could not trigger reconnect for {target_ip}.')
                )
                self._notify_live_ops_action(f"Reconnect failed for {target_ip}", 3000)
        except Exception as e:
            self._run_live_pfds_modal(
                lambda: QMessageBox.critical(parent or self, 'Reconnect Failed', f'Could not reconnect {target_ip}: {e}')
            )
            self._notify_live_ops_action(f"Reconnect error for {target_ip}: {e}", 3500)
        self._refresh_live_operations_views()

    def _open_devices_tab(self):
        # Legacy cards still use "Devices Tab". If the tab isn't mounted in this layout,
        # route users to the Live PFDS dialog instead of silently doing nothing.
        try:
            if hasattr(self, 'tabs') and self.tabs is not None:
                for idx in range(self.tabs.count()):
                    if str(self.tabs.tabText(idx)).strip().upper() == 'DEVICES':
                        self.tabs.setCurrentIndex(idx)
                        self._notify_live_ops_action("Opened DEVICES tab", 2000)
                        return
        except Exception as e:
            print(f"Devices tab open failed: {e}")
            self._notify_live_ops_action(f"Devices tab open failed: {e}", 3000)

        try:
            self.show_pfds_view_dialog()
            self._notify_live_ops_action("DEVICES tab unavailable; opened PFDS dialog", 2500)
        except Exception as e:
            QMessageBox.critical(self, 'Devices Tab', f'Unable to open PFDS dialog: {e}')
            self._notify_live_ops_action(f"Unable to open PFDS dialog: {e}", 3500)

    def _on_tab_changed(self, index):
        """Handle tab switch: re-activate window on macOS and hard-refresh LIVE PFDS surface."""
        try:
            from PyQt6.QtCore import QTimer
            # Never force activateWindow()/raise_() on tab change.
            # On macOS this can trigger app focus churn while switching tabs.

            tab_name = ''
            try:
                if hasattr(self, 'tabs') and self.tabs is not None and 0 <= int(index) < self.tabs.count():
                    tab_name = str(self.tabs.tabText(int(index))).strip().upper()
            except Exception:
                tab_name = ''

            try:
                self._set_videowall_render_enabled(tab_name == 'VIDEOWALL')
            except Exception:
                pass

            if tab_name == 'LIVE PFDS':
                if bool(getattr(self, '_live_pfds_transition_inflight', False)):
                    return
                self._live_pfds_transition_inflight = True

                def _finish_live_pfds_transition():
                    self._live_pfds_transition_inflight = False
                    deferred = getattr(self, '_live_pfds_deferred_filter', None)
                    if deferred:
                        self._live_pfds_deferred_filter = None
                        try:
                            QTimer.singleShot(0, lambda f=deferred: self._set_live_pfds_filter(f))
                        except Exception:
                            pass

                # Ensure VIDEOWALL maximize mode is fully torn down before PFDS actions.
                # Keeping a maximized tile state alive across tab switches can cause
                # repaint artifacts and focus churn when PFDS filters trigger refreshes.
                try:
                    if getattr(self, 'maximized_widget', None) is not None:
                        self.handle_minimize()
                except Exception:
                    pass

                def _restore_live_pfds_surface():
                    # Guard: if the user switched away before the timer fired, skip.
                    if not self._is_live_pfds_tab_active():
                        _finish_live_pfds_transition()
                        return
                    try:
                        self._stabilize_live_pfds_surface()
                    except Exception:
                        pass

                    for attr_name in (
                        'live_pfds_scroll',
                        'live_pfds_grid_host',
                        'live_pfds_sidebar',
                        'live_pfds_pending_host',
                    ):
                        widget = getattr(self, attr_name, None)
                        if widget is None:
                            continue
                        try:
                            widget.setUpdatesEnabled(True)
                            widget.update()
                        except Exception:
                            pass
                        viewport_getter = getattr(widget, 'viewport', None)
                        if callable(viewport_getter):
                            try:
                                viewport = viewport_getter()
                            except Exception:
                                viewport = None
                            if viewport is not None:
                                try:
                                    viewport.setUpdatesEnabled(True)
                                    viewport.update()
                                except Exception:
                                    pass

                    try:
                        self._refresh_live_pfds_tab()
                    except Exception:
                        pass
                    finally:
                        QTimer.singleShot(0, _finish_live_pfds_transition)

                QTimer.singleShot(0, _restore_live_pfds_surface)
        except Exception:
            pass

    def _open_live_pfds_tab(self):
        # Prefer focusing the LIVE PFDS tab in the main window.
        # Only open the dialog as a fallback when the tab is not present.
        try:
            if hasattr(self, 'tabs') and self.tabs is not None:
                for idx in range(self.tabs.count()):
                    if str(self.tabs.tabText(idx)).strip().upper() == 'LIVE PFDS':
                        self.tabs.setCurrentIndex(idx)
                        self._refresh_live_operations_views()
                        self._notify_live_ops_action("Opened LIVE PFDS tab", 2000)
                        return
        except Exception as e:
            print(f"LIVE PFDS tab focus failed: {e}")

        # Fallback: if tab is unavailable, use dialog entry point.
        try:
            self.show_pfds_view_dialog()
        except Exception as e:
            QMessageBox.critical(self, 'Live PFDS', f'Unable to open Live PFDS dialog: {e}')

    def _set_videowall_render_enabled(self, enabled: bool):
        """Enable/disable videowall widget repainting when tab visibility changes."""
        try:
            widgets = list(getattr(self, 'video_widgets', {}).values())
        except Exception:
            widgets = []
        for widget in widgets:
            if widget is None:
                continue
            try:
                widget.setUpdatesEnabled(bool(enabled))
                if bool(enabled):
                    widget.update()
            except Exception:
                pass
            try:
                label = getattr(widget, 'video_label', None)
                if label is not None:
                    label.setUpdatesEnabled(bool(enabled))
                    if bool(enabled):
                        label.update()
            except Exception:
                pass

    def _collect_live_asset_entries(self):
        devices, _pending_list, _offline_list, now_ts = self._collect_live_pfds_snapshot()
        streams_config = self.config.get('streams', [])
        streams = []
        if isinstance(streams_config, dict):
            for group_name, group_streams in streams_config.items():
                for stream in group_streams:
                    payload = dict(stream)
                    payload.setdefault('group', group_name)
                    streams.append(payload)
        else:
            streams = [dict(stream) for stream in streams_config]

        device_by_loc = {}
        for device in devices:
            loc_key = self._normalize_loc_key(device.get('location_id'))
            if loc_key and loc_key not in device_by_loc:
                device_by_loc[loc_key] = device

        asset_entries = []
        seen_locs = set()
        for stream in streams:
            loc_id = self._normalize_loc_key(stream.get('loc_id') or stream.get('location_id') or stream.get('name'))
            if not loc_id:
                continue
            seen_locs.add(loc_id)
            device = device_by_loc.get(loc_id)
            state = self._get_device_lifecycle_state(device, now_ts=now_ts) if device else 'pending_location'
            asset_entries.append({
                'loc_id': loc_id,
                'stream_name': str(stream.get('name') or loc_id),
                'stream_url': str(stream.get('url') or ''),
                'group': str(stream.get('group') or self.current_group or 'default'),
                'device': device,
                'state': state,
                'sensor_seen': self._sensor_last_packet_ts_by_loc_id.get(loc_id),
            })

        for loc_id, device in sorted(device_by_loc.items(), key=lambda item: item[0]):
            if loc_id in seen_locs:
                continue
            asset_entries.append({
                'loc_id': loc_id,
                'stream_name': 'No linked video stream',
                'stream_url': '',
                'group': 'unassigned',
                'device': device,
                'state': self._get_device_lifecycle_state(device, now_ts=now_ts),
                'sensor_seen': self._sensor_last_packet_ts_by_loc_id.get(loc_id),
            })

        return sorted(asset_entries, key=lambda item: (str(item.get('group')), str(item.get('loc_id'))))

    def _apply_live_card_style(self, frame, state: str):
        if frame is None:
            return
        state_key = str(state or 'pending_location').strip().lower()
        is_active = state_key == 'active'
        is_offline = state_key in {'offline', 'disconnected'}
        is_incomplete = state_key in {'ghost', 'pending_identity', 'pending_location', 'unlinked', 'unauthorized'}
        border_style = 'solid' if is_active else 'dashed' if (is_incomplete or is_offline) else 'solid'
        border_color = '#ffdc00' if (is_active or is_incomplete) else '#c15b5b' if is_offline else '#75808d'
        background = '#10161c' if is_active else '#201519' if is_offline else '#141a22'
        frame.setObjectName('LiveOpCard')
        frame.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        frame.setStyleSheet(
            f"QFrame#LiveOpCard {{ background-color: {background}; border: 2px {border_style} {border_color}; border-radius: 4px; }}"
            "QFrame#LiveOpCard:hover { border-color: #ffe564; background-color: #182028; }"
            "QLabel#LiveCardEyebrow { color: #97a1ac; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }"
            "QLabel#LiveCardTitle { color: #edf1f5; font-size: 14px; font-weight: 800; }"
            "QLabel#LiveCardState { color: #ffdc00; font-size: 10px; font-weight: 800; letter-spacing: 0.7px; }"
            "QLabel#LiveCardMeta { color: #8f99a5; font-size: 11px; font-family: \"Roboto Mono\", \"Menlo\", \"Consolas\", monospace; }"
            "QToolButton#LiveCardMenuButton { background: transparent; border: 1px solid #495564; border-radius: 3px; color: #ffdc00; font-size: 15px; padding: 2px 8px; }"
            "QToolButton#LiveCardMenuButton:hover { border-color: #ffe46e; color: #fff2a8; background-color: rgba(255, 220, 0, 0.08); }"
            "QPushButton#LiveCardActionButton { background-color: #26303a; color: #edf1f5; border: 1px solid #596575; border-radius: 3px; padding: 6px 10px; font-weight: 700; }"
            "QPushButton#LiveCardActionButton:hover { border-color: #ffdc00; color: #ffdc00; }"
        )
        # Keep rendering deterministic across platforms by avoiding stacked graphics effects on cards.
        frame.setGraphicsEffect(None)

    def _build_live_card_menu(self, actions):
        menu_btn = QToolButton()
        menu_btn.setObjectName('LiveCardMenuButton')
        menu_btn.setText('⋯')
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_btn)
        self._style_tactical_settings_menu(menu)
        for label, callback in actions:
            menu.addAction(label, callback)
        menu_btn.setMenu(menu)
        return menu_btn

    def _close_live_pfds_popups(self):
        try:
            popup = QApplication.activePopupWidget()
            if popup is not None:
                try:
                    popup.close()
                except Exception:
                    pass
        except Exception:
            pass

        for host_name in ('live_pfds_grid_host', 'live_pfds_pending_host'):
            host = getattr(self, host_name, None)
            if host is None:
                continue
            try:
                tool_buttons = host.findChildren(QToolButton)
            except Exception:
                tool_buttons = []
            for button in tool_buttons:
                try:
                    menu = button.menu()
                except Exception:
                    menu = None
                if menu is None:
                    continue
                try:
                    menu.close()
                except Exception:
                    pass

    def _restore_live_pfds_focus(self):
        # Intentionally no-op: programmatic focus assignment on macOS causes
        # activation churn while switching PFDS filters.
        return

    def _build_live_pfds_device_card(self, device):
        state = self._get_device_lifecycle_state(device)
        card = QFrame()
        card.setMinimumWidth(320)
        card.setMinimumHeight(240)
        card.setVisible(True)
        self._apply_live_card_style(card, state)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        device_id = device.get('id')
        eyebrow = QLabel(f"PFDS {device_id}")
        eyebrow.setObjectName('LiveCardEyebrow')
        top.addWidget(eyebrow)
        top.addStretch(1)
        top.addWidget(self._build_live_card_menu([
            ('Toggle Authorized', lambda did=device_id: self._toggle_live_device_authorized(did, self)),
            ('Toggle Linked', lambda did=device_id: self._toggle_live_device_linked(did, self)),
            ('Set Location Id', lambda did=device_id: self._set_live_device_location(did, self)),
            ('Set Poll Rate', lambda did=device_id: self._set_live_device_poll_seconds(did, self)),
            ('Remove Device', lambda did=device_id: self._remove_live_device(did, self)),
        ]))
        layout.addLayout(top)

        title = QLabel(str(device.get('name') or f"PFDS {device_id}").upper())
        title.setObjectName('LiveCardTitle')
        layout.addWidget(title)

        state_label = QLabel(str(state).replace('_', ' ').upper())
        state_label.setObjectName('LiveCardState')
        layout.addWidget(state_label)

        for meta in [
            f"ID       {device_id}",
            f"LOCATION {device.get('location_id') or 'UNMAPPED'}",
            f"IP       {device.get('ip') or '--'}",
            f"SERIAL   {device.get('serial_number') or 'UNSEEN'}",
            f"MODE     {device.get('mode') or '--'} | POLL {device.get('poll_seconds') or '--'}s",
            f"SEEN     {self._format_seen_text(device.get('last_seen_at'))}",
        ]:
            lbl = QLabel(meta)
            lbl.setObjectName('LiveCardMeta')
            layout.addWidget(lbl)

        action_row = QHBoxLayout()
        set_loc_btn = QPushButton('Set Location')
        set_loc_btn.setObjectName('LiveCardActionButton')
        set_loc_btn.clicked.connect(lambda _=False, did=device_id: self._set_live_device_location(did, self))
        action_row.addWidget(set_loc_btn)

        auth_btn = QPushButton('Authorize')
        auth_btn.setObjectName('LiveCardActionButton')
        auth_btn.clicked.connect(lambda _=False, did=device_id: self._toggle_live_device_authorized(did, self))
        action_row.addWidget(auth_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return card

    def _build_pending_identity_card(self, pending_info):
        state = str(pending_info.get('resolved_state') or self._get_pending_identity_state(pending_info)).strip()
        card = QFrame()
        card.setMinimumWidth(300)
        card.setMinimumHeight(170)
        card.setVisible(True)
        self._apply_live_card_style(card, state)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        eyebrow = QLabel('PENDING IDENTITY')
        eyebrow.setObjectName('LiveCardEyebrow')
        top.addWidget(eyebrow)
        top.addStretch(1)
        top.addWidget(self._build_live_card_menu([
            ('Assign Room', lambda info=dict(pending_info): self._assign_pending_identity_to_room_from_info(info, self)),
        ]))
        layout.addLayout(top)

        title = QLabel(str(pending_info.get('serial_number') or 'UNKNOWN SERIAL').upper())
        title.setObjectName('LiveCardTitle')
        layout.addWidget(title)

        state_label = QLabel(state.replace('_', ' ').upper())
        state_label.setObjectName('LiveCardState')
        layout.addWidget(state_label)

        for meta in [
            f"CLIENT   {pending_info.get('client_ip') or '--'}",
            f"SEEN     {self._format_seen_text(pending_info.get('last_seen'))}",
            f"DEVICE   {pending_info.get('device_id') or 'UNBOUND'}",
        ]:
            lbl = QLabel(meta)
            lbl.setObjectName('LiveCardMeta')
            layout.addWidget(lbl)

        assign_btn = QPushButton('Assign Room')
        assign_btn.setObjectName('LiveCardActionButton')
        assign_btn.clicked.connect(lambda _=False, info=dict(pending_info): self._assign_pending_identity_to_room_from_info(info, self))
        layout.addWidget(assign_btn)
        return card

    def _build_offline_device_card(self, device_status):
        def _read(field, default='--'):
            if isinstance(device_status, dict):
                value = device_status.get(field, default)
            else:
                value = getattr(device_status, field, default)
            if value is None or value == '':
                return default
            return value

        card = QFrame()
        card.setMinimumWidth(320)
        card.setMinimumHeight(220)
        self._apply_live_card_style(card, 'offline')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        eyebrow = QLabel('OFFLINE DEVICE')
        eyebrow.setObjectName('LiveCardEyebrow')
        top.addWidget(eyebrow)
        top.addStretch(1)
        top.addWidget(self._build_live_card_menu([
            ('Reconnect', lambda ip=str(_read('ip', '')): self._reconnect_offline_device(ip, self)),
            ('Open Devices Tab', self._open_devices_tab),
        ]))
        layout.addLayout(top)

        title = QLabel(str(_read('device_name', 'Unknown Device')).upper())
        title.setObjectName('LiveCardTitle')
        layout.addWidget(title)

        state_label = QLabel('OFFLINE')
        state_label.setObjectName('LiveCardState')
        layout.addWidget(state_label)

        failure_reason = str(_read('failure_reason', '') or 'No telemetry')
        for meta in [
            f"IP       {_read('ip', '--')}",
            f"LOCATION {_read('loc_id', '--')}",
            f"TYPE     {_read('device_type', '--')}",
            f"ATTEMPTS {_read('connection_attempts', 0)}",
            f"REASON   {failure_reason}",
        ]:
            lbl = QLabel(meta)
            lbl.setWordWrap(True)
            lbl.setObjectName('LiveCardMeta')
            layout.addWidget(lbl)

        action_row = QHBoxLayout()
        reconnect_btn = QPushButton('Reconnect')
        reconnect_btn.setObjectName('LiveCardActionButton')
        reconnect_btn.clicked.connect(lambda _=False, ip=str(_read('ip', '')): self._reconnect_offline_device(ip, self))
        action_row.addWidget(reconnect_btn)

        devices_btn = QPushButton('Devices Tab')
        devices_btn.setObjectName('LiveCardActionButton')
        devices_btn.clicked.connect(self._open_devices_tab)
        action_row.addWidget(devices_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return card

    def _build_live_asset_card(self, entry):
        device = entry.get('device')
        state = str(entry.get('state') or 'pending_location')
        card = QFrame()
        card.setMinimumWidth(340)
        card.setMinimumHeight(240)
        self._apply_live_card_style(card, state)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        menu_actions = [('Open PFDS Dialog', self.show_pfds_view_dialog)]
        if device:
            device_id = device.get('id')
            menu_actions = [
                ('Toggle Authorized', lambda did=device_id: self._toggle_live_device_authorized(did, self)),
                ('Toggle Linked', lambda did=device_id: self._toggle_live_device_linked(did, self)),
                ('Set Location Id', lambda did=device_id: self._set_live_device_location(did, self)),
                ('Set Poll Rate', lambda did=device_id: self._set_live_device_poll_seconds(did, self)),
                ('Open PFDS Dialog', self.show_pfds_view_dialog),
            ]

        top = QHBoxLayout()
        eyebrow = QLabel(f"GROUP {str(entry.get('group') or 'default').upper()}")
        eyebrow.setObjectName('LiveCardEyebrow')
        top.addWidget(eyebrow)
        top.addStretch(1)
        top.addWidget(self._build_live_card_menu(menu_actions))
        layout.addLayout(top)

        title = QLabel(str(entry.get('loc_id') or 'UNMAPPED').upper())
        title.setObjectName('LiveCardTitle')
        layout.addWidget(title)

        stream_name = QLabel(str(entry.get('stream_name') or '').upper())
        stream_name.setObjectName('LiveCardState')
        layout.addWidget(stream_name)

        for meta in [
            f"STREAM   {entry.get('stream_url') or 'NO VIDEO URL'}",
            f"PFDS     {device.get('name') if device else 'NO PFDS LINK'}",
            f"SERIAL   {device.get('serial_number') if device else 'UNSEEN'}",
            f"STATUS   {state.replace('_', ' ').upper()}",
            f"SEEN     {self._format_seen_text(entry.get('sensor_seen') or (device or {}).get('last_seen_at'))}",
        ]:
            lbl = QLabel(meta)
            lbl.setWordWrap(True)
            lbl.setObjectName('LiveCardMeta')
            layout.addWidget(lbl)

        action_row = QHBoxLayout()
        primary_btn = QPushButton('Set Location' if device else 'Add PFDS Device')
        primary_btn.setObjectName('LiveCardActionButton')
        if device:
            primary_btn.clicked.connect(lambda _=False, did=device.get('id'): self._set_live_device_location(did, self))
        else:
            primary_btn.clicked.connect(self.show_pfds_add_dialog)
        action_row.addWidget(primary_btn)

        secondary_btn = QPushButton('Authorize' if device else 'Open PFDS')
        secondary_btn.setObjectName('LiveCardActionButton')
        if device:
            secondary_btn.clicked.connect(lambda _=False, did=device.get('id'): self._toggle_live_device_authorized(did, self))
        else:
            secondary_btn.clicked.connect(self.show_pfds_view_dialog)
        action_row.addWidget(secondary_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return card

    def _refresh_live_pfds_tab(self):
        import time
        refresh_start = time.time()
        from PyQt6.QtWidgets import QApplication
        
        if not hasattr(self, 'live_pfds_grid'):
            return
        if bool(getattr(self, '_live_pfds_refresh_inflight', False)):
            self._live_pfds_refresh_pending = True
            return
        self._live_pfds_refresh_inflight = True

        try:
            self._stabilize_live_pfds_surface()
        except Exception:
            pass

        # Do NOT freeze PFDS widgets during card rebuild.
        # On macOS, calling setUpdatesEnabled(False) on widgets and then toggling
        # sidebar visibility within the frozen state causes the native compositor
        # to briefly expose the window background, producing a flash and releasing
        # app activation.  The card rebuild is fast and imperceptible without a freeze.
        self._live_pfds_refresh_pending = False
        devices, pending_list, offline_list, _now_ts = self._collect_live_pfds_snapshot()

        offline_device_ids = set()
        for entry in (offline_list or []):
            did = None
            if isinstance(entry, dict):
                did = entry.get('device_id')
            else:
                did = getattr(entry, 'device_id', None)
            try:
                if did is not None:
                    offline_device_ids.add(int(did))
            except Exception:
                pass

        online_devices = []
        for device in (devices or []):
            try:
                did = int(device.get('id'))
            except Exception:
                did = None
            if did is not None and did in offline_device_ids:
                continue
            # Only count as LIVE if device is authorized + linked (active/ghost state).
            # Unauthorized or unlinked devices appear only in PENDING, not LIVE —
            # counting them in both causes the ALL total to over-count unique devices.
            state = self._get_device_lifecycle_state(device, now_ts=_now_ts)
            if state not in {'active', 'ghost'}:
                continue
            online_devices.append(device)

        live_count = len(online_devices)
        pending_count = len(pending_list)
        total_count = live_count + len(offline_list) + pending_count

        if hasattr(self, 'live_pfds_filter_all_btn'):
            self.live_pfds_filter_all_btn.setText(f"ALL {total_count}")
        if hasattr(self, 'live_pfds_filter_live_btn'):
            self.live_pfds_filter_live_btn.setText(f"LIVE {live_count}")
        if hasattr(self, 'live_pfds_filter_pending_btn'):
            self.live_pfds_filter_pending_btn.setText(f"PENDING {pending_count}")

        current_filter = str(getattr(self, '_live_pfds_filter', 'all') or 'all').strip().lower()
        if current_filter not in {'all', 'live', 'pending'}:
            current_filter = 'all'
            self._live_pfds_filter = 'all'
        self._sync_live_pfds_filter_buttons()
        show_pending_sidebar = current_filter != 'pending'
        self._apply_live_pfds_sidebar_state(None if show_pending_sidebar else False)

        # Do not force-close popups during refresh; on macOS this can trigger
        # focus churn while operator clicks PFDS filter buttons.
        self._clear_dynamic_layout(self.live_pfds_grid)
        viewport_width = self.live_pfds_scroll.viewport().width() if hasattr(self, 'live_pfds_scroll') else 1200
        cols = self._responsive_card_columns(viewport_width, 320)
        first_main_card = None
        for c in range(max(1, cols)):
            self.live_pfds_grid.setColumnStretch(c, 1)

        merged_cards = []
        if current_filter in {'all', 'live'}:
            for device in online_devices:
                merged_cards.append(('live', device))
        if current_filter == 'all':
            for status in (offline_list or []):
                merged_cards.append(('offline', status))
        if current_filter in {'all', 'pending'}:
            for pending in pending_list:
                merged_cards.append(('pending', pending))

        for idx, payload in enumerate(merged_cards):
            row = idx // cols
            col = idx % cols
            kind, item = payload
            try:
                if kind == 'pending':
                    card = self._build_pending_identity_card(item)
                    if first_main_card is None:
                        first_main_card = card
                    print(f"  [PENDING_CARD] idx={idx} row={row} col={col} serial={item.get('serial_number')} visible={card.isVisible()}")
                    self.live_pfds_grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                elif kind == 'offline':
                    card = self._build_offline_device_card(item)
                    if first_main_card is None:
                        first_main_card = card
                    self.live_pfds_grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                else:
                    card = self._build_live_pfds_device_card(item)
                    if first_main_card is None:
                        first_main_card = card
                    self.live_pfds_grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            except Exception as e:
                print(f"  [CARD_RENDER_ERROR] {e}")
                err = QLabel(f"CARD RENDER ERROR: {e}")
                err.setStyleSheet('color: #ffb4b4; font-size: 11px; padding: 10px; border: 1px dashed #aa6666;')
                self.live_pfds_grid.addWidget(err, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        if not merged_cards:
            empty = QLabel('No live or offline PFDS devices available')
            empty.setStyleSheet('color: #9aa4af; font-size: 12px; padding: 20px;')
            self.live_pfds_grid.addWidget(empty, 0, 0)

        if hasattr(self, 'live_pfds_grid_host'):
            try:
                self.live_pfds_grid.activate()
                self.live_pfds_grid_host.update()
            except Exception:
                pass
            self.live_pfds_grid_host.adjustSize()

        first_pending_card = None
        if hasattr(self, 'live_pfds_pending_layout'):
            self._clear_dynamic_layout(self.live_pfds_pending_layout)
            if show_pending_sidebar:
                for info in pending_list:
                    card = self._build_pending_identity_card(info)
                    if first_pending_card is None:
                        first_pending_card = card
                    self.live_pfds_pending_layout.addWidget(card)
            if show_pending_sidebar and not pending_list:
                empty = QLabel('No pending or unmapped identities')
                empty.setStyleSheet('color: #9aa4af; font-size: 12px; padding: 8px 4px;')
                self.live_pfds_pending_layout.addWidget(empty)
            self.live_pfds_pending_layout.addStretch(1)

        if hasattr(self, 'live_pfds_pending_host'):
            try:
                self.live_pfds_pending_layout.activate()
                self.live_pfds_pending_host.update()
            except Exception:
                pass
            self.live_pfds_pending_host.adjustSize()

        def _restore_live_pfds_scroll_targets():
            if hasattr(self, 'live_pfds_scroll') and self.live_pfds_scroll is not None:
                try:
                    self.live_pfds_scroll.verticalScrollBar().setValue(0)
                except Exception:
                    pass
            if hasattr(self, 'live_pfds_pending_scroll') and self.live_pfds_pending_scroll is not None:
                try:
                    self.live_pfds_pending_scroll.verticalScrollBar().setValue(0)
                except Exception:
                    pass

        QTimer.singleShot(0, _restore_live_pfds_scroll_targets)
        QTimer.singleShot(50, _restore_live_pfds_scroll_targets)
        QTimer.singleShot(0, self._stabilize_live_pfds_surface)

        self._live_pfds_refresh_inflight = False

        if bool(getattr(self, '_live_pfds_refresh_pending', False)):
            self._live_pfds_refresh_pending = False
            QTimer.singleShot(0, self._refresh_live_pfds_tab)

    def _set_live_pfds_filter(self, filter_name: str):
        next_filter = str(filter_name or 'all').strip().lower()
        if next_filter not in {'all', 'live', 'pending'}:
            next_filter = 'all'
        if bool(getattr(self, '_live_pfds_transition_inflight', False)) or bool(getattr(self, '_live_pfds_refresh_inflight', False)):
            self._live_pfds_deferred_filter = next_filter
            return
        self._live_pfds_filter = next_filter
        self._sync_live_pfds_filter_buttons()
        self._refresh_live_pfds_tab()

    def _sync_live_pfds_filter_buttons(self):
        current = str(getattr(self, '_live_pfds_filter', 'all') or 'all').strip().lower()
        mapping = {
            'all': getattr(self, 'live_pfds_filter_all_btn', None),
            'live': getattr(self, 'live_pfds_filter_live_btn', None),
            'pending': getattr(self, 'live_pfds_filter_pending_btn', None),
        }
        for key, btn in mapping.items():
            if btn is not None:
                btn.setChecked(key == current)

    def _refresh_live_assets_tab(self):
        if not hasattr(self, 'live_assets_grid'):
            return
        asset_entries = self._collect_live_asset_entries()
        ready = sum(1 for entry in asset_entries if str(entry.get('state')) == 'active')
        if hasattr(self, 'live_assets_count_chip'):
            self.live_assets_count_chip.setText(f"ASSETS {len(asset_entries)}")
        if hasattr(self, 'live_assets_healthy_chip'):
            self.live_assets_healthy_chip.setText(f"READY {ready}")

        self._clear_dynamic_layout(self.live_assets_grid)
        viewport_width = self.live_assets_scroll.viewport().width() if hasattr(self, 'live_assets_scroll') else 1200
        cols = self._responsive_card_columns(viewport_width, 340)
        for c in range(max(1, cols)):
            self.live_assets_grid.setColumnStretch(c, 1)
        for idx, entry in enumerate(asset_entries):
            row = idx // cols
            col = idx % cols
            try:
                self.live_assets_grid.addWidget(self._build_live_asset_card(entry), row, col)
            except Exception as e:
                err = QLabel(f"CARD RENDER ERROR: {e}")
                err.setStyleSheet('color: #ffb4b4; font-size: 11px; padding: 10px; border: 1px dashed #aa6666;')
                self.live_assets_grid.addWidget(err, row, col)
        if not asset_entries:
            empty = QLabel('No configured assets available')
            empty.setStyleSheet('color: #9aa4af; font-size: 12px; padding: 20px;')
            self.live_assets_grid.addWidget(empty, 0, 0)

        if hasattr(self, 'live_assets_host'):
            self.live_assets_host.adjustSize()

    def _toggle_live_pfds_sidebar(self):
        if not hasattr(self, 'live_pfds_sidebar'):
            return
        if str(getattr(self, '_live_pfds_filter', 'all') or 'all').strip().lower() == 'pending':
            return
        expanded = bool(getattr(self, 'live_pfds_sidebar_expanded', True))
        end_width = 0 if expanded else int(getattr(self, '_live_pfds_sidebar_width', 340))
        self.live_pfds_sidebar_expanded = not expanded
        if hasattr(self, 'live_pfds_sidebar_toggle'):
            self.live_pfds_sidebar_toggle.setText('Hide Pending' if not expanded else 'Show Pending')
        # Apply sidebar width immediately (no animation) to avoid transition flicker.
        self.live_pfds_sidebar.setVisible(end_width > 0)
        self.live_pfds_sidebar.setMaximumWidth(end_width)
        self.live_pfds_sidebar.update()

    def _apply_live_pfds_sidebar_state(self, force_visible=None):
        if not hasattr(self, 'live_pfds_sidebar'):
            return

        # Stop any running sidebar animation so it cannot override the width we
        # are about to set directly.
        anim = getattr(self, '_live_pfds_sidebar_anim', None)
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass

        if force_visible is None:
            visible = bool(getattr(self, 'live_pfds_sidebar_expanded', True))
            toggle_enabled = True
        else:
            visible = bool(force_visible)
            toggle_enabled = False

        target_width = int(getattr(self, '_live_pfds_sidebar_width', 340)) if visible else 0
        self.live_pfds_sidebar.setVisible(visible)
        self.live_pfds_sidebar.setMaximumWidth(target_width)

        if hasattr(self, 'live_pfds_sidebar_toggle'):
            self.live_pfds_sidebar_toggle.setEnabled(toggle_enabled)
            if toggle_enabled:
                expanded = bool(getattr(self, 'live_pfds_sidebar_expanded', True))
                self.live_pfds_sidebar_toggle.setText('Hide Pending' if expanded else 'Show Pending')
            else:
                self.live_pfds_sidebar_toggle.setText('Show Pending')

    def _on_live_pfds_sidebar_anim_finished(self):
        if not hasattr(self, 'live_pfds_sidebar'):
            return
        if not bool(getattr(self, 'live_pfds_sidebar_expanded', True)):
            self.live_pfds_sidebar.setVisible(False)
        else:
            self.live_pfds_sidebar.setVisible(True)

    def _toggle_live_device_authorized(self, device_id, parent=None):
        if not self._ensure_operator_identity(parent or self, action='authorization toggle'):
            return
        device = self._get_emberhawk_device_by_id(device_id)
        if not device:
            QMessageBox.warning(parent or self, 'Device Missing', 'Selected device could not be found.')
            return
        try:
            self.emberhawk.set_device_access(
                int(device_id),
                is_authorized=not bool(device.get('is_authorized', True)),
                actor=self._operator_actor(),
                reason='toggle_authorized_card',
            )
            self._refresh_live_operations_views()
        except Exception as e:
            QMessageBox.critical(parent or self, 'Update Failed', f'Could not update authorization: {e}')

    def _toggle_live_device_linked(self, device_id, parent=None):
        if not self._ensure_operator_identity(parent or self, action='link toggle'):
            return
        device = self._get_emberhawk_device_by_id(device_id)
        if not device:
            QMessageBox.warning(parent or self, 'Device Missing', 'Selected device could not be found.')
            return
        try:
            self.emberhawk.set_device_access(
                int(device_id),
                is_linked=not bool(device.get('is_linked', True)),
                actor=self._operator_actor(),
                reason='toggle_linked_card',
            )
            self._refresh_live_operations_views()
        except Exception as e:
            QMessageBox.critical(parent or self, 'Update Failed', f'Could not update link state: {e}')

    def _set_live_device_location(self, device_id, parent=None):
        if not self._ensure_operator_identity(parent or self, action='updating location'):
            return
        loc_id, ok = self._run_live_pfds_modal(
            lambda: QInputDialog.getItem(parent or self, 'Set Location', 'Location Id', self._location_choices_for_live_devices(), 0, True)
        )
        if not ok:
            return
        loc_id = self._normalize_loc_key(loc_id)
        if not loc_id:
            QMessageBox.warning(parent or self, 'Missing Location', 'Location Id is required.')
            return
        try:
            self.emberhawk.update_device_location(int(device_id), loc_id)
            self._refresh_live_operations_views()
        except Exception as e:
            QMessageBox.critical(parent or self, 'Update Failed', f'Could not update location: {e}')

    def _set_live_device_poll_seconds(self, device_id, parent=None):
        if not self._ensure_operator_identity(parent or self, action='updating poll period'):
            return
        poll, ok = self._run_live_pfds_modal(
            lambda: QInputDialog.getInt(parent or self, 'Set Poll', 'Poll seconds', 10, 1, 3600)
        )
        if not ok:
            return
        try:
            self.emberhawk.update_device_poll_seconds(int(device_id), int(poll))
            self._refresh_live_operations_views()
        except Exception as e:
            QMessageBox.critical(parent or self, 'Update Failed', f'Could not update poll period: {e}')

    def _remove_live_device(self, device_id, parent=None):
        if not self._ensure_operator_identity(parent or self, action='removing PFDS device'):
            return
        reply = self._run_live_pfds_modal(
            lambda: QMessageBox.question(
                parent or self,
                'Remove Device',
                'Remove selected PFDS device from the active registry?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.emberhawk.remove_device(int(device_id))
            self._refresh_live_operations_views()
        except Exception as e:
            QMessageBox.critical(parent or self, 'Remove Failed', f'Could not remove device: {e}')

    def _assign_pending_identity_to_room_from_info(self, pending_info, parent=None):
        if not self._ensure_operator_identity(parent or self, action='assign pending identity'):
            return
        serial = self._normalize_serial_key((pending_info or {}).get('serial_number'))
        peer_ip = str((pending_info or {}).get('client_ip') or '').strip()
        if not serial:
            QMessageBox.warning(parent or self, 'Invalid Serial', 'Selected pending identity has no serial number.')
            return

        loc_id, ok = self._run_live_pfds_modal(
            lambda: QInputDialog.getItem(parent or self, 'Assign Room', 'Location Id', self._location_choices_for_live_devices(), 0, True)
        )
        if not ok:
            return
        loc_id = self._normalize_loc_key(loc_id)
        if not loc_id:
            QMessageBox.warning(parent or self, 'Missing Location', 'Location Id is required.')
            return

        existing = self.emberhawk.get_device_by_serial(serial)
        try:
            if existing:
                did = int(existing.get('id'))
                self.emberhawk.update_device_location(did, loc_id)
                self.emberhawk.set_device_access(
                    did,
                    is_authorized=True,
                    is_linked=True,
                    actor=self._operator_actor(),
                    reason='assign_pending_identity_existing_card',
                )
                self.emberhawk.touch_device_seen(serial, peer_ip or None)
            else:
                default_name = f'PFDS {serial}'
                name, ok_name = self._run_live_pfds_modal(
                    lambda: QInputDialog.getText(parent or self, 'Device Name', 'Name', text=default_name)
                )
                if not ok_name:
                    return
                name = str(name or '').strip() or default_name

                mode, ok_mode = self._run_live_pfds_modal(
                    lambda: QInputDialog.getItem(parent or self, 'Device Mode', 'Mode', ['Continuous', 'On Demand'], 0, False)
                )
                if not ok_mode:
                    return

                poll, ok_poll = self._run_live_pfds_modal(
                    lambda: QInputDialog.getInt(parent or self, 'Poll (seconds)', 'Poll seconds', 10, 1, 3600)
                )
                if not ok_poll:
                    return

                port_value = int(getattr(self, 'tcp_server_port', self.config.get('tcp_server_port', 5001)) or 5001)
                ip_host = peer_ip or '127.0.0.1'
                did = self.emberhawk.add_device(name, f'{ip_host}:{port_value}', loc_id, mode, int(poll))
                self.emberhawk.set_device_access(
                    did,
                    is_authorized=True,
                    is_linked=True,
                    actor=self._operator_actor(),
                    reason='assign_pending_identity_create_card',
                )
                self.emberhawk.bind_serial_to_device(did, serial, peer_ip or None)

            self._loc_by_serial[serial] = loc_id
            self._pending_device_by_serial.pop(serial, None)
            self._refresh_live_operations_views()
            info_box = QMessageBox(parent or self)
            info_box.setIcon(QMessageBox.Icon.Information)
            info_box.setWindowTitle('Assigned')
            info_box.setText(f'Serial {serial} assigned to {loc_id}.')
            self._style_tactical_dialog(info_box)
            self._exec_live_pfds_dialog(info_box)
        except Exception as e:
            QMessageBox.critical(parent or self, 'Assign Failed', f'Could not assign pending identity: {e}')

    def show_pfds_view_dialog(self):
        """View configured live PFDS devices and pending serial identities."""
        from PyQt6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QTableWidget,
            QTableWidgetItem,
            QHBoxLayout,
            QPushButton,
            QMessageBox,
            QLabel,
            QInputDialog,
        )
        from datetime import datetime

        dlg = QDialog(self)
        dlg.setWindowTitle("Live PFDS Devices")
        self._style_tactical_dialog(dlg)
        layout = QVBoxLayout(dlg)

        table = QTableWidget(0, 12)
        table.setHorizontalHeaderLabels([
            "ID", "Name", "IP", "Location Id", "Serial", "Authorized", "Linked",
            "State", "Mode", "Poll (s)", "Last Seen IP", "Last Seen At"
        ])
        layout.addWidget(table)

        layout.addWidget(QLabel("Pending Identities (serial seen but not linked or not mapped to location)", dlg))
        pending_table = QTableWidget(0, 4)
        pending_table.setHorizontalHeaderLabels(["Serial", "Client IP", "Last Seen", "State"])
        layout.addWidget(pending_table)

        def load_rows():
            table.setRowCount(0)
            pending_table.setRowCount(0)
            try:
                devices = self.emberhawk.list_devices()
                now_ts = time.time()
                for d in devices:
                    row = table.rowCount()
                    table.insertRow(row)
                    state = self._get_device_lifecycle_state(d, now_ts=now_ts)
                    vals = [
                        d['id'],
                        d['name'],
                        d['ip'],
                        d.get('location_id') or '',
                        d.get('serial_number') or '',
                        'Yes' if d.get('is_authorized', True) else 'No',
                        'Yes' if d.get('is_linked', True) else 'No',
                        state,
                        d['mode'],
                        d['poll_seconds'],
                        d.get('last_seen_ip') or '',
                        d.get('last_seen_at') or '',
                    ]
                    for c, val in enumerate(vals):
                        table.setItem(row, c, QTableWidgetItem(str(val)))

                pending = dict(self._pending_device_by_serial)
                if bool(getattr(self, '_pending_from_telemetry_enabled', False)):
                    for serial, info in self._pending_from_recent_telemetry(now_ts=now_ts).items():
                        pending.setdefault(serial, info)
                for d in devices:
                    serial = self._normalize_serial_key(d.get('serial_number'))
                    if not serial or serial in pending:
                        continue
                    missing_location = not self._normalize_loc_key(d.get('location_id'))
                    not_linked = not bool(d.get('is_linked', True))
                    not_authorized = not bool(d.get('is_authorized', True))
                    if missing_location or not_linked or not_authorized:
                        if missing_location:
                            pending_state = 'pending_location'
                        elif not_linked:
                            pending_state = 'unlinked'
                        else:
                            pending_state = 'unauthorized'
                        pending[serial] = {
                            'serial_number': serial,
                            'client_ip': d.get('last_seen_ip') or '',
                            'last_seen': d.get('last_seen_at') or '',
                            'state': pending_state,
                            'device_id': d.get('id'),
                        }

                pending = self._exclude_active_serials_from_pending(pending, devices, now_ts=now_ts)

                for serial, info in sorted(pending.items(), key=lambda kv: kv[0]):
                    prow = pending_table.rowCount()
                    pending_table.insertRow(prow)
                    ts = info.get('last_seen')
                    ts_text = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if isinstance(ts, (int, float)) else ''
                    state = self._get_pending_identity_state(info, now_ts=now_ts)
                    pending_table.setItem(prow, 0, QTableWidgetItem(str(serial)))
                    pending_table.setItem(prow, 1, QTableWidgetItem(str(info.get('client_ip') or '')))
                    pending_table.setItem(prow, 2, QTableWidgetItem(ts_text))
                    pending_table.setItem(prow, 3, QTableWidgetItem(state))
                self._refresh_live_operations_views()
            except Exception as e:
                QMessageBox.critical(dlg, "Load Failed", f"Could not load devices: {e}")

        load_rows()

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        bind_btn = QPushButton("Bind Serial")
        assign_pending_btn = QPushButton("Assign Room")
        bulk_reconcile_btn = QPushButton("Bulk Reconcile")
        set_loc_btn = QPushButton("Set Location")

        more_btn = QToolButton()
        more_btn.setText("More")
        more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(more_btn)
        self._style_tactical_settings_menu(more_menu)
        dry_run_action = more_menu.addAction("Dry Run Pending")
        export_report_action = more_menu.addAction("Export Reconcile Report")
        more_menu.addSeparator()
        auth_action = more_menu.addAction("Toggle Authorized")
        link_action = more_menu.addAction("Toggle Linked")
        set_poll_selected_action = more_menu.addAction("Set Poll (Selected)")
        set_poll_all_action = more_menu.addAction("Set Poll (All)")
        more_menu.addSeparator()
        remove_action = more_menu.addAction("Remove Selected")
        remove_all_action = more_menu.addAction("Remove All Devices")
        more_btn.setMenu(more_menu)

        close_btn = QPushButton("Close")
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(bind_btn)
        btn_row.addWidget(assign_pending_btn)
        btn_row.addWidget(bulk_reconcile_btn)
        btn_row.addWidget(set_loc_btn)
        btn_row.addWidget(more_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        last_reconcile_summary = {}

        refresh_btn.clicked.connect(load_rows)

        def _selected_device_id():
            row = table.currentRow()
            if row < 0:
                return None
            did_item = table.item(row, 0)
            if not did_item:
                return None
            try:
                return int(did_item.text())
            except Exception:
                return None

        def bind_pending_serial():
            if not self._ensure_operator_identity(dlg, action="binding pending serial"):
                return
            did = _selected_device_id()
            prow = pending_table.currentRow()
            if did is None or prow < 0:
                QMessageBox.information(dlg, "Selection Required", "Select one device and one pending serial row.")
                return
            serial_item = pending_table.item(prow, 0)
            ip_item = pending_table.item(prow, 1)
            if not serial_item:
                return
            serial = self._normalize_serial_key(serial_item.text())
            peer_ip = ip_item.text().strip() if ip_item else None
            try:
                self.emberhawk.bind_serial_to_device(did, serial, peer_ip)
                self._pending_device_by_serial.pop(serial, None)
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Bind Failed", f"Could not bind serial: {e}")

        def _location_choices():
            loc_ids = set()
            try:
                for g in self.config.get('groups', []):
                    streams = self.config.get('streams', {}).get(g, []) if isinstance(self.config.get('streams'), dict) else self.config.get('streams', [])
                    for s in streams:
                        lid = s.get('location_id') or s.get('loc_id') or s.get('name')
                        if lid:
                            loc_ids.add(str(lid).strip())
            except Exception:
                pass
            if not loc_ids:
                loc_ids.add('demo_room')
            return sorted(loc_ids)

        def assign_pending_to_room():
            if not self._ensure_operator_identity(dlg, action="assign pending identity"):
                return
            prow = pending_table.currentRow()
            if prow < 0:
                QMessageBox.information(dlg, "Selection Required", "Select one pending identity row.")
                return

            serial_item = pending_table.item(prow, 0)
            ip_item = pending_table.item(prow, 1)
            if not serial_item:
                return
            serial = self._normalize_serial_key(serial_item.text())
            peer_ip = ip_item.text().strip() if ip_item else ''
            if not serial:
                QMessageBox.warning(dlg, "Invalid Serial", "Selected pending row has no serial.")
                return

            loc_options = _location_choices()
            loc_id, ok = QInputDialog.getItem(dlg, "Assign Room", "Location Id", loc_options, 0, True)
            if not ok:
                return
            loc_id = self._normalize_loc_key(loc_id)
            if not loc_id:
                QMessageBox.warning(dlg, "Missing Location", "Location Id is required.")
                return

            existing = self.emberhawk.get_device_by_serial(serial)
            try:
                if existing:
                    did = int(existing.get('id'))
                    self.emberhawk.update_device_location(did, loc_id)
                    self.emberhawk.set_device_access(
                        did,
                        is_authorized=True,
                        is_linked=True,
                        actor=self._operator_actor(),
                        reason="assign_pending_to_room_existing",
                    )
                    self.emberhawk.touch_device_seen(serial, peer_ip or None)
                else:
                    default_name = f"PFDS {serial}"
                    name, ok_name = QInputDialog.getText(dlg, "Device Name", "Name", text=default_name)
                    if not ok_name:
                        return
                    name = str(name or '').strip() or default_name

                    mode, ok_mode = QInputDialog.getItem(dlg, "Device Mode", "Mode", ["Continuous", "On Demand"], 0, False)
                    if not ok_mode:
                        return

                    poll, ok_poll = QInputDialog.getInt(dlg, "Poll (seconds)", "Poll seconds", 10, 1, 3600)
                    if not ok_poll:
                        return

                    ip_host = peer_ip or '127.0.0.1'
                    ip_endpoint = f"{ip_host}:{int(self.tcp_server_port)}"
                    did = self.emberhawk.add_device(name, ip_endpoint, loc_id, mode, int(poll))
                    self.emberhawk.set_device_access(
                        did,
                        is_authorized=True,
                        is_linked=True,
                        actor=self._operator_actor(),
                        reason="assign_pending_to_room_create",
                    )
                    self.emberhawk.bind_serial_to_device(did, serial, peer_ip or None)

                self._loc_by_serial[serial] = loc_id
                self._pending_device_by_serial.pop(serial, None)
                load_rows()
                info_box = QMessageBox(dlg)
                info_box.setIcon(QMessageBox.Icon.Information)
                info_box.setWindowTitle("Assigned")
                info_box.setText(f"Serial {serial} assigned to {loc_id}.")
                self._style_tactical_dialog(info_box)
                info_box.exec()
            except Exception as e:
                QMessageBox.critical(dlg, "Assign Failed", f"Could not assign pending identity: {e}")

        def bulk_reconcile_pending():
            nonlocal last_reconcile_summary
            if not self._ensure_operator_identity(dlg, action="bulk reconcile"):
                return
            pending = dict(self._pending_device_by_serial)
            if not pending:
                QMessageBox.information(dlg, "No Pending", "No pending identities to reconcile.")
                return
            try:
                summary = self.emberhawk.bulk_reconcile_pending_serials(
                    pending,
                    auto_link=True,
                    actor=self._operator_actor(),
                )
                last_reconcile_summary = dict(summary)
                for serial in summary.get('bound_serials', []):
                    self._pending_device_by_serial.pop(serial, None)
                    self._emit_device_telemetry(
                        'bulk_reconcile_bound',
                        serial=serial,
                        state='active',
                    )
                for serial in summary.get('unmatched_serials', []):
                    self._emit_device_telemetry(
                        'bulk_reconcile_unmatched',
                        serial=serial,
                        state='pending_identity',
                        drop_reason='no_matching_device',
                    )

                attempted = int(summary.get('attempted', 0))
                bound = int(summary.get('bound', 0))
                already_bound = int(summary.get('already_bound', 0))
                unmatched = int(summary.get('unmatched', 0))
                errors = int(summary.get('errors', 0))
                message = (
                    f"Attempted: {attempted}\n"
                    f"Bound: {bound}\n"
                    f"Already Bound: {already_bound}\n"
                    f"Unmatched: {unmatched}\n"
                    f"Errors: {errors}"
                )
                QMessageBox.information(dlg, "Bulk Reconcile Complete", message)
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Bulk Reconcile Failed", f"Could not reconcile pending identities: {e}")

        def dry_run_reconcile_pending():
            nonlocal last_reconcile_summary
            if not self._ensure_operator_identity(dlg, action="reconcile dry-run"):
                return
            pending = dict(self._pending_device_by_serial)
            if not pending:
                QMessageBox.information(dlg, "No Pending", "No pending identities to preview.")
                return
            try:
                summary = self.emberhawk.bulk_reconcile_pending_serials(
                    pending,
                    auto_link=True,
                    actor=self._operator_actor(),
                    dry_run=True,
                )
                last_reconcile_summary = dict(summary)
                self._emit_device_telemetry(
                    'bulk_reconcile_preview',
                    state='pending_identity',
                    command='dry_run',
                    attempted=int(summary.get('attempted', 0)),
                    would_bind=int(summary.get('would_bind', 0)),
                    unmatched=int(summary.get('unmatched', 0)),
                    errors=int(summary.get('errors', 0)),
                )
                message = (
                    f"Dry Run Complete\n\n"
                    f"Attempted: {int(summary.get('attempted', 0))}\n"
                    f"Would Bind: {int(summary.get('would_bind', 0))}\n"
                    f"Already Bound: {int(summary.get('already_bound', 0))}\n"
                    f"Unmatched: {int(summary.get('unmatched', 0))}\n"
                    f"Errors: {int(summary.get('errors', 0))}"
                )
                QMessageBox.information(dlg, "Dry Run Reconcile", message)
            except Exception as e:
                QMessageBox.critical(dlg, "Dry Run Failed", f"Could not run dry reconciliation preview: {e}")

        def export_reconcile_report():
            summary = dict(last_reconcile_summary or {})
            rows = summary.get('report_rows') or []
            if not rows:
                QMessageBox.information(dlg, "No Report", "Run Dry Run or Bulk Reconcile first.")
                return
            default_name = f"reconcile_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            file_path, _ = QFileDialog.getSaveFileName(
                dlg,
                "Export Reconcile Report",
                f"{default_name}.json",
                "JSON Files (*.json);;CSV Files (*.csv)",
            )
            if not file_path:
                return
            try:
                if file_path.lower().endswith('.csv'):
                    import csv
                    columns = [
                        'serial',
                        'status',
                        'candidate_device_id',
                        'candidate_device_name',
                        'candidate_ip',
                        'client_ip',
                        'dry_run',
                        'error',
                    ]
                    with open(file_path, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=columns)
                        writer.writeheader()
                        for r in rows:
                            writer.writerow({k: r.get(k) for k in columns})
                else:
                    payload = {
                        'generated_at': datetime.utcnow().isoformat() + 'Z',
                        'summary': {
                            'dry_run': bool(summary.get('dry_run', False)),
                            'attempted': int(summary.get('attempted', 0)),
                            'bound': int(summary.get('bound', 0)),
                            'would_bind': int(summary.get('would_bind', 0)),
                            'already_bound': int(summary.get('already_bound', 0)),
                            'unmatched': int(summary.get('unmatched', 0)),
                            'errors': int(summary.get('errors', 0)),
                        },
                        'report_rows': rows,
                    }
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f, indent=2, sort_keys=True)
                QMessageBox.information(dlg, 'Export Complete', f'Report exported to:\n{file_path}')
            except Exception as e:
                QMessageBox.critical(dlg, 'Export Failed', f'Could not export report: {e}')

        def toggle_authorized():
            if not self._ensure_operator_identity(dlg, action="authorization toggle"):
                return
            row = table.currentRow()
            did = _selected_device_id()
            if did is None:
                QMessageBox.information(dlg, "No Selection", "Select a device row.")
                return
            current = (table.item(row, 5).text().strip().lower() == 'yes') if table.item(row, 5) else True
            try:
                self.emberhawk.set_device_access(
                    did,
                    is_authorized=not current,
                    actor=self._operator_actor(),
                    reason="toggle_authorized",
                )
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Update Failed", f"Could not update authorization: {e}")

        def toggle_linked():
            if not self._ensure_operator_identity(dlg, action="link toggle"):
                return
            row = table.currentRow()
            did = _selected_device_id()
            if did is None:
                QMessageBox.information(dlg, "No Selection", "Select a device row.")
                return
            current = (table.item(row, 6).text().strip().lower() == 'yes') if table.item(row, 6) else True
            try:
                self.emberhawk.set_device_access(
                    did,
                    is_linked=not current,
                    actor=self._operator_actor(),
                    reason="toggle_linked",
                )
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Update Failed", f"Could not update link status: {e}")

        def set_selected_location():
            if not self._ensure_operator_identity(dlg, action="updating location"):
                return
            did = _selected_device_id()
            if did is None:
                QMessageBox.information(dlg, "No Selection", "Select a device row.")
                return
            loc_options = _location_choices()
            loc_id, ok = QInputDialog.getItem(dlg, "Set Location", "Location Id", loc_options, 0, True)
            if not ok:
                return
            loc_id = self._normalize_loc_key(loc_id)
            if not loc_id:
                QMessageBox.warning(dlg, "Missing Location", "Location Id is required.")
                return
            try:
                self.emberhawk.update_device_location(did, loc_id)
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Update Failed", f"Could not update location: {e}")

        def set_poll_selected():
            if not self._ensure_operator_identity(dlg, action="updating poll period"):
                return
            did = _selected_device_id()
            if did is None:
                QMessageBox.information(dlg, "No Selection", "Select a device row.")
                return
            poll, ok = QInputDialog.getInt(dlg, "Set Poll (Selected)", "Poll seconds", 10, 1, 3600)
            if not ok:
                return
            try:
                self.emberhawk.update_device_poll_seconds(did, int(poll))
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Update Failed", f"Could not update poll: {e}")

        def set_poll_all():
            if not self._ensure_operator_identity(dlg, action="updating all poll periods"):
                return
            poll, ok = QInputDialog.getInt(dlg, "Set Poll (All)", "Poll seconds", 10, 1, 3600)
            if not ok:
                return
            try:
                updated = self.emberhawk.update_all_poll_seconds(int(poll))
                load_rows()
                QMessageBox.information(dlg, "Updated", f"Updated poll period for {updated} device(s).")
            except Exception as e:
                QMessageBox.critical(dlg, "Update Failed", f"Could not update poll for all devices: {e}")

        def remove_selected():
            if not self._ensure_operator_identity(dlg, action="removing PFDS device"):
                return
            did = _selected_device_id()
            if did is None:
                QMessageBox.information(dlg, "No Selection", "Select a device row to remove.")
                return
            try:
                self.emberhawk.remove_device(did)
                load_rows()
            except Exception as e:
                QMessageBox.critical(dlg, "Remove Failed", f"Could not remove device: {e}")

        def remove_all_devices():
            if not self._ensure_operator_identity(dlg, action="removing all PFDS devices"):
                return
            try:
                devices = list(self.emberhawk.list_devices())
            except Exception as e:
                QMessageBox.critical(dlg, "Load Failed", f"Could not load devices: {e}")
                return

            if not devices:
                QMessageBox.information(dlg, "No Devices", "No PFDS devices to remove.")
                return

            reply = QMessageBox.question(
                dlg,
                "Remove All Devices",
                f"Remove all {len(devices)} PFDS devices from registry?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            removed = 0
            failed = 0
            for d in devices:
                try:
                    self.emberhawk.remove_device(int(d.get('id')))
                    removed += 1
                except Exception:
                    failed += 1

            load_rows()
            if failed:
                QMessageBox.warning(
                    dlg,
                    "Remove All Complete",
                    f"Removed {removed} device(s), failed {failed}.",
                )
            else:
                QMessageBox.information(
                    dlg,
                    "Remove All Complete",
                    f"Removed all {removed} device(s).",
                )

        bind_btn.clicked.connect(bind_pending_serial)
        assign_pending_btn.clicked.connect(assign_pending_to_room)
        bulk_reconcile_btn.clicked.connect(bulk_reconcile_pending)
        set_loc_btn.clicked.connect(set_selected_location)
        dry_run_action.triggered.connect(dry_run_reconcile_pending)
        export_report_action.triggered.connect(export_reconcile_report)
        auth_action.triggered.connect(toggle_authorized)
        link_action.triggered.connect(toggle_linked)
        set_poll_selected_action.triggered.connect(set_poll_selected)
        set_poll_all_action.triggered.connect(set_poll_all)
        remove_action.triggered.connect(remove_selected)
        remove_all_action.triggered.connect(remove_all_devices)
        close_btn.clicked.connect(dlg.accept)
        dlg.resize(1100, 650)
        self._exec_live_pfds_dialog(dlg)

    def show_log_viewer_dialog(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QFileDialog, QLineEdit, QComboBox
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QTabWidget
        from embereye_base.utils.error_logger import get_error_logger
        dlg = QDialog(self)
        dlg.setWindowTitle("Log Viewer")
        self._style_tactical_dialog(dlg)
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
                from PyQt6.QtWidgets import QApplication
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
        from PyQt6.QtWidgets import QTextEdit, QLabel
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
        from embereye_base.utils.tcp_logger import DEBUG_LOG, ERROR_LOG
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
        dlg.exec()

    def show_ip_loc_mappings_dialog(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

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
            from PyQt6.QtWidgets import QInputDialog
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
        dlg.exec()

    def import_deployment_model(self):
        """Import a trained model from Studio for deployment in Field app."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog, QProgressDialog
        from PyQt6.QtCore import Qt
        from pathlib import Path
        import shutil
        
        # Create import dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Import Deployment Model")
        dlg.setModal(True)
        dlg.resize(600, 250)
        self._style_tactical_dialog(dlg)
        
        layout = QVBoxLayout(dlg)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Import Model from EmberEye Studio")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e7c75f;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel(
            "Select a trained model exported from Studio to use for real-time detection.\n"
            "After import, you can choose whether to activate it immediately for all video streams."
        )
        desc.setStyleSheet("color: rgba(200,175,90,0.72); margin-bottom: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Model file selection
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Model File:"))
        self._import_model_path_label = QLabel("No file selected")
        self._import_model_path_label.setStyleSheet("color: rgba(200,175,90,0.55); font-style: italic;")
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
            "background-color: rgba(20, 29, 42, 0.9); "
            "border: 1px solid rgba(213, 171, 45, 0.4); "
            "border-radius: 4px; "
            "padding: 10px; "
            "color: rgba(200,175,90,0.75); "
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
            "background-color: #e2b83a; color: #0f1722; "
            "padding: 8px 20px; font-weight: bold; border-radius: 4px;"
        )
        import_btn.clicked.connect(lambda: self._execute_model_import(dlg))
        button_layout.addWidget(import_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        dlg.exec()
    
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
            self._import_model_path_label.setStyleSheet("color: #e7c75f; font-weight: bold;")
            
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
        from PyQt6.QtWidgets import QProgressDialog, QMessageBox
        from PyQt6.QtCore import Qt
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
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Importing Model")
        progress.show()
        QApplication.processEvents()
        
        try:
            from embereye_base.core.model_versioning import ModelVersionManager, ModelMetadata
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
                from embereye_base.core.class_config import load_master_classes, get_classes_hash, get_leaf_classes
                
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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if activate_now == QMessageBox.StandardButton.Yes:
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
            from embereye_base.core.detection_worker import stop_detection_worker

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
            from embereye_base.core.model_versioning import ModelVersionManager
            from PyQt6.QtWidgets import QFileDialog, QProgressDialog
            from PyQt6.QtCore import Qt
            
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
            progress.setWindowModality(Qt.WindowModality.WindowModal)
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
        from embereye_base.utils.tcp_logger import log_raw_packet, log_error_packet

        def _extract_host(value: str | None) -> str:
            raw = str(value or '').strip()
            if not raw:
                return ''
            if '://' in raw:
                raw = raw.split('://', 1)[1]
            raw = raw.split('/', 1)[0].strip()
            if ':' in raw:
                raw = raw.split(':', 1)[0].strip()
            return raw

        serial_number = str(cmd.get('serial_number') or '').strip()
        fallback_host = _extract_host(cmd.get('ip') or cmd.get('device_ip') or cmd.get('host'))
        loc = cmd.get('location_id') or ''
        name = cmd.get('name') or ''
        command = cmd.get('command')
        if not command:
            return False

        if not serial_number:
            self._emit_device_telemetry(
                'command_failed',
                command=command,
                location_id=loc,
                device_name=name,
                state='pending_identity',
                drop_reason='missing_serial',
            )
            log_error_packet(loc, f"PFDS_CMD_FAIL {command} ({name}) | missing serial_number")
            return False
        
        # Send command through existing TCP server connection
        if self.tcp_sensor_server and hasattr(self.tcp_sensor_server, 'send_command_to_client'):
            success = self.tcp_sensor_server.send_command_to_client(serial_number, command)
            route = f"serial={serial_number}"
            if not success and fallback_host:
                success = self.tcp_sensor_server.send_command_to_client(fallback_host, command)
                if success:
                    route = f"ip_fallback={fallback_host}"

            if success:
                self._emit_device_telemetry(
                    'command_sent',
                    command=command,
                    serial=serial_number,
                    location_id=loc,
                    device_name=name,
                )
                log_raw_packet(loc, f"PFDS_CMD {command} to {route} ({name}) | sent via active connection")
                return True
            else:
                self._emit_device_telemetry(
                    'command_failed',
                    command=command,
                    serial=serial_number,
                    location_id=loc,
                    device_name=name,
                    drop_reason='no_active_connection',
                )
                log_error_packet(loc, f"PFDS_CMD_FAIL {command} to serial={serial_number} ({name}) | no active connection")
                return False
        else:
            self._emit_device_telemetry(
                'command_failed',
                command=command,
                serial=serial_number,
                location_id=loc,
                device_name=name,
                drop_reason='tcp_server_unavailable',
            )
            log_error_packet(loc, f"PFDS_CMD_FAIL {command} to serial={serial_number} ({name}) | TCP server not available")
            return False

    def dispatch_emberhawk_command(self, cmd: dict) -> bool:
        """Dispatch EmberHawk device commands via PFDS command interface.
        Called by EmberHawk manager to send PERIOD_ON, PERIOD_OFF, EEPROM1, REQUEST1, etc.
        
        Args:
            cmd: Command dict with keys: command, ip, name, location_id, device_id, etc.
        
        Returns:
            bool: True if command was sent successfully
        """
        def _extract_host(value: str | None) -> str:
            raw = str(value or '').strip()
            if not raw:
                return ''
            if '://' in raw:
                raw = raw.split('://', 1)[1]
            raw = raw.split('/', 1)[0].strip()
            if ':' in raw:
                raw = raw.split(':', 1)[0].strip()
            return raw

        try:
            command = cmd.get('command')
            serial_number = str(cmd.get('serial_number') or '').strip()
            fallback_host = _extract_host(cmd.get('ip') or cmd.get('device_ip') or cmd.get('host'))
            
            if not command or not serial_number:
                print(f"❌ dispatch_emberhawk_command: missing command={command} or serial_number")
                self._emit_device_telemetry(
                    'command_failed',
                    command=command,
                    serial=serial_number or None,
                    location_id=cmd.get('location_id'),
                    drop_reason='missing_command_or_serial',
                )
                return False
            
            # Map EmberHawk commands to PFDS format
            # PFDS expects raw command strings like "PERIOD_ON", "EEPROM1", "REQUEST1", "PERIOD_OFF"
            if self.tcp_sensor_server and hasattr(self.tcp_sensor_server, 'send_command_to_client'):
                success = self.tcp_sensor_server.send_command_to_client(serial_number, command)
                if not success and fallback_host:
                    success = self.tcp_sensor_server.send_command_to_client(fallback_host, command)
                
                if success:
                    print(f"✅ dispatch_emberhawk_command: '{command}' sent to serial={serial_number}")
                    self._emit_device_telemetry(
                        'command_sent',
                        command=command,
                        serial=serial_number,
                        location_id=cmd.get('location_id'),
                        device_id=cmd.get('device_id'),
                    )
                    return True
                else:
                    now = time.time()
                    if not hasattr(self, '_dispatch_no_conn_warn_ts'):
                        self._dispatch_no_conn_warn_ts = {}
                    warn_key = f"{serial_number}|{command}"
                    last_warn = float(self._dispatch_no_conn_warn_ts.get(warn_key, 0.0))
                    if now - last_warn >= 30.0:
                        # Keep telemetry, but avoid repeated console noise during reconnect windows.
                        self._dispatch_no_conn_warn_ts[warn_key] = now
                    self._emit_device_telemetry(
                        'command_failed',
                        command=command,
                        serial=serial_number,
                        location_id=cmd.get('location_id'),
                        device_id=cmd.get('device_id'),
                        drop_reason='no_active_connection',
                    )
                    return False
            else:
                now = time.time()
                if not hasattr(self, '_dispatch_tcp_unavailable_warn_ts'):
                    self._dispatch_tcp_unavailable_warn_ts = {}
                warn_key = f"{serial_number}|{command}"
                last_warn = float(self._dispatch_tcp_unavailable_warn_ts.get(warn_key, 0.0))
                if now - last_warn >= 30.0:
                    # Keep telemetry, but avoid repeated console noise during startup when TCP is down.
                    self._dispatch_tcp_unavailable_warn_ts[warn_key] = now
                self._emit_device_telemetry(
                    'command_failed',
                    command=command,
                    serial=serial_number,
                    location_id=cmd.get('location_id'),
                    device_id=cmd.get('device_id'),
                    drop_reason='tcp_server_unavailable',
                )
                return False
                
        except Exception as e:
            print(f"❌ dispatch_emberhawk_command exception: {e}")
            self._emit_device_telemetry(
                'command_failed',
                command=cmd.get('command') if isinstance(cmd, dict) else None,
                serial=str(cmd.get('serial_number') or '').strip() if isinstance(cmd, dict) else None,
                location_id=cmd.get('location_id') if isinstance(cmd, dict) else None,
                drop_reason='dispatch_exception',
                error=str(e),
            )
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
        from embereye_base.utils.error_logger import get_error_logger
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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
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
                self.active_analytics_category = self._normalize_analytics_category(self.config.get('active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
                self._load_analytics_banner_preferences()
                self._reload_rule_engine_for_active_category()
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
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        is_modern = app.property("theme") == "modern" if app and self.theme_manager else False
        
        rtsp_tab = QWidget()
        if is_modern:
            rtsp_tab.setStyleSheet("background: #0f1820;")
        layout = QVBoxLayout(rtsp_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        command_frame = QFrame()
        command_frame.setObjectName("VideoWallCommandFrame")
        command_frame.setStyleSheet("""
            QFrame#VideoWallCommandFrame {
                background-color: #11171d;
                border-bottom: 1px solid #38444f;
            }
            QLabel#VideoWallHeadline {
                color: #ffdc00;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLabel#VideoWallSubline {
                color: #8e98a4;
                font-size: 11px;
            }
            QLabel#VideoWallChip {
                color: #d8dde4;
                background-color: #1a222a;
                border: 1px solid #495563;
                border-radius: 3px;
                padding: 5px 10px;
                font-family: "Roboto Mono", "Menlo", "Consolas", monospace;
                font-size: 11px;
                font-weight: 700;
            }
        """)
        command_layout = QHBoxLayout(command_frame)
        command_layout.setContentsMargins(16, 10, 16, 10)
        command_layout.setSpacing(10)

        command_copy = QVBoxLayout()
        self.videowall_headline = QLabel("VIDEOWALL > TACTICAL OVERWATCH")
        self.videowall_headline.setObjectName("VideoWallHeadline")
        self.videowall_subline = QLabel("Awaiting active feed map")
        self.videowall_subline.setObjectName("VideoWallSubline")
        command_copy.addWidget(self.videowall_headline)
        command_copy.addWidget(self.videowall_subline)
        command_layout.addLayout(command_copy)
        command_layout.addStretch(1)

        self.videowall_group_chip = QLabel("GROUP --")
        self.videowall_group_chip.setObjectName("VideoWallChip")
        command_layout.addWidget(self.videowall_group_chip)

        self.videowall_feed_chip = QLabel("FEEDS 0")
        self.videowall_feed_chip.setObjectName("VideoWallChip")
        command_layout.addWidget(self.videowall_feed_chip)

        self.videowall_page_chip = QLabel("PAGE 0/0")
        self.videowall_page_chip.setObjectName("VideoWallChip")
        command_layout.addWidget(self.videowall_page_chip)

        layout.addWidget(command_frame)
        
        # Container with position: relative for absolute positioning of nav buttons
        grid_container = QWidget()
        grid_container.setObjectName("gridContainer")
        self.rtsp_grid_container = grid_container  # stored for flash-free max/min
        if is_modern:
            grid_container.setStyleSheet("""
                #gridContainer {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #0c141b, stop:0.65 #0b1116, stop:1 #091016);
                    border-top: 1px solid #1e323f;
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
        self.prev_rtsp.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_modern:
            self.prev_rtsp.setStyleSheet("""
                QPushButton {
                    background-color: rgba(11, 21, 29, 0.92);
                    border: 1px solid #3f6a82;
                    border-radius: 25px;
                    color: #7fd6e6;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(26, 44, 57, 0.95);
                    border-color: #66b4c8;
                }
                QPushButton:pressed {
                    background-color: rgba(41, 64, 79, 0.95);
                }
            """)
        # Position at left edge, centered vertically
        self.prev_rtsp.move(10, grid_container.height() // 2 - 25)
        
        # Right edge - Next button
        self.next_rtsp = QPushButton("▶", grid_container)
        self.next_rtsp.clicked.connect(self.next_rtsp_page)
        self.next_rtsp.setFixedSize(50, 50)
        self.next_rtsp.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_modern:
            self.next_rtsp.setStyleSheet("""
                QPushButton {
                    background-color: rgba(11, 21, 29, 0.92);
                    border: 1px solid #3f6a82;
                    border-radius: 25px;
                    color: #7fd6e6;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(26, 44, 57, 0.95);
                    border-color: #66b4c8;
                }
                QPushButton:pressed {
                    background-color: rgba(41, 64, 79, 0.95);
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
        has_webengine = bool(HAS_WEBENGINE)
        self._grafana_has_webengine = has_webengine
        self._grafana_external_fallback_triggered = False
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
        self.grafana_open_btn = None
        
        # Web view for Grafana (only if WebEngine is available)
        if has_webengine:
            try:
                self.grafana_webview = QWebEngineView()
                self.grafana_webview.setMinimumHeight(600)
                self.grafana_webview.loadFinished.connect(self._on_grafana_webview_load_finished)
                # Load initial URL
                if grafana_url:
                    if self._grafana_url_reachable(grafana_url):
                        self._grafana_last_requested_url = grafana_url
                        self.grafana_webview.setUrl(QUrl(grafana_url))
                    else:
                        self._show_grafana_unavailable_view(grafana_url)
                layout.addWidget(self.grafana_webview)
                # Connect refresh button for embedded mode
                refresh_btn.clicked.connect(self.refresh_grafana_dashboard)
            except Exception as e:
                has_webengine = False
                self._grafana_has_webengine = False
        if not has_webengine:
            refresh_btn.setEnabled(False)

            # Route load action to browser when embedded WebEngine is unavailable.
            load_btn.setText("Open in Browser")
            load_btn.clicked.connect(self.open_grafana_in_browser)

            fallback_host = QWidget()
            fallback_host.setObjectName("grafanaFallbackHost")
            fallback_layout = QVBoxLayout(fallback_host)
            fallback_layout.setContentsMargins(0, 0, 0, 0)
            fallback_layout.setSpacing(0)

            fallback_layout.addStretch()

            card = QWidget()
            card.setObjectName("grafanaFallbackCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(28, 22, 28, 22)
            card_layout.setSpacing(10)

            title = QLabel("Grafana Embed Not Available")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("color: #a8dff0; font-size: 18px; font-weight: 700;")

            subtitle = QLabel(
                "This build does not include QWebEngine. You can still open the dashboard externally."
            )
            subtitle.setWordWrap(True)
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle.setStyleSheet("color: #8ea4b1; font-size: 12px;")

            steps = QLabel(
                "1. Start Grafana (default: http://localhost:3000)\n"
                "2. Configure Prometheus datasource (http://localhost:9090)\n"
                "3. Import dashboard from ADAPTIVE_FPS_METRICS_GUIDE.md"
            )
            steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
            steps.setStyleSheet("color: #7f95a1; font-size: 12px; line-height: 1.5;")

            actions = QHBoxLayout()
            actions.setContentsMargins(0, 4, 0, 0)
            actions.setSpacing(10)

            self.grafana_open_btn = QPushButton("Open Grafana")
            self.grafana_open_btn.clicked.connect(self.open_grafana_in_browser)

            copy_url_btn = QPushButton("Copy URL")
            copy_url_btn.clicked.connect(self.copy_grafana_url)

            actions.addStretch()
            actions.addWidget(self.grafana_open_btn)
            actions.addWidget(copy_url_btn)
            actions.addStretch()

            card_layout.addWidget(title)
            card_layout.addWidget(subtitle)
            card_layout.addWidget(steps)
            card_layout.addLayout(actions)

            card.setStyleSheet(
                "QWidget#grafanaFallbackCard {"
                "background: #121d25;"
                "border: 1px solid #2c4452;"
                "border-radius: 12px;"
                "}"
            )

            card.setMaximumWidth(760)
            fallback_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
            fallback_layout.addStretch()

            layout.addWidget(fallback_host)
        else:
            load_btn.clicked.connect(self.load_grafana_dashboard)
        
        self.tabs.addTab(grafana_tab, "📊 Metrics Dashboard")

    def show_observability_settings(self):
        """Edit observability settings separately from stream configuration."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Observability Settings")
        dialog.setMinimumWidth(420)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        enable_grafana_cb = QCheckBox("Enable Metrics Dashboard tab")
        enable_grafana_cb.setChecked(bool(self.config.get('enable_grafana', False)))

        grafana_url_input = QLineEdit()
        grafana_url_input.setText(str(self.config.get('grafana_url', 'http://localhost:3000')))
        grafana_url_input.setPlaceholderText("http://localhost:3000/d/emberye-metrics")

        metrics_port_input = QLineEdit()
        metrics_port_input.setText(str(self.config.get('metrics_port', 9090)))
        metrics_port_input.setPlaceholderText("9090")

        reduced_motion_cb = QCheckBox("Reduce motion (disable dashboard fade-in)")
        reduced_motion_cb.setChecked(bool(self.config.get('reduced_motion', False)))

        enable_grafana_cb.toggled.connect(grafana_url_input.setEnabled)
        grafana_url_input.setEnabled(enable_grafana_cb.isChecked())

        form.addRow("Dashboard", enable_grafana_cb)
        form.addRow("Grafana URL", grafana_url_input)
        form.addRow("Metrics Port", metrics_port_input)
        form.addRow("UI Motion", reduced_motion_cb)

        grafana_service_row = QWidget(dialog)
        service_layout = QHBoxLayout(grafana_service_row)
        service_layout.setContentsMargins(0, 0, 0, 0)
        service_layout.setSpacing(8)

        grafana_service_status = QLabel("Checking...")
        grafana_start_btn = QPushButton("Start Grafana")
        grafana_stop_btn = QPushButton("Stop Grafana")

        service_layout.addWidget(grafana_service_status, 1)
        service_layout.addWidget(grafana_start_btn)
        service_layout.addWidget(grafana_stop_btn)
        form.addRow("Grafana Service", grafana_service_row)
        layout.addLayout(form)

        def _effective_url():
            raw = (grafana_url_input.text() or '').strip() or 'http://localhost:3000'
            if not raw.startswith('http'):
                raw = 'http://' + raw
            return raw

        def _refresh_grafana_service_state():
            target = _effective_url()
            is_local = self._is_local_grafana_url(target)
            running = self._grafana_url_reachable(target)
            if running:
                grafana_service_status.setText("Running")
                grafana_service_status.setStyleSheet("color:#6fd6a7;font-weight:600;")
            else:
                grafana_service_status.setText("Stopped / Unreachable")
                grafana_service_status.setStyleSheet("color:#e6b36f;font-weight:600;")
            grafana_start_btn.setEnabled(is_local and not running)
            grafana_stop_btn.setEnabled(is_local and running)
            if not is_local:
                grafana_service_status.setText("Manual (non-local URL)")
                grafana_service_status.setStyleSheet("color:#8aa1ad;font-weight:600;")

        def _start_grafana():
            target = _effective_url()
            ok, message = self._start_local_grafana_service(target)
            if ok:
                self.statusBar().showMessage("Grafana start command completed", 3500)
            else:
                QMessageBox.warning(dialog, "Start Grafana", message)
            QTimer.singleShot(1200, _refresh_grafana_service_state)

        def _stop_grafana():
            target = _effective_url()
            ok, message = self._stop_local_grafana_service(target)
            if ok:
                self.statusBar().showMessage("Grafana stop command completed", 3500)
            else:
                QMessageBox.warning(dialog, "Stop Grafana", message)
            QTimer.singleShot(1200, _refresh_grafana_service_state)

        grafana_start_btn.clicked.connect(_start_grafana)
        grafana_stop_btn.clicked.connect(_stop_grafana)
        grafana_url_input.textChanged.connect(lambda _: _refresh_grafana_service_state())
        _refresh_grafana_service_state()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.config['enable_grafana'] = bool(enable_grafana_cb.isChecked())
        self.config['grafana_url'] = grafana_url_input.text().strip() or 'http://localhost:3000'
        self.config['reduced_motion'] = bool(reduced_motion_cb.isChecked())
        try:
            metrics_port = int(metrics_port_input.text().strip())
            if metrics_port < 1 or metrics_port > 65535:
                raise ValueError('out of range')
            self.config['metrics_port'] = metrics_port
        except Exception:
            QMessageBox.warning(self, "Invalid Metrics Port", "Metrics port must be between 1 and 65535.")
            return

        StreamConfig.save_config(self.config)
        self._set_grafana_tab_visibility(bool(self.config.get('enable_grafana', False)))
        self._animate_dashboard_entry()
        self.statusBar().showMessage("Observability settings updated", 4000)

    def _is_local_grafana_url(self, url):
        try:
            parsed = urlparse(str(url or ''))
            host = (parsed.hostname or '').strip().lower()
            return host in ('localhost', '127.0.0.1', '::1')
        except Exception:
            return False

    def _run_control_commands(self, commands):
        """Run first available control command and return execution status."""
        last_error = "No control command available"
        for cmd in commands:
            if not cmd:
                continue
            exe = cmd[0]
            if os.path.sep not in exe and shutil.which(exe) is None:
                continue
            try:
                completed = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                    timeout=45,
                    check=False,
                )
                if completed.returncode == 0:
                    return True, ""
                err = (completed.stderr or completed.stdout or '').strip()
                last_error = f"{' '.join(cmd)} failed: {err or 'exit code ' + str(completed.returncode)}"
            except Exception as exc:
                last_error = f"{' '.join(cmd)} failed: {exc}"
        return False, last_error

    def _start_local_grafana_service(self, url):
        if not self._is_local_grafana_url(url):
            return False, "Grafana service controls are available only for localhost URLs."
        if self._grafana_url_reachable(url):
            return True, "Grafana already running"

        if sys.platform == 'darwin':
            commands = [
                ['brew', 'services', 'start', 'grafana'],
                ['brew', 'services', 'start', 'grafana-full'],
            ]
        elif sys.platform.startswith('win'):
            commands = [
                ['powershell', '-NoProfile', '-Command', 'Start-Service -Name grafana'],
                ['sc', 'start', 'grafana'],
                ['sc', 'start', 'grafana-server'],
            ]
        else:
            commands = [
                ['systemctl', '--user', 'start', 'grafana-server'],
                ['systemctl', 'start', 'grafana-server'],
                ['service', 'grafana-server', 'start'],
            ]

        ok, msg = self._run_control_commands(commands)
        if not ok:
            if sys.platform == 'darwin' and ('not installed' in msg.lower() or 'no available formula' in msg.lower()):
                return False, (
                    "Grafana is not installed on this machine.\n"
                    "Install with: brew install grafana\n"
                    "Then click Start Grafana again."
                )
            return False, f"Could not start Grafana automatically.\n{msg}"

        for _ in range(8):
            if self._grafana_url_reachable(url):
                return True, "Grafana started"
            time.sleep(1)
        return False, "Start command ran, but Grafana is still unreachable."

    def _stop_local_grafana_service(self, url):
        if not self._is_local_grafana_url(url):
            return False, "Grafana service controls are available only for localhost URLs."
        if not self._grafana_url_reachable(url):
            return True, "Grafana already stopped"

        if sys.platform == 'darwin':
            commands = [
                ['brew', 'services', 'stop', 'grafana'],
                ['brew', 'services', 'stop', 'grafana-full'],
            ]
        elif sys.platform.startswith('win'):
            commands = [
                ['powershell', '-NoProfile', '-Command', 'Stop-Service -Name grafana'],
                ['sc', 'stop', 'grafana'],
                ['sc', 'stop', 'grafana-server'],
            ]
        else:
            commands = [
                ['systemctl', '--user', 'stop', 'grafana-server'],
                ['systemctl', 'stop', 'grafana-server'],
                ['service', 'grafana-server', 'stop'],
            ]

        ok, msg = self._run_control_commands(commands)
        if not ok:
            return False, f"Could not stop Grafana automatically.\n{msg}"

        for _ in range(8):
            if not self._grafana_url_reachable(url):
                return True, "Grafana stopped"
            time.sleep(1)
        return False, "Stop command ran, but Grafana endpoint is still reachable."

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
                if self._grafana_url_reachable(url):
                    self._grafana_external_fallback_triggered = False
                    self._grafana_last_requested_url = url
                    self.grafana_webview.setUrl(QUrl(url))
                    self.statusBar().showMessage(f"Loading Grafana dashboard: {url}", 3000)
                else:
                    self._show_grafana_unavailable_view(url)
                    self.statusBar().showMessage("Grafana is not reachable. Start Grafana and retry.", 4000)
            else:
                self.open_grafana_in_browser()
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load Grafana dashboard:\n{str(e)}")

    def refresh_grafana_dashboard(self):
        """Reload embedded dashboard with graceful unreachable handling."""
        try:
            if not hasattr(self, 'grafana_webview'):
                return
            url = self.grafana_url_input.text().strip() if hasattr(self, 'grafana_url_input') else ''
            if not url:
                url = str(self.config.get('grafana_url', 'http://localhost:3000'))
            if not url.startswith('http'):
                url = 'http://' + url
            if self._grafana_url_reachable(url):
                self._grafana_external_fallback_triggered = False
                self._grafana_last_requested_url = url
                self.grafana_webview.setUrl(QUrl(url))
            else:
                self._show_grafana_unavailable_view(url)
                self.statusBar().showMessage("Grafana is not reachable. Start Grafana and retry.", 3500)
        except Exception:
            pass

    def _on_grafana_webview_load_finished(self, ok):
        """Detect embedded runtime failures and auto-fallback to external browser."""
        if not hasattr(self, 'grafana_webview'):
            return

        current_url = ''
        try:
            current_url = self.grafana_webview.url().toString()
        except Exception:
            current_url = ''
        if not current_url:
            current_url = str(getattr(self, '_grafana_last_requested_url', '') or self.config.get('grafana_url', 'http://localhost:3000'))

        if not ok:
            self._handle_grafana_embed_runtime_failure(current_url, "Embedded page load failed.")
            return

        # Grafana may render an in-page failure screen even when HTTP load succeeds.
        def _inspect_loaded_page(text):
            lowered = str(text or '').lower()
            markers = (
                'failed to load its application files',
                'reverse proxy settings',
                'serve_from_sub_path',
            )
            if any(marker in lowered for marker in markers):
                self._handle_grafana_embed_runtime_failure(
                    current_url,
                    "Embedded browser is not compatible with this Grafana frontend build.",
                )

        try:
            self.grafana_webview.page().toPlainText(_inspect_loaded_page)
        except Exception:
            pass

    def _handle_grafana_embed_runtime_failure(self, url, detail):
        """Show a stable fallback view and open external browser once per load attempt."""
        self._show_grafana_unavailable_view(url, detail=detail)
        already_opened = bool(getattr(self, '_grafana_external_fallback_triggered', False))
        if already_opened:
            return
        self._grafana_external_fallback_triggered = True
        try:
            webbrowser.open(url)
            self.statusBar().showMessage("Grafana opened in browser due to embedded compatibility issue.", 5000)
        except Exception:
            pass

    def _grafana_url_reachable(self, url):
        """Best-effort reachability check before embedding URL."""
        try:
            target = str(url or '').strip()
            if not target:
                return False
            if not target.startswith('http'):
                target = 'http://' + target
            req = urllib.request.Request(target, method='GET')
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                code = int(getattr(resp, 'status', 200) or 200)
                return 200 <= code < 500
        except Exception:
            return False

    def _show_grafana_unavailable_view(self, attempted_url, detail=None):
        """Render a styled in-app placeholder when Grafana endpoint is down."""
        if not hasattr(self, 'grafana_webview'):
            return
        safe_url = str(attempted_url or 'http://localhost:3000').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        safe_detail = str(detail or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        detail_html = ""
        if safe_detail:
            detail_html = f"<div style=\"font-size:13px;color:#f0b37a;margin-bottom:10px;\">{safe_detail}</div>"
        html = f"""
        <html>
        <body style=\"margin:0;background:#0f1820;color:#d8e5ec;font-family:'Segoe UI','Avenir Next',sans-serif;\">
            <div style=\"height:100vh;display:flex;align-items:center;justify-content:center;\">
                <div style=\"width:min(760px,88vw);background:#121d25;border:1px solid #2c4452;border-radius:12px;padding:26px 30px;\">
                    <div style=\"font-size:24px;font-weight:700;color:#9adff0;margin-bottom:10px;\">Grafana Not Reachable</div>
                    <div style=\"font-size:14px;color:#9eb2bf;margin-bottom:12px;\">Could not connect to <b>{safe_url}</b>.</div>
                    {detail_html}
                    <div style=\"font-size:13px;color:#869ca9;line-height:1.6;\">
                        1. Start Grafana server.<br/>
                        2. Verify URL and port in Observability settings.<br/>
                        3. If this is a browser compatibility issue, use <b>Open Grafana</b>.
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        self.grafana_webview.setHtml(html, QUrl("about:blank"))

    def open_grafana_in_browser(self):
        """Open configured Grafana URL in external browser."""
        try:
            url = self.grafana_url_input.text().strip() if hasattr(self, 'grafana_url_input') else ''
            if not url:
                url = str(self.config.get('grafana_url', 'http://localhost:3000'))
            if not url.startswith('http'):
                url = 'http://' + url
            webbrowser.open(url)
            self.statusBar().showMessage(f"Opened Grafana in browser: {url}", 3500)
        except Exception as e:
            QMessageBox.critical(self, "Open Browser Failed", f"Could not open Grafana URL:\n{e}")

    def copy_grafana_url(self):
        """Copy configured Grafana URL to clipboard."""
        try:
            url = self.grafana_url_input.text().strip() if hasattr(self, 'grafana_url_input') else ''
            if not url:
                url = str(self.config.get('grafana_url', 'http://localhost:3000'))
            if not url.startswith('http'):
                url = 'http://' + url
            QApplication.clipboard().setText(url)
            self.statusBar().showMessage("Grafana URL copied", 2500)
        except Exception as e:
            QMessageBox.critical(self, "Copy Failed", f"Could not copy URL:\n{e}")

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

    def init_marketplace_tab(self):
        marketplace_tab = QWidget()
        layout = QVBoxLayout(marketplace_tab)

        self.analytics_cards_view = AnalyticsCardsView()
        self.analytics_cards_view.refresh_requested.connect(self._refresh_marketplace_analytics)
        self.analytics_cards_view.import_requested.connect(self._import_marketplace_analytics)
        layout.addWidget(self.analytics_cards_view)

        self.tabs.addTab(marketplace_tab, "ANALYTICS")

        self.marketplace_plugin_manager = PluginManager(self.marketplace_dir)
        self.marketplace_plugin_manager.analytic_added.connect(self._on_marketplace_descriptor_changed)
        self.marketplace_plugin_manager.analytic_removed.connect(self._on_marketplace_descriptor_changed)
        self.marketplace_plugin_manager.analytic_updated.connect(self._on_marketplace_descriptor_changed)
        self.marketplace_plugin_manager.scan_completed.connect(self._on_marketplace_scan_completed)

        self._refresh_marketplace_analytics()

    def _refresh_marketplace_analytics(self):
        if not self.marketplace_plugin_manager:
            return
        try:
            self.marketplace_plugin_manager.refresh()
        except Exception as exc:
            logger.exception("Marketplace scan failed: %s", exc)
            try:
                self.statusBar().showMessage(f"Marketplace scan failed: {exc}", 5000)
            except Exception:
                pass

    def _on_marketplace_descriptor_changed(self, _analytic_id):
        # Descriptor changes are reflected when scan_completed is emitted.
        return

    def _on_marketplace_scan_completed(self):
        if not self.marketplace_plugin_manager or not self.analytics_cards_view:
            return
        descriptors = self.marketplace_plugin_manager.descriptors()
        self.analytics_cards_view.set_descriptors(descriptors)
        try:
            self.statusBar().showMessage(
                f"Marketplace scan complete: {len(descriptors)} package(s)",
                2500,
            )
        except Exception:
            pass

    def _import_marketplace_analytics(self):
        source_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Import Analytics",
            str(Path.home()),
        )
        if not source_dir:
            return

        source_path = Path(source_dir)
        candidates = sorted(source_path.rglob("*.eapkg"))
        if not candidates:
            QMessageBox.information(
                self,
                "Import Analytics",
                "No .eapkg files found in the selected folder.",
            )
            return

        progress = QProgressDialog("Importing analytics packages...", "Cancel", 0, len(candidates), self)
        progress.setWindowTitle("Import Analytics")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        imported = 0
        failed = 0
        failures: list[str] = []

        self.marketplace_dir.mkdir(parents=True, exist_ok=True)

        for index, package_path in enumerate(candidates, start=1):
            if progress.wasCanceled():
                break

            progress.setValue(index - 1)
            progress.setLabelText(f"Validating {package_path.name} ({index}/{len(candidates)})")
            QApplication.processEvents()

            validation = validate_eapkg(package_path)
            if not validation.is_valid:
                failed += 1
                error_text = "; ".join(validation.errors) if validation.errors else "Unknown validation error"
                failures.append(f"{package_path.name}: {error_text}")
                continue

            destination = self.marketplace_dir / package_path.name
            destination = self._next_available_marketplace_path(destination)

            try:
                shutil.copy2(package_path, destination)
                imported += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{package_path.name}: copy failed ({exc})")

        progress.setValue(len(candidates))
        progress.close()

        self._refresh_marketplace_analytics()

        summary_lines = [
            f"Imported: {imported}",
            f"Failed: {failed}",
            f"Target folder: {self.marketplace_dir}",
        ]
        if progress.wasCanceled():
            summary_lines.append("Status: canceled by user")

        if failures:
            preview = "\n".join(failures[:8])
            if len(failures) > 8:
                preview += f"\n... and {len(failures) - 8} more"
            summary_lines.append("")
            summary_lines.append("Failure details:")
            summary_lines.append(preview)

        QMessageBox.information(self, "Import Analytics Summary", "\n".join(summary_lines))

    def _next_available_marketplace_path(self, base_path: Path) -> Path:
        if not base_path.exists():
            return base_path

        stem = base_path.stem
        suffix = base_path.suffix
        counter = 1
        while True:
            candidate = base_path.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def showEvent(self, event):
        """Start WebSocket client when window is shown"""
        super().showEvent(event)
        if self.ws_client and hasattr(self.ws_client, 'start'):
            self.ws_client.start()

    def mouseMoveEvent(self, event):
        """Handle mouse hover to show/hide overlay header in Modern mode."""
        try:
            # On LIVE PFDS tab: skip all X-ray/stabilize side-effects on mouse move.
            # Calling _stabilize_live_pfds_surface (show/raise overlay_header) on every
            # mouse move causes constant churn that can interfere with filter button
            # activation on macOS.  The surface is stabilized once on tab entry.
            if self._is_live_pfds_tab_active():
                super().mouseMoveEvent(event)
                return

            if hasattr(self, 'overlay_header') and self.overlay_header is not None:
                # Get cursor position relative to main window
                cursor_pos = event.position().toPoint()

                # Check if mouse is in header area (top 60px including header height)
                in_header_zone = cursor_pos.y() < 60

                if in_header_zone:
                    # Show header and cancel any hide timer
                    if not self.overlay_header.isVisible():
                        self.overlay_header.show()
                        self.overlay_header.raise_()

                    # Cancel hide timer if active
                    if hasattr(self, 'header_hide_timer') and self.header_hide_timer:
                        self.header_hide_timer.stop()
                        self.header_hide_timer = None
                        self.header_countdown_seconds = 0
                        if hasattr(self, 'header_countdown_label'):
                            self.header_countdown_label.hide()
                else:
                    # Mouse outside header zone - start timer if header is visible
                    if self.overlay_header.isVisible():
                        if not hasattr(self, 'header_hide_timer') or self.header_hide_timer is None:
                            from PyQt6.QtCore import QTimer
                            self.header_countdown_seconds = 5
                            self.header_hide_timer = QTimer(self)
                            self.header_hide_timer.timeout.connect(self._update_header_countdown)
                            self.header_hide_timer.start(1000)  # Update every second
                            if hasattr(self, 'header_countdown_label'):
                                self.header_countdown_label.setText(f"Hiding in {self.header_countdown_seconds}s")
                                self.header_countdown_label.show()
        except Exception as e:
            print(f"Mouse event error: {e}")

        super().mouseMoveEvent(event)

    def _update_header_countdown(self):
        """Update countdown timer and hide header when it reaches 0."""
        try:
            if self._is_live_pfds_tab_active():
                if hasattr(self, 'header_hide_timer') and self.header_hide_timer:
                    self.header_hide_timer.stop()
                    self.header_hide_timer = None
                if hasattr(self, 'header_countdown_label'):
                    self.header_countdown_label.hide()
                return

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
            else:
                # Update countdown display
                if hasattr(self, 'header_countdown_label'):
                    self.header_countdown_label.setText(f"Hiding in {self.header_countdown_seconds}s")
        except Exception as e:
            print(f"Countdown update error: {e}")
            pass

    def _stabilize_live_pfds_surface(self):
        """Disable X-ray timers/animations while LIVE PFDS is active to prevent repaint artifacts."""
        try:
            # Stop hide timers
            for timer_attr in ('status_hide_timer', 'header_hide_timer'):
                timer = getattr(self, timer_attr, None)
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception:
                        pass
                    setattr(self, timer_attr, None)

            if hasattr(self, 'header_countdown_label') and self.header_countdown_label is not None:
                self.header_countdown_label.hide()

            # Stop and clear X-ray fade animations/effects
            for slot_name, widget in (
                ('header', getattr(self, 'overlay_header', None)),
                ('status', self.statusBar() if hasattr(self, 'statusBar') else None),
            ):
                anim_attr = f"_xray_{slot_name}_fade_anim"
                effect_attr = f"_xray_{slot_name}_opacity_effect"

                anim = getattr(self, anim_attr, None)
                if anim is not None:
                    try:
                        anim.stop()
                    except Exception:
                        pass
                    setattr(self, anim_attr, None)

                effect = getattr(self, effect_attr, None)
                if widget is not None:
                    try:
                        if effect is not None and widget.graphicsEffect() is effect:
                            widget.setGraphicsEffect(None)
                    except Exception:
                        pass
                setattr(self, effect_attr, None)

            # Keep top/bottom bars visible in a stable state
            if hasattr(self, 'overlay_header') and self.overlay_header is not None:
                self.overlay_header.show()
                self.overlay_header.raise_()
                self.header_visible = True

            sb = self.statusBar() if hasattr(self, 'statusBar') else None
            if sb is not None:
                sb.show()
                self.statusbar_visible = True
        except Exception:
            pass

    
    # ==================== X-RAY EFFECT FEATURES ====================

    def _xray_fade_widget(self, widget, visible, slot_name, duration_ms=180):
        """Fade a widget in/out for smoother X-ray transitions."""
        try:
            if widget is None:
                return

            from PyQt6.QtWidgets import QGraphicsOpacityEffect
            from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

            effect_attr = f"_xray_{slot_name}_opacity_effect"
            anim_attr = f"_xray_{slot_name}_fade_anim"

            effect = getattr(self, effect_attr, None)
            if effect is None or widget.graphicsEffect() is not effect:
                effect = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(effect)
                effect.setOpacity(1.0 if widget.isVisible() else 0.0)
                setattr(self, effect_attr, effect)

            running = getattr(self, anim_attr, None)
            if running is not None:
                try:
                    running.stop()
                except Exception:
                    pass

            start = float(effect.opacity())
            end = 1.0 if visible else 0.0

            if visible:
                if not widget.isVisible():
                    widget.show()
                widget.raise_()

            if abs(start - end) < 0.01:
                if not visible:
                    widget.hide()
                return

            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(max(80, int(duration_ms)))
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

            def _finish():
                try:
                    if not visible:
                        widget.hide()
                except Exception:
                    pass

            anim.finished.connect(_finish)
            anim.start()
            setattr(self, anim_attr, anim)
        except Exception:
            # Fallback to instant behavior when animation setup fails.
            try:
                widget.setVisible(bool(visible))
            except Exception:
                pass

    def _show_header_xray(self):
        if hasattr(self, 'overlay_header') and self.overlay_header is not None:
            self._xray_fade_widget(self.overlay_header, True, 'header', 170)
            self.header_visible = True

    def _hide_header_xray(self):
        if hasattr(self, 'overlay_header') and self.overlay_header is not None:
            self._xray_fade_widget(self.overlay_header, False, 'header', 180)
            self.header_visible = False

    def _show_statusbar_xray(self):
        sb = self.statusBar() if hasattr(self, 'statusBar') else None
        if sb is not None:
            self._xray_fade_widget(sb, True, 'status', 170)
            self.statusbar_visible = True

    def _hide_statusbar_xray(self):
        sb = self.statusBar() if hasattr(self, 'statusBar') else None
        if sb is not None:
            self._xray_fade_widget(sb, False, 'status', 180)
            self.statusbar_visible = False

    def _is_live_pfds_tab_active(self):
        """Return True when the LIVE PFDS tab is currently selected."""
        try:
            if not hasattr(self, 'tabs') or self.tabs is None:
                return False
            idx = self.tabs.currentIndex()
            if idx < 0:
                return False
            return str(self.tabs.tabText(idx)).strip().upper() == 'LIVE PFDS'
        except Exception:
            return False
    
    def eventFilter(self, obj, event):
        """
        Global event filter for X-ray effect:
        - Tracks mouse movement to auto-show/hide header and status bar
        - Implements cursor auto-hide after inactivity
        """
        try:
            from PyQt6.QtCore import QEvent
            from PyQt6.QtGui import QCursor
            from PyQt6.QtWidgets import QApplication

            # LIVE PFDS: bypass all global X-ray/cursor side effects.
            # Re-running stabilization and cursor timer logic on every mouse move
            # causes repaint churn and focus glitches during filter interactions.
            if self._is_live_pfds_tab_active():
                return super().eventFilter(obj, event)

            if event.type() == QEvent.Type.MouseMove:
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
                        self._show_header_xray()
                    # Hide header if mouse moves away and not in maximized view
                    elif window_pos.y() > 150 and self.header_visible and self.maximized_widget is None:
                        self._hide_header_xray()
                
                # X-ray effect: Show status bar when mouse near bottom (also show header)
                # Skip toggling when cursor is over the status bar itself
                if not hovering_status_bar and hasattr(self, 'statusBar') and hasattr(self, 'statusbar_visible'):
                    from PyQt6.QtCore import QTimer
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
                            self._show_statusbar_xray()
                            # Also ensure header is visible when bottom bar shows
                            if hasattr(self, 'overlay_header') and hasattr(self, 'header_visible') and not self.header_visible:
                                self._show_header_xray()
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
            
            elif event.type() == QEvent.Type.KeyPress:
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
        """Keep cursor visible; hiding breaks tab/navigation usability."""
        self.unsetCursor()
        self.cursor_visible = True

    def _hide_status_bar(self):
        """Hide the status bar via debounced timer."""
        try:
            if hasattr(self, 'statusBar') and self.statusbar_visible:
                self._hide_statusbar_xray()
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
        if bool(getattr(self, '_cleanup_done', False)):
            return
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
                tcp_mode = self.config.get('tcp_mode', 'async')  # async is the default; threaded is DEPRECATED
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

        # Stop device alert monitor timer
        try:
            if hasattr(self, '_device_alert_timer') and self._device_alert_timer:
                self._device_alert_timer.stop()
                self._device_alert_timer = None
        except Exception as e:
            print(f"Device alert monitor cleanup error: {e}")

        # Stop scheduled reconcile timer
        try:
            if hasattr(self, '_reconcile_timer') and self._reconcile_timer:
                self._reconcile_timer.stop()
                self._reconcile_timer = None
        except Exception as e:
            print(f"Scheduled reconcile cleanup error: {e}")
        
        # Stop cursor hide timer
        try:
            if hasattr(self, 'cursor_hide_timer'):
                self.cursor_hide_timer.stop()
        except Exception as e:
            print(f"Cursor timer cleanup error: {e}")

        self._cleanup_done = True
        
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
        # Skip blocking duplicate cleanup when logout already handled async cleanup.
        if not bool(getattr(self, '_skip_close_cleanup', False)):
            try:
                self.cleanup_all_workers()
            except Exception as e:
                print(f"Comprehensive cleanup error: {e}")

        # Stop marketplace watcher so shutdown does not keep directory observers alive.
        try:
            if self.marketplace_plugin_manager is not None:
                watcher = getattr(self.marketplace_plugin_manager, 'watcher', None)
                if watcher is not None:
                    for directory in watcher.directories():
                        watcher.removePath(directory)
        except Exception as e:
            print(f"Marketplace watcher cleanup error: {e}")
        
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
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtWidgets import QSizePolicy
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
                no_streams_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

            if hasattr(self, 'videowall_subline'):
                self.videowall_subline.setText(f"Live camera matrix for {self.current_group} with real-time fusion overlays")
            if hasattr(self, 'videowall_group_chip'):
                self.videowall_group_chip.setText(f"GROUP {str(self.current_group).upper()}")
            if hasattr(self, 'videowall_feed_chip'):
                self.videowall_feed_chip.setText(f"FEEDS {total_streams}")
            if hasattr(self, 'videowall_page_chip'):
                self.videowall_page_chip.setText(f"PAGE {self.current_rtsp_page}/{total_pages}")

            for idx in range(start, end):
                stream = filtered_streams[idx]
                position = idx - start
                row = position // cols
                col = position % cols
                
                try:
                    video_widget = VideoWidget(stream["url"], stream['name'], stream['loc_id'])
                    try:
                        video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                    except Exception:
                        pass
                    # Preserve operator-selected per-tile display mode (loaded by VideoWidget).
                    self.video_widgets[stream['loc_id']] = video_widget
                    video_widget.setToolTip(f"{stream['name']}\n{stream['url']}")
                    
                    # Room/status labeling is rendered by the fusion overlay cards.

                    # Connect signals
                    # video_widget.maximize_requested.connect(self.handle_maximize)
                    # video_widget.minimize_requested.connect(self.handle_minimize)
                    video_widget.maximize_requested.connect(
                        self.handle_maximize, 
                        Qt.ConnectionType.QueuedConnection
                    )
                    video_widget.minimize_requested.connect(
                        self.handle_minimize, 
                        Qt.ConnectionType.QueuedConnection
                    )
                    if hasattr(video_widget, 'alarm_raise_requested'):
                        video_widget.alarm_raise_requested.connect(
                            self.handle_alarm_raise_from_widget,
                            Qt.ConnectionType.QueuedConnection,
                        )
                    if hasattr(video_widget, 'alarm_ack_requested'):
                        video_widget.alarm_ack_requested.connect(
                            self.handle_alarm_ack_from_widget,
                            Qt.ConnectionType.QueuedConnection,
                        )
                    # Update status
                    video_widget.update_fire_alarm(False)
                    video_widget.set_temperature(22.5)


                    self.rtsp_grid.addWidget(video_widget, row, col)
                except Exception as e:
                    error_label = QLabel(f"{stream['name']}\nError: {str(e)}")
                    error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

    def init_live_pfds_tab(self):
        """Create tactical live PFDS device tab with collapsible pending sidebar."""
        live_tab = QWidget()
        live_tab.setStyleSheet("background-color: #0d1319;")
        root = QVBoxLayout(live_tab)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("LiveSurfaceHeader")
        header.setStyleSheet("""
            QFrame#LiveSurfaceHeader {
                background-color: #141a22;
                border: 1px solid #45505d;
                border-radius: 4px;
            }
            QLabel#LiveSurfaceTitle {
                color: #ffdc00;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLabel#LiveSurfaceSubline {
                color: #96a1ad;
                font-size: 11px;
            }
            QLabel#LiveSurfaceLegend {
                color: #8f99a5;
                font-size: 10px;
                font-family: "Roboto Mono", "Menlo", "Consolas", monospace;
            }
            QPushButton#LiveSurfaceFilter {
                color: #d5dbe3;
                background-color: #1a222a;
                border: 1px solid #4b5664;
                border-radius: 3px;
                padding: 6px 10px;
                font-family: "Roboto Mono", "Menlo", "Consolas", monospace;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#LiveSurfaceFilter:hover {
                border-color: #ffdc00;
                color: #ffdc00;
            }
            QPushButton#LiveSurfaceFilter:checked {
                background-color: #26333f;
                border-color: #ffdc00;
                color: #ffdc00;
            }
            QPushButton {
                background-color: #27313b;
                color: #edf1f5;
                border: 1px solid #566273;
                border-radius: 3px;
                padding: 7px 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                border-color: #ffdc00;
                color: #ffdc00;
            }
            QPushButton#LivePrimaryButton {
                background-color: #ffdc00;
                color: #171b21;
                border-color: #d4b200;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(8)

        copy_col = QVBoxLayout()
        title = QLabel("LIVE PFDS DEVICES")
        title.setObjectName("LiveSurfaceTitle")
        subtitle = QLabel("Merged operational view for live, offline, and pending PFDS identities")
        subtitle.setObjectName("LiveSurfaceSubline")
        legend = QLabel("Legend: LIVE=solid yellow | OFFLINE=red tone | PENDING=dashed")
        legend.setObjectName("LiveSurfaceLegend")
        copy_col.addWidget(title)
        copy_col.addWidget(subtitle)
        copy_col.addWidget(legend)
        header_layout.addLayout(copy_col)
        header_layout.addStretch(1)

        self._live_pfds_filter = 'all'

        self.live_pfds_filter_all_btn = QPushButton("ALL 0")
        self.live_pfds_filter_all_btn.setObjectName("LiveSurfaceFilter")
        self.live_pfds_filter_all_btn.setCheckable(True)
        self.live_pfds_filter_all_btn.clicked.connect(lambda _=False: self._set_live_pfds_filter('all'))
        header_layout.addWidget(self.live_pfds_filter_all_btn)

        self.live_pfds_filter_live_btn = QPushButton("LIVE 0")
        self.live_pfds_filter_live_btn.setObjectName("LiveSurfaceFilter")
        self.live_pfds_filter_live_btn.setCheckable(True)
        self.live_pfds_filter_live_btn.clicked.connect(lambda _=False: self._set_live_pfds_filter('live'))
        header_layout.addWidget(self.live_pfds_filter_live_btn)

        self.live_pfds_filter_pending_btn = QPushButton("PENDING 0")
        self.live_pfds_filter_pending_btn.setObjectName("LiveSurfaceFilter")
        self.live_pfds_filter_pending_btn.setCheckable(True)
        self.live_pfds_filter_pending_btn.clicked.connect(lambda _=False: self._set_live_pfds_filter('pending'))
        header_layout.addWidget(self.live_pfds_filter_pending_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_live_operations_views)
        header_layout.addWidget(refresh_btn)

        add_btn = QPushButton("Add Device")
        add_btn.setObjectName("LivePrimaryButton")
        add_btn.clicked.connect(self.show_pfds_add_dialog)
        header_layout.addWidget(add_btn)

        self.live_pfds_sidebar_toggle = QPushButton("Hide Pending")
        self.live_pfds_sidebar_toggle.clicked.connect(self._toggle_live_pfds_sidebar)
        header_layout.addWidget(self.live_pfds_sidebar_toggle)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.live_pfds_scroll = QScrollArea()
        self.live_pfds_scroll.setWidgetResizable(True)
        self.live_pfds_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.live_pfds_grid_host = QWidget()
        self.live_pfds_grid = QGridLayout(self.live_pfds_grid_host)
        self.live_pfds_grid.setContentsMargins(0, 0, 0, 0)
        self.live_pfds_grid.setHorizontalSpacing(12)
        self.live_pfds_grid.setVerticalSpacing(12)
        self.live_pfds_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.live_pfds_grid_host.setLayout(self.live_pfds_grid)
        self.live_pfds_scroll.setWidget(self.live_pfds_grid_host)
        body.addWidget(self.live_pfds_scroll, 1)

        self.live_pfds_sidebar = QFrame()
        self.live_pfds_sidebar.setObjectName("LivePFDSSidebar")
        self.live_pfds_sidebar.setStyleSheet("""
            QFrame#LivePFDSSidebar {
                background-color: #141a22;
                border: 1px solid #4b5664;
                border-radius: 4px;
            }
            QLabel#PendingSidebarTitle {
                color: #ffdc00;
                font-size: 12px;
                font-weight: 800;
            }
            QLabel#PendingSidebarSubtitle {
                color: #8f9aa6;
                font-size: 11px;
            }
        """)
        self.live_pfds_sidebar.setMinimumWidth(0)
        self.live_pfds_sidebar.setMaximumWidth(340)
        sidebar_layout = QVBoxLayout(self.live_pfds_sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(10)
        sidebar_title = QLabel("PENDING & UNMAPPED")
        sidebar_title.setObjectName("PendingSidebarTitle")
        sidebar_layout.addWidget(sidebar_title)
        sidebar_copy = QLabel("Newly seen serial identities and incomplete room mappings")
        sidebar_copy.setObjectName("PendingSidebarSubtitle")
        sidebar_copy.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_copy)
        self.live_pfds_pending_scroll = QScrollArea()
        self.live_pfds_pending_scroll.setWidgetResizable(True)
        self.live_pfds_pending_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.live_pfds_pending_host = QWidget()
        self.live_pfds_pending_layout = QVBoxLayout(self.live_pfds_pending_host)
        self.live_pfds_pending_layout.setContentsMargins(0, 0, 0, 0)
        self.live_pfds_pending_layout.setSpacing(10)
        self.live_pfds_pending_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.live_pfds_pending_layout.addStretch(1)
        self.live_pfds_pending_scroll.setWidget(self.live_pfds_pending_host)
        sidebar_layout.addWidget(self.live_pfds_pending_scroll, 1)
        body.addWidget(self.live_pfds_sidebar)

        root.addLayout(body, 1)

        self.live_pfds_sidebar_expanded = True
        self._live_pfds_sidebar_width = 340
        self._live_pfds_sidebar_anim = QPropertyAnimation(self.live_pfds_sidebar, b"maximumWidth", self)
        self._live_pfds_sidebar_anim.setDuration(220)
        self._live_pfds_sidebar_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._live_pfds_sidebar_anim.finished.connect(self._on_live_pfds_sidebar_anim_finished)

        self._live_pfds_resize_timer = QTimer(self)
        self._live_pfds_resize_timer.setSingleShot(True)
        self._live_pfds_resize_timer.timeout.connect(self._refresh_live_pfds_tab)

        original_resize = self.live_pfds_scroll.resizeEvent
        def _live_pfds_resize(event, orig=original_resize):
            orig(event)
            if not self._is_live_pfds_tab_active():
                return
            # Coalesce resize bursts (especially during tab/filter transitions).
            try:
                self._live_pfds_resize_timer.start(120)
            except Exception:
                pass
        self.live_pfds_scroll.resizeEvent = _live_pfds_resize

        self._live_pfds_refresh_pending = False

        self.tabs.addTab(live_tab, "LIVE PFDS")
        self._sync_live_pfds_filter_buttons()
        self._refresh_live_pfds_tab()

    def init_live_assets_tab(self):
        """Create tactical live assets tab backed by configured streams and PFDS mappings."""
        assets_tab = QWidget()
        root = QVBoxLayout(assets_tab)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("LiveAssetsHeader")
        header.setStyleSheet("""
            QFrame#LiveAssetsHeader {
                background-color: #141a22;
                border: 1px solid #45505d;
                border-radius: 4px;
            }
            QLabel#LiveAssetsTitle {
                color: #ffdc00;
                font-size: 14px;
                font-weight: 800;
            }
            QLabel#LiveAssetsSubline {
                color: #96a1ad;
                font-size: 11px;
            }
            QLabel#LiveAssetsStat {
                color: #d5dbe3;
                background-color: #1a222a;
                border: 1px solid #4b5664;
                border-radius: 3px;
                padding: 6px 10px;
                font-family: "Roboto Mono", "Menlo", "Consolas", monospace;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #27313b;
                color: #edf1f5;
                border: 1px solid #566273;
                border-radius: 3px;
                padding: 7px 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                border-color: #ffdc00;
                color: #ffdc00;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(8)

        copy_col = QVBoxLayout()
        title = QLabel("LIVE ASSETS")
        title.setObjectName("LiveAssetsTitle")
        subtitle = QLabel("Mission asset cards linking video rooms to PFDS lifecycle and control state")
        subtitle.setObjectName("LiveAssetsSubline")
        copy_col.addWidget(title)
        copy_col.addWidget(subtitle)
        header_layout.addLayout(copy_col)
        header_layout.addStretch(1)

        self.live_assets_count_chip = QLabel("ASSETS 0")
        self.live_assets_count_chip.setObjectName("LiveAssetsStat")
        header_layout.addWidget(self.live_assets_count_chip)

        self.live_assets_healthy_chip = QLabel("READY 0")
        self.live_assets_healthy_chip.setObjectName("LiveAssetsStat")
        header_layout.addWidget(self.live_assets_healthy_chip)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_live_operations_views)
        header_layout.addWidget(refresh_btn)
        root.addWidget(header)

        self.live_assets_scroll = QScrollArea()
        self.live_assets_scroll.setWidgetResizable(True)
        self.live_assets_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.live_assets_host = QWidget()
        self.live_assets_grid = QGridLayout(self.live_assets_host)
        self.live_assets_grid.setContentsMargins(0, 0, 0, 0)
        self.live_assets_grid.setHorizontalSpacing(12)
        self.live_assets_grid.setVerticalSpacing(12)
        self.live_assets_host.setLayout(self.live_assets_grid)
        self.live_assets_scroll.setWidget(self.live_assets_host)
        root.addWidget(self.live_assets_scroll, 1)

        original_resize = self.live_assets_scroll.resizeEvent
        def _live_assets_resize(event, orig=original_resize):
            orig(event)
            QTimer.singleShot(0, self._refresh_live_assets_tab)
        self.live_assets_scroll.resizeEvent = _live_assets_resize

        self.tabs.addTab(assets_tab, "LIVE ASSETS")
        self._refresh_live_assets_tab()

    def update_graph(self):
        try:
            # Lazy import matplotlib only when needed
            import matplotlib
            matplotlib.use('QtAgg')
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
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
                if hasattr(sender, 'handle_maximize_state'):
                    sender.handle_maximize_state()
            except Exception as e:
                print(f"Button visibility error in maximize: {e}")

            # SECOND: Now modify the grid - hide non-sender widgets and maximize sender.
            # Freeze the grid host to suppress intermediate paints (black-flash prevention).
            # Qt6 does NOT propagate setUpdatesEnabled(False) to children, so we
            # freeze the container and each VideoWidget individually.
            _grid_container = getattr(self, 'rtsp_grid_container', None) or self.rtsp_grid.parentWidget()
            _frozen_widgets = []
            try:
                if _grid_container:
                    _grid_container.setUpdatesEnabled(False)
                    _frozen_widgets.append(_grid_container)
            except Exception:
                pass
            for item_data in self.original_layout['grid_items']:
                w = item_data.get('widget')
                if w is not None:
                    try:
                        w.setUpdatesEnabled(False)
                        _frozen_widgets.append(w)
                    except Exception:
                        pass

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
            # Avoid forcing keyboard focus here; it can contribute to focus churn
            # when the operator switches tabs immediately after maximizing.

            # Re-enable painting now that all widgets are in their final state.
            # Re-enable all frozen widgets — single composite repaint.
            for w in reversed(_frozen_widgets):
                try:
                    w.setUpdatesEnabled(True)
                    w.update()
                except Exception:
                    pass
            self.rtsp_grid.update()

            # Force a redraw after layout settles so fusion overlay appears in maximized mode.
            try:
                QTimer.singleShot(0, lambda w=sender: self._refresh_widget_after_layout(w))
            except Exception:
                pass

        except Exception as e:
            print(f"Maximize error: {str(e)}")
            import traceback
            traceback.print_exc()

    def handle_minimize(self):
        """Restore to grid view - show all hidden widgets"""
        try:
            if not self.maximized_widget or not self.original_layout:
                return

            restored_items = list(self.original_layout.get('grid_items', []))
            
            # Restore button visibility for the previously maximized widget
            try:
                if hasattr(self.maximized_widget, 'maximize_btn'):
                    self.maximized_widget.maximize_btn.setVisible(True)  # Show maximize
                if hasattr(self.maximized_widget, 'minimize_btn'):
                    self.maximized_widget.minimize_btn.setVisible(False)  # Hide minimize
                if hasattr(self.maximized_widget, 'handle_minimize_state'):
                    self.maximized_widget.handle_minimize_state()
            except Exception as e:
                print(f"Button visibility error: {e}")

            # Freeze grid host to prevent black flash while restoring all tiles at once.
            # removeWidget is intentionally moved INSIDE the freeze so the grid never
            # has a visually-empty frame (all tiles hidden + maximized tile removed)
            # between two paint frames — that gap is what causes the brief black flash.
            # Qt6 does NOT propagate setUpdatesEnabled(False) to children, so freeze
            # each VideoWidget explicitly.
            _grid_container = getattr(self, 'rtsp_grid_container', None) or self.rtsp_grid.parentWidget()
            _frozen_widgets = []
            try:
                if _grid_container:
                    _grid_container.setUpdatesEnabled(False)
                    _frozen_widgets.append(_grid_container)
            except Exception:
                pass
            for item in restored_items:
                w = item.get('widget')
                if w is not None:
                    try:
                        w.setUpdatesEnabled(False)
                        _frozen_widgets.append(w)
                    except Exception:
                        pass

            # Remove the maximized widget from grid (inside freeze so layout is
            # never in a painted-empty state).
            try:
                self.rtsp_grid.removeWidget(self.maximized_widget)
            except Exception as e:
                print(f"Remove widget error: {e}")

            # Restore all widgets to their original grid positions
            for item in restored_items:
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

            # Re-enable painting now that all tiles are restored.
            # Re-enable all frozen widgets — single composite repaint.
            for w in reversed(_frozen_widgets):
                try:
                    w.setUpdatesEnabled(True)
                    w.update()
                except Exception:
                    pass
            self.rtsp_grid.update()

            # Refresh all restored widgets after geometry settles.
            try:
                for item in restored_items:
                    widget = item.get('widget')
                    if widget:
                        QTimer.singleShot(0, lambda w=widget: self._refresh_widget_after_layout(w))
            except Exception:
                pass

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

    def _refresh_widget_after_layout(self, widget):
        """Best-effort overlay refresh after maximize/minimize geometry changes."""
        try:
            if not widget:
                return
            if hasattr(widget, 'position_controls'):
                widget.position_controls()
            if hasattr(widget, '_redraw_with_grid'):
                widget._redraw_with_grid()
            elif hasattr(widget, 'update'):
                widget.update()
        except Exception:
            pass

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
        old_grafana_enabled = bool(self.config.get('enable_grafana', False))
        dialog = StreamConfigDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.get_config()
            self.active_analytics_category = self._normalize_analytics_category(self.config.get('active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
            self._load_analytics_banner_preferences()
            self._reload_rule_engine_for_active_category()
            StreamConfig.save_config(self.config)
            self._set_grafana_tab_visibility(bool(self.config.get('enable_grafana', False)))
            self.group_combo.clear()
            self.group_combo.addItems(self.config["groups"])
            # Defer grid rebuild to avoid blocking UI during cleanup
            self.schedule_grid_rebuild()

            # Notify user when dashboard visibility changed at runtime.
            new_grafana_enabled = bool(self.config.get('enable_grafana', False))
            if old_grafana_enabled != new_grafana_enabled:
                state = "enabled" if new_grafana_enabled else "disabled"
                self.statusBar().showMessage(f"Metrics Dashboard {state}", 4000)

    def _set_grafana_tab_visibility(self, enabled: bool):
        if not hasattr(self, 'tabs'):
            return

        metrics_idx = -1
        for i in range(self.tabs.count()):
            if "Metrics Dashboard" in self.tabs.tabText(i):
                metrics_idx = i
                break

        if enabled and metrics_idx == -1:
            self.init_grafana_tab()
            return

        if not enabled and metrics_idx >= 0:
            self.tabs.removeTab(metrics_idx)

    def reset_streams(self):
        """Clear all configured streams and reset to default group layout."""
        reply = QMessageBox.question(
            self,
            "Reset Streams",
            "This will remove all configured streams and reset to a blank default configuration. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return
        # Build default empty configuration — preserve all non-stream keys (thresholds, tcp settings, etc.)
        default_config = {k: v for k, v in self.config.items() if k not in ("groups", "streams")}
        default_config["groups"] = ["Default"]
        default_config["streams"] = []
        default_config.setdefault("tcp_port", 9000)
        if StreamConfig.save_config(default_config):
            self.config = default_config
            self.active_analytics_category = self._normalize_analytics_category(self.config.get('active_analytics_category', DEFAULT_ANALYTICS_CATEGORY))
            self._load_analytics_banner_preferences()
            self._reload_rule_engine_for_active_category()
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
        self._style_tactical_dialog(profile_dialog)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Username: admin"))
        layout.addWidget(QLabel("Email: admin@example.com"))
        close_btn = QPushButton("Close", clicked=profile_dialog.close)
        layout.addWidget(close_btn)
        profile_dialog.setLayout(layout)
        profile_dialog.exec()

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
        if bool(getattr(self, '_is_logging_out', False)):
            return
        self._is_logging_out = True
        self._skip_close_cleanup = False
        self._cleanup_done = False

        print("Logout initiated - starting async shutdown...")
        self.statusBar().showMessage("Signing out...", 3000)
        self.setEnabled(False)
        
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

                # Stop optional background managers used by field runtime.
                try:
                    if hasattr(self, 'emberhawk') and self.emberhawk:
                        self.emberhawk.stop_scheduler()
                except Exception as e:
                    print(f"EmberHawk scheduler stop error: {e}")

                try:
                    if hasattr(self, 'metrics_server') and self.metrics_server:
                        self.metrics_server.stop()
                except Exception as e:
                    print(f"Metrics server stop error: {e}")

                self._cleanup_done = True
                
                print("Cleanup complete, returning to login...")
            except Exception as e:
                print(f"Shutdown error: {e}")
            finally:
                # UI operations must run on the GUI thread.
                try:
                    QMetaObject.invokeMethod(self, "_finalize_logout_on_ui_thread", Qt.ConnectionType.QueuedConnection)
                except Exception as e:
                    print(f"Logout finalize invoke error: {e}")
                    self._is_logging_out = False
        
        # Run shutdown in daemon thread (won't block UI)
        import threading
        shutdown_thread = threading.Thread(target=_shutdown_in_thread, daemon=True)
        shutdown_thread.start()

    @pyqtSlot()
    def _finalize_logout_on_ui_thread(self):
        """Finalize logout by closing this window and opening login on GUI thread."""
        try:
            from embereye_base.app.ee_loginwindow import EELoginWindow

            self._skip_close_cleanup = True
            self._login_window = EELoginWindow()
            self._login_window.show()
            self.hide()
            self.close()
        except Exception as e:
            print(f"Finalize logout error: {e}")
            try:
                self.setEnabled(True)
            except Exception:
                pass
        finally:
            self._is_logging_out = False

    def shutdown_video_widgets(self):
        """Iterate all video widgets and ensure their worker threads stop (with timeout)."""
        for widget in self.get_video_widgets():
            if hasattr(widget, 'stop'):
                try:
                    widget.stop()
                except Exception as e:
                    print(f"Error stopping video widget ({getattr(widget, 'loc_id', 'unknown')}): {e}")
