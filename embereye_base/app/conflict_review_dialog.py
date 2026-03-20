from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QMessageBox, QFileDialog, QLabel, QComboBox
)
import json


class ConflictReviewDialog(QDialog):
    def __init__(self, parent=None, class_conflicts=None, ann_conflicts=None):
        super().__init__(parent)
        self.setWindowTitle("Conflicts Review")
        self.resize(800, 500)
        self.class_conflicts = class_conflicts or {}
        self.ann_conflicts = ann_conflicts or {}
        self._build_ui()
        self._resolutions = {"classes": {"moved": [], "deleted_in_incoming": []}, "annotations": {"duplicates": [], "disagreements": []}}

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Classes tab
        cls_tab = QWidget()
        cls_layout = QVBoxLayout(cls_tab)
        moved_tbl = QTableWidget(0, 4)
        moved_tbl.setHorizontalHeaderLabels(["Name", "From", "To", "Resolution"])
        for item in self.class_conflicts.get("moved", []):
            r = moved_tbl.rowCount()
            moved_tbl.insertRow(r)
            moved_tbl.setItem(r, 0, QTableWidgetItem(item.get("name", "")))
            moved_tbl.setItem(r, 1, QTableWidgetItem(item.get("from", "")))
            moved_tbl.setItem(r, 2, QTableWidgetItem(item.get("to", "")))
            combo = QComboBox()
            combo.addItems(["Local", "Incoming"])  # default Local (keep current)
            moved_tbl.setCellWidget(r, 3, combo)
        del_tbl = QTableWidget(0, 2)
        del_tbl.setHorizontalHeaderLabels(["Deleted (incoming)", "Resolution"])
        for item in self.class_conflicts.get("deleted_in_incoming", []):
            r = del_tbl.rowCount()
            del_tbl.insertRow(r)
            del_tbl.setItem(r, 0, QTableWidgetItem(item.get("name", "")))
            combo = QComboBox()
            combo.addItems(["Ignore", "Apply"])  # default Ignore
            del_tbl.setCellWidget(r, 1, combo)
        dup_lbl = QLabel(f"Duplicate class names (incoming): {len(self.class_conflicts.get('duplicates', []))}")
        cls_layout.addWidget(QLabel("Moved Classes"))
        cls_layout.addWidget(moved_tbl)
        cls_layout.addWidget(QLabel("Incoming Tombstones"))
        cls_layout.addWidget(del_tbl)
        cls_layout.addWidget(dup_lbl)

        # Annotations tab
        ann_tab = QWidget()
        ann_layout = QVBoxLayout(ann_tab)
        dup_tbl = QTableWidget(0, 6)
        dup_tbl.setHorizontalHeaderLabels(["Media", "Image", "Class", "x", "y", "w/h", "Resolution"])
        for item in self.ann_conflicts.get("duplicates", []):
            r = dup_tbl.rowCount()
            dup_tbl.insertRow(r)
            dup_tbl.setItem(r, 0, QTableWidgetItem(item.get("media_base", "")))
            dup_tbl.setItem(r, 1, QTableWidgetItem(item.get("image", "")))
            dup_tbl.setItem(r, 2, QTableWidgetItem(item.get("class", "")))
            bbox = item.get("bbox", [0, 0, 0, 0])
            dup_tbl.setItem(r, 3, QTableWidgetItem(f"{bbox[0]:.3f}"))
            dup_tbl.setItem(r, 4, QTableWidgetItem(f"{bbox[1]:.3f}"))
            dup_tbl.setItem(r, 5, QTableWidgetItem(f"{bbox[2]:.3f}/{bbox[3]:.3f}"))
            combo = QComboBox()
            combo.addItems(["Local", "Incoming"])  # default Local
            dup_tbl.setCellWidget(r, 6, combo)
        dis_tbl = QTableWidget(0, 6)
        dis_tbl.setHorizontalHeaderLabels(["Media", "Image", "Incoming Class", "x", "y", "w/h", "Resolution"])
        for item in self.ann_conflicts.get("disagreements", []):
            r = dis_tbl.rowCount()
            dis_tbl.insertRow(r)
            dis_tbl.setItem(r, 0, QTableWidgetItem(item.get("media_base", "")))
            dis_tbl.setItem(r, 1, QTableWidgetItem(item.get("image", "")))
            dis_tbl.setItem(r, 2, QTableWidgetItem(item.get("incoming_class", "")))
            bbox = item.get("bbox", [0, 0, 0, 0])
            dis_tbl.setItem(r, 3, QTableWidgetItem(f"{bbox[0]:.3f}"))
            dis_tbl.setItem(r, 4, QTableWidgetItem(f"{bbox[1]:.3f}"))
            dis_tbl.setItem(r, 5, QTableWidgetItem(f"{bbox[2]:.3f}/{bbox[3]:.3f}"))
            combo = QComboBox()
            combo.addItems(["Local", "Incoming"])  # default Local
            dis_tbl.setCellWidget(r, 6, combo)
        ann_layout.addWidget(QLabel("Duplicates"))
        ann_layout.addWidget(dup_tbl)
        ann_layout.addWidget(QLabel("Disagreements"))
        ann_layout.addWidget(dis_tbl)

        tabs.addTab(cls_tab, "Classes")
        tabs.addTab(ann_tab, "Annotations")
        layout.addWidget(tabs)

        btns = QHBoxLayout()
        save_btn = QPushButton("Save Report…")
        proceed_btn = QPushButton("Proceed")
        cancel_btn = QPushButton("Cancel")
        btns.addWidget(save_btn)
        btns.addStretch(1)
        btns.addWidget(proceed_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        def save_report():
            path, _ = QFileDialog.getSaveFileName(self, "Save Conflicts Report", "conflicts_report.json", "JSON (*.json)")
            if not path:
                return
            try:
                payload = {"classes": self.class_conflicts, "annotations": self.ann_conflicts}
                with open(path, "w") as f:
                    json.dump(payload, f, indent=2)
                QMessageBox.information(self, "Saved", f"Report written to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Save failed: {e}")

        save_btn.clicked.connect(save_report)
        def collect_resolutions_and_accept():
            # Classes moved
            for r in range(moved_tbl.rowCount()):
                name = moved_tbl.item(r, 0).text() if moved_tbl.item(r, 0) else ""
                from_cat = moved_tbl.item(r, 1).text() if moved_tbl.item(r, 1) else ""
                to_cat = moved_tbl.item(r, 2).text() if moved_tbl.item(r, 2) else ""
                combo = moved_tbl.cellWidget(r, 3)
                res = combo.currentText() if combo else "Local"
                self._resolutions["classes"]["moved"].append({"name": name, "from": from_cat, "to": to_cat, "resolution": res.lower()})
            # Classes tombstones
            for r in range(del_tbl.rowCount()):
                name = del_tbl.item(r, 0).text() if del_tbl.item(r, 0) else ""
                combo = del_tbl.cellWidget(r, 1)
                res = combo.currentText() if combo else "Ignore"
                self._resolutions["classes"]["deleted_in_incoming"].append({"name": name, "resolution": res.lower()})
            # Annotation duplicates
            for r in range(dup_tbl.rowCount()):
                media = dup_tbl.item(r, 0).text() if dup_tbl.item(r, 0) else ""
                image = dup_tbl.item(r, 1).text() if dup_tbl.item(r, 1) else ""
                cls = dup_tbl.item(r, 2).text() if dup_tbl.item(r, 2) else ""
                # Bbox cells 3,4,5 contain x, y and w/h respectively
                try:
                    x = float(dup_tbl.item(r, 3).text())
                    y = float(dup_tbl.item(r, 4).text())
                    wh = dup_tbl.item(r, 5).text()
                    w, h = [float(v) for v in wh.split("/")]
                except Exception:
                    x, y, w, h = 0.0, 0.0, 0.0, 0.0
                combo = dup_tbl.cellWidget(r, 6)
                res = combo.currentText() if combo else "Local"
                self._resolutions["annotations"]["duplicates"].append({"media_base": media, "image": image, "class": cls, "bbox": [x, y, w, h], "resolution": res.lower()})
            # Annotation disagreements
            for r in range(dis_tbl.rowCount()):
                media = dis_tbl.item(r, 0).text() if dis_tbl.item(r, 0) else ""
                image = dis_tbl.item(r, 1).text() if dis_tbl.item(r, 1) else ""
                cls = dis_tbl.item(r, 2).text() if dis_tbl.item(r, 2) else ""
                try:
                    x = float(dis_tbl.item(r, 3).text())
                    y = float(dis_tbl.item(r, 4).text())
                    wh = dis_tbl.item(r, 5).text()
                    w, h = [float(v) for v in wh.split("/")]
                except Exception:
                    x, y, w, h = 0.0, 0.0, 0.0, 0.0
                combo = dis_tbl.cellWidget(r, 6)
                res = combo.currentText() if combo else "Local"
                self._resolutions["annotations"]["disagreements"].append({"media_base": media, "image": image, "incoming_class": cls, "bbox": [x, y, w, h], "resolution": res.lower()})
            self.accept()

        proceed_btn.clicked.connect(collect_resolutions_and_accept)
        cancel_btn.clicked.connect(self.reject)

    def get_resolutions(self):
        return self._resolutions
