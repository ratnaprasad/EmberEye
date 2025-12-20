import json
import base64
import uuid
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.asymmetric import padding
from PyQt5.QtWidgets import QWizard, QApplication, QFileDialog, QTextEdit,QHBoxLayout, QWizardPage, QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox
from activationkey_generator import ActivationKeyGenerator
from license_generator import LicenseKeyGenerator

class LicenseKeyPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("License Management")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Key Generation
        self.generate_btn = QPushButton("Generate Activation Key")
        self.generate_btn.clicked.connect(self.generate_keys)

        # Public Key Display
        self.public_key_text = QTextEdit()
        self.public_key_text.setReadOnly(True)

        # Key Actions
        key_btn_layout = QHBoxLayout()
        self.copy_btn = QPushButton("Copy Key")
        self.copy_btn.clicked.connect(self.copy_key)
        self.save_btn = QPushButton("Save Key")
        self.save_btn.clicked.connect(self.save_key)
        key_btn_layout.addWidget(self.copy_btn)
        key_btn_layout.addWidget(self.save_btn)

        # License Validation
        self.license_entry = QTextEdit()
        self.validate_btn = QPushButton("Validate License")
        self.validate_btn.clicked.connect(self.validate_license)
        self.result_label = QLabel()

        # Add widgets to layout
        layout.addWidget(self.generate_btn)
        layout.addWidget(QLabel("Public Key:"))
        layout.addWidget(self.public_key_text)
        layout.addLayout(key_btn_layout)
        layout.addWidget(QLabel("License Key:"))
        layout.addWidget(self.license_entry)
        layout.addWidget(self.validate_btn)
        layout.addWidget(self.result_label)
        self.setLayout(layout)

        self.private_key = None
        self.activation_key = ""
        self.secret_key = "my_super_secret_key"
    # def generate_keys(self):
    #     try:
    #         self.private_key = rsa.generate_private_key(
    #             public_exponent=65537,
    #             key_size=2048,
    #             backend=default_backend()
    #         )

    #         # Save with explicit Traditional format
    #         with open("private_key.pem", "wb") as f:
    #             f.write(self.private_key.private_bytes(
    #                 encoding=serialization.Encoding.PEM,
    #                 format=serialization.PrivateFormat.TraditionalOpenSSL,
    #                 encryption_algorithm=serialization.NoEncryption()
    #             ))
    #             # Store public key
    #             self.public_key_pem = self.private_key.public_key().public_bytes(
    #                 encoding=serialization.Encoding.PEM,
    #                 format=serialization.PublicFormat.SubjectPublicKeyInfo
    #             ).decode()

    #             self.public_key_text.setPlainText(self.public_key_pem)
    #             self.copy_btn.setEnabled(True)
    #             self.save_btn.setEnabled(True)

    #     except Exception as e:
    #         QMessageBox.critical(self, "Error", f"Key generation failed: {str(e)}")

    def generate_keys(self):
        try:
            generator = ActivationKeyGenerator(self.secret_key)
            user_id = str(uuid.uuid4())
            self.activation_key = generator.generate_activation_key(user_id)
            # print(generator.generate_activation_key(user_id))
            # Save public key to file
            with open("activation_key.dat", "w") as f:
                f.write(self.activation_key)

            # with open("private_key.pem", "w") as f:
            #     f.write(self.private_key)

            self.public_key_text.setPlainText(self.activation_key)
            QMessageBox.information(self, "Success", 
                "Key generated:")

        except Exception as e:
            QMessageBox.critical(self, "Generation Error", 
                f"Failed to generate keys: {str(e)}\n"
                "Ensure cryptography package is updated")


    def copy_key(self):
        QApplication.clipboard().setText(self.activation_key)
        QMessageBox.information(self, "Success", "Public key copied to clipboard")

    def save_key(self):
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Activation Key", "", "PEMat Files (*.dat)")
            if path:
                with open(path, 'w') as f:
                    f.write(self.activation_key)
                QMessageBox.information(self, "Success", "Key saved successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {str(e)}")

    def validate_license(self):
        try:
            # Decode license data
            license_b64 = self.license_entry.toPlainText().strip()
            if not license_b64:
                raise ValueError("Empty license key")
            secret_key = "my_super_secret_key"
            generator = LicenseKeyGenerator(secret_key)
            is_valid, vendore_json,valid_activation_key, valid_expiration_date = generator.validate_license_key(license_b64)
            if(is_valid):
                QMessageBox.information(self, "Success", "Key saved successfully")
                
            # license_data = json.loads(base64.b64decode(license_b64))
            
            # # Load public key with validation
            # public_key = serialization.load_pem_public_key(
            #     license_data['public_key'].encode(),
            #     backend=default_backend()
            # )
            
            # # Convert to PEM for verification
            # public_pem = public_key.public_bytes(
            #     encoding=serialization.Encoding.PEM,
            #     format=serialization.PublicFormat.SubjectPublicKeyInfo
            # ).decode()
            
            # if public_pem != license_data['public_key']:
            #     raise ValueError("Public key tampering detected")

            # Rest of validation logic...
            
        except Exception as e:
            self.result_label.setText(f"Invalid License: {str(e)}")
            return False
