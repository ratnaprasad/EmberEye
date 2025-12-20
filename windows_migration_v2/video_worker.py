import cv2

from PyQt5.QtWidgets import (
    QApplication
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QMutex, QMutexLocker, 
    QObject, QMetaObject
)


from vision_detector import VisionDetector

class VideoWorker(QObject):
    frame_ready = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    connection_status = pyqtSignal(bool)
    vision_score_ready = pyqtSignal(float)  # New signal for fire/smoke confidence

    def __init__(self, rtsp_url):
        super().__init__()
        self.rtsp_url = self._format_url(rtsp_url)
        self.mutex = QMutex()
        self.cap = None
        self.timer = QTimer()
        self.timer.moveToThread(QApplication.instance().thread())  # Move timer to main thread
        self.timer.setInterval(30)  # ~33 FPS
        self.vision_detector = VisionDetector()

    def start_stream(self):
        try:
            with QMutexLocker(self.mutex):
                if self.cap and self.cap.isOpened():
                    return
                # Attempt to open the configured stream URL first
                open_attempts = []
                self.cap = cv2.VideoCapture(self.rtsp_url)
                open_attempts.append(f"OpenCV default backend -> {'OK' if self.cap.isOpened() else 'FAIL'}")

                # Fallback: try FFMPEG explicitly if not opened and backend exists
                if not self.cap.isOpened():
                    try:
                        tmp_cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                        open_attempts.append(f"CAP_FFMPEG backend -> {'OK' if tmp_cap.isOpened() else 'FAIL'}")
                        if tmp_cap.isOpened():
                            # Replace cap with successful fallback
                            self.cap.release()
                            self.cap = tmp_cap
                    except Exception as fe:
                        open_attempts.append(f"CAP_FFMPEG exception: {fe}")

                # Final fallback: if URL looks like integer device id, try local device
                if (not self.cap.isOpened()) and self.rtsp_url:
                    try:
                        # Extract potential device index from raw original url before formatting
                        raw = self.rtsp_url.replace('rtsp://', '').split('?')[0]
                        if raw.isdigit():
                            dev_index = int(raw)
                            tmp_cap = cv2.VideoCapture(dev_index)
                            open_attempts.append(f"Local device {dev_index} -> {'OK' if tmp_cap.isOpened() else 'FAIL'}")
                            if tmp_cap.isOpened():
                                self.cap.release()
                                self.cap = tmp_cap
                    except Exception as de:
                        open_attempts.append(f"Device fallback exception: {de}")

                if not self.cap.isOpened():
                    attempts_str = '; '.join(open_attempts)
                    raise ConnectionError(f"Failed to open stream. Attempts: {attempts_str}")

                # Start timer in main thread context
                QMetaObject.invokeMethod(
                    self.timer,
                    'start',
                    Qt.QueuedConnection
                )
                self.connection_status.emit(True)

        except Exception as e:
            from error_logger import get_error_logger
            get_error_logger().log(self.rtsp_url, f"start_stream error: {e}")
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)

    def update_frame(self):
        try:
            with QMutexLocker(self.mutex):
                if not self.cap.isOpened():
                    return

                ret, frame = self.cap.read()
                if ret:
                    # Fire/smoke vision detection (BGR frame)
                    try:
                        score = self.vision_detector.detect(frame)
                        self.vision_score_ready.emit(score)
                    except Exception as e:
                        print(f"Vision detection error: {e}")
                    # Convert for display
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    bytes_per_line = ch * w
                    q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                    self.frame_ready.emit(QPixmap.fromImage(q_img))
                else:
                    raise RuntimeError("No frame received")

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
            # Stop timer in main thread context
            QMetaObject.invokeMethod(
                self.timer,
                'stop',
                Qt.QueuedConnection
            )
            self.connection_status.emit(False)

    def _format_url(self, url):
        """Ensure proper RTSP URL formatting"""
        if not url.startswith("rtsp://"):
            url = "rtsp://" + url
        if "?tcp" not in url and "?udp" not in url:
            url += "?tcp"  # Force TCP transport
        return url
