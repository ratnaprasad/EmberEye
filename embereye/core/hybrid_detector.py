"""
Hybrid Fire/Hazard Detection System
Combines fast heuristic filtering with accurate YOLO model detection
"""
import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Dict, List
from pathlib import Path
import sys
import os

from .detection_queue import DetectionQueue, FrameMetadata, DetectionResult, get_detection_queue


class HybridDetector:
    """
    Two-stage detection pipeline:
    1. Heuristic (fast) - filters 70-80% of frames
    2. YOLO (async) - validates suspicious frames with ML model
    
    Confidence levels:
    - >= 0.70: CONFIRMED (red alert)
    - 0.50-0.70: POSSIBLE (orange warning)
    - < 0.50: LOW (ignore)
    """
    
    def __init__(self, model_path: Optional[str] = None, stream_id: str = "default"):
        self.stream_id = stream_id
        self.model = None
        self.model_loaded = False
        self.yolo_model_path = model_path
        self.central_class_names: List[str] = []

        try:
            from embereye.core.class_config import get_leaf_classes
            self.central_class_names = get_leaf_classes()
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] Could not load central class mapping: {e}")
        
        # Heuristic parameters
        self.heuristic_threshold = 0.20  # Skip YOLO if heuristic < 0.20
        
        # Confidence level thresholds
        self.confirmed_threshold = 0.70    # >= 0.70: CONFIRMED
        self.possible_threshold = 0.50     # 0.50-0.70: POSSIBLE
        # < 0.50: LOW (ignored)
        
        # Detection queue (shared across all streams)
        self.detection_queue = get_detection_queue()
        
        # Frame counter for this stream
        self._frame_counter = 0
        self._results_received = 0
        
        # Class priority (higher = more important)
        self.class_priority = {
            'PERSON_IN_DISTRESS': 0.95,
            'FIRE': 0.95,
            'SMOKE_WITH_FIRE': 0.90,
            'EXPLOSIVE_DEVICE': 0.98,
            'EXPLOSION': 0.95,
            'ELECTRICAL_ARC': 0.85,
            'PERSON_WITHOUT_SAFETY_WEAR': 0.60,
            'DAMAGED_EQUIPMENT': 0.65,
            'HARMFUL_GASES': 0.75,
            'HAZARD_UNSPECIFIED': 0.40,
        }
        
        # Try to load YOLO model
        if model_path:
            self._load_yolo_model(model_path)
        else:
            self._auto_load_model()
    
    def _auto_load_model(self) -> None:
        """Automatically find and load latest model from ModelVersionManager or ./models/"""
        # First, try to use ModelVersionManager (preferred location for imported models)
        try:
            from embereye.core.model_versioning import ModelVersionManager
            manager = ModelVersionManager()
            current_best = manager.get_current_best()
            if current_best and current_best.exists():
                self._load_yolo_model(str(current_best))
                return
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] Could not use ModelVersionManager: {e}")
        
        # Fallback: Check for loose .pt files in ./models/
        models_dir = Path("./models")
        if models_dir.exists():
            model_files = sorted(
                [f for f in models_dir.glob("*.pt") if f.is_file() and not f.name.startswith(".")],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if model_files:
                print(f"[HybridDetector-{self.stream_id}] Using loose model file: {model_files[0].name}")
                self._load_yolo_model(str(model_files[0]))
                return
        
        print(f"[HybridDetector-{self.stream_id}] No model found in ModelVersionManager or ./models/")
    
    def _load_yolo_model(self, model_path: str) -> None:
        """Load YOLO model (must be called in worker thread to avoid DLL issues)"""
        try:
            from ultralytics import YOLO
            print(f"[HybridDetector-{self.stream_id}] Loading YOLO from: {model_path}")
            self.model = YOLO(model_path)
            self.model_loaded = True
            self.yolo_model_path = model_path
            print(f"[HybridDetector-{self.stream_id}] [OK] Model loaded. Classes: {len(self.model.names)}")
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] [ERROR] Failed to load model: {e}")
            self.model_loaded = False
            self.model = None
    
    def heuristic_detect(self, frame: np.ndarray) -> float:
        """
        Fast heuristic detection (fire/smoke colors).
        Returns confidence score 0-1.
        
        < 0.20: Not suspicious, skip YOLO
        >= 0.20: Suspicious, queue for YOLO validation
        """
        try:
            # Convert to HSV for color analysis
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, w = frame.shape[:2]
            
            # Fire detection: warm colors (orange/red/yellow)
            # Hue: 0-40 (red wraps around), Saturation: 100-255, Value: 100-255
            lower_fire = np.array([0, 100, 100])
            upper_fire = np.array([40, 255, 255])
            mask_fire = cv2.inRange(hsv, lower_fire, upper_fire)
            fire_pixels = cv2.countNonZero(mask_fire)
            fire_ratio = fire_pixels / (h * w)
            
            # Smoke detection: low saturation, high brightness (gray/white)
            # Hue: any, Saturation: 0-60, Value: 180-255
            lower_smoke = np.array([0, 0, 180])
            upper_smoke = np.array([180, 60, 255])
            mask_smoke = cv2.inRange(hsv, lower_smoke, upper_smoke)
            smoke_pixels = cv2.countNonZero(mask_smoke)
            smoke_ratio = smoke_pixels / (h * w)
            
            # Combine with weights
            # Fire is more critical, weight 3x; smoke 1.5x
            score = min(1.0, fire_ratio * 3 + smoke_ratio * 1.5)
            
            return score
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] Heuristic error: {e}")
            return 0.0
    
    def detect_frame(self, frame: np.ndarray) -> Tuple[float, Optional[DetectionResult]]:
        """
        Main detection entry point for video frames.
        
        Returns:
            (heuristic_score, result_or_None)
            - heuristic_score: 0-1, always returned
            - result: DetectionResult if YOLO processing complete, else None
        """
        self._frame_counter += 1
        frame_id = f"{self.stream_id}-{self._frame_counter}"
        
        # Stage 1: Heuristic (fast)
        heuristic_score = self.heuristic_detect(frame)
        
        # Stage 2: Queue suspicious frames for YOLO
        if heuristic_score >= self.heuristic_threshold and self.model_loaded:
            # Create frame metadata for async YOLO processing
            metadata = FrameMetadata(
                frame_id=frame_id,
                stream_id=self.stream_id,
                heuristic_score=heuristic_score,
                frame_data=frame.copy()  # Store frame data
            )
            self.detection_queue.add_frame(metadata)
        
        # Stage 3: Check if previous results are available
        # Look for any completed results waiting for this stream
        result = self._check_pending_results()
        
        return heuristic_score, result
    
    def _check_pending_results(self) -> Optional[DetectionResult]:
        """Check if any detection results are ready for this stream"""
        # In real implementation, this would check for cached results
        # For now, we'll leave this for the video_worker to handle
        return None
    
    @staticmethod
    def map_to_confidence_level(yolo_confidence: float) -> str:
        """
        Map YOLO confidence to user-friendly level.
        
        >= 0.70: CONFIRMED (red)
        0.50-0.70: POSSIBLE (orange)
        < 0.50: LOW (gray)
        """
        if yolo_confidence >= 0.70:
            return "CONFIRMED"
        elif yolo_confidence >= 0.50:
            return "POSSIBLE"
        else:
            return "LOW"
    
    def process_queued_frame(self, metadata: FrameMetadata) -> DetectionResult:
        """
        Process a queued frame with YOLO (runs in worker thread).
        
        Called by detection worker thread.
        """
        start_time = time.time()
        
        if not self.model_loaded or self.model is None:
            # Model not available, return LOW confidence
            return DetectionResult(
                frame_id=metadata.frame_id,
                stream_id=metadata.stream_id,
                status="LOW",
                confidence=0.0,
                primary_class="NO_MODEL",
                yolo_latency_ms=0.0,
                timestamp_ms=metadata.timestamp_ms
            )
        
        try:
            # Run YOLO inference
            frame = metadata.frame_data
            if frame is None:
                return DetectionResult(
                    frame_id=metadata.frame_id,
                    stream_id=metadata.stream_id,
                    status="LOW",
                    confidence=0.0,
                    yolo_latency_ms=time.time() - start_time
                )
            
            # Inference
            results = self.model(frame, verbose=False, conf=0.25)
            
            detections = []
            max_confidence = 0.0
            primary_class = ""
            
            # Extract detections
            if results and len(results) > 0:
                for result in results:
                    if result.boxes is not None:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            confidence = float(box.conf[0])
                            if 0 <= class_id < len(self.central_class_names):
                                class_name = self.central_class_names[class_id]
                            else:
                                class_name = self.model.names.get(class_id, f"class_{class_id}")
                            
                            detections.append({
                                'class': class_name,
                                'confidence': confidence,
                                'bbox': box.xyxy[0].cpu().numpy().tolist() if hasattr(box.xyxy, 'cpu') else box.xyxy[0].tolist()
                            })
                            
                            # Track highest confidence
                            if confidence > max_confidence:
                                max_confidence = confidence
                                primary_class = class_name
            
            # Determine confidence level
            status = self.map_to_confidence_level(max_confidence)
            latency_ms = (time.time() - start_time) * 1000
            
            result = DetectionResult(
                frame_id=metadata.frame_id,
                stream_id=metadata.stream_id,
                status=status,
                confidence=max_confidence,
                detections=detections,
                primary_class=primary_class,
                yolo_latency_ms=latency_ms,
                timestamp_ms=metadata.timestamp_ms
            )
            
            return result
            
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] YOLO inference error: {e}")
            return DetectionResult(
                frame_id=metadata.frame_id,
                stream_id=metadata.stream_id,
                status="LOW",
                confidence=0.0,
                yolo_latency_ms=time.time() - start_time
            )
