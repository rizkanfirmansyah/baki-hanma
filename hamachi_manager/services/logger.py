from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal


class AppLogger(QObject):
    log_added = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[str] = []

    def log(self, message: str) -> None:
        for line in self._normalize_lines(message):
            entry = f"[{datetime.now().strftime('%H:%M:%S')}] {line}"
            self._entries.append(entry)
            self.log_added.emit(entry)

    def entries(self) -> list[str]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self.log_added.emit("")

    @staticmethod
    def _normalize_lines(message: str) -> list[str]:
        stripped = message.rstrip()
        if not stripped:
            return []
        return [line for line in stripped.splitlines() if line.strip()]
