import cv2
import numpy as np

class VisionDetector:
    def __init__(self, yolo_model_path=None):
        self.yolo_model_path = yolo_model_path
        self.model = None
        if yolo_model_path:
            self.load_model(yolo_model_path)

    def load_model(self, path):
        # Placeholder: load YOLOv8 or other model here
        # Example: self.model = YOLO(path)
        pass

    def heuristic_fire_smoke(self, frame):
        """
        Fast OpenCV-based fire/smoke detection.
        Returns: confidence score (0-1)
        """
        # Fire: look for high saturation, warm colors (HSV)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_fire = np.array([0, 100, 100])
        upper_fire = np.array([40, 255, 255])
        mask_fire = cv2.inRange(hsv, lower_fire, upper_fire)
        fire_pixels = cv2.countNonZero(mask_fire)
        fire_ratio = fire_pixels / (frame.shape[0] * frame.shape[1])
        # Smoke: low saturation, high brightness
        lower_smoke = np.array([0, 0, 180])
        upper_smoke = np.array([180, 60, 255])
        mask_smoke = cv2.inRange(hsv, lower_smoke, upper_smoke)
        smoke_pixels = cv2.countNonZero(mask_smoke)
        smoke_ratio = smoke_pixels / (frame.shape[0] * frame.shape[1])
        # Combine heuristics
        confidence = min(1.0, fire_ratio * 2 + smoke_ratio)
        return confidence

    def yolo_detect(self, frame):
        """
        Run YOLO or other model on frame. Returns confidence score (0-1).
        """
        # Placeholder: run model inference and return score
        # Example: results = self.model(frame)
        # return max([r.confidence for r in results if r.class in ['fire','smoke','flame']], default=0)
        return 0.0

    def detect(self, frame):
        """
        Main entry: run heuristic and model, return max confidence.
        """
        h_score = self.heuristic_fire_smoke(frame)
        y_score = self.yolo_detect(frame)
        return max(h_score, y_score)
