import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

print("[VIDEO_WORKER_MODULE] Loading video_worker.py with NEW CODE v2.0", flush=True)

import cv2

from PyQt6.QtWidgets import (
    QApplication
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QMutex, QMutexLocker,
    QObject, QMetaObject, Q_ARG
)

from embereye_base.core.vision_detector import VisionDetector
from embereye_base.core.pipeline_logs import log_vision_event
from shared.emberkit import log_debug, log_error
from embereye_base.utils.debug_config import is_debug_enabled
from shared.emberkit import get_fps_controller
from shared.emberkit import get_metrics
# Hybrid detection system imports
import threading
import time
import math
from embereye_base.core.detection_queue import get_detection_queue, FrameMetadata
from embereye_base.core.detection_worker import get_detection_worker, stop_detection_worker


def _normalize_detection_class_name(name):
    return str(name or '').strip().lower().replace(' ', '_').replace('-', '_')


def _canonicalize_ppe_class_name(name):
    normalized = _normalize_detection_class_name(name)
    return {
        'hardhat': 'helmet',
        'safety_helmet': 'helmet',
        'without_helmet': 'no_helmet',
        'head_no_helmet': 'head',
        'safety_vest': 'vest',
        'high_visibility_vest': 'vest',
        'without_vest': 'no_vest',
        'worker': 'person',
    }.get(normalized, normalized)

class VideoWorker(QObject):
    frame_ready = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    connection_status = pyqtSignal(bool)
    vision_score_ready = pyqtSignal(float)  # New signal for fire/smoke confidence
    # Emit when an anomaly frame is captured: QImage, score, stream_id, yolo_score, detections
    anomaly_frame_ready = pyqtSignal(QImage, float, str, float, object)
    # Emit when YOLO returns detections: status, yolo_score, detections, frame_size
    detection_event = pyqtSignal(str, float, object, object)
    start_timer_requested = pyqtSignal()  # Signal to safely start timer from main thread
    stop_timer_requested = pyqtSignal()  # Signal to safely stop timer from main thread
    set_interval_requested = pyqtSignal(int)  # Signal to safely set timer interval from main thread

    def __init__(self, rtsp_url, stream_id=None):
        super().__init__()
        self.rtsp_url = self._format_url(rtsp_url)
        self.stream_id = stream_id or rtsp_url  # Unique identifier for metrics
        self.mutex = QMutex()
        self.cap = None
        self.timer = QTimer()
        self.timer.moveToThread(QApplication.instance().thread())  # Move timer to main thread
        self.timer.setInterval(30)  # ~33 FPS (will be adjusted adaptively)
        # Note: timer.timeout connection is done in video_widget.py to ensure proper thread context
        # Initialize VisionDetector WITHOUT loading YOLO (prevent DLL errors in main thread)
        self.vision_detector = VisionDetector(yolo_model_path="__no_model__")
        # Hybrid detection system
        self.detection_queue = get_detection_queue()
        self.detection_worker = None  # Will be started in init_detection_worker()
        self._detection_frame_id = 0  # Counter for tracking queued frames
        # Adaptive FPS controller and metrics
        self.fps_controller = get_fps_controller()
        self.metrics = get_metrics()
        self._last_fps_check = 0
        self._fps_check_interval = 1.0  # Check FPS adjustment every second
        # Anomaly capture
        self.anomaly_threshold = 0.4
        self._last_qimage = None
        self._detections_lock = threading.Lock()
        self._latest_detections = []
        self._latest_detection_ts = 0.0
        overlay_ttl_env = os.environ.get("EMBEREYE_DETECTION_OVERLAY_TTL_MS", "700")
        try:
            self._detection_overlay_ttl_ms = max(100, int(float(overlay_ttl_env)))
        except Exception:
            self._detection_overlay_ttl_ms = 700
        self._detection_counter = 0
        self._last_frame_size = None
        # Limit anomaly snapshot signal rate to avoid saturating the UI thread
        # during sustained alarm conditions with high detection frequency.
        max_emit_fps_env = os.environ.get("EMBEREYE_ANOMALY_EMIT_MAX_FPS", "6")
        try:
            max_emit_fps = float(max_emit_fps_env)
        except Exception:
            max_emit_fps = 6.0
        self._anomaly_emit_interval_s = (1.0 / max_emit_fps) if max_emit_fps > 0.0 else 0.0
        self._last_anomaly_emit_ts = 0.0
        # Local cameras on macOS can intermittently return empty frames during
        # warm-up or when auto-exposure changes. Avoid tearing down the stream
        # on a single failed read.
        self._read_failures = 0
        self._max_read_failures = 45
        # RTSP buffer management for low latency
        self._is_rtsp_stream = self._check_if_rtsp(rtsp_url)
        self._frame_skip_count = 0  # Track frames skipped for buffer drain
        self._heuristic_log_counter = 0
        heuristic_env = os.environ.get("EMBEREYE_HEURISTIC_THRESHOLD", "0.20")
        try:
            self.heuristic_threshold = max(0.0, min(1.0, float(heuristic_env)))
        except Exception:
            self.heuristic_threshold = 0.20
        force_yolo_env = os.environ.get("EMBEREYE_FORCE_YOLO_EVERY_N", "10")
        try:
            self.force_yolo_every_n_frames = max(1, int(force_yolo_env))
        except Exception:
            self.force_yolo_every_n_frames = 10
        heuristic_decimation_env = os.environ.get("EMBEREYE_HEURISTIC_DECIMATION", "3")
        try:
            self._heuristic_decimation = max(1, int(float(heuristic_decimation_env)))
        except Exception:
            self._heuristic_decimation = 3
        heuristic_hot_decimation_env = os.environ.get("EMBEREYE_HEURISTIC_HOT_DECIMATION", "5")
        try:
            self._heuristic_hot_decimation = max(self._heuristic_decimation, int(float(heuristic_hot_decimation_env)))
        except Exception:
            self._heuristic_hot_decimation = max(self._heuristic_decimation, 5)
        self._heuristic_frame_counter = 0
        self._last_heuristic_score = None
        overlay_decimation_env = os.environ.get("EMBEREYE_OVERLAY_DECIMATION", "3")
        try:
            self._overlay_decimation = max(1, int(float(overlay_decimation_env)))
        except Exception:
            self._overlay_decimation = 3
        self._overlay_frame_counter = 0
        box_mode_env = str(os.environ.get("EMBEREYE_BBOX_MODE", "all")).strip().lower()
        self.detection_box_mode = box_mode_env if box_mode_env in ("all", "specific") else "all"
        box_classes_env = str(os.environ.get("EMBEREYE_BBOX_CLASSES", "")).strip()
        self.detection_box_classes = set(
            class_name.strip().lower().replace(' ', '_').replace('-', '_')
            for class_name in box_classes_env.split(';')
            if class_name.strip()
        )
        # Motion gating for PPE: suppress static sticker/sign detections.
        # Nearest-neighbour tracking avoids the grid-cell boundary reset bug.
        # 12 px movement threshold is well above RTSP compression jitter (2-5 px)
        # but below real person movement.  2 static observations = fast suppression.
        self._ppe_motion_px_threshold = 12.0
        self._ppe_static_frames_to_drop = 2
        self._ppe_track_merge_radius = 40.0   # px — max dist to associate with existing track
        self._ppe_motion_state = {}
        # Time-based cap on queue submissions: even when every frame passes the
        # heuristic threshold (sustained alarm), frame.copy() + queue add are
        # skipped when submissions would exceed this rate.  The YOLO worker runs
        # at its own pace; exceeding ~10 submissions/sec only wastes GUI-thread
        # time and floods the queue backpressure mechanism.
        max_queue_fps_env = os.environ.get("EMBEREYE_MAX_QUEUE_FPS", "10")
        try:
            max_queue_fps = max(1.0, float(max_queue_fps_env))
        except Exception:
            max_queue_fps = 10.0
        self._queue_submit_interval_s = 1.0 / max_queue_fps
        self._last_queue_submit_ts = 0.0
        backpressure_depth_env = os.environ.get("EMBEREYE_QUEUE_BACKPRESSURE_DEPTH", "2")
        try:
            self._queue_backpressure_depth = max(1, int(float(backpressure_depth_env)))
        except Exception:
            self._queue_backpressure_depth = 2

    def init_detection_worker(self):
        """Initialize the background DetectionWorker for async YOLO processing."""
        try:
            # Start the global detection worker with our callback
            self.detection_worker = get_detection_worker(self._on_detection_result)
            if self.detection_worker:
                print(f"[DETECTION_WORKER] Started for stream {self.stream_id}", flush=True)
            else:
                print(f"[WARNING] Failed to initialize DetectionWorker for stream {self.stream_id}", flush=True)
        except Exception as e:
            print(f"[ERROR] DetectionWorker init failed: {e}", flush=True)
            self.detection_worker = None

    def _is_ppe_mode_active(self):
        try:
            category = str(os.environ.get("EMBEREYE_ANALYTICS_CATEGORY", "fire") or "fire").strip().lower()
            return category == "ppe"
        except Exception:
            return False

    def _filter_ppe_static_detections(self, detections):
        """Drop persistent static PPE detections to reduce sticker/sign false positives.

        Uses nearest-neighbour track matching instead of grid-cell buckets to avoid
        false resets caused by RTSP compression jitter crossing cell boundaries.
        A track is considered static when the bbox centre hasn't moved more than
        ``_ppe_motion_px_threshold`` pixels across ``_ppe_static_frames_to_drop``
        consecutive inference observations.
        """
        if not detections:
            return []
        if not self._is_ppe_mode_active():
            return list(detections)

        now = time.time()
        filtered = []
        # Filter only hazard/equipment classes — never suppress PERSON detections.
        # A real person standing still must still show a box (and drive alarm logic).
        ppe_classes = {"helmet", "no_helmet", "head", "vest", "no_vest"}
        merge_r = float(self._ppe_track_merge_radius)

        # Prune stale tracks (not seen in 3 s).
        stale_keys = [
            k
            for k, v in self._ppe_motion_state.items()
            if isinstance(k, str)
            and isinstance(v, dict)
            and (now - float(v.get("last_seen", 0.0))) > 3.0
        ]
        for k in stale_keys:
            self._ppe_motion_state.pop(k, None)

        # Next track id counter (stored in state dict under "__next_id").
        next_id = int(self._ppe_motion_state.pop("__next_id", 0))

        for det in detections:
            if not isinstance(det, dict):
                continue
            cls = _canonicalize_ppe_class_name(det.get("class", ""))
            bbox = det.get("bbox")
            if cls not in ppe_classes or not bbox or len(bbox) != 4:
                filtered.append(det)
                continue

            try:
                x1, y1, x2, y2 = [float(v) for v in bbox]
                cx = (x1 + x2) * 0.5
                cy = (y1 + y2) * 0.5
            except Exception:
                filtered.append(det)
                continue

            # Find nearest existing track of same class within merge_r.
            best_key = None
            best_dist = merge_r
            for key, st in self._ppe_motion_state.items():
                # Skip metadata slots (e.g. "__next_id") and any malformed states.
                if not isinstance(key, str) or not isinstance(st, dict):
                    continue
                if not key.startswith(cls + ":"):
                    continue
                pcx, pcy = st.get("last_center", (cx, cy))
                d = math.hypot(cx - float(pcx), cy - float(pcy))
                if d < best_dist:
                    best_dist = d
                    best_key = key

            if best_key is None:
                # New track — always show on first observation.
                best_key = f"{cls}:{next_id}"
                next_id += 1
                self._ppe_motion_state[best_key] = {
                    "last_center": (cx, cy),
                    "static_hits": 0,
                    "last_seen": now,
                }
                filtered.append(det)
                continue

            st = self._ppe_motion_state[best_key]
            prev_cx, prev_cy = st.get("last_center", (cx, cy))
            dist = math.hypot(cx - float(prev_cx), cy - float(prev_cy))
            moved = dist >= self._ppe_motion_px_threshold

            if moved:
                st["static_hits"] = 0
                keep = True
            else:
                st["static_hits"] = int(st.get("static_hits", 0)) + 1
                keep = int(st["static_hits"]) < int(self._ppe_static_frames_to_drop)

            st["last_center"] = (cx, cy)
            st["last_seen"] = now
            self._ppe_motion_state[best_key] = st

            if keep:
                filtered.append(det)

        self._ppe_motion_state["__next_id"] = next_id
        return filtered

    def _on_detection_result(self, result):
        """Callback when DetectionWorker completes YOLO inference on a queued frame."""
        try:
            if result is None:
                return
           
            # Extract detection info from DetectionResult dataclass
            stream_id = result.stream_id
            if stream_id != str(self.stream_id):
                return  # Result is for a different stream
            
            status = result.status  # "CONFIRMED", "POSSIBLE", "LOW"
            confidence = result.confidence
            detections = self._filter_ppe_static_detections(result.detections or [])
            primary_class = result.primary_class
            yolo_latency = result.yolo_latency_ms

            with self._detections_lock:
                self._latest_detections = detections or []
                self._latest_detection_ts = result.timestamp_ms or (time.time() * 1000)
                if detections:
                    self._detection_counter += 1
            
            # Map confidence level to numerical score for backward compatibility
            possible_thr = 0.60
            confirmed_thr = 0.80
            if self.detection_worker and getattr(self.detection_worker, 'detector', None):
                detector = self.detection_worker.detector
                possible_thr = float(getattr(detector, 'possible_threshold', possible_thr))
                confirmed_thr = float(getattr(detector, 'confirmed_threshold', confirmed_thr))
            if confirmed_thr <= possible_thr:
                confirmed_thr = min(1.0, possible_thr + 0.05)

            if status == 'CONFIRMED':
                yolo_score = max(confirmed_thr, confidence)
            elif status == 'POSSIBLE':
                yolo_score = max(possible_thr, min(confirmed_thr, confidence))
            else:
                yolo_score = min(possible_thr, confidence)
            
            # Emit detection_event FIRST so widget._latest_detections is
            # updated before handle_vision_score reads PPE stats from it.
            if detections:
                self.detection_event.emit(status, yolo_score, detections or [], self._last_frame_size)

            # Forward vision score to fusion/alarm pipeline for every inference result.
            self.vision_score_ready.emit(yolo_score)

            log_vision_event(
                "YOLO",
                str(self.stream_id),
                f"status={status} conf={confidence:.3f} yolo_score={yolo_score:.3f} det={len(detections or [])} class={primary_class or '-'} latency_ms={yolo_latency:.1f}"
            )

            if status in ['CONFIRMED', 'POSSIBLE'] and len(detections) > 0:
                # Emit anomaly frame with YOLO results
                if self._last_qimage:
                    now_s = time.time()
                    can_emit = True
                    if self._anomaly_emit_interval_s > 0.0:
                        can_emit = (now_s - float(self._last_anomaly_emit_ts)) >= self._anomaly_emit_interval_s
                    if can_emit:
                        self._last_anomaly_emit_ts = now_s
                        if is_debug_enabled():
                            print(
                                f"[DETECTION_RESULT] Emitting anomaly: stream={self.stream_id}, "
                                f"status={status}, yolo={yolo_score:.3f}, detections={len(detections)}",
                                flush=True,
                            )
                        self.anomaly_frame_ready.emit(self._last_qimage, yolo_score, str(self.stream_id), yolo_score, detections)
            else:
                if is_debug_enabled():
                    print(f"[DETECTION_RESULT] Skipping emission: stream={self.stream_id}, status={status}, yolo={yolo_score:.3f} (below 0.50 threshold)", flush=True)
        except Exception as e:
            log_debug(f"Detection result handler error: {e}")

    def _draw_hybrid_detections(self, frame):
        """Overlay latest hybrid detection boxes on the display frame."""
        try:
            with self._detections_lock:
                detections = list(self._latest_detections)
                last_ts = self._latest_detection_ts

            if not detections:
                return frame

            age_ms = (time.time() * 1000) - last_ts
            if age_ms > self._detection_overlay_ttl_ms:
                return frame

            # Use possible_conf_threshold from the detection worker as the
            # display floor — only draw boxes that reach at least POSSIBLE level.
            # Falls back to the EMBEREYE_POSSIBLE_CONF env var then 0.60.
            min_conf = 0.60
            try:
                if self.detection_worker and getattr(self.detection_worker, 'detector', None):
                    min_conf = float(getattr(self.detection_worker.detector, 'possible_threshold', min_conf))
                else:
                    env_val = os.environ.get('EMBEREYE_POSSIBLE_CONF', '')
                    if env_val:
                        min_conf = max(0.0, min(1.0, float(env_val)))
            except Exception:
                pass

            # In PPE mode, only render PPE equipment/violation boxes when they
            # are spatially associated with a detected person in the same frame.
            # This avoids noisy arm/object-only boxes from cluttering the UI.
            ppe_classes = {'helmet', 'no_helmet', 'head', 'vest', 'no_vest'}
            person_bboxes = []
            for det in detections:
                try:
                    cls_name = _canonicalize_ppe_class_name(det.get('class', 'UNKNOWN'))
                    conf = float(det.get('confidence', 0.0))
                    bbox = det.get('bbox')
                    if cls_name == 'person' and conf >= min(0.4, min_conf) and bbox and len(bbox) == 4:
                        person_bboxes.append([float(v) for v in bbox])
                except Exception:
                    continue

            def _ppe_overlaps_person_local(ppe_bbox, persons, min_containment=0.3):
                try:
                    x1, y1, x2, y2 = [float(v) for v in ppe_bbox]
                    ppe_w = max(0.0, x2 - x1)
                    ppe_h = max(0.0, y2 - y1)
                    ppe_area = ppe_w * ppe_h
                    if ppe_area <= 0.0:
                        return False
                    for pb in persons:
                        px1, py1, px2, py2 = [float(v) for v in pb]
                        ix1 = max(x1, px1)
                        iy1 = max(y1, py1)
                        ix2 = min(x2, px2)
                        iy2 = min(y2, py2)
                        iw = max(0.0, ix2 - ix1)
                        ih = max(0.0, iy2 - iy1)
                        inter_area = iw * ih
                        if (inter_area / ppe_area) >= float(min_containment):
                            return True
                except Exception:
                    return False
                return False

            for det in detections:
                bbox = det.get('bbox')
                if not bbox or len(bbox) != 4:
                    continue

                x1, y1, x2, y2 = [int(v) for v in bbox]
                class_name = det.get('class', 'UNKNOWN')
                conf = float(det.get('confidence', 0.0))

                # Skip boxes below the display confidence threshold.
                if conf < min_conf:
                    continue

                class_key = _canonicalize_ppe_class_name(class_name)
                if class_key in ppe_classes:
                    if not person_bboxes:
                        continue
                    if not _ppe_overlaps_person_local(bbox, person_bboxes):
                        continue

                if self.detection_box_mode == 'specific' and class_key not in self.detection_box_classes:
                    continue

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
                label = f"{class_name} {conf:.2f}"
                cv2.putText(frame, label, (x1, max(0, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)

            return frame
        except Exception as e:
            log_debug(f"Hybrid overlay error: {e}")
            return frame

    def _draw_detection_counter(self, frame):
        """Detection counter overlay disabled for production UI."""
        return frame

    def start_stream(self):
        try:
            with QMutexLocker(self.mutex):
                if self.cap and self.cap.isOpened():
                    return
                open_attempts = []
                # Distinguish local device index vs RTSP/URL
                is_device = self.rtsp_url.isdigit()
                if is_device:
                    dev_index = int(self.rtsp_url)
                    # Try platform-friendly backends
                    # macOS: AVFoundation
                    backend_codes = []
                    if hasattr(cv2, 'CAP_AVFOUNDATION'):
                        backend_codes.append(getattr(cv2, 'CAP_AVFOUNDATION'))
                    backend_codes.append(getattr(cv2, 'CAP_ANY', 0))
                    # Windows: DirectShow and Media Foundation
                    for backend_name in ['CAP_DSHOW', 'CAP_MSMF']:
                        if hasattr(cv2, backend_name):
                            backend_codes.append(getattr(cv2, backend_name))
                    self.cap = None
                    for b in backend_codes:
                        try:
                            if b == getattr(cv2, 'CAP_ANY', 0):
                                tmp_cap = cv2.VideoCapture(dev_index)
                                attempt_label = 'CAP_ANY/default'
                            else:
                                tmp_cap = cv2.VideoCapture(dev_index, b)
                                # Derive readable name
                                name_map = {
                                    getattr(cv2, 'CAP_AVFOUNDATION', -1): 'CAP_AVFOUNDATION',
                                    getattr(cv2, 'CAP_DSHOW', -2): 'CAP_DSHOW',
                                    getattr(cv2, 'CAP_MSMF', -3): 'CAP_MSMF'
                                }
                                attempt_label = name_map.get(b, str(b))
                            open_attempts.append(f"Device {dev_index} {attempt_label} -> {'OK' if tmp_cap.isOpened() else 'FAIL'}")
                            if tmp_cap.isOpened():
                                self.cap = tmp_cap
                                break
                        except Exception as be:
                            open_attempts.append(f"Device {dev_index} backend exception: {be}")
                    if not self.cap or not self.cap.isOpened():
                        raise ConnectionError(f"Failed to open local device {dev_index}. Attempts: {'; '.join(open_attempts)}")
                    # Try setting common macOS webcam properties for reliability
                    try:
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        self.cap.set(cv2.CAP_PROP_FPS, 30)
                    except Exception:
                        pass
                else:
                    # URL / RTSP path - optimize for low latency
                    # Try CAP_FFMPEG first for better RTSP performance
                    try:
                        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                        open_attempts.append(f"CAP_FFMPEG backend -> {'OK' if self.cap.isOpened() else 'FAIL'}")
                    except Exception as fe:
                        open_attempts.append(f"CAP_FFMPEG exception: {fe}")
                        self.cap = None
                    
                    # Fallback to default backend if FFMPEG fails
                    if not self.cap or not self.cap.isOpened():
                        self.cap = cv2.VideoCapture(self.rtsp_url)
                        open_attempts.append(f"OpenCV default backend -> {'OK' if self.cap.isOpened() else 'FAIL'}")
                    
                    if not self.cap.isOpened():
                        raise ConnectionError(f"Failed to open stream. Attempts: {'; '.join(open_attempts)}")
                    
                    # Configure RTSP stream for minimal latency
                    if self._is_rtsp_stream:
                        self._configure_rtsp_low_latency()

                # Request timer start from main thread (timer lives in GUI thread)
                self.start_timer_requested.emit()
                # Initialize DetectionWorker for background YOLO processing
                self.init_detection_worker()
                self.connection_status.emit(True)

        except Exception as e:
            from embereye_base.utils.error_logger import get_error_logger
            get_error_logger().log(self.rtsp_url, f"start_stream error: {e}")
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)

    def update_frame(self):
        if is_debug_enabled():
            print(f"[UPDATE_FRAME] Called for stream {self.stream_id}", flush=True)
        try:
            import time
            with QMutexLocker(self.mutex):
                if not self.cap or not self.cap.isOpened():
                    if is_debug_enabled():
                        print(f"[UPDATE_FRAME] No cap or not opened", flush=True)
                    return
                
                # CRITICAL FIX: For RTSP streams, aggressively drain buffer to get latest frame
                # This eliminates the 1-minute lag caused by buffered old frames
                if self._is_rtsp_stream:
                    # Read and discard old frames in buffer (keep only latest)
                    for _ in range(5):  # Drain up to 5 frames at once
                        ret = self.cap.grab()  # Fast grab without decoding
                        if not ret:
                            break
                    # Now retrieve the latest frame
                    ret, frame = self.cap.retrieve()
                    if not ret:
                        ret, frame = self.cap.read()  # Fallback if retrieve fails
                else:
                    # Local camera: normal read
                    ret, frame = self.cap.read()
            
            if not ret:
                # Attempt a brief reconnect for device streams
                raw = self.rtsp_url.replace('rtsp://', '').split('?')[0]
                if raw.isdigit():
                    # Reopen using the same backend sequence
                    try:
                        dev_index = int(raw)
                        tmp = cv2.VideoCapture(dev_index)
                        if not tmp.isOpened() and hasattr(cv2, 'CAP_AVFOUNDATION'):
                            tmp = cv2.VideoCapture(dev_index, getattr(cv2, 'CAP_AVFOUNDATION'))
                        if tmp.isOpened():
                            with QMutexLocker(self.mutex):
                                if self.cap and self.cap.isOpened():
                                    self.cap.release()
                                self.cap = tmp
                            ret, frame = self.cap.read()
                    except Exception:
                        pass
                if not ret:
                        self._read_failures += 1
                        if self._read_failures < self._max_read_failures:
                            return
                        raise RuntimeError("No frame received")

                # Successful frame read: reset transient failure counter.
                self._read_failures = 0

            # Record frame processed
            self.metrics.record_frame_processed(self.stream_id)

            # Draw overlays only every Nth frame; intermediate frames use fast raw path.
            self._overlay_frame_counter += 1
            draw_overlays = (self._overlay_frame_counter % self._overlay_decimation) == 0
            if draw_overlays:
                display_frame = frame.copy()
                display_frame = self._draw_hybrid_detections(display_frame)
                display_frame = self._draw_detection_counter(display_frame)
            else:
                display_frame = frame

            # Convert for display immediately (fast path)
            frame_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            self.frame_ready.emit(QPixmap.fromImage(q_img))
            # Keep a copy for anomaly capture (thread-safe copy created above)
            self._last_qimage = q_img
            self._last_frame_size = (w, h)
            
            # HYBRID DETECTION: Heuristic-first, then queue for YOLO if needed
            try:
                queue_depth = self.detection_queue.get_queue_size()
                # Step 1: Fast heuristic detection with decimation in UI thread.
                self._heuristic_frame_counter += 1
                effective_decimation = (
                    self._heuristic_hot_decimation
                    if queue_depth >= self._queue_backpressure_depth
                    else self._heuristic_decimation
                )
                run_heuristic = (
                    self._last_heuristic_score is None
                    or (self._heuristic_frame_counter % effective_decimation) == 0
                )
                if run_heuristic:
                    h_score = self.vision_detector.heuristic_fire_smoke(frame)
                    self._last_heuristic_score = h_score
                else:
                    h_score = float(self._last_heuristic_score)
                heuristic_threshold = self.heuristic_threshold
                force_sample = (self._detection_frame_id % self.force_yolo_every_n_frames) == 0
                _now_q = time.time()
                # Adaptive back-pressure: double the minimum interval when the
                # queue is running hot (≥3 pending frames) so the worker has
                # time to catch up before we add more.
                _effective_interval = (
                    self._queue_submit_interval_s * 2
                    if queue_depth >= self._queue_backpressure_depth
                    else self._queue_submit_interval_s
                )
                _time_gate_open = (_now_q - self._last_queue_submit_ts) >= _effective_interval
                should_queue = (h_score >= heuristic_threshold or force_sample) and _time_gate_open
                queue_reason = "HEURISTIC" if h_score >= heuristic_threshold else "PERIODIC_SAMPLE"
                
                if is_debug_enabled():
                    print(f"[HYBRID_DETECTION] stream={self.stream_id}, heuristic={h_score:.3f}, threshold={heuristic_threshold}", flush=True)
                
                # Step 2: If heuristic score is above threshold, queue for YOLO validation
                # This prevents obvious non-hazards from being sent to YOLO
                if should_queue:
                    self._last_queue_submit_ts = _now_q
                    # Queue the frame for background YOLO processing
                    frame_id = f"{self.stream_id}-{self._detection_frame_id:05d}"
                    metadata = FrameMetadata(
                        frame_id=frame_id,
                        stream_id=str(self.stream_id),
                        heuristic_score=h_score,
                        frame_data=frame.copy(),
                        timestamp_ms=time.time() * 1000
                    )
                    self._detection_frame_id += 1
                    self.detection_queue.add_frame(metadata)
                    log_vision_event(
                        "HEURISTIC",
                        str(self.stream_id),
                        f"score={h_score:.3f} threshold={heuristic_threshold:.3f} decision=QUEUED reason={queue_reason} frame_id={frame_id}"
                    )
                    if is_debug_enabled():
                        print(f"[HYBRID_DETECTION] Queued frame {metadata.frame_id} for YOLO (heur={h_score:.3f}, reason={queue_reason})", flush=True)
                else:
                    self._heuristic_log_counter += 1
                    if self._heuristic_log_counter % 30 == 0:
                        log_vision_event(
                            "HEURISTIC",
                            str(self.stream_id),
                            f"score={h_score:.3f} threshold={heuristic_threshold:.3f} decision=SKIP"
                        )
            except Exception as e:
                log_debug(f"Hybrid detection error: {e}")
                queue_depth = self.detection_queue.get_queue_size()

            # Update metrics - track hybrid queue depth instead of old pending counter
            self.metrics.update_detection_queue_depth(self.stream_id, queue_depth)
            
            # Periodic FPS adjustment check
            now = time.time()
            if now - self._last_fps_check >= self._fps_check_interval:
                self._last_fps_check = now
                new_fps = self.fps_controller.update(self.stream_id, queue_depth)
                new_interval = self.fps_controller.get_interval_ms(self.stream_id)
                if self.timer.interval() != new_interval:
                    # Request timer interval change from main thread
                    self.set_interval_requested.emit(new_interval)
                self.metrics.update_fps(self.stream_id, new_fps)
        except Exception as e:
            from embereye_base.utils.error_logger import get_error_logger
            get_error_logger().log(self.rtsp_url, f"update_frame error: {e}")
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)
            self.stop_stream()

    def stop_stream(self):
        with QMutexLocker(self.mutex):
            if self.cap and self.cap.isOpened():
                self.cap.release()
            # Request timer stop from main thread (timer lives in GUI thread)
            self.stop_timer_requested.emit()
            self.connection_status.emit(False)

    def _check_if_rtsp(self, url):
        """Check if URL is an RTSP stream (not local device)."""
        url = url.strip().lower()
        return url.startswith('rtsp://') or ('rtsp://' in url and not url.isdigit())
    
    def _configure_rtsp_low_latency(self):
        """Configure VideoCapture properties for minimal RTSP latency."""
        try:
            # Set buffer size to 1 frame (minimum possible) to prevent lag accumulation
            # This is THE MOST CRITICAL setting for real-time RTSP streaming
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            log_debug(f"RTSP buffer size set to 1 for {self.stream_id}")
            
            # Disable any internal buffering
            # Note: Not all backends support these properties
            try:
                self.cap.set(cv2.CAP_PROP_FPS, 30)  # Request 30 FPS
            except:
                pass
            
            log_debug(f"Low-latency RTSP configuration applied to {self.stream_id}")
        except Exception as e:
            log_error(f"Could not set low-latency RTSP properties: {e}")
    
    def _format_url(self, url):
        """Ensure proper RTSP URL formatting with low-latency flags."""
        # Strip whitespace and newlines first
        url = url.strip()
        
        # Treat pure numeric string as a local device index (e.g. '0')
        if url.isdigit():
            return url  # Do NOT prepend rtsp:// or append transport flags

        if not url.startswith("rtsp://"):
            url = "rtsp://" + url
        
        # Add TCP transport with low-latency flags
        lowered = url.lower()
        if "?tcp" not in lowered and "?udp" not in lowered:
            # Use TCP for reliability + add flags for minimal latency
            if "?" in url:
                url += "&tcp"
            else:
                url += "?tcp"
        
        # Add additional low-latency RTSP options if not present
        if "rtsp_transport" not in lowered:
            separator = "&" if "?" in url else "?"
            url += f"{separator}rtsp_transport=tcp"
        
        return url
