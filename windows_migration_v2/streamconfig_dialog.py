
from PyQt5.QtWidgets import (
    QPushButton, QVBoxLayout, QHBoxLayout,  QDialog,
    QMessageBox, QStyle, QInputDialog, QListWidget, 
    QDialogButtonBox, QProgressDialog, QTreeWidget, QTreeWidgetItem, QLabel
)
from PyQt5.QtCore import (
    Qt, QThread
)
from streamconfig_editdialog import StreamEditDialog
from steam_tester import StreamTester

class StreamConfigDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Stream Configuration")
        self.setMinimumSize(600, 400)
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
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.setLayout(layout)
        
        # Populate groups after widgets are created to avoid attribute errors
        self.populate_groups()
        self.group_tree.currentItemChanged.connect(self.on_group_tree_selection_changed)

    def populate_groups(self):
        self.group_tree.clear()
        for group in self.config["groups"]:
            group_item = QTreeWidgetItem([group])
            for stream in self.config["streams"]:
                if stream["group"] == group:
                    QTreeWidgetItem(group_item, [stream["name"]])
            self.group_tree.addTopLevelItem(group_item)
        self.group_tree.expandAll()
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
                self.stream_list.addItem(f"{s['name']}  |  {s['loc_id']}")

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
        if dialog.exec_() == QDialog.Accepted:
            stream_data = dialog.get_stream_data()
            self.config["streams"].append(stream_data)
            self.populate_groups()

    def edit_stream(self):
        # Determine selection: prefer a stream child in the tree, else from the list
        current = self.group_tree.currentItem()
        group_name = None
        stream_name = None
        if current and current.parent():
            stream_name = current.text(0)
            group_name = current.parent().text(0)
        else:
            # Use selected in list
            group_name = self._current_group_name()
            if group_name and self.stream_list.currentItem():
                # Extract name from "name  |  loc_id" format
                stream_name = self.stream_list.currentItem().text().split("  |  ")[0]
        if not (group_name and stream_name):
            QMessageBox.information(self, "Edit Stream", "Select a group and a stream to edit.")
            return
        stream = next((s for s in self.config["streams"] 
                      if s["name"] == stream_name and s["group"] == group_name), None)
        if stream:
            dialog = StreamEditDialog(self.config["groups"], self, existing=stream)
            if dialog.exec_() == QDialog.Accepted:
                new_data = dialog.get_stream_data()
                stream.update(new_data)
                self.populate_groups()

    def remove_stream(self):
        # Determine selection from tree child or list
        current = self.group_tree.currentItem()
        group_name = None
        stream_name = None
        if current and current.parent():
            stream_name = current.text(0)
            group_name = current.parent().text(0)
        else:
            group_name = self._current_group_name()
            if group_name and self.stream_list.currentItem():
                stream_name = self.stream_list.currentItem().text().split("  |  ")[0]
        if not (group_name and stream_name):
            QMessageBox.information(self, "Remove Stream", "Select a group and a stream to remove.")
            return
        stream = next((s for s in self.config["streams"] 
                      if s["name"] == stream_name and s["group"] == group_name), None)
        if stream:
            self.config["streams"].remove(stream)
            self.populate_groups()
        else:
            QMessageBox.warning(self, "Error", "Stream not found")

    def test_stream(self, url):
        progress = QProgressDialog("Testing stream...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        
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
        progress.exec_()
        return result[0]

    def get_config(self):
        return self.config
