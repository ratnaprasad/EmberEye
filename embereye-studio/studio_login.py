"""
EmberEye Studio Login Window
Handles authentication and user login
"""

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QFont, QIcon
from PyQt6.QtCore import Qt
import bcrypt


class StudioLoginWindow(QWidget):
    """Login window for EmberEye Studio"""
    
    login_success = pyqtSignal(str)  # Emits username on successful login
    MAX_ATTEMPTS = 3

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.attempt_count = 0
        self.init_ui()

    def init_ui(self):
        """Initialize login UI"""
        self.setWindowTitle("🔥 EmberEye STUDIO - Training Hub Login")
        self.setGeometry(400, 300, 450, 450)
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
            }
            QLineEdit {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
                background-color: white;
            }
            QPushButton {
                padding: 10px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#loginBtn {
                background-color: #2196F3;
                color: white;
            }
            QPushButton#loginBtn:hover {
                background-color: #1976D2;
            }
            QPushButton#forgotBtn {
                background-color: #f5f5f5;
                color: #2196F3;
                border: 1px solid #2196F3;
            }
            QLabel#titleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #333;
            }
            QLabel#subtitleLabel {
                font-size: 14px;
                color: #666;
            }
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 15px;
                margin-top: 10px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Logo and title
        title = QLabel("🔥 EmberEye Studio")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("Training & Model Development Hub")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add distinctive banner
        banner = QLabel("🧠 LABS EDITION - NOT FIELD APP")
        banner.setStyleSheet("background-color: #FF9800; color: white; padding: 8px; font-weight: bold; font-size: 11px;")
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(banner)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        
        # Separator
        layout.addSpacing(10)

        # Login form group
        form_group = QGroupBox("User Login")
        form_layout = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        self.username_input.returnPressed.connect(self.authenticate)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.authenticate)

        form_layout.addRow("Username:", self.username_input)
        form_layout.addRow("Password:", self.password_input)
        form_group.setLayout(form_layout)
        
        layout.addWidget(form_group)

        # Status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        
        self.login_btn = QPushButton("Login")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.clicked.connect(self.authenticate)
        self.login_btn.setMinimumHeight(40)
        
        self.forgot_btn = QPushButton("Forgot Password?")
        self.forgot_btn.setObjectName("forgotBtn")
        self.forgot_btn.clicked.connect(self.show_forgot_password)
        self.forgot_btn.setMinimumHeight(40)
        
        button_layout.addWidget(self.login_btn)
        button_layout.addWidget(self.forgot_btn)
        
        layout.addLayout(button_layout)

        # Test credentials hint (remove in production)
        hint = QLabel("Demo: admin/password, ratna/ratna, s3micro/s3micro")
        hint.setStyleSheet("color: #999; font-size: 10px; text-align: center;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addStretch()
        self.setLayout(layout)

    def authenticate(self):
        """Authenticate user"""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Validation Error", "Please enter username and password")
            return

        try:
            user = self.db.get_user(username)
            if not user:
                self.update_status("Invalid credentials", error=True)
                self.attempt_count += 1
                self.check_account_lockout()
                return

            # Unpack user data
            (db_username, password_hash, attempts, locked,
             first_name, last_name, dob,
             sq1, sa1, sq2, sa2, sq3, sa3, role) = user

            if locked:
                QMessageBox.critical(
                    self, "Account Locked",
                    "Your account has been locked.\nPlease contact the administrator."
                )
                return

            # Verify password
            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                self.db.increment_failed_attempt(username)
                self.attempt_count += 1
                remaining = self.MAX_ATTEMPTS - self.attempt_count
                
                if remaining <= 0:
                    self.db.lock_user(username)
                    QMessageBox.critical(
                        self, "Account Locked",
                        "Too many failed attempts.\nYour account has been locked."
                    )
                else:
                    self.update_status(f"Invalid credentials. {remaining} attempts remaining", error=True)
                return

            # Successful login
            self.db.reset_user(username)
            self.update_status(f"Welcome, {first_name}!", error=False)
            self.login_success.emit(username)
            self.clear_inputs()

        except Exception as e:
            QMessageBox.critical(self, "Authentication Error", f"Error: {str(e)}")

    def update_status(self, message, error=False):
        """Update status message"""
        self.status_label.setText(message)
        if error:
            self.status_label.setStyleSheet("color: #d32f2f; font-size: 11px; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: #388e3c; font-size: 11px; font-weight: bold;")

    def check_account_lockout(self):
        """Check if account should be locked"""
        if self.attempt_count >= self.MAX_ATTEMPTS:
            username = self.username_input.text()
            if username:
                self.db.lock_user(username)
                QMessageBox.critical(
                    self, "Account Locked",
                    f"Too many failed attempts for '{username}'.\nAccount has been locked."
                )

    def show_forgot_password(self):
        """Show password reset dialog"""
        QMessageBox.information(
            self, "Password Reset",
            "Please contact your administrator to reset your password."
        )

    def clear_inputs(self):
        """Clear input fields"""
        self.username_input.clear()
        self.password_input.clear()
        self.username_input.setFocus()

    def closeEvent(self, event):
        """Handle window close"""
        if self.db:
            self.db.close()
        event.accept()
