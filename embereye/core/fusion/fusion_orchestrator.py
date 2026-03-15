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

        # Hardware mapping: ADC1 -> flame analog, ADC2 -> smoke/gas channel.
        smoke_value = frame_data.get('smoke_pct', frame_data.get('adc2'))
        if smoke_value is not None:
            detection = self.detectors[DetectionSource.SMOKE].detect(smoke_value)
            if detection:
                detections.append(detection)

        flame_analog_value = frame_data.get('flame_analog_pct', frame_data.get('adc1'))
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
        vision_value: Optional[float] = None
        if 'vision_detections' in frame_data:
            vision_input = frame_data.get('vision_detections')
        elif 'vision_score' in frame_data:
            vision_input = frame_data.get('vision_score')
        if vision_input is not None:
            vision_value = self._extract_vision_value(vision_input)
            detection = self.detectors[DetectionSource.VISION].detect(vision_input)
            if detection:
                detections.append(detection)
            elif vision_value is not None:
                detections.append(
                    Detection(
                        source=DetectionSource.VISION,
                        confidence=0.0,
                        value=vision_value,
                        timestamp=datetime.now(),
                        metadata={'raw_only': True},
                    )
                )

        gas_value = frame_data.get('gas_ppm')
        if gas_value is not None:
            detection = self.detectors[DetectionSource.GAS].detect(gas_value)
            if detection:
                detections.append(detection)

        self.detection_history.extend(detections)
        self.detection_history = self.detection_history[-self.max_history:]

        return self._fuse_detections(detections, frame_data)

    @staticmethod
    def _extract_vision_value(vision_input) -> Optional[float]:
        if vision_input is None:
            return None
        if isinstance(vision_input, (int, float)):
            return float(vision_input)
        if isinstance(vision_input, list):
            if not vision_input:
                return None
            try:
                return max(float(item.get('confidence', 0.0)) for item in vision_input)
            except Exception:
                return None
        return None

    def _fuse_detections(self, detections: list[Detection], frame_data: Optional[dict] = None) -> FusionResult:
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

        payload = frame_data or {}

        thermal_detection = next((d for d in detections if d.source == DetectionSource.THERMAL), None)
        smoke_detection = next((d for d in detections if d.source == DetectionSource.SMOKE), None)
        flame_analog_detection = next((d for d in detections if d.source == DetectionSource.FLAME_ANALOG), None)
        flame_digital_detection = next((d for d in detections if d.source == DetectionSource.FLAME_DIGITAL), None)
        gas_detection = next((d for d in detections if d.source == DetectionSource.GAS), None)
        vision_detection = next((d for d in detections if d.source == DetectionSource.VISION), None)

        raw_smoke = payload.get('smoke_pct', payload.get('adc2'))
        raw_flame = payload.get('flame_analog_pct', payload.get('adc1'))
        raw_vision = None
        if 'vision_detections' in payload:
            raw_vision = self._extract_vision_value(payload.get('vision_detections'))
        elif 'vision_score' in payload:
            raw_vision = self._extract_vision_value(payload.get('vision_score'))
        raw_gas = payload.get('gas_ppm')

        has_smoke = smoke_detection is not None or raw_smoke is not None
        has_flame = flame_analog_detection is not None or flame_digital_detection is not None
        has_thermal = thermal_detection is not None
        has_vision = vision_detection is not None or raw_vision is not None
        has_gas = gas_detection is not None or raw_gas is not None

        thermal_value = float(thermal_detection.value) if thermal_detection is not None else float('-inf')
        smoke_value = float(raw_smoke) if raw_smoke is not None else (float(smoke_detection.value) if smoke_detection is not None else float('-inf'))
        flame_value = float(raw_flame) if raw_flame is not None else (float(flame_analog_detection.value) if flame_analog_detection is not None else float('-inf'))
        vision_value = float(raw_vision) if raw_vision is not None else (float(vision_detection.value) if vision_detection is not None else float('-inf'))
        gas_value = float(raw_gas) if raw_gas is not None else (float(gas_detection.value) if gas_detection is not None else float('-inf'))

        critical_temp_threshold = float(self.config.get('critical_temp_threshold', 60.0))
        smoke_threshold_pct = float(self.config.get('smoke_threshold_pct', 25.0))
        flame_threshold_pct = float(self.config.get('flame_threshold_pct', 25.0))

        independent_trigger = (
            thermal_value >= critical_temp_threshold
            or smoke_value >= smoke_threshold_pct
            or flame_value >= flame_threshold_pct
        )

        if thermal_value >= critical_temp_threshold:
            alarm = True
            severity = SeverityLevel.CRITICAL
            reason = f"Critical temperature: {thermal_value:.1f}°C >= {critical_temp_threshold}°C"
        elif smoke_value >= smoke_threshold_pct:
            alarm = True
            severity = SeverityLevel.HIGH
            reason = f"Smoke threshold exceeded: {smoke_value:.1f}% >= {smoke_threshold_pct}%"
        elif flame_value >= flame_threshold_pct:
            alarm = True
            severity = SeverityLevel.HIGH
            reason = f"Flame threshold exceeded: {flame_value:.1f}% >= {flame_threshold_pct}%"
        elif has_gas and gas_value >= float(self.config.get('gas_ppm_threshold', 400.0)):
            alarm = True
            severity = SeverityLevel.HIGH
            reason = f"Hazardous gas detected: {gas_value:.1f}ppm >= {float(self.config.get('gas_ppm_threshold', 400.0))}ppm"
        else:
            if has_vision:
                if vision_value >= 0.70:
                    alarm = True
                    severity = SeverityLevel.HIGH
                    reason = f"Vision threshold met: Vision={vision_value:.2f} >= 0.70"
                elif vision_value >= 0.50 and thermal_value > 50.0 and flame_value >= 10.0:
                    alarm = True
                    severity = SeverityLevel.HIGH
                    reason = f"Vision band correlation: Vision={vision_value:.2f}, Thermal={thermal_value:.1f}°C > 50, Flame={flame_value:.1f}% >= 10"
                elif vision_value >= 0.30 and thermal_value > 50.0 and flame_value >= 10.0:
                    alarm = True
                    severity = SeverityLevel.HIGH
                    reason = f"Vision band correlation: Vision={vision_value:.2f}, Thermal={thermal_value:.1f}°C > 50, Flame={flame_value:.1f}% >= 10"
                elif vision_value < 0.30 and thermal_value > 50.0 and flame_value >= 10.0:
                    alarm = True
                    severity = SeverityLevel.HIGH
                    reason = f"Vision low-band correlation: Vision={vision_value:.2f}, Thermal={thermal_value:.1f}°C > 50, Flame={flame_value:.1f}% >= 10"

        if alarm and independent_trigger and has_flame and has_thermal and flame_analog_detection is not None and thermal_detection is not None:
            confidence += 0.3

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
