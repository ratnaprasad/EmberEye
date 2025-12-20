from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QCheckBox, QSpinBox, QPushButton, QColorDialog, QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPalette


class ThermalGridConfigDialog(QDialog):
    """Dialog for configuring thermal grid overlay settings."""
    
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, parent=None, initial_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Thermal Grid Configuration")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        # Default settings
        self.settings = {
            'enabled': True,
            'rows': 24,
            'cols': 32,
            'cell_color': QColor(255, 0, 0, 180),  # Semi-transparent red
            'border_color': QColor(255, 255, 0, 200),  # Yellow border
            'border_width': 2,
            'temp_threshold': 40.0,  # Celsius - basic threshold
            'critical_temp_threshold': 60.0  # Celsius - immediate alarm threshold
        }
        
        # Override with initial settings if provided
        if initial_settings:
            self.settings.update(initial_settings)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        
        # Enable/Disable thermal grid
        self.enable_checkbox = QCheckBox("Enable Thermal Grid Overlay")
        self.enable_checkbox.setChecked(self.settings['enabled'])
        layout.addWidget(self.enable_checkbox)
        
        # Grid dimensions group
        grid_group = QGroupBox("Grid Dimensions")
        grid_layout = QVBoxLayout()
        
        # Rows
        rows_layout = QHBoxLayout()
        rows_layout.addWidget(QLabel("Rows:"))
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setRange(1, 100)
        self.rows_spinbox.setValue(self.settings['rows'])
        rows_layout.addWidget(self.rows_spinbox)
        rows_layout.addStretch()
        grid_layout.addLayout(rows_layout)
        
        # Columns
        cols_layout = QHBoxLayout()
        cols_layout.addWidget(QLabel("Columns:"))
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setRange(1, 100)
        self.cols_spinbox.setValue(self.settings['cols'])
        cols_layout.addWidget(self.cols_spinbox)
        cols_layout.addStretch()
        grid_layout.addLayout(cols_layout)
        
        grid_group.setLayout(grid_layout)
        layout.addWidget(grid_group)
        
        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QVBoxLayout()
        
        # Cell color
        cell_color_layout = QHBoxLayout()
        cell_color_layout.addWidget(QLabel("Cell Fill Color:"))
        self.cell_color_btn = QPushButton()
        self.cell_color_btn.setFixedSize(50, 25)
        self.update_color_button(self.cell_color_btn, self.settings['cell_color'])
        self.cell_color_btn.clicked.connect(lambda: self.choose_color('cell'))
        cell_color_layout.addWidget(self.cell_color_btn)
        cell_color_layout.addStretch()
        appearance_layout.addLayout(cell_color_layout)
        
        # Border color
        border_color_layout = QHBoxLayout()
        border_color_layout.addWidget(QLabel("Border Color:"))
        self.border_color_btn = QPushButton()
        self.border_color_btn.setFixedSize(50, 25)
        self.update_color_button(self.border_color_btn, self.settings['border_color'])
        self.border_color_btn.clicked.connect(lambda: self.choose_color('border'))
        border_color_layout.addWidget(self.border_color_btn)
        border_color_layout.addStretch()
        appearance_layout.addLayout(border_color_layout)
        
        # Border width
        border_width_layout = QHBoxLayout()
        border_width_layout.addWidget(QLabel("Border Width:"))
        self.border_width_spinbox = QSpinBox()
        self.border_width_spinbox.setRange(1, 10)
        self.border_width_spinbox.setValue(self.settings['border_width'])
        border_width_layout.addWidget(self.border_width_spinbox)
        border_width_layout.addStretch()
        appearance_layout.addLayout(border_width_layout)
        
        appearance_group.setLayout(appearance_layout)
        layout.addWidget(appearance_group)
        
        # Detection threshold group
        threshold_group = QGroupBox("Temperature Thresholds")
        threshold_layout = QVBoxLayout()
        
        # Basic temperature threshold
        basic_temp_layout = QHBoxLayout()
        basic_temp_layout.addWidget(QLabel("Basic Threshold (°C):"))
        self.temp_threshold_spinbox = QSpinBox()
        self.temp_threshold_spinbox.setRange(0, 200)
        self.temp_threshold_spinbox.setValue(int(self.settings['temp_threshold']))
        self.temp_threshold_spinbox.setToolTip("Temperature for multi-source alarm detection")
        basic_temp_layout.addWidget(self.temp_threshold_spinbox)
        basic_temp_layout.addStretch()
        threshold_layout.addLayout(basic_temp_layout)
        
        # Critical temperature threshold
        critical_temp_layout = QHBoxLayout()
        critical_temp_layout.addWidget(QLabel("Critical Threshold (°C):"))
        self.critical_temp_threshold_spinbox = QSpinBox()
        self.critical_temp_threshold_spinbox.setRange(0, 200)
        self.critical_temp_threshold_spinbox.setValue(int(self.settings['critical_temp_threshold']))
        self.critical_temp_threshold_spinbox.setToolTip("Temperature for immediate alarm (overrides multi-source requirement)")
        critical_temp_layout.addWidget(self.critical_temp_threshold_spinbox)
        critical_temp_layout.addStretch()
        threshold_layout.addLayout(critical_temp_layout)
        
        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_settings)
        button_layout.addWidget(apply_btn)
        
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept_settings)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def update_color_button(self, button, color):
        """Update button background to show selected color."""
        button.setStyleSheet(f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});")
    
    def choose_color(self, color_type):
        """Open color picker dialog."""
        initial_color = self.settings['cell_color'] if color_type == 'cell' else self.settings['border_color']
        color = QColorDialog.getColor(initial_color, self, "Choose Color", QColorDialog.ShowAlphaChannel)
        
        if color.isValid():
            if color_type == 'cell':
                self.settings['cell_color'] = color
                self.update_color_button(self.cell_color_btn, color)
            else:
                self.settings['border_color'] = color
                self.update_color_button(self.border_color_btn, color)
    
    def gather_settings(self):
        """Collect current settings from UI controls."""
        return {
            'enabled': self.enable_checkbox.isChecked(),
            'rows': self.rows_spinbox.value(),
            'cols': self.cols_spinbox.value(),
            'cell_color': self.settings['cell_color'],
            'border_color': self.settings['border_color'],
            'border_width': self.border_width_spinbox.value(),
            'temp_threshold': float(self.temp_threshold_spinbox.value()),
            'critical_temp_threshold': float(self.critical_temp_threshold_spinbox.value())
        }
    
    def apply_settings(self):
        """Apply settings without closing dialog."""
        self.settings = self.gather_settings()
        self.settings_changed.emit(self.settings)
    
    def accept_settings(self):
        """Apply settings and close dialog."""
        self.apply_settings()
        self.accept()
    
    def get_settings(self):
        """Return current settings."""
        return self.settings
