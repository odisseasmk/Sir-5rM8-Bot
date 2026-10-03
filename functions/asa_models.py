"""Internal ASA models — Discord code should use these, not raw CDN JSON."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AsaServer:
    """Mapped official-list row. Legacy dict helpers use `to_raw_dict()` (not retained)."""

    session_id: str
    name: str
    session_name: str
    ip: str
    port: int | None
    map_name: str
    num_players: int
    max_players: int
    ping: int | None
    build_id: int | None
    minor_build_id: int | None
    version: str | None
    platform: str
    cluster_id: str
    day_time: str
    last_updated: datetime | None
    last_updated_age_seconds: float | None
    is_official: bool
    session_is_pve: bool | None
    server_key: str

    @property
    def ip_port(self) -> str | None:
        if not self.ip or self.ip == "—":
            return None
        if self.port is None:
            return self.ip
        return f"{self.ip}:{self.port}"

    def to_raw_dict(self) -> dict[str, Any]:
        """Synthesize the slim official-list shape used by matchers / BM / bucket flush."""
        last_ms = (
            int(self.last_updated.timestamp() * 1000) if self.last_updated is not None else None
        )
        ip = "" if self.ip == "—" else self.ip
        map_name = "" if self.map_name == "—" else self.map_name
        platform = "" if self.platform == "—" else self.platform
        day_time = "" if self.day_time == "—" else self.day_time
        out: dict[str, Any] = {
            "SessionName": self.session_name,
            "SessionNameUpper": self.session_name.upper(),
            "Name": self.name,
            "SessionID": self.session_id,
            "IP": ip,
            "Port": self.port,
            "MapName": map_name,
            "NumPlayers": self.num_players,
            "MaxPlayers": self.max_players,
            "ServerPing": self.ping,
            "BuildId": self.build_id,
            "MinorBuildId": self.minor_build_id,
            "PlatformType": platform,
            "ClusterId": self.cluster_id,
            "DayTime": day_time,
            "LastUpdated": last_ms,
            "IsOfficial": "1" if self.is_official else "0",
        }
        if self.session_is_pve is not None:
            out["SessionIsPve"] = "1" if self.session_is_pve else "0"
        return {k: v for k, v in out.items() if v is not None and v != ""}

    @property
    def raw(self) -> dict[str, Any]:
        """Alias for legacy call sites — synthesized, not a retained CDN copy."""
        return self.to_raw_dict()


@dataclass(frozen=True)
class NetworkStatus:
    fetch_ok: bool
    online: bool | None  # True/False if parsed, None if unknown/unparsed
    version: str | None
    raw: str = ""
    error: str | None = None  # "fetch_failed" | "parse_failed"

    @property
    def label(self) -> str:
        if not self.fetch_ok:
            return "API_UNAVAILABLE"
        if self.online is True:
            return "ONLINE"
        if self.online is False:
            return "OFFLINE"
        return "UNKNOWN"


@dataclass(frozen=True)
class AsaAnnouncement:
    fetch_ok: bool
    text: str | None
    error: str | None = None


@dataclass(frozen=True)
class AsaSnapshot:
    fetch_ok: bool
    fetched_at: datetime
    servers: tuple[AsaServer, ...] = ()
    error: str | None = None  # "fetch_failed" | "invalid_json" | "empty" | "not_list"
    server_count: int = 0
    skipped: int = 0

    def by_key(self) -> dict[str, AsaServer]:
        return {s.server_key: s for s in self.servers if s.server_key}

    def get(self, server_key: str) -> AsaServer | None:
        """Lookup by notify/server key without rebuilding the full raw dict list."""
        key = str(server_key or "").strip()
        if not key:
            return None
        for server in self.servers:
            if server.server_key == key:
                return server
        return None

    def as_raw_list(self) -> list[dict]:
        return [s.to_raw_dict() for s in self.servers]
