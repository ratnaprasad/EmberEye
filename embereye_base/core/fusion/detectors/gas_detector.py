from datetime import datetime
from typing import Optional

from .base_detector import BaseDetector
from ..fusion_engine import Detection, DetectionSource


class GasDetector(BaseDetector):
    def detect(self, gas_ppm: float) -> Optional[Detection]:
        threshold = float(self.config.get('gas_ppm_threshold', 400.0))
        current = float(gas_ppm)
        if current >= threshold:
            confidence = max(0.5, min(1.0, current / max(threshold * 2.0, 1.0)))
            detection = Detection(
                source=DetectionSource.GAS,
                confidence=confidence,
                value=current,
                timestamp=datetime.now(),
                metadata={'threshold': threshold}
            )
            self.last_detection = detection
            return detection
        return None

    def get_thresholds(self) -> dict:
        return {'gas_ppm_threshold': float(self.config.get('gas_ppm_threshold', 400.0))}
