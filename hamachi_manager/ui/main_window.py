from __future__ import annotations

import csv
from pathlib import Path
from time import monotonic

from openpyxl import Workbook
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
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
from hamachi_manager.widgets.status_indicator import StatusIndicator
from hamachi_manager.widgets.traffic_monitor import TrafficMonitorWidget


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication | None = None, icon_path: Path | None = None) -> None:
        super().__init__()
        self.app = app
        self.logger = AppLogger()
        self.service = HamachiService(self.logger)
        self.current_status = HamachiStatus()
        self.current_networks: list[NetworkInfo] = []
        self.current_members: list[MemberInfo] = []
        self._traffic_interface: str | None = None
        self._traffic_manual_interface: str | None = None
        self._traffic_prev_sample: tuple[int, int, float] | None = None
        self.mono_font = QFont("DejaVu Sans Mono", 10)
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setWindowTitle("BAKI HANMA")
        self.setMinimumSize(1450, 920)

        self._build_ui()
        self._connect_signals()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start()

        self.traffic_timer = QTimer(self)
        self.traffic_timer.setInterval(1000)
        self.traffic_timer.timeout.connect(self._poll_traffic_stats)
        self.traffic_timer.start()

        self._update_notes()
        self.service.refresh()

    def _build_ui(self) -> None:
        central = QWidget(self)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        main_layout.addWidget(self._create_top_bar())
        main_layout.addWidget(self._create_dashboard_row())

        workspace_splitter = QSplitter(Qt.Orientation.Vertical, central)
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.addWidget(self._create_workspace_area())
        workspace_splitter.addWidget(self._create_logs_area())
        workspace_splitter.setStretchFactor(0, 7)
        workspace_splitter.setStretchFactor(1, 4)
        workspace_splitter.setSizes([620, 360])
        main_layout.addWidget(workspace_splitter, 1)

        self.setCentralWidget(central)

    def _create_top_bar(self) -> QWidget:
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title_col = QVBoxLayout()
        title = QLabel("BAKI HANMA", bar)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        subtitle = QLabel("Broad native Hamachi monitoring dashboard", bar)
        subtitle.setStyleSheet("color: #94a3b8;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        layout.addLayout(title_col, 1)

        for label, handler, primary in [
            ("Login", self.service.login, False),
            ("Refresh", self._manual_refresh, True),
            ("Logout", self.service.logout, False),
            ("Join", self._join_network, False),
            ("Leave", self._leave_network, False),
            ("Set Nickname", self._set_nickname, False),
        ]:
            button = QPushButton(label, bar)
            if primary:
                button.setObjectName("PrimaryButton")
            button.clicked.connect(handler)
            layout.addWidget(button)
        return bar

    def _create_dashboard_row(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._create_dashboard_summary(), 3)
        self.traffic_widget = TrafficMonitorWidget(self)
        layout.addWidget(self.traffic_widget, 2)
        return container

    def _create_dashboard_summary(self) -> QWidget:
        group = QGroupBox("Dashboard", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(22)
        layout.setVerticalSpacing(10)
        self.status_indicator = StatusIndicator(group)
        self.status_labels: dict[str, QLabel] = {}
        fields = [
            ("Hamachi Status", "hamachi_status"),
            ("Login Status", "login_status"),
            ("Client ID", "client_id"),
            ("Nickname", "nickname"),
            ("Hamachi IPv4", "ipv4"),
            ("Hamachi IPv6", "ipv6"),
            ("LogMeIn Account", "account"),
            ("Attach Status", "attach_status"),
        ]
        for row, (label_text, key) in enumerate(fields):
            label = QLabel(label_text, group)
            value = QLabel("-", group)
            value.setObjectName("ValueLabel")
            value.setWordWrap(True)
            self.status_labels[key] = value
            layout.addWidget(label, row, 0)
            layout.addWidget(value, row, 1)
        online_label = QLabel("Online State", group)
        self.status_labels["online_state"] = QLabel("Offline", group)
        self.status_labels["online_state"].setObjectName("ValueLabel")
        state_row = QHBoxLayout()
        state_row.addWidget(self.status_indicator)
        state_row.addWidget(self.status_labels["online_state"])
        state_row.addStretch(1)
        layout.addWidget(online_label, len(fields), 0)
        layout.addLayout(state_row, len(fields), 1)
        return group

    def _create_workspace_area(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal, container)
        splitter.setChildrenCollapsible(False)
        left_splitter = QSplitter(Qt.Orientation.Vertical, splitter)
        left_splitter.setChildrenCollapsible(False)
        left_splitter.addWidget(self._create_network_panel())
        left_splitter.addWidget(self._create_notes_panel())
        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 2)
        left_splitter.setSizes([430, 220])
        splitter.addWidget(left_splitter)
        splitter.addWidget(self._create_member_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([380, 1120])
        layout.addWidget(splitter)
        return container

    def _create_network_panel(self) -> QWidget:
        group = QGroupBox("Networks", self)
        layout = QVBoxLayout(group)
        self.network_count_label = QLabel("No network loaded", group)
        layout.addWidget(self.network_count_label)
        self.network_table = QTableWidget(0, 4, group)
        self.network_table.setHorizontalHeaderLabels(["Network Name", "Network ID", "Owner", "Status"])
        self._configure_table(self.network_table)
        header = self.network_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.network_table.itemSelectionChanged.connect(self._on_network_selected)
        layout.addWidget(self.network_table)
        return group

    def _create_notes_panel(self) -> QWidget:
        group = QGroupBox("Notes / Announcement", self)
        layout = QVBoxLayout(group)
        self.notes_panel = QPlainTextEdit(group)
        self.notes_panel.setReadOnly(True)
        self.notes_panel.setMinimumHeight(150)
        layout.addWidget(self.notes_panel)
        return group

    def _create_member_panel(self) -> QWidget:
        group = QGroupBox("Members", self)
        layout = QVBoxLayout(group)
        header_row = QHBoxLayout()
        self.member_count_label = QLabel("Select a network to load members", group)
        header_row.addWidget(self.member_count_label)
        header_row.addStretch(1)
        export_csv_button = QPushButton("Export CSV", group)
        export_csv_button.clicked.connect(self._export_csv)
        export_xlsx_button = QPushButton("Export Excel", group)
        export_xlsx_button.clicked.connect(self._export_excel)
        header_row.addWidget(export_csv_button)
        header_row.addWidget(export_xlsx_button)
        layout.addLayout(header_row)
        self.member_table = QTableWidget(0, 8, group)
        self.member_table.setHorizontalHeaderLabels(["Nickname", "IPv4", "IPv6", "Status", "Direct / Relay", "Endpoint", "Client ID", "Connection Type"])
        self._configure_table(self.member_table)
        header = self.member_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.member_table)
        return group

    def _create_logs_area(self) -> QWidget:
        group = QGroupBox("Live Logs", self)
        layout = QVBoxLayout(group)
        self.log_panel = LogPanel(self.logger, group)
        self.log_panel.output.setMinimumHeight(240)
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
        self.traffic_widget.interface_changed.connect(self._on_traffic_interface_changed)

    def _configure_table(self, table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)

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
        state_text = "Online" if status.online else "Offline"
        self.status_labels["online_state"].setText(state_text)
        self.status_indicator.set_state(state_text)
        self._update_notes()

    def _populate_networks(self, networks: list[NetworkInfo]) -> None:
        self.current_networks = networks
        self.network_table.setRowCount(len(networks))
        self.network_count_label.setText(f"{len(networks)} network loaded")
        for row, network in enumerate(networks):
            values = [network.name, network.network_id, network.owner, network.status]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 1:
                    item.setFont(self.mono_font)
                if col == 3:
                    self._style_status_item(item, value)
                self.network_table.setItem(row, col, item)
        if networks and self.network_table.currentRow() < 0:
            self.network_table.selectRow(0)
            self.service.get_members(networks[0].network_id)
        self._update_notes()

    def _populate_members(self, members: list[MemberInfo]) -> None:
        self.current_members = members
        self.member_table.setRowCount(len(members))
        self.member_count_label.setText(f"{len(members)} member visible in the selected network")
        for row, member in enumerate(members):
            values = [member.nickname, member.ipv4, member.ipv6, "Online" if member.online else "Offline", member.direct_state, member.endpoint_ip, member.client_id, member.connection_type]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col in {1, 2, 5, 6}:
                    item.setFont(self.mono_font)
                if col == 3:
                    self._style_status_item(item, value)
                if col == 4:
                    self._style_status_item(item, member.direct_state)
                self.member_table.setItem(row, col, item)
        self._update_notes()

    def _update_notes(self) -> None:
        lines = [
            "Announcement",
            "",
            "Use the Members table to inspect peer IP addresses, endpoint routing, and direct/relay state quickly.",
        ]
        if self.current_status.account != "-":
            lines.extend(["", f"Account: {self.current_status.account}"])
        if self.current_networks:
            selected = self.current_networks[0]
            lines.extend(["", f"Selected Network: {selected.name}", f"Network ID: {selected.network_id}"])
        if self._traffic_interface:
            lines.append(f"Traffic Interface In Use: {self._traffic_interface}")
        lines.append(f"Traffic Monitor Selection: {self._traffic_manual_interface or 'Auto (preferred)'}")
        lines.extend(["", "Tips", "- Watch the traffic chart for upload/download spikes.", "- Use the command console to run hamachi list or reconnect flows."])
        self.notes_panel.setPlainText("\n".join(lines))

    def _poll_traffic_stats(self) -> None:
        counters = self._read_netdev_counters()
        preferred_interfaces = self._preferred_traffic_interfaces(counters)
        selected_interface = self._resolve_selected_traffic_interface(counters)
        self.traffic_widget.set_interface_choices(preferred_interfaces, self._traffic_manual_interface)
        self._traffic_interface = selected_interface

        if not selected_interface:
            self._traffic_prev_sample = None
            self.traffic_widget.reset_metrics(None)
            self._update_notes()
            return

        rx_bytes, tx_bytes = counters[selected_interface]
        now = monotonic()
        previous = self._traffic_prev_sample
        self._traffic_prev_sample = (rx_bytes, tx_bytes, now)
        if previous is None:
            self.traffic_widget.reset_metrics(selected_interface)
            self._update_notes()
            return
        prev_rx, prev_tx, prev_time = previous
        elapsed = max(now - prev_time, 0.001)
        download_mbps = max((rx_bytes - prev_rx) * 8 / elapsed / 1_000_000, 0.0)
        upload_mbps = max((tx_bytes - prev_tx) * 8 / elapsed / 1_000_000, 0.0)
        self.traffic_widget.update_metrics(upload_mbps, download_mbps, selected_interface)

    def _read_netdev_counters(self) -> dict[str, tuple[int, int]]:
        counters: dict[str, tuple[int, int]] = {}
        try:
            with open("/proc/net/dev", "r", encoding="utf-8") as handle:
                lines = handle.readlines()[2:]
        except OSError:
            return counters
        for line in lines:
            if ":" not in line:
                continue
            name_part, stats_part = line.split(":", 1)
            fields = stats_part.split()
            if len(fields) < 16:
                continue
            counters[name_part.strip()] = (int(fields[0]), int(fields[8]))
        return counters

    def _preferred_traffic_interfaces(self, counters: dict[str, tuple[int, int]]) -> list[str]:
        preferred: list[str] = []
        for candidate in ("ham0", "hamachi", "tun0"):
            if candidate in counters and candidate not in preferred:
                preferred.append(candidate)
        for name in sorted(counters):
            if name.startswith(("lo", "docker", "veth", "br-", "virbr", "ifb")):
                continue
            if name not in preferred:
                preferred.append(name)
        return preferred

    def _resolve_selected_traffic_interface(self, counters: dict[str, tuple[int, int]]) -> str | None:
        if self._traffic_manual_interface:
            if self._traffic_manual_interface in counters:
                if self._traffic_prev_sample and self._traffic_interface != self._traffic_manual_interface:
                    self._traffic_prev_sample = None
                return self._traffic_manual_interface
            self._traffic_prev_sample = None
            return None

        auto_interface = self._select_auto_traffic_interface(counters)
        if self._traffic_prev_sample and self._traffic_interface != auto_interface:
            self._traffic_prev_sample = None
        return auto_interface

    def _select_auto_traffic_interface(self, counters: dict[str, tuple[int, int]]) -> str | None:
        if self._traffic_interface in counters and self._traffic_interface in {"ham0", "hamachi", "tun0"}:
            return self._traffic_interface
        for candidate in ("ham0", "hamachi", "tun0"):
            if candidate in counters:
                return candidate
        fallback = [name for name in counters if not name.startswith(("lo", "docker", "veth", "br-", "virbr", "ifb"))]
        return fallback[0] if fallback else None

    def _on_traffic_interface_changed(self, interface_name: str) -> None:
        self._traffic_manual_interface = interface_name or None
        self._traffic_prev_sample = None
        self._poll_traffic_stats()

    def _style_status_item(self, item: QTableWidgetItem, status: str) -> None:
        lowered = status.lower()
        if lowered in {"online", "direct"}:
            item.setBackground(QColor("#173b2a"))
            item.setForeground(QColor("#7ee787"))
        elif lowered == "offline":
            item.setBackground(QColor("#3d1d22"))
            item.setForeground(QColor("#ff7b72"))
        elif lowered in {"relay", "pending"}:
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

    def _auto_refresh(self) -> None:
        self.service.refresh(self._selected_network_id())

    def _on_network_selected(self) -> None:
        network_id = self._selected_network_id()
        if network_id:
            self.service.get_members(network_id)
        self._update_notes()

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

    def _export_csv(self) -> None:
        if not self.current_members:
            self._show_error("Export Error", "There are no members to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Members to CSV", "hamachi_members.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Nickname", "IPv4", "IPv6", "Status", "Direct / Relay", "Endpoint", "Client ID", "Connection Type"])
            for member in self.current_members:
                writer.writerow([member.nickname, member.ipv4, member.ipv6, "Online" if member.online else "Offline", member.direct_state, member.endpoint_ip, member.client_id, member.connection_type])

    def _export_excel(self) -> None:
        if not self.current_members:
            self._show_error("Export Error", "There are no members to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Members to Excel", "hamachi_members.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Members"
        sheet.append(["Nickname", "IPv4", "IPv6", "Status", "Direct / Relay", "Endpoint", "Client ID", "Connection Type"])
        for member in self.current_members:
            sheet.append([member.nickname, member.ipv4, member.ipv6, "Online" if member.online else "Offline", member.direct_state, member.endpoint_ip, member.client_id, member.connection_type])
        workbook.save(path)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
