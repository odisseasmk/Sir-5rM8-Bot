"""Resolve ASA server status for /serverstatus (official list primary, BM fallback)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import config
from functions.asa import (
    match_server_in_list,
    notify_key_from_server,
    query_server_key,
    query_server_number,
)
from functions.asa_cache import (
    current_announcement,
    current_network,
    get_snapshot,
    last_good_snapshot,
    last_known_server,
)
from functions.asa_client import parse_asa_server
from functions.asa_models import AsaServer
from functions.asa_status import (
    STATUS_API_UNAVAILABLE,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_UNKNOWN,
    ServerPresenceStatus,
    get_server_status,
)
from functions.battlemetrics import (
    BattleMetricsUptime,
    fetch_server_uptime_from_asa,
    fetch_server_uptime_from_query,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedServer:
    error: str | None = None  # "fetch_failed" | "not_found"
    online: bool = False
    presence: str = STATUS_UNKNOWN  # ONLINE | OFFLINE | UNKNOWN | API_UNAVAILABLE
    presence_reason: str = ""
    server_key: str = ""
    query: str = ""
    session_name: str = "Unknown"
    ip: str = "—"
    num_players: int = 0
    max_players: int = 70
    day: str = "—"
    ping: str = "—"
    map_name: str = "—"
    platform: str = "—"
    version: str | None = None
    bm: BattleMetricsUptime | None = None
    from_last_known: bool = False
    network_label: str = "UNKNOWN"
    announcement: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _int_field(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _bm_or_empty(*, asa_row: dict | None, query: str, need_identity: bool) -> BattleMetricsUptime:
    token = (config.BATTLEMETRICS_TOKEN or "").strip()
    if not token:
        return BattleMetricsUptime(
            server_id="",
            name=None,
            url="",
            uptime_7=None,
            uptime_30=None,
            uptime_90=None,
            history=[],
            error="no_token",
        )
    if asa_row is not None:
        return fetch_server_uptime_from_asa(asa_row)
    if need_identity and config.ASA_BM_FALLBACK:
        return fetch_server_uptime_from_query(query)
    return BattleMetricsUptime(
        server_id="",
        name=None,
        url="",
        uptime_7=None,
        uptime_30=None,
        uptime_90=None,
        history=[],
        error="not_found",
    )


def _log_bm_discrepancy(presence: ServerPresenceStatus, bm: BattleMetricsUptime | None, server_key: str) -> None:
    if not config.ASA_BM_COMPARE or bm is None or not bm.ok:
        return
    bm_status = (bm.status or "").strip().lower()
    if bm_status not in ("online", "offline"):
        return
    ours = presence.status
    if ours == STATUS_ONLINE and bm_status == "offline":
        logger.info("ASA/BM discrepancy %s: official=%s battlemetrics=%s", server_key, ours, bm_status)
    elif ours == STATUS_OFFLINE and bm_status == "online":
        logger.info("ASA/BM discrepancy %s: official=%s battlemetrics=%s", server_key, ours, bm_status)


def _from_asa_server(
    data: AsaServer,
    bm: BattleMetricsUptime,
    query: str,
    presence: ServerPresenceStatus,
) -> ResolvedServer:
    ping = f"{data.ping} ms" if data.ping is not None else "—"
    return ResolvedServer(
        online=presence.is_online,
        presence=presence.status,
        presence_reason=presence.reason,
        server_key=data.server_key,
        query=query,
        session_name=data.session_name or data.name or "Unknown",
        ip=data.ip or "—",
        num_players=data.num_players,
        max_players=data.max_players,
        day=data.day_time,
        ping=ping,
        map_name=data.map_name,
        platform=data.platform,
        version=data.version,
        bm=bm,
        from_last_known=presence.from_last_known,
        network_label=presence.network,
        announcement=(current_announcement().text if current_announcement() else None),
    )


def _from_raw_dict(data: dict, bm: BattleMetricsUptime, query: str, *, presence: ServerPresenceStatus) -> ResolvedServer:
    parsed = parse_asa_server(data)
    if parsed is None:
        ping_raw = data.get("ServerPing")
        ping = f"{ping_raw} ms" if ping_raw not in (None, "") else "—"
        return ResolvedServer(
            online=presence.is_online,
            presence=presence.status,
            presence_reason=presence.reason,
            server_key=notify_key_from_server(data),
            query=query,
            session_name=str(data.get("SessionName") or "Unknown"),
            ip=str(data.get("IP") or "—"),
            num_players=_int_field(data.get("NumPlayers"), 0),
            max_players=_int_field(data.get("MaxPlayers"), 70),
            day=str(data.get("DayTime") or "—"),
            ping=ping,
            map_name=str(data.get("MapName") or "—").replace("_WP", ""),
            platform=str(data.get("PlatformType") or "—"),
            bm=bm,
            from_last_known=presence.from_last_known,
            network_label=presence.network,
        )
    return _from_asa_server(parsed, bm, query, presence)


def resolve_server_status(query: str) -> ResolvedServer:
    q = (query or "").strip()
    snapshot = get_snapshot()
    network = current_network()
    announcement = current_announcement()
    notice = announcement.text if announcement else None

    if snapshot is None or (not snapshot.fetch_ok and last_good_snapshot() is None):
        return ResolvedServer(
            error="fetch_failed",
            query=q,
            presence=STATUS_API_UNAVAILABLE,
            presence_reason="official_list_unavailable",
            network_label=network.label if network else "API_UNAVAILABLE",
            announcement=notice,
        )

    live = snapshot if snapshot.fetch_ok else last_good_snapshot()
    rows = live.as_raw_list() if live else []
    found_row = match_server_in_list(rows, q) if q else None
    found = parse_asa_server(found_row) if found_row else None

    key = (found.server_key if found else None) or (query_server_key(q) if q else "")
    known = last_known_server(key) if key else None
    if known is None and found is not None:
        known = found

    presence = get_server_status(
        found if snapshot.fetch_ok else None,
        snapshot=snapshot,
        network=network,
        last_known=known if found is None else found,
        server_key=key,
        record=True,
    )

    if found is not None and snapshot.fetch_ok:
        bm = _bm_or_empty(asa_row=found.raw, query=q, need_identity=False)
        _log_bm_discrepancy(presence, bm, found.server_key)
        resolved = _from_asa_server(found, bm, q, presence)
        return resolved

    if not q:
        return ResolvedServer(error="not_found", query=q, announcement=notice)

    number = query_server_number(q)
    need_bm_identity = found is None
    bm = _bm_or_empty(asa_row=None, query=q, need_identity=need_bm_identity)

    last = presence.server
    if last is not None:
        _log_bm_discrepancy(presence, bm, last.server_key)
        return _from_asa_server(last, bm, q, presence)

    if not number and not bm.ok:
        return ResolvedServer(
            error="not_found",
            query=q,
            presence=presence.status,
            presence_reason=presence.reason,
            network_label=presence.network,
            announcement=notice,
        )

    session = (bm.name if bm.name else None) or (q)
    ping = "—"
    return ResolvedServer(
        online=False,
        presence=presence.status if presence.status != STATUS_ONLINE else STATUS_OFFLINE,
        presence_reason=presence.reason or "missing_from_list",
        server_key=query_server_key(session) or query_server_key(q),
        query=q,
        session_name=session,
        ip=bm.ip or "—",
        num_players=0,
        max_players=bm.max_players or 70,
        day="—",
        ping=ping,
        map_name=(bm.map_name or "—"),
        platform="—",
        version=None,
        bm=bm,
        from_last_known=False,
        network_label=presence.network,
        announcement=notice,
    )


def resolve_from_asa_server(data: AsaServer | dict, query: str = "") -> ResolvedServer:
    """Build a status payload from an official-list row (used by the up-checker)."""
    parsed = data if isinstance(data, AsaServer) else parse_asa_server(data)
    snapshot = get_snapshot(refresh_if_stale=False)
    network = current_network()
    if parsed is None:
        if not isinstance(data, dict):
            raise TypeError("resolve_from_asa_server expected AsaServer or dict")
        bm = _bm_or_empty(asa_row=data, query=query, need_identity=False)
        presence = ServerPresenceStatus(
            status=STATUS_ONLINE,
            reason="present_in_official_list",
            network=network.label if network else "UNKNOWN",
        )
        return _from_raw_dict(data, bm, query, presence=presence)
    presence = get_server_status(
        parsed,
        snapshot=snapshot if snapshot and snapshot.fetch_ok else None,
        network=network,
        last_known=parsed,
        server_key=parsed.server_key,
        record=True,
    )
    if snapshot is None or not snapshot.fetch_ok:
        presence = ServerPresenceStatus(
            status=STATUS_ONLINE,
            reason="present_in_official_list",
            server=parsed,
            network=network.label if network else "UNKNOWN",
        )
    bm = _bm_or_empty(asa_row=parsed.raw, query=query, need_identity=False)
    _log_bm_discrepancy(presence, bm, parsed.server_key)
    return _from_asa_server(parsed, bm, query, presence)
