#!/usr/bin/env python3
"""
Copy Sir-5rM8 state from Neon/Postgres (DATABASE_URL) into Turso.

Usage:
  export DATABASE_URL=postgresql://...
  export TURSO_DATABASE_URL=libsql://...
  export TURSO_AUTH_TOKEN=...

  python scripts/migrate_neon_to_turso.py --apply-schema
  python scripts/migrate_neon_to_turso.py                 # dry-run counts from Neon
  python scripts/migrate_neon_to_turso.py --apply
  python scripts/migrate_neon_to_turso.py --apply --force
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

SCHEMA_FILE = ROOT / "turso" / "schema.sql"

BOT_TABLES = (
    "guild_rate_notifications",
    "rate_state",
    "bothunter_config",
    "bothunter_events",
    "server_watchlist",
    "server_player_samples",
    "server_up_notify",
    "guild_ark_notifications",
    "ark_notification_state",
    "twitch_stream_pinged",
    "twitch_stream_watchlist",
    "bot_runtime_state",
)


def _collect_from_postgres() -> dict:
    from db._base import get_database_url

    url = get_database_url()
    if not url:
        raise SystemExit("Set DATABASE_URL to your Neon/Postgres connection string.")

    import psycopg
    from psycopg.rows import dict_row

    payload: dict = {}
    with psycopg.connect(url, row_factory=dict_row) as conn:
        for table in BOT_TABLES:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            payload[table] = [dict(row) for row in rows]
    return payload


def _print_summary(payload: dict, label: str) -> None:
    print(f"\n{label}")
    for table in BOT_TABLES:
        rows = payload.get(table, [])
        print(f"  {table}: {len(rows)} row(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Sir-5rM8 from Neon to Turso.")
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Create tables on Turso (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy data from DATABASE_URL into Turso.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow import when Turso already has rows.",
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        metavar="PATH",
        help="Write Neon export to JSON (for inspection; do not commit).",
    )
    args = parser.parse_args()

    from db._base import turso_configured

    if (args.apply_schema or args.apply) and not turso_configured():
        print(
            "Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN before applying to Turso.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.apply_schema:
        from db.turso_client import apply_schema

        sql = SCHEMA_FILE.read_text(encoding="utf-8")
        apply_schema(sql)
        print(f"Applied schema from {SCHEMA_FILE}")
        if not args.apply:
            print("\nSchema applied. Re-run with --apply to copy data from Neon.")
            return

    payload = _collect_from_postgres()
    if args.export_json:
        args.export_json.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Wrote export to {args.export_json}")

    _print_summary(payload, "Neon/Postgres source")

    if not args.apply:
        print("\nDry run only — re-run with --apply-schema --apply to load Turso.")
        return

    from db.turso_client import import_payload

    counts = import_payload(payload, force=args.force)
    print("\nMigration applied successfully.")
    print("Turso row counts:", counts)
    print(
        "\nNext steps:\n"
        "  1. Keep DATABASE_URL on the bot (Neon remains active).\n"
        "  2. Set TURSO_* on Railway and leave TURSO_ACTIVE unset (standby).\n"
        "  3. When ready to cut over: set TURSO_ACTIVE=1 and remove DATABASE_URL (future)."
    )


if __name__ == "__main__":
    main()