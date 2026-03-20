import sys
import cv2
import numpy as np
import time
import glob
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout


# ---------------------- Real-time FPS Counter ----------------------
class FPSCounter:
    def __init__(self, window_size=30):
        self.times = []
        self.window_size = window_size
    
    def update(self):
        self.times.append(time.time())
        if len(self.times) > self.window_size:
            self.times.pop(0)
    
    def get_fps(self):
        if len(self.times) < 2:
            return 0.0
        return (len(self.times)-1) / (self.times[-1] - self.times[0])
    

class CameraCalibrator:
    def __init__(self, chessboard_size=(9,6)):
        self.chessboard_size = chessboard_size
        self.calibration_data = {}
        self.calibration_file = 'camera_calibration.npy'
        self.criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        
        # Prepare object points (0,0,0), (1,0,0), ..., (8,5,0)
        self.objp = np.zeros((chessboard_size[0]*chessboard_size[1],3), np.float32)
        self.objp[:,:2] = np.mgrid[0:chessboard_size[0],0:chessboard_size[1]].T.reshape(-1,2)

    def calibrate(self, image_paths):
        objpoints = []  # 3D points in real world
        imgpoints = []  # 2D points in image plane
        
        for fname in image_paths:
            img = cv2.imread(fname)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Find chessboard corners
            ret, corners = cv2.findChessboardCorners(gray, self.chessboard_size, None)

            if ret:
                objpoints.append(self.objp)
                corners_refined = cv2.cornerSubPix(gray, corners, (11,11), 
                                                 (-1,-1), self.criteria)
                imgpoints.append(corners_refined)

        # Perform camera calibration
        ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
            objpoints, imgpoints, gray.shape[::-1], None, None)

        if ret:
            self.calibration_data = {
                'camera_matrix': mtx,
                'dist_coeffs': dist,
                'reprojection_error': self._compute_reprojection_error(
                    objpoints, imgpoints, mtx, dist, rvecs, tvecs)
            }
            np.save(self.calibration_file, self.calibration_data)
            return True
        return False

    def _compute_reprojection_error(self, objpoints, imgpoints, mtx, dist, rvecs, tvecs):
        mean_error = 0
        for i in range(len(objpoints)):
            imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], 
                                             mtx, dist)
            error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2)/len(imgpoints2)
            mean_error += error
        return mean_error/len(objpoints)

    def load_calibration(self):
        if os.path.exists(self.calibration_file):
            self.calibration_data = np.load(self.calibration_file, 
                                           allow_pickle=True).item()
            return True
        return False

    def undistort(self, frame):
        if self.calibration_data:
            return cv2.undistort(
                frame,
                self.calibration_data['camera_matrix'],
                self.calibration_data['dist_coeffs']
            )
        return frame

class CalibrationValidator:
    @staticmethod
    def validate(image_paths, chessboard_size):
        calibrator = CameraCalibrator(chessboard_size)
        valid_images = []
        reprojection_errors = []
        
        for fname in image_paths:
            img = cv2.imread(fname)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, corners = cv2.findChessboardCorners(gray, chessboard_size, None)
            
            if ret:
                corners_refined = cv2.cornerSubPix(gray, corners, (11,11),
                                                 (-1,-1), calibrator.criteria)
                error = calibrator._compute_reprojection_error(
                    [calibrator.objp], [corners_refined],
                    calibrator.calibration_data['camera_matrix'],
                    calibrator.calibration_data['dist_coeffs'],
                    [np.zeros((3,1))], [np.zeros((3,1))]
                )
                if error < 0.2:
                    valid_images.append(fname)
                    reprojection_errors.append(error)
        
        return valid_images, np.mean(reprojection_errors) if reprojection_errors else float('inf')

class ROSInterface:
    def __init__(self, node_name="room_monitor"):
        try:
            rospy.init_node(node_name, anonymous=True)
            self.bridge = CvBridge()
            self.image_pub = rospy.Publisher("/camera/image_raw", ROSImage, queue_size=1)
            self.initialized = True
        except:
            self.initialized = False
    
    def publish_frame(self, frame):
        if self.initialized and frame is not None:
            try:
                ros_image = self.bridge.cv2_to_imgmsg(frame, "bgr8")
                self.image_pub.publish(ros_image)
            except:
                pass

# ---------------------- PyQt5 GUI Components ----------------------
class VideoStreamWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        self.setLayout(layout)

    def update_image(self, cv_img):
        qt_img = self.convert_cv_qt(cv_img)
        self.image_label.setPixmap(qt_img)
    
    def convert_cv_qt(self, cv_img):
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return QPixmap.fromImage(qt_image)

class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        self.calibrate_btn = QPushButton("Calibrate Camera")
        self.feedback_btn = QPushButton("Provide Feedback")
        self.history_btn = QPushButton("View History")
        self.fps_label = QLabel("FPS: 0.0")
        
        layout = QHBoxLayout()
        layout.addWidget(self.calibrate_btn)
        layout.addWidget(self.feedback_btn)
        layout.addWidget(self.history_btn)
        layout.addWidget(self.fps_label)
        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Ember Eye Monitor")
        self.setGeometry(100, 100, 800, 600)
        
        central_widget = QWidget()
        layout = QVBoxLayout()
        
        self.video_widget = VideoStreamWidget()
        self.control_panel = ControlPanel()
        
        layout.addWidget(self.video_widget)
        layout.addWidget(self.control_panel)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

# ---------------------- Video Processing Thread ----------------------
class VideoThread(QThread):
    change_pixmap = pyqtSignal(np.ndarray)
    update_fps = pyqtSignal(float)
    calibration_complete = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.cap = cv2.VideoCapture(0)
        self.fps_counter = FPSCounter()
        self.calibrator = CameraCalibrator()
        self.validator = CalibrationValidator()
        
        # ROS Integration
        self.ros_interface = ROSInterface() if USE_ROS else None

    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue
                
            processed_frame = self.process_frame(frame)
            self.change_pixmap.emit(processed_frame)
            self.fps_counter.update()
            self.update_fps.emit(self.fps_counter.get_fps())
            
            if self.ros_interface:
                self.ros_interface.publish_frame(processed_frame)
                
    def process_frame(self, frame):
        # Add your processing pipeline here
        frame = cv2.resize(frame, (640, 480))
        cv2.putText(frame, "Processing...", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        return frame
    
    def run_calibration(self):
        # Implement your calibration logic here
        print(glob.glob("calibration_images/*.jpg"))
        self.calibrator.calibrate(glob.glob("calibration_images/*.jpg"))
        self.calibration_complete.emit(True)
        
    def stop(self):
        self.running = False
        self.cap.release()
        if self.ros_interface:
            self.ros_interface.shutdown()

# ---------------------- Integrated Application ----------------------
class EmberEyeApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.main_window = MainWindow()
        self.video_thread = VideoThread()
        
        # Connect signals
        self.video_thread.change_pixmap.connect(self.update_video)
        self.video_thread.update_fps.connect(self.update_fps_display)
        self.main_window.control_panel.calibrate_btn.clicked.connect(
        self.video_thread.run_calibration)
        self.video_thread.calibration_complete.connect(
            self.handle_calibration_result)
        
    def update_video(self, cv_img):
        self.main_window.video_widget.update_image(cv_img)
        
    def update_fps_display(self, fps):
        self.main_window.control_panel.fps_label.setText(f"FPS: {fps:.1f}")
        
    def handle_calibration_result(self, success):
        if success:
            print("Calibration successful!")
        else:
            print("Calibration failed")

    def run(self):
        self.main_window.show()
        self.video_thread.start()
        sys.exit(self.app.exec_())

# ---------------------- Usage ----------------------
if __name__ == "__main__":
    USE_ROS = False  # Set to True if using ROS
    
    eye_app = EmberEyeApp()
    eye_app.run()