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
            'temp_threshold': 40.0,  # Celsius (fire detection threshold)
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
            'vision_confidence_weight': 0.5,
            
            # Anomalies capture
            'anomaly_threshold': 0.4,
            'anomaly_max_items': 200,
            'anomaly_save_enabled': False,
            'anomaly_save_dir': '',
            'anomaly_retention_days': 7
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
        
        # Tab 4: Anomalies
        anomalies_tab = self.create_anomalies_tab()
        tabs.addTab(anomalies_tab, "Anomalies")
        
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
        self.temp_threshold_spin = QDoubleSpinBox()
        self.temp_threshold_spin.setRange(0.0, 200.0)
        self.temp_threshold_spin.setDecimals(1)
        self.temp_threshold_spin.setValue(float(self.settings['temp_threshold']))
        self.temp_threshold_spin.setSuffix(" °C")
        temp_row.addWidget(self.temp_threshold_spin)
        
        temp_info = QLabel("Temperature in Celsius. 40°C = fire detection, 30°C = warm objects")
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
        # Digital flame sensor display (removed configurable threshold; hardware-only)
        flame_group = QGroupBox("Flame Sensor (Digital - read-only)")
        flame_layout = QVBoxLayout()
        flame_info = QLabel("Digital flame input (MPY30) is hardware driven (0/1). Thresholds are based on analog percentage only.")
        flame_info.setWordWrap(True)
        flame_info.setStyleSheet("color: gray; font-size: 9pt;")
        flame_layout.addWidget(flame_info)
        flame_group.setLayout(flame_layout)
        layout.addWidget(flame_group)

        # Analog thresholds (ADC1/ADC2)
        adc_group = QGroupBox("Analog Sensor Thresholds")
        adc_layout = QVBoxLayout()

        # Smoke (ADC1) threshold in percentage
        smoke_row = QHBoxLayout()
        smoke_row.addWidget(QLabel("Smoke Threshold (ADC1):"))
        self.smoke_threshold_spin = QDoubleSpinBox()
        self.smoke_threshold_spin.setRange(0.0, 100.0)
        self.smoke_threshold_spin.setDecimals(1)
        self.smoke_threshold_spin.setSingleStep(1.0)
        self.smoke_threshold_spin.setValue(float(self.settings.get('smoke_threshold_pct', 25.0)))
        self.smoke_threshold_spin.setSuffix(" %")
        smoke_row.addWidget(self.smoke_threshold_spin)
        adc_layout.addLayout(smoke_row)

        # Flame analog (ADC2) threshold in percentage
        flamea_row = QHBoxLayout()
        flamea_row.addWidget(QLabel("Flame Threshold (ADC2 Analog):"))
        self.flame_threshold_spin = QDoubleSpinBox()
        self.flame_threshold_spin.setRange(0.0, 100.0)
        self.flame_threshold_spin.setDecimals(1)
        self.flame_threshold_spin.setSingleStep(1.0)
        self.flame_threshold_spin.setValue(float(self.settings.get('flame_threshold_pct', 25.0)))
        self.flame_threshold_spin.setSuffix(" %")
        flamea_row.addWidget(self.flame_threshold_spin)
        adc_layout.addLayout(flamea_row)

        adc_info = QLabel("12-bit ADC (0-4095) mapped to %: value × 100 / 4095. Configure thresholds used by fusion.")
        adc_info.setStyleSheet("color: gray; font-size: 9pt;")
        adc_layout.addWidget(adc_info)

        adc_group.setLayout(adc_layout)
        layout.addWidget(adc_group)
        
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

    def create_anomalies_tab(self):
        """Create anomalies capture configuration tab."""
        from PyQt5.QtWidgets import QLineEdit, QFileDialog
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Threshold for capturing anomalies
        thr_group = QGroupBox("Capture Threshold")
        thr_layout = QVBoxLayout()
        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Vision Score Threshold:"))
        self.anomaly_threshold_spin = QDoubleSpinBox()
        self.anomaly_threshold_spin.setRange(0.0, 1.0)
        self.anomaly_threshold_spin.setSingleStep(0.05)
        self.anomaly_threshold_spin.setValue(self.settings['anomaly_threshold'])
        thr_row.addWidget(self.anomaly_threshold_spin)
        thr_layout.addLayout(thr_row)
        thr_info = QLabel("Frames with score ≥ threshold are captured")
        thr_info.setStyleSheet("color: gray; font-size: 9pt;")
        thr_layout.addWidget(thr_info)
        thr_group.setLayout(thr_layout)
        layout.addWidget(thr_group)

        # In-memory gallery size
        mem_group = QGroupBox("Anomalies Gallery")
        mem_layout = QVBoxLayout()
        mem_row = QHBoxLayout()
        mem_row.addWidget(QLabel("Max Thumbnails (memory):"))
        self.anomaly_max_items_spin = QSpinBox()
        self.anomaly_max_items_spin.setRange(10, 5000)
        self.anomaly_max_items_spin.setValue(int(self.settings['anomaly_max_items']))
        mem_row.addWidget(self.anomaly_max_items_spin)
        mem_layout.addLayout(mem_row)
        mem_group.setLayout(mem_layout)
        layout.addWidget(mem_group)

        # Disk persistence
        disk_group = QGroupBox("Disk Persistence")
        disk_layout = QVBoxLayout()
        self.save_enabled_checkbox = QCheckBox("Save captured anomalies to disk")
        self.save_enabled_checkbox.setChecked(bool(self.settings['anomaly_save_enabled']))
        disk_layout.addWidget(self.save_enabled_checkbox)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Save Directory:"))
        self.anomaly_dir_edit = QLineEdit()
        self.anomaly_dir_edit.setText(self.settings['anomaly_save_dir'])
        browse_btn = QPushButton("…")
        def on_browse():
            path = QFileDialog.getExistingDirectory(self, "Select Anomalies Folder")
            if path:
                self.anomaly_dir_edit.setText(path)
        browse_btn.clicked.connect(on_browse)
        dir_row.addWidget(self.anomaly_dir_edit)
        dir_row.addWidget(browse_btn)
        disk_layout.addLayout(dir_row)

        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("Retention (days):"))
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 3650)
        self.retention_spin.setValue(int(self.settings['anomaly_retention_days']))
        keep_row.addWidget(self.retention_spin)
        disk_layout.addLayout(keep_row)
        disk_group.setLayout(disk_layout)
        layout.addWidget(disk_group)

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
            # Digital flame active value no longer configurable; kept internal (default=1)
            'smoke_threshold_pct': self.smoke_threshold_spin.value(),
            'flame_threshold_pct': self.flame_threshold_spin.value(),
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
            'vision_confidence_weight': self.vision_weight_spin.value(),
            
            # Anomalies capture
            'anomaly_threshold': self.anomaly_threshold_spin.value(),
            'anomaly_max_items': self.anomaly_max_items_spin.value(),
            'anomaly_save_enabled': self.save_enabled_checkbox.isChecked(),
            'anomaly_save_dir': self.anomaly_dir_edit.text().strip(),
            'anomaly_retention_days': self.retention_spin.value()
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
