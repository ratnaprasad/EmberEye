import unittest

import numpy as np

from embereye.core.fusion import FusionOrchestrator, SeverityLevel, DetectionSource


class TestFusionOrchestrator(unittest.TestCase):
    def setUp(self):
        self.config = {
            'temp_threshold': 40.0,
            'critical_temp_threshold': 60.0,
            'gas_ppm_threshold': 400.0,
            'smoke_threshold_pct': 25.0,
            'flame_threshold_pct': 25.0,
            'flame_active_value': 1,
            'vision_threshold': 0.7,
            'vision_confidence_weight': 0.5,
            'enable_temporal_fusion': False,
        }
        self.orchestrator = FusionOrchestrator(self.config)

    def test_empty_frame_no_alarm(self):
        result = self.orchestrator.process_frame({})
        self.assertFalse(result.alarm)
        self.assertEqual(result.severity, SeverityLevel.NONE)
        self.assertEqual(result.confidence, 0.0)

    def test_critical_thermal_override(self):
        frame = np.full((24, 32), 80.0, dtype=float)
        result = self.orchestrator.process_frame({'thermal': frame})
        self.assertTrue(result.alarm)
        self.assertEqual(result.severity, SeverityLevel.CRITICAL)
        self.assertEqual(result.confidence, 1.0)

    def test_smoke_immediate_alarm(self):
        result = self.orchestrator.process_frame({'smoke_pct': 40.0})
        self.assertTrue(result.alarm)
        self.assertIn('smoke', result.metadata.get('sources', []))

    def test_flame_plus_thermal_alarm(self):
        frame = np.full((24, 32), 45.0, dtype=float)
        result = self.orchestrator.process_frame({'flame_analog_pct': 35.0, 'thermal': frame})
        self.assertTrue(result.alarm)
        self.assertEqual(result.severity, SeverityLevel.HIGH)
        sources = {d.source for d in result.detections}
        self.assertIn(DetectionSource.FLAME_ANALOG, sources)
        self.assertIn(DetectionSource.THERMAL, sources)

    def test_vision_with_sensor_alarm(self):
        result = self.orchestrator.process_frame({'vision_score': 0.85, 'gas_ppm': 500.0})
        self.assertTrue(result.alarm)
        self.assertEqual(result.severity, SeverityLevel.HIGH)

    def test_detection_history_cap(self):
        for _ in range(150):
            self.orchestrator.process_frame({'gas_ppm': 500.0})
        self.assertLessEqual(len(self.orchestrator.detection_history), self.orchestrator.max_history)


if __name__ == '__main__':
    unittest.main()
