"""Turso (libSQL) connection helpers — standby until TURSO_ACTIVE=1."""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any, Iterator

from db._base import get_turso_auth_token, get_turso_database_url, turso_configured

try:
    import libsql_client
except ImportError as exc:  # pragma: no cover
    libsql_client = None  # type: ignore[assignment]
    _IMPORT_ERROR: Exception | None = exc
else:
    _IMPORT_ERROR = None


def _require_libsql() -> Any:
    if libsql_client is None:
        raise RuntimeError(
            "libsql-client is required for Turso. pip install libsql-client"
        ) from _IMPORT_ERROR
    return libsql_client


@contextmanager
def turso_client() -> Iterator[Any]:
    """Open a synchronous libSQL client (caller must not use when Turso is unset)."""
    url = get_turso_database_url()
    token = get_turso_auth_token()
    if not url or not token:
        raise RuntimeError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set")
    mod = _require_libsql()
    client = mod.create_client_sync(url=url, auth_token=token)
    try:
        yield client
    finally:
        client.close()


def check_connection() -> None:
    """Lightweight Turso ping (inactive standby — does not affect storage backend)."""
    with turso_client() as client:
        client.execute("SELECT 1 FROM rate_state WHERE id = 1 LIMIT 1")


def apply_schema(schema_sql: str) -> None:
    """Run turso/schema.sql statements one at a time."""
    statements = [
        stmt.strip()
        for stmt in re.split(r";\s*\n", schema_sql)
        if stmt.strip() and not stmt.strip().startswith("--")
    ]
    with turso_client() as client:
        for stmt in statements:
            if stmt.upper().startswith("PRAGMA"):
                client.execute(stmt)
                continue
            client.execute(stmt)


def table_counts(client: Any) -> dict[str, int]:
    tables = [
        "guild_rate_notifications",
        "bothunter_config",
        "bothunter_events",
        "server_watchlist",
        "server_player_samples",
        "server_up_notify",
        "guild_ark_notifications",
        "twitch_stream_pinged",
        "twitch_stream_watchlist",
        "bot_runtime_state",
    ]
    counts: dict[str, int] = {}
    for table in tables:
        row = client.execute(f"SELECT COUNT(*) AS n FROM {table}").rows
        counts[table] = int(row[0][0]) if row else 0
    rate_row = client.execute(
        "SELECT previous_rates IS NOT NULL FROM rate_state WHERE id = 1"
    ).rows
    counts["rate_state_has_data"] = int(bool(rate_row and rate_row[0][0]))
    return counts


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def import_payload(payload: dict[str, Any], *, force: bool = False) -> dict[str, int]:
    """Upsert a full Neon export into Turso."""
    with turso_client() as client:
        counts = table_counts(client)
        has_data = any(
            counts.get(k, 0)
            for k in counts
            if k != "rate_state_has_data"
        ) or counts.get("rate_state_has_data")
        if has_data and not force:
            raise RuntimeError(
                "Turso already has data. Re-run with --force to overwrite/upsert."
            )

        for row in payload.get("guild_rate_notifications", []):
            client.execute(
                """
                INSERT INTO guild_rate_notifications (guild_id, channel_id, role_id)
                VALUES (?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                  channel_id = excluded.channel_id,
                  role_id = excluded.role_id
                """,
                [
                    str(row["guild_id"]),
                    str(row["channel_id"]),
                    str(row["role_id"]),
                ],
            )

        for row in payload.get("rate_state", []):
            client.execute(
                """
                INSERT INTO rate_state (id, previous_rates)
                VALUES (1, ?)
                ON CONFLICT (id) DO UPDATE SET previous_rates = excluded.previous_rates
                """,
                [_json_text(row.get("previous_rates"))],
            )

        for row in payload.get("bothunter_config", []):
            client.execute(
                """
                INSERT INTO bothunter_config (
                  guild_id, channel_id, log_channel_id, action, warning_msg_id,
                  experiments, warning_message, dm_message, log_message, reinvite_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                  channel_id = excluded.channel_id,
                  log_channel_id = excluded.log_channel_id,
                  action = excluded.action,
                  warning_msg_id = excluded.warning_msg_id,
                  experiments = excluded.experiments,
                  warning_message = excluded.warning_message,
                  dm_message = excluded.dm_message,
                  log_message = excluded.log_message,
                  reinvite_code = excluded.reinvite_code
                """,
                [
                    str(row["guild_id"]),
                    row.get("channel_id"),
                    row.get("log_channel_id"),
                    row.get("action") or "softban",
                    row.get("warning_msg_id"),
                    _json_text(row.get("experiments") or []),
                    row.get("warning_message"),
                    row.get("dm_message"),
                    row.get("log_message"),
                    row.get("reinvite_code"),
                ],
            )

        for row in payload.get("bothunter_events", []):
            client.execute(
                """
                INSERT INTO bothunter_events (id, guild_id, user_id, channel_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                  guild_id = excluded.guild_id,
                  user_id = excluded.user_id,
                  channel_id = excluded.channel_id,
                  created_at = excluded.created_at
                """,
                [
                    int(row["id"]),
                    str(row["guild_id"]),
                    str(row["user_id"]),
                    row.get("channel_id"),
                    row.get("created_at"),
                ],
            )

        for row in payload.get("server_watchlist", []):
            client.execute(
                """
                INSERT INTO server_watchlist (server_key, session_name, last_queried, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (server_key) DO UPDATE SET
                  session_name = excluded.session_name,
                  last_queried = excluded.last_queried
                """,
                [
                    str(row["server_key"]),
                    row.get("session_name"),
                    row.get("last_queried"),
                    row.get("created_at"),
                ],
            )

        for row in payload.get("server_player_samples", []):
            client.execute(
                """
                INSERT INTO server_player_samples
                  (id, server_key, num_players, max_players, sampled_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                  server_key = excluded.server_key,
                  num_players = excluded.num_players,
                  max_players = excluded.max_players,
                  sampled_at = excluded.sampled_at
                """,
                [
                    int(row["id"]),
                    str(row["server_key"]),
                    int(row["num_players"]),
                    int(row["max_players"]),
                    row.get("sampled_at"),
                ],
            )

        for row in payload.get("server_up_notify", []):
            client.execute(
                """
                INSERT INTO server_up_notify
                  (server_key, user_id, channel_id, guild_id, query, session_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (server_key, user_id, channel_id) DO UPDATE SET
                  guild_id = excluded.guild_id,
                  query = excluded.query,
                  session_name = excluded.session_name,
                  created_at = excluded.created_at
                """,
                [
                    str(row["server_key"]),
                    str(row["user_id"]),
                    str(row["channel_id"]),
                    row.get("guild_id"),
                    row.get("query"),
                    row.get("session_name"),
                    row.get("created_at"),
                ],
            )

        for row in payload.get("guild_ark_notifications", []):
            client.execute(
                """
                INSERT INTO guild_ark_notifications (guild_id, channel_id, last_message_id)
                VALUES (?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                  channel_id = excluded.channel_id,
                  last_message_id = excluded.last_message_id
                """,
                [
                    str(row["guild_id"]),
                    str(row["channel_id"]),
                    row.get("last_message_id"),
                ],
            )

        for row in payload.get("ark_notification_state", []):
            client.execute(
                """
                INSERT INTO ark_notification_state (id, previous_text)
                VALUES (1, ?)
                ON CONFLICT (id) DO UPDATE SET previous_text = excluded.previous_text
                """,
                [row.get("previous_text")],
            )

        for row in payload.get("twitch_stream_pinged", []):
            client.execute(
                """
                INSERT INTO twitch_stream_pinged (twitch_login, stream_id)
                VALUES (?, ?)
                ON CONFLICT (twitch_login) DO UPDATE SET stream_id = excluded.stream_id
                """,
                [str(row["twitch_login"]).lower(), str(row["stream_id"])],
            )

        for row in payload.get("twitch_stream_watchlist", []):
            client.execute(
                """
                INSERT INTO twitch_stream_watchlist (twitch_login, created_at)
                VALUES (?, ?)
                ON CONFLICT (twitch_login) DO NOTHING
                """,
                [str(row["twitch_login"]).lower(), row.get("created_at")],
            )

        for row in payload.get("bot_runtime_state", []):
            client.execute(
                """
                INSERT INTO bot_runtime_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                [
                    str(row["key"]),
                    _json_text(row.get("value") or {}),
                    row.get("updated_at"),
                ],
            )

        return table_counts(client)


def turso_ready() -> bool:
    return turso_configured() and _IMPORT_ERROR is None