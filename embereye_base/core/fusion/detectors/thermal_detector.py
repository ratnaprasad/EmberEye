from datetime import datetime
from typing import Optional

import numpy as np

from .base_detector import BaseDetector
from ..fusion_engine import Detection, DetectionSource


class ThermalDetector(BaseDetector):
    def detect(self, thermal_frame: np.ndarray) -> Optional[Detection]:
        arr = np.asarray(thermal_frame, dtype=float)
        if arr.size == 0:
            return None

        finite_mask = np.isfinite(arr)
        if not np.any(finite_mask):
            return None

        finite_values = arr[finite_mask]

        max_temp = float(np.max(finite_values))
        mean_temp = float(np.mean(finite_values))
        threshold = float(self.config.get('temp_threshold', 40.0))
        critical_threshold = float(self.config.get('critical_temp_threshold', 60.0))

        if max_temp < threshold:
            return None

        hot_cells = [(int(r), int(c)) for r, c in zip(*np.where(finite_mask & (arr >= threshold)))]
        critical = max_temp >= critical_threshold
        confidence = 1.0 if critical else 0.4

        detection = Detection(
            source=DetectionSource.THERMAL,
            confidence=confidence,
            value=max_temp,
            timestamp=datetime.now(),
            metadata={
                'threshold': threshold,
                'critical_threshold': critical_threshold,
                'critical': critical,
                'max_temp': max_temp,
                'mean_temp': mean_temp,
                'hot_cells': hot_cells,
            }
        )
        self.last_detection = detection
        return detection

    def get_thresholds(self) -> dict:
        return {
            'temp_threshold': float(self.config.get('temp_threshold', 40.0)),
            'critical_temp_threshold': float(self.config.get('critical_temp_threshold', 60.0)),
        }
