import sys
import json
import base64
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTextEdit, QLabel, QHBoxLayout, QInputDialog, QMessageBox, QFileDialog
)
from license_generator import LicenseKeyGenerator
from vendorepojo import Vendor

class LicenseGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ember Eye License Generator")
        self.secret_key = "my_super_secret_key"  # Replace with a strong, unique secret key
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Key Input Section
        self.key_text = QTextEdit()
        self.key_text.setPlaceholderText("Paste activation key here...")
        
        key_btn_layout = QHBoxLayout()
        self.load_file_btn = QPushButton("Load from File")
        self.load_file_btn.clicked.connect(self.load_from_file)
        self.load_text_btn = QPushButton("Use Pasted Key")
        self.load_text_btn.clicked.connect(self.load_from_text)
        key_btn_layout.addWidget(self.load_file_btn)
        key_btn_layout.addWidget(self.load_text_btn)

        # Client Info Section
        form = QFormLayout()
        self.client_name = QLineEdit()
        self.client_address = QLineEdit()
        self.city = QLineEdit()
        self.days_entry = QLineEdit()
        form.addRow("Client Name:", self.client_name)
        form.addRow("Client Address:", self.client_address)
        form.addRow("City:", self.city)
        form.addRow("License Days:", self.days_entry)


        # Generate Button
        self.generate_btn = QPushButton("Generate License")
        self.generate_btn.clicked.connect(self.generate_license)

        # Output Section
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.copy_btn = QPushButton("Copy License Key")
        self.copy_btn.clicked.connect(self.copy_license)

        # Assemble layout
        layout.addWidget(QLabel("Private Key:"))
        layout.addWidget(self.key_text)
        layout.addLayout(key_btn_layout)
        layout.addLayout(form)
        layout.addWidget(self.generate_btn)
        layout.addWidget(QLabel("Generated License:"))
        layout.addWidget(self.output)
        layout.addWidget(self.copy_btn)
        
        self.setLayout(layout)

    def load_from_file(self):
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open Activation Key", "", "dat Files (*.dat)")
            if path:
                with open(path, "rb") as f:
                    key_data = f.read()
                # self.process_key(key_data)
                self.key_text.setPlainText(str(key_data))
        except Exception as e:
            self.handle_error(e)

    def load_from_text(self):
        try:
            key_data = self.key_text.toPlainText().encode()
            if not key_data:
                raise ValueError("No key provided")
            self.process_key(key_data)
        except Exception as e:
            self.handle_error(e)

    def process_key(self, key_data):
        try:
            generator = LicenseKeyGenerator(self.secret_key)
            license_key = generator.generate_license_key(key_data, Vendor("102134", self.client_name.text().strip(), self.city.text().strip(),self.client_address.text().strip(), int(self.days_entry.text().strip())))
            if license_key:
                # print(f"License Key: {license_key}")
                self.output.setPlainText(license_key)

        except Exception as e:
            raise ValueError(f"Key validation failed: {str(e)}")
                
    def handle_error(self, error):
        error_msg = f"""
        Key Loading Failed!

        Reason: {str(error)}

        Required Format:
        -----BEGIN RSA PRIVATE KEY-----
        [Base64 encoded key data]
        -----END RSA PRIVATE KEY-----

        Or:

        -----BEGIN ENCRYPTED PRIVATE KEY-----
        [Base64 encoded encrypted key data]
        -----END ENCRYPTED PRIVATE KEY-----

        Steps to Fix:
        1. Generate new keys using Admin Wizard
        2. Use private_key.pem (not public key)
        3. Ensure no file corruption
        4. Use exact password if encrypted
        """
        QMessageBox.critical(self, "Key Error", error_msg)

    def generate_license(self):
        try:
            if not all([
                self.client_name.text().strip(),
                self.client_address.text().strip(),
                self.days_entry.text().strip()
            ]):
                raise ValueError("All fields are required")
                
            if not self.days_entry.text().isdigit():
                raise ValueError("License days must be a number")
                
            days = int(self.days_entry.text())
            if days < 1 or days > 3650:  # 10 year max
                raise ValueError("License days must be between 1 and 3650")
                
            
            key_data = self.key_text.toPlainText().encode()
            if not key_data:
                raise ValueError("No key provided")
            self.process_key(key_data)
            # self.output.setPlainText(license_key)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Generation failed: {str(e)}")

    def copy_license(self):
        QApplication.clipboard().setText(self.output.toPlainText())
        QMessageBox.information(self, "Copied", "License copied to clipboard")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LicenseGenerator()
    window.show()
    sys.exit(app.exec_())