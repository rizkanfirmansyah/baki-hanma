from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QStyle, QVBoxLayout, QWidget


class CommandConsole(QWidget):
    command_submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Command Console", self)
        title.setObjectName("SectionTitle")
        subtitle = QLabel("Run Hamachi commands and inspect results instantly in the logs below.", self)
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        row.setSpacing(10)

        prompt = QLabel("hamachi", self)
        prompt.setObjectName("PromptLabel")

        self.input = QLineEdit(self)
        self.input.setObjectName("CommandInput")
        self.input.setMinimumHeight(44)
        self.input.setPlaceholderText("Type command, for example: hamachi list")
        self.input.returnPressed.connect(self._submit)

        run_button = QPushButton("Run Command", self)
        run_button.setObjectName("PrimaryButton")
        run_button.setMinimumHeight(44)
        run_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        run_button.clicked.connect(self._submit)

        row.addWidget(prompt)
        row.addWidget(self.input, 1)
        row.addWidget(run_button)
        layout.addLayout(row)

    def _submit(self) -> None:
        command = self.input.text().strip()
        if not command:
            return
        self.command_submitted.emit(command)
        self.input.clear()
