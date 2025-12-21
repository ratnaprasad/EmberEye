from PyQt5.QtWidgets import (QWizard, QWizardPage, QLabel, QLineEdit, 
                            QVBoxLayout, QFormLayout, QDateEdit, 
                            QMessageBox, QCheckBox)
from PyQt5.QtGui import (
    QPixmap
)
from license_dialog import LicenseKeyPage
from user_creation import UserCreationPage
from resource_helper import get_resource_path

class SetupWizard(QWizard):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("Admin Wizard - Ember Eye")
        # self.addPage(LicensePage(db))
        self.addPage(LicenseKeyPage())
        self.addPage(UserCreationPage(db))
        self.setOption(QWizard.IndependentPages, False)
        self.setOption(QWizard.NoCancelButton, False)
        logo_path = get_resource_path('logo.png')
        self.setPixmap(QWizard.LogoPixmap, QPixmap(logo_path).scaled(64, 64))