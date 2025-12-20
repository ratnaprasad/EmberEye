import cv2

from PyQt5.QtWidgets import (
    QApplication
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QMutex, QMutexLocker,
    QObject, QMetaObject, Q_ARG
)


from vision_detector import VisionDetector
from vision_logger import log_debug, log_error
from concurrent.futures import ThreadPoolExecutor
from adaptive_fps import get_controller as get_fps_controller
from metrics import get_metrics

class VideoWorker(QObject):
    frame_ready = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    connection_status = pyqtSignal(bool)
    vision_score_ready = pyqtSignal(float)  # New signal for fire/smoke confidence
    # Emit when an anomaly frame is captured: QImage (thread-safe), score, stream_id, yolo_score
    anomaly_frame_ready = pyqtSignal(QImage, float, str, float)
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
        self.vision_detector = VisionDetector()
        # Thread pool for asynchronous vision detection to prevent blocking capture loop
        self.detection_pool = ThreadPoolExecutor(max_workers=4)
        self._pending_detections = 0  # simple backpressure counter
        # Adaptive FPS controller and metrics
        self.fps_controller = get_fps_controller()
        self.metrics = get_metrics()
        self._last_fps_check = 0
        self._fps_check_interval = 1.0  # Check FPS adjustment every second
        # Anomaly capture
        self.anomaly_threshold = 0.4
        self._last_qimage = None
        # RTSP buffer management for low latency
        self._is_rtsp_stream = self._check_if_rtsp(rtsp_url)
        self._frame_skip_count = 0  # Track frames skipped for buffer drain

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
                self.connection_status.emit(True)

        except Exception as e:
            from error_logger import get_error_logger
            get_error_logger().log(self.rtsp_url, f"start_stream error: {e}")
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)

    def update_frame(self):
        try:
            import time
            with QMutexLocker(self.mutex):
                if not self.cap or not self.cap.isOpened():
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

            # Convert for display immediately (fast path)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
            self.frame_ready.emit(QPixmap.fromImage(q_img))
            # Keep a copy for anomaly capture (thread-safe copy created above)
            self._last_qimage = q_img

            # Submit vision detection asynchronously if backlog is low
            if self._pending_detections < 8:  # simple cap to avoid unbounded queue
                self._pending_detections += 1
                future = self.detection_pool.submit(self._detect_safe, frame, time.time())
                future.add_done_callback(self._on_detection_done)
            else:
                # Drop frame due to backpressure
                self.metrics.record_frame_dropped(self.stream_id)
            
            # Update metrics and adaptive FPS
            self.metrics.update_detection_queue_depth(self.stream_id, self._pending_detections)
            
            # Periodic FPS adjustment check
            now = time.time()
            if now - self._last_fps_check >= self._fps_check_interval:
                self._last_fps_check = now
                new_fps = self.fps_controller.update(self.stream_id, self._pending_detections)
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

    def _detect_safe(self, frame, start_time):
        try:
            import time
            # Get heuristic and YOLO separately
            h_score = self.vision_detector.heuristic_fire_smoke(frame)
            y_score = self.vision_detector.yolo_detect(frame)
            score = max(h_score, y_score)
            latency_ms = (time.time() - start_time) * 1000
            return (score, y_score, latency_ms)
        except Exception as e:
            log_error(f"Vision detection error: {e}")
            return (None, 0, 0)

    def _on_detection_done(self, future):
        self._pending_detections = max(0, self._pending_detections - 1)
        result = future.result()
        if result:
            score, yolo_score, latency_ms = result
            if score is not None:
                # Record metrics
                self.metrics.record_vision_latency(self.stream_id, latency_ms)
                try:
                    # Lightweight debug log for visibility during tests
                    log_debug(f"[Vision] {self.stream_id} score={score:.3f}, yolo={yolo_score:.3f}, latency={latency_ms:.1f}ms")
                except Exception:
                    pass
                # Emit signal on GUI thread
                self.vision_score_ready.emit(score)
                # Capture anomaly frame when:
                # 1. YOLO detected fire-related class (yolo_score > 0), OR
                # 2. High heuristic score (>= 0.6) indicating likely fire/smoke
                # This allows heuristic-based capture when YOLO model doesn't have fire classes
                try:
                    if ((yolo_score > 0 or score >= 0.6) and score >= getattr(self, 'anomaly_threshold', 0.4) 
                        and self._last_qimage is not None):
                        # Emit QImage with both scores
                        self.anomaly_frame_ready.emit(self._last_qimage, score, str(self.stream_id), yolo_score)
                except Exception as e:
                    log_error(f"Anomaly emit error: {e}")

    def stop_stream(self):
        with QMutexLocker(self.mutex):
            if self.cap and self.cap.isOpened():
                self.cap.release()
            # Request timer stop from main thread (timer lives in GUI thread)
            self.stop_timer_requested.emit()
            self.connection_status.emit(False)
        # Shutdown detection pool (non-blocking attempt)
        try:
            self.detection_pool.shutdown(wait=False)
        except Exception:
            pass

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
