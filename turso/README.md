# Turso setup (standby)

Sir-5rM8 can mirror bot state into **Turso** (libSQL) while **Neon/Postgres**
remains the live backend via `DATABASE_URL`.

## 1. Create a Turso database

Create a database in the [Turso console](https://turso.tech/) and note:

- Database URL (`libsql://…`)
- Auth token

## 2. Environment

```env
DATABASE_URL=postgresql://...          # Neon — still authoritative
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
# TURSO_ACTIVE=0                       # omit or 0 = inactive (default)
```

With only `TURSO_*` set, startup logs **Turso standby connection OK** and keeps
using Postgres for reads/writes.

## 3. Schema + data migration

```bash
pip install -r requirements.txt

python scripts/migrate_neon_to_turso.py --apply-schema
python scripts/migrate_neon_to_turso.py                 # dry-run
python scripts/migrate_neon_to_turso.py --apply-schema --apply
```

Schema source: [`turso/schema.sql`](schema.sql).

On Railway, run the same commands in a one-off shell with `DATABASE_URL` and
`TURSO_*` set on the Sir-5rM8 service.

## 4. Cutover (later)

Full `db` backend on Turso is not enabled in this phase. When it ships:

1. Verify Turso data matches Neon.
2. Set `TURSO_ACTIVE=1`.
3. Remove `DATABASE_URL`.

Until then, leave `TURSO_ACTIVE` unset.