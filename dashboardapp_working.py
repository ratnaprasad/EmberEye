import sys
import os
import re
import json
import cv2
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow, QTabWidget, QGridLayout, 
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog,
    QStatusBar, QAction, QMenu, QToolButton, QComboBox, QDialog,
    QMessageBox, QStyle, QInputDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QProgressDialog, QTreeWidget, QTreeWidgetItem
)
from PyQt5.QtGui import QPixmap, QIcon, QImage
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QMutex, QMutexLocker, 
    QThread, QObject, QSize, QMetaObject
)

# ----------------------------
# Configuration Management
# ----------------------------
class StreamConfig:
    CONFIG_FILE = "stream_config.json"
    
    @staticmethod
    def load_config():
        default_config = {
            "groups": ["Default"],
            "streams": []
        }
        try:
            if os.path.exists(StreamConfig.CONFIG_FILE):
                with open(StreamConfig.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    return config if isinstance(config, dict) else default_config
            return default_config
        except Exception as e:
            print(f"Config load error: {str(e)}")
            return default_config

    @staticmethod
    def save_config(config):
        try:
            with open(StreamConfig.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Config save error: {str(e)}")
            return False
    
    @staticmethod
    def export_config(path):
        """Export configuration to specified path"""
        try:
            if not os.path.exists(StreamConfig.CONFIG_FILE):
                return False
            shutil.copyfile(StreamConfig.CONFIG_FILE, path)
            return True
        except Exception as e:
            print(f"Export error: {str(e)}")
            return False

    @staticmethod
    def import_config(path):
        """Import configuration from specified path"""
        try:
            # Validate file format
            with open(path, 'r') as f:
                config = json.load(f)
                if "groups" not in config or "streams" not in config:
                    return False
                
            # Create backup before overwriting
            backup_path = os.path.join(
                os.path.dirname(StreamConfig.CONFIG_FILE),
                f"config_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            )
            shutil.copyfile(StreamConfig.CONFIG_FILE, backup_path)
            
            # Replace with new config
            shutil.copyfile(path, StreamConfig.CONFIG_FILE)
            return True
        except Exception as e:
            print(f"Import error: {str(e)}")
            return False


# ----------------------------
# Video Streaming Components
# ----------------------------
class VideoWorker(QObject):
    frame_ready = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    connection_status = pyqtSignal(bool)

    def __init__(self, rtsp_url):
        super().__init__()
        self.rtsp_url = self._format_url(rtsp_url)
        self.mutex = QMutex()
        self.cap = None
        self.timer = QTimer()
        self.timer.moveToThread(QApplication.instance().thread())  # Move timer to main thread
        self.timer.setInterval(30)  # ~33 FPS

    def start_stream(self):
        try:
            with QMutexLocker(self.mutex):
                if self.cap and self.cap.isOpened():
                    return

                self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                if not self.cap.isOpened():
                    raise ConnectionError(f"Failed to open {self.rtsp_url}")

                # Start timer in main thread context
                QMetaObject.invokeMethod(
                    self.timer,
                    'start',
                    Qt.QueuedConnection
                )
                self.connection_status.emit(True)

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)

    def update_frame(self):
        try:
            with QMutexLocker(self.mutex):
                if not self.cap.isOpened():
                    return

                ret, frame = self.cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame.shape
                    bytes_per_line = ch * w
                    q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    self.frame_ready.emit(QPixmap.fromImage(q_img))
                else:
                    raise RuntimeError("No frame received")

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)
            self.stop_stream()

    def stop_stream(self):
        with QMutexLocker(self.mutex):
            if self.cap and self.cap.isOpened():
                self.cap.release()
            # Stop timer in main thread context
            QMetaObject.invokeMethod(
                self.timer,
                'stop',
                Qt.QueuedConnection
            )
            self.connection_status.emit(False)

    def _format_url(self, url):
        """Ensure proper RTSP URL formatting"""
        if not url.startswith("rtsp://"):
            url = "rtsp://" + url
        if "?tcp" not in url and "?udp" not in url:
            url += "?tcp"  # Force TCP transport
        return url
    
class VideoWidget(QLabel):
    def __init__(self, rtsp_url, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        
        # Initialize worker and thread
        self.worker = VideoWorker(rtsp_url)
        self.worker_thread = QThread()
        
        # Move worker to thread
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals
        self.worker.frame_ready.connect(self.update_frame)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.connection_status.connect(self.handle_connection_status)
        
        # Connect timer signal
        self.worker.timer.timeout.connect(self.worker.update_frame)
        
        # Start worker thread
        self.worker_thread.started.connect(self.worker.start_stream)
        self.worker_thread.start()
        
    def update_frame(self, pixmap):
        try:
            self.setPixmap(pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        except Exception as e:
            self.handle_error(str(e))

    def handle_error(self, message):
        self.setText(f"ERROR: {message}\n{self.worker.rtsp_url}")
        self.setStyleSheet("color: red; background-color: black; padding: 5px;")

    def handle_connection_status(self, connected):
        if connected:
            self.setText("")
            self.setStyleSheet("background-color: black;")
        else:
            self.setText("Reconnecting...\n" + self.worker.rtsp_url)
            self.setStyleSheet("color: yellow; background-color: black; padding: 5px;")

    def resizeEvent(self, event):
        if self.pixmap() and not self.pixmap().isNull():
            self.setPixmap(self.pixmap().scaled(
                event.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        super().resizeEvent(event)

    def stop(self):
        """Clean up worker and thread"""
        try:
            self.worker.stop_stream()
            self.worker_thread.quit()
            if not self.worker_thread.wait(2000):
                self.worker_thread.terminate()
        except Exception as e:
            print(f"Error stopping worker: {str(e)}")

    def resizeEvent(self, event):
        """Handle widget resizing"""
        try:
            current_pixmap = self.pixmap()
            if current_pixmap and not current_pixmap.isNull():
                self.setPixmap(current_pixmap.scaled(event.size(), 
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            self.handle_error(f"Resize error: {str(e)}")
        super().resizeEvent(event)

    def deleteLater(self):
        """Ensure proper cleanup"""
        self.stop()
        super().deleteLater()

# ----------------------------
# Stream Testing & Validation
# ----------------------------
class StreamTester(QObject):
    test_complete = pyqtSignal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cap = None

    def test_stream(self):
        try:
            # # URL validation
            # if not re.match(r'^rtsp?://[\w\-\.]+(:\d+)?(/[\w\-\.]*)*$', self.url):
            #     self.test_complete.emit(False, "Invalid RTSP URL format")
            #     return

            # Connection test with timeout
            self.cap = cv2.VideoCapture(self.url)
            if not self.cap.isOpened():
                self.test_complete.emit(False, "Failed to open stream")
                return

            # Frame read test
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.test_complete.emit(True, "Connection successful")
            else:
                self.test_complete.emit(False, "No frames received")

        except Exception as e:
            self.test_complete.emit(False, str(e))
        finally:
            if self.cap and self.cap.isOpened():
                self.cap.release()

# ----------------------------
# Configuration Dialog
# ----------------------------
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
        self.populate_groups()
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
        self.stream_list = QListWidget()
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

    def populate_groups(self):
        self.group_tree.clear()
        for group in self.config["groups"]:
            group_item = QTreeWidgetItem([group])
            for stream in self.config["streams"]:
                if stream["group"] == group:
                    QTreeWidgetItem(group_item, [stream["name"]])
            self.group_tree.addTopLevelItem(group_item)
        self.group_tree.expandAll()

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
        dialog = StreamEditDialog(self.config["groups"], self)
        if dialog.exec_() == QDialog.Accepted:
            stream_data = dialog.get_stream_data()
            if self.test_stream(stream_data["url"]):
                self.config["streams"].append(stream_data)
                self.populate_groups()

    def edit_stream(self):
        current = self.group_tree.currentItem()
        if current and current.parent():
            stream_name = current.text(0)
            group_name = current.parent().text(0)
            stream = next((s for s in self.config["streams"] 
                          if s["name"] == stream_name and s["group"] == group_name), None)
            if stream:
                dialog = StreamEditDialog(self.config["groups"], self, stream)
                if dialog.exec_() == QDialog.Accepted:
                    new_data = dialog.get_stream_data()
                    if self.test_stream(new_data["url"]):
                        stream.update(new_data)
                        self.populate_groups()

    def remove_stream(self):
        current = self.group_tree.currentItem()
        if current and current.parent():
            stream_name = current.text(0)
            group_name = current.parent().text(0)
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
        thread = QThread()
        tester.moveToThread(thread)
        result = [False]
        
        def handle_result(success, message):
            result[0] = success
            thread.quit()
            progress.close()
            if not success:
                QMessageBox.warning(self, "Test Failed", message)
        
        tester.test_complete.connect(handle_result)
        thread.started.connect(tester.test_stream)
        thread.start()
        progress.exec_()
        return result[0]

    def get_config(self):
        return self.config

class StreamEditDialog(QDialog):
    def __init__(self, groups, parent=None, existing=None):
        super().__init__(parent)
        self.existing = existing
        self.groups = groups
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Edit Stream" if self.existing else "Add Stream")
        layout = QVBoxLayout()
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Stream Name")
        layout.addWidget(self.name_input)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("rtsp://...")
        layout.addWidget(self.url_input)
        
        self.group_combo = QComboBox()
        self.group_combo.addItems(self.groups)
        layout.addWidget(self.group_combo)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        if self.existing:
            self.name_input.setText(self.existing["name"])
            self.url_input.setText(self.existing["url"])
            self.group_combo.setCurrentText(self.existing["group"])
        
        self.setLayout(layout)

    def get_stream_data(self):
        return {
            "name": self.name_input.text(),
            "url": self.url_input.text(),
            "group": self.group_combo.currentText()
        }

# ----------------------------
# Main Application
# ----------------------------
class LoginWindow(QWidget):
    success = pyqtSignal(QMainWindow)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Login")
        self.setGeometry(300, 300, 300, 150)
        layout = QVBoxLayout()
        
        self.username = QLineEdit(placeholderText="Username")
        self.password = QLineEdit(placeholderText="Password", echoMode=QLineEdit.Password)
        self.login_btn = QPushButton("Login", clicked=self.authenticate)
        
        layout.addWidget(self.username)
        layout.addWidget(self.password)
        layout.addWidget(self.login_btn)
        self.setLayout(layout)

    def authenticate(self):
        try:
            if self.username.text() == 'admin' and self.password.text() == 'password':
                self.dashboard = Dashboard()  # Store reference
                self.success.emit(self.dashboard)
                self.hide()  # Hide instead of close
            else:
                QMessageBox.warning(self, 'Error', 'Invalid credentials')
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = StreamConfig.load_config()
        self.current_group = "Default"
        self.current_rtsp_page = 1
        self.current_graph_page = 1
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.initUI()

    def initUI(self):
        try:
            self.setWindowTitle("Dashboard")
            self.setGeometry(100, 100, 1024, 768)
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            
            # Title Bar
            title_bar = QHBoxLayout()
            self.init_logo(title_bar)
            
            self.group_combo = QComboBox()
            self.group_combo.addItems(self.config["groups"])
            self.group_combo.currentTextChanged.connect(self.group_changed)
            title_bar.addWidget(self.group_combo)
            
            title = QLabel("Dashboard")
            title.setStyleSheet("font-size: 20px; font-weight: bold;")
            title_bar.addWidget(title)
            title_bar.addStretch()
            self.init_settings_menu(title_bar)
            main_layout.addLayout(title_bar)
            
            # Tab Widget
            self.tabs = QTabWidget()
            main_layout.addWidget(self.tabs)
            
            self.init_rtsp_tab()
            self.init_graph_tab()
            
            self.statusBar().showMessage("System Ready")
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Initialization failed: {str(e)}")

    def init_logo(self, title_bar):
        self.logo = QLabel()
        self.logo.setFixedSize(40, 40)
        try:
            pixmap = QPixmap("logo.png").scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo.setPixmap(pixmap)
        except:
            self.logo.setText("LOGO")
            self.logo.setStyleSheet("""
                background-color: #f0f0f0;
                border: 2px solid #d0d0d0;
                border-radius: 5px;
                font-weight: bold;
                color: #404040;
                qproperty-alignment: AlignCenter;
            """)
        title_bar.addWidget(self.logo)

    def init_settings_menu(self, title_bar):
        menu_btn = QToolButton()
        menu_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu()
        menu.addAction("Profile", self.show_profile)
        menu.addAction("Configure Streams", self.configure_streams)
        # Add backup/restore actions
        menu.addSeparator()
        menu.addAction("Backup Configuration", self.backup_config)
        menu.addAction("Restore Configuration", self.restore_config)
        menu.addSeparator()

        menu.addAction("Logout", self.logout)
        menu_btn.setMenu(menu)
        title_bar.addWidget(menu_btn)

    def backup_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backup",
            f"stream_config_backup_{datetime.now().strftime('%Y%m%d')}.json",
            "JSON Files (*.json)"
        )
        if path:
            if StreamConfig.export_config(path):
                QMessageBox.information(self, "Success", "Configuration backup created successfully!")
            else:
                QMessageBox.critical(self, "Error", "Failed to create backup")
    
    def restore_config(self):
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            "This will overwrite current configuration. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            "",
            "JSON Files (*.json)"
        )
        if path:
            if StreamConfig.import_config(path):
                # Reload configuration
                self.config = StreamConfig.load_config()
                self.group_combo.clear()
                self.group_combo.addItems(self.config["groups"])
                self.update_rtsp_grid()
                QMessageBox.information(self, "Success", "Configuration restored successfully!")
            else:
                QMessageBox.critical(self, "Error", "Invalid backup file or restore failed")

    
    def init_rtsp_tab(self):
        rtsp_tab = QWidget()
        layout = QVBoxLayout(rtsp_tab)
        
        size_layout = QHBoxLayout()
        self.grid_size = QComboBox()
        self.grid_size.addItems(["2x2", "3x3", "4x4"])
        self.grid_size.currentIndexChanged.connect(self.update_rtsp_grid)
        size_layout.addWidget(QLabel("Grid Size:"))
        size_layout.addWidget(self.grid_size)
        size_layout.addStretch()
        
        self.rtsp_grid = QGridLayout()
        grid_widget = QWidget()
        grid_widget.setLayout(self.rtsp_grid)
        
        page_layout = QHBoxLayout()
        self.prev_rtsp = QPushButton("Previous", clicked=self.prev_rtsp_page)
        self.next_rtsp = QPushButton("Next", clicked=self.next_rtsp_page)
        self.page_label = QLabel()
        page_layout.addWidget(self.prev_rtsp)
        page_layout.addWidget(self.page_label)
        page_layout.addWidget(self.next_rtsp)
        
        layout.addLayout(size_layout)
        layout.addWidget(grid_widget)
        layout.addLayout(page_layout)
        self.tabs.addTab(rtsp_tab, "RTSP Feeds")
        self.update_rtsp_grid()

    def init_graph_tab(self):
        graph_tab = QWidget()
        layout = QVBoxLayout(graph_tab)
        self.graph_stack = QVBoxLayout()
        layout.addLayout(self.graph_stack)
        
        page_layout = QHBoxLayout()
        self.prev_graph = QPushButton("Previous", clicked=self.prev_graph_page)
        self.next_graph = QPushButton("Next", clicked=self.next_graph_page)
        self.graph_label = QLabel()
        page_layout.addWidget(self.prev_graph)
        page_layout.addWidget(self.graph_label)
        page_layout.addWidget(self.next_graph)
        layout.addLayout(page_layout)
        
        self.tabs.addTab(graph_tab, "Analytics")
        self.update_graph()

    def update_rtsp_grid(self):
        try:
            # Clear existing widgets safely
            while self.rtsp_grid.count():
                item = self.rtsp_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            filtered_streams = [
                s for s in self.config["streams"]
                if s["group"] == self.current_group
            ]
            
            if not filtered_streams:
                no_streams_label = QLabel(f"No streams in {self.current_group} group")
                no_streams_label.setAlignment(Qt.AlignCenter)
                self.rtsp_grid.addWidget(no_streams_label, 0, 0)
                self.page_label.setText("Page 0 of 0")
                return

            rows, cols = map(int, self.grid_size.currentText().split("x"))
            feeds_per_page = rows * cols
            total_streams = len(filtered_streams)
            total_pages = max(1, (total_streams + feeds_per_page - 1) // feeds_per_page)
            self.current_rtsp_page = max(1, min(self.current_rtsp_page, total_pages))
            start = (self.current_rtsp_page - 1) * feeds_per_page
            end = min(start + feeds_per_page, total_streams)

            for idx in range(start, end):
                stream = filtered_streams[idx]
                position = idx - start
                row = position // cols
                col = position % cols
                
                try:
                    video_widget = VideoWidget(stream["url"])
                    video_widget.setToolTip(f"{stream['name']}\n{stream['url']}")
                    name_label = QLabel(stream["name"], video_widget)
                    name_label.setStyleSheet("""
                        background-color: rgba(0, 0, 0, 150);
                        color: white;
                        padding: 2px;
                        border-radius: 3px;
                    """)
                    name_label.move(5, 5)
                    self.rtsp_grid.addWidget(video_widget, row, col)
                except Exception as e:
                    error_label = QLabel(f"{stream['name']}\nError: {str(e)}")
                    error_label.setAlignment(Qt.AlignCenter)
                    error_label.setStyleSheet("color: red; background-color: black;")
                    self.rtsp_grid.addWidget(error_label, row, col)

            self.page_label.setText(f"Page {self.current_rtsp_page} of {total_pages}")
            self.prev_rtsp.setEnabled(self.current_rtsp_page > 1)
            self.next_rtsp.setEnabled(end < total_streams)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Grid update failed: {str(e)}")
            self.current_rtsp_page = 1
            self.update_rtsp_grid()

    def update_graph(self):
        try:
            for i in reversed(range(self.graph_stack.count())): 
                self.graph_stack.itemAt(i).widget().deleteLater()
            
            figure = plt.figure()
            canvas = FigureCanvas(figure)
            ax = figure.add_subplot(111)
            
            if self.current_graph_page == 1:
                x = np.linspace(0, 10, 100)
                ax.plot(x, np.sin(x))
                ax.set_title("Sine Wave")
            else:
                categories = ["A", "B", "C"]
                values = np.random.randint(1, 10, 3)
                ax.bar(categories, values)
                ax.set_title("Random Data")
            
            canvas.draw()
            self.graph_stack.addWidget(canvas)
            self.graph_label.setText(f"Graph {self.current_graph_page}/2")
            self.prev_graph.setEnabled(self.current_graph_page > 1)
            self.next_graph.setEnabled(self.current_graph_page < 2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Graph update failed: {str(e)}")

    def group_changed(self, group):
        self.current_group = group
        self.current_rtsp_page = 1
        self.update_rtsp_grid()

    def configure_streams(self):
        dialog = StreamConfigDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            self.config = dialog.get_config()
            StreamConfig.save_config(self.config)
            self.group_combo.clear()
            self.group_combo.addItems(self.config["groups"])
            self.update_rtsp_grid()

    def show_profile(self):
        profile_dialog = QDialog(self)
        profile_dialog.setWindowTitle("User Profile")
        profile_dialog.setFixedSize(300, 200)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Username: admin"))
        layout.addWidget(QLabel("Email: admin@example.com"))
        close_btn = QPushButton("Close", clicked=profile_dialog.close)
        layout.addWidget(close_btn)
        profile_dialog.setLayout(layout)
        profile_dialog.exec_()

    def prev_rtsp_page(self):
        self.current_rtsp_page = max(1, self.current_rtsp_page - 1)
        self.update_rtsp_grid()

    def next_rtsp_page(self):
        self.current_rtsp_page += 1
        self.update_rtsp_grid()

    def prev_graph_page(self):
        self.current_graph_page = max(1, self.current_graph_page - 1)
        self.update_graph()

    def next_graph_page(self):
        self.current_graph_page = min(2, self.current_graph_page + 1)
        self.update_graph()

    def logout(self):
        self.close()
        login_window = LoginWindow()
        login_window.show()

if __name__ == "__main__":
    # Set High DPI attributes first
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Exception handling
    sys.excepthook = lambda type, value, traceback: QMessageBox.critical(
        None, "Error", f"{type.__name__}: {value}"
    )
    
    login = LoginWindow()
    
    # Connect signal properly
    def handle_login_success(dashboard):
        dashboard.show()
        login.hide()
    
    login.success.connect(handle_login_success)
    
    login.show()
    
    try:
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Application error: {str(e)}")