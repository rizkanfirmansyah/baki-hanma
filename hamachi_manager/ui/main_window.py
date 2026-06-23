from __future__ import annotations

import csv
from pathlib import Path
from time import monotonic

from openpyxl import Workbook
from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QCloseEvent, QFont, QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
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
    def __init__(self, app: QApplication, icon_path: Path) -> None:
        super().__init__()
        self.app = app
        self.logger = AppLogger()
        self.service = HamachiService(self.logger)
        self.current_status = HamachiStatus()
        self.current_networks: list[NetworkInfo] = []
        self.current_members: list[MemberInfo] = []
        self.external_processes: list[QProcess] = []
        self._close_to_tray_hint_shown = False
        self._allow_close = False
        self._traffic_interface: str | None = None
        self._traffic_manual_interface: str | None = None
        self._traffic_prev_sample: tuple[int, int, float] | None = None
        self._traffic_session_started_at: float | None = None
        self._traffic_total_download_bytes = 0
        self._traffic_total_upload_bytes = 0
        self._mtu_test_process: QProcess | None = None
        self._mtu_test_target_ip: str = ""
        self._mtu_test_target_name: str = ""
        self._mtu_test_queue: list[int] = []
        self._mtu_test_results: list[tuple[int, bool]] = []
        self._mtu_test_stdout = ""
        self._mtu_test_stderr = ""
        self.icon = (
            QIcon(str(icon_path))
            if icon_path.exists()
            else self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        )
        self.mono_font = QFont("DejaVu Sans Mono", 11)

        self.setWindowTitle("BAKI HANMA")
        self.setMinimumSize(1520, 980)
        self.setWindowIcon(self.icon)

        self._create_actions()
        self._build_ui()
        self._build_tray()
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
        self._poll_traffic_stats()
        self.service.refresh()

    def _create_actions(self) -> None:
        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setShortcut("Ctrl+R")
        self.refresh_action.triggered.connect(self._manual_refresh)

        self.reconnect_action = QAction("Reconnect", self)
        self.reconnect_action.triggered.connect(self.service.reconnect)

        self.login_action = QAction("Login", self)
        self.login_action.triggered.connect(self.service.login)

        self.logout_action = QAction("Logout", self)
        self.logout_action.triggered.connect(self.service.logout)

        self.attach_action = QAction("Attach", self)
        self.attach_action.triggered.connect(self._attach_account)

        self.detach_action = QAction("Detach", self)
        self.detach_action.triggered.connect(self.service.detach_account)

        self.join_action = QAction("Join", self)
        self.join_action.triggered.connect(self._join_network)

        self.leave_action = QAction("Leave", self)
        self.leave_action.triggered.connect(self._leave_network)

        self.nickname_action = QAction("Set Nickname", self)
        self.nickname_action.triggered.connect(self._set_nickname)

        self.set_mtu_action = QAction("Set MTU", self)
        self.set_mtu_action.triggered.connect(self._set_mtu)

        self.safe_profile_action = QAction("Apply Safe SSH/Web Profile", self)
        self.safe_profile_action.triggered.connect(self._apply_safe_mtu_profile)

        self.auto_mtu_test_action = QAction("Auto MTU Test", self)
        self.auto_mtu_test_action.triggered.connect(self._run_auto_mtu_test)

        self.step_down_mtu_action = QAction("Lower MTU Preset", self)
        self.step_down_mtu_action.triggered.connect(self._step_down_mtu)

        self.mtu_preset_actions: list[QAction] = []
        for mtu in self.service.available_mtu_presets():
            action = QAction(f"Use MTU {mtu}", self)
            action.triggered.connect(lambda _checked=False, value=mtu: self._apply_mtu_preset(value))
            self.mtu_preset_actions.append(action)

        self.export_csv_action = QAction("Export CSV", self)
        self.export_csv_action.triggered.connect(self._export_csv)

        self.export_excel_action = QAction("Export Excel", self)
        self.export_excel_action.triggered.connect(self._export_excel)

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self._exit_application)

        for action in (self.refresh_action, self.exit_action):
            self.addAction(action)

    def _build_ui(self) -> None:
        self.menuBar().hide()

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
        bar = QFrame(self)
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("BAKI HANMA", bar)
        title.setObjectName("TopTitle")
        subtitle = QLabel("Bash Kit Hamachi Network Manager", bar)
        subtitle.setObjectName("TopSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        layout.addLayout(title_col, 1)

        self.overview_chip = self._create_status_chip("Offline")
        self.attach_chip = self._create_status_chip("Detached")
        self.network_chip = self._create_status_chip("0 Networks")
        layout.addWidget(self.overview_chip)
        layout.addWidget(self.attach_chip)
        layout.addWidget(self.network_chip)

        layout.addWidget(self._make_nav_button("Login", self.login_action))
        layout.addWidget(self._make_nav_button("Refresh", self.refresh_action, primary=True))
        layout.addWidget(self._make_nav_button("Logout", self.logout_action))
        layout.addWidget(
            self._make_nav_dropdown(
                "More",
                [
                    self.reconnect_action,
                    self.join_action,
                    self.leave_action,
                    self.attach_action,
                    self.detach_action,
                    self.nickname_action,
                    None,
                    self.safe_profile_action,
                    self.auto_mtu_test_action,
                    self.step_down_mtu_action,
                    self._build_mtu_presets_menu(),
                    self.set_mtu_action,
                    None,
                    self.export_csv_action,
                    self.export_excel_action,
                ],
            )
        )
        layout.addWidget(self._make_nav_button("Exit", self.exit_action))
        return bar

    def _create_dashboard_row(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._create_dashboard_summary(), 3)
        layout.addWidget(self._create_traffic_panel(), 2)
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
        state_row.setSpacing(8)
        state_row.addWidget(self.status_indicator)
        state_row.addWidget(self.status_labels["online_state"])
        state_row.addStretch(1)

        layout.addWidget(online_label, len(fields), 0)
        layout.addLayout(state_row, len(fields), 1)
        return group

    def _create_traffic_panel(self) -> QWidget:
        self.traffic_widget = TrafficMonitorWidget(self)
        return self.traffic_widget

    def _create_status_chip(self, text: str) -> QLabel:
        chip = QLabel(text, self)
        chip.setObjectName("StatusChip")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return chip

    def _make_nav_button(self, text: str, action: QAction, primary: bool = False) -> QPushButton:
        button = QPushButton(text, self)
        button.clicked.connect(action.trigger)
        if primary:
            button.setObjectName("PrimaryButton")
        return button

    def _make_nav_dropdown(self, title: str, actions: list[QAction | QMenu | None]) -> QToolButton:
        button = QToolButton(self)
        button.setText(title)
        button.setObjectName("ToolbarDropButton")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for action in actions:
            if action is None:
                menu.addSeparator()
            elif isinstance(action, QMenu):
                menu.addMenu(action)
            else:
                menu.addAction(action)
        button.setMenu(menu)
        return button

    def _build_mtu_presets_menu(self) -> QMenu:
        menu = QMenu("MTU Presets", self)
        for action in self.mtu_preset_actions:
            menu.addAction(action)
        return menu

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
        layout.setSpacing(8)

        self.network_count_label = QLabel("No network loaded", group)
        self.network_count_label.setObjectName("MutedLabel")
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
        layout.setSpacing(8)

        self.notes_panel = QPlainTextEdit(group)
        self.notes_panel.setReadOnly(True)
        self.notes_panel.setPlaceholderText("Operational notes and selected network details will appear here.")
        self.notes_panel.setMinimumHeight(150)
        layout.addWidget(self.notes_panel)
        return group

    def _create_member_panel(self) -> QWidget:
        group = QGroupBox("Members", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        self.member_count_label = QLabel("Select a network to load members", group)
        self.member_count_label.setObjectName("MutedLabel")
        header_row.addWidget(self.member_count_label)
        header_row.addStretch(1)

        self.member_search_input = QLineEdit(group)
        self.member_search_input.setPlaceholderText(
            "Search nickname, IP, endpoint, status, client ID, or connection type"
        )
        self.member_search_input.setClearButtonEnabled(True)
        self.member_search_input.setMinimumWidth(360)
        self.member_search_input.setMinimumHeight(40)
        self.member_search_input.textChanged.connect(self._apply_member_filter)
        header_row.addWidget(self.member_search_input)

        export_csv_button = QPushButton("Export CSV", group)
        export_csv_button.clicked.connect(self._export_csv)
        export_xlsx_button = QPushButton("Export Excel", group)
        export_xlsx_button.clicked.connect(self._export_excel)
        header_row.addWidget(export_csv_button)
        header_row.addWidget(export_xlsx_button)
        layout.addLayout(header_row)

        self.member_route_label = QLabel("", group)
        self.member_route_label.setObjectName("MutedLabel")
        layout.addWidget(self.member_route_label)

        self.member_table = QTableWidget(0, 8, group)
        self.member_table.setHorizontalHeaderLabels(
            [
                "Nickname",
                "IPv4",
                "IPv6",
                "Status",
                "Direct / Relay",
                "Endpoint",
                "Client ID",
                "Connection Type",
            ]
        )
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
        self.member_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.member_table.customContextMenuRequested.connect(self._show_member_menu)
        self.member_table.itemSelectionChanged.connect(self._on_member_selected)
        layout.addWidget(self.member_table)
        return group

    def _create_logs_area(self) -> QWidget:
        group = QGroupBox("Live Logs", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        self.log_panel = LogPanel(self.logger, group)
        self.log_panel.output.setObjectName("LogOutput")
        self.log_panel.output.setMinimumHeight(240)
        self.command_console = CommandConsole(group)
        layout.addWidget(self.log_panel, 1)
        layout.addWidget(self.command_console)
        return group

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        tray_menu = QMenu(self)

        show_action = QAction("Show", self)
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)
        tray_menu.addAction(self.refresh_action)
        tray_menu.addAction(self.reconnect_action)
        tray_menu.addSeparator()
        tray_menu.addAction(self.exit_action)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setToolTip("BAKI HANMA")
        self.tray.show()

    def _connect_signals(self) -> None:
        self.command_console.command_submitted.connect(self.service.run_raw_command)
        self.service.status_updated.connect(self._update_dashboard)
        self.service.networks_updated.connect(self._populate_networks)
        self.service.members_updated.connect(self._populate_members)
        self.service.error_occurred.connect(self._show_error)
        self.service.notification_requested.connect(self._notify)
        self.traffic_widget.interface_changed.connect(self._on_traffic_interface_changed)

    def _configure_table(self, table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def _set_chip_state(self, chip: QLabel, text: str) -> None:
        chip.setText(text)
        lowered = text.lower()
        if any(token in lowered for token in ("online", "direct", "attached")):
            style = "background-color: #173b2a; color: #7ee787;"
        elif any(token in lowered for token in ("offline", "detached", "error")):
            style = "background-color: #3d1d22; color: #ff7b72;"
        elif any(token in lowered for token in ("relay", "pending", "connecting")):
            style = "background-color: #4d3b1f; color: #e3b341;"
        else:
            style = "background-color: #162033; color: #c9d1d9;"
        chip.setStyleSheet(style)

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
        self._set_chip_state(self.overview_chip, state_text)
        self._set_chip_state(self.attach_chip, status.attach_status)
        self._update_notes()

    def _populate_networks(self, networks: list[NetworkInfo]) -> None:
        previous_network_id = self._selected_network_id()
        self.current_networks = networks
        self.network_table.setRowCount(len(networks))
        self.network_count_label.setText(f"{len(networks)} network loaded")
        self.network_chip.setText(f"{len(networks)} Networks")

        for row, network in enumerate(networks):
            values = [network.name, network.network_id, network.owner, network.status]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 1:
                    item.setFont(self.mono_font)
                if col == 3:
                    self._style_status_item(item, network.status)
                self.network_table.setItem(row, col, item)

        if not networks:
            self.member_table.setRowCount(0)
            self.network_count_label.setText("No network loaded")
            self.member_count_label.setText("Select a network to load members")
            self.network_chip.setText("0 Networks")
            self._apply_member_filter()
            self._update_notes()
            return

        target_network = previous_network_id or self.service.selected_network_id or networks[0].network_id
        self._select_network_row(target_network)
        self._update_notes()

    def _populate_members(self, members: list[MemberInfo]) -> None:
        selected_client_id = self._selected_member_id()
        self.current_members = members
        self.member_table.setRowCount(len(members))

        for row, member in enumerate(members):
            values = [
                member.nickname,
                member.ipv4,
                member.ipv6,
                "Online" if member.online else "Offline",
                member.direct_state,
                member.endpoint_ip,
                member.client_id,
                member.connection_type,
            ]
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

        if selected_client_id:
            self._select_member_row(selected_client_id)

        self._apply_member_filter()
        self._update_notes()

    def _update_notes(self) -> None:
        lines = [
            "Announcement",
            "",
            "Use the Members table to inspect peer IP addresses, endpoint routing, and direct/relay state quickly.",
        ]

        selected_network = self._selected_network()
        if selected_network:
            lines.extend(
                [
                    "",
                    f"Selected Network: {selected_network.name}",
                    f"Network ID: {selected_network.network_id}",
                    f"Owner: {selected_network.owner}",
                    f"Capacity: {selected_network.capacity}",
                    f"Subscription: {selected_network.subscription_type}",
                    f"Status: {selected_network.status}",
                ]
            )

        if self.current_status.account != "-":
            lines.extend(["", f"Account: {self.current_status.account}"])
        if self.current_status.attach_status != "Unknown":
            lines.append(f"Attach State: {self.current_status.attach_status}")
        lines.append(f"Preferred Hamachi MTU: {self.service.preferred_mtu()}")
        relay_count = sum(1 for member in self.current_members if "relay" in member.direct_state.lower())
        direct_count = sum(1 for member in self.current_members if "direct" in member.direct_state.lower())
        if self.current_members:
            lines.append(f"Member Route Summary: {direct_count} direct, {relay_count} relay")
            if relay_count:
                lines.append("Warning: relay routing can keep peers connected while SSH/web throughput becomes unstable.")
        if self._traffic_interface:
            lines.append(f"Traffic Interface In Use: {self._traffic_interface}")
            lines.append(
                f"Traffic Session Totals: up {self._format_bytes(self._traffic_total_upload_bytes)}, down {self._format_bytes(self._traffic_total_download_bytes)}"
            )
        lines.append(f"Traffic Monitor Selection: {self._traffic_manual_interface or 'Auto (preferred)'}")

        lines.extend(
            [
                "",
                "Tips",
                "- Watch the traffic chart for upload/download spikes.",
                "- Use the command console to run hamachi list, hamachi peer, or reconnect flows.",
                "- Logs remain live while commands execute.",
            ]
        )
        self.notes_panel.setPlainText("\n".join(lines))

    def _selected_network(self) -> NetworkInfo | None:
        network_id = self._selected_network_id()
        for network in self.current_networks:
            if network.network_id == network_id:
                return network
        return None

    def _poll_traffic_stats(self) -> None:
        counters = self._read_netdev_counters()
        preferred_interfaces = self._preferred_traffic_interfaces(counters)
        selected_interface = self._resolve_selected_traffic_interface(counters)
        self.traffic_widget.set_interface_choices(preferred_interfaces, self._traffic_manual_interface)

        interface_changed = selected_interface != self._traffic_interface
        self._traffic_interface = selected_interface
        if interface_changed:
            self._traffic_prev_sample = None
            self._traffic_session_started_at = None
            self._traffic_total_download_bytes = 0
            self._traffic_total_upload_bytes = 0

        if not selected_interface:
            self._traffic_prev_sample = None
            self._traffic_session_started_at = None
            self._traffic_total_download_bytes = 0
            self._traffic_total_upload_bytes = 0
            self.traffic_widget.reset_metrics(None)
            self._update_notes()
            return

        rx_bytes, tx_bytes = counters[selected_interface]
        now = monotonic()
        previous = self._traffic_prev_sample
        self._traffic_prev_sample = (rx_bytes, tx_bytes, now)
        if previous is None:
            self._traffic_session_started_at = now
            self.traffic_widget.reset_metrics(selected_interface)
            self._update_notes()
            return

        prev_rx, prev_tx, prev_time = previous
        elapsed = max(now - prev_time, 0.001)
        delta_download_bytes = max(rx_bytes - prev_rx, 0)
        delta_upload_bytes = max(tx_bytes - prev_tx, 0)
        self._traffic_total_download_bytes += delta_download_bytes
        self._traffic_total_upload_bytes += delta_upload_bytes

        if self._traffic_session_started_at is None:
            self._traffic_session_started_at = prev_time
        session_elapsed = max(now - self._traffic_session_started_at, 0.001)

        download_mbps = max(delta_download_bytes * 8 / elapsed / 1_000_000, 0.0)
        upload_mbps = max(delta_upload_bytes * 8 / elapsed / 1_000_000, 0.0)
        average_download_mbps = max(self._traffic_total_download_bytes * 8 / session_elapsed / 1_000_000, 0.0)
        average_upload_mbps = max(self._traffic_total_upload_bytes * 8 / session_elapsed / 1_000_000, 0.0)
        self.traffic_widget.update_metrics(
            upload_mbps,
            download_mbps,
            selected_interface,
            self._traffic_total_upload_bytes,
            self._traffic_total_download_bytes,
            average_upload_mbps,
            average_download_mbps,
        )

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
            name = name_part.strip()
            fields = stats_part.split()
            if len(fields) < 16:
                continue
            rx_bytes = int(fields[0])
            tx_bytes = int(fields[8])
            counters[name] = (rx_bytes, tx_bytes)
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

        fallback_interfaces = [
            name
            for name in counters
            if not name.startswith(("lo", "docker", "veth", "br-", "virbr", "ifb"))
        ]
        return fallback_interfaces[0] if fallback_interfaces else None

    def _on_traffic_interface_changed(self, interface_name: str) -> None:
        self._traffic_manual_interface = interface_name or None
        self._traffic_prev_sample = None
        self._poll_traffic_stats()

    @staticmethod
    def _format_bytes(value_bytes: int) -> str:
        value = float(max(value_bytes, 0))
        units = ["B", "KB", "MB", "GB", "TB"]
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        if unit in {"B", "KB"}:
            return f"{value:.0f} {unit}"
        return f"{value:.2f} {unit}"

    def _apply_member_filter(self) -> None:
        query = self.member_search_input.text().strip().lower() if hasattr(self, "member_search_input") else ""
        visible_count = 0
        relay_count = 0
        direct_count = 0
        offline_count = 0

        for row, member in enumerate(self.current_members):
            haystack = " | ".join(
                [
                    member.nickname,
                    member.ipv4,
                    member.ipv6,
                    "Online" if member.online else "Offline",
                    member.direct_state,
                    member.endpoint_ip,
                    member.client_id,
                    member.connection_type,
                ]
            ).lower()
            matched = not query or query in haystack
            self.member_table.setRowHidden(row, not matched)
            if not matched:
                continue
            visible_count += 1
            lowered_route = member.direct_state.lower()
            if "relay" in lowered_route:
                relay_count += 1
            elif "direct" in lowered_route:
                direct_count += 1
            if not member.online:
                offline_count += 1

        if not self.current_members:
            self.member_count_label.setText("No member found for the selected network")
            self.member_route_label.clear()
        elif query:
            self.member_count_label.setText(
                f"{visible_count} of {len(self.current_members)} member match the current search"
            )
        else:
            self.member_count_label.setText(
                f"{len(self.current_members)} member visible in the selected network"
            )

        if self.current_members:
            if relay_count:
                self.member_route_label.setText(
                    f"Relay warning: {relay_count} visible member use relayed routing. SSH/web throughput may become unstable."
                )
                self.member_route_label.setStyleSheet("color: #e3b341; font-weight: 600;")
            else:
                self.member_route_label.setText(
                    f"Path summary: {direct_count} direct, {offline_count} offline, Preferred MTU {self.service.preferred_mtu()}"
                )
                self.member_route_label.setStyleSheet("color: #7ee787; font-weight: 600;")

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
        else:
            item.setForeground(QColor("#c9d1d9"))

    def _selected_network_id(self) -> str:
        row = self.network_table.currentRow()
        if row < 0:
            return ""
        item = self.network_table.item(row, 1)
        return item.text() if item else ""

    def _selected_member_id(self) -> str:
        row = self.member_table.currentRow()
        if row < 0:
            return ""
        item = self.member_table.item(row, 6)
        return item.text() if item else ""

    def _select_network_row(self, network_id: str) -> None:
        for row in range(self.network_table.rowCount()):
            item = self.network_table.item(row, 1)
            if item and item.text() == network_id:
                self.network_table.selectRow(row)
                return

    def _select_member_row(self, client_id: str) -> None:
        for row in range(self.member_table.rowCount()):
            item = self.member_table.item(row, 6)
            if item and item.text() == client_id:
                self.member_table.selectRow(row)
                return

    def _on_network_selected(self) -> None:
        network_id = self._selected_network_id()
        if network_id:
            self.service.get_members(network_id)
        self._update_notes()

    def _on_member_selected(self) -> None:
        client_id = self._selected_member_id()
        if client_id:
            self.service.get_peer_detail(client_id)

    def _show_member_menu(self, position) -> None:
        row = self.member_table.currentRow()
        if row < 0:
            return

        member = self.current_members[row]
        menu = QMenu(self)
        ping_action = menu.addAction("Ping Member")
        copy_ip_action = menu.addAction("Copy Hamachi IP")
        copy_client_id_action = menu.addAction("Copy Client ID")
        ssh_action = menu.addAction("SSH to Host")

        chosen = menu.exec(self.member_table.viewport().mapToGlobal(position))
        if chosen == ping_action:
            self._ping_member(member)
        elif chosen == copy_ip_action:
            QGuiApplication.clipboard().setText(member.ipv4)
            self.logger.log(f"Copied Hamachi IP: {member.ipv4}")
        elif chosen == copy_client_id_action:
            QGuiApplication.clipboard().setText(member.client_id)
            self.logger.log(f"Copied Client ID: {member.client_id}")
        elif chosen == ssh_action:
            self._ssh_to_member(member)

    def _ping_member(self, member: MemberInfo) -> None:
        if member.ipv4 == "-":
            self._show_error("Ping Error", "Selected member does not have a Hamachi IPv4 address.")
            return
        self._start_logged_process("ping", ["-c", "4", member.ipv4], f"ping -c 4 {member.ipv4}")

    def _ssh_to_member(self, member: MemberInfo) -> None:
        if member.ipv4 == "-":
            self._show_error("SSH Error", "Selected member does not have a Hamachi IPv4 address.")
            return

        user, accepted = QInputDialog.getText(self, "SSH Username", "SSH username:")
        if not accepted or not user.strip():
            return
        target = f"{user.strip()}@{member.ipv4}"
        terminals = [
            ("x-terminal-emulator", ["-e", "ssh", target]),
            ("gnome-terminal", ["--", "ssh", target]),
            ("konsole", ["-e", "ssh", target]),
            ("xfce4-terminal", ["-e", f"ssh {target}"]),
            ("xterm", ["-e", "ssh", target]),
        ]
        for program, args in terminals:
            if QProcess.startDetached(program, args):
                self.logger.log(f"Launching SSH session: ssh {target}")
                return
        self._show_error("SSH Error", "No supported terminal emulator was found for launching SSH.")

    def _start_logged_process(self, program: str, args: list[str], label: str) -> None:
        process = QProcess(self)
        self.external_processes.append(process)
        stdout_buffer = {"data": ""}
        stderr_buffer = {"data": ""}

        process.readyReadStandardOutput.connect(
            lambda: self._append_external_output(process, stdout_buffer, "stdout")
        )
        process.readyReadStandardError.connect(
            lambda: self._append_external_output(process, stderr_buffer, "stderr")
        )
        process.finished.connect(lambda code, _status: self._external_finished(process, label, code))

        self.logger.log(f"Executing: {label}")
        process.start(program, args)

    def _append_external_output(self, process: QProcess, buffer: dict[str, str], stream: str) -> None:
        if stream == "stdout":
            chunk = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        else:
            chunk = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
        buffer["data"] += chunk
        self.logger.log(chunk)

    def _external_finished(self, process: QProcess, label: str, code: int) -> None:
        self.logger.log(f"External command finished ({code}): {label}")
        if process in self.external_processes:
            self.external_processes.remove(process)
        process.deleteLater()

    def _manual_refresh(self) -> None:
        self.service.refresh(self._selected_network_id())

    def _auto_refresh(self) -> None:
        self.service.refresh(self._selected_network_id())

    def _attach_account(self) -> None:
        account, accepted = QInputDialog.getText(self, "Attach Account", "LogMeIn account email:")
        if accepted and account.strip():
            self.service.attach_account(account.strip())

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

    def _set_mtu(self) -> None:
        mtu, accepted = QInputDialog.getInt(
            self,
            "Set Hamachi MTU",
            "Preferred MTU for Hamachi tuning:",
            self.service.preferred_mtu(),
            1000,
            1450,
            1,
        )
        if not accepted:
            return
        self.service.set_preferred_mtu(mtu, apply_now=True)
        self._update_notes()
        self._apply_member_filter()

    def _apply_mtu_preset(self, mtu: int) -> None:
        self.service.set_preferred_mtu(mtu, apply_now=True)
        self._update_notes()
        self._apply_member_filter()

    def _apply_safe_mtu_profile(self) -> None:
        mtu = self.service.apply_safe_web_profile()
        self.logger.log(f"Safe SSH/web profile selected: MTU {mtu}")
        self._update_notes()
        self._apply_member_filter()

    def _run_auto_mtu_test(self) -> None:
        if self._mtu_test_process is not None:
            self._show_error("Auto MTU Test", "An MTU test is already running.")
            return

        row = self.member_table.currentRow()
        if row < 0 or row >= len(self.current_members):
            self._show_error("Auto MTU Test", "Select a member with a Hamachi IPv4 address first.")
            return

        member = self.current_members[row]
        if member.ipv4 == "-":
            self._show_error("Auto MTU Test", "Selected member does not have a Hamachi IPv4 address.")
            return

        preferred = self.service.preferred_mtu()
        lower_presets = [mtu for mtu in self.service.available_mtu_presets() if mtu < preferred]
        sequence = [preferred, *lower_presets]
        deduped: list[int] = []
        for mtu in sequence:
            if mtu not in deduped:
                deduped.append(mtu)

        self._mtu_test_target_ip = member.ipv4
        self._mtu_test_target_name = member.nickname
        self._mtu_test_queue = deduped
        self._mtu_test_results = []
        self.logger.log(
            f"Starting Auto MTU Test for {member.nickname} ({member.ipv4}) with presets: {', '.join(str(mtu) for mtu in deduped)}"
        )
        self._start_next_mtu_test()

    def _start_next_mtu_test(self) -> None:
        if not self._mtu_test_queue:
            self._finish_auto_mtu_test()
            return

        mtu = self._mtu_test_queue.pop(0)
        payload_size = max(mtu - 28, 0)
        self._mtu_test_stdout = ""
        self._mtu_test_stderr = ""
        process = QProcess(self)
        self._mtu_test_process = process
        process.setProgram("ping")
        process.setArguments(["-c", "2", "-W", "2", "-M", "do", "-s", str(payload_size), self._mtu_test_target_ip])
        process.readyReadStandardOutput.connect(self._handle_mtu_test_stdout)
        process.readyReadStandardError.connect(self._handle_mtu_test_stderr)
        process.finished.connect(lambda code, _status, test_mtu=mtu: self._handle_mtu_test_finished(test_mtu, code))
        self.logger.log(
            f"Executing: ping -c 2 -W 2 -M do -s {payload_size} {self._mtu_test_target_ip} (MTU {mtu})"
        )
        process.start()

    def _handle_mtu_test_stdout(self) -> None:
        if not self._mtu_test_process:
            return
        chunk = bytes(self._mtu_test_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._mtu_test_stdout += chunk
        self.logger.log(chunk)

    def _handle_mtu_test_stderr(self) -> None:
        if not self._mtu_test_process:
            return
        chunk = bytes(self._mtu_test_process.readAllStandardError()).decode("utf-8", errors="replace")
        self._mtu_test_stderr += chunk
        self.logger.log(chunk)

    def _handle_mtu_test_finished(self, mtu: int, exit_code: int) -> None:
        combined = "\n".join(part for part in (self._mtu_test_stdout, self._mtu_test_stderr) if part).strip()
        success = exit_code == 0 and "100% packet loss" not in combined.lower()
        self._mtu_test_results.append((mtu, success))

        process = self._mtu_test_process
        self._mtu_test_process = None
        if process is not None:
            process.deleteLater()

        if success:
            self.logger.log(f"Auto MTU Test success with MTU {mtu}; applying profile.")
            self.service.set_preferred_mtu(mtu, apply_now=True)
            self._update_notes()
            self._apply_member_filter()
            self._finish_auto_mtu_test(success_mtu=mtu)
            return

        self.logger.log(f"Auto MTU Test failed with MTU {mtu}; trying next preset if available.")
        self._start_next_mtu_test()

    def _finish_auto_mtu_test(self, success_mtu: int | None = None) -> None:
        target_label = f"{self._mtu_test_target_name} ({self._mtu_test_target_ip})" if self._mtu_test_target_ip else "selected peer"
        results_summary = ", ".join(
            f"{mtu}:{'ok' if ok else 'fail'}" for mtu, ok in self._mtu_test_results
        ) or "no tests executed"
        self.logger.log(f"Auto MTU Test completed for {target_label}: {results_summary}")
        if success_mtu is not None:
            QMessageBox.information(
                self,
                "Auto MTU Test",
                f"Best working MTU for {target_label}: {success_mtu}\n\nResults: {results_summary}",
            )
        else:
            self._show_error(
                "Auto MTU Test",
                f"No tested MTU preset succeeded for {target_label}.\n\nResults: {results_summary}",
            )
        self._mtu_test_target_ip = ""
        self._mtu_test_target_name = ""
        self._mtu_test_queue = []
        self._mtu_test_stdout = ""
        self._mtu_test_stderr = ""

    def _step_down_mtu(self) -> None:
        mtu = self.service.step_down_mtu(apply_now=True)
        self.logger.log(f"Lower MTU preset applied: MTU {mtu}")
        self._update_notes()
        self._apply_member_filter()

    def _export_csv(self) -> None:
        if not self.current_members:
            self._show_error("Export Error", "There are no members to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Members to CSV",
            "hamachi_members.csv",
            "CSV Files (*.csv)",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Nickname",
                    "IPv4",
                    "IPv6",
                    "Status",
                    "Direct / Relay",
                    "Endpoint",
                    "Client ID",
                    "Connection Type",
                ]
            )
            for member in self.current_members:
                writer.writerow(
                    [
                        member.nickname,
                        member.ipv4,
                        member.ipv6,
                        "Online" if member.online else "Offline",
                        member.direct_state,
                        member.endpoint_ip,
                        member.client_id,
                        member.connection_type,
                    ]
                )
        self.logger.log(f"Member list exported to CSV: {path}")

    def _export_excel(self) -> None:
        if not self.current_members:
            self._show_error("Export Error", "There are no members to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Members to Excel",
            "hamachi_members.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Members"
        sheet.append(
            [
                "Nickname",
                "IPv4",
                "IPv6",
                "Status",
                "Direct / Relay",
                "Endpoint",
                "Client ID",
                "Connection Type",
            ]
        )
        for member in self.current_members:
            sheet.append(
                [
                    member.nickname,
                    member.ipv4,
                    member.ipv6,
                    "Online" if member.online else "Offline",
                    member.direct_state,
                    member.endpoint_ip,
                    member.client_id,
                    member.connection_type,
                ]
            )
        workbook.save(path)
        self.logger.log(f"Member list exported to Excel: {path}")

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _notify(self, title: str, message: str) -> None:
        self.logger.log(message)
        if self.tray.isVisible():
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_application(self) -> None:
        self._allow_close = True
        self.refresh_timer.stop()
        self.traffic_timer.stop()
        self.tray.hide()
        self.close()
        self.app.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close or QApplication.closingDown():
            event.accept()
            return
        if self.tray.isVisible():
            event.ignore()
            self.hide()
            if not self._close_to_tray_hint_shown:
                self.tray.showMessage(
                    "BAKI HANMA",
                    "Application is still running in the system tray. Use Ctrl+Q or top Exit to quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
                self._close_to_tray_hint_shown = True
            return
        event.accept()
