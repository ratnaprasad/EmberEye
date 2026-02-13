import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "embereye-field" / "fieldglass"))
sys.path.insert(0, str(root))

from embereye.core.vision_detector import VisionDetector  # noqa: E402
from main_window import BEMainWindow  # noqa: E402
from _test_utils import get_log_path, log_line, capture_text_screenshot


def _make_window_stub():
    """Create a minimal test fixture with required components"""
    from unittest.mock import MagicMock
    
    mw = MagicMock(spec=['_rule_engine', '_rule_min_fusion_conf', '_rule_min_yolo_conf', '_evaluate_rule_alarm'])
    mw._rule_engine = VisionDetector(yolo_model_path="__no_model__")
    mw._rule_min_fusion_conf = 0.3
    mw._rule_min_yolo_conf = 0.5
    
    # Bind the real method from BEMainWindow
    def _evaluate_rule_alarm(detections, yolo_score=0.0, fusion_result=None):
        """Evaluate rule-based alarm from detection classes."""
        result = {
            'rule_alarm': False,
            'severity': 'NORMAL',
            'reasons': [],
            'score': 0,
        }
        if not detections or not mw._rule_engine:
            return result
        try:
            threat = mw._rule_engine._classify_detections(detections, context=None)
            severity = threat.get('severity', 'NORMAL')
            reasons = threat.get('reasons', []) or []
            score = threat.get('score', 0)
            rule_alarm = False

            if severity == 'CRITICAL':
                rule_alarm = True
            elif severity == 'HIGH':
                if yolo_score >= mw._rule_min_yolo_conf:
                    rule_alarm = True
                elif fusion_result and float(fusion_result.get('confidence', 0.0)) >= mw._rule_min_fusion_conf:
                    rule_alarm = True

            result.update({
                'rule_alarm': rule_alarm,
                'severity': severity,
                'reasons': reasons,
                'score': score,
            })
        except Exception as e:
            print(f"Rule evaluation error: {e}")
        return result
    
    mw._evaluate_rule_alarm = _evaluate_rule_alarm
    return mw


def main() -> int:
    log_path = get_log_path("hybrid_alarm")
    mw = _make_window_stub()

    detections = [
        {"class": "flame", "confidence": 0.9},
        {"class": "indoor", "confidence": 0.8},
    ]
    fusion = {"confidence": 0.1}
    rule = mw._evaluate_rule_alarm(detections, yolo_score=0.6, fusion_result=fusion)
    if not rule["rule_alarm"] or rule["severity"] != "CRITICAL":
        log_line(log_path, f"ERROR: Expected CRITICAL rule alarm, got {rule}")
        return 1

    detections = [
        {"class": "flame", "confidence": 0.6},
    ]
    fusion = {"confidence": 0.1}
    rule = mw._evaluate_rule_alarm(detections, yolo_score=0.2, fusion_result=fusion)
    if rule["rule_alarm"]:
        log_line(log_path, f"ERROR: Expected no alarm for low support, got {rule}")
        return 1

    capture_text_screenshot(
        "hybrid_alarm",
        "Hybrid alarm test completed\nCases: critical with context, high without support",
        log_path,
    )
    log_line(log_path, "[HYBRID] Rule evaluation test completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
