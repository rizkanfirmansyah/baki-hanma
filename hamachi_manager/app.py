from __future__ import annotations

import os
import sys
from pathlib import Path

if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from hamachi_manager.styles.dark_theme import APP_STYLE
from hamachi_manager.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BAKI HANMA")
    app.setDesktopFileName("baki-hanma")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(APP_STYLE)

    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    icon_candidates = [
        project_root / "logo.png",
        package_dir / "icons" / "hamachi_manager.svg",
    ]
    icon_path = next((candidate for candidate in icon_candidates if candidate.exists()), icon_candidates[-1])
    app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(app, icon_path)
    window.show()

    return app.exec()
