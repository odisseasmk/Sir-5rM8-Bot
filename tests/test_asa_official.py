from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from functions.asa import _score_server, match_server_in_list
from functions.asa_client import (
    parse_announcement,
    parse_asa_server,
    parse_last_updated,
    parse_network_status,
    parse_server_list,
)
from functions.asa_models import AsaSnapshot, NetworkStatus
from functions.asa_status import (
    STATUS_API_UNAVAILABLE,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_UNKNOWN,
    get_server_status,
    miss_count,
    prune_status_tracker,
    reset_status_tracker,
)
from functions.battlemetrics import BattleMetricsUptime
from functions.server_status import resolve_from_asa_server, resolve_server_status


def _row(**overrides) -> dict:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    row = {
        "SessionName": "EU-PVE-TheIsland5313 - (v92.43)",
        "SessionNameUpper": "EU-PVE-THEISLAND5313 - (V92.43)",
        "Name": "EU-PVE-TheIsland5313",
        "SessionID": "e6700e1233264846a0fbd1230d3513e3",
        "IsOfficial": "1",
        "MaxPlayers": 70,
        "NumPlayers": 10,
        "Port": 7779,
        "DayTime": "50",
        "IP": "5.62.112.69",
        "MinorBuildId": 43,
        "ServerPing": 231,
        "MapName": "TheIsland_WP",
        "LastUpdated": now_ms,
        "BuildId": 92,
        "PlatformType": "PC+XSX+WINGDK+PS5",
        "ClusterId": "PVECrossplay",
    }
    row.update(overrides)
    return row


def _bm(**overrides) -> BattleMetricsUptime:
    data = dict(
        server_id="42",
        name="EU-PVE-TheIsland5313 - (v92.43)",
        url="https://www.battlemetrics.com/servers/arksa/42",
        uptime_7=99.0,
        uptime_30=98.0,
        uptime_90=97.0,
        history=[],
        error=None,
        ip="1.2.3.4",
        max_players=70,
        map_name="TheIsland",
        status="online",
    )
    data.update(overrides)
    return BattleMetricsUptime(**data)


def _online_network() -> NetworkStatus:
    return NetworkStatus(fetch_ok=True, online=True, version="v92.43", raw="Online")


def _patch_resolve(monkeypatch, rows, *, network=None, bm=None, token="test"):
    snap = parse_server_list(rows)
    monkeypatch.setattr("functions.server_status.get_snapshot", lambda **_k: snap)
    monkeypatch.setattr(
        "functions.server_status.current_network",
        lambda: network if network is not None else _online_network(),
    )
    monkeypatch.setattr("functions.server_status.current_announcement", lambda: None)
    monkeypatch.setattr("functions.server_status.last_good_snapshot", lambda: snap if snap.fetch_ok else None)
    monkeypatch.setattr("functions.server_status.last_known_server", lambda _k: None)
    monkeypatch.setattr("functions.server_status.config.BATTLEMETRICS_TOKEN", token)
    bm = bm if bm is not None else _bm()
    monkeypatch.setattr("functions.server_status.fetch_server_uptime_from_asa", lambda _s: bm)
    monkeypatch.setattr("functions.server_status.fetch_server_uptime_from_query", lambda _q: bm)
    reset_status_tracker()
    return snap


def test_parse_official_server_list_fields():
    parsed = parse_asa_server(_row())
    assert parsed is not None
    assert parsed.server_key == "5313"
    assert parsed.num_players == 10
    assert parsed.max_players == 70
    assert parsed.ping == 231
    assert parsed.version == "v92.43"
    assert parsed.map_name == "TheIsland"
    assert parsed.ip == "5.62.112.69"
    assert parsed.port == 7779
    assert parsed.last_updated is not None
    assert parsed.session_id == "e6700e1233264846a0fbd1230d3513e3"


def test_snapshot_get_by_server_key():
    snap = parse_server_list([_row()])
    assert snap.get("5313") is not None
    assert snap.get("5313").session_id == "e6700e1233264846a0fbd1230d3513e3"
    assert snap.get("missing") is None
    assert snap.get("") is None


def test_resolve_from_asa_server_accepts_model(monkeypatch):
    snap = parse_server_list([_row()])
    server = snap.get("5313")
    assert server is not None
    monkeypatch.setattr("functions.server_status.get_snapshot", lambda **_k: snap)
    monkeypatch.setattr("functions.server_status.current_network", _online_network)
    monkeypatch.setattr("functions.server_status.current_announcement", lambda: None)
    monkeypatch.setattr("functions.server_status.config.BATTLEMETRICS_TOKEN", "")
    monkeypatch.setattr(
        "functions.server_status.fetch_server_uptime_from_asa",
        lambda _s: _bm(error="no_token"),
    )
    reset_status_tracker()
    resolved = resolve_from_asa_server(server, "5313")
    assert resolved.ok
    assert resolved.server_key == "5313"
    assert resolved.presence == STATUS_ONLINE


def test_parse_last_updated_millis():
    ts, age = parse_last_updated(
        1787048249444,
        now=datetime.fromtimestamp(1787048249444 / 1000.0, tz=timezone.utc) + timedelta(seconds=10),
    )
    assert ts is not None
    assert 9.0 <= age <= 11.0


def test_malformed_row_skipped():
    snap = parse_server_list([{"nope": 1}, _row(), "bad"])
    assert snap.fetch_ok
    assert snap.server_count == 1
    assert snap.skipped == 2


def test_empty_list():
    snap = parse_server_list([])
    assert snap.fetch_ok
    assert snap.error == "empty"
    assert snap.server_count == 0


def test_invalid_payload_not_list():
    snap = parse_server_list({"data": []})
    assert snap.fetch_ok is False
    assert snap.error == "not_list"


def test_lookup_by_number_session_id_ip_and_name():
    row = _row()
    servers = [row]
    assert match_server_in_list(servers, "5313")["SessionID"] == row["SessionID"]
    assert match_server_in_list(servers, row["SessionID"])["Name"] == row["Name"]
    assert match_server_in_list(servers, "5.62.112.69")["Port"] == 7779
    assert match_server_in_list(servers, "5.62.112.69:7779")["Port"] == 7779
    assert match_server_in_list(servers, "EU-PVE-TheIsland5313")["IP"] == row["IP"]
    assert _score_server(row, row["SessionID"]) > _score_server(row, "TheIsland")


def test_player_count_and_ping_on_resolve(monkeypatch):
    _patch_resolve(monkeypatch, [_row()])
    resolved = resolve_server_status("5313")
    assert resolved.presence == STATUS_ONLINE
    assert resolved.online is True
    assert resolved.num_players == 10
    assert resolved.max_players == 70
    assert resolved.ping == "231 ms"
    assert resolved.version == "v92.43"


def test_online_when_present_in_list(monkeypatch):
    _patch_resolve(monkeypatch, [_row()])
    resolved = resolve_server_status("5313")
    assert resolved.presence == STATUS_ONLINE
    assert resolved.presence_reason == "present_in_official_list"


def test_prune_status_tracker_drops_stale_keys():
    reset_status_tracker()
    from functions.asa_status import note_missing

    note_missing("keep-me")
    note_missing("drop-me")
    assert miss_count("drop-me") == 1
    prune_status_tracker({"keep-me"})
    assert miss_count("keep-me") == 1
    assert miss_count("drop-me") == 0
    reset_status_tracker()


def test_unknown_then_offline_after_consecutive_misses():
    reset_status_tracker()
    snap = parse_server_list([_row()])
    net = _online_network()
    first = get_server_status(
        None,
        snapshot=snap,
        network=net,
        server_key="5313",
        miss_threshold=2,
    )
    assert first.status == STATUS_UNKNOWN
    assert miss_count("5313") == 1
    second = get_server_status(
        None,
        snapshot=snap,
        network=net,
        server_key="5313",
        miss_threshold=2,
    )
    assert second.status == STATUS_OFFLINE
    assert miss_count("5313") == 2


def test_recovery_resets_misses():
    reset_status_tracker()
    snap = parse_server_list([_row()])
    net = _online_network()
    server = parse_asa_server(_row())
    get_server_status(None, snapshot=snap, network=net, server_key="5313", miss_threshold=2)
    recovered = get_server_status(server, snapshot=snap, network=net, server_key="5313")
    assert recovered.status == STATUS_ONLINE
    assert miss_count("5313") == 0


def test_api_failure_is_not_offline():
    reset_status_tracker()
    failed = AsaSnapshot(
        fetch_ok=False,
        fetched_at=datetime.now(timezone.utc),
        error="fetch_failed",
    )
    status = get_server_status(
        None,
        snapshot=failed,
        network=NetworkStatus(fetch_ok=False, online=None, version=None, error="fetch_failed"),
        last_known=parse_asa_server(_row()),
        server_key="5313",
    )
    assert status.status == STATUS_API_UNAVAILABLE
    assert status.from_last_known is True
    assert not status.is_offline


def test_stale_last_updated_is_unknown():
    reset_status_tracker()
    old = datetime.now(timezone.utc) - timedelta(minutes=20)
    row = _row(LastUpdated=int(old.timestamp() * 1000))
    server = parse_asa_server(row)
    snap = parse_server_list([row])
    status = get_server_status(
        server,
        snapshot=snap,
        network=_online_network(),
        stale_seconds=300,
    )
    assert status.status == STATUS_UNKNOWN
    assert status.reason == "stale_last_updated"


def test_stale_age_recomputed_without_reparse():
    """Cached rows keep a frozen parse-time age; status must use last_updated vs now."""
    reset_status_tracker()
    old = datetime.now(timezone.utc) - timedelta(minutes=20)
    row = _row(LastUpdated=int(old.timestamp() * 1000))
    server = parse_asa_server(row)
    cached = replace(server, last_updated_age_seconds=0.0)
    snap = parse_server_list([row])
    now = datetime.now(timezone.utc)
    status = get_server_status(
        cached,
        snapshot=snap,
        network=_online_network(),
        now=now,
        stale_seconds=300,
    )
    assert status.status == STATUS_UNKNOWN
    assert status.reason == "stale_last_updated"


def test_network_status_online_parse():
    parsed = parse_network_status(
        'ARK Official Server Network Status: <RichColor Color="0, 1, 0, 1">Online (v92.43)</>'
    )
    assert parsed.fetch_ok
    assert parsed.online is True
    assert parsed.version == "v92.43"
    assert parsed.label == "ONLINE"


def test_network_status_offline_parse():
    parsed = parse_network_status("ARK Official Server Network Status: Offline")
    assert parsed.online is False
    assert parsed.label == "OFFLINE"


def test_network_offline_does_not_mark_server_offline():
    reset_status_tracker()
    snap = parse_server_list([])
    net = NetworkStatus(fetch_ok=True, online=False, version="v92.43")
    status = get_server_status(
        None,
        snapshot=snap,
        network=net,
        server_key="5313",
        miss_threshold=1,
    )
    assert status.status == STATUS_UNKNOWN
    assert status.reason == "official_network_offline"
    assert not status.is_offline


def test_announcement_dotdot_is_empty():
    assert parse_announcement("..").text is None
    assert parse_announcement("<p>Servers coming down for maintenance</p>").text


def test_missing_unknown_name_not_found(monkeypatch):
    _patch_resolve(
        monkeypatch,
        [],
        bm=_bm(server_id="", name=None, url="", error="not_found", ip=None, max_players=None, map_name=None),
    )
    resolved = resolve_server_status("zzzznotaserver")
    assert resolved.error == "not_found"


def test_bm_fallback_identity_when_missing(monkeypatch):
    _patch_resolve(monkeypatch, [], bm=_bm(status="offline"))
    resolved = resolve_server_status("5313")
    assert resolved.ok
    assert resolved.online is False
    assert resolved.ip == "1.2.3.4"
    assert resolved.bm is not None
    assert resolved.bm.ok


def test_bm_discrepancy_logged_when_status_disagrees(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    _patch_resolve(monkeypatch, [_row()], bm=_bm(status="offline"))
    resolve_server_status("5313")
    assert any("discrepancy" in rec.message for rec in caplog.records)


def test_resolve_fetch_failed_without_last_known(monkeypatch):
    failed = AsaSnapshot(fetch_ok=False, fetched_at=datetime.now(timezone.utc), error="fetch_failed")
    monkeypatch.setattr("functions.server_status.get_snapshot", lambda **_k: failed)
    monkeypatch.setattr("functions.server_status.last_good_snapshot", lambda: None)
    monkeypatch.setattr("functions.server_status.current_network", lambda: None)
    monkeypatch.setattr("functions.server_status.current_announcement", lambda: None)
    resolved = resolve_server_status("5313")
    assert resolved.error == "fetch_failed"
    assert resolved.presence == STATUS_API_UNAVAILABLE
