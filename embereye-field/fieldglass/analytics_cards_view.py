from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QCheckBox,
    QScrollArea,
    QGridLayout,
)


class AnalyticCardWidget(QFrame):
    """Minimal card used to display marketplace analytic descriptors."""

    def __init__(self, descriptor, parent: QWidget | None = None):
        super().__init__(parent)
        self.descriptor = descriptor

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("AnalyticCardWidget")
        self.setStyleSheet(
            "QFrame#AnalyticCardWidget {"
            "background-color: #162330;"
            "border: 1px solid #2f4d63;"
            "border-radius: 8px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel(descriptor.metadata.name)
        title.setStyleSheet("color: #d4e9f3; font-size: 13px; font-weight: 700;")
        layout.addWidget(title)

        version = QLabel(f"Version: {descriptor.metadata.version}")
        version.setStyleSheet("color: #9db6c5; font-size: 11px;")
        layout.addWidget(version)

        license_state = str(descriptor.license_status).strip().lower()
        license_label_text = "Licensed" if license_state == "licensed" else "Unlicensed"
        license_color = "#78d486" if license_state == "licensed" else "#f08b7e"

        license_label = QLabel(f"License: {license_label_text}")
        license_label.setStyleSheet(f"color: {license_color}; font-size: 11px; font-weight: 600;")
        layout.addWidget(license_label)

        toggle = QCheckBox("Enabled")
        toggle.setEnabled(license_state == "licensed")
        toggle.setChecked(False)
        toggle.setStyleSheet("color: #d4e9f3; font-size: 11px;")
        layout.addWidget(toggle)

        if descriptor.error_message:
            error_label = QLabel(descriptor.error_message)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #ffb0a7; font-size: 10px;")
            layout.addWidget(error_label)


class AnalyticsCardsView(QWidget):
    """Scrollable cards view backed by PluginManager descriptors."""

    refresh_requested = pyqtSignal()
    import_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_bar = QHBoxLayout()
        self.summary_label = QLabel("Marketplace analytics: 0")
        self.summary_label.setStyleSheet("color: #9db6c5; font-size: 12px; font-weight: 600;")
        top_bar.addWidget(self.summary_label)
        top_bar.addStretch(1)

        refresh_button = QPushButton("Rescan Marketplace")
        refresh_button.clicked.connect(self.refresh_requested.emit)
        refresh_button.setStyleSheet(
            "QPushButton {"
            "background-color: #24435a;"
            "border: 1px solid #356584;"
            "border-radius: 6px;"
            "padding: 6px 12px;"
            "color: #d4e9f3;"
            "font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "background-color: #2c4f69;"
            "}"
        )
        top_bar.addWidget(refresh_button)

        import_button = QPushButton("Import Analytics")
        import_button.clicked.connect(self.import_requested.emit)
        import_button.setStyleSheet(
            "QPushButton {"
            "background-color: #375f2f;"
            "border: 1px solid #4d7f40;"
            "border-radius: 6px;"
            "padding: 6px 12px;"
            "color: #d4f3d1;"
            "font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "background-color: #42753a;"
            "}"
        )
        top_bar.addWidget(import_button)
        root.addLayout(top_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_host = QWidget()
        self.cards_layout = QGridLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(10)
        self.cards_layout.setVerticalSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll)

    def set_descriptors(self, descriptors: list) -> None:
        self._clear_cards()

        sorted_descriptors = sorted(
            descriptors,
            key=lambda item: (item.metadata.name or item.analytic_id).lower(),
        )

        self.summary_label.setText(f"Marketplace analytics: {len(sorted_descriptors)}")

        if not sorted_descriptors:
            empty = QLabel("No .eapkg packages detected in the marketplace folder.")
            empty.setStyleSheet("color: #8fa7b6; font-size: 12px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.addWidget(empty, 0, 0)
            return

        column_count = 2
        for index, descriptor in enumerate(sorted_descriptors):
            row = index // column_count
            col = index % column_count
            self.cards_layout.addWidget(AnalyticCardWidget(descriptor), row, col)

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
