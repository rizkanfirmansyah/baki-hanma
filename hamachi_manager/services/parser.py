from __future__ import annotations

import re
from typing import Iterable

from hamachi_manager.models import HamachiStatus, MemberInfo, NetworkInfo


class HamachiParser:
    IPV4_RE = re.compile(r"\b(?:25|5)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    GENERIC_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    IPV6_RE = re.compile(r"\b[a-fA-F0-9:]{3,}\b")
    CLIENT_ID_RE = re.compile(r"\b(?:\d{3}-\d{3}-\d{3}|[A-Za-z0-9]{8,})\b")
    KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z0-9 /_-]+?)\s*:\s*(.+?)\s*$")
    OWNER_RE = re.compile(r"owner(?:\s+name)?\s*[:=]?\s*([^,|;]+)", re.IGNORECASE)
    CAPACITY_RE = re.compile(r"\b(\d+\s*/\s*\d+)\b")
    SUBSCRIPTION_RE = re.compile(
        r"subscription(?:\s+type)?\s*[:=]?\s*([^,|;]+)",
        re.IGNORECASE,
    )
    STATUS_WORD_RE = re.compile(
        r"\b(online|offline|relay|direct|attached|detached|locked|unlocked|pending)\b",
        re.IGNORECASE,
    )
    ENDPOINT_RE = re.compile(
        r"(?:endpoint|addr|address|via)\s*[:=]?\s*((?:\d{1,3}\.){3}\d{1,3}(?::\d+)?)",
        re.IGNORECASE,
    )

    def parse_status(self, output: str) -> HamachiStatus:
        status = HamachiStatus()
        raw = self._parse_key_values(output)

        version_match = re.search(r"\bver\s+([0-9A-Za-z._-]+)", output)
        if version_match:
            status.version = version_match.group(1)

        status.raw = raw
        status.daemon_pid = self._first_value(raw, ("pid", "daemon pid"), default="-")
        status.client_id = self._first_value(raw, ("client id", "client-id"), default="-")
        status.nickname = self._first_value(raw, ("nickname", "nick"), default="-")
        status.account = self._first_value(
            raw,
            ("lmi account", "account", "logmein account", "attached account"),
            default="-",
        )
        status.attach_status = self._derive_attach_status(output, raw)
        status.login_status = self._derive_login_status(output, raw)
        status.online = "online" in status.login_status.lower()

        ipv4s = self.IPV4_RE.findall(output)
        generic_ipv4s = self.GENERIC_IPV4_RE.findall(output)
        status.ipv4 = ipv4s[0] if ipv4s else (generic_ipv4s[0] if generic_ipv4s else "-")
        status.ipv6 = self._find_ipv6(output) or "-"

        if status.version == "-":
            status.version = self._derive_hamachi_state(output, status)
        return status

    def parse_list(self, output: str) -> list[NetworkInfo]:
        networks: list[NetworkInfo] = []
        current_network: NetworkInfo | None = None

        for raw_line in output.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue

            indent = len(raw_line) - len(raw_line.lstrip())
            stripped = line.strip()

            if self._looks_like_network_line(stripped, indent):
                current_network = self._parse_network_line(stripped)
                networks.append(current_network)
                continue

            if current_network is None:
                current_network = self._parse_network_line(stripped)
                networks.append(current_network)
                continue

            member = self._parse_member_line(stripped, current_network)
            if member:
                current_network.members.append(member)

        return networks

    def parse_network_details(self, output: str) -> dict[str, str]:
        raw = self._parse_key_values(output)
        details: dict[str, str] = {
            "network_id": self._first_match(self.CLIENT_ID_RE, output) or raw.get("id", "-"),
            "name": raw.get("name", raw.get("network name", "-")),
            "owner": self._first_value(raw, ("owner", "owner name"), default="Unknown"),
            "capacity": self._extract_capacity(output) or raw.get("capacity", "Unknown"),
            "subscription_type": self._extract_subscription(output)
            or self._first_value(raw, ("subscription", "subscription type"), default="Unknown"),
            "status": self._derive_network_status(output),
        }
        return details

    def parse_peer_details(self, output: str) -> dict[str, str]:
        raw = self._parse_key_values(output)
        endpoint = self._extract_endpoint(output)
        ipv4s = self.GENERIC_IPV4_RE.findall(output)
        hamachi_ip = self.IPV4_RE.findall(output)
        details = {
            "client_id": self._first_value(raw, ("client id", "id"), default="-")
            or self._first_match(self.CLIENT_ID_RE, output)
            or "-",
            "nickname": self._first_value(raw, ("nickname", "nick"), default="-"),
            "ipv4": hamachi_ip[0] if hamachi_ip else (ipv4s[0] if ipv4s else "-"),
            "ipv6": self._find_ipv6(output) or "-",
            "connection_type": self._derive_connection_type(output),
            "direct_state": self._derive_direct_state(output),
            "endpoint_ip": endpoint or self._pick_non_hamachi_ip(ipv4s) or "-",
            "online": "true" if self._derive_online(output) else "false",
        }
        return details

    def _parse_network_line(self, line: str) -> NetworkInfo:
        network_id = self._first_match(self.CLIENT_ID_RE, line) or "-"
        compact = re.sub(r"^[*!x+\-#\s]+", "", line).strip()
        compact = compact.replace("[", " ").replace("]", " ")
        compact = re.sub(r"\s+", " ", compact)
        name = compact
        if network_id != "-" and network_id in compact:
            name = compact.split(network_id, 1)[1].strip(" -")

        for fragment in (
            self._extract_capacity(line),
            self._extract_subscription(line),
            self._extract_owner(line),
        ):
            if fragment:
                name = name.replace(fragment, "").strip(" -,|")

        status = self._derive_network_status(line)
        if status and status in name.lower():
            name = re.sub(status, "", name, flags=re.IGNORECASE).strip(" -,|")

        return NetworkInfo(
            network_id=network_id,
            name=name or network_id,
            owner=self._extract_owner(line) or "Unknown",
            capacity=self._extract_capacity(line) or "Unknown",
            subscription_type=self._extract_subscription(line) or "Unknown",
            status=status,
            raw={"line": line},
        )

    def _parse_member_line(self, line: str, network: NetworkInfo) -> MemberInfo | None:
        client_id = self._first_match(self.CLIENT_ID_RE, line)
        if not client_id:
            return None

        compact = re.sub(r"^[*!x+\-#\s]+", "", line).strip()
        compact = compact.replace("[", " ").replace("]", " ")
        compact = re.sub(r"\s+", " ", compact)
        nickname = compact.split(client_id, 1)[1].strip() if client_id in compact else compact

        ipv4s = self.GENERIC_IPV4_RE.findall(line)
        hamachi_ip = self.IPV4_RE.findall(line)
        ipv4 = hamachi_ip[0] if hamachi_ip else (ipv4s[0] if ipv4s else "-")
        endpoint_ip = self._extract_endpoint(line) or self._pick_non_hamachi_ip(ipv4s) or "-"
        ipv6 = self._find_ipv6(line) or "-"
        connection_type = self._derive_connection_type(line)
        direct_state = self._derive_direct_state(line)
        online = self._derive_online(line)

        if ipv4 != "-":
            nickname = nickname.replace(ipv4, "").strip(" -,|")
        if ipv6 != "-":
            nickname = nickname.replace(ipv6, "").strip(" -,|")
        for fragment in (connection_type, direct_state, endpoint_ip):
            if fragment and fragment != "-" and fragment.lower() in nickname.lower():
                nickname = re.sub(fragment, "", nickname, flags=re.IGNORECASE).strip(" -,|")

        return MemberInfo(
            client_id=client_id,
            nickname=nickname or client_id,
            ipv4=ipv4,
            ipv6=ipv6,
            connection_type=connection_type,
            direct_state=direct_state,
            endpoint_ip=endpoint_ip,
            online=online,
            network_id=network.network_id,
            network_name=network.name,
            raw={"line": line},
        )

    def _parse_key_values(self, output: str) -> dict[str, str]:
        raw: dict[str, str] = {}
        for line in output.splitlines():
            match = self.KEY_VALUE_RE.match(line)
            if not match:
                continue
            key = self._normalize_key(match.group(1))
            raw[key] = match.group(2).strip()
        return raw

    def _normalize_key(self, key: str) -> str:
        return re.sub(r"\s+", " ", key.strip().lower())

    def _first_value(
        self,
        raw: dict[str, str],
        keys: Iterable[str],
        default: str = "",
    ) -> str:
        for key in keys:
            if key in raw:
                return raw[key]
        return default

    def _derive_attach_status(self, output: str, raw: dict[str, str]) -> str:
        candidates = [
            raw.get("attach status", ""),
            raw.get("attached", ""),
            raw.get("attached account", ""),
            raw.get("account", ""),
            output,
        ]
        for candidate in candidates:
            lowered = candidate.lower()
            if "not attached" in lowered or "detached" in lowered:
                return "Detached"
            if "attached" in lowered:
                return "Attached"
            if "pending" in lowered:
                return "Pending"
        return "Unknown"

    def _derive_login_status(self, output: str, raw: dict[str, str]) -> str:
        candidates = [
            raw.get("status", ""),
            raw.get("online", ""),
            raw.get("login status", ""),
            output,
        ]
        for candidate in candidates:
            lowered = candidate.lower()
            if "offline" in lowered or "logged out" in lowered:
                return "Offline"
            if "online" in lowered or "logged in" in lowered:
                return "Online"
            if "connecting" in lowered:
                return "Connecting"
        return "Unknown"

    def _derive_hamachi_state(self, output: str, status: HamachiStatus) -> str:
        lowered = output.lower()
        if "daemon not running" in lowered:
            return "Daemon Offline"
        if (
            "you do not have permission to control the hamachid daemon" in lowered
            or "h2-engine-override.cfg" in lowered
            or "ipc.user" in lowered
        ):
            return "Permission Error"
        if status.client_id != "-" or status.daemon_pid != "-" or status.ipv4 != "-":
            return "Running"
        if status.login_status == "Online":
            return "Running"
        if status.login_status == "Offline":
            return "Disconnected"
        return "-"

    def _looks_like_network_line(self, line: str, indent: int) -> bool:
        if indent == 0:
            return True
        lowered = line.lower()
        if any(token in lowered for token in ("owner", "subscription", "capacity")):
            return True
        if self.IPV4_RE.search(line) or self._find_ipv6(line):
            return False
        return indent < 2 and bool(self.CLIENT_ID_RE.search(line))

    def _derive_network_status(self, line: str) -> str:
        match = self.STATUS_WORD_RE.search(line)
        if match:
            return match.group(1).capitalize()
        stripped = line.lstrip()
        if stripped.startswith("x"):
            return "Offline"
        if stripped.startswith("!"):
            return "Relay"
        if stripped.startswith("*"):
            return "Online"
        return "Unknown"

    def _derive_connection_type(self, line: str) -> str:
        lowered = line.lower()
        if "relay" in lowered:
            return "Relay"
        if "direct" in lowered:
            return "Direct"
        if "tunnel" in lowered:
            return "Tunnel"
        return "Unknown"

    def _derive_direct_state(self, line: str) -> str:
        lowered = line.lower()
        if "relay" in lowered or line.lstrip().startswith("!"):
            return "Relay"
        if "direct" in lowered or line.lstrip().startswith("*"):
            return "Direct"
        return "Unknown"

    def _derive_online(self, line: str) -> bool:
        lowered = line.lower()
        if "offline" in lowered or line.lstrip().startswith("x"):
            return False
        if "online" in lowered or line.lstrip().startswith("*") or line.lstrip().startswith("!"):
            return True
        return False

    def _extract_owner(self, line: str) -> str | None:
        match = self.OWNER_RE.search(line)
        return match.group(1).strip() if match else None

    def _extract_capacity(self, line: str) -> str | None:
        match = self.CAPACITY_RE.search(line)
        return match.group(1).replace(" ", "") if match else None

    def _extract_subscription(self, line: str) -> str | None:
        match = self.SUBSCRIPTION_RE.search(line)
        return match.group(1).strip() if match else None

    def _extract_endpoint(self, line: str) -> str | None:
        match = self.ENDPOINT_RE.search(line)
        if match:
            return match.group(1)
        return None

    def _pick_non_hamachi_ip(self, ips: list[str]) -> str | None:
        for ip in ips:
            if not ip.startswith(("25.", "5.")):
                return ip
        return None

    def _find_ipv6(self, text: str) -> str | None:
        candidates = [candidate for candidate in self.IPV6_RE.findall(text) if ":" in candidate]
        return candidates[0] if candidates else None

    def _first_match(self, pattern: re.Pattern[str], text: str) -> str | None:
        match = pattern.search(text)
        return match.group(0) if match else None
