from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QGridLayout
from PyQt6.QtCore import Qt

from _test_utils import get_log_path, log_line, assert_true, capture_widget_screenshot


def _make_label(name: str, color: str) -> QLabel:
    label = QLabel(name)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet(f"background-color: {color}; color: white; font-size: 16px;")
    label.setMinimumSize(320, 180)
    return label


def main() -> int:
    log_path = get_log_path("multi_camera_grid")
    app = QApplication.instance() or QApplication([])

    widget = QWidget()
    widget.setWindowTitle("Multi-Camera Grid")
    grid = QGridLayout()
    widget.setLayout(grid)

    labels = [
        _make_label("Cam 1", "#2d6a4f"),
        _make_label("Cam 2", "#1d3557"),
        _make_label("Cam 3", "#6a4c93"),
        _make_label("Cam 4", "#8d0801"),
    ]

    grid.addWidget(labels[0], 0, 0)
    grid.addWidget(labels[1], 0, 1)
    grid.addWidget(labels[2], 1, 0)
    grid.addWidget(labels[3], 1, 1)

    widget.resize(700, 450)
    widget.show()

    try:
        app.processEvents()
        assert_true(grid.count() == 4, "Expected 4 camera tiles in grid")
        assert_true(grid.itemAtPosition(0, 0) is not None, "Missing tile at (0,0)")
        assert_true(grid.itemAtPosition(0, 1) is not None, "Missing tile at (0,1)")
        assert_true(grid.itemAtPosition(1, 0) is not None, "Missing tile at (1,0)")
        assert_true(grid.itemAtPosition(1, 1) is not None, "Missing tile at (1,1)")

        capture_widget_screenshot("multi_camera_grid", widget, log_path)
        log_line(log_path, "[GRID] Multi-camera layout validated")
        return 0
    except Exception as e:
        log_line(log_path, f"ERROR: Multi-camera grid test failed: {e}")
        return 1
    finally:
        widget.close()


if __name__ == "__main__":
    raise SystemExit(main())
