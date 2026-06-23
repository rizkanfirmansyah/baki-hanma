from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class StatusIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#f1c40f")
        self._state = "unknown"
        self.setFixedSize(QSize(18, 18))
        self.setToolTip("Unknown")

    def set_state(self, state: str) -> None:
        lowered = state.lower()
        if lowered == "online":
            self._color = QColor("#3fb950")
        elif lowered == "offline":
            self._color = QColor("#f85149")
        elif lowered == "relay":
            self._color = QColor("#d29922")
        else:
            self._color = QColor("#8b949e")
        self._state = state
        self.setToolTip(state.title())
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(1, 1, 16, 16)
