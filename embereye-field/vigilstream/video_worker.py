import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

print("[VIDEO_WORKER_MODULE] Loading video_worker.py with NEW CODE v2.0", flush=True)

import cv2

from PyQt5.QtWidgets import (
    QApplication
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QMutex, QMutexLocker,
    QObject, QMetaObject, Q_ARG
)

from embereye.core.vision_detector import VisionDetector
from embereye.core.pipeline_logs import log_vision_event
from shared.emberkit import log_debug, log_error
from debug_config import is_debug_enabled
from shared.emberkit import get_fps_controller
from shared.emberkit import get_metrics
# Hybrid detection system imports
import threading
import time
from embereye.core.detection_queue import get_detection_queue, FrameMetadata
from embereye.core.detection_worker import get_detection_worker, stop_detection_worker

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
        self._detection_overlay_ttl_ms = 1500
        self._detection_counter = 0
        self._last_frame_size = None
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
        box_mode_env = str(os.environ.get("EMBEREYE_BBOX_MODE", "all")).strip().lower()
        self.detection_box_mode = box_mode_env if box_mode_env in ("all", "specific") else "all"
        box_classes_env = str(os.environ.get("EMBEREYE_BBOX_CLASSES", "")).strip()
        self.detection_box_classes = set(class_name.strip() for class_name in box_classes_env.split(';') if class_name.strip())

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
            detections = result.detections
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
            
            # ONLY emit anomaly if YOLO confirmed detection (>= 0.50)
            # This prevents heuristic false positives from appearing in Anomalies tab
            if detections:
                self.detection_event.emit(status, yolo_score, detections or [], self._last_frame_size)

            log_vision_event(
                "YOLO",
                str(self.stream_id),
                f"status={status} conf={confidence:.3f} yolo_score={yolo_score:.3f} det={len(detections or [])} class={primary_class or '-'} latency_ms={yolo_latency:.1f}"
            )

            if status in ['CONFIRMED', 'POSSIBLE'] and len(detections) > 0:
                # Emit anomaly frame with YOLO results
                if self._last_qimage:
                    print(f"[DETECTION_RESULT] Emitting anomaly: stream={self.stream_id}, status={status}, yolo={yolo_score:.3f}, detections={len(detections)}", flush=True)
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

            for det in detections:
                bbox = det.get('bbox')
                if not bbox or len(bbox) != 4:
                    continue

                x1, y1, x2, y2 = [int(v) for v in bbox]
                class_name = det.get('class', 'UNKNOWN')
                conf = float(det.get('confidence', 0.0))

                if self.detection_box_mode == 'specific' and class_name not in self.detection_box_classes:
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
                    backend_codes = [getattr(cv2, 'CAP_ANY', 0)]
                    # macOS: AVFoundation
                    if hasattr(cv2, 'CAP_AVFOUNDATION'):
                        backend_codes.append(getattr(cv2, 'CAP_AVFOUNDATION'))
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
            from error_logger import get_error_logger
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
                    raise RuntimeError("No frame received")

            # Record frame processed
            self.metrics.record_frame_processed(self.stream_id)

            # Draw detections on frame BEFORE display (fast path)
            display_frame = frame.copy()
            display_frame = self._draw_hybrid_detections(display_frame)
            display_frame = self._draw_detection_counter(display_frame)

            # Convert for display immediately (fast path)
            frame_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
            self.frame_ready.emit(QPixmap.fromImage(q_img))
            # Keep a copy for anomaly capture (thread-safe copy created above)
            self._last_qimage = q_img
            self._last_frame_size = (w, h)
            
            # HYBRID DETECTION: Heuristic-first, then queue for YOLO if needed
            try:
                # Step 1: Fast heuristic detection on current frame
                h_score = self.vision_detector.heuristic_fire_smoke(frame)
                heuristic_threshold = self.heuristic_threshold
                force_sample = (self._detection_frame_id % self.force_yolo_every_n_frames) == 0
                should_queue = h_score >= heuristic_threshold or force_sample
                queue_reason = "HEURISTIC" if h_score >= heuristic_threshold else "PERIODIC_SAMPLE"
                
                if is_debug_enabled():
                    print(f"[HYBRID_DETECTION] stream={self.stream_id}, heuristic={h_score:.3f}, threshold={heuristic_threshold}", flush=True)
                
                # Step 2: If heuristic score is above threshold, queue for YOLO validation
                # This prevents obvious non-hazards from being sent to YOLO
                if should_queue:
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

            # Update metrics - track hybrid queue depth instead of old pending counter
            queue_depth = self.detection_queue.get_queue_size()
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
            from error_logger import get_error_logger
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
