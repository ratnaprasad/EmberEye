import sqlite3
import bcrypt
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QDialog,
    QMainWindow,
    QMessageBox,
    QLabel,
    QWizard,
)
from PyQt5.QtCore import (Qt, pyqtSignal)
from PyQt5.QtGui import QPixmap
from resource_helper import get_resource_path
from main_window import BEMainWindow
from sensor_server import SensorServer
from threading import Thread
from database_manager import DatabaseManager
from theme_manager import ThemeManager
# from license_dialog import LicenseKeyDialog
# from user_creation import UserCreationDialog
from setup_wizard import SetupWizard
from password_reset import PasswordResetDialog

class EELoginWindow(QWidget):
    success = pyqtSignal(QMainWindow)
    MAX_ATTEMPTS = 3

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.server = None
        self.db = DatabaseManager()
        self.theme_manager = ThemeManager()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Login - Ember Eye")
        self.setGeometry(300, 300, 300, 250)
        layout = QVBoxLayout()

        # Logo and App Name
        logo_label = QLabel()
        logo_path = get_resource_path('logo.png')
        pixmap = QPixmap(logo_path).scaled(64, 64, Qt.KeepAspectRatio)
        logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignCenter)

        app_name_label = QLabel("Ember Eye")
        app_name_label.setAlignment(Qt.AlignCenter)
        font = app_name_label.font()
        font.setPointSize(16)
        app_name_label.setFont(font)
        # Form elements
        self.username = QLineEdit(placeholderText="Username")
        self.password = QLineEdit(placeholderText="Password", echoMode=QLineEdit.Password)
        
        self.login_btn = QPushButton("Login", clicked=self.authenticate)
        self.login_btn.setObjectName("primary")
        self.status = QLabel()
        self.forgot_btn = QPushButton("Forgot Password?", clicked=self.show_password_reset)
        
        layout.addWidget(logo_label)
        layout.addWidget(app_name_label)
        layout.addWidget(self.username)
        layout.addWidget(self.password)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.status)
        self.setLayout(layout)

    def authenticate(self):
        username = self.username.text()
        password = self.password.text()

        try:
            user = self.db.get_user(username)
            if not user:
                QMessageBox.warning(self, 'Error', 'Invalid credentials')
                return

            # Unpack all 13 fields from the database
            (username_db, password_hash, attempts, locked,
            first_name, last_name, dob,
            sq1, sa1, sq2, sa2, sq3, sa3) = user

            if locked:
                QMessageBox.warning(self, 'Account Locked', 
                                'Your account has been locked. Contact administrator.')
                return

            # Verify password with bcrypt
            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                self.db.increment_failed_attempt(username)
                remaining = self.MAX_ATTEMPTS - (attempts + 1)
                if remaining <= 0:
                    self.db.lock_user(username)
                    QMessageBox.warning(self, 'Account Locked', 
                                    'Too many failed attempts. Account locked.')
                else:
                    QMessageBox.warning(self, 'Invalid Credentials',
                                        f'Invalid credentials. {remaining} attempts remaining.')
                return

            # Reset attempts on successful login
            self.db.reset_user(username)

            # Handle admin flow
            if username == 'admin':
                # license_dialog = LicenseKeyDialog(self.db)
                # if license_dialog.exec_() != QDialog.Accepted:
                #     return

                # user_creation_dialog = UserCreationDialog(self.db)
                # if user_creation_dialog.exec_() == QDialog.Accepted:
                #     QMessageBox.information(self, 'Success', 
                #                         'User created successfully! New user can now login.')
                wizard = SetupWizard(self.db)
                if wizard.exec_() == QWizard.Accepted:
                    wizard.currentPage().create_user()
                    QMessageBox.information(self, 'Success', 
                                        'User created successfully!')
                return

            # Regular user flow - Modern theme is default
            self.theme_manager.set_theme(ThemeManager.MODERN)
            
            self.start_sensor_server()
            self.dashboard = BEMainWindow(theme_manager=self.theme_manager)
            self.success.emit(self.dashboard)
            self.hide()

        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Authentication failed: {str(e)}')

    def start_sensor_server(self):
        """Start sensor server in background thread"""
        try:
            # Prevent duplicate starts if already running
            if getattr(self, 'server', None) and getattr(self.server, 'running', False):
                print("Sensor server already running; skipping start")
                return

            self.server = SensorServer()
            self.server_thread = Thread(target=self.server.start, daemon=True)
            self.server_thread.start()
            print("Sensor server started")
        except OSError as e:
            # Handle address already in use or other bind issues gracefully
            msg = str(e)
            print(f"Sensor server start error: {msg}")
            QMessageBox.warning(self, 'Sensor Server', f'Could not start sensor server: {msg}')

    def show_password_reset(self):
        reset_dialog = PasswordResetDialog(self.db)
        reset_dialog.exec_()
 
    def closeEvent(self, event):
        if self.server:
            self.server.stop()
        self.db.close()
        super().closeEvent(event)