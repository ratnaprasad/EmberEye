import os
import time
from pathlib import Path
from typing import Optional


def get_log_path(name: str) -> Path:
    root = Path(__file__).resolve().parent
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{name}_{ts}.log"


def get_screenshot_dir() -> Path:
    root = Path(__file__).resolve().parent
    shot_dir = root / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    return shot_dir


def log_line(log_path: Path, message: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        # Fallback: remove non-ASCII characters if utf-8 fails
        try:
            line_ascii = line.encode('ascii', 'replace').decode('ascii')
            with open(log_path, "a") as f:
                f.write(line_ascii + "\n")
        except Exception:
            pass


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _ensure_qt_app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return None
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def _sanitize_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)


def capture_widget_screenshot(name: str, widget, log_path: Optional[Path] = None) -> Optional[Path]:
    app = _ensure_qt_app()
    if not app:
        if log_path:
            log_line(log_path, "WARNING: PyQt5 not available; screenshot skipped")
        return None

    shot_dir = get_screenshot_dir()
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_name(name)
    path = shot_dir / f"{safe_name}_{ts}.png"

    try:
        app.processEvents()
        pixmap = widget.grab()
        pixmap.save(str(path))
        if log_path:
            log_line(log_path, f"[SCREENSHOT] {path.name}")
        return path
    except Exception as e:
        if log_path:
            log_line(log_path, f"WARNING: Screenshot failed: {e}")
        return None


def capture_text_screenshot(name: str, text: str, log_path: Optional[Path] = None, width: int = 800, height: int = 450) -> Optional[Path]:
    app = _ensure_qt_app()
    if not app:
        if log_path:
            log_line(log_path, "WARNING: PyQt5 not available; screenshot skipped")
        return None

    try:
        from PyQt6.QtGui import QImage, QPainter, QColor, QFont
        from PyQt6.QtCore import Qt, QRect
    except Exception as e:
        if log_path:
            log_line(log_path, f"WARNING: Qt imports failed: {e}")
        return None

    shot_dir = get_screenshot_dir()
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_name(name)
    path = shot_dir / f"{safe_name}_{ts}.png"

    img = QImage(width, height, QImage.Format_RGB32)
    img.fill(QColor(245, 245, 245))

    painter = QPainter(img)
    painter.setPen(QColor(20, 20, 20))
    painter.setFont(QFont("Segoe UI", 12))
    rect = QRect(20, 20, width - 40, height - 40)
    painter.drawText(rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
    painter.end()

    try:
        img.save(str(path))
        if log_path:
            log_line(log_path, f"[SCREENSHOT] {path.name}")
        return path
    except Exception as e:
        if log_path:
            log_line(log_path, f"WARNING: Screenshot save failed: {e}")
        return None
