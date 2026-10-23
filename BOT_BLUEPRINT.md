# BOT_BLUEPRINT.md

**Universal architecture and strategy for Discord bots** built with **Python 3.11+**, **discord.py** (slash/interactions only), and **Neon / Lakebase Postgres**.

Copy this file into every bot repo unchanged. Pair it with a bot-specific **`AGENTS.md`**. This file defines **how** bots are built — not **what** each bot does.

---

## Three documents, three jobs

| File | Scope | Contains |
|------|--------|----------|
| **`BOT_BLUEPRINT.md`** | All bots (same everywhere) | Layout, packages, db workflow, validation, deploy, agent briefing |
| **`AGENTS.md`** | This bot only | Cog list, load order, slash commands, feature env vars, bot-specific tables |
| **`README.md`** | This bot only | Human setup guide and command catalog |

**Do not put bot-specific commands, cogs, or feature folders in this blueprint.** Document those in that bot's `AGENTS.md` and `README.md`.

For a large, filled-in example of the pattern, see **ALICE** (`ALICE/AGENTS.md` + repo layout). ALICE is one bot — not a checklist every other bot must copy.

---

## Non-negotiable rules

1. **Slash commands only** for users. Prefix `!` exists only because discord.py requires it internally — do not add user-facing prefix commands.
2. **Centralize IDs and tunables** in `config.py`. Never scatter guild/channel/role literals in cogs.
3. **Secrets in environment variables** (`.env` locally, host dashboard in production). Never commit tokens or keys.
4. **All persistence through the `db` package** — no raw SQL or ad hoc `psycopg` in command files.
5. **Shared non-cog logic in `functions/` or `commands/common/`** — not copy-pasted across cogs.
6. **`logging` only** for runtime behaviour — no `print`.
7. **Keep `README.md` in sync** when user-visible commands change.
8. **Prefer `command_sync.sync_application_commands`** over ad hoc `bot.tree.sync()` so guild-scoped duplicates stay cleared where configured.
9. **Keep the event loop free** — offload sync Postgres/JSON/HTTP helpers from async handlers with `asyncio.to_thread(...)`. Prefer `interaction.response.defer(...)` before any storage or network work, then `followup`.
10. **Fail closed on startup** — if extension load fails, log, `await bot.close()`, and do **not** mark the bot ready with a half-loaded command tree.
11. **Declare state authority before adding a cache** — a JSON file or object-storage blob must never silently become authoritative for rows owned by Postgres.

---

## Standard project layout

Every bot shares the **skeleton** below. Feature folders under `commands/` are created **only for what that bot needs** — see that bot's `AGENTS.md`.

```
.
├── main.py                 # Entry: bot client, extension load order, login/429 retry, global listeners
├── config.py               # IDs, feature flags, env reads — no secrets hard-coded
├── db/                     # Database package (domain-split; __init__ re-exports full API)
│   ├── __init__.py
│   ├── _base.py            # Client, _tbl, EXPECTED_SCHEMA, check_schema, use_postgres
│   ├── pg_client.py        # psycopg client (PostgREST-shaped table/rpc API)
│   ├── <domain>.py         # One module per table group this bot uses
│   └── sql/                # Canonical DDL + patches (Neon SQL Editor)
│       ├── schema.sql
│       ├── README.md
│       └── probe.py        # Optional connection ping (no db package import)
├── functions/              # Shared bot helpers (optional modules as needed)
│   ├── __init__.py         # Re-exports public API: functions.<name>
│   ├── _base.py            # Logger, locks, tiny shared state
│   ├── checks.py           # Guild/feature guard helpers (if needed)
│   └── <concern>.py        # Logic shared by 2+ cogs — name by purpose, not by copying another bot
├── commands/
│   ├── common/             # Optional cross-cog helpers — NO cog, NO setup()
│   ├── core/               # Optional: help, sync, maintenance, killswitch, extensions loader
│   └── <feature>/          # One folder per feature area THIS bot implements
├── scripts/                # Offline verification scripts (no Discord token required)
├── data/                   # Runtime JSON state (gitignored); created by main.py if used
├── Dockerfile              # Production: CMD ["python", "main.py"]
├── requirements.txt
├── README.md               # Human command catalog + setup
├── BOT_BLUEPRINT.md        # This file — universal architecture (copy to every bot)
└── AGENTS.md               # Bot-specific agent notes (commands, load order, env vars)
```

| Path | Role |
|------|------|
| `main.py` | `commands.Bot`, staggered login / 429 exit+restart, `on_ready` extension load list, maintenance + killswitch gate, global listeners |
| `config.py` | `CHANNELS`, `ROLES`, guild IDs, timeouts, message templates — read env with `os.environ.get` |
| `db/` | All Neon/Postgres access; `EXPECTED_SCHEMA` + `check_schema()` in `db/_base.py` |
| `functions/` | Guards, shared business logic — add modules only when 2+ cogs need the same code |
| `commands/<feature>/` | One or more cogs; each exposes `async def setup(bot)` — **only folders this bot uses** |
| `commands/common/` | Optional helpers (`state.py`, `sticky.py`, `logging.py`) — never loaded as an extension |
| `commands/core/extensions.py` | **`COG_EXTENSIONS`** — single source of truth for extension load order |
| `db/sql/schema.sql` | Source of truth for table DDL |
| `scripts/` | `verify_*.py` smoke tests runnable without the bot online |

### Not every bot has

These appear in some bots (e.g. ALICE) but are **not required** by this blueprint:

- `commands/mod/`, `economy/`, `partner/`, `integrations/` — feature areas, not standard folders
- Sticky-channel embeds (`commands/common/sticky.py`)
- Admin slash commands like `/sync-commands`, `/maintenance`, or `/killswitch` — add only if that bot needs them
- Remote log handler writing to Postgres (`bot_logs`)
- Background `@tasks.loop` jobs
- Restart/redeploy owner DM (`RESTART_NOTIFY_USER_ID`) — also used as the `/killswitch` owner identity when that command is present
- JSON-file storage fallback when `DATABASE_URL` is unset
- Shared multi-bot Neon project (separate databases or schemas per bot)

If a bot does not need something, **omit it** — do not scaffold empty cogs "because the blueprint shows them."

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ (`.python-version` for pyenv) |
| Discord | `discord.py` — interactions / app commands only |
| Database | **Lakebase Postgres via Neon** (`DATABASE_URL` + `psycopg[binary]`) |
| Config | `config.py` for IDs/tunables; `.env` / host vars for secrets |
| Deploy | Docker (`python:3.12-slim`) on Railway or similar worker host |
| Logging | Python `logging`; optional remote handler (e.g. Postgres `bot_logs`) |
| Files | Railway S3 (or Neon Object Storage) — not a hosted REST storage API |

---

## Layer responsibilities

### `main.py`

- Load `.env` **before importing modules that read environment at import time**, then validate required env (exit early with a clear message if missing). Use `load_dotenv(interpolate=False)` when local files may contain Railway `${{service.VAR}}` references.
- Configure logging (console + optional remote handler).
- Create `commands.Bot` with appropriate intents.
- Load extensions in a **fixed, documented order** (listed in that bot's `AGENTS.md`). On failure: log + `bot.close()` — do not continue.
- Sync slash commands **once after cogs load**; retry **global** sync on later `on_ready` only if the first attempt failed. Do **not** re-sync on every Discord reconnect.
- Treat guild-scope clears as **best-effort**; global sync success is what gates “ready”.
- Optional: one restart/redeploy DM per process (`RESTART_NOTIFY_USER_ID`) — not on every reconnect.
- Optional: deploy marker / git SHA in startup logs for host verification.
- On Discord **429** at login: wait, `sys.exit(1)` — let Docker/Railway restart policy retry (see `LOGIN_RETRY_ATTEMPT`).
- Stagger startup (`time.sleep` jitter) to avoid hammering Discord on crash loops.

### `config.py`

- Dicts/constants for Discord IDs (`CHANNELS`, `ROLES`, `CATEGORIES`, guild allowlists).
- Feature tunables (cooldowns, batch sizes, message templates).
- Optional env overrides with sensible defaults.
- **`DATA_DIR`** — path for runtime JSON when the bot uses file-backed state.

### `db/` package

Split by **domain** (one file per table group). Keep each module focused; aim for **< ~400 lines** per file.

| Module | Typical contents |
|--------|------------------|
| `_base.py` | `get_database_url()`, `_get_client()`, `_tbl()`, `_parse_dt()`, `use_postgres()`, `EXPECTED_SCHEMA`, `check_schema()`, package logger |
| `pg_client.py` | `psycopg` client with `table(...).select/eq/insert/update/upsert/delete/execute()` (and optional `rpc`) |
| `<domain>.py` | CRUD/query helpers for related tables |
| `__init__.py` | Re-export **everything** callers use so `import db` / `db.foo()` never breaks |

**Rules:**

- Add DDL to `db/sql/schema.sql` first.
- Update `db/_base.py::EXPECTED_SCHEMA` to match.
- Implement helpers in the appropriate domain module.
- Use `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` for idempotent migrations.
- Offload synchronous `psycopg` calls from async handlers with `asyncio.to_thread(...)`.
- Schema probes should be light: `.select(...).limit(0).execute()` — existence/column check only, not row fetches.
- One-shot data migrations belong in **`db/` helpers + `scripts/*.py` CLI** — not user-facing slash commands.

**When to split:** a single `db.py` is fine for small bots. Once it exceeds ~400–500 lines or mixes unrelated tables, split into `db/` with `__init__.py` re-exports so callers keep using `import db`.

**Storage backends:** new bots use Neon via `DATABASE_URL` (alias `NEON_DATABASE_URL`). Prefer the **pooled** `-pooler` connection string for the long-running bot process; use the **direct** (non-pooler) URL only for schema dumps / one-shot migrations. Some bots may fall back to JSON under `data/` when `DATABASE_URL` is unset — document that in `AGENTS.md`. Do **not** scaffold a Supabase REST client for new bots.

### `functions/` package

Split by **concern**. Same re-export pattern as `db/`. Add modules only when logic is shared across cogs.

| Module | Typical contents |
|--------|------------------|
| `_base.py` | Shared logger, threading locks for atomic read-modify-write |
| `checks.py` | `require_guild(interaction)`, feature-specific guards |
| `<concern>.py` | Business logic shared across cogs — name for this bot's domain |
| `__init__.py` | Explicit `__all__` + re-exports — callers use `functions.<name>` only |

Do **not** put Discord UI (views, modals) here — those belong in `commands/`.

### `commands/<feature>/`

Each **extension** is a Python module or package loaded via `await bot.load_extension("commands.<feature>.<module>")`. Folder names are **your choice** — group by feature, not by copying another bot's tree.

**Single-file cog** (simple features):

```python
class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None: ...

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MyCog(bot))
```

**Package cog** (large features — split when a file exceeds ~400–500 lines or mixes concerns):

```
commands/<feature>/<name>/
├── __init__.py    # setup() registers cog(s), persistent views, cross-cog hooks
├── cog.py         # Slash commands (commands.Cog)
├── views.py       # Buttons, modals, select menus (if needed)
├── _store.py      # Persistence, parsing, reconcile (pure + db) — if needed
└── _shared.py     # Constants, embed builders, matchers — no setup()
```

| Split | Goes in |
|-------|---------|
| Slash handlers | `cog.py` or main feature module |
| Discord UI components | `views.py` |
| DB load/save, parsing, reconcile | `_store.py` |
| Constants, embed builders, matchers | `_shared.py` |
| Extension registration | `__init__.py` → `setup(bot)` |

### `commands/common/` (optional)

Helpers used by multiple cogs. **Never** has `setup()` and **never** loaded as an extension. Skip this folder entirely if nothing is shared.

- **`state.py`** — optional JSON persistence for message ids or small runtime keys in `data/*.json`.
- **`sticky.py`** — optional `StickyMessage` helper when a bot keeps a persistent embed in a channel (see [optional pattern](#sticky-messages--background-tasks-optional-pattern) below).
- **`logging.py`** — optional remote log handler; wire from `main.py` after `load_dotenv()`.

---

## Cog & task conventions

```python
async def cog_load(self) -> None:
    if self._channel_id:
        self._my_loop.start()

def cog_unload(self) -> None:
    self._my_loop.cancel()

@tasks.loop(minutes=1)
async def _my_loop(self) -> None:
    try:
        ...
    except Exception:
        logger.exception("my_loop failed")

@_my_loop.before_loop
async def _before_my_loop(self) -> None:
    await self.bot.wait_until_ready()
```

- Start background work in **`cog_load`**, cancel in **`cog_unload`**.
- Use **`asyncio.get_running_loop().create_task(...)`** inside async hooks — not `self.bot.loop` (fragile before connect).
- Wrap loop bodies in **`try/except`** + `logger.exception` so one failure does not kill the task silently.
- Register **persistent views** in `setup()` via `bot.add_view(...)` when buttons must survive restarts.
- One-shot startup reconcile: `await bot.wait_until_ready()` inside the task, then run.

---

## Extension load order

Order matters for slash registration, persistent views, and log clarity. Define the list once in **`commands/core/extensions.py`** — **only extensions this bot actually loads**:

```python
COG_EXTENSIONS: list[tuple[str, str]] = [
    ("commands.core.help", "Help cog loaded"),
    ("commands.community.daily_message", "Daily message cog loaded"),
    # ... this bot's cogs only — not copied from another repo
]

async def load_all_extensions(bot: commands.Bot) -> None: ...
```

`main.py` calls `load_all_extensions(bot)` on first `on_ready`. Mirror the list in that bot's **`AGENTS.md`**.

**Rules when adding a cog:**

1. Add `async def setup(bot)` to the module/package.
2. Append to **`COG_EXTENSIONS`** in `commands/core/extensions.py`.
3. Document in that bot's **`AGENTS.md`** (command name, purpose, env vars).
4. Update **`README.md`** command catalog.
5. If load order depends on another cog (shared views, DB seed), place it **after** the dependency.

---

## Slash command sync

Most bots use **`commands/core/command_sync.py`** — `sync_application_commands(bot)` clears stale guild-scoped commands where configured, then global sync.

Preferred shape: return a small **`SyncResult`** (guild clears attempted, global count / names, per-phase errors). Callers treat **`global_error is None`** (or `result.ok`) as success.

- Strategy: **global registration only**. Guild-scope `clear_commands` + sync exists only to remove stale per-guild duplicates that would double-list slash entries.
- Startup: sync once after all cogs load; retry on later `on_ready` **only if** global sync failed (rate limit). Do not sync on every reconnect.
- Guild clears are best-effort (log + continue); brief sleep between guild clears helps Discord rate limits.
- Optional admin **`/sync-commands`** cog — force sync; useful during development.
- Optional **`SLASH_SYNC_GUILD_IDS`** in env/config for extra guild-scope clears.
- Register commands **globally** unless there is a deliberate reason for guild scope.

Document which sync/admin commands **this bot** exposes in its `AGENTS.md` — they are not universal.

---

## Slash command gates (maintenance + kill switch)

Optional production controls.

### Maintenance (`main.py`)

Wire maintenance once on the app-command tree in `main.py` (discord.py has no `tree.add_check`):

```python
bot.maintenance_until = None  # datetime (UTC) or None

async def slash_gate_check(interaction: discord.Interaction) -> bool:
    cmd_name = interaction.command.name if interaction.command else None
    if cmd_name in ("maintenance", "sync-commands", "help", "killswitch"):
        return True
    until = getattr(bot, "maintenance_until", None)
    # ... if until is set and still in the future, ephemeral block and return False
    return True

bot.tree.interaction_check = slash_gate_check
```

| Control | Command | Who | Behaviour |
|---------|---------|-----|-----------|
| **Maintenance** | `/maintenance <minutes>` (`0` = off) | Server administrators (typical) | Timed block; still allow `/maintenance`, `/sync-commands`, `/help`, and `/killswitch`. |

Reference shape: **ALICE** (`main.py` gate + `commands/core/utility.py`).

### Kill switch (`commands/core/killswitch.py`)

Ship a dedicated cog that **composes** `tree.interaction_check` and `tree.on_error` around any existing `main.py` gate (Wonderbot pattern). Load the extension **early** in `commands/core/extensions.py`. Do **not** duplicate kill-switch logic in `main.py` once the cog is loaded.

| Control | Command | Who | Behaviour |
|---------|---------|-----|-----------|
| **Kill switch** | `/killswitch on` \| `off` | Bot owner (`RESTART_NOTIFY_USER_ID`; optional `KILLSWITCH_USER_ID` override) | When **on**, **every** slash command is blocked except `/killswitch` (so the owner can turn it **off**). Harder than maintenance — no admin bypass. **Off by default.** Persist `{"enabled": true}` via `db.get_state` / `db.set_state` when Postgres (or remote DB) is configured; otherwise in-memory only (resets on restart). **If persistence fails, do not enable** and do not tell the owner it is on — reply with an ephemeral error and leave the previous state. |

Background event listeners (`on_message`, `@tasks.loop`, etc.) **keep running** — document this in each bot's **`AGENTS.md`**. List `/killswitch` in **`README.md`** / **`AGENTS.md`** when the bot ships it.

---

## Async / interaction reliability

Discord must ACK interactions quickly. Established pattern across reference bots:

1. **`await interaction.response.defer(...)`** (ephemeral when the reply is private) before any DB, file, or outbound HTTP work.
2. Run sync `db.*` / storage helpers via **`await asyncio.to_thread(...)`**.
3. Reply with **`interaction.followup.send(...)`** (or edit the deferred response).
4. Wrap background `@tasks.loop` bodies in `try/except` + `logger.exception` so one failure does not kill the loop.
5. Prefer regression tests that assert command paths call `asyncio.to_thread` for blocking storage (see Sir-5rM8 / ALICE patterns).

Do **not** call blocking `requests` / `psycopg` `.execute()` directly inside async slash handlers or views.

---

## Object-storage JSON cache standard (optional)

Use this pattern only when profiling shows repeated reads, timer scans, or restart recovery justify the extra state layer. A bucket reduces database load only when hot paths actually read memory/JSON instead of querying Postgres; it does not replace correct database indexes or queries.

Bots that adopt this standard ship the same pair of modules (no shared pip package yet): **`functions/json_db_cache.py`** (in-process API + replicas) and **`commands/core/cache_sync.py`** (background reconcile + bucket snapshot loops). List each registered cache key and its authority class in that bot's **`AGENTS.md`**.

### Fleet contract (database-backed keys)

| Layer | Location | Role |
|-------|----------|------|
| **Authority** | Neon/Postgres domain tables | Source of truth for DB-owned rows |
| **Replica** | In-process memory | Hot reads; deep-copied on access |
| **Replica** | `{DATA_DIR}/cache/db/{key}.json` | Local recovery across restarts |
| **Replica** | `STATE_BUCKET` object `cache/db/{key}.json` | Cross-host recovery when S3 credentials are set |

**Non-negotiable:** replicas must never silently become authoritative for Postgres-owned rows. A JSON file or bucket object alone does not justify skipping a failed database read or writing domain tables from cache.

**Envelope v2** (persisted shape): `version` (2), `written_at` (unix seconds), `generation` (uuid hex), `source` (provenance string), `data` (payload). v1 envelopes may be read for migration; invalid or corrupt copies are ignored. When local and bucket copies both exist, keep the freshest by `(written_at, version)`.

**Lifecycle**

1. **Reads:** memory → local JSON → bucket → database loader on a complete miss (`get` / `update`).
2. **Writes:** commit the domain write in Postgres, verify success, then `put` or `update` replicas. A replica write failure does not roll back the database; mark the key dirty and retry (`retry_dirty`, bucket snapshot loop).
3. **Startup:** `cache_sync` waits for bot ready, then **startup grace** (`JSON_CACHE_STARTUP_GRACE_SECONDS` + jitter) before the first hourly reconcile — persisted replicas may serve during grace, but reconciliation always refreshes from the database.
4. **Background:** at least **hourly** DB reconcile (`verify_due` via `verify_cached_db_state`); **periodic bucket snapshot** of dirty/pending keys (`JSON_CACHE_BUCKET_SNAPSHOT_SECONDS`, default 60s) without extra database reads.

**Public API (`functions/json_db_cache`)**

| Symbol | Purpose |
|--------|---------|
| `get(key, loader)` | Load through replicas; call `loader` only on miss |
| `put(key, value)` | After successful DB write |
| `update(key, loader, mutator)` | Per-key locked read-modify-write |
| `update_loaded(key, mutator)` | Mutate only if already in memory or on disk |
| `peek` / `has` | Introspection without hitting the database |
| `verify` / `verify_due` | Refresh from DB; repair mismatches |
| `retry_dirty` / `snapshot_loaded_to_bucket` | Replica persistence recovery |
| `stats_snapshot` / `diagnostics_snapshot` | Local observability |
| `ENVELOPE_VERSION`, `MISSING` | Contract constants |

Greenfield bots without tables yet (e.g. **W0nd3r**): follow this contract in **`AGENTS.md`** only; add the modules when the first database-backed cache keys exist.

### Classify every object by authority

| Class | Examples | Authority | Repair direction |
|-------|----------|-----------|------------------|
| **Database-backed derived cache** | Guild config, destinations, subscriptions, deadlines, aggregate counts | Neon/Postgres domain tables | **DB → cache only** |
| **External-source snapshot** | Last-known-good third-party API/CDN response | Upstream service | **upstream → cache** |
| **Cache-owned durable state** | Dedupe token, sticky message locator, resumable cursor | Explicitly documented bucket object | Bucket/object storage |

Do not mix classes in one document. List every object key and its authority in the bot's `AGENTS.md`. A table such as `bot_state_blobs` may back up cache documents, but it is not authority for domain records.

### Required semantics

1. **Database-first writes:** commit the domain write, verify success, then update memory/local/bucket copies. A cache write failure must not roll back a successful domain write; mark the key dirty and retry.
2. **Strict authoritative reads:** distinguish “query succeeded with zero rows” from “query failed.” A failed seed/reconcile must keep the old cache, remain unseeded, and retry with bounded backoff.
3. **Stale-while-revalidate startup:** memory → local JSON → bucket → database on a complete miss. A persisted hit may serve during a short startup grace, then trigger a jittered DB verification. Do not trust restart-loaded JSON for a blind hour.
4. **Authority-safe repair:** repair database-backed objects only from DB to JSON. Never flush bucket data into domain tables. Re-check authoritative state immediately before destructive or terminal actions; use conditional updates/claims for deadlines and queues.
5. **Versioned envelope:** persist at least `version`, `written_at`, and `data`; add `source_revision` or `generation` when available. Read legacy formats only for migration. When local and bucket copies both exist, validate both and choose the freshest; corrupt copies fall through.
6. **Atomic in-process access:** use per-key locks, single-flight loaders, deep copies, and an atomic `update(key, mutator)` API. Serialize persistence per key and write local files with a unique temporary file plus `os.replace`.
7. **Multi-replica safety:** process locks do not protect multiple workers. Use database atomic operations, object generations/ETags with compare-and-swap, or a distributed lock. Otherwise deploy exactly one writer and document that constraint.
8. **Failure recovery:** track dirty keys, retry failed bucket/local writes with bounded jitter, and preserve write ordering so an older async write cannot overwrite a newer generation.
9. **Bucket isolation:** use a dedicated bucket and credentials per bot. If infrastructure forces a shared bucket, use bot-specific prefixes plus credentials restricted to that prefix. Never give two bots unrestricted credentials to each other's state.
10. **Runtime hygiene:** ignore `data/cache/` (and equivalent runtime state) in Git. Never commit guild IDs, user IDs, reminders, or other runtime snapshots.
11. **Non-blocking Discord paths:** all local file, bucket, and database I/O called from async code runs through `asyncio.to_thread(...)`.
12. **Local observability:** count hits by source, cache age, DB loads, repairs, dirty retries, failures, and queries avoided. Log summaries locally; do not send routine INFO cache telemetry back into the database being protected.

### Timer and delivery rules

- Cache `next_check_at` / nearest deadline and use explicit wake hooks instead of scanning Postgres every busy tick.
- Before ending an auction, giveaway, job, or lease, atomically confirm that the DB row is still active and due.
- Claim work idempotently. For reminders/notifications, persist a sent/claimed transition before removing the cache item; delete only after the authoritative transition succeeds.
- Paginate authoritative seeds. A fixed first-page limit can silently lose deadlines.

### Minimum offline tests

- Legacy/current envelope decode, corruption fallback, and freshest-copy selection
- Failed seed retries without replacing state with empty data
- DB → cache reconciliation and no cache → domain-table repair
- Single-flight miss loading and concurrent atomic mutations
- Failed persistence, dirty retry, and stale-write ordering
- Startup stale-while-revalidate timing
- Terminal deadline revalidation and idempotent delivery/claim behavior
- `asyncio.to_thread` delegation for blocking Discord paths

No cache test may require a Discord token, network, object storage, or a live database.

---

## Database workflow

1. Create a Neon project; copy the **pooled** (`-pooler`) connection string into `DATABASE_URL` (`sslmode=require`).
2. Design table → add **`CREATE TABLE IF NOT EXISTS`** to `db/sql/schema.sql`.
3. Apply `schema.sql` in the **Neon SQL Editor** (or `psql "$DATABASE_URL_UNPOOLED" -f db/sql/schema.sql` with the **direct** URL).
4. Add table + columns to **`db/_base.py::EXPECTED_SCHEMA`**.
5. Implement helpers in **`db/<domain>.py`**.
6. Note the change in **`db/sql/README.md`**.
7. Validate: `db.check_schema()` (requires live `DATABASE_URL` in env).

Never skip the `EXPECTED_SCHEMA` step — `check_schema()` is the guardrail against drift.

For a **new bot**, design tables for that bot's features only. Do **not** copy another bot's tables unless you explicitly share a database.

### Shared Neon project (optional multi-bot pattern)

Several bots may share one Neon project with **separate databases** (or schemas) per bot. In that setup:

- Give each bot its own `DATABASE_URL` (its own database on the project, or its own Neon project).
- Keep a privileged / owner role for backups and migrations only.
- Document project, database name, and owned tables in that bot's **`AGENTS.md`** / `db/sql/README.md`.
- Data migrations: CLI scripts under `scripts/` (or `db/migrate_*.py` called by scripts) — remove temporary slash migrate commands once cutover is done.

---

## Environment variables

### Required (typical bots on this stack)

| Variable | Purpose |
|----------|---------|
| `TOKEN` | Discord bot token |
| `DATABASE_URL` | Neon pooled connection string (`postgresql://…@…-pooler.…/…?sslmode=require`) |

### Auth alternatives

| Variable | Purpose |
|----------|---------|
| `NEON_DATABASE_URL` | Alias for `DATABASE_URL` if the host injects that name |

### Common optional

| Variable | Purpose |
|----------|---------|
| `SLASH_SYNC_GUILD_IDS` | Comma-separated guild IDs for guild-scope command clear |
| `RESTART_NOTIFY_USER_ID` | Discord user to DM once when the process comes online; empty disables. Default identity for `/killswitch` when that command is present. |
| `KILLSWITCH_USER_ID` | Optional override for who may run `/killswitch` (when set, takes precedence over `RESTART_NOTIFY_USER_ID`). |
| `DATA_DIR` | Runtime JSON / log directory when used |
| `STATE_BUCKET`, `STATE_ACCESS_KEY_ID`, `STATE_SECRET_ACCESS_KEY` | Dedicated S3-compatible cache bucket and its exact credentials, when the optional cache standard is used |
| `JSON_CACHE_STARTUP_GRACE_SECONDS`, `JSON_CACHE_STARTUP_JITTER_SECONDS`, `JSON_CACHE_BUCKET_SNAPSHOT_SECONDS`, `JSON_CACHE_RECONCILE_SECONDS` | Startup grace before first DB reconcile, jitter, coalesced bucket snapshots, and minimum hourly authoritative reconciliation |
| `LOGIN_RETRY_ATTEMPT` | **Internal** — 429 retry counter; do not set manually |

Feature-specific vars (channel IDs, API keys, intervals, etc.) belong in that bot's **`README.md`** and **`AGENTS.md`** — not in this file.

---

## Local setup

```bash
python3.11 --version          # 3.11+ required (.python-version in repo for pyenv)
pip install -r requirements.txt
# create .env with TOKEN and DATABASE_URL (Neon pooled string)
python main.py
```

---

## Validation (run before every PR / deploy)

### 1. Syntax

```bash
python -m compileall main.py config.py db functions commands scripts
```

### 2. Lint (project source only — exclude `.venv`)

```bash
python -m pyflakes main.py config.py db functions commands scripts
```

### 3. Extension smoke test

Load every extension into a bare `commands.Bot` and confirm zero failures. All slash commands should register with no duplicate names.

### 4. Schema (when DB touched)

```bash
python -c "import db; print(db.check_schema())"
```

All tables should return `(name, True, None)`.

### 5. Feature scripts

Run relevant `scripts/verify_*.py` for the area you changed.

### 6. Reference resolution (after package splits)

Grep for `db.<name>` and `functions.<name>` usages; confirm every name exists on the package via `hasattr`.

### 7. Pytest

```bash
pip install -r requirements-dev.txt
pytest -q
```

Offline tests live in `tests/`; they never require a Discord token or live database. Feature scripts in `scripts/verify_*.py` provide additional integration checks without Discord.

### 8. Scaffold a new bot repo

From a repo that ships `scripts/scaffold_bot.py` (e.g. **ALICE**):

```bash
python scripts/scaffold_bot.py /path/to/NewBot --name "New Bot"
```

Creates layout + stub files. Copy **`BOT_BLUEPRINT.md`**, write a fresh **`AGENTS.md`** for that bot's features only, and register cogs in **`COG_EXTENSIONS`**.

---

## Deployment (Docker / Railway)

- **`Dockerfile`**: `FROM python:3.12-slim`, `CMD ["python", "main.py"]`, `PYTHONUNBUFFERED=1`.
- **Railway**: connect repo, set env vars in dashboard (`TOKEN`, `DATABASE_URL`), deploy on push to `main`.
- **"Stopping Container"** during deploy is normal — Railway stops the old instance before starting the new one. If the bot is online in Discord after ~1–2 minutes, the deploy succeeded.
- **Crash loop?** Check deploy logs for: missing env vars, import errors, Discord 429 (bot exits and Railway restarts — usually clears).
- **No HTTP port required** — Discord bots are outbound-only; Railway works fine with a worker-style service.

---

## Change checklist

When adding or modifying features in any bot:

- [ ] IDs/tunables in `config.py` (not literals in cogs)
- [ ] DB changes: `schema.sql` + `EXPECTED_SCHEMA` + domain module + `db/sql/README.md`
- [ ] Cached state: authority class documented; DB-first writes; strict seed/reconcile; versioned envelope; dirty retry; isolated bucket
- [ ] Async paths: `defer` + `asyncio.to_thread` for blocking storage/HTTP
- [ ] Cog added to **`commands/core/extensions.py`** (`COG_EXTENSIONS`); load failure remains fail-closed
- [ ] **`AGENTS.md`** updated (load order, commands, feature env vars)
- [ ] **`README.md`** updated if user-visible commands changed
- [ ] Validation steps above pass
- [ ] No secrets committed
- [ ] One-shot migrations are CLI scripts — not permanent slash commands

---

## Briefing a coding agent

### New bot (greenfield)

> I'm starting a brand-new Discord bot. Follow **`BOT_BLUEPRINT.md`**: Python 3.11+, discord.py slash-only, `main.py` + `config.py` + `db/` package + `functions/` (as needed) + `commands/<feature>/` cogs + `db/sql/schema.sql` + `EXPECTED_SCHEMA`. Persist with **Neon** via `DATABASE_URL` and `psycopg` (`db/pg_client.py`). Create a bot-specific **`AGENTS.md`** listing only the cogs and slash commands for **this** bot. Do **not** copy commands, cogs, or feature folders from my other bots. For v1, here are the features I want: … (list). Create skeleton, requirements, `.env` docs, empty cogs with `setup()`, and README command section. Do not add object-storage JSON caching until a hot-read need is identified; when added, keep Neon authoritative for domain state and use a dedicated bucket.

### Existing bot

> Follow **`BOT_BLUEPRINT.md`** for architecture and validation. Follow this repo's **`AGENTS.md`** for bot-specific commands, load order, and env vars. Preserve public import paths (`import db`, `import functions`, extension names). Split large files into packages with `__init__.py` re-exports rather than changing callers. Keep slash handlers non-blocking (`defer` + `asyncio.to_thread`); fail closed if extension load fails.

### Starting from ALICE as template

> Copy **`BOT_BLUEPRINT.md`** and use **ALICE** (`AGENTS.md` + repo structure) as one reference implementation. **Strip** ALICE-specific cogs, tables, and commands; keep only the package layout and conventions that this new bot actually needs. Use Neon (`DATABASE_URL` + `psycopg`); do not add a Supabase client unless this bot still documents a cutover fallback in `AGENTS.md`.

---

## Sticky messages & background tasks (optional pattern)

Use only when a bot needs a persistent embed in a channel:

1. Store message id in `data/<feature>_message.json` via optional `commands/common/state.py`.
2. Use optional `commands/common/sticky.py` (`StickyMessage`) for recover/ensure/repost.
3. Run verify/refresh loops with `@tasks.loop` in the feature cog.
4. Optional: purge unrelated messages in the same channel (cog-specific sweep logic).

State can also live in the DB when multiple instances or durability matters. Sticky locators are cache-owned; domain data remains DB-owned. Follow the object-storage cache standard above if the locator is mirrored to a bucket. Many bots never need this — skip it unless required.

---

## Package split decision guide

| Situation | Action |
|-----------|--------|
| File < ~400 lines, single concern | Keep as one module |
| File > ~500 lines or mixed UI + DB + tasks | Split into package |
| Helper used by 2+ cogs, no Discord UI | `functions/` or `commands/common/` |
| All DB access | `db/<domain>.py` only |
| After split | Re-export from `__init__.py`; grep callers; run extension smoke test |

Preserve **`import db`**, **`import functions`**, and extension paths — never force a repo-wide import rewrite unless intentional.
