from __future__ import annotations


APP_STYLE = """
QWidget {
    background-color: #0d1117;
    color: #e5e7eb;
    font-family: "DejaVu Sans";
    font-size: 13px;
}
QMainWindow, QMenuBar, QMenu, QStatusBar {
    background-color: #0d1117;
    color: #e5e7eb;
}
QFrame#TopBar, QFrame#TrafficCard {
    background-color: #111827;
    border: 1px solid #263041;
    border-radius: 12px;
}
QLabel#TopTitle {
    color: #f8fafc;
    font-size: 18px;
    font-weight: 700;
}
QLabel#TopSubtitle, QLabel#MutedLabel, QLabel#TrafficMeta {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#SectionTitle {
    color: #f8fafc;
    font-size: 15px;
    font-weight: 600;
}
QLabel#ValueLabel {
    color: #f8fafc;
    font-weight: 600;
}
QLabel#PromptLabel {
    background-color: #0f172a;
    border: 1px solid #263041;
    border-radius: 8px;
    padding: 9px 12px;
    color: #93c5fd;
    font-weight: 600;
}
QLabel#StatusChip {
    border-radius: 10px;
    padding: 7px 10px;
    min-width: 82px;
    font-weight: 600;
    background-color: #162033;
    color: #c9d1d9;
}
QLabel#TrafficUpload {
    color: #38bdf8;
    font-weight: 600;
}
QLabel#TrafficDownload {
    color: #22c55e;
    font-weight: 600;
}
QLabel#TrafficTrend {
    color: #f8fafc;
    font-weight: 600;
}
QGroupBox {
    border: 1px solid #263041;
    border-radius: 12px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
    background-color: #111827;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #93c5fd;
}
QPushButton, QToolButton {
    background-color: #162033;
    color: #f8fafc;
    border: 1px solid #2a3950;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 18px;
    min-width: 92px;
}
QPushButton:hover, QToolButton:hover {
    background-color: #1d2b40;
    border-color: #39557c;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #142133;
}
QPushButton#PrimaryButton {
    background-color: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
}
QPushButton#PrimaryButton:hover {
    background-color: #3b82f6;
    border-color: #3b82f6;
}
QLineEdit, QPlainTextEdit, QTableWidget {
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #263041;
    border-radius: 8px;
    selection-background-color: #1d4ed8;
    selection-color: #f8fafc;
}
QLineEdit#CommandInput {
    padding: 0 12px;
    font-size: 14px;
}
QPlainTextEdit {
    padding: 8px;
}
QPlainTextEdit#LogOutput {
    font-family: "DejaVu Sans Mono";
    font-size: 12px;
}
QHeaderView::section {
    background-color: #111827;
    color: #93c5fd;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #263041;
}
QTableCornerButton::section {
    background-color: #111827;
    border: none;
}
QTableWidget {
    gridline-color: #1f2937;
    alternate-background-color: #101826;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #0f172a;
    border: none;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #334155;
    border-radius: 6px;
    min-height: 24px;
    min-width: 24px;
}
QMenu {
    background-color: #111827;
    border: 1px solid #263041;
    padding: 4px;
}
QMenu::item {
    padding: 8px 12px;
}
QMenu::item:selected, QMenuBar::item:selected {
    background-color: #1f2937;
}
QSplitter::handle {
    background-color: #1f2937;
}
"""
