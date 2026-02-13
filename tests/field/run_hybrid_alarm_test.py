import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "embereye-field" / "fieldglass"))
sys.path.insert(0, str(root))

from embereye.core.vision_detector import VisionDetector  # noqa: E402
from main_window import BEMainWindow  # noqa: E402
from _test_utils import get_log_path, log_line


def _make_window_stub():
    mw = BEMainWindow.__new__(BEMainWindow)
    mw._rule_engine = VisionDetector(yolo_model_path="__no_model__")
    mw._rule_min_fusion_conf = 0.3
    mw._rule_min_yolo_conf = 0.5
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

    log_line(log_path, "[HYBRID] Rule evaluation test completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
