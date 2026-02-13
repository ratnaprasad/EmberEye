import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "embereye-field" / "fieldglass"))

from video_widget import VideoWidget  # noqa: E402
from _test_utils import get_log_path, log_line, assert_true  # noqa: E402


def _build_matrix(rows=24, cols=32):
    matrix = []
    for r in range(rows):
        row = []
        for c in range(cols):
            row.append(20.0 + (r + c) * 0.5)
        matrix.append(row)
    return matrix


def main() -> int:
    app = QApplication.instance() or QApplication([])
    widget = VideoWidget("rtsp://127.0.0.1/dummy", "Test", "test", start_worker=False)
    widget.resize(640, 480)
    widget.show()
    log_path = get_log_path("ui_toggle")

    try:
        matrix = _build_matrix()
        widget._handle_thermal_data(matrix)

        img = QImage(640, 480, QImage.Format_RGB888)
        img.fill(Qt.black)
        pix = QPixmap.fromImage(img)

        widget.set_display_mode("default")
        widget.update_frame(pix)
        app.processEvents()
        log_line(log_path, "Default mode rendered")

        widget.set_display_mode("thermal")
        widget.update_frame(pix)
        app.processEvents()
        log_line(log_path, "Thermal mode rendered")

        widget.set_display_mode("grid")
        widget.update_frame(pix)
        app.processEvents()
        log_line(log_path, "Grid mode rendered")

        # Alarm color assertion
        widget.update_fire_alarm(True)
        app.processEvents()
        assert_true(widget.fire_alarm_status.objectName() == "led_offline", "Alarm LED did not switch to red state")
        log_line(log_path, "Alarm LED set to red")

        widget.update_fire_alarm(False)
        app.processEvents()
        assert_true(widget.fire_alarm_status.objectName() == "led_online", "Alarm LED did not switch to green state")
        log_line(log_path, "Alarm LED set to green")

        # Fusion overlay assertion (no crash and pixmap present)
        widget.set_display_mode("default")
        widget.set_fusion_data({
            "alarm": True,
            "confidence": 0.9,
            "sources": ["thermal", "smoke"],
            "hot_cells": [(1, 1), (2, 2)],
            "thermal_max": 65.0,
            "smoke_level": 30.0,
        })
        widget.update_frame(pix)
        app.processEvents()
        assert_true(widget.show_fusion_overlay, "Fusion overlay flag not enabled")
        assert_true(widget.video_label.pixmap() is not None, "Fusion overlay did not render a pixmap")
        log_line(log_path, "Fusion overlay rendered")

        log_line(log_path, "[UI] Toggle test completed")
        return 0
    except Exception as e:
        log_line(log_path, f"ERROR: UI toggle test failed: {e}")
        return 1
    finally:
        widget.close()


if __name__ == "__main__":
    raise SystemExit(main())
