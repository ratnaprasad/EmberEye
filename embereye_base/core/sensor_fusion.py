import time
import numpy as np

from embereye_base.core.fusion import FusionOrchestrator, DetectionSource


class SensorFusion:
    def __init__(self, temp_threshold=40.0, gas_ppm_threshold=400, flame_active_value=1, min_sources=2, critical_temp_threshold=60.0, smoke_threshold_pct=25.0, flame_threshold_pct=25.0, vision_threshold=0.7, vision_confidence_weight=0.4):
        self.temp_threshold = temp_threshold
        self.gas_ppm_threshold = gas_ppm_threshold
        self.flame_active_value = flame_active_value
        self.min_sources = min_sources
        self.critical_temp_threshold = critical_temp_threshold
        self.smoke_threshold_pct = smoke_threshold_pct
        self.flame_threshold_pct = flame_threshold_pct
        self.vision_threshold = vision_threshold
        self.vision_confidence_weight = vision_confidence_weight
        self.event_log = []

        try:
            from ..utils.metrics import get_metrics
            self.metrics = get_metrics()
        except Exception:
            self.metrics = None

        self._orchestrator = FusionOrchestrator(self._build_config())

    def _build_config(self) -> dict:
        return {
            'temp_threshold': float(self.temp_threshold),
            'gas_ppm_threshold': float(self.gas_ppm_threshold),
            'flame_active_value': int(self.flame_active_value),
            'min_sources': int(self.min_sources),
            'critical_temp_threshold': float(self.critical_temp_threshold),
            'smoke_threshold_pct': float(self.smoke_threshold_pct),
            'flame_threshold_pct': float(self.flame_threshold_pct),
            'vision_threshold': float(self.vision_threshold),
            'vision_confidence_weight': float(self.vision_confidence_weight),
        }

    def _sync_orchestrator(self) -> None:
        self._orchestrator.update_config(self._build_config())

    def fuse(self, thermal_matrix=None, gas_ppm=None, flame=None, vision_score=None, **kwargs):
        self._sync_orchestrator()
        fusion_start = time.time() if self.metrics else None

        frame_data = {}
        if thermal_matrix is not None:
            frame_data['thermal'] = thermal_matrix
        if gas_ppm is not None:
            frame_data['gas_ppm'] = gas_ppm
        if flame is not None:
            frame_data['flame_digital'] = flame
        if vision_score is not None:
            frame_data['vision_score'] = vision_score

        if 'vision_detections' in kwargs:
            frame_data['vision_detections'] = kwargs.get('vision_detections')
        if 'smoke_pct' in kwargs:
            frame_data['smoke_pct'] = kwargs.get('smoke_pct')
        if 'flame_analog_pct' in kwargs:
            frame_data['flame_analog_pct'] = kwargs.get('flame_analog_pct')
        if 'flame_digital' in kwargs:
            frame_data['flame_digital'] = kwargs.get('flame_digital')
        if 'mpy30' in kwargs:
            frame_data['flame_digital'] = kwargs.get('mpy30')

        fusion_result = self._orchestrator.process_frame(frame_data)

        thermal_detection = next((d for d in fusion_result.detections if d.source == DetectionSource.THERMAL), None)
        hot_cells = thermal_detection.metadata.get('hot_cells', []) if thermal_detection else []
        thermal_max = float(thermal_detection.metadata.get('max_temp', 0.0)) if thermal_detection else 0.0

        result = {
            'alarm': bool(fusion_result.alarm),
            'alarm_reason': fusion_result.metadata.get('reason'),
            'confidence': float(fusion_result.confidence),
            'sources': [d.source.name.lower() for d in fusion_result.detections],
            'hot_cells': hot_cells,
            'thermal_max': thermal_max,
            'gas_ppm': float(gas_ppm) if gas_ppm is not None else 0.0,
            'smoke_pct': float(kwargs.get('smoke_pct', 0.0) or 0.0),
            'flame_analog_pct': float(kwargs.get('flame_analog_pct', 0.0) or 0.0),
            'flame_digital': int(kwargs.get('flame_digital', frame_data.get('flame_digital', 0)) or 0),
            'severity': fusion_result.severity.name,
        }

        result.update(kwargs)

        self.event_log.append({
            'timestamp': time.time(),
            'alarm': result['alarm'],
            'confidence': result['confidence'],
            'sources': result['sources'],
            'hot_cells': len(result['hot_cells']),
            'reason': result['alarm_reason'],
        })

        if self.metrics and fusion_start is not None:
            fusion_latency = (time.time() - fusion_start) * 1000
            self.metrics.record_fusion(result['alarm'], fusion_latency)

        return result

    def get_event_log(self):
        return self.event_log
