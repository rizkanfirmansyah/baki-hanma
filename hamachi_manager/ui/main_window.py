from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BAKI HANMA")
        self.resize(1200, 780)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)

        hero = QFrame(self)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(10)

        title = QLabel("BAKI HANMA", hero)
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Bash Kit Hamachi Network Manager", hero)
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)

        body = QLabel(
            "Initial native desktop scaffold for a future Hamachi monitoring dashboard on Linux.",
            hero,
        )
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        hero_layout.addWidget(body)
        layout.addWidget(hero)
        layout.addStretch(1)

        self.setCentralWidget(central)
