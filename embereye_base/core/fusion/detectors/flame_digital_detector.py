from datetime import datetime
from typing import Optional

from .base_detector import BaseDetector
from ..fusion_engine import Detection, DetectionSource


class FlameDigitalDetector(BaseDetector):
    def detect(self, digital_value: int) -> Optional[Detection]:
        active_value = int(self.config.get('flame_active_value', 1))
        current = int(digital_value)
        if current == active_value:
            detection = Detection(
                source=DetectionSource.FLAME_DIGITAL,
                confidence=0.3,
                value=float(current),
                timestamp=datetime.now(),
                metadata={'active_value': active_value}
            )
            self.last_detection = detection
            return detection
        return None

    def get_thresholds(self) -> dict:
        return {'flame_active_value': int(self.config.get('flame_active_value', 1))}
