from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox

class PasswordResetDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.current_step = 0
        self.username = None
        self.setWindowTitle("Password Reset")
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