"""
Anomalies Module for EmberEye.
Thermal vision analysis, ROI extraction, anomaly detection, and YOLO training.
"""

import cv2
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import os
import json

@dataclass
class AnomalyRecord:
    """Record of a detected anomaly."""
    timestamp: datetime
    anomaly_type: str  # 'temperature', 'smoke', 'flame', 'gas', 'motion'
    severity: str  # 'low', 'medium', 'high', 'critical'
    location: str
    description: str
    sensor_values: Dict = field(default_factory=dict)
    frame_path: Optional[str] = None
    roi_coords: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'anomaly_type': self.anomaly_type,
            'severity': self.severity,
            'location': self.location,
            'description': self.description,
            'sensor_values': self.sensor_values,
            'frame_path': self.frame_path,
            'roi_coords': self.roi_coords
        }

class ThermalROIExtractor:
    """Extract Regions of Interest from thermal frames."""
    
    def __init__(self, temp_threshold=40.0, min_area=100):
        self.temp_threshold = temp_threshold
        self.min_area = min_area
    
    def extract_hotspots(self, thermal_frame: np.ndarray, temperature_matrix: np.ndarray):
        """
        Extract hot regions from thermal frame.
        Returns list of (x, y, w, h, max_temp) tuples.
        """
        hotspots = []
        
        # Create binary mask of regions above threshold
        mask = (temperature_matrix > self.temp_threshold).astype(np.uint8) * 255
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # Get max temperature in this ROI
            roi_temps = temperature_matrix[y:y+h, x:x+w]
            max_temp = np.max(roi_temps)
            
            hotspots.append((x, y, w, h, max_temp))
        
        return hotspots
    
    def extract_roi_image(self, frame: np.ndarray, x: int, y: int, w: int, h: int):
        """Extract ROI image from frame."""
        return frame[y:y+h, x:x+w].copy()

class AnomaliesManager:
    """Manage anomaly records with persistence."""
    
    def __init__(self, storage_file="anomalies.json"):
        self.storage_file = storage_file
        self.anomalies: List[AnomalyRecord] = []
        self.load_anomalies()
    
    def add_anomaly(self, anomaly: AnomalyRecord):
        """Add new anomaly record."""
        self.anomalies.append(anomaly)
        self.save_anomalies()
    
    def get_recent_anomalies(self, count=50) -> List[AnomalyRecord]:
        """Get most recent anomalies."""
        return sorted(self.anomalies, key=lambda x: x.timestamp, reverse=True)[:count]
    
    def save_anomalies(self):
        """Save anomalies to JSON file."""
        try:
            data = [a.to_dict() for a in self.anomalies]
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ANOMALIES] Error saving: {e}")
    
    def load_anomalies(self):
        """Load anomalies from JSON file."""
        if not os.path.exists(self.storage_file):
            return
        
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
            
            self.anomalies = []
            for item in data:
                item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                self.anomalies.append(AnomalyRecord(**item))
        except Exception as e:
            print(f"[ANOMALIES] Error loading: {e}")

class ThermalVisionAnalyzer:
    """Analyze thermal vision data for anomalies."""
    
    def __init__(self):
        self.roi_extractor = ThermalROIExtractor()
        self.baseline_temps = {}  # location -> baseline_temp
    
    def analyze_frame(self, frame: np.ndarray, temperature_matrix: np.ndarray, 
                     location: str) -> List[AnomalyRecord]:
        """
        Analyze thermal frame for anomalies.
        Returns list of detected anomalies.
        """
        anomalies = []
        
        # Extract hotspots
        hotspots = self.roi_extractor.extract_hotspots(frame, temperature_matrix)
        
        for x, y, w, h, max_temp in hotspots:
            # Determine severity
            if max_temp > 80:
                severity = 'critical'
            elif max_temp > 60:
                severity = 'high'
            elif max_temp > 50:
                severity = 'medium'
            else:
                severity = 'low'
            
            anomaly = AnomalyRecord(
                timestamp=datetime.now(),
                anomaly_type='temperature',
                severity=severity,
                location=location,
                description=f"High temperature detected: {max_temp:.1f}°C",
                sensor_values={'temperature': max_temp, 'area': w*h},
                roi_coords=(x, y, w, h)
            )
            anomalies.append(anomaly)
        
        return anomalies

@dataclass
class YOLOTrainingProgress:
    """Track YOLO training progress."""
    epoch: int = 0
    total_epochs: int = 0
    loss: float = 0.0
    metrics: Dict = field(default_factory=dict)
    status: str = "idle"  # 'idle', 'training', 'validating', 'complete', 'error'
    
    def to_dict(self):
        return {
            'epoch': self.epoch,
            'total_epochs': self.total_epochs,
            'loss': self.loss,
            'metrics': self.metrics,
            'status': self.status
        }

class YOLOTrainer:
    """YOLO model training with progress tracking."""
    
    def __init__(self, model_path="models/yolov8n.pt"):
        self.model_path = model_path
        self.progress = YOLOTrainingProgress()
        self.is_training = False
        self.model = None
        self.training_data_dir = "training_data"
        os.makedirs(self.training_data_dir, exist_ok=True)
    
    def add_training_frame(self, frame: np.ndarray, annotations: List[Dict]):
        """
        Add a frame with annotations to training dataset.
        annotations: list of {class_id, x, y, w, h} dicts
        """
        # Save frame
        frame_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        frame_path = os.path.join(self.training_data_dir, f"frame_{frame_id}.jpg")
        cv2.imwrite(frame_path, frame)
        
        # Save annotations in YOLO format
        label_path = os.path.join(self.training_data_dir, f"frame_{frame_id}.txt")
        with open(label_path, 'w') as f:
            for ann in annotations:
                # YOLO format: class_id center_x center_y width height (normalized)
                h, w = frame.shape[:2]
                x_center = (ann['x'] + ann['w'] / 2) / w
                y_center = (ann['y'] + ann['h'] / 2) / h
                width = ann['w'] / w
                height = ann['h'] / h
                f.write(f"{ann['class_id']} {x_center} {y_center} {width} {height}\n")
        
        return frame_path
    
    def start_training(self, epochs=50, batch_size=16, imgsz=640):
        """Start YOLO training (async)."""
        if self.is_training:
            return False
        
        try:
            from ultralytics import YOLO
            
            self.is_training = True
            self.progress.status = "training"
            self.progress.total_epochs = epochs
            
            # Load model
            self.model = YOLO(self.model_path)
            
            # Train (this is a simplified version - full implementation needs threading)
            results = self.model.train(
                data="config.yaml",  # You'll need to create this
                epochs=epochs,
                batch=batch_size,
                imgsz=imgsz,
                project="runs/train",
                name="embereye_custom"
            )
            
            self.progress.status = "complete"
            self.is_training = False
            return True
            
        except Exception as e:
            print(f"[YOLO_TRAINER] Training error: {e}")
            self.progress.status = "error"
            self.is_training = False
            return False
    
    def get_progress(self) -> YOLOTrainingProgress:
        """Get current training progress."""
        return self.progress
    
    def is_frame_similar(self, frame1: np.ndarray, frame2: np.ndarray, threshold=0.95) -> bool:
        """
        Check if two frames are similar using histogram correlation.
        Used for de-duplication.
        """
        if frame1.shape != frame2.shape:
            frame2 = cv2.resize(frame2, (frame1.shape[1], frame1.shape[0]))
        
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY) if len(frame1.shape) == 3 else frame1
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY) if len(frame2.shape) == 3 else frame2
        
        # Calculate histograms
        hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])
        
        # Normalize
        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        
        # Compare
        correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        
        return correlation > threshold
