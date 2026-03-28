
from PyQt6.QtWidgets import (
    QPushButton, QVBoxLayout, QHBoxLayout,  QDialog,
    QMessageBox, QStyle, QInputDialog, QListWidget, 
    QDialogButtonBox, QProgressDialog, QTreeWidget, QTreeWidgetItem, QLabel, QListWidgetItem
)
from PyQt6.QtCore import (
    Qt, QThread
)
from embereye_base.app.streamconfig_editdialog import StreamEditDialog
from embereye_base.app.steam_tester import StreamTester

class StreamConfigDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Stream Configuration")
        self.setMinimumSize(600, 400)
        self.setStyleSheet("""
            QDialog { background-color: #0f1722; color: #e7c75f; border: 1px solid #d7aa1a; }
            QLabel { color: #e7c75f; font-size: 12px; font-weight: 600; }
            QTreeWidget, QListWidget {
                background-color: #141d2a;
                color: #ffe7a0;
                border: 1px solid #75602a;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1b2533;
                color: #f3cc6c;
                border: 1px solid #5f4f26;
                padding: 4px 6px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #273448;
                color: #f0d17c;
                border: 1px solid #7a6633;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #344a67; border-color: #d7aa1a; color: #ffe9a6; }
            QDialogButtonBox QPushButton { min-width: 90px; }
        """)
        layout = QHBoxLayout()
        
        # Group Management
        group_layout = QVBoxLayout()
        self.group_tree = QTreeWidget()
        self.group_tree.setHeaderLabel("Groups & Streams")
        group_layout.addWidget(self.group_tree)
        
        # Group Buttons
        group_btn_layout = QHBoxLayout()
        self.add_group_btn = QPushButton("Add Group")
        self.add_group_btn.clicked.connect(self.add_group)
        
        self.remove_group_btn = QPushButton("Remove Group")
        self.remove_group_btn.clicked.connect(self.remove_group)
        
        group_btn_layout.addWidget(self.add_group_btn)
        group_btn_layout.addWidget(self.remove_group_btn)
        group_layout.addLayout(group_btn_layout)
        
        # Stream Management
        stream_layout = QVBoxLayout()
        self.stream_label = QLabel("Cameras in selected group:")
        self.stream_list = QListWidget()
        self.stream_list.itemDoubleClicked.connect(lambda *_: self.edit_stream())
        stream_layout.addWidget(self.stream_label)
        stream_layout.addWidget(self.stream_list)
        
        # Stream Buttons
        stream_btn_layout = QHBoxLayout()
        self.add_stream_btn = QPushButton("Add Stream")
        self.add_stream_btn.clicked.connect(self.add_stream)
        
        self.edit_stream_btn = QPushButton("Edit Stream")
        self.edit_stream_btn.clicked.connect(self.edit_stream)
        
        self.remove_stream_btn = QPushButton("Remove Stream")
        self.remove_stream_btn.clicked.connect(self.remove_stream)
        
        stream_btn_layout.addWidget(self.add_stream_btn)
        stream_btn_layout.addWidget(self.edit_stream_btn)
        stream_btn_layout.addWidget(self.remove_stream_btn)
        stream_layout.addLayout(stream_btn_layout)

        layout.addLayout(group_layout, 40)
        layout.addLayout(stream_layout, 60)
        
        # Dialog Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.setLayout(layout)
        
        # Populate groups after widgets are created to avoid attribute errors
        self.populate_groups()
        self.group_tree.currentItemChanged.connect(self.on_group_tree_selection_changed)

    def _stream_identity(self, stream):
        return (
            str(stream.get("group", "") or ""),
            str(stream.get("name", "") or ""),
            str(stream.get("loc_id", "") or "")
        )

    def _find_stream(self, group_name, stream_name=None, loc_id=None):
        for stream in self.config["streams"]:
            if str(stream.get("group", "") or "") != str(group_name or ""):
                continue
            if stream_name is not None and str(stream.get("name", "") or "") != str(stream_name or ""):
                continue
            if loc_id is not None and str(stream.get("loc_id", "") or "") != str(loc_id or ""):
                continue
            return stream
        return None

    def _selected_stream_identity(self):
        current = self.group_tree.currentItem()
        if current and current.parent() is not None:
            payload = current.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                return (
                    str(payload.get("group", "") or ""),
                    str(payload.get("name", "") or ""),
                    str(payload.get("loc_id", "") or "")
                )

        current_item = self.stream_list.currentItem()
        if current_item is not None:
            payload = current_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                return (
                    str(payload.get("group", "") or ""),
                    str(payload.get("name", "") or ""),
                    str(payload.get("loc_id", "") or "")
                )

        return None

    def populate_groups(self):
        self.group_tree.clear()
        first_group_item = None
        for group in self.config["groups"]:
            group_item = QTreeWidgetItem([group])
            if first_group_item is None:
                first_group_item = group_item
            for stream in self.config["streams"]:
                if stream["group"] == group:
                    child = QTreeWidgetItem(group_item, [stream["name"]])
                    child.setData(0, Qt.ItemDataRole.UserRole, {
                        "group": stream.get("group", ""),
                        "name": stream.get("name", ""),
                        "loc_id": stream.get("loc_id", ""),
                    })
            self.group_tree.addTopLevelItem(group_item)
        self.group_tree.expandAll()
        if self.group_tree.currentItem() is None and first_group_item is not None:
            self.group_tree.setCurrentItem(first_group_item)
        # Also refresh right panel for currently selected group
        self.refresh_stream_list()

    def on_group_tree_selection_changed(self, current, previous):
        self.refresh_stream_list()

    def _current_group_name(self):
        item = self.group_tree.currentItem()
        if item is None:
            return None
        return item.text(0) if item.parent() is None else item.parent().text(0)

    def refresh_stream_list(self):
        self.stream_list.clear()
        group_name = self._current_group_name()
        if not group_name:
            return
        for s in self.config["streams"]:
            if s["group"] == group_name:
                item = QListWidgetItem(f"{s['name']}  |  {s['loc_id']}")
                item.setData(Qt.ItemDataRole.UserRole, {
                    "group": s.get("group", ""),
                    "name": s.get("name", ""),
                    "loc_id": s.get("loc_id", ""),
                })
                self.stream_list.addItem(item)

    def add_group(self):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if ok and name and name not in self.config["groups"]:
            self.config["groups"].append(name)
            self.populate_groups()

    def remove_group(self):
        current = self.group_tree.currentItem()
        if current and current.parent() is None and current.text(0) != "Default":
            group_name = current.text(0)
            self.config["groups"].remove(group_name)
            for stream in self.config["streams"]:
                if stream["group"] == group_name:
                    stream["group"] = "Default"
            self.populate_groups()

    def add_stream(self):
        # Default group based on selection
        default_group = self._current_group_name() or (self.config["groups"][0] if self.config["groups"] else "Default")
        dialog = StreamEditDialog(self.config["groups"], self, default_group=default_group)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            stream_data = dialog.get_stream_data()
            self.config["streams"].append(stream_data)
            self.populate_groups()

    def edit_stream(self):
        identity = self._selected_stream_identity()
        if not identity:
            QMessageBox.information(self, "Edit Stream", "Select a group and a stream to edit.")
            return
        group_name, stream_name, loc_id = identity
        stream = self._find_stream(group_name, stream_name=stream_name, loc_id=loc_id)
        if stream:
            dialog = StreamEditDialog(self.config["groups"], self, existing=stream)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_stream_data()
                stream.update(new_data)
                self.populate_groups()

    def remove_stream(self):
        identity = self._selected_stream_identity()
        if not identity:
            QMessageBox.information(self, "Remove Stream", "Select a group and a stream to remove.")
            return
        group_name, stream_name, loc_id = identity
        stream = self._find_stream(group_name, stream_name=stream_name, loc_id=loc_id)
        if stream:
            self.config["streams"].remove(stream)
            self.populate_groups()
        else:
            QMessageBox.warning(self, "Error", "Stream not found")

    def test_stream(self, url):
        progress = QProgressDialog("Testing stream...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        
        tester = StreamTester(url)
        thread = QThread(self)
        tester.moveToThread(thread)
        result = [False]
        
        def handle_result(success, message):
            result[0] = success
            try:
                thread.quit()
            except Exception:
                pass
            try:
                progress.close()
            except RuntimeError:
                pass  # Dialog already deleted
            if not success and self.isVisible():
                try:
                    QMessageBox.warning(self, "Test Failed", message)
                except RuntimeError:
                    pass
        
        def on_canceled():
            try:
                thread.quit()
            except Exception:
                pass
        
        progress.canceled.connect(on_canceled)
        tester.test_complete.connect(handle_result)
        thread.started.connect(tester.test_stream)
        thread.start()
        progress.exec()
        return result[0]

    def get_config(self):
        return self.config
