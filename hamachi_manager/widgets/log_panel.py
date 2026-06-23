from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget

from hamachi_manager.services.logger import AppLogger


class LogPanel(QWidget):
    def __init__(self, logger: AppLogger, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.logger = logger
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)

        clear_button = QPushButton("Clear Log", self)
        clear_button.clicked.connect(self._clear)

        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.output)

        self.logger.log_added.connect(self._append_entry)

    def _append_entry(self, entry: str) -> None:
        if not entry:
            self.output.clear()
            return
        self.output.appendPlainText(entry)
        scrollbar = self.output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear(self) -> None:
        self.logger.clear()
