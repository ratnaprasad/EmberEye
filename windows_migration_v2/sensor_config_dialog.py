from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QDoubleSpinBox, QSpinBox, QPushButton, QGroupBox, QCheckBox, QTabWidget, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal


class SensorConfigDialog(QDialog):
    """Dialog for configuring sensor fusion and detection parameters."""
    
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, parent=None, initial_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Sensor Configuration")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        # Default settings
        self.settings = {
            # Fusion parameters
            'temp_threshold': 160,  # 0-255 scale (≈40°C)
            'gas_ppm_threshold': 400,
            'flame_active_value': 1,
            'min_sources': 2,
            
            # Gas sensor calibration (MQ-135)
            'gas_r0': 76.63,  # Calibrated R0 in clean air
            'gas_rl': 1.0,    # Load resistance in kΩ
            'gas_vcc': 5.0,   # Supply voltage
            
            # Display settings
            'hot_cell_decay_time': 5.0,  # Seconds to keep hot cells visible
            'freeze_on_alarm': True,
            'show_fusion_overlay': True,
            
            # Vision detection
            'vision_threshold': 0.7,
            'vision_confidence_weight': 0.5
        }
        
        # Override with initial settings if provided
        if initial_settings:
            self.settings.update(initial_settings)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        
        # Create tabs for different configuration sections
        tabs = QTabWidget()
        
        # Tab 1: Fusion Thresholds
        fusion_tab = self.create_fusion_tab()
        tabs.addTab(fusion_tab, "Fusion Thresholds")
        
        # Tab 2: Gas Sensor Calibration
        gas_tab = self.create_gas_sensor_tab()
        tabs.addTab(gas_tab, "Gas Sensor")
        
        # Tab 3: Display Settings
        display_tab = self.create_display_tab()
        tabs.addTab(display_tab, "Display")
        
        layout.addWidget(tabs)
        
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
    
    def create_fusion_tab(self):
        """Create fusion threshold configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Temperature threshold
        temp_group = QGroupBox("Thermal Sensor")
        temp_layout = QVBoxLayout()
        
        temp_row = QHBoxLayout()
        temp_row.addWidget(QLabel("Temperature Threshold:"))
        self.temp_threshold_spin = QSpinBox()
        self.temp_threshold_spin.setRange(0, 255)
        self.temp_threshold_spin.setValue(int(self.settings['temp_threshold']))
        self.temp_threshold_spin.setSuffix(" units")
        temp_row.addWidget(self.temp_threshold_spin)
        
        temp_info = QLabel("Raw sensor value (0-255). 160 ≈ 40°C, 200 ≈ 50°C")
        temp_info.setStyleSheet("color: gray; font-size: 9pt;")
        temp_layout.addLayout(temp_row)
        temp_layout.addWidget(temp_info)
        temp_group.setLayout(temp_layout)
        layout.addWidget(temp_group)
        
        # Gas threshold
        gas_group = QGroupBox("Gas Sensor (MQ-135)")
        gas_layout = QVBoxLayout()
        
        gas_row = QHBoxLayout()
        gas_row.addWidget(QLabel("Gas PPM Threshold:"))
        self.gas_threshold_spin = QSpinBox()
        self.gas_threshold_spin.setRange(0, 10000)
        self.gas_threshold_spin.setValue(int(self.settings['gas_ppm_threshold']))
        self.gas_threshold_spin.setSuffix(" PPM")
        gas_row.addWidget(self.gas_threshold_spin)
        
        gas_info = QLabel("Gas concentration in parts per million. 400 PPM = normal air")
        gas_info.setStyleSheet("color: gray; font-size: 9pt;")
        gas_layout.addLayout(gas_row)
        gas_layout.addWidget(gas_info)
        gas_group.setLayout(gas_layout)
        layout.addWidget(gas_group)
        
        # Flame sensor
        flame_group = QGroupBox("Flame Sensor")
        flame_layout = QVBoxLayout()
        
        flame_row = QHBoxLayout()
        flame_row.addWidget(QLabel("Active Value:"))
        self.flame_value_spin = QSpinBox()
        self.flame_value_spin.setRange(0, 1)
        self.flame_value_spin.setValue(int(self.settings['flame_active_value']))
        flame_row.addWidget(self.flame_value_spin)
        
        flame_info = QLabel("Digital value indicating flame detection (0 or 1)")
        flame_info.setStyleSheet("color: gray; font-size: 9pt;")
        flame_layout.addLayout(flame_row)
        flame_layout.addWidget(flame_info)
        flame_group.setLayout(flame_layout)
        layout.addWidget(flame_group)
        
        # Vision detection
        vision_group = QGroupBox("Vision Detection")
        vision_layout = QVBoxLayout()
        
        vision_row = QHBoxLayout()
        vision_row.addWidget(QLabel("Confidence Threshold:"))
        self.vision_threshold_spin = QDoubleSpinBox()
        self.vision_threshold_spin.setRange(0.0, 1.0)
        self.vision_threshold_spin.setSingleStep(0.1)
        self.vision_threshold_spin.setValue(self.settings['vision_threshold'])
        vision_row.addWidget(self.vision_threshold_spin)
        
        vision_weight_row = QHBoxLayout()
        vision_weight_row.addWidget(QLabel("Confidence Weight:"))
        self.vision_weight_spin = QDoubleSpinBox()
        self.vision_weight_spin.setRange(0.0, 1.0)
        self.vision_weight_spin.setSingleStep(0.1)
        self.vision_weight_spin.setValue(self.settings['vision_confidence_weight'])
        vision_weight_row.addWidget(self.vision_weight_spin)
        
        vision_info = QLabel("AI model fire detection threshold and weight in fusion")
        vision_info.setStyleSheet("color: gray; font-size: 9pt;")
        vision_layout.addLayout(vision_row)
        vision_layout.addLayout(vision_weight_row)
        vision_layout.addWidget(vision_info)
        vision_group.setLayout(vision_layout)
        layout.addWidget(vision_group)
        
        # Minimum sources
        min_sources_group = QGroupBox("Fusion Logic")
        min_sources_layout = QVBoxLayout()
        
        min_sources_row = QHBoxLayout()
        min_sources_row.addWidget(QLabel("Minimum Active Sensors:"))
        self.min_sources_spin = QSpinBox()
        self.min_sources_spin.setRange(1, 4)
        self.min_sources_spin.setValue(int(self.settings['min_sources']))
        min_sources_row.addWidget(self.min_sources_spin)
        
        min_sources_info = QLabel("Minimum number of sensors required to trigger alarm")
        min_sources_info.setStyleSheet("color: gray; font-size: 9pt;")
        min_sources_layout.addLayout(min_sources_row)
        min_sources_layout.addWidget(min_sources_info)
        min_sources_group.setLayout(min_sources_layout)
        layout.addWidget(min_sources_group)
        
        layout.addStretch()
        return widget
    
    def create_gas_sensor_tab(self):
        """Create gas sensor calibration tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Calibration parameters
        calib_group = QGroupBox("MQ-135 Calibration")
        calib_layout = QVBoxLayout()
        
        # R0 value
        r0_row = QHBoxLayout()
        r0_row.addWidget(QLabel("R0 (Clean Air):"))
        self.gas_r0_spin = QDoubleSpinBox()
        self.gas_r0_spin.setRange(1.0, 1000.0)
        self.gas_r0_spin.setDecimals(2)
        self.gas_r0_spin.setValue(self.settings['gas_r0'])
        self.gas_r0_spin.setSuffix(" kΩ")
        r0_row.addWidget(self.gas_r0_spin)
        r0_row.addStretch()
        calib_layout.addLayout(r0_row)
        
        r0_info = QLabel("Sensor resistance in clean air (calibrate in known environment)")
        r0_info.setStyleSheet("color: gray; font-size: 9pt;")
        calib_layout.addWidget(r0_info)
        
        # Load resistance
        rl_row = QHBoxLayout()
        rl_row.addWidget(QLabel("Load Resistance (RL):"))
        self.gas_rl_spin = QDoubleSpinBox()
        self.gas_rl_spin.setRange(0.1, 100.0)
        self.gas_rl_spin.setDecimals(1)
        self.gas_rl_spin.setValue(self.settings['gas_rl'])
        self.gas_rl_spin.setSuffix(" kΩ")
        rl_row.addWidget(self.gas_rl_spin)
        rl_row.addStretch()
        calib_layout.addLayout(rl_row)
        
        rl_info = QLabel("Load resistor value in circuit (check hardware)")
        rl_info.setStyleSheet("color: gray; font-size: 9pt;")
        calib_layout.addWidget(rl_info)
        
        # Supply voltage
        vcc_row = QHBoxLayout()
        vcc_row.addWidget(QLabel("Supply Voltage (VCC):"))
        self.gas_vcc_spin = QDoubleSpinBox()
        self.gas_vcc_spin.setRange(3.0, 12.0)
        self.gas_vcc_spin.setDecimals(1)
        self.gas_vcc_spin.setValue(self.settings['gas_vcc'])
        self.gas_vcc_spin.setSuffix(" V")
        vcc_row.addWidget(self.gas_vcc_spin)
        vcc_row.addStretch()
        calib_layout.addLayout(vcc_row)
        
        vcc_info = QLabel("Circuit supply voltage (typically 5V)")
        vcc_info.setStyleSheet("color: gray; font-size: 9pt;")
        calib_layout.addWidget(vcc_info)
        
        calib_group.setLayout(calib_layout)
        layout.addWidget(calib_group)
        
        # Calibration guide
        guide_group = QGroupBox("Calibration Guide")
        guide_layout = QVBoxLayout()
        guide_text = QLabel(
            "1. Place sensor in clean, outdoor air for 24-48 hours\n"
            "2. Note the ADC reading when stabilized\n"
            "3. Calculate R0 = RL × (VCC/Vout - 1)\n"
            "4. Vout = ADC × VCC / 1024 (for 10-bit ADC)\n"
            "5. Enter calculated R0 value above\n\n"
            "Typical R0 values: 30-100 kΩ in clean air"
        )
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #e0e0e0; padding: 10px; background-color: #2a2a2a; border-radius: 5px;")
        guide_layout.addWidget(guide_text)
        guide_group.setLayout(guide_layout)
        layout.addWidget(guide_group)
        
        layout.addStretch()
        return widget
    
    def create_display_tab(self):
        """Create display settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Hot cell persistence
        persistence_group = QGroupBox("Hot Cell Persistence")
        persistence_layout = QVBoxLayout()
        
        decay_row = QHBoxLayout()
        decay_row.addWidget(QLabel("Decay Time:"))
        self.decay_time_spin = QDoubleSpinBox()
        self.decay_time_spin.setRange(1.0, 60.0)
        self.decay_time_spin.setSingleStep(1.0)
        self.decay_time_spin.setValue(self.settings['hot_cell_decay_time'])
        self.decay_time_spin.setSuffix(" seconds")
        decay_row.addWidget(self.decay_time_spin)
        decay_row.addStretch()
        persistence_layout.addLayout(decay_row)
        
        decay_info = QLabel("How long hot cells remain visible after detection")
        decay_info.setStyleSheet("color: gray; font-size: 9pt;")
        persistence_layout.addWidget(decay_info)
        persistence_group.setLayout(persistence_layout)
        layout.addWidget(persistence_group)
        
        # Frame freeze
        freeze_group = QGroupBox("Alarm Behavior")
        freeze_layout = QVBoxLayout()
        
        self.freeze_checkbox = QCheckBox("Freeze frame on alarm")
        self.freeze_checkbox.setChecked(self.settings['freeze_on_alarm'])
        freeze_layout.addWidget(self.freeze_checkbox)
        
        freeze_info = QLabel("Stop video updates when alarm is active to preserve evidence")
        freeze_info.setStyleSheet("color: gray; font-size: 9pt;")
        freeze_layout.addWidget(freeze_info)
        freeze_group.setLayout(freeze_layout)
        layout.addWidget(freeze_group)
        
        # Fusion overlay
        overlay_group = QGroupBox("Information Overlay")
        overlay_layout = QVBoxLayout()
        
        self.overlay_checkbox = QCheckBox("Show fusion data overlay")
        self.overlay_checkbox.setChecked(self.settings['show_fusion_overlay'])
        overlay_layout.addWidget(self.overlay_checkbox)
        
        overlay_info = QLabel("Display sensor readings, accuracy, and active sensors on video")
        overlay_info.setStyleSheet("color: gray; font-size: 9pt;")
        overlay_layout.addWidget(overlay_info)
        overlay_group.setLayout(overlay_layout)
        layout.addWidget(overlay_group)
        
        layout.addStretch()
        return widget
    
    def gather_settings(self):
        """Collect current settings from UI controls."""
        return {
            # Fusion parameters
            'temp_threshold': self.temp_threshold_spin.value(),
            'gas_ppm_threshold': self.gas_threshold_spin.value(),
            'flame_active_value': self.flame_value_spin.value(),
            'min_sources': self.min_sources_spin.value(),
            
            # Gas sensor calibration
            'gas_r0': self.gas_r0_spin.value(),
            'gas_rl': self.gas_rl_spin.value(),
            'gas_vcc': self.gas_vcc_spin.value(),
            
            # Display settings
            'hot_cell_decay_time': self.decay_time_spin.value(),
            'freeze_on_alarm': self.freeze_checkbox.isChecked(),
            'show_fusion_overlay': self.overlay_checkbox.isChecked(),
            
            # Vision detection
            'vision_threshold': self.vision_threshold_spin.value(),
            'vision_confidence_weight': self.vision_weight_spin.value()
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
