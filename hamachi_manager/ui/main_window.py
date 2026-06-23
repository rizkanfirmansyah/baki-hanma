from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hamachi_manager.models import HamachiStatus, MemberInfo, NetworkInfo
from hamachi_manager.services.hamachi_service import HamachiService
from hamachi_manager.services.logger import AppLogger
from hamachi_manager.widgets.command_console import CommandConsole
from hamachi_manager.widgets.log_panel import LogPanel


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication | None = None, icon_path: Path | None = None) -> None:
        super().__init__()
        self.app = app
        self.logger = AppLogger()
        self.service = HamachiService(self.logger)
        self.current_status = HamachiStatus()
        self.current_networks: list[NetworkInfo] = []
        self.current_members: list[MemberInfo] = []
        self.mono_font = QFont("DejaVu Sans Mono", 10)
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setWindowTitle("BAKI HANMA")
        self.resize(1380, 900)

        self._build_ui()
        self._connect_signals()
        self.service.refresh()

    def _build_ui(self) -> None:
        central = QWidget(self)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        main_layout.addWidget(self._create_toolbar())
        main_layout.addWidget(self._create_dashboard())

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._create_workspace())
        splitter.addWidget(self._create_logs())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 320])
        main_layout.addWidget(splitter, 1)

        self.setCentralWidget(central)

    def _create_toolbar(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("BAKI HANMA", container)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        subtitle = QLabel("Core Hamachi dashboard", container)
        subtitle.setStyleSheet("color: #94a3b8;")
        title_col = QVBoxLayout()
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        layout.addLayout(title_col, 1)

        for label, handler in [
            ("Refresh", self._manual_refresh),
            ("Login", self.service.login),
            ("Logout", self.service.logout),
            ("Join", self._join_network),
            ("Leave", self._leave_network),
            ("Set Nickname", self._set_nickname),
        ]:
            button = QPushButton(label, container)
            button.clicked.connect(handler)
            layout.addWidget(button)
        return container

    def _create_dashboard(self) -> QWidget:
        group = QGroupBox("Dashboard", self)
        layout = QGridLayout(group)
        self.status_labels: dict[str, QLabel] = {}
        fields = [
            ("Version", "hamachi_status"),
            ("Login Status", "login_status"),
            ("Client ID", "client_id"),
            ("Nickname", "nickname"),
            ("IPv4", "ipv4"),
            ("IPv6", "ipv6"),
            ("Account", "account"),
            ("Attach Status", "attach_status"),
        ]
        for row, (label, key) in enumerate(fields):
            layout.addWidget(QLabel(label, group), row, 0)
            value = QLabel("-", group)
            value.setWordWrap(True)
            self.status_labels[key] = value
            layout.addWidget(value, row, 1)
        return group

    def _create_workspace(self) -> QWidget:
        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._create_networks(), 2)
        layout.addWidget(self._create_members(), 4)
        return widget

    def _create_networks(self) -> QWidget:
        group = QGroupBox("Networks", self)
        layout = QVBoxLayout(group)
        self.network_count = QLabel("No network loaded", group)
        layout.addWidget(self.network_count)
        self.network_table = QTableWidget(0, 3, group)
        self.network_table.setHorizontalHeaderLabels(["Name", "Network ID", "Status"])
        self._configure_table(self.network_table)
        header = self.network_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.network_table.itemSelectionChanged.connect(self._on_network_selected)
        layout.addWidget(self.network_table)
        return group

    def _create_members(self) -> QWidget:
        group = QGroupBox("Members", self)
        layout = QVBoxLayout(group)
        self.member_count = QLabel("Select a network to load members", group)
        layout.addWidget(self.member_count)
        self.member_table = QTableWidget(0, 6, group)
        self.member_table.setHorizontalHeaderLabels(["Nickname", "IPv4", "IPv6", "Status", "Direct / Relay", "Client ID"])
        self._configure_table(self.member_table)
        header = self.member_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.member_table)
        return group

    def _create_logs(self) -> QWidget:
        group = QGroupBox("Live Logs", self)
        layout = QVBoxLayout(group)
        self.log_panel = LogPanel(self.logger, group)
        self.command_console = CommandConsole(group)
        layout.addWidget(self.log_panel, 1)
        layout.addWidget(self.command_console)
        return group

    def _connect_signals(self) -> None:
        self.command_console.command_submitted.connect(self.service.run_raw_command)
        self.service.status_updated.connect(self._update_dashboard)
        self.service.networks_updated.connect(self._populate_networks)
        self.service.members_updated.connect(self._populate_members)
        self.service.error_occurred.connect(self._show_error)

    def _configure_table(self, table: QTableWidget) -> None:
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)

    def _update_dashboard(self, status: HamachiStatus) -> None:
        self.current_status = status
        self.status_labels["hamachi_status"].setText(status.version)
        self.status_labels["login_status"].setText(status.login_status)
        self.status_labels["client_id"].setText(status.client_id)
        self.status_labels["nickname"].setText(status.nickname)
        self.status_labels["ipv4"].setText(status.ipv4)
        self.status_labels["ipv6"].setText(status.ipv6)
        self.status_labels["account"].setText(status.account)
        self.status_labels["attach_status"].setText(status.attach_status)

    def _populate_networks(self, networks: list[NetworkInfo]) -> None:
        self.current_networks = networks
        self.network_table.setRowCount(len(networks))
        self.network_count.setText(f"{len(networks)} network loaded")
        for row, network in enumerate(networks):
            for col, value in enumerate([network.name, network.network_id, network.status]):
                item = QTableWidgetItem(value)
                if col == 1:
                    item.setFont(self.mono_font)
                self.network_table.setItem(row, col, item)
        if networks and self.network_table.currentRow() < 0:
            self.network_table.selectRow(0)
            self.service.get_members(networks[0].network_id)

    def _populate_members(self, members: list[MemberInfo]) -> None:
        self.current_members = members
        self.member_table.setRowCount(len(members))
        self.member_count.setText(f"{len(members)} member loaded")
        for row, member in enumerate(members):
            values = [member.nickname, member.ipv4, member.ipv6, "Online" if member.online else "Offline", member.direct_state, member.client_id]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in {1, 2, 5}:
                    item.setFont(self.mono_font)
                if col == 3:
                    self._style_status_item(item, value)
                if col == 4:
                    self._style_status_item(item, member.direct_state)
                self.member_table.setItem(row, col, item)

    def _style_status_item(self, item: QTableWidgetItem, status: str) -> None:
        lowered = status.lower()
        if lowered in {"online", "direct"}:
            item.setBackground(QColor("#173b2a"))
            item.setForeground(QColor("#7ee787"))
        elif lowered == "offline":
            item.setBackground(QColor("#3d1d22"))
            item.setForeground(QColor("#ff7b72"))
        elif lowered == "relay":
            item.setBackground(QColor("#4d3b1f"))
            item.setForeground(QColor("#e3b341"))

    def _selected_network_id(self) -> str:
        row = self.network_table.currentRow()
        if row < 0:
            return ""
        item = self.network_table.item(row, 1)
        return item.text() if item else ""

    def _manual_refresh(self) -> None:
        self.service.refresh(self._selected_network_id())

    def _on_network_selected(self) -> None:
        network_id = self._selected_network_id()
        if network_id:
            self.service.get_members(network_id)

    def _join_network(self) -> None:
        network_id, accepted = QInputDialog.getText(self, "Join Network", "Network ID:")
        if not accepted or not network_id.strip():
            return
        password, _ = QInputDialog.getText(self, "Join Network", "Network password (optional):")
        self.service.join_network(network_id.strip(), password)

    def _leave_network(self) -> None:
        network_id = self._selected_network_id()
        if not network_id:
            self._show_error("Leave Network", "Select a network first.")
            return
        self.service.leave_network(network_id)

    def _set_nickname(self) -> None:
        nickname, accepted = QInputDialog.getText(self, "Set Nickname", "New nickname:")
        if accepted and nickname.strip():
            self.service.set_nickname(nickname.strip())

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
