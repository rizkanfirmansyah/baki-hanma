from __future__ import annotations

import shlex
from collections import deque
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from hamachi_manager.models import HamachiStatus, MemberInfo, NetworkInfo
from hamachi_manager.services.logger import AppLogger
from hamachi_manager.services.parser import HamachiParser


@dataclass(slots=True)
class CommandTask:
    args: list[str]
    label: str
    parser_key: str | None = None
    refresh_after: bool = False
    meta: dict[str, str] = field(default_factory=dict)


class HamachiService(QObject):
    status_updated = pyqtSignal(object)
    networks_updated = pyqtSignal(list)
    members_updated = pyqtSignal(list)
    peer_updated = pyqtSignal(object)
    error_occurred = pyqtSignal(str, str)
    notification_requested = pyqtSignal(str, str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, logger: AppLogger) -> None:
        super().__init__()
        self.logger = logger
        self.parser = HamachiParser()
        self.status = HamachiStatus()
        self.networks: list[NetworkInfo] = []
        self.selected_network_id = ""
        self._queue: deque[CommandTask] = deque()
        self._current_task: CommandTask | None = None
        self._process: QProcess | None = None
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._previous_online_state = False
        self._member_state_cache: dict[str, bool] = {}
        self._last_error_message: str | None = None

    def refresh(self, selected_network_id: str | None = None) -> None:
        if selected_network_id is not None:
            self.selected_network_id = selected_network_id
        if self._has_pending_refresh():
            return
        self._enqueue(CommandTask(["hamachi"], "hamachi", parser_key="status"))
        self._enqueue(CommandTask(["hamachi", "list"], "hamachi list", parser_key="list"))

    def login(self) -> None:
        self._run_and_refresh(["hamachi", "login"], "hamachi login")

    def logout(self) -> None:
        self._run_and_refresh(["hamachi", "logout"], "hamachi logout")

    def join_network(self, network_id: str, password: str = "") -> None:
        args = ["hamachi", "join", network_id]
        if password:
            args.append(password)
        self._run_and_refresh(args, " ".join(args))

    def leave_network(self, network_id: str) -> None:
        self._run_and_refresh(["hamachi", "leave", network_id], f"hamachi leave {network_id}")

    def set_nickname(self, nickname: str) -> None:
        self._run_and_refresh(["hamachi", "set-nick", nickname], f"hamachi set-nick {nickname}")

    def get_members(self, network_id: str) -> None:
        self.selected_network_id = network_id
        self.members_updated.emit(self._members_for_network(network_id))

    def run_raw_command(self, command_line: str) -> None:
        try:
            args = shlex.split(command_line)
        except ValueError as exc:
            self.error_occurred.emit("Command Error", f"Unable to parse command: {exc}")
            self.logger.log(f"Command parse error: {exc}")
            return

        if not args or args[0] != "hamachi":
            message = "Only hamachi commands are allowed in the embedded console."
            self.error_occurred.emit("Command Rejected", message)
            self.logger.log(message)
            return

        refresh_after = any(token in args for token in {"login", "logout", "join", "leave", "set-nick"})
        self._enqueue(CommandTask(args, command_line, refresh_after=refresh_after))

    def _run_and_refresh(self, args: list[str], label: str) -> None:
        self._enqueue(CommandTask(args, label, refresh_after=True))

    def _enqueue(self, task: CommandTask) -> None:
        self._queue.append(task)
        if self._current_task is None:
            self._start_next()

    def _start_next(self) -> None:
        if self._current_task is not None or not self._queue:
            return
        self._current_task = self._queue.popleft()
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._process = QProcess(self)
        self._process.setProgram(self._current_task.args[0])
        self._process.setArguments(self._current_task.args[1:])
        self._process.readyReadStandardOutput.connect(self._handle_stdout)
        self._process.readyReadStandardError.connect(self._handle_stderr)
        self._process.finished.connect(self._handle_finished)
        self.busy_changed.emit(True)
        self.logger.log(f"Executing: {self._current_task.label}")
        self._process.start()

    def _handle_stdout(self) -> None:
        if not self._process:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._stdout_buffer += chunk
        self.logger.log(chunk)

    def _handle_stderr(self) -> None:
        if not self._process:
            return
        chunk = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._stderr_buffer += chunk
        self.logger.log(chunk)

    def _handle_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        task = self._current_task
        combined = "\n".join(part for part in (self._stdout_buffer, self._stderr_buffer) if part).strip()

        if task and task.parser_key:
            self._apply_parser(task.parser_key, combined, task.meta)

        error_message = self._classify_error(combined, exit_code)
        if error_message:
            if error_message != self._last_error_message:
                self.error_occurred.emit("Hamachi Error", error_message)
                self._last_error_message = error_message
            self.logger.log(f"Error detected: {error_message}")
        else:
            self._last_error_message = None
            self.logger.log("Command completed successfully")

        if task and task.refresh_after and not self._has_pending_refresh():
            self._queue.appendleft(CommandTask(["hamachi", "list"], "hamachi list", parser_key="list"))
            self._queue.appendleft(CommandTask(["hamachi"], "hamachi", parser_key="status"))

        self._current_task = None
        if self._process:
            self._process.deleteLater()
            self._process = None
        self.busy_changed.emit(False)
        self._start_next()

    def _apply_parser(self, parser_key: str, output: str, meta: dict[str, str]) -> None:
        if parser_key == "status":
            status = self.parser.parse_status(output)
            self.status = status
            self.status_updated.emit(status)
            return
        if parser_key == "list":
            networks = self.parser.parse_list(output)
            self.networks = networks
            self.networks_updated.emit(networks)
            if self.selected_network_id:
                self.members_updated.emit(self._members_for_network(self.selected_network_id))
            elif networks:
                self.selected_network_id = networks[0].network_id
                self.members_updated.emit(networks[0].members)

    def _members_for_network(self, network_id: str) -> list[MemberInfo]:
        for network in self.networks:
            if network.network_id == network_id:
                return list(network.members)
        return []

    def _has_pending_refresh(self) -> bool:
        return self._has_pending_parser("status") or self._has_pending_parser("list")

    def _has_pending_parser(self, parser_key: str) -> bool:
        if self._current_task and self._current_task.parser_key == parser_key:
            return True
        return any(task.parser_key == parser_key for task in self._queue)

    def _classify_error(self, output: str, exit_code: int) -> str | None:
        lowered = output.lower()
        patterns = {
            "daemon not running": "The Hamachi daemon is not running. Start hamachid and try again.",
            "permission denied": "Permission denied while talking to hamachid.",
            "network not found": "The requested network was not found.",
            "manual approval required": "This action requires manual approval from the network owner.",
            "invalid password": "Invalid network password.",
        }
        for pattern, message in patterns.items():
            if pattern in lowered:
                return message
        if exit_code != 0 and output.strip():
            return output.strip().splitlines()[-1]
        return None
