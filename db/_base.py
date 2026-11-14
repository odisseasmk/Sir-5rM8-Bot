"""Database client selection, schema checks, and shared helpers."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("db")

EXPECTED_SCHEMA: dict[str, list[str]] = {
    "guild_rate_notifications": ["guild_id", "channel_id", "role_id"],
    "rate_state": ["id", "previous_rates"],
    "bothunter_config": [
        "guild_id",
        "channel_id",
        "log_channel_id",
        "action",
        "warning_msg_id",
        "experiments",
        "warning_message",
        "dm_message",
        "log_message",
        "reinvite_code",
    ],
    "bothunter_events": ["id", "guild_id", "user_id", "channel_id", "created_at"],
    "server_watchlist": ["server_key", "session_name", "last_queried", "created_at"],
    "server_player_samples": [
        "id",
        "server_key",
        "num_players",
        "max_players",
        "sampled_at",
    ],
    "server_up_notify": [
        "server_key",
        "user_id",
        "channel_id",
        "guild_id",
        "query",
        "session_name",
        "created_at",
    ],
    "guild_ark_notifications": ["guild_id", "channel_id"],
    "ark_notification_state": ["id", "previous_text"],
    "twitch_stream_pinged": ["twitch_login", "stream_id"],
    "twitch_stream_watchlist": ["twitch_login"],
    "bot_runtime_state": ["key", "value", "updated_at"],
}

_client: Any = None


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def get_database_url() -> str:
    return _first_env("DATABASE_URL", "NEON_DATABASE_URL")


def get_turso_database_url() -> str:
    return _first_env("TURSO_DATABASE_URL", "LIBSQL_URL")


def get_turso_auth_token() -> str:
    return _first_env("TURSO_AUTH_TOKEN", "LIBSQL_AUTH_TOKEN")


def turso_configured() -> bool:
    return bool(get_turso_database_url() and get_turso_auth_token())


def turso_active() -> bool:
    """Turso is the storage backend only when explicitly enabled."""
    if not turso_configured():
        return False
    flag = _first_env("TURSO_ACTIVE", "USE_TURSO").lower()
    return flag in ("1", "true", "yes", "on")


def get_postgrest_url() -> str:
    return _first_env("POSTGREST_URL", "SUPABASE_URL")


def get_postgrest_key() -> str:
    return _first_env("POSTGREST_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY")


def get_postgrest_jwt() -> str:
    return _first_env("POSTGREST_JWT", "SUPABASE_BOT_JWT")


def get_postgrest_anon_key() -> str:
    return _first_env("POSTGREST_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY")


def use_postgres() -> bool:
    """Prefer Postgres when DATABASE_URL is set."""
    return bool(get_database_url())


def use_postgrest() -> bool:
    """Postgres REST fallback when DATABASE_URL is unset."""
    if use_postgres():
        return False
    if not get_postgrest_url():
        return False
    if get_postgrest_key():
        return True
    return bool(get_postgrest_jwt() and get_postgrest_anon_key())


def storage_backend_name() -> str:
    if turso_active():
        return "turso"
    if use_postgres():
        return "postgres"
    if use_postgrest():
        return "postgrest"
    return "files"


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    if not use_postgrest():
        raise RuntimeError("Postgres REST is not configured (POSTGREST_URL and key required).")
    from db.postgrest_client import create_bot_postgrest_client

    _client = create_bot_postgrest_client()
    return _client


def _tbl(name: str) -> Any:
    return _get_client().table(name)


def check_schema() -> list[tuple[str, bool, Optional[str]]]:
    """Verify EXPECTED_SCHEMA tables exist with required columns."""
    if not EXPECTED_SCHEMA:
        return []

    if use_postgres():
        return _check_schema_postgres()
    if not use_postgrest():
        return [(name, False, "No remote database configured") for name in EXPECTED_SCHEMA]
    return _check_schema_postgrest()


def _check_schema_postgres() -> list[tuple[str, bool, Optional[str]]]:
    results: list[tuple[str, bool, Optional[str]]] = []
    try:
        from db.postgres import _conn
    except Exception as exc:
        return [(name, False, str(exc)) for name in EXPECTED_SCHEMA]

    try:
        with _conn() as conn:
            for table, columns in EXPECTED_SCHEMA.items():
                try:
                    cols = ", ".join(columns)
                    conn.execute(f"SELECT {cols} FROM {table} LIMIT 0")
                    results.append((table, True, None))
                except Exception as exc:
                    results.append((table, False, str(exc)))
    except Exception as exc:
        return [(name, False, str(exc)) for name in EXPECTED_SCHEMA]
    return results


def _check_schema_postgrest() -> list[tuple[str, bool, Optional[str]]]:
    results: list[tuple[str, bool, Optional[str]]] = []
    try:
        client = _get_client()
    except Exception as exc:
        return [(name, False, str(exc)) for name in EXPECTED_SCHEMA]

    for table, columns in EXPECTED_SCHEMA.items():
        try:
            client.table(table).select(",".join(columns)).limit(0).execute()
            results.append((table, True, None))
        except Exception as exc:
            results.append((table, False, str(exc)))
    return results
