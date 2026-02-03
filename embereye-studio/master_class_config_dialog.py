"""
Master Class & Threat Rules Dialog for EmberEye.
Manage taxonomy (classes/subclasses), threat rules, and settings in one place.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton,
    QLabel, QMessageBox, QInputDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFormLayout, QComboBox, QLineEdit, QDialogButtonBox, QWidget, QTextEdit
)
from PyQt5.QtCore import Qt
import os
from resource_helper import get_data_path
from master_class_config import load_master_classes, save_master_classes
from threat_rules import load_threat_rules, save_threat_rules, DEFAULT_SETTINGS, SEVERITIES, DEFAULT_THREAT_RULES, DEFAULT_EXAMPLES

class MasterClassConfigDialog(QDialog):
    """Dialog for configuring taxonomy, rules, and settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Taxonomy, Rules, and Settings")
        self.resize(760, 580)
        self.classes_dict = load_master_classes()
        self.threat_matrix, self.examples, self.settings = load_threat_rules()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- Tab 1: Classes ---
        classes_tab = QWidget()
        classes_layout = QVBoxLayout(classes_tab)

        label = QLabel("Manage object detection classes and subclasses:")
        classes_layout.addWidget(label)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Class", "Subclasses"])
        self.tree.setColumnWidth(0, 250)
        classes_layout.addWidget(self.tree)
        
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
        btn_layout.addStretch(1)
        classes_layout.addLayout(btn_layout)

        tabs.addTab(classes_tab, "Classes")

        # --- Tab 2: Rules (Threat Matrix) ---
        rules_tab = QWidget()
        rules_layout = QVBoxLayout(rules_tab)

        rules_label = QLabel("Threat Classification Matrix (organized by severity level):")
        rules_layout.addWidget(rules_label)

        # Threat matrix display with tabs for each severity level
        threat_tabs = QTabWidget()
        
        for severity in SEVERITIES:
            severity_widget = QWidget()
            severity_layout = QVBoxLayout(severity_widget)
            
            # Rules list for this severity
            table = QTableWidget(0, 2)
            table.setHorizontalHeaderLabels(["Rule", "Actions"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            
            # Populate rules for this severity
            rules_list = self.threat_matrix.get(severity, [])
            for rule_text in rules_list:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(rule_text))
                # Action buttons (edit/remove)
                action_btn = QPushButton("✎ ✗")
                action_btn.setMaximumWidth(50)
                action_btn.clicked.connect(lambda checked, s=severity, r=row: self._edit_threat_rule(s, r, table))
                table.setCellWidget(row, 1, action_btn)
            
            severity_layout.addWidget(table)
            
            # Add rule button for this severity
            add_btn_layout = QHBoxLayout()
            add_btn = QPushButton(f"Add {severity} Rule")
            add_btn.clicked.connect(lambda checked, s=severity, t=table: self._add_threat_rule(s, t))
            add_btn_layout.addWidget(add_btn)
            add_btn_layout.addStretch(1)
            severity_layout.addLayout(add_btn_layout)
            
            threat_tabs.addTab(severity_widget, severity)
        
        rules_layout.addWidget(threat_tabs)

        # Scenarios sub-tab
        scenarios_label = QLabel("Scenarios:")
        rules_layout.addWidget(scenarios_label)
        
        self.scenarios_table = QTableWidget(0, 5)
        self.scenarios_table.setHorizontalHeaderLabels(["Scenario", "Detected", "Classification", "Rule", "Notes"])
        self.scenarios_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        rules_layout.addWidget(self.scenarios_table)
        
        scenarios_btn_layout = QHBoxLayout()
        add_scenario_btn = QPushButton("Add Scenario")
        add_scenario_btn.clicked.connect(self.add_scenario)
        scenarios_btn_layout.addWidget(add_scenario_btn)
        scenarios_btn_layout.addStretch(1)
        rules_layout.addLayout(scenarios_btn_layout)

        tabs.addTab(rules_tab, "Rules")
        self.populate_scenarios()

        # --- Tab 3: Settings ---
        settings_tab = QWidget()
        settings_layout = QFormLayout(settings_tab)
        self.default_flame_sev = QComboBox(); self.default_flame_sev.addItems(SEVERITIES)
        self.default_flame_sev.setCurrentText(self.settings.get('default_flame', 'HIGH'))
        settings_layout.addRow("Default flame severity", self.default_flame_sev)

        self.default_smoke_sev = QComboBox(); self.default_smoke_sev.addItems(SEVERITIES)
        self.default_smoke_sev.setCurrentText(self.settings.get('default_smoke', 'MEDIUM'))
        settings_layout.addRow("Default smoke severity", self.default_smoke_sev)

        self.score_threshold_edit = QLineEdit(str(self.settings.get('score_threshold', 0.4)))
        settings_layout.addRow("Score threshold (0-1)", self.score_threshold_edit)

        self.notes_box = QTextEdit()
        self.notes_box.setPlaceholderText("Notes / operator guidance")
        self.notes_box.setText(self.settings.get('notes', ''))
        settings_layout.addRow("Notes", self.notes_box)

        tabs.addTab(settings_tab, "Settings")

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_and_close)
        bottom_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addStretch(1)
        layout.addLayout(bottom_layout)

        self.populate_tree()
        self.populate_scenarios()
    
    def populate_scenarios(self):
        """Populate scenarios table."""
        self.scenarios_table.setRowCount(0)
        for example in self.examples:
            row = self.scenarios_table.rowCount()
            self.scenarios_table.insertRow(row)
            self.scenarios_table.setItem(row, 0, QTableWidgetItem(example.get('name', '')))
            self.scenarios_table.setItem(row, 1, QTableWidgetItem(", ".join(example.get('detected', []))))
            self.scenarios_table.setItem(row, 2, QTableWidgetItem(example.get('classification', '')))
            self.scenarios_table.setItem(row, 3, QTableWidgetItem(example.get('rule', '')))
            self.scenarios_table.setItem(row, 4, QTableWidgetItem(example.get('notes', '')))
    
    def populate_tree(self):
        self.tree.clear()
        # Start with root level (IncidentEnvironment)
        if "IncidentEnvironment" in self.classes_dict:
            root_item = self._build_tree_item(self.tree, "IncidentEnvironment", None)
            root_item.setExpanded(True)
        else:
            # Fallback: show all top-level items
            for main_class in self.classes_dict:
                item = self._build_tree_item(self.tree, main_class, None)
                item.setExpanded(True)
    
    def _build_tree_item(self, parent, class_name, parent_path):
        """Recursively build tree item and its children."""
        # Create the tree item
        if isinstance(parent, QTreeWidget):
            item = QTreeWidgetItem(parent, [class_name, ""])
        else:
            item = QTreeWidgetItem(parent, [class_name, ""])
        
        # Set path for identification
        if parent_path:
            full_path = f"{parent_path}:{class_name}"
        else:
            full_path = class_name
        item.setData(0, Qt.UserRole, full_path)
        
        # Add children if this class has subclasses
        if class_name in self.classes_dict:
            subclasses = self.classes_dict[class_name]
            if subclasses:
                for subclass in subclasses:
                    child_item = self._build_tree_item(item, subclass, full_path)
                    child_item.setExpanded(True)
        
        return item

    def _add_threat_rule(self, severity, table):
        """Add a new threat rule for a severity level."""
        text, ok = QInputDialog.getText(self, f"Add {severity} Rule", "Enter threat rule (e.g., 'flame + person_distress'):")
        if ok and text:
            text = text.strip()
            if severity not in self.threat_matrix:
                self.threat_matrix[severity] = []
            if text not in self.threat_matrix[severity]:
                self.threat_matrix[severity].append(text)
                # Refresh the table
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(text))
                action_btn = QPushButton("✎ ✗")
                action_btn.setMaximumWidth(50)
                action_btn.clicked.connect(lambda checked, s=severity, r=row, t=table: self._edit_threat_rule(s, r, t))
                table.setCellWidget(row, 1, action_btn)

    def _edit_threat_rule(self, severity, row, table):
        """Edit or remove a threat rule."""
        current_text = table.item(row, 0).text() if table.item(row, 0) else ""
        choice = QInputDialog.getItem(self, "Edit Rule", "Action:", ["Edit", "Remove"], 0)
        if choice == "Edit":
            text, ok = QInputDialog.getText(self, "Edit Rule", "Enter new rule:", text=current_text)
            if ok and text:
                text = text.strip()
                if severity in self.threat_matrix:
                    idx = self.threat_matrix[severity].index(current_text) if current_text in self.threat_matrix[severity] else row
                    if idx < len(self.threat_matrix[severity]):
                        self.threat_matrix[severity][idx] = text
                        table.item(row, 0).setText(text)
        elif choice == "Remove":
            if severity in self.threat_matrix and current_text in self.threat_matrix[severity]:
                self.threat_matrix[severity].remove(current_text)
            table.removeRow(row)

    def add_scenario(self):
        """Add a scenario."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Scenario")
        form = QFormLayout(dlg)
        
        name_edit = QLineEdit()
        form.addRow("Scenario Name", name_edit)
        
        detected_edit = QLineEdit()
        detected_edit.setPlaceholderText("comma-separated classes")
        form.addRow("Detected Classes", detected_edit)
        
        classification_edit = QLineEdit()
        form.addRow("Classification", classification_edit)
        
        rule_edit = QLineEdit()
        form.addRow("Rule", rule_edit)
        
        notes_edit = QLineEdit()
        form.addRow("Notes", notes_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        
        if dlg.exec_() == QDialog.Accepted:
            example = {
                "name": name_edit.text().strip(),
                "detected": [c.strip() for c in detected_edit.text().split(",") if c.strip()],
                "classification": classification_edit.text().strip(),
                "rule": rule_edit.text().strip(),
                "notes": notes_edit.text().strip(),
            }
            if example["name"]:
                self.examples.append(example)
                self.populate_scenarios()

    def populate_rules(self):
        self.rules_table.setRowCount(0)
        for rule in self.rules:
            row = self.rules_table.rowCount()
            self.rules_table.insertRow(row)
            self.rules_table.setItem(row, 0, QTableWidgetItem(rule.get('class', '')))
            self.rules_table.setItem(row, 1, QTableWidgetItem(",".join(rule.get('conditions', []))))
            self.rules_table.setItem(row, 2, QTableWidgetItem(rule.get('severity', '')))
            self.rules_table.setItem(row, 3, QTableWidgetItem(",".join(rule.get('mitigations', []))))
            self.rules_table.setItem(row, 4, QTableWidgetItem(rule.get('notes', '')))

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
        """Add a subclass to the selected class (supports 3-level hierarchy)."""
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Select a parent class first")
            return
        item = selected[0]
        parent_class = item.text(0)
        
        # Determine level (for guidance)
        level_name = "subclass"
        if parent_class == "IncidentEnvironment":
            level_name = "category (Level 2)"
        elif parent_class.endswith("_CATEGORY") or parent_class in ["ENVIRONMENT_MARKERS", "HUMAN_CATEGORY", "VEHICLE_CATEGORY", "SAFETY_CATEGORY", "STRUCTURAL_CATEGORY", "SMOKE_CATEGORY", "FIRE_CATEGORY"]:
            level_name = "detection class (Level 3)"
        
        text, ok = QInputDialog.getText(self, f"Add {level_name}", f"Enter {level_name} name for '{parent_class}':")
        if ok and text:
            text = text.strip()
            if text in self.classes_dict.get(parent_class, []):
                QMessageBox.warning(self, "Duplicate", f"'{text}' already exists under '{parent_class}'")
                return
            if parent_class not in self.classes_dict:
                self.classes_dict[parent_class] = []
            self.classes_dict[parent_class].append(text)
            self.populate_tree()
    
    def remove_selected(self):
        """Remove the selected class or subclass."""
        selected = self.tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        class_name = item.text(0)
        
        # Don't allow removing root
        if class_name == "IncidentEnvironment" and not item.parent():
            QMessageBox.warning(self, "Cannot Remove", "Cannot remove root IncidentEnvironment class")
            return
        
        if item.parent():
            parent_class = item.parent().text(0)
            if parent_class in self.classes_dict and class_name in self.classes_dict[parent_class]:
                self.classes_dict[parent_class].remove(class_name)
                # If this was also a category with children, remove its entry
                if class_name in self.classes_dict:
                    del self.classes_dict[class_name]
        else:
            if class_name in self.classes_dict:
                del self.classes_dict[class_name]
        self.populate_tree()

    def add_rule(self):
        rule = self._rule_dialog()
        if rule:
            self.rules.append(rule)
            self.populate_rules()

    def edit_rule(self):
        row = self.rules_table.currentRow()
        if row < 0:
            return
        existing = self.rules[row]
        updated = self._rule_dialog(existing)
        if updated:
            self.rules[row] = updated
            self.populate_rules()

    def remove_rule(self):
        row = self.rules_table.currentRow()
        if row < 0:
            return
        del self.rules[row]
        self.rules_table.removeRow(row)

    def _rule_dialog(self, existing=None):
        dlg = QDialog(self)
        dlg.setWindowTitle("Rule")
        form = QFormLayout(dlg)

        class_edit = QLineEdit(existing.get('class', '') if existing else '')
        form.addRow("Class", class_edit)

        cond_edit = QLineEdit(",".join(existing.get('conditions', [])) if existing else '')
        form.addRow("Conditions (comma)", cond_edit)

        sev_combo = QComboBox(); sev_combo.addItems(SEVERITIES)
        if existing:
            sev_combo.setCurrentText(existing.get('severity', 'MEDIUM'))
        else:
            sev_combo.setCurrentText('MEDIUM')
        form.addRow("Severity", sev_combo)

        mit_edit = QLineEdit(",".join(existing.get('mitigations', [])) if existing else '')
        form.addRow("Mitigations (comma)", mit_edit)

        notes_edit = QLineEdit(existing.get('notes', '') if existing else '')
        form.addRow("Notes", notes_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec_() == QDialog.Accepted:
            cls = class_edit.text().strip()
            if not cls:
                QMessageBox.warning(self, "Required", "Class is required")
                return None
            return {
                'class': cls,
                'conditions': [c.strip() for c in cond_edit.text().split(',') if c.strip()],
                'severity': sev_combo.currentText(),
                'mitigations': [m.strip() for m in mit_edit.text().split(',') if m.strip()],
                'notes': notes_edit.text().strip(),
            }
        return None

    def save_and_close(self):
        """Save configuration and close dialog."""
        # Warn if existing annotations may be impacted by taxonomy changes
        try:
            ann_root = get_data_path("annotations")
            impacted = 0
            if os.path.exists(ann_root):
                for root, dirs, files in os.walk(ann_root):
                    impacted += sum(1 for f in files if f.endswith('.txt') and f != 'labels.txt')
            if impacted > 0:
                msg = (
                    f"⚠️ {impacted} existing annotation files detected.\n\n"
                    "Changing classes may cause mismatches. EmberEye will temporarily remap any missing classes to\n"
                    "category-specific 'unclassified_*' during training. You can review and reassign after training.\n\n"
                    "Do you want to continue and save the new taxonomy?"
                )
                reply = QMessageBox.question(self, "Class Change Impact", msg, QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
        except Exception:
            pass

        ok_classes = save_master_classes(self.classes_dict)
        ok_rules = save_threat_rules(self.threat_matrix, self.examples, {
            'default_flame': self.default_flame_sev.currentText(),
            'default_smoke': self.default_smoke_sev.currentText(),
            'score_threshold': float(self.score_threshold_edit.text() or 0),
            'notes': self.notes_box.toPlainText(),
        })
        if ok_classes and ok_rules:
            QMessageBox.information(self, "Saved", "Taxonomy and rules saved")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to save configuration")
