import glob
import sys
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QDialog,QProgressBar, QMessageBox
from camera_calibrator import CalibrationImageCollector, CameraCalibrator 
class CalibrationWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.calibrator = CameraCalibrator()
        self.collector = CalibrationImageCollector()
        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        self.setWindowTitle("Camera Calibration")
        self.setFixedSize(800, 600)
        
        self.video_label = QLabel(self)
        self.status_label = QLabel("Press 'C' to capture frames", self)
        self.progress_bar = QProgressBar(self)
        
        layout = QVBoxLayout()
        layout.addWidget(self.video_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def connect_signals(self):
        self.calibrator.calibration_progress.connect(self.update_progress)
        self.calibrator.calibration_complete.connect(self.handle_success)
        self.calibrator.calibration_failed.connect(self.handle_failure)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C:
            self.capture_frame()

    def capture_frame(self):
        if self.collector.capture_frame(self.current_frame):
            self.status_label.setText(f"Captured {self.collector.counter} frames")

    def start_calibration(self):
        images = glob.glob(os.path.join(self.collector.output_dir, "*.jpg"))
        if len(images) < 10:
            self.status_label.setText("Need at least 10 captured frames!")
            return
            
        self.progress_bar.setRange(0, len(images))
        self.calibrator.calibrate_from_images(images)

    def update_progress(self, current, total):
        self.progress_bar.setValue(current)

    def handle_success(self, data):
        QMessageBox.information(
            self, "Success",
            f"Calibration complete!\nReprojection error: {data['reprojection_error']:.2f}px"
        )
        self.accept()

    def handle_failure(self, message):
        QMessageBox.critical(self, "Error", message)
        self.reject()


if __name__ == "__main__":
    USE_ROS = False  # Set to True if using ROS
    app = QApplication(sys.argv)
    # app.show()
    if app.exec_() == QDialog.Accepted:
        calibrator = app.calibrator
        calibrator.show()
        calibrator.save_calibration("camera_calibration.json")
        