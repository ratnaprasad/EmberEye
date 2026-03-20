from datetime import datetime
from typing import Optional

from .base_detector import BaseDetector
from ..fusion_engine import Detection, DetectionSource


class SmokeDetector(BaseDetector):
    def detect(self, adc_value: float) -> Optional[Detection]:
        threshold = float(self.config.get('smoke_threshold_pct', 25.0))
        current = float(adc_value)
        if current >= threshold:
            confidence = max(0.5, min(1.0, current / 100.0))
            detection = Detection(
                source=DetectionSource.SMOKE,
                confidence=confidence,
                value=current,
                timestamp=datetime.now(),
                metadata={'threshold': threshold}
            )
            self.last_detection = detection
            return detection
        return None

    def get_thresholds(self) -> dict:
        return {'smoke_threshold_pct': float(self.config.get('smoke_threshold_pct', 25.0))}
