from PyQt5.QtWidgets import QWizardPage,    QDialog, QFormLayout, QLineEdit, QPushButton, QDateEdit, QMessageBox

class UserCreationDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("Create New User")
        layout = QFormLayout()
        
        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.username = QLineEdit()
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        self.dob = QDateEdit(calendarPopup=True)
        self.questions = [QLineEdit() for _ in range(3)]
        self.answers = [QLineEdit() for _ in range(3)]
        
        fields = [
            ("First Name", self.first_name),
            ("Last Name", self.last_name),
            ("Username", self.username),
            ("Password", self.password),
            ("Date of Birth", self.dob),
        ]
        
        for i in range(3):
            fields.append((f"Secret Question {i+1}", self.questions[i]))
            fields.append((f"Answer {i+1}", self.answers[i]))
        
        for label, widget in fields:
            layout.addRow(label, widget)
        
        self.submit_btn = QPushButton("Create User", clicked=self.create_user)
        layout.addRow(self.submit_btn)
        self.setLayout(layout)

    def create_user(self):
        # Validation and user creation logic
        if self.db.get_user(self.username.text()):
            QMessageBox.warning(self, "Error", "Username already exists")
            return
        
        user_data = {
            'first_name': self.first_name.text(),
            'last_name': self.last_name.text(),
            'username': self.username.text(),
            'password': self.password.text(),
            'dob': self.dob.date().toString("yyyy-MM-dd"),
            'questions': [
                (self.questions[i].text(), self.answers[i].text())
                for i in range(3)
            ]
        }
        
        self.db.create_user(user_data)
        QMessageBox.information(self, "Success", "User created successfully")
        self.accept()

class UserCreationPage(QWizardPage):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setTitle("Create New User")
        self.setSubTitle("Enter user details and security questions")

        layout = QFormLayout()
        
        # Basic Info
        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.username = QLineEdit()
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        self.confirm_pass = QLineEdit(echoMode=QLineEdit.Password)
        self.dob = QDateEdit(calendarPopup=True)
        
        # Security Questions
        self.questions = [
            QLineEdit() for _ in range(3)
        ]
        self.answers = [
            QLineEdit() for _ in range(3)
        ]
        
        # Registration
        self.registerField("first_name*", self.first_name)
        self.registerField("last_name*", self.last_name)
        self.registerField("username*", self.username)
        self.registerField("password*", self.password)
        self.registerField("confirm_pass*", self.confirm_pass)
        self.registerField("dob*", self.dob)
        
        # Add fields to layout
        layout.addRow("First Name:", self.first_name)
        layout.addRow("Last Name:", self.last_name)
        layout.addRow("Username:", self.username)
        layout.addRow("Password:", self.password)
        layout.addRow("Confirm Password:", self.confirm_pass)
        layout.addRow("Date of Birth:", self.dob)
        
        # Add security questions
        for i in range(3):
            layout.addRow(f"Security Question {i+1}:", self.questions[i])
            layout.addRow(f"Answer {i+1}:", self.answers[i])
            self.registerField(f"question_{i+1}*", self.questions[i])
            self.registerField(f"answer_{i+1}*", self.answers[i])

        self.setLayout(layout)

    def validatePage(self):
        # Password match check
        if self.password.text() != self.confirm_pass.text():
            QMessageBox.warning(self, "Error", "Passwords do not match")
            return False
            
        # Username availability check
        if self.db.get_user(self.username.text()):
            QMessageBox.warning(self, "Error", "Username already exists")
            return False
            
        # Security questions validation
        for i in range(3):
            if not self.questions[i].text() or not self.answers[i].text():
                QMessageBox.warning(self, "Error", 
                                  f"Security Question {i+1} and answer are required")
                return False
                
        return True

    def create_user(self):
        user_data = {
            'first_name': self.field("first_name"),
            'last_name': self.field("last_name"),
            'username': self.field("username"),
            'password': self.field("password"),
            'dob': self.field("dob").toString("yyyy-MM-dd"),
            'questions': [
                (self.field(f"question_{i+1}"), self.field(f"answer_{i+1}"))
                for i in range(3)
            ]
        }
        self.db.create_user(user_data)
