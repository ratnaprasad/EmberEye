import cv2
import numpy as np
import os
import glob
import json
from PyQt5.QtCore import pyqtSignal, QObject

class CameraCalibrator(QObject):
    calibration_progress = pyqtSignal(int, int)  # current, total
    calibration_complete = pyqtSignal(dict)
    calibration_failed = pyqtSignal(str)

    def __init__(self, chessboard_size=(9,6)):
        super().__init__()
        self.chessboard_size = chessboard_size
        self.calibration_data = {
            'matrix': None,
            'distortion': None,
            'reprojection_error': None
        }
        self.criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        
        # Prepare 3D object points (0,0,0), (1,0,0), ..., (chessboard_w-1,chessboard_h-1,0)
        self.objp = np.zeros((chessboard_size[0]*chessboard_size[1],3), np.float32)
        self.objp[:,:2] = np.mgrid[0:chessboard_size[0],0:chessboard_size[1]].T.reshape(-1,2)

    def calibrate_from_images(self, image_paths):
        """Main calibration routine using saved images"""
        objpoints = []  # 3D point arrays
        imgpoints = []  # 2D point arrays
        
        valid_images = []
        for idx, fpath in enumerate(image_paths):
            self.calibration_progress.emit(idx+1, len(image_paths))
            
            img = cv2.imread(fpath)
            if img is None:
                continue
                
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, corners = self._find_chessboard_corners(gray)
            
            if ret:
                objpoints.append(self.objp)
                imgpoints.append(corners)
                valid_images.append(fpath)

        if len(valid_images) < 10:
            self.calibration_failed.emit(f"Need at least 10 valid images (found {len(valid_images)})")
            return False

        try:
            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                objpoints, imgpoints, gray.shape[::-1], None, None
            )
            
            if not ret:
                self.calibration_failed.emit("Calibration matrix calculation failed")
                return False

            self.calibration_data['matrix'] = mtx
            self.calibration_data['distortion'] = dist
            self.calibration_data['reprojection_error'] = self._calculate_reprojection_error(
                objpoints, imgpoints, rvecs, tvecs, mtx, dist
            )
            
            self.calibration_complete.emit(self.calibration_data)
            return True
            
        except Exception as e:
            self.calibration_failed.emit(str(e))
            return False

    def _find_chessboard_corners(self, gray_img):
        """Find and refine chessboard corners with subpixel accuracy"""
        ret, corners = cv2.findChessboardCorners(gray_img, self.chessboard_size, None)
        if ret:
            corners_refined = cv2.cornerSubPix(
                gray_img, corners, (11,11), (-1,-1), self.criteria
            )
            return True, corners_refined
        return False, None

    def _calculate_reprojection_error(self, objpoints, imgpoints, rvecs, tvecs, mtx, dist):
        """Calculate mean reprojection error for calibration quality assessment"""
        mean_error = 0
        for i in range(len(objpoints)):
            imgpoints2, _ = cv2.projectPoints(
                objpoints[i], rvecs[i], tvecs[i], mtx, dist
            )
            error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2)/len(imgpoints2)
            mean_error += error
        return mean_error/len(objpoints)

    def save_calibration(self, file_path):
        """Save calibration data to JSON file"""
        data = {
            'camera_matrix': self.calibration_data['matrix'].tolist(),
            'distortion_coefficients': self.calibration_data['distortion'].tolist(),
            'reprojection_error': self.calibration_data['reprojection_error'],
            'resolution': self.resolution,
            'chessboard_size': self.chessboard_size
        }
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_calibration(self, file_path):
        """Load calibration data from JSON file"""
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        self.calibration_data['matrix'] = np.array(data['camera_matrix'])
        self.calibration_data['distortion'] = np.array(data['distortion_coefficients'])
        self.calibration_data['reprojection_error'] = data['reprojection_error']
        self.chessboard_size = tuple(data['chessboard_size'])
        self.resolution = tuple(data['resolution'])

    def undistort_frame(self, frame):
        """Apply undistortion to a frame using calibration data"""
        if self.calibration_data['matrix'] is not None:
            h, w = frame.shape[:2]
            new_mtx, roi = cv2.getOptimalNewCameraMatrix(
                self.calibration_data['matrix'],
                self.calibration_data['distortion'],
                (w,h), 1, (w,h))
            return cv2.undistort(
                frame, self.calibration_data['matrix'],
                self.calibration_data['distortion'], None, new_mtx
            )
        return frame

class CalibrationImageCollector:
    """Helper class for interactive calibration image collection"""
    def __init__(self, output_dir="calibration_frames"):
        self.output_dir = output_dir
        self.counter = 0
        os.makedirs(output_dir, exist_ok=True)

    def capture_frame(self, frame):
        """Save frame with chessboard detection"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ret, _ = cv2.findChessboardCorners(gray, self.chessboard_size, None)
        
        if ret:
            path = os.path.join(self.output_dir, f"calib_{self.counter:04d}.jpg")
            cv2.imwrite(path, frame)
            self.counter += 1
            return True
        return False
