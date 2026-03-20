"""
Theme Manager for EmberEye Application
Modern UI theme with dark styling only
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings


class ThemeManager:
    """Manages application theme (modern only)."""

    MODERN = "modern"

    COLORS = {
        "modern": {
            "primary": "#00bcd4",
            "danger": "#ff5252",
            "warning": "#ffc107",
            "info": "#448aff",
            "success": "#69f0ae",
            "bg_primary": "#1e1e1e",
            "bg_secondary": "#252525",
            "bg_tertiary": "#2d2d2d",
            "text_primary": "#e0e0e0",
            "text_secondary": "#9e9e9e",
            "border": "#404040",
            "accent": "#00bcd4",
            "hover": "#00acc1",
        }
    }

    def __init__(self):
        self.settings = QSettings("EmberEye", "Theme")
        self.current_theme = self.MODERN

    def set_theme(self, theme_name):
        """Set and persist theme choice (modern only)."""
        self.current_theme = self.MODERN
        self.settings.setValue("theme", self.MODERN)

    def get_theme(self):
        return self.current_theme

    def get_colors(self):
        return self.COLORS["modern"]

    def apply_theme(self, app: QApplication):
        if not app:
            return
        stylesheet = self.get_modern_stylesheet()
        app.setStyleSheet(stylesheet)
        app.setProperty("theme", self.current_theme)

    def get_modern_stylesheet(self):
        colors = self.COLORS["modern"]
        return f"""
/* ========================================
   MODERN THEME - EmberEye
   Slim, Professional, Video-Focused Design
   ======================================== */

/* Global Application Styles */
QMainWindow {{
    background-color: {colors['bg_primary']};
    color: {colors['text_primary']};
}}

QWidget {{
    background-color: {colors['bg_primary']};
    color: {colors['text_primary']};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

QLabel {{
    color: {colors['text_primary']};
    font-size: 12px;
}}

QPushButton {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    padding: 6px 12px;
    border-radius: 4px;
}}
QPushButton:hover {{
    background-color: {colors['hover']};
    color: #ffffff;
    border: 1px solid {colors['accent']};
}}
QPushButton:pressed {{
    background-color: {colors['accent']};
    color: #ffffff;
}}

QLineEdit, QComboBox {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    padding: 6px;
    border-radius: 4px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {colors['accent']};
}}

QTabWidget::pane {{
    border: none;
    background: {colors['bg_primary']};
}}
QTabBar {{
    background: {colors['bg_primary']};
    alignment: center;
}}
QTabBar::tab {{
    background: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    padding: 12px 40px;
    margin: 0px 4px;
    border: none;
    border-top: 3px solid transparent;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 2px;
    min-width: 140px;
}}
QTabBar::tab:selected {{
    background: {colors['bg_primary']};
    color: {colors['accent']};
    border-top-color: {colors['accent']};
}}
QTabBar::tab:hover:!selected {{
    background: {colors['bg_tertiary']};
    color: {colors['text_primary']};
}}

QScrollBar:vertical {{
    background: {colors['bg_secondary']};
    width: 12px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {colors['accent']};
    min-height: 20px;
    border-radius: 6px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
"""
