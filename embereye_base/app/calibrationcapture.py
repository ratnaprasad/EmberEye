import sys
import cv2
import numpy as np
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, 
                             QPushButton, QVBoxLayout, QWidget, QSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen

class VideoThread(QThread):
    change_pixmap = pyqtSignal(QImage)
    alert_signal = pyqtSignal(str)
    sensor_update = pyqtSignal(dict)
    roi_update = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.running = True
        self.learning = True
        self.background = None
        self.roi_polygon = []
        self.current_roi = []
        self.detect_humans = True
        self.sensor_data = {'smoke': False, 'heat': 25}
        self.grid_rows = 3  # Configurable grid rows
        self.grid_cols = 3  # Configurable grid columns

        # Initialize detectors
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, detectShadows=False)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


    def run(self):
        cap = cv2.VideoCapture(0)
        while self.running:
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (640, 480))
                processed_frame, alerts = self.process_frame(frame)
                self.update_sensors()
                
                if alerts:
                    self.alert_signal.emit(" | ".join(alerts))

                # Draw ROI directly on the frame
                processed_frame = self.draw_roi(processed_frame)
                
                rgb_image = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.change_pixmap.emit(qt_image)

        cap.release()

    def draw_grid(self, frame, polygon):
        if len(polygon) < 3:
            return frame  # Need at least 3 points for a polygon
            
        # Create mask for ROI area
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 255)
        
        # Get bounding rectangle of ROI
        x, y, w, h = cv2.boundingRect(np.array(polygon, dtype=np.int32))
        
        # Calculate grid spacing
        cell_width = max(1, w // self.grid_cols)
        cell_height = max(1, h // self.grid_rows)
        
        # Create grid overlay image
        grid_overlay = np.zeros_like(frame)
        
        # Draw vertical grid lines (corrected coordinates)
        for i in range(1, self.grid_cols):
            x_line = x + i * cell_width
            cv2.line(grid_overlay, 
                    (x_line, y), 
                    (x_line, y + h), 
                    (255, 255, 0), 1, lineType=cv2.LINE_AA)
        
        # Draw horizontal grid lines (corrected coordinates)
        for i in range(1, self.grid_rows):
            y_line = y + i * cell_height
            cv2.line(grid_overlay, 
                    (x, y_line), 
                    (x + w, y_line), 
                    (255, 255, 0), 1, lineType=cv2.LINE_AA)
        
        # Apply mask to only show grid within ROI
        grid_masked = cv2.bitwise_and(grid_overlay, grid_overlay, mask=mask)
        
        # Blend grid with original frame
        return cv2.addWeighted(frame, 1, grid_masked, 0.3, 0)

    def draw_roi(self, frame):
        # Draw finalized ROI polygon and grid
        if self.roi_polygon:
            # Draw polygon outline
            pts = np.array(self.roi_polygon, np.int32).reshape((-1,1,2))
            cv2.polylines(frame, [pts], True, (0,0,255), 2)
            
            # Draw grid and update frame
            frame = self.draw_grid(frame, self.roi_polygon)
        
        return frame

    def update_grid_size(self, rows, cols):
        self.grid_rows = rows
        self.grid_cols = cols


    @pyqtSlot(list)
    def update_roi(self, points):
        """Update the current ROI points from the GUI"""
        self.current_roi = points.copy()
        if not self.draw_roi and len(points) > 2:
            self.roi_polygon = points.copy()

    def process_frame(self, frame):
        alerts = []
        
        # 1. Background Learning
        fg_mask = self.bg_subtractor.apply(frame)
        if self.learning:
            self.background = self.bg_subtractor.getBackgroundImage()
            if np.count_nonzero(fg_mask) < 500:
                self.learning = False

        # 2. Human Detection
        if self.detect_humans and not self.learning:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            (humans, _) = self.hog.detectMultiScale(gray, winStride=(4, 4),
                                                    padding=(8, 8), scale=1.05)
            for (x, y, w, h) in humans:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                if self.check_roi_intrusion(x, y, w, h):
                    alerts.append("Human in restricted area!")

        # 3. Fire Detection
        fire_alert = self.detect_fire(frame)
        if fire_alert or self.sensor_data['smoke'] or self.sensor_data['heat'] > 60:
            alerts.append("Fire hazard detected!")

        # 4. Object Change Detection
        if not self.learning and self.background is not None:
            change = self.detect_object_changes(frame)
            if change:
                alerts.append("Object changes detected!")

        return frame, alerts

    def detect_fire(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 120, 70])
        upper = np.array([20, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        return np.count_nonzero(mask) > 5000

    def detect_object_changes(self, frame):
        diff = cv2.absdiff(frame, self.background)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(cv2.contourArea(cnt) > 500 for cnt in contours)

    def check_roi_intrusion(self, x, y, w, h):
        if not self.roi_polygon:
            return False
            
        # Check if any point of the bounding box is inside the polygon
        points = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
        return any(self.point_in_polygon(p, self.roi_polygon) for p in points)

    def point_in_polygon(self, point, polygon):
        x, y = point
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(n+1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xints = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
                        if p1x == p2x or x <= xints:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def update_sensors(self):
        # Simulate sensor data
        self.sensor_data = {
            'smoke': random.random() < 0.02,  # 2% chance of smoke
            'heat': random.randint(20, 80)     # Random heat values
        }
        self.sensor_update.emit(self.sensor_data)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Room Monitor")
        self.setGeometry(100, 100, 800, 600)
        
        # Video Display
        self.video_label = QLabel(self)
        self.video_label.setFixedSize(640, 480)
        self.video_label.setAlignment(Qt.AlignCenter)
        
        # Controls
        self.start_btn = QPushButton("Start Monitoring", self)
        self.start_btn.clicked.connect(self.toggle_monitoring)
        self.roi_btn = QPushButton("Set ROI", self)
        self.roi_btn.clicked.connect(self.start_drawing_roi)
        
        # Grid controls
        self.grid_rows = QSpinBox(self)
        self.grid_rows.setRange(1, 10)
        self.grid_rows.setValue(3)
        self.grid_cols = QSpinBox(self)
        self.grid_cols.setRange(1, 10)
        self.grid_cols.setValue(3)
        self.grid_btn = QPushButton("Update Grid", self)
        self.grid_btn.clicked.connect(self.update_grid)
        
        # Status Bar
        self.status = self.statusBar()
        
        # Layout
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.video_label)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.roi_btn)
        layout.addWidget(QLabel("Grid Rows:"))
        layout.addWidget(self.grid_rows)
        layout.addWidget(QLabel("Grid Columns:"))
        layout.addWidget(self.grid_cols)
        layout.addWidget(self.grid_btn)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # Thread Setup
        self.thread = VideoThread()
        self.thread.change_pixmap.connect(self.set_image)
        self.thread.alert_signal.connect(self.show_alert)
        self.thread.sensor_update.connect(self.update_sensors)
        self.thread.roi_update.connect(self.thread.update_roi)
        
        self.monitoring = False
        self.drawing_roi = False
        self.roi_points = []

    def update_grid(self):
        rows = self.grid_rows.value()
        cols = self.grid_cols.value()
        self.thread.update_grid_size(rows, cols)

    def toggle_monitoring(self):
        if not self.monitoring:
            self.thread.start()
            self.start_btn.setText("Stop Monitoring")
            self.monitoring = True
        else:
            self.thread.running = False
            self.start_btn.setText("Start Monitoring")
            self.monitoring = False

    def start_drawing_roi(self):
        self.drawing_roi = True
        self.roi_points = []
        self.status.showMessage("Click to draw ROI polygon, right-click to finish")
    
    def mousePressEvent(self, event):
        if self.drawing_roi:
            # Convert to video label coordinates
            pos = event.pos()
            local_pos = self.video_label.mapFrom(self, pos)
            
            if 0 <= local_pos.x() < 640 and 0 <= local_pos.y() < 480:
                self.roi_points.append((local_pos.x(), local_pos.y()))
                # Emit updated ROI points to the thread
                self.thread.roi_update.emit(self.roi_points.copy())
                
                if event.button() == Qt.RightButton:
                    self.drawing_roi = False
                    self.thread.roi_update.emit(self.roi_points.copy())
                    self.status.showMessage(f"ROI set with {len(self.roi_points)} points")

    @pyqtSlot(QImage)
    def set_image(self, image):
        self.video_label.setPixmap(QPixmap.fromImage(image))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drawing_roi and self.roi_points:
            painter = QPainter(self)
            painter.setPen(QPen(Qt.red, 2))
            for i in range(len(self.roi_points)-1):
                painter.drawLine(QPoint(*self.roi_points[i]), 
                               QPoint(*self.roi_points[i+1]))
            if len(self.roi_points) > 1:
                painter.drawLine(QPoint(*self.roi_points[-1]), 
                                QPoint(*self.roi_points[0]))

    @pyqtSlot(QImage)
    def set_image(self, image):
        self.video_label.setPixmap(QPixmap.fromImage(image))

    @pyqtSlot(str)
    def show_alert(self, message):
        self.status.showMessage(message)
        # Add actual alert actions (sound, notifications) here

    @pyqtSlot(dict)
    def update_sensors(self, data):
        sensor_text = f"Smoke: {data['smoke']} | Heat: {data['heat']}°C"
        self.status.showMessage(sensor_text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())