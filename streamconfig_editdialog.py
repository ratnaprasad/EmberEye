from PyQt5.QtWidgets import (
    QLineEdit,  QVBoxLayout,  QComboBox, QDialog,
    QDialogButtonBox, QHBoxLayout, QPushButton, QProgressDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread
from steam_tester import StreamTester

try:
    from camera_discovery_dialog import CameraDiscoveryDialog
except Exception:
    CameraDiscoveryDialog = None

class StreamEditDialog(QDialog):
    def __init__(self, groups, parent=None, existing=None, default_group=None):
        super().__init__(parent)
        self.existing = existing
        self.groups = groups
        self.default_group = default_group
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Edit Stream" if self.existing else "Add Stream")
        layout = QVBoxLayout()

        self.loc_id = QLineEdit()
        self.loc_id.setPlaceholderText("Location Id")
        layout.addWidget(self.loc_id)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Stream Name")
        layout.addWidget(self.name_input)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("rtsp://...")
        layout.addWidget(self.url_input)
        
        self.group_combo = QComboBox()
        self.group_combo.addItems(self.groups)
        layout.addWidget(self.group_combo)
        
        # Actions row: Discover and Test
        actions_row = QHBoxLayout()
        self.discover_btn = QPushButton("Discover...")
        self.discover_btn.clicked.connect(self.discover_stream)
        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self.test_current_url)
        actions_row.addWidget(self.discover_btn)
        actions_row.addWidget(self.test_btn)
        layout.addLayout(actions_row)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        if self.existing:
            self.loc_id.setText(self.existing["loc_id"])
            self.name_input.setText(self.existing["name"])
            self.url_input.setText(self.existing["url"])
            self.group_combo.setCurrentText(self.existing["group"])
        elif self.default_group:
            idx = self.group_combo.findText(self.default_group)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        
        self.setLayout(layout)

    def get_stream_data(self):
        return {
            "loc_id": self.loc_id.text(),
            "name": self.name_input.text(),
            "url": self.url_input.text(),
            "group": self.group_combo.currentText()
        }

    def test_current_url(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.information(self, "Test Stream", "Please enter a stream URL first.")
            return
        progress = QProgressDialog("Testing stream...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        tester = StreamTester(url)
        thread = QThread()
        tester.moveToThread(thread)

        def handle_result(success, message):
            thread.quit()
            progress.close()
            if success:
                QMessageBox.information(self, "Test Successful", message)
            else:
                QMessageBox.warning(self, "Test Failed", message)

        tester.test_complete.connect(handle_result)
        thread.started.connect(tester.test_stream)
        thread.start()
        progress.exec_()

    def discover_stream(self):
        if CameraDiscoveryDialog is None:
            QMessageBox.information(self, "Discover", "Discovery dialog not available.")
            return
        dlg = CameraDiscoveryDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            selected_url = dlg.get_selected_url()
            if selected_url:
                self.url_input.setText(selected_url)
