"""
Master Class Configuration Dialog for EmberEye.
UI for managing hierarchical class/subclass definitions.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, 
                             QTreeWidgetItem, QPushButton, QLineEdit, QLabel,
                             QMessageBox, QInputDialog)
from PyQt5.QtCore import Qt
from master_class_config import load_master_classes, save_master_classes

class MasterClassConfigDialog(QDialog):
    """Dialog for configuring master classes and subclasses."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Master Class Configuration")
        self.resize(600, 500)
        self.classes_dict = load_master_classes()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        label = QLabel("Configure object detection classes and subclasses:")
        layout.addWidget(label)
        
        # Tree widget for hierarchical display
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Class", "Subclasses"])
        self.tree.setColumnWidth(0, 250)
        layout.addWidget(self.tree)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        add_class_btn = QPushButton("Add Class")
        add_class_btn.clicked.connect(self.add_class)
        btn_layout.addWidget(add_class_btn)
        
        add_subclass_btn = QPushButton("Add Subclass")
        add_subclass_btn.clicked.connect(self.add_subclass)
        btn_layout.addWidget(add_subclass_btn)
        
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected)
        btn_layout.addWidget(remove_btn)
        
        layout.addLayout(btn_layout)
        
        # Save/Cancel buttons
        bottom_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_and_close)
        bottom_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        
        layout.addLayout(bottom_layout)
        
        self.populate_tree()
    
    def populate_tree(self):
        """Populate tree widget with current classes."""
        self.tree.clear()
        for main_class, subclasses in self.classes_dict.items():
            item = QTreeWidgetItem(self.tree, [main_class, ""])
            item.setData(0, Qt.UserRole, main_class)
            if subclasses:
                for subclass in subclasses:
                    child = QTreeWidgetItem(item, [subclass, ""])
                    child.setData(0, Qt.UserRole, f"{main_class}:{subclass}")
            item.setExpanded(True)
    
    def add_class(self):
        """Add a new main class."""
        text, ok = QInputDialog.getText(self, "Add Class", "Enter class name:")
        if ok and text:
            text = text.strip()
            if text in self.classes_dict:
                QMessageBox.warning(self, "Duplicate", f"Class '{text}' already exists")
                return
            self.classes_dict[text] = []
            self.populate_tree()
    
    def add_subclass(self):
        """Add a subclass to the selected main class."""
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Select a main class first")
            return
        
        item = selected[0]
        # Get main class (if subclass selected, get parent)
        if item.parent():
            main_class = item.parent().text(0)
        else:
            main_class = item.text(0)
        
        text, ok = QInputDialog.getText(self, "Add Subclass", 
                                        f"Enter subclass name for '{main_class}':")
        if ok and text:
            text = text.strip()
            if text in self.classes_dict.get(main_class, []):
                QMessageBox.warning(self, "Duplicate", f"Subclass '{text}' already exists")
                return
            if main_class not in self.classes_dict:
                self.classes_dict[main_class] = []
            self.classes_dict[main_class].append(text)
            self.populate_tree()
    
    def remove_selected(self):
        """Remove the selected class or subclass."""
        selected = self.tree.selectedItems()
        if not selected:
            return
        
        item = selected[0]
        if item.parent():  # Subclass
            main_class = item.parent().text(0)
            subclass = item.text(0)
            if main_class in self.classes_dict and subclass in self.classes_dict[main_class]:
                self.classes_dict[main_class].remove(subclass)
        else:  # Main class
            main_class = item.text(0)
            if main_class in self.classes_dict:
                del self.classes_dict[main_class]
        
        self.populate_tree()
    
    def save_and_close(self):
        """Save configuration and close dialog."""
        if save_master_classes(self.classes_dict):
            QMessageBox.information(self, "Saved", "Master class configuration saved successfully")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to save configuration")
