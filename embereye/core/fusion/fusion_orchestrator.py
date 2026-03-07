from datetime import datetime, timedelta
from typing import Dict, Optional

from .fusion_engine import Detection, DetectionSource, FusionResult, SeverityLevel
from .detectors import (
    BaseDetector,
    SmokeDetector,
    FlameAnalogDetector,
    FlameDigitalDetector,
    ThermalDetector,
    VisionDetector,
    GasDetector,
)


class FusionOrchestrator:
    def __init__(self, config: dict):
        self.config = dict(config)
        self.detectors: Dict[DetectionSource, BaseDetector] = {}
        self.detection_history: list[Detection] = []
        self.max_history = int(self.config.get('max_history', 100))
        self._init_detectors()

    def _init_detectors(self) -> None:
        self.detectors = {
            DetectionSource.SMOKE: SmokeDetector(self.config),
            DetectionSource.FLAME_ANALOG: FlameAnalogDetector(self.config),
            DetectionSource.FLAME_DIGITAL: FlameDigitalDetector(self.config),
            DetectionSource.THERMAL: ThermalDetector(self.config),
            DetectionSource.VISION: VisionDetector(self.config),
            DetectionSource.GAS: GasDetector(self.config),
        }

    def update_config(self, config: dict) -> None:
        self.config = dict(config)
        self.max_history = int(self.config.get('max_history', self.max_history))
        for detector in self.detectors.values():
            detector.update_config(self.config)

    def process_frame(self, frame_data: dict) -> FusionResult:
        detections: list[Detection] = []

        smoke_value = frame_data.get('smoke_pct', frame_data.get('adc1'))
        if smoke_value is not None:
            detection = self.detectors[DetectionSource.SMOKE].detect(smoke_value)
            if detection:
                detections.append(detection)

        flame_analog_value = frame_data.get('flame_analog_pct', frame_data.get('adc2'))
        if flame_analog_value is not None:
            detection = self.detectors[DetectionSource.FLAME_ANALOG].detect(flame_analog_value)
            if detection:
                detections.append(detection)

        flame_digital_value = frame_data.get('flame_digital', frame_data.get('mpy30'))
        if flame_digital_value is not None:
            detection = self.detectors[DetectionSource.FLAME_DIGITAL].detect(flame_digital_value)
            if detection:
                detections.append(detection)

        if 'thermal' in frame_data and frame_data.get('thermal') is not None:
            detection = self.detectors[DetectionSource.THERMAL].detect(frame_data['thermal'])
            if detection:
                detections.append(detection)

        vision_input = None
        if 'vision_detections' in frame_data:
            vision_input = frame_data.get('vision_detections')
        elif 'vision_score' in frame_data:
            vision_input = frame_data.get('vision_score')
        if vision_input is not None:
            detection = self.detectors[DetectionSource.VISION].detect(vision_input)
            if detection:
                detections.append(detection)

        gas_value = frame_data.get('gas_ppm')
        if gas_value is not None:
            detection = self.detectors[DetectionSource.GAS].detect(gas_value)
            if detection:
                detections.append(detection)

        self.detection_history.extend(detections)
        self.detection_history = self.detection_history[-self.max_history:]

        return self._fuse_detections(detections)

    def _fuse_detections(self, detections: list[Detection]) -> FusionResult:
        now = datetime.now()
        if not detections:
            return FusionResult(
                alarm=False,
                severity=SeverityLevel.NONE,
                confidence=0.0,
                primary_source=None,
                detections=[],
                timestamp=now,
                metadata={'reason': None, 'sources': []},
            )

        critical_detections = [d for d in detections if bool(d.metadata.get('critical', False))]
        if critical_detections:
            primary = critical_detections[0]
            return FusionResult(
                alarm=True,
                severity=SeverityLevel.CRITICAL,
                confidence=1.0,
                primary_source=primary.source,
                detections=detections,
                timestamp=now,
                metadata={
                    'override': True,
                    'reason': f"Critical temperature: {primary.value:.1f}°C >= {float(self.config.get('critical_temp_threshold', 60.0))}°C",
                    'sources': [d.source.name.lower() for d in detections],
                },
            )

        alarm = False
        severity = SeverityLevel.NONE
        confidence = float(sum(max(0.0, d.confidence) for d in detections))
        reason: Optional[str] = None

        has_smoke = any(d.source == DetectionSource.SMOKE for d in detections)
        has_flame = any(d.source in (DetectionSource.FLAME_ANALOG, DetectionSource.FLAME_DIGITAL) for d in detections)
        thermal_detection = next((d for d in detections if d.source == DetectionSource.THERMAL), None)
        has_thermal = thermal_detection is not None
        has_vision = any(d.source == DetectionSource.VISION for d in detections)
        has_gas = any(d.source == DetectionSource.GAS for d in detections)

        if has_smoke:
            alarm = True
            severity = self._max_severity(severity, SeverityLevel.HIGH)
            smoke_detection = next(d for d in detections if d.source == DetectionSource.SMOKE)
            reason = f"Smoke threshold exceeded: {smoke_detection.value:.1f}% >= {float(self.config.get('smoke_threshold_pct', 25.0))}%"

        if has_flame and has_thermal:
            alarm = True
            severity = self._max_severity(severity, SeverityLevel.HIGH)
            confidence += 0.3
            if reason is None:
                flame_value = next(d.value for d in detections if d.source in (DetectionSource.FLAME_ANALOG, DetectionSource.FLAME_DIGITAL))
                reason = f"Flame + Thermal correlation: Flame={float(flame_value):.1f}%, Thermal={float(thermal_detection.value):.1f}°C"

        if has_vision and (has_smoke or has_flame or has_thermal or has_gas):
            vision_detection = next(d for d in detections if d.source == DetectionSource.VISION)
            vision_gate = float(self.config.get('vision_threshold', 0.7))
            if vision_detection.value >= vision_gate:
                alarm = True
                severity = self._max_severity(severity, SeverityLevel.HIGH)
                if reason is None:
                    reason = f"Vision + Sensor correlation: Vision={float(vision_detection.value):.2f}"

        if has_gas:
            alarm = True
            severity = self._max_severity(severity, SeverityLevel.HIGH)
            gas_detection = next(d for d in detections if d.source == DetectionSource.GAS)
            reason = f"Hazardous gas detected: {gas_detection.value:.1f}ppm >= {float(self.config.get('gas_ppm_threshold', 400.0))}ppm"

        confidence += self._temporal_fusion(detections)
        confidence = float(max(0.0, confidence))

        primary_source = max(detections, key=lambda item: item.confidence).source
        return FusionResult(
            alarm=alarm,
            severity=severity,
            confidence=confidence,
            primary_source=primary_source,
            detections=detections,
            timestamp=now,
            metadata={
                'reason': reason,
                'sources': [d.source.name.lower() for d in detections],
            },
        )

    def _temporal_fusion(self, detections: list[Detection]) -> float:
        if not bool(self.config.get('enable_temporal_fusion', False)):
            return 0.0

        window_seconds = int(self.config.get('temporal_window_seconds', 5))
        min_support = int(self.config.get('temporal_min_support', 2))
        window_start = datetime.now() - timedelta(seconds=window_seconds)
        recent = [d for d in self.detection_history if d.timestamp >= window_start]
        if not recent:
            return 0.0

        active_sources = {d.source for d in detections}
        support = sum(1 for d in recent if d.source in active_sources)
        if support < min_support:
            return 0.0

        return min(0.2, support * 0.02)

    @staticmethod
    def _max_severity(current: SeverityLevel, candidate: SeverityLevel) -> SeverityLevel:
        return candidate if candidate.value > current.value else current
