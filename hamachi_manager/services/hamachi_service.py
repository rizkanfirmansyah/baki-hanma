from __future__ import annotations

import os
import shlex
import shutil
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

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
        self._mtu_presets = (1250, 1200, 1180, 1160)
        self._preferred_mtu = 1250
        self._last_tune_attempt = 0.0
        self._tune_cooldown_seconds = 20.0
        self._tuning_unavailable_reported = False

    def refresh(self, selected_network_id: str | None = None) -> None:
        if selected_network_id is not None:
            self.selected_network_id = selected_network_id
        if self._has_pending_refresh():
            return
        self._enqueue(CommandTask(["hamachi"], "hamachi", parser_key="status"))
        self._enqueue(CommandTask(["hamachi", "list"], "hamachi list", parser_key="list"))

    def get_status(self) -> None:
        self._enqueue(CommandTask(["hamachi"], "hamachi", parser_key="status"))

    def get_networks(self) -> None:
        self._enqueue(CommandTask(["hamachi", "list"], "hamachi list", parser_key="list"))

    def get_members(self, network_id: str) -> None:
        self.selected_network_id = network_id
        self.members_updated.emit(self._members_for_network(network_id))
        if network_id and not self._has_pending_parser("network"):
            self._enqueue(
                CommandTask(
                    ["hamachi", "network", network_id],
                    f"hamachi network {network_id}",
                    parser_key="network",
                    meta={"network_id": network_id},
                )
            )

    def get_peer_detail(self, client_id: str) -> None:
        if client_id and not self._has_pending_peer(client_id):
            self._enqueue(
                CommandTask(
                    ["hamachi", "peer", client_id],
                    f"hamachi peer {client_id}",
                    parser_key="peer",
                    meta={"client_id": client_id},
                )
            )

    def login(self) -> None:
        self._ensure_network_tuning()
        self._run_and_refresh(["hamachi", "login"], "hamachi login")

    def logout(self) -> None:
        self._run_and_refresh(["hamachi", "logout"], "hamachi logout")

    def reconnect(self) -> None:
        self._ensure_network_tuning()
        self._enqueue(CommandTask(["hamachi", "logout"], "hamachi logout"))
        self._enqueue(CommandTask(["hamachi", "login"], "hamachi login", refresh_after=True))

    def attach_account(self, account: str) -> None:
        self._run_and_refresh(["hamachi", "attach", account], f"hamachi attach {account}")

    def detach_account(self) -> None:
        self._run_and_refresh(["hamachi", "cancel"], "hamachi cancel")

    def join_network(self, network_id: str, password: str = "") -> None:
        self._ensure_network_tuning()
        args = ["hamachi", "join", network_id]
        if password:
            args.append(password)
        self._run_and_refresh(args, " ".join(args))

    def leave_network(self, network_id: str) -> None:
        self._run_and_refresh(["hamachi", "leave", network_id], f"hamachi leave {network_id}")

    def set_nickname(self, nickname: str) -> None:
        self._run_and_refresh(
            ["hamachi", "set-nick", nickname],
            f"hamachi set-nick {nickname}",
        )

    def preferred_mtu(self) -> int:
        return self._preferred_mtu

    def available_mtu_presets(self) -> tuple[int, ...]:
        return self._mtu_presets

    def set_preferred_mtu(self, mtu: int, apply_now: bool = True) -> None:
        mtu = max(1000, min(mtu, 1450))
        self._preferred_mtu = mtu
        self.logger.log(f"Preferred Hamachi MTU set to {mtu}")
        if apply_now:
            self.apply_network_tuning(force=True)

    def apply_safe_web_profile(self) -> int:
        safe_mtu = 1200
        self.set_preferred_mtu(safe_mtu, apply_now=True)
        self.logger.log("Applied safe SSH/web profile")
        return safe_mtu

    def step_down_mtu(self, apply_now: bool = True) -> int:
        ordered = sorted(self._mtu_presets, reverse=True)
        target = ordered[-1]
        for preset in ordered:
            if preset < self._preferred_mtu:
                target = preset
                break
        self.set_preferred_mtu(target, apply_now=apply_now)
        self.logger.log(f"Stepped down preferred MTU to {target}")
        return target

    def apply_network_tuning(self, force: bool = True) -> None:
        self._ensure_network_tuning(force=force)

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

        if self._command_requires_network_tuning(args):
            self._ensure_network_tuning()

        refresh_after = any(
            token in args
            for token in {"login", "logout", "join", "leave", "attach", "cancel", "set-nick"}
        )
        self._enqueue(CommandTask(args, command_line, refresh_after=refresh_after))

    def _run_and_refresh(self, args: list[str], label: str) -> None:
        self._enqueue(CommandTask(args, label, refresh_after=True))

    def _command_requires_network_tuning(self, args: list[str]) -> bool:
        return len(args) > 1 and args[0] == "hamachi" and args[1] in {"login", "join"}

    def _ensure_network_tuning(self, force: bool = False) -> None:
        if self._has_pending_tuning():
            return

        now = monotonic()
        if not force and now - self._last_tune_attempt < self._tune_cooldown_seconds:
            return

        task = self._build_tuning_task()
        if task is None:
            self.logger.log(
                "Automatic MTU tuning unavailable. Install the helper service or ensure pkexec is installed."
            )
            if not self._tuning_unavailable_reported:
                self.error_occurred.emit(
                    "Network Tuning",
                    "Automatic MTU tuning is unavailable. Install PolicyKit support or run the included systemd tuning installer.",
                )
                self._tuning_unavailable_reported = True
            return

        self._last_tune_attempt = now
        self._enqueue(task)

    def _build_tuning_task(self) -> CommandTask | None:
        project_root = Path(__file__).resolve().parents[2]
        script_candidates = [
            Path('/usr/local/sbin/hamachi-network-tune.sh'),
            project_root / 'scripts' / 'hamachi-network-tune.sh',
        ]
        script_path = next((candidate for candidate in script_candidates if candidate.exists()), None)
        if script_path is None:
            return None

        args = [str(script_path), 'ham0', str(self._preferred_mtu), 'clamp']
        if os.geteuid() != 0:
            pkexec = shutil.which('pkexec')
            if not pkexec:
                return None
            args = [pkexec, *args]

        return CommandTask(
            args,
            f'Prepare network path: MTU {self._preferred_mtu} + TCP MSS clamp',
            meta={'task_type': 'tune'},
        )

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
        task_type = task.meta.get('task_type', '') if task else ''

        if task and task.parser_key:
            self._apply_parser(task.parser_key, combined, task.meta)

        if task_type == 'tune':
            tuning_error = self._classify_tuning_error(combined, exit_code)
            if tuning_error:
                self.error_occurred.emit('Network Tuning', tuning_error)
                self.logger.log(f'Network tuning issue: {tuning_error}')
            else:
                self.logger.log('Network tuning applied successfully')
        else:
            error_message = self._classify_error(combined, exit_code)
            if error_message:
                if error_message != self._last_error_message:
                    self.error_occurred.emit('Hamachi Error', error_message)
                    self._last_error_message = error_message
                else:
                    self.logger.log(f'Repeated error suppressed: {error_message}')
                self.logger.log(f'Error detected: {error_message}')
            else:
                self._last_error_message = None
                self.logger.log('Command completed successfully')

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
            new_status = self.parser.parse_status(output)
            self._notify_status_change(new_status)
            self.status = new_status
            self.status_updated.emit(new_status)
            return

        if parser_key == "list":
            networks = self.parser.parse_list(output)
            self._notify_member_changes(networks)
            self.networks = networks
            self.networks_updated.emit(networks)
            if self.selected_network_id:
                self.members_updated.emit(self._members_for_network(self.selected_network_id))
            elif networks:
                self.selected_network_id = networks[0].network_id
                self.members_updated.emit(networks[0].members)
            return

        if parser_key == "network":
            details = self.parser.parse_network_details(output)
            self._merge_network_details(meta.get("network_id", ""), details)
            self.networks_updated.emit(self.networks)
            if self.selected_network_id:
                self.members_updated.emit(self._members_for_network(self.selected_network_id))
            return

        if parser_key == "peer":
            details = self.parser.parse_peer_details(output)
            member = self._merge_peer_details(meta.get("client_id", ""), details)
            if member:
                self.peer_updated.emit(member)
                if self.selected_network_id:
                    self.members_updated.emit(self._members_for_network(self.selected_network_id))

    def _merge_network_details(self, network_id: str, details: dict[str, str]) -> None:
        for network in self.networks:
            if network.network_id != network_id:
                continue
            network.name = details.get("name", network.name) or network.name
            network.owner = details.get("owner", network.owner) or network.owner
            network.capacity = details.get("capacity", network.capacity) or network.capacity
            network.subscription_type = (
                details.get("subscription_type", network.subscription_type) or network.subscription_type
            )
            network.status = details.get("status", network.status) or network.status
            network.raw.update(details)
            break

    def _merge_peer_details(self, client_id: str, details: dict[str, str]) -> MemberInfo | None:
        for network in self.networks:
            for member in network.members:
                if member.client_id != client_id:
                    continue
                member.nickname = details.get("nickname", member.nickname) or member.nickname
                member.ipv4 = details.get("ipv4", member.ipv4) or member.ipv4
                member.ipv6 = details.get("ipv6", member.ipv6) or member.ipv6
                member.connection_type = (
                    details.get("connection_type", member.connection_type) or member.connection_type
                )
                member.direct_state = details.get("direct_state", member.direct_state) or member.direct_state
                member.endpoint_ip = details.get("endpoint_ip", member.endpoint_ip) or member.endpoint_ip
                member.online = details.get("online", "false").lower() == "true"
                member.raw.update(details)
                return member
        return None

    def _members_for_network(self, network_id: str) -> list[MemberInfo]:
        for network in self.networks:
            if network.network_id == network_id:
                return list(network.members)
        return []

    def _notify_status_change(self, new_status: HamachiStatus) -> None:
        if self.status.login_status == "Unknown":
            self._previous_online_state = new_status.online
            return

        if new_status.online and not self._previous_online_state:
            self._ensure_network_tuning(force=True)
            self.notification_requested.emit("Hamachi Connected", "Hamachi client is now online.")
        elif not new_status.online and self._previous_online_state:
            self.notification_requested.emit("Hamachi Disconnected", "Hamachi client is now offline.")
        self._previous_online_state = new_status.online

    def _notify_member_changes(self, networks: list[NetworkInfo]) -> None:
        current_state: dict[str, bool] = {}
        for network in networks:
            for member in network.members:
                current_state[member.state_key] = member.online

        if not self._member_state_cache:
            self._member_state_cache = current_state
            return

        for network in networks:
            for member in network.members:
                previous = self._member_state_cache.get(member.state_key)
                if previous is None or previous == member.online:
                    continue
                state = "online" if member.online else "offline"
                self.logger.log(f"Member {state}: {member.nickname}")
                self.notification_requested.emit(
                    f"Member {state.title()}",
                    f"{member.nickname} in {member.network_name} is now {state}.",
                )

        self._member_state_cache = current_state

    def _has_pending_refresh(self) -> bool:
        return self._has_pending_parser("status") or self._has_pending_parser("list")

    def _has_pending_parser(self, parser_key: str) -> bool:
        if self._current_task and self._current_task.parser_key == parser_key:
            return True
        return any(task.parser_key == parser_key for task in self._queue)

    def _has_pending_peer(self, client_id: str) -> bool:
        if self._current_task and self._current_task.parser_key == "peer":
            return self._current_task.meta.get("client_id") == client_id
        return any(
            task.parser_key == "peer" and task.meta.get("client_id") == client_id
            for task in self._queue
        )

    def _has_pending_tuning(self) -> bool:
        if self._current_task and self._current_task.meta.get('task_type') == 'tune':
            return True
        return any(task.meta.get('task_type') == 'tune' for task in self._queue)

    def _classify_tuning_error(self, output: str, exit_code: int) -> str | None:
        lowered = output.lower()
        if not output.strip() and exit_code == 0:
            return None
        if 'interface ham0 not found' in lowered or 'skipping hamachi tuning' in lowered:
            self.logger.log('Hamachi interface not ready yet; tuning will be retried on next login/online transition.')
            return None
        if 'not authorized' in lowered or 'authentication failed' in lowered:
            return 'Administrator authentication is required to apply automatic MTU tuning.'
        if 'cancelled' in lowered or 'canceled' in lowered:
            return 'Network tuning was cancelled. SSH or web access over Hamachi may remain unstable until MTU tuning is applied.'
        if 'pkexec' in lowered and 'not found' in lowered:
            return 'pkexec is not available. Install PolicyKit support or run the included systemd tuning installer.'
        if 'ip command not found' in lowered or 'iptables command not found' in lowered:
            return 'Required network tools are missing. Install iproute2 and iptables.'
        if 'permission denied' in lowered:
            return 'Administrator permission is required to apply MTU tuning.'
        if exit_code != 0:
            if output.strip():
                return output.strip().splitlines()[-1]
            return 'Failed to apply automatic Hamachi MTU tuning.'
        return None

    def _classify_error(self, output: str, exit_code: int) -> str | None:
        lowered = output.lower()
        if (
            "you do not have permission to control the hamachid daemon" in lowered
            or "h2-engine-override.cfg" in lowered
            or "ipc.user" in lowered
        ):
            return (
                "Permission denied while talking to hamachid. Add your login user to "
                "/var/lib/logmein-hamachi/h2-engine-override.cfg, then restart the daemon."
            )
        patterns = {
            "daemon not running": "The Hamachi daemon is not running. Start hamachid and try again.",
            "permission denied": (
                "Permission denied while talking to hamachid. Add your user to "
                "/var/lib/logmein-hamachi/h2-engine-override.cfg or run the daemon with the proper ACL."
            ),
            "network not found": "The requested network was not found.",
            "manual approval required": "This action requires manual approval from the network owner.",
            "invalid password": "Invalid network password.",
            "not attached": "The client is not attached to a LogMeIn account.",
        }
        for pattern, message in patterns.items():
            if pattern in lowered:
                return message
        if exit_code != 0 and output.strip():
            error_markers = (
                "error",
                "failed",
                "invalid",
                "not found",
                "permission",
                "denied",
                "required",
                "daemon not running",
            )
            if any(marker in lowered for marker in error_markers):
                return output.strip().splitlines()[-1]
        return None
