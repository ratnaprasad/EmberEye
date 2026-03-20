import sqlite3
import bcrypt
import os
import sys
import importlib
import importlib.util
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLineEdit,
    QPushButton,
    QDialog,
    QMainWindow,
    QMessageBox,
    QLabel,
    QWizard,
    QCheckBox,
    QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import (Qt, pyqtSignal)
from PyQt5.QtGui import QPixmap
from resource_helper import get_resource_path
from sensor_server import SensorServer
from threading import Thread
from database_manager import DatabaseManager
from embereye_base.utils.theme_manager import ThemeManager
# from license_dialog import LicenseKeyDialog
# from user_creation import UserCreationDialog
from embereye_base.app.setup_wizard import SetupWizard
from embereye_base.app.password_reset import PasswordResetDialog


def _load_fieldglass_main_window():
    # Prefer package import first; this works in both source and PyInstaller bundles
    # when 'fieldglass' is collected as a package.
    try:
        module = importlib.import_module('fieldglass.main_window')
        return module.BEMainWindow
    except Exception:
        pass

    # Fallback: attempt to load from known source/bundle file-system layouts.
    candidate_paths = []

    # Source layout: <repo>/embereye-field/fieldglass/main_window.py
    source_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    candidate_paths.append(os.path.join(source_base, 'embereye-field', 'fieldglass', 'main_window.py'))
    candidate_paths.append(os.path.join(source_base, 'fieldglass', 'main_window.py'))

    # Frozen layout: _MEIPASS may contain either fieldglass/main_window.py directly,
    # or under embereye-field/fieldglass depending on build settings.
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidate_paths.append(os.path.join(meipass, 'fieldglass', 'main_window.py'))
        candidate_paths.append(os.path.join(meipass, 'embereye-field', 'fieldglass', 'main_window.py'))

    for fieldglass_path in candidate_paths:
        if not os.path.exists(fieldglass_path):
            continue
        spec = importlib.util.spec_from_file_location('fieldglass_main_window', fieldglass_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.BEMainWindow

    raise ImportError(
        "Failed to load FieldGlass main window. Tried module import and paths: "
        + "; ".join(candidate_paths)
    )


if os.environ.get('EMBEREYE_FIELD', '').strip().lower() in ('1', 'true', 'yes'):
    BEMainWindow = _load_fieldglass_main_window()
else:
    from main_window import BEMainWindow

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
        self.setWindowTitle("Secure Access Terminal - Ember Eye")
        self.setFixedSize(480, 600)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(0)

        terminal_frame = QFrame(self)
        terminal_frame.setObjectName("terminalFrame")
        terminal_layout = QVBoxLayout(terminal_frame)
        terminal_layout.setContentsMargins(26, 20, 26, 16)
        terminal_layout.setSpacing(8)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(Qt.black)
        terminal_frame.setGraphicsEffect(shadow)

        logo_frame = QFrame()
        logo_frame.setObjectName("logoFrame")
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(0, 4, 0, 4)
        logo_layout.setSpacing(2)

        logo_label = QLabel()
        logo_path = get_resource_path('logo.png')
        pixmap = QPixmap(logo_path).scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setObjectName("logoLabel")

        app_name_label = QLabel("Ember Eye")
        app_name_label.setObjectName("appTitle")
        app_name_label.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Secure Terminal Access")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        logo_layout.addWidget(logo_label, 0, Qt.AlignCenter)
        logo_layout.addWidget(app_name_label)
        logo_layout.addWidget(subtitle)

        user_row = QFrame()
        user_row.setObjectName("inputRow")
        user_row_layout = QHBoxLayout(user_row)
        user_row_layout.setContentsMargins(12, 6, 12, 6)
        user_row_layout.setSpacing(8)
        user_badge = QLabel("ID")
        user_badge.setObjectName("inputBadge")
        self.username = QLineEdit(placeholderText="Username")
        self.username.setObjectName("terminalInput")
        self.username.setClearButtonEnabled(True)
        user_row_layout.addWidget(user_badge)
        user_row_layout.addWidget(self.username, 1)

        pass_row = QFrame()
        pass_row.setObjectName("inputRow")
        pass_row_layout = QHBoxLayout(pass_row)
        pass_row_layout.setContentsMargins(12, 6, 12, 6)
        pass_row_layout.setSpacing(8)
        key_badge = QLabel("KEY")
        key_badge.setObjectName("inputBadge")
        self.password = QLineEdit(placeholderText="Password", echoMode=QLineEdit.Password)
        self.password.setObjectName("terminalInput")
        self.password.setClearButtonEnabled(True)
        pass_row_layout.addWidget(key_badge)
        pass_row_layout.addWidget(self.password, 1)

        self.show_password_cb = QCheckBox("Show password")
        self.show_password_cb.setObjectName("showPassword")
        self.show_password_cb.toggled.connect(self._toggle_password_visibility)

        show_row = QHBoxLayout()
        show_row.setContentsMargins(0, 0, 0, 0)
        show_row.addStretch(1)
        show_row.addWidget(self.show_password_cb)

        self.login_btn = QPushButton("AUTHORIZE", clicked=self.authenticate)
        self.login_btn.setObjectName("authorizeBtn")

        self.status = QLabel()
        self.status.setObjectName("statusLabel")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignCenter)

        links_row = QHBoxLayout()
        links_row.setContentsMargins(0, 0, 0, 0)
        links_row.setSpacing(24)

        self.forgot_link = QLabel('<a href="forgot">Forgot password?</a>')
        self.forgot_link.setObjectName("linkLabel")
        self.forgot_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.forgot_link.setOpenExternalLinks(False)
        self.forgot_link.linkActivated.connect(self._handle_link_activated)

        self.create_link = QLabel('<a href="create">Request access</a>')
        self.create_link.setObjectName("linkLabel")
        self.create_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.create_link.setOpenExternalLinks(False)
        self.create_link.linkActivated.connect(self._handle_link_activated)

        links_row.addStretch(1)
        links_row.addWidget(self.forgot_link)
        links_row.addWidget(self.create_link)
        links_row.addStretch(1)

        system_status = QLabel("System status: SECURE")
        system_status.setObjectName("systemStatus")
        system_status.setAlignment(Qt.AlignCenter)

        terminal_layout.addSpacing(6)
        terminal_layout.addWidget(logo_frame)
        terminal_layout.addSpacing(10)
        terminal_layout.addWidget(user_row)
        terminal_layout.addWidget(pass_row)
        terminal_layout.addLayout(show_row)
        terminal_layout.addSpacing(6)
        terminal_layout.addWidget(self.login_btn)
        terminal_layout.addWidget(self.status)
        terminal_layout.addStretch(1)
        terminal_layout.addLayout(links_row)
        terminal_layout.addSpacing(6)
        terminal_layout.addWidget(system_status)

        root_layout.addWidget(terminal_frame)

        self.username.returnPressed.connect(self.authenticate)
        self.password.returnPressed.connect(self.authenticate)
        self.login_btn.setDefault(True)

        self.setStyleSheet("""
            QWidget {
                font-family: "Avenir Next", "Segoe UI", sans-serif;
                background: qradialgradient(
                    cx: 0.2, cy: 0.08, radius: 1.25,
                    fx: 0.2, fy: 0.08,
                    stop: 0 #1a2233,
                    stop: 0.42 #0f1725,
                    stop: 1 #070b13
                );
            }
            QFrame#terminalFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #081421,
                    stop: 0.55 #0a1827,
                    stop: 1 #07101b
                );
                border: 2px solid rgba(233, 219, 42, 0.55);
                border-radius: 34px;
            }
            QFrame#logoFrame {
                background: transparent;
                border: 0;
            }
            QLabel#logoLabel {
                background: transparent;
            }
            QLabel#appTitle {
                color: #f8eb28;
                font-size: 32px;
                font-weight: 800;
                letter-spacing: 0.6px;
                background: transparent;
            }
            QLabel#subtitle {
                color: #f0dc2e;
                font-size: 20px;
                font-weight: 600;
                letter-spacing: 0.4px;
                background: transparent;
            }
            QFrame#inputRow {
                background: rgba(27, 39, 56, 0.76);
                border: 2px solid rgba(234, 217, 39, 0.72);
                border-radius: 12px;
            }
            QLabel#inputBadge {
                color: rgba(231, 215, 56, 0.95);
                font-size: 10px;
                font-weight: 800;
                min-width: 22px;
                background: transparent;
            }
            QLineEdit#terminalInput {
                background: transparent;
                border: 0;
                color: #f5ef9b;
                font-size: 16px;
                font-weight: 500;
                selection-background-color: rgba(233, 219, 42, 0.32);
            }
            QLineEdit#terminalInput::placeholder {
                color: rgba(209, 196, 69, 0.72);
            }
            QCheckBox#showPassword {
                color: rgba(214, 203, 87, 0.95);
                font-size: 12px;
                font-weight: 600;
                spacing: 8px;
                background: transparent;
            }
            QCheckBox#showPassword::indicator {
                width: 34px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid rgba(185, 196, 209, 0.5);
                background: rgba(30, 38, 53, 0.96);
            }
            QCheckBox#showPassword::indicator:checked {
                border: 1px solid rgba(230, 215, 46, 0.92);
                background: rgba(240, 224, 54, 0.98);
            }
            QPushButton#authorizeBtn {
                min-height: 54px;
                border-radius: 10px;
                border: 2px solid #ffe924;
                background: #f4e51f;
                color: #0d1118;
                font-size: 22px;
                font-weight: 900;
                letter-spacing: 2px;
                padding: 4px 10px;
            }
            QPushButton#authorizeBtn:hover {
                background: #fff152;
            }
            QPushButton#authorizeBtn:pressed {
                background: #d9ca17;
            }
            QLabel#statusLabel {
                color: #ff6c5c;
                min-height: 18px;
                background: transparent;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#linkLabel {
                color: rgba(221, 208, 79, 0.92);
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }
            QLabel#linkLabel:hover {
                color: #fff08f;
            }
            QLabel#systemStatus {
                color: rgba(201, 195, 93, 0.86);
                font-size: 10px;
                letter-spacing: 0.4px;
                font-weight: 600;
                background: transparent;
            }
        """)

    def _toggle_password_visibility(self, checked):
        self.password.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _set_status(self, text, is_error=True):
        color = "#c62828" if is_error else "#2e7d32"
        self.status.setStyleSheet(
            f"color: {color}; min-height: 20px; background: transparent; font-size: 12px; font-weight: 500;"
        )
        self.status.setText(text)

    def _handle_link_activated(self, action):
        if action == "forgot":
            self.show_password_reset()
            return
        QMessageBox.information(
            self,
            "Create Account",
            "Account creation is managed by administrator setup.",
        )

    def authenticate(self):
        username = self.username.text()
        password = self.password.text()

        if not username.strip():
            self._set_status("Please enter your username.")
            self.username.setFocus()
            return
        if not password:
            self._set_status("Please enter your password.")
            self.password.setFocus()
            return
        self._set_status("")

        try:
            user = self.db.get_user(username)
            if not user:
                self._set_status('Invalid credentials')
                QMessageBox.warning(self, 'Error', 'Invalid credentials')
                return

            # Unpack all 13 fields from the database
            (username_db, password_hash, attempts, locked,
            first_name, last_name, dob,
            sq1, sa1, sq2, sa2, sq3, sa3) = user

            if locked:
                self._set_status('Your account is locked')
                QMessageBox.warning(self, 'Account Locked', 
                                'Your account has been locked. Contact administrator.')
                return

            # Verify password with bcrypt
            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                self.db.increment_failed_attempt(username)
                remaining = self.MAX_ATTEMPTS - (attempts + 1)
                if remaining <= 0:
                    self.db.lock_user(username)
                    self._set_status('Too many failed attempts. Account locked.')
                    QMessageBox.warning(self, 'Account Locked', 
                                    'Too many failed attempts. Account locked.')
                else:
                    self._set_status(f'Invalid credentials. {remaining} attempts remaining.')
                    QMessageBox.warning(self, 'Invalid Credentials',
                                        f'Invalid credentials. {remaining} attempts remaining.')
                return

            # Reset attempts on successful login
            self.db.reset_user(username)
            self._set_status('Login successful', is_error=False)

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