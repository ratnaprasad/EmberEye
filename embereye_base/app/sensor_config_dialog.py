from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QDoubleSpinBox, QSpinBox, QPushButton, QGroupBox, QCheckBox, QTabWidget, QWidget, QMessageBox,
                             QRadioButton, QListWidget, QListWidgetItem, QStackedWidget, QComboBox, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal


class SensorConfigDialog(QDialog):
    """Dialog for configuring sensor fusion and detection parameters."""
    
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, parent=None, initial_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Sensor Configuration")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f1722;
                color: #e7c75f;
            }
            QGroupBox {
                color: #e7c75f;
                border: 1px solid #75602a;
                border-radius: 6px;
                margin-top: 8px;
                font-weight: 700;
                font-size: 11px;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #f0d17c;
            }
            QLabel {
                color: #e7c75f;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {
                background-color: #141d2a;
                color: #ffe7a0;
                border: 1px solid #75602a;
                border-radius: 4px;
                padding: 4px 6px;
                selection-background-color: rgba(226, 184, 58, 0.30);
            }
            QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
                border: 1px solid #e2b83a;
            }
            QCheckBox, QRadioButton {
                color: #e7c75f;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QPushButton {
                background-color: #273448;
                color: #f0d17c;
                border: 1px solid #7a6633;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 700;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
            }
            QPushButton:hover { background-color: #344a67; border-color: #d7aa1a; color: #ffe9a6; }
            QPushButton:pressed { background-color: #1e2a3a; }
            QTabWidget::pane { border: 1px solid #5f4f26; background-color: #0f1722; }
            QTabBar::tab {
                background-color: #1a2432; color: #c9a95a;
                border: 1px solid #5f4f26; padding: 6px 14px; margin-right: 2px;
            }
            QTabBar::tab:selected { background-color: #2b3a50; color: #ffe38a; border-color: #d7aa1a; }
            QListWidget {
                background-color: #141d2a; color: #ffe7a0;
                border: 1px solid #75602a; border-radius: 4px;
                selection-background-color: rgba(226,184,58,0.28);
            }
            QScrollBar:vertical { background: #141d2a; width: 8px; }
            QScrollBar::handle:vertical { background: #4a3c1a; border-radius: 4px; }
        """)

        # Default settings
        self.settings = {
            # Fusion parameters
            'temp_threshold': 40.0,  # Celsius (fire detection threshold)
            'critical_temp_threshold': 60.0,  # Celsius (critical alarm threshold)
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

            # Hybrid detection tuning
            'heuristic_threshold': 0.20,
            'force_yolo_every_n_frames': 10,
            'yolo_conf_threshold': 0.05,
            'possible_conf_threshold': 0.60,
            'confirmed_conf_threshold': 0.80,
            'rule_min_fusion_conf': 0.30,
            'rule_min_yolo_conf': 0.60,

            # Detection overlay filter
            'detection_box_mode': 'all',
            'detection_box_classes': [],
            'detection_available_classes': [],
            'detection_selected_preset': 'Custom',
            'detection_default_profile': {},
            
            # Anomalies capture
            'anomaly_threshold': 0.4,
            'anomaly_max_items': 200,
            'anomaly_save_enabled': False,
            'anomaly_save_dir': '',
            'anomaly_retention_days': 7,

            # Thermal rendering runtime controls
            'thermal_render_mode': 'fixed_scale_inferno',
            'thermal_emissivity': 0.95,
            'thermal_auto_window': True,
            'thermal_window_min': 20.0,
            'thermal_window_max': 120.0,
            'thermal_apply_scope': 'all',
            'thermal_target_pfds': '',
            'thermal_available_pfds': []
        }
        
        # Override with initial settings if provided
        if initial_settings:
            self.settings.update(initial_settings)

        self._applying_detection_preset = False
        self._detection_presets = {
            'High Recall': {
                'heuristic_threshold': 0.25,
                'force_yolo_every_n_frames': 8,
                'yolo_conf_threshold': 0.05,
            },
            'Balanced': {
                'heuristic_threshold': 0.33,
                'force_yolo_every_n_frames': 12,
                'yolo_conf_threshold': 0.08,
            },
            'Low Noise': {
                'heuristic_threshold': 0.40,
                'force_yolo_every_n_frames': 30,
                'yolo_conf_threshold': 0.12,
            }
        }
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        
        # Create tabs for different configuration sections
        tabs = QTabWidget()
        
        # Tab 1: Fusion Thresholds
        fusion_tab = self.create_fusion_tab()
        tabs.addTab(fusion_tab, "Fusion Thresholds")
        
        # Tab 2: Thermal Sensor
        thermal_sensor_tab = self.create_thermal_sensor_tab()
        tabs.addTab(thermal_sensor_tab, "Thermal Sensor")

        # Tab 3: Gas Sensor Calibration
        gas_tab = self.create_gas_sensor_tab()
        tabs.addTab(gas_tab, "Gas Sensor")
        
        # Tab 4: Detection settings
        display_tab = self.create_display_tab()
        tabs.addTab(display_tab, "Detection settings")
        
        # Tab 5: Anomalies
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

        critical_temp_row = QHBoxLayout()
        critical_temp_row.addWidget(QLabel("Critical Temp Threshold:"))
        self.critical_temp_threshold_spin = QDoubleSpinBox()
        self.critical_temp_threshold_spin.setRange(0.0, 250.0)
        self.critical_temp_threshold_spin.setDecimals(1)
        self.critical_temp_threshold_spin.setValue(float(self.settings.get('critical_temp_threshold', 60.0)))
        self.critical_temp_threshold_spin.setSuffix(" °C")
        critical_temp_row.addWidget(self.critical_temp_threshold_spin)
        
        temp_info = QLabel("Temperature in Celsius. 40°C = fire detection, 30°C = warm objects")
        temp_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        temp_layout.addLayout(temp_row)
        temp_layout.addLayout(critical_temp_row)
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
        gas_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        flame_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        flame_layout.addWidget(flame_info)
        flame_group.setLayout(flame_layout)
        layout.addWidget(flame_group)

        # Analog thresholds (ADC1/ADC2)
        adc_group = QGroupBox("Analog Sensor Thresholds")
        adc_layout = QVBoxLayout()

        # Smoke (ADC2) threshold in percentage
        smoke_row = QHBoxLayout()
        smoke_row.addWidget(QLabel("Smoke Threshold (ADC2):"))
        self.smoke_threshold_spin = QDoubleSpinBox()
        self.smoke_threshold_spin.setRange(0.0, 100.0)
        self.smoke_threshold_spin.setDecimals(1)
        self.smoke_threshold_spin.setSingleStep(1.0)
        self.smoke_threshold_spin.setValue(float(self.settings.get('smoke_threshold_pct', 25.0)))
        self.smoke_threshold_spin.setSuffix(" %")
        smoke_row.addWidget(self.smoke_threshold_spin)
        adc_layout.addLayout(smoke_row)

        # Flame analog (ADC1) threshold in percentage
        flamea_row = QHBoxLayout()
        flamea_row.addWidget(QLabel("Flame Threshold (ADC1 Analog):"))
        self.flame_threshold_spin = QDoubleSpinBox()
        self.flame_threshold_spin.setRange(0.0, 100.0)
        self.flame_threshold_spin.setDecimals(1)
        self.flame_threshold_spin.setSingleStep(1.0)
        self.flame_threshold_spin.setValue(float(self.settings.get('flame_threshold_pct', 25.0)))
        self.flame_threshold_spin.setSuffix(" %")
        flamea_row.addWidget(self.flame_threshold_spin)
        adc_layout.addLayout(flamea_row)

        adc_info = QLabel("12-bit ADC (0-4095) mapped to %: value × 100 / 4095. Configure thresholds used by fusion.")
        adc_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        vision_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        min_sources_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        min_sources_layout.addLayout(min_sources_row)
        min_sources_layout.addWidget(min_sources_info)
        min_sources_group.setLayout(min_sources_layout)
        layout.addWidget(min_sources_group)
        
        layout.addStretch()
        return widget

    def create_thermal_sensor_tab(self):
        """Create thermal sensor runtime controls tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        thermal_render_group = QGroupBox("Thermal Rendering")
        thermal_render_layout = QVBoxLayout()

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("TBA Thermal Sensor Mode:"))
        self.thermal_mode_combo = QComboBox()
        self.thermal_mode_combo.addItem("fixed-scale radiometric + inferno false-color", "fixed_scale_inferno")
        self.thermal_mode_combo.addItem("hot-mask + temporal delta", "hot_mask_temporal_delta")
        self.thermal_mode_combo.addItem("grayscale + valid-map + hotspot markers", "grayscale_valid_hotspots")
        mode_idx = self.thermal_mode_combo.findData(str(self.settings.get('thermal_render_mode', 'fixed_scale_inferno')))
        self.thermal_mode_combo.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
        mode_row.addWidget(self.thermal_mode_combo)
        thermal_render_layout.addLayout(mode_row)

        emissivity_row = QHBoxLayout()
        emissivity_row.addWidget(QLabel("Emissivity:"))
        self.thermal_emissivity_spin = QDoubleSpinBox()
        self.thermal_emissivity_spin.setRange(0.10, 1.00)
        self.thermal_emissivity_spin.setDecimals(2)
        self.thermal_emissivity_spin.setSingleStep(0.01)
        self.thermal_emissivity_spin.setValue(float(self.settings.get('thermal_emissivity', 0.95)))
        emissivity_row.addWidget(self.thermal_emissivity_spin)
        thermal_render_layout.addLayout(emissivity_row)

        window_group = QGroupBox("Thermal Contrast Window")
        window_layout = QVBoxLayout()

        self.thermal_auto_window_checkbox = QCheckBox("Auto window (recommended)")
        self.thermal_auto_window_checkbox.setChecked(bool(self.settings.get('thermal_auto_window', True)))
        window_layout.addWidget(self.thermal_auto_window_checkbox)

        min_row = QHBoxLayout()
        min_row.addWidget(QLabel("Manual Min (°C):"))
        self.thermal_window_min_spin = QDoubleSpinBox()
        self.thermal_window_min_spin.setRange(-40.0, 200.0)
        self.thermal_window_min_spin.setDecimals(1)
        self.thermal_window_min_spin.setSingleStep(0.5)
        self.thermal_window_min_spin.setValue(float(self.settings.get('thermal_window_min', 20.0)))
        min_row.addWidget(self.thermal_window_min_spin)
        window_layout.addLayout(min_row)

        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("Manual Max (°C):"))
        self.thermal_window_max_spin = QDoubleSpinBox()
        self.thermal_window_max_spin.setRange(-40.0, 250.0)
        self.thermal_window_max_spin.setDecimals(1)
        self.thermal_window_max_spin.setSingleStep(0.5)
        self.thermal_window_max_spin.setValue(float(self.settings.get('thermal_window_max', 120.0)))
        max_row.addWidget(self.thermal_window_max_spin)
        window_layout.addLayout(max_row)

        window_info = QLabel("Use manual window only when Auto window is OFF.")
        window_info.setWordWrap(True)
        window_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        window_layout.addWidget(window_info)

        window_group.setLayout(window_layout)
        thermal_render_layout.addWidget(window_group)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Apply Scope:"))
        self.thermal_scope_combo = QComboBox()
        self.thermal_scope_combo.addItem("All PFDS", "all")
        self.thermal_scope_combo.addItem("Per PFDS", "per_pfds")
        scope_idx = self.thermal_scope_combo.findData(str(self.settings.get('thermal_apply_scope', 'all')))
        if scope_idx < 0 and str(self.settings.get('thermal_apply_scope', '')) == 'per_camera':
            scope_idx = self.thermal_scope_combo.findData('per_pfds')
        self.thermal_scope_combo.setCurrentIndex(scope_idx if scope_idx >= 0 else 0)
        scope_row.addWidget(self.thermal_scope_combo)
        thermal_render_layout.addLayout(scope_row)

        pfds_row = QHBoxLayout()
        pfds_row.addWidget(QLabel("PFDS Device:"))
        self.thermal_pfds_combo = QComboBox()
        available_pfds = self.settings.get('thermal_available_pfds', self.settings.get('thermal_available_rooms', []))
        if not isinstance(available_pfds, list):
            available_pfds = []
        pfds_items = [str(device).strip() for device in available_pfds if str(device).strip()]
        if pfds_items:
            self.thermal_pfds_combo.addItems(pfds_items)
            pfds_value = str(self.settings.get('thermal_target_pfds', self.settings.get('thermal_target_room', ''))).strip()
            pfds_idx = self.thermal_pfds_combo.findText(pfds_value)
            if pfds_idx >= 0:
                self.thermal_pfds_combo.setCurrentIndex(pfds_idx)
        else:
            self.thermal_pfds_combo.addItem("(no PFDS devices available)")
            self.thermal_pfds_combo.setEnabled(False)
        pfds_row.addWidget(self.thermal_pfds_combo)
        thermal_render_layout.addLayout(pfds_row)

        self.thermal_scope_combo.currentIndexChanged.connect(self._toggle_thermal_pfds_selector)
        self.thermal_auto_window_checkbox.toggled.connect(self._toggle_thermal_window_controls)
        self._toggle_thermal_pfds_selector()
        self._toggle_thermal_window_controls()

        thermal_render_info = QLabel("These controls update thermal rendering immediately on Apply (no restart).")
        thermal_render_info.setWordWrap(True)
        thermal_render_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        thermal_render_layout.addWidget(thermal_render_info)

        thermal_render_group.setLayout(thermal_render_layout)
        layout.addWidget(thermal_render_group)

        layout.addStretch()
        return widget

    def create_anomalies_tab(self):
        """Create anomalies capture configuration tab."""
        from PyQt6.QtWidgets import QLineEdit, QFileDialog
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
        thr_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        r0_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        rl_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        vcc_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
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
        guide_text.setStyleSheet("color: #ffe7a0; padding: 10px; background-color: #141d2a; border: 1px solid #5f4f26; border-radius: 5px;")
        guide_layout.addWidget(guide_text)
        guide_group.setLayout(guide_layout)
        layout.addWidget(guide_group)
        
        layout.addStretch()
        return widget
    
    def create_display_tab(self):
        """Create detection settings tab (renamed from Display)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Stepper header
        stepper_header = QHBoxLayout()
        self.detection_step_label = QLabel()
        stepper_header.addWidget(self.detection_step_label)
        stepper_header.addStretch()

        self.detection_prev_btn = QPushButton("Previous")
        self.detection_prev_btn.clicked.connect(lambda: self._change_detection_step(-1))
        stepper_header.addWidget(self.detection_prev_btn)

        self.detection_next_btn = QPushButton("Next")
        self.detection_next_btn.clicked.connect(lambda: self._change_detection_step(1))
        stepper_header.addWidget(self.detection_next_btn)
        layout.addLayout(stepper_header)

        self.detection_step_stack = QStackedWidget()
        layout.addWidget(self.detection_step_stack)

        step_names = [
            "1/4 • Hybrid Tuning",
            "2/4 • Box Display",
            "3/4 • Visual Behavior",
            "4/4 • Application"
        ]
        self._detection_step_names = step_names

        # Step 1: Hybrid tuning
        step1 = QWidget()
        step1_layout = QVBoxLayout(step1)

        # Presets
        preset_group = QGroupBox("Tuning Presets")
        preset_layout = QVBoxLayout()

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self.detection_preset_combo = QComboBox()
        self.detection_preset_combo.addItems(["Custom", "High Recall", "Balanced", "Low Noise"])
        self.detection_preset_combo.setToolTip(
            "High Recall: more sensitive, may increase false alarms.\n"
            "Balanced: moderate sensitivity and noise.\n"
            "Low Noise: fewer false alarms, may miss brief events.\n"
            "Custom: user-defined values."
        )
        preset_row.addWidget(self.detection_preset_combo)
        preset_row.addStretch()
        preset_layout.addLayout(preset_row)

        preset_btn_row = QHBoxLayout()
        self.save_default_profile_btn = QPushButton("Save as Default Profile")
        self.load_default_profile_btn = QPushButton("Load Default Profile")
        self.save_default_profile_btn.clicked.connect(self._save_default_detection_profile)
        self.load_default_profile_btn.clicked.connect(self._load_default_detection_profile)
        preset_btn_row.addWidget(self.save_default_profile_btn)
        preset_btn_row.addWidget(self.load_default_profile_btn)
        preset_btn_row.addStretch()
        preset_layout.addLayout(preset_btn_row)

        preset_info = QLabel("Choose a preset for quick tuning, or use Custom to keep manual values.")
        preset_info.setWordWrap(True)
        preset_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        preset_layout.addWidget(preset_info)

        preset_hint = QLabel("High Recall = more detections (more noise). Low Noise = fewer false alarms (higher miss risk).")
        preset_hint.setWordWrap(True)
        preset_hint.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        preset_layout.addWidget(preset_hint)

        preset_group.setLayout(preset_layout)
        step1_layout.addWidget(preset_group)

        # Heuristic gate settings
        heuristic_group = QGroupBox("Heuristic Gate Settings")
        heuristic_layout = QVBoxLayout()

        heuristic_row = QHBoxLayout()
        heuristic_row.addWidget(QLabel("Heuristic Threshold:"))
        self.heuristic_threshold_spin = QDoubleSpinBox()
        self.heuristic_threshold_spin.setRange(0.0, 1.0)
        self.heuristic_threshold_spin.setSingleStep(0.01)
        self.heuristic_threshold_spin.setDecimals(3)
        self.heuristic_threshold_spin.setValue(float(self.settings.get('heuristic_threshold', 0.20)))
        heuristic_row.addWidget(self.heuristic_threshold_spin)
        heuristic_row.addStretch()
        heuristic_layout.addLayout(heuristic_row)

        sample_row = QHBoxLayout()
        sample_row.addWidget(QLabel("Force YOLO Every N Frames:"))
        self.force_yolo_every_n_spin = QSpinBox()
        self.force_yolo_every_n_spin.setRange(1, 300)
        self.force_yolo_every_n_spin.setValue(int(self.settings.get('force_yolo_every_n_frames', 10)))
        sample_row.addWidget(self.force_yolo_every_n_spin)
        sample_row.addStretch()
        heuristic_layout.addLayout(sample_row)

        yolo_gate_row = QHBoxLayout()
        yolo_gate_row.addWidget(QLabel("YOLO Inference Min Confidence:"))
        self.yolo_conf_threshold_spin = QDoubleSpinBox()
        self.yolo_conf_threshold_spin.setRange(0.001, 0.9)
        self.yolo_conf_threshold_spin.setSingleStep(0.01)
        self.yolo_conf_threshold_spin.setDecimals(3)
        self.yolo_conf_threshold_spin.setValue(float(self.settings.get('yolo_conf_threshold', 0.05)))
        yolo_gate_row.addWidget(self.yolo_conf_threshold_spin)
        yolo_gate_row.addStretch()
        heuristic_layout.addLayout(yolo_gate_row)

        heuristic_info = QLabel("Frames with heuristic score above threshold are queued to YOLO. YOLO min confidence filters weak detections.")
        heuristic_info.setWordWrap(True)
        heuristic_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        heuristic_layout.addWidget(heuristic_info)
        heuristic_group.setLayout(heuristic_layout)
        step1_layout.addWidget(heuristic_group)

        # Hybrid confidence bands
        bands_group = QGroupBox("Hybrid Confidence Bands")
        bands_layout = QVBoxLayout()

        possible_row = QHBoxLayout()
        possible_row.addWidget(QLabel("POSSIBLE Threshold:"))
        self.possible_conf_spin = QDoubleSpinBox()
        self.possible_conf_spin.setRange(0.0, 1.0)
        self.possible_conf_spin.setSingleStep(0.01)
        self.possible_conf_spin.setDecimals(3)
        self.possible_conf_spin.setValue(float(self.settings.get('possible_conf_threshold', 0.60)))
        possible_row.addWidget(self.possible_conf_spin)
        possible_row.addStretch()
        bands_layout.addLayout(possible_row)

        confirmed_row = QHBoxLayout()
        confirmed_row.addWidget(QLabel("CONFIRMED Threshold:"))
        self.confirmed_conf_spin = QDoubleSpinBox()
        self.confirmed_conf_spin.setRange(0.0, 1.0)
        self.confirmed_conf_spin.setSingleStep(0.01)
        self.confirmed_conf_spin.setDecimals(3)
        self.confirmed_conf_spin.setValue(float(self.settings.get('confirmed_conf_threshold', 0.80)))
        confirmed_row.addWidget(self.confirmed_conf_spin)
        confirmed_row.addStretch()
        bands_layout.addLayout(confirmed_row)

        bands_info = QLabel("LOW < POSSIBLE, POSSIBLE ≤ score < CONFIRMED, CONFIRMED ≥ threshold")
        bands_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        bands_layout.addWidget(bands_info)
        bands_group.setLayout(bands_layout)
        step1_layout.addWidget(bands_group)

        # Rule alarm gates
        rule_group = QGroupBox("Rule Alarms")
        rule_layout = QVBoxLayout()

        rule_yolo_row = QHBoxLayout()
        rule_yolo_row.addWidget(QLabel("Min YOLO Confidence (HIGH severity):"))
        self.rule_min_yolo_spin = QDoubleSpinBox()
        self.rule_min_yolo_spin.setRange(0.0, 1.0)
        self.rule_min_yolo_spin.setSingleStep(0.01)
        self.rule_min_yolo_spin.setDecimals(3)
        self.rule_min_yolo_spin.setValue(float(self.settings.get('rule_min_yolo_conf', 0.60)))
        rule_yolo_row.addWidget(self.rule_min_yolo_spin)
        rule_yolo_row.addStretch()
        rule_layout.addLayout(rule_yolo_row)

        rule_fusion_row = QHBoxLayout()
        rule_fusion_row.addWidget(QLabel("Min Fusion Confidence (HIGH severity):"))
        self.rule_min_fusion_spin = QDoubleSpinBox()
        self.rule_min_fusion_spin.setRange(0.0, 1.0)
        self.rule_min_fusion_spin.setSingleStep(0.01)
        self.rule_min_fusion_spin.setDecimals(3)
        self.rule_min_fusion_spin.setValue(float(self.settings.get('rule_min_fusion_conf', 0.30)))
        rule_fusion_row.addWidget(self.rule_min_fusion_spin)
        rule_fusion_row.addStretch()
        rule_layout.addLayout(rule_fusion_row)

        rule_info = QLabel("Used by rule-based alarms for HIGH severity escalation.")
        rule_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        rule_layout.addWidget(rule_info)
        rule_group.setLayout(rule_layout)
        step1_layout.addWidget(rule_group)

        self.detection_preset_combo.currentTextChanged.connect(self._on_detection_preset_changed)
        self.heuristic_threshold_spin.valueChanged.connect(self._mark_detection_preset_custom)
        self.force_yolo_every_n_spin.valueChanged.connect(self._mark_detection_preset_custom)
        self.yolo_conf_threshold_spin.valueChanged.connect(self._mark_detection_preset_custom)
        self._sync_detection_preset_from_values()

        step1_layout.addStretch()
        self.detection_step_stack.addWidget(step1)

        # Step 2: Detection box filter
        step2 = QWidget()
        step2_layout = QVBoxLayout(step2)

        # Detection box filter
        box_group = QGroupBox("Detection Box Display")
        box_layout = QVBoxLayout()

        self.box_mode_all_radio = QRadioButton("Show rectangles for all classes")
        self.box_mode_specific_radio = QRadioButton("Show rectangles for selected classes")

        box_mode = str(self.settings.get('detection_box_mode', 'all')).strip().lower()
        if box_mode == 'specific':
            self.box_mode_specific_radio.setChecked(True)
        else:
            self.box_mode_all_radio.setChecked(True)

        box_layout.addWidget(self.box_mode_all_radio)
        box_layout.addWidget(self.box_mode_specific_radio)

        self.box_class_list = QListWidget()
        self.box_class_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        available_classes = self.settings.get('detection_available_classes', []) or []
        selected_classes = set(self.settings.get('detection_box_classes', []) or [])
        for class_name in available_classes:
            item = QListWidgetItem(str(class_name))
            self.box_class_list.addItem(item)
            if str(class_name) in selected_classes:
                item.setSelected(True)
        box_layout.addWidget(self.box_class_list)

        self.box_mode_all_radio.toggled.connect(self._toggle_box_class_selector)
        self.box_mode_specific_radio.toggled.connect(self._toggle_box_class_selector)
        self._toggle_box_class_selector()

        box_info = QLabel("Choose whether bounding boxes appear for all detections or only selected classes.")
        box_info.setWordWrap(True)
        box_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        box_layout.addWidget(box_info)

        box_group.setLayout(box_layout)
        step2_layout.addWidget(box_group)
        step2_layout.addStretch()
        self.detection_step_stack.addWidget(step2)

        # Step 3: Visual behavior
        step3 = QWidget()
        step3_layout = QVBoxLayout(step3)
        
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
        decay_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        persistence_layout.addWidget(decay_info)
        persistence_group.setLayout(persistence_layout)
        step3_layout.addWidget(persistence_group)
        
        # Frame freeze
        freeze_group = QGroupBox("Alarm Behavior")
        freeze_layout = QVBoxLayout()
        
        self.freeze_checkbox = QCheckBox("Freeze frame on alarm")
        self.freeze_checkbox.setChecked(self.settings['freeze_on_alarm'])
        freeze_layout.addWidget(self.freeze_checkbox)
        
        freeze_info = QLabel("Stop video updates when alarm is active to preserve evidence")
        freeze_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        freeze_layout.addWidget(freeze_info)
        freeze_group.setLayout(freeze_layout)
        step3_layout.addWidget(freeze_group)
        
        # Fusion overlay
        overlay_group = QGroupBox("Information Overlay")
        overlay_layout = QVBoxLayout()
        
        self.overlay_checkbox = QCheckBox("Show fusion data overlay")
        self.overlay_checkbox.setChecked(self.settings['show_fusion_overlay'])
        overlay_layout.addWidget(self.overlay_checkbox)
        
        overlay_info = QLabel("Display sensor readings, accuracy, and active sensors on video")
        overlay_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        overlay_layout.addWidget(overlay_info)
        overlay_group.setLayout(overlay_layout)
        step3_layout.addWidget(overlay_group)
        step3_layout.addStretch()
        self.detection_step_stack.addWidget(step3)

        # Step 4: Application behavior
        step4 = QWidget()
        step4_layout = QVBoxLayout(step4)

        # Optional app restart
        restart_group = QGroupBox("Application")
        restart_layout = QVBoxLayout()
        self.restart_app_checkbox = QCheckBox("Restart application after applying these settings")
        self.restart_app_checkbox.setChecked(bool(self.settings.get('restart_app', False)))
        restart_layout.addWidget(self.restart_app_checkbox)
        restart_info = QLabel("Not required for most detection parameters; use if any runtime component appears stuck on old values.")
        restart_info.setWordWrap(True)
        restart_info.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        restart_layout.addWidget(restart_info)

        step4_hint = QLabel("Reminder: High Recall increases detections (and noise). Low Noise reduces false alarms (and can miss brief events).")
        step4_hint.setWordWrap(True)
        step4_hint.setStyleSheet("color: rgba(200,175,90,0.65); font-size: 9pt;")
        restart_layout.addWidget(step4_hint)
        restart_group.setLayout(restart_layout)
        step4_layout.addWidget(restart_group)
        step4_layout.addStretch()
        self.detection_step_stack.addWidget(step4)

        self._update_detection_stepper_ui()
        return widget
    
    def gather_settings(self):
        """Collect current settings from UI controls."""
        selected_box_classes = [item.text() for item in self.box_class_list.selectedItems()] if hasattr(self, 'box_class_list') else []
        if hasattr(self, 'detection_preset_combo'):
            self.settings['detection_selected_preset'] = self.detection_preset_combo.currentText()
        return {
            # Fusion parameters
            'temp_threshold': self.temp_threshold_spin.value(),
            'critical_temp_threshold': self.critical_temp_threshold_spin.value(),
            'gas_ppm_threshold': self.gas_threshold_spin.value(),
            # Digital flame active value no longer configurable; keep and forward current value
            'flame_active_value': int(self.settings.get('flame_active_value', 1)),
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

            # Hybrid detection
            'heuristic_threshold': self.heuristic_threshold_spin.value(),
            'force_yolo_every_n_frames': self.force_yolo_every_n_spin.value(),
            'yolo_conf_threshold': self.yolo_conf_threshold_spin.value(),
            'possible_conf_threshold': self.possible_conf_spin.value(),
            'confirmed_conf_threshold': self.confirmed_conf_spin.value(),
            'rule_min_fusion_conf': self.rule_min_fusion_spin.value(),
            'rule_min_yolo_conf': self.rule_min_yolo_spin.value(),
            'detection_selected_preset': self.settings.get('detection_selected_preset', 'Custom'),
            'detection_default_profile': self.settings.get('detection_default_profile', {}),

            # Detection box display filter
            'detection_box_mode': 'specific' if self.box_mode_specific_radio.isChecked() else 'all',
            'detection_box_classes': selected_box_classes,
            
            # Anomalies capture
            'anomaly_threshold': self.anomaly_threshold_spin.value(),
            'anomaly_max_items': self.anomaly_max_items_spin.value(),
            'anomaly_save_enabled': self.save_enabled_checkbox.isChecked(),
            'anomaly_save_dir': self.anomaly_dir_edit.text().strip(),
            'anomaly_retention_days': self.retention_spin.value(),
            'thermal_render_mode': self.thermal_mode_combo.currentData(),
            'thermal_emissivity': self.thermal_emissivity_spin.value(),
            'thermal_auto_window': self.thermal_auto_window_checkbox.isChecked(),
            'thermal_window_min': self.thermal_window_min_spin.value(),
            'thermal_window_max': self.thermal_window_max_spin.value(),
            'thermal_apply_scope': self.thermal_scope_combo.currentData(),
            'thermal_target_pfds': '' if not self.thermal_pfds_combo.isEnabled() else self.thermal_pfds_combo.currentText().strip(),
            'thermal_available_pfds': [self.thermal_pfds_combo.itemText(i) for i in range(self.thermal_pfds_combo.count()) if self.thermal_pfds_combo.itemText(i) != "(no PFDS devices available)"],
            'thermal_target_room': '' if not self.thermal_pfds_combo.isEnabled() else self.thermal_pfds_combo.currentText().strip(),
            'thermal_available_rooms': [self.thermal_pfds_combo.itemText(i) for i in range(self.thermal_pfds_combo.count()) if self.thermal_pfds_combo.itemText(i) != "(no PFDS devices available)"],
            'restart_app': self.restart_app_checkbox.isChecked()
        }

    def _toggle_thermal_pfds_selector(self):
        if not hasattr(self, 'thermal_scope_combo') or not hasattr(self, 'thermal_pfds_combo'):
            return
        per_pfds = self.thermal_scope_combo.currentData() in ('per_pfds', 'per_camera')
        has_pfds = self.thermal_pfds_combo.count() > 0 and self.thermal_pfds_combo.itemText(0) != "(no PFDS devices available)"
        self.thermal_pfds_combo.setEnabled(per_pfds and has_pfds)

    def _toggle_thermal_window_controls(self):
        if not hasattr(self, 'thermal_auto_window_checkbox'):
            return
        manual_enabled = not self.thermal_auto_window_checkbox.isChecked()
        if hasattr(self, 'thermal_window_min_spin'):
            self.thermal_window_min_spin.setEnabled(manual_enabled)
        if hasattr(self, 'thermal_window_max_spin'):
            self.thermal_window_max_spin.setEnabled(manual_enabled)

    def _toggle_box_class_selector(self):
        if hasattr(self, 'box_class_list'):
            self.box_class_list.setEnabled(self.box_mode_specific_radio.isChecked())

    def _on_detection_preset_changed(self, preset_name):
        if self._applying_detection_preset:
            return
        self.settings['detection_selected_preset'] = str(preset_name)
        if preset_name == 'Custom':
            return
        self._apply_detection_preset(preset_name)

    def _apply_detection_preset(self, preset_name):
        preset = self._detection_presets.get(str(preset_name))
        if not preset:
            return
        self._applying_detection_preset = True
        try:
            self.heuristic_threshold_spin.setValue(float(preset['heuristic_threshold']))
            self.force_yolo_every_n_spin.setValue(int(preset['force_yolo_every_n_frames']))
            self.yolo_conf_threshold_spin.setValue(float(preset['yolo_conf_threshold']))
        finally:
            self._applying_detection_preset = False

    def _mark_detection_preset_custom(self, *_):
        if self._applying_detection_preset or not hasattr(self, 'detection_preset_combo'):
            return
        self._sync_detection_preset_from_values()

    def _sync_detection_preset_from_values(self):
        if not hasattr(self, 'detection_preset_combo'):
            return

        heuristic = float(self.heuristic_threshold_spin.value())
        force_n = int(self.force_yolo_every_n_spin.value())
        yolo_conf = float(self.yolo_conf_threshold_spin.value())

        matched_name = 'Custom'
        for preset_name, preset_values in self._detection_presets.items():
            heuristic_match = abs(heuristic - float(preset_values['heuristic_threshold'])) < 1e-6
            force_match = force_n == int(preset_values['force_yolo_every_n_frames'])
            yolo_match = abs(yolo_conf - float(preset_values['yolo_conf_threshold'])) < 1e-6
            if heuristic_match and force_match and yolo_match:
                matched_name = preset_name
                break

        self._applying_detection_preset = True
        try:
            index = self.detection_preset_combo.findText(matched_name)
            if index >= 0 and self.detection_preset_combo.currentIndex() != index:
                self.detection_preset_combo.setCurrentIndex(index)
            self.settings['detection_selected_preset'] = matched_name
        finally:
            self._applying_detection_preset = False

    def _get_current_detection_profile(self):
        return {
            'preset': self.detection_preset_combo.currentText() if hasattr(self, 'detection_preset_combo') else 'Custom',
            'heuristic_threshold': float(self.heuristic_threshold_spin.value()),
            'force_yolo_every_n_frames': int(self.force_yolo_every_n_spin.value()),
            'yolo_conf_threshold': float(self.yolo_conf_threshold_spin.value()),
            'possible_conf_threshold': float(self.possible_conf_spin.value()),
            'confirmed_conf_threshold': float(self.confirmed_conf_spin.value()),
            'rule_min_yolo_conf': float(self.rule_min_yolo_spin.value()),
            'rule_min_fusion_conf': float(self.rule_min_fusion_spin.value()),
        }

    def _save_default_detection_profile(self):
        profile = self._get_current_detection_profile()
        self.settings['detection_default_profile'] = profile
        QMessageBox.information(self, "Default Profile Saved", "Detection profile saved as default for this site. Click Apply/OK to persist.")

    def _load_default_detection_profile(self):
        profile = self.settings.get('detection_default_profile', {})
        if not isinstance(profile, dict) or not profile:
            QMessageBox.information(self, "No Default Profile", "No default detection profile is saved yet.")
            return

        self._applying_detection_preset = True
        try:
            preset_name = str(profile.get('preset', 'Custom'))
            index = self.detection_preset_combo.findText(preset_name)
            if index < 0:
                index = self.detection_preset_combo.findText('Custom')
            if index >= 0:
                self.detection_preset_combo.setCurrentIndex(index)

            self.heuristic_threshold_spin.setValue(float(profile.get('heuristic_threshold', self.heuristic_threshold_spin.value())))
            self.force_yolo_every_n_spin.setValue(int(profile.get('force_yolo_every_n_frames', self.force_yolo_every_n_spin.value())))
            self.yolo_conf_threshold_spin.setValue(float(profile.get('yolo_conf_threshold', self.yolo_conf_threshold_spin.value())))
            self.possible_conf_spin.setValue(float(profile.get('possible_conf_threshold', self.possible_conf_spin.value())))
            self.confirmed_conf_spin.setValue(float(profile.get('confirmed_conf_threshold', self.confirmed_conf_spin.value())))
            self.rule_min_yolo_spin.setValue(float(profile.get('rule_min_yolo_conf', self.rule_min_yolo_spin.value())))
            self.rule_min_fusion_spin.setValue(float(profile.get('rule_min_fusion_conf', self.rule_min_fusion_spin.value())))
            self.settings['detection_selected_preset'] = self.detection_preset_combo.currentText()
        finally:
            self._applying_detection_preset = False
        QMessageBox.information(self, "Default Profile Loaded", "Default detection profile loaded. Click Apply/OK to use it.")

    def _change_detection_step(self, direction):
        if not hasattr(self, 'detection_step_stack'):
            return
        current_index = self.detection_step_stack.currentIndex()
        next_index = max(0, min(self.detection_step_stack.count() - 1, current_index + int(direction)))
        if next_index != current_index:
            self.detection_step_stack.setCurrentIndex(next_index)
        self._update_detection_stepper_ui()

    def _update_detection_stepper_ui(self):
        if not hasattr(self, 'detection_step_stack'):
            return
        current_index = self.detection_step_stack.currentIndex()
        total_steps = self.detection_step_stack.count()

        step_name = ""
        if hasattr(self, '_detection_step_names') and current_index < len(self._detection_step_names):
            step_name = self._detection_step_names[current_index]
        self.detection_step_label.setText(f"Detection Settings Step: {step_name}")

        self.detection_prev_btn.setEnabled(current_index > 0)
        self.detection_next_btn.setEnabled(current_index < total_steps - 1)
    
    def apply_settings(self):
        """Apply settings without closing dialog."""
        self.settings = self.gather_settings()
        self.settings_changed.emit(self.settings)
        parent = self.parent()
        if parent is not None and bool(getattr(parent, '_last_sensor_apply_warning_shown', False)):
            parent._last_sensor_apply_warning_shown = False
            return
        scope = str(self.settings.get('thermal_apply_scope', 'all'))
        pfds_device = str(self.settings.get('thermal_target_pfds', self.settings.get('thermal_target_room', ''))).strip()
        target_text = f"PFDS Device: {pfds_device}" if scope in ('per_pfds', 'per_camera') and pfds_device else "All PFDS"
        QMessageBox.information(self, "Settings Applied", f"Configuration applied successfully to {target_text}.")
    
    def accept_settings(self):
        """Apply settings and close dialog."""
        self.apply_settings()
        self.accept()
    
    def get_settings(self):
        """Return current settings."""
        return self.settings
