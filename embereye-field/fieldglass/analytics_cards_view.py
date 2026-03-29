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
    """Interactive card used to display and manage marketplace analytic descriptors."""

    enabled_changed = pyqtSignal(str, bool)
    configure_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, descriptor, *, enabled: bool = False, parent: QWidget | None = None):
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
        toggle.setChecked(bool(enabled and license_state == "licensed"))
        toggle.setStyleSheet("color: #d4e9f3; font-size: 11px;")
        toggle.toggled.connect(lambda value: self.enabled_changed.emit(self.descriptor.analytic_id, bool(value)))
        layout.addWidget(toggle)

        action_row = QHBoxLayout()
        configure_btn = QPushButton("Configure")
        configure_btn.setEnabled(license_state == "licensed")
        configure_btn.clicked.connect(lambda: self.configure_requested.emit(self.descriptor.analytic_id))
        configure_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #24435a;"
            "border: 1px solid #356584;"
            "border-radius: 5px;"
            "padding: 4px 8px;"
            "color: #d4e9f3;"
            "font-size: 10px;"
            "font-weight: 600;"
            "}"
        )
        action_row.addWidget(configure_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.descriptor.analytic_id))
        remove_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #5a2c2c;"
            "border: 1px solid #7a3b3b;"
            "border-radius: 5px;"
            "padding: 4px 8px;"
            "color: #ffd8d1;"
            "font-size: 10px;"
            "font-weight: 600;"
            "}"
        )
        action_row.addWidget(remove_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        if descriptor.error_message:
            error_label = QLabel(descriptor.error_message)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #ffb0a7; font-size: 10px;")
            layout.addWidget(error_label)


class AnalyticsCardsView(QWidget):
    """Scrollable cards view backed by PluginManager descriptors."""

    refresh_requested = pyqtSignal()
    import_requested = pyqtSignal()
    analytic_enabled_changed = pyqtSignal(str, bool)
    analytic_configure_requested = pyqtSignal(str)
    analytic_remove_requested = pyqtSignal(str)

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

    def set_descriptors(self, descriptors: list, enabled_map: dict[str, bool] | None = None) -> None:
        self._clear_cards()
        enabled_map = enabled_map or {}

        sorted_descriptors = sorted(
            descriptors,
            key=lambda item: (item.metadata.name or item.analytic_id).lower(),
        )

        enabled_count = 0
        for descriptor in sorted_descriptors:
            if bool(enabled_map.get(descriptor.analytic_id, False)):
                enabled_count += 1

        self.summary_label.setText(
            f"Marketplace analytics: {len(sorted_descriptors)} (enabled: {enabled_count})"
        )

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
            card = AnalyticCardWidget(
                descriptor,
                enabled=bool(enabled_map.get(descriptor.analytic_id, False)),
            )
            card.enabled_changed.connect(self.analytic_enabled_changed.emit)
            card.configure_requested.connect(self.analytic_configure_requested.emit)
            card.remove_requested.connect(self.analytic_remove_requested.emit)
            self.cards_layout.addWidget(card, row, col)

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
