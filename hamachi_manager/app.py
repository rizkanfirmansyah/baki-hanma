from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from hamachi_manager.styles.dark_theme import APP_STYLE
from hamachi_manager.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BAKI HANMA")
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()
    return app.exec()
