
from video_worker import VideoWorker
from PyQt5.QtWidgets import (
    QLabel
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal 
)


class VideoWidget(QLabel):

    maximize_requested = pyqtSignal()
    minimize_requested = pyqtSignal()

    def __init__(self, rtsp_url, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        self.maximized = False
        self.original_size = None
        
        # Initialize worker and thread
        self.worker = VideoWorker(rtsp_url)
        self.worker_thread = QThread()
        
        # Move worker to thread
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals
        self.worker.frame_ready.connect(self.update_frame)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.connection_status.connect(self.handle_connection_status)
        
        # Connect timer signal
        self.worker.timer.timeout.connect(self.worker.update_frame)
        
        # Start worker thread
        self.worker_thread.started.connect(self.worker.start_stream)
        self.worker_thread.start()
        
    def update_frame(self, pixmap):
        try:
            self.setPixmap(pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        except Exception as e:
            self.handle_error(str(e))

    def handle_error(self, message):
        self.setText(f"ERROR: {message}\n{self.worker.rtsp_url}")
        self.setStyleSheet("color: red; background-color: black; padding: 5px;")

    def handle_connection_status(self, connected):
        if connected:
            self.setText("")
            self.setStyleSheet("background-color: black;")
        else:
            self.setText("Reconnecting...\n" + self.worker.rtsp_url)
            self.setStyleSheet("color: yellow; background-color: black; padding: 5px;")

    def resizeEvent(self, event):
        if self.pixmap() and not self.pixmap().isNull():
            self.setPixmap(self.pixmap().scaled(
                event.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        super().resizeEvent(event)

    def stop(self):
        """Clean up worker and thread"""
        try:
            self.worker.stop_stream()
            self.worker_thread.quit()
            if not self.worker_thread.wait(2000):
                self.worker_thread.terminate()
        except Exception as e:
            print(f"Error stopping worker: {str(e)}")

    def resizeEvent(self, event):
        """Handle widget resizing"""
        try:
            current_pixmap = self.pixmap()
            if current_pixmap and not current_pixmap.isNull():
                self.setPixmap(current_pixmap.scaled(event.size(), 
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            self.handle_error(f"Resize error: {str(e)}")
        super().resizeEvent(event)

    def deleteLater(self):
        """Ensure proper cleanup"""
        self.stop()
        super().deleteLater()
