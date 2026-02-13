import sys
from pathlib import Path

from _test_utils import get_log_path, log_line, assert_true, capture_text_screenshot

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

from embereye.core.vision_detector import VisionDetector  # noqa: E402


def _evaluate_rule_alarm(detector, detections, yolo_score, fusion_result, min_yolo, min_fusion):
    result = {
        "rule_alarm": False,
        "severity": "NORMAL",
        "reasons": [],
        "score": 0,
    }
    if not detections or not detector:
        return result

    threat = detector._classify_detections(detections, context=None)
    severity = threat.get("severity", "NORMAL")
    reasons = threat.get("reasons", []) or []
    score = threat.get("score", 0)
    rule_alarm = False

    if severity == "CRITICAL":
        rule_alarm = True
    elif severity == "HIGH":
        if yolo_score >= min_yolo:
            rule_alarm = True
        elif fusion_result and float(fusion_result.get("confidence", 0.0)) >= min_fusion:
            rule_alarm = True

    result.update({
        "rule_alarm": rule_alarm,
        "severity": severity,
        "reasons": reasons,
        "score": score,
    })
    return result


def main() -> int:
    log_path = get_log_path("threshold_config")
    detector = VisionDetector(yolo_model_path="__no_model__")

    try:
        detections = [{"class": "flame", "confidence": 0.8}]

        rule = _evaluate_rule_alarm(
            detector,
            detections,
            yolo_score=0.6,
            fusion_result={"confidence": 0.1},
            min_yolo=0.5,
            min_fusion=0.3,
        )
        assert_true(rule["rule_alarm"], f"Expected alarm when yolo >= threshold, got {rule}")

        rule = _evaluate_rule_alarm(
            detector,
            detections,
            yolo_score=0.2,
            fusion_result={"confidence": 0.1},
            min_yolo=0.5,
            min_fusion=0.3,
        )
        assert_true(not rule["rule_alarm"], f"Expected no alarm for low scores, got {rule}")

        rule = _evaluate_rule_alarm(
            detector,
            detections,
            yolo_score=0.2,
            fusion_result={"confidence": 0.6},
            min_yolo=0.5,
            min_fusion=0.3,
        )
        assert_true(rule["rule_alarm"], f"Expected alarm when fusion >= threshold, got {rule}")

        rule = _evaluate_rule_alarm(
            detector,
            detections,
            yolo_score=0.6,
            fusion_result={"confidence": 0.5},
            min_yolo=0.8,
            min_fusion=0.6,
        )
        assert_true(not rule["rule_alarm"], f"Expected no alarm for raised thresholds, got {rule}")

        capture_text_screenshot(
            "threshold_config",
            "Threshold config test completed\nCases: yolo on, yolo off, fusion on, thresholds raised",
            log_path,
        )
        log_line(log_path, "[THRESHOLD] Config test completed")
        return 0
    except Exception as e:
        log_line(log_path, f"ERROR: Threshold config test failed: {e}")
        capture_text_screenshot("threshold_config_error", f"Threshold config failed\n{e}", log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
