from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class HamachiStatus:
    version: str = "-"
    daemon_pid: str = "-"
    client_id: str = "-"
    nickname: str = "-"
    ipv4: str = "-"
    ipv6: str = "-"
    account: str = "-"
    attach_status: str = "Unknown"
    login_status: str = "Unknown"
    online: bool = False
    raw: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MemberInfo:
    client_id: str = "-"
    nickname: str = "-"
    ipv4: str = "-"
    ipv6: str = "-"
    connection_type: str = "Unknown"
    direct_state: str = "Unknown"
    endpoint_ip: str = "-"
    online: bool = False
    network_id: str = "-"
    network_name: str = "-"
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def state_key(self) -> str:
        return f"{self.network_id}:{self.client_id}:{self.ipv4}"


@dataclass(slots=True)
class NetworkInfo:
    network_id: str = "-"
    name: str = "-"
    owner: str = "Unknown"
    capacity: str = "Unknown"
    subscription_type: str = "Unknown"
    status: str = "Unknown"
    members: list[MemberInfo] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)
