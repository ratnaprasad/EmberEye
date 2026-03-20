from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox

class PasswordResetDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.current_step = 0
        self.username = None
        self.setWindowTitle("Password Reset")
        self.setStyleSheet("""
            QDialog { background-color: #0f1722; color: #e7c75f; border: 1px solid #d7aa1a; }
            QLabel { color: #e7c75f; font-size: 12px; font-weight: 600; }
            QLineEdit {
                background-color: #141d2a;
                color: #ffe7a0;
                border: 1px solid #75602a;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QLineEdit:focus { border: 1px solid #e2b83a; }
            QPushButton {
                background-color: #273448;
                color: #f0d17c;
                border: 1px solid #7a6633;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #344a67; border-color: #d7aa1a; color: #ffe9a6; }
        """)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.show_username_step()

    def show_username_step(self):
        self.clear_layout()
        self.username_input = QLineEdit(placeholderText="Username")
        self.submit_btn = QPushButton("Next", clicked=self.verify_username)
        self.layout.addWidget(QLabel("Enter your username:"))
        self.layout.addWidget(self.username_input)
        self.layout.addWidget(self.submit_btn)

    def verify_username(self):
        username = self.username_input.text()
        user = self.db.get_user(username)
        if not user:
            QMessageBox.warning(self, "Error", "Username not found")
            return
        self.username = username
        self.show_dob_step()

    # Add similar methods for dob verification and secret questions