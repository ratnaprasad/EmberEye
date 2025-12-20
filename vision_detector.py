import cv2
import numpy as np
import os
import sys
from vision_logger import log_warning, log_debug, log_error

class VisionDetector:
    def __init__(self, yolo_model_path=None):
        self.model = None
        self.model_loaded = False
        
        # Auto-detect bundled model path
        if yolo_model_path is None:
            yolo_model_path = self._get_bundled_model_path()
        
        self.yolo_model_path = yolo_model_path
        
        # Load model at initialization for offline operation
        if yolo_model_path and os.path.exists(yolo_model_path):
            self.load_model(yolo_model_path)
        else:
            log_warning(f"YOLO model not found at {yolo_model_path}. Using heuristic detection only.")

    def _get_bundled_model_path(self):
        """
        Get the path to the bundled YOLO model.
        Works for both development and PyInstaller bundled app.
        """
        # Check if running as PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            base_path = sys._MEIPASS
        else:
            # Running as script
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        model_path = os.path.join(base_path, 'models', 'yolov8n_fire.pt')
        return model_path

    def load_model(self, path):
        """
        Load YOLOv8 model from local file (100% offline).
        """
        try:
            from ultralytics import YOLO
            print(f"Loading YOLO model from: {path}")
            self.model = YOLO(path)
            self.model_loaded = True
            print(f"YOLO model loaded successfully. Classes: {self.model.names if hasattr(self.model, 'names') else 'N/A'}")
        except ImportError:
            print("Warning: ultralytics package not installed. Install with: pip install ultralytics")
            self.model_loaded = False
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            self.model_loaded = False

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
        
        # Smoke: low saturation, high brightness (gray/white smoke)
        lower_smoke = np.array([0, 0, 180])
        upper_smoke = np.array([180, 60, 255])
        mask_smoke = cv2.inRange(hsv, lower_smoke, upper_smoke)
        smoke_pixels = cv2.countNonZero(mask_smoke)
        smoke_ratio = smoke_pixels / (frame.shape[0] * frame.shape[1])
        
        # Combine heuristics with adjusted weights
        # Fire is more critical, so weight it higher
        confidence = min(1.0, fire_ratio * 3 + smoke_ratio * 1.5)
        return confidence

    def yolo_detect(self, frame):
        """
        Run YOLO model on frame. Returns confidence score (0-1).
        Detects fire, smoke, flame, and potentially cigarettes.
        """
        if not self.model_loaded or self.model is None:
            return 0.0
        
        try:
            # Run inference (verbose=False to suppress output)
            results = self.model(frame, verbose=False, conf=0.25)  # 25% confidence threshold
            
            max_conf = 0.0
            detections = []

            # Only consider detections for fire-relevant classes when available
            allowed_names = {"fire", "smoke", "flame", "cigarette", "lighter", "match", "matches"}
            names = {}
            if hasattr(self.model, 'names') and isinstance(self.model.names, (dict, list)):
                # Normalize to dict index->name
                if isinstance(self.model.names, list):
                    names = {i: n for i, n in enumerate(self.model.names)}
                else:
                    names = self.model.names
            # If model doesn't include any fire-relevant class names, ignore YOLO output entirely
            if names and not any(str(n).strip().lower() in allowed_names for n in names.values()):
                return 0.0
            
            for r in results:
                if r.boxes is not None and len(r.boxes) > 0:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        class_id = int(box.cls[0])
                        
                        # Get class name
                        if names:
                            class_name = names.get(class_id, str(class_id))
                        else:
                            class_name = str(class_id)
                        
                        # Consider only fire-relevant classes
                        if str(class_name).strip().lower() in allowed_names:
                            detections.append({
                                'class': class_name,
                                'confidence': conf
                            })
                            if conf > max_conf:
                                max_conf = conf
            
            # Log detections if any found (for debugging)
            if detections and max_conf > 0.5:
                log_debug(f"YOLO detections: {detections[:3]}")  # Log top 3
            
            return max_conf
            
        except Exception as e:
            log_error(f"YOLO inference error: {e}")
            return 0.0

    def detect(self, frame):
        """
        Main entry: run both heuristic and YOLO model, return max confidence.
        Combines fast heuristic with accurate YOLO detection.
        """
        h_score = self.heuristic_fire_smoke(frame)
        y_score = self.yolo_detect(frame)
        
        # Return max of both methods
        final_score = max(h_score, y_score)
        
        # Debug logging for moderate+ scores to aid testing (lowered threshold)
        if final_score >= 0.2:
            try:
                log_debug(f"[VisionDetect] Heuristic={h_score:.3f}, YOLO={y_score:.3f}, Final={final_score:.3f}")
            except Exception:
                pass
        
        return final_score
