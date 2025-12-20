"""
Theme Manager for EmberEye Application
Provides Classic and Modern UI themes with centralized styling
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

class ThemeManager:
    """Manages application themes and styling"""
    
    CLASSIC = "classic"
    MODERN = "modern"
    
    # Color Palettes
    COLORS = {
        "classic": {
            "primary": "#4CAF50",
            "danger": "#f44336",
            "warning": "#ff9800",
            "info": "#2196F3",
            "success": "#4CAF50",
            "bg_primary": "#ffffff",
            "bg_secondary": "#f5f5f5",
            "text_primary": "#333333",
            "text_secondary": "#666666",
            "border": "#e0e0e0"
        },
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
            "hover": "#00acc1"
        }
    }
    
    def __init__(self):
        self.settings = QSettings("EmberEye", "Theme")
        self.current_theme = self.settings.value("theme", self.CLASSIC)
    
    def set_theme(self, theme_name):
        """Set and persist theme choice"""
        if theme_name in [self.CLASSIC, self.MODERN]:
            self.current_theme = theme_name
            self.settings.setValue("theme", theme_name)
    
    def get_theme(self):
        """Get current theme"""
        return self.current_theme
    
    def get_colors(self):
        """Get color palette for current theme"""
        return self.COLORS.get(self.current_theme, self.COLORS["classic"])
    
    def get_classic_stylesheet(self):
        """Classic theme stylesheet (minimal changes to existing)"""
        return ""
    
    def get_modern_stylesheet(self):
        """Modern theme stylesheet with all enhancements"""
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
    font-size: 13px;
}}

/* ========================================
   BUTTONS - Enhanced with Icons & Hover
   ======================================== */

QPushButton {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 32px;
    transition: all 0.2s ease;
}}

QPushButton:hover {{
    background-color: {colors['bg_tertiary']};
    border-color: {colors['accent']};
    transform: translateY(-1px);
}}

QPushButton:pressed {{
    background-color: {colors['bg_primary']};
    transform: translateY(0px);
}}

QPushButton:disabled {{
    background-color: {colors['bg_primary']};
    color: {colors['text_secondary']};
    border-color: {colors['border']};
    opacity: 0.5;
}}

/* Primary Action Buttons */
QPushButton#primary, QPushButton.primary {{
    background-color: {colors['primary']};
    color: #ffffff;
    border: none;
    font-weight: 600;
}}

QPushButton#primary:hover, QPushButton.primary:hover {{
    background-color: {colors['hover']};
    box-shadow: 0 4px 12px rgba(0, 188, 212, 0.3);
}}

/* Danger Buttons */
QPushButton#danger, QPushButton.danger {{
    background-color: {colors['danger']};
    color: #ffffff;
    border: none;
}}

QPushButton#danger:hover, QPushButton.danger:hover {{
    background-color: #ff6b6b;
}}

/* Success Buttons */
QPushButton#success, QPushButton.success {{
    background-color: {colors['success']};
    color: #1e1e1e;
    border: none;
    font-weight: 600;
}}

QPushButton#success:hover, QPushButton.success:hover {{
    background-color: #81f4ae;
}}

/* Icon Buttons (Small, Compact) */
QPushButton.icon-btn {{
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
    padding: 0px;
    border-radius: 18px;
    font-size: 16px;
}}

QPushButton.icon-btn:hover {{
    background-color: {colors['accent']};
    color: #ffffff;
}}

/* ========================================
   INPUTS - Text Fields, Combos
   ======================================== */

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: {colors['primary']};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {colors['accent']};
    outline: none;
}}

QComboBox {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 32px;
}}

QComboBox:hover {{
    border-color: {colors['accent']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {colors['text_primary']};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    selection-background-color: {colors['accent']};
    selection-color: #ffffff;
}}

/* ========================================
   LABELS & TEXT
   ======================================== */

QLabel {{
    color: {colors['text_primary']};
    background-color: transparent;
}}

QLabel.heading {{
    font-size: 18px;
    font-weight: 600;
    color: {colors['text_primary']};
}}

QLabel.subheading {{
    font-size: 14px;
    font-weight: 500;
    color: {colors['text_secondary']};
}}

QLabel.caption {{
    font-size: 11px;
    color: {colors['text_secondary']};
}}

/* Status Labels */
QLabel.status-online {{
    color: {colors['success']};
    font-weight: 600;
}}

QLabel.status-offline {{
    color: {colors['danger']};
    font-weight: 600;
}}

QLabel.status-warning {{
    color: {colors['warning']};
    font-weight: 600;
}}

/* ========================================
   TABS - Slim, Modern Design
   ======================================== */

QTabWidget::pane {{
    border: 1px solid {colors['border']};
    border-radius: 6px;
    background-color: {colors['bg_primary']};
    padding: 4px;
}}

QTabBar::tab {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    margin-right: 2px;
    font-weight: 500;
}}

QTabBar::tab:hover {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_primary']};
}}

QTabBar::tab:selected {{
    background-color: {colors['bg_primary']};
    color: {colors['accent']};
    border-bottom: 2px solid {colors['accent']};
}}

/* ========================================
   TABLES - Clean, Professional
   ======================================== */

QTableWidget, QTableView {{
    background-color: {colors['bg_primary']};
    alternate-background-color: {colors['bg_secondary']};
    gridline-color: {colors['border']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    selection-background-color: {colors['accent']};
    selection-color: #ffffff;
}}

QTableWidget::item, QTableView::item {{
    padding: 8px;
    border: none;
}}

QHeaderView::section {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: none;
    border-right: 1px solid {colors['border']};
    border-bottom: 1px solid {colors['border']};
    padding: 8px;
    font-weight: 600;
}}

/* ========================================
   SCROLLBARS - Slim, Unobtrusive
   ======================================== */

QScrollBar:vertical {{
    background-color: {colors['bg_primary']};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {colors['border']};
    border-radius: 5px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {colors['text_secondary']};
}}

QScrollBar:horizontal {{
    background-color: {colors['bg_primary']};
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background-color: {colors['border']};
    border-radius: 5px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {colors['text_secondary']};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    background: none;
    border: none;
}}

/* ========================================
   GROUPBOX - Card-Style Containers
   ======================================== */

QGroupBox {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    color: {colors['text_primary']};
    background-color: {colors['bg_secondary']};
}}

/* ========================================
   DIALOGS - Professional Windows
   ======================================== */

QDialog {{
    background-color: {colors['bg_primary']};
    border-radius: 8px;
}}

QMessageBox {{
    background-color: {colors['bg_primary']};
}}

/* ========================================
   CHECKBOXES & RADIO BUTTONS
   ======================================== */

QCheckBox, QRadioButton {{
    color: {colors['text_primary']};
    spacing: 8px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {colors['border']};
    border-radius: 4px;
    background-color: {colors['bg_secondary']};
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {colors['accent']};
}}

QCheckBox::indicator:checked {{
    background-color: {colors['accent']};
    border-color: {colors['accent']};
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTAgM0w0LjUgOC41TDIgNiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=);
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}

QRadioButton::indicator:checked {{
    background-color: {colors['accent']};
    border-color: {colors['accent']};
}}

/* ========================================
   SLIDERS
   ======================================== */

QSlider::groove:horizontal {{
    background-color: {colors['bg_secondary']};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {colors['accent']};
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}}

QSlider::handle:horizontal:hover {{
    background-color: {colors['hover']};
}}

/* ========================================
   PROGRESS BARS
   ======================================== */

QProgressBar {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    height: 24px;
    text-align: center;
    color: {colors['text_primary']};
}}

QProgressBar::chunk {{
    background-color: {colors['accent']};
    border-radius: 5px;
}}

/* ========================================
   TOOLTIPS
   ======================================== */

QToolTip {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ========================================
   MENU & TOOLBAR - Compact Design
   ======================================== */

QMenuBar {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border-bottom: 1px solid {colors['border']};
    padding: 2px;
}}

QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {colors['bg_tertiary']};
}}

QMenu {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {colors['accent']};
    color: #ffffff;
}}

QToolBar {{
    background-color: {colors['bg_secondary']};
    border: none;
    spacing: 4px;
    padding: 4px;
}}

QToolButton {{
    background-color: transparent;
    color: {colors['text_primary']};
    border: none;
    border-radius: 4px;
    padding: 8px;
}}

QToolButton:hover {{
    background-color: {colors['bg_tertiary']};
}}

/* ========================================
   STATUS BAR - Minimal
   ======================================== */

QStatusBar {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    border-top: 1px solid {colors['border']};
    padding: 4px;
}}

/* ========================================
   VIDEO WIDGET OVERLAY - Slim Controls
   ======================================== */

QWidget#video_controls {{
    background-color: rgba(30, 30, 30, 0.85);
    border-radius: 8px;
    padding: 4px;
}}

QWidget#video_status {{
    background-color: rgba(30, 30, 30, 0.85);
    border-radius: 6px;
    padding: 6px 10px;
}}

/* LED Status Indicators */
QLabel#led_online {{
    background-color: {colors['success']};
    border-radius: 6px;
    min-width: 12px;
    min-height: 12px;
    max-width: 12px;
    max-height: 12px;
}}

QLabel#led_offline {{
    background-color: {colors['danger']};
    border-radius: 6px;
    min-width: 12px;
    min-height: 12px;
    max-width: 12px;
    max-height: 12px;
}}

QLabel#led_connecting {{
    background-color: {colors['warning']};
    border-radius: 6px;
    min-width: 12px;
    min-height: 12px;
    max-width: 12px;
    max-height: 12px;
}}

/* ========================================
   NOTIFICATION PANEL
   ======================================== */

QWidget#notification {{
    background-color: {colors['bg_tertiary']};
    border: 1px solid {colors['accent']};
    border-left: 4px solid {colors['accent']};
    border-radius: 6px;
    padding: 12px;
}}

QWidget#notification_warning {{
    border-left-color: {colors['warning']};
}}

QWidget#notification_error {{
    border-left-color: {colors['danger']};
}}

QWidget#notification_success {{
    border-left-color: {colors['success']};
}}

/* ========================================
   ANIMATIONS & TRANSITIONS
   ======================================== */

* {{
    outline: none;
}}

/* Focus styles */
QLineEdit:focus, QTextEdit:focus, QPushButton:focus {{
    border-color: {colors['accent']};
}}

/* ========================================
   CUSTOM COMPONENTS
   ======================================== */

/* Temperature Display */
QLabel#temp_normal {{
    color: {colors['text_primary']};
    font-size: 14px;
    font-weight: 600;
}}

QLabel#temp_warning {{
    color: {colors['warning']};
    font-size: 14px;
    font-weight: 600;
}}

QLabel#temp_critical {{
    color: {colors['danger']};
    font-size: 14px;
    font-weight: 600;
}}

/* Metrics Card */
QWidget#metric_card {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border']};
    border-radius: 8px;
    padding: 16px;
}}

QWidget#metric_card:hover {{
    border-color: {colors['accent']};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}}

/* ========================================
   RESPONSIVE ADJUSTMENTS
   ======================================== */

/* Compact mode for smaller screens */
@media (max-width: 1280px) {{
    QPushButton {{
        padding: 6px 12px;
        min-height: 28px;
    }}
    
    QTabBar::tab {{
        padding: 8px 16px;
    }}
}}
"""
    
    def apply_theme(self, app):
        """Apply current theme to application"""
        if self.current_theme == self.MODERN:
            stylesheet = self.get_modern_stylesheet()
        else:
            stylesheet = self.get_classic_stylesheet()
        
        app.setStyleSheet(stylesheet)
        
        # Store theme choice for widgets that need it
        app.setProperty("theme", self.current_theme)
