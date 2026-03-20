import cv2
from PyQt5.QtCore import (
    pyqtSignal, QObject
)

class StreamTester(QObject):
    test_complete = pyqtSignal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cap = None

    def test_stream(self):
        try:
            # # URL validation
            # if not re.match(r'^rtsp?://[\w\-\.]+(:\d+)?(/[\w\-\.]*)*$', self.url):
            #     self.test_complete.emit(False, "Invalid RTSP URL format")
            #     return

            # Connection test with timeout
            self.cap = cv2.VideoCapture(self.url)
            if not self.cap.isOpened():
                self.test_complete.emit(False, "Failed to open stream")
                return

            # Frame read test
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.test_complete.emit(True, "Connection successful")
            else:
                self.test_complete.emit(False, "No frames received")

        except Exception as e:
            self.test_complete.emit(False, str(e))
        finally:
            if self.cap and self.cap.isOpened():
                self.cap.release()
