"""
Failed Devices Tab - UI for monitoring offline devices and manual reconnection
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QLabel, QHeaderView,
                             QCheckBox, QMessageBox, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from datetime import datetime
from device_status_manager import DeviceStatusManager, DeviceStatus


class FailedDevicesTab(QWidget):
    """Tab showing offline/failed devices with manual reconnect options"""
    
    reconnect_requested = pyqtSignal(str)  # Signal emitted with device IP
    
    def __init__(self, device_manager: DeviceStatusManager, parent=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.init_ui()
        
        # Refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_table)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header section
        header_layout = QHBoxLayout()
        
        title_label = QLabel("Failed Devices Monitor")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_table)
        header_layout.addWidget(refresh_btn)
        
        # Reconnect all button
        reconnect_all_btn = QPushButton("🔄 Reconnect All")
        reconnect_all_btn.clicked.connect(self.reconnect_all_devices)
        reconnect_all_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        header_layout.addWidget(reconnect_all_btn)
        
        layout.addLayout(header_layout)
        
        # Stats section
        stats_group = QGroupBox("Connection Statistics")
        stats_layout = QHBoxLayout()
        
        self.total_devices_label = QLabel("Total: 0")
        self.online_devices_label = QLabel("Online: 0")
        self.online_devices_label.setStyleSheet("color: green; font-weight: bold;")
        self.offline_devices_label = QLabel("Offline: 0")
        self.offline_devices_label.setStyleSheet("color: red; font-weight: bold;")
        
        stats_layout.addWidget(self.total_devices_label)
        stats_layout.addWidget(QLabel("|"))
        stats_layout.addWidget(self.online_devices_label)
        stats_layout.addWidget(QLabel("|"))
        stats_layout.addWidget(self.offline_devices_label)
        stats_layout.addStretch()
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Table for offline devices
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Device Name", "IP Address", "Location ID", "Type", 
            "Last Seen", "Failure Reason", "Attempts", "Actions"
        ])
        
        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Device Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # IP
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Location ID
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Last Seen
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Failure Reason
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Attempts
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Actions
        
        layout.addWidget(self.table)
        
        # Info label
        self.info_label = QLabel("ℹ️ Devices that are offline or unreachable will appear here. " +
                                "Use 'Reconnect' to manually retry connection.")
        self.info_label.setStyleSheet("color: gray; padding: 10px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        self.setLayout(layout)
        
        # Initial refresh
        self.refresh_table()
    
    def refresh_table(self):
        """Refresh the table with current device status"""
        try:
            all_devices = self.device_manager.get_all_devices()
            offline_devices = self.device_manager.get_offline_devices()
            online_devices = self.device_manager.get_online_devices()
            
            # Update stats
            self.total_devices_label.setText(f"Total: {len(all_devices)}")
            self.online_devices_label.setText(f"Online: {len(online_devices)}")
            self.offline_devices_label.setText(f"Offline: {len(offline_devices)}")
            
            # Clear and repopulate table with offline devices
            self.table.setRowCount(0)
            
            if not offline_devices:
                # Show a message if all devices are online
                self.table.setRowCount(1)
                item = QTableWidgetItem("✅ All devices are online!")
                item.setTextAlignment(Qt.AlignCenter)
                item.setForeground(QColor(0, 150, 0))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                self.table.setItem(0, 0, item)
                self.table.setSpan(0, 0, 1, 8)
                return
            
            for row, device in enumerate(offline_devices):
                self.table.insertRow(row)
                
                # Device Name
                name_item = QTableWidgetItem(device.device_name)
                name_item.setForeground(QColor(200, 0, 0))
                self.table.setItem(row, 0, name_item)
                
                # IP Address
                ip_item = QTableWidgetItem(device.ip)
                self.table.setItem(row, 1, ip_item)
                
                # Location ID
                loc_item = QTableWidgetItem(device.loc_id)
                self.table.setItem(row, 2, loc_item)
                
                # Type
                type_item = QTableWidgetItem(device.device_type)
                self.table.setItem(row, 3, type_item)
                
                # Last Seen
                if device.last_seen:
                    elapsed = datetime.now() - device.last_seen
                    if elapsed.seconds < 60:
                        last_seen_text = f"{elapsed.seconds}s ago"
                    elif elapsed.seconds < 3600:
                        last_seen_text = f"{elapsed.seconds // 60}m ago"
                    else:
                        last_seen_text = device.last_seen.strftime("%H:%M:%S")
                else:
                    last_seen_text = "Never"
                
                last_seen_item = QTableWidgetItem(last_seen_text)
                self.table.setItem(row, 4, last_seen_item)
                
                # Failure Reason
                reason_item = QTableWidgetItem(device.failure_reason or "Unknown")
                reason_item.setForeground(QColor(150, 0, 0))
                self.table.setItem(row, 5, reason_item)
                
                # Connection Attempts
                attempts_item = QTableWidgetItem(f"{device.connection_attempts}/5")
                if device.connection_attempts >= 5:
                    attempts_item.setForeground(QColor(200, 0, 0))
                    attempts_item.setFont(self._bold_font())
                self.table.setItem(row, 6, attempts_item)
                
                # Actions - Reconnect button
                actions_widget = QWidget()
                actions_layout = QHBoxLayout()
                actions_layout.setContentsMargins(2, 2, 2, 2)
                
                reconnect_btn = QPushButton("🔄 Reconnect")
                reconnect_btn.setStyleSheet("background-color: #2196F3; color: white;")
                reconnect_btn.clicked.connect(lambda checked, ip=device.ip: self.reconnect_device(ip))
                actions_layout.addWidget(reconnect_btn)
                
                # Auto-reconnect checkbox
                auto_checkbox = QCheckBox("Auto")
                auto_checkbox.setChecked(device.auto_reconnect_enabled)
                auto_checkbox.stateChanged.connect(
                    lambda state, ip=device.ip: self.toggle_auto_reconnect(ip, state == Qt.Checked)
                )
                actions_layout.addWidget(auto_checkbox)
                
                actions_widget.setLayout(actions_layout)
                self.table.setCellWidget(row, 7, actions_widget)
        
        except Exception as e:
            print(f"Failed to refresh table: {e}")
            import traceback
            traceback.print_exc()
    
    def reconnect_device(self, ip: str):
        """Manually reconnect a specific device"""
        try:
            print(f"Manual reconnect requested for {ip}")
            success = self.device_manager.manual_reconnect(ip)
            
            if success:
                QMessageBox.information(
                    self, 
                    "Reconnect Initiated",
                    f"Reconnection attempt initiated for device at {ip}.\n\n" +
                    "Check the device status in a few seconds."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Reconnect Failed",
                    f"Failed to initiate reconnection for {ip}.\n\n" +
                    "Please check the device and network connection."
                )
            
            # Refresh after a short delay
            QTimer.singleShot(1000, self.refresh_table)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Reconnect error: {str(e)}")
            print(f"Reconnect error: {e}")
    
    def reconnect_all_devices(self):
        """Reconnect all offline devices"""
        offline_devices = self.device_manager.get_offline_devices()
        
        if not offline_devices:
            QMessageBox.information(
                self,
                "No Offline Devices",
                "All devices are currently online!"
            )
            return
        
        reply = QMessageBox.question(
            self,
            "Reconnect All",
            f"Attempt to reconnect all {len(offline_devices)} offline devices?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success_count = 0
            for device in offline_devices:
                if self.device_manager.manual_reconnect(device.ip):
                    success_count += 1
            
            QMessageBox.information(
                self,
                "Reconnect Initiated",
                f"Reconnection initiated for {success_count}/{len(offline_devices)} devices.\n\n" +
                "Check device status in a few seconds."
            )
            
            # Refresh after delay
            QTimer.singleShot(2000, self.refresh_table)
    
    def toggle_auto_reconnect(self, ip: str, enabled: bool):
        """Toggle auto-reconnect for a device"""
        self.device_manager.set_auto_reconnect(ip, enabled)
        status_text = "enabled" if enabled else "disabled"
        print(f"Auto-reconnect {status_text} for {ip}")
    
    def _bold_font(self):
        """Helper to create bold font"""
        from PyQt5.QtGui import QFont
        font = QFont()
        font.setBold(True)
        return font
