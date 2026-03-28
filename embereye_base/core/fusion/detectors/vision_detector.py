from datetime import datetime
from typing import Optional

from .base_detector import BaseDetector
from ..fusion_engine import Detection, DetectionSource


class VisionDetector(BaseDetector):
    def __init__(self, config: dict):
        super().__init__(config)
        self.consecutive_detections = 0

    def detect(self, detections) -> Optional[Detection]:
        if detections is None:
            self.consecutive_detections = 0
            return None

        if isinstance(detections, (int, float)):
            max_conf = float(detections)
            payload = []
        elif isinstance(detections, list):
            if not detections:
                self.consecutive_detections = 0
                return None
            max_conf = max(float(item.get('confidence', 0.0)) for item in detections)
            payload = detections
        else:
            self.consecutive_detections = 0
            return None

        vision_threshold = float(self.config.get('vision_threshold', 0.7))
        base_weight = float(self.config.get('vision_confidence_weight', 0.5))

        if max_conf >= vision_threshold:
            self.consecutive_detections += 1
            persistence_boost = min(0.3, self.consecutive_detections * 0.1)
            confidence = min(1.0, base_weight + persistence_boost)
            detection = Detection(
                source=DetectionSource.VISION,
                confidence=confidence,
                value=max_conf,
                timestamp=datetime.now(),
                metadata={
                    'threshold': vision_threshold,
                    'raw_confidence': max_conf,
                    'detections': payload,
                    'consecutive': self.consecutive_detections,
                }
            )
            self.last_detection = detection
            return detection

        self.consecutive_detections = 0
        return None

    def get_thresholds(self) -> dict:
        return {
            'vision_threshold': float(self.config.get('vision_threshold', 0.7)),
            'vision_confidence_weight': float(self.config.get('vision_confidence_weight', 0.5)),
        }
