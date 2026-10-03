# Changelog

## [Unreleased]

### Features

### Fixes

### Docs

## [1.8.3] - 2026-10-03

### Fixes

- Lower default ASA poll/cache TTL to 120s and look up up-notify servers without rebuilding the full ~3k-row dict list each minute (cuts allocator churn / RSS pressure)
- Lazy-load Pillow chart rendering until `/serverstatus` or an up-notify send needs a PNG
- Log guild/channel/role footprint on ready to make multi-guild RAM drivers visible
- Deploy marker `v1.8.3`

### Docs

- Document ASA poll/TTL defaults as 120 seconds

## [1.8.0] - 2026-08-31

### Features

- Post official server-removal notices as red alerts and replace stale countdown messages
- Deploy marker `v1.8.0`

## [1.7.0] - 2026-08-29

### Features

- Full `/streamers` flow: database watchlist persistence, STATE_BUCKET ping dedupe, notify buttons, and go-live polling with `@here` fallback
- Deploy marker `v1.7.0`

## [1.6.2] - 2026-08-28

### Fixed

- Suppress ASA notification messages containing `ExecDisableFullCrashDumps`
- Deploy marker `v1.6.2`

## [1.6.1] - 2026-08-28

### Fixed

- Suppress ASA notification messages containing `ExecEnableFullCrashDumps`
- Treat 1–15 minute restart notices as countdown replacements, including skipped steps like 4 minutes
- Deploy marker `v1.6.1`

## [1.6.0] - 2026-08-25

### Added

- Twitch go-live notifications and the `/streamers add`, `/streamers list`, `/streamers remove`, and `/streamers setup` command group
- Twitch watchlist and ping deduplication persisted in the Railway state bucket
- Deploy marker `v1.6.0`

## [1.5.0] - 2026-08-23

### Added

- JSON copies of Neon-backed rates, ARK notifications, Bothunter configuration/counters, and pending server-up notifications
- Hourly Neon reconciliation repairs stale JSON cache copies while keeping Neon authoritative
- Cache-aware writes update Neon first, then persist the successful value locally and in the Railway bucket
- Deploy marker `v1.5.0`

### Changed

- Cache files use backward-compatible v2 envelopes with freshness metadata, newest-copy selection, per-key single-flight updates, dirty-write retries, and process-local statistics
- Startup uses a configurable jittered stale-while-revalidate grace (10–30 seconds by default) instead of trusting persisted state for one hour
- Railway setup now requires a dedicated Sir-5rM8 state bucket and documents the `cache/` and `state/` object prefixes

### Fixed

- Bothunter events keep aggregate and channel-specific cached counts in sync without double-incrementing events that have no channel
- Sticky state bucket and local writes are offloaded from async Discord paths

## [1.4.1] - 2026-08-23

### Fixed

- Disable dotenv interpolation so Railway `${{bot-state.*}}` references are not mangled into invalid bucket names locally
- Startup logs a STATE_BUCKET read/write probe and clearer warnings when bucket vars are missing or still templates
- Deploy marker `v1.4.1`

## [1.4.0] - 2026-08-23

### Added

- Railway Storage Bucket (`STATE_BUCKET`) for the official ASA list cache and sticky guild-list message id
- Deploy marker `v1.4.0`

## [1.3.0] - 2026-08-21

### Changed

- Official ARK notices skip posting `execsave`
- 15 / 10 / 5 minute restart warnings replace the previous countdown message, so only the 5-minute notice remains
- Deploy marker `v1.3.0`

## [1.2.14] - 2026-08-21

### Removed

- `/karma` and `/manage_karma` (the karma system)
- Deploy marker `v1.2.14`. After deploy, run `/sync-commands` so Discord drops the old slash commands. Unused karma tables may remain in Postgres.

## [1.2.13] - 2026-08-21

### Changed

- License is GNU Affero GPL v3 (AGPL-3.0), matching the honeypot-derived bothunter code

## [1.2.12] - 2026-08-21

### Changed

- Restart/redeploy always DMs `RESTART_NOTIFY_USER_ID` on process start; retries on later `on_ready` if the first send fails
- Deploy marker `v1.2.12`

## [1.2.11] - 2026-08-21

### Changed

- Restart/redeploy still DMs `RESTART_NOTIFY_USER_ID`. New-guild join posts in `GUILD_LIST_CHANNEL_ID` and pings that user
- Deploy marker `v1.2.11`

## [1.2.10] - 2026-08-20

### Changed

- Removed `/servers`. A sticky embed in `GUILD_LIST_CHANNEL_ID` lists every Discord guild the bot is in, refreshed hourly and when the bot joins or leaves a server
- Deploy marker `v1.2.10`

## [1.2.9] - 2026-08-20

### Added

- `/arknotifications` *(Admin)* — pick a Discord channel for official in-game ASA notices from `notification.html`
- Posts when Wildcard publishes a new notice; empty pages (`..`) are ignored; restart seeds state without spam
- Deploy marker `v1.2.9`

  **Schema:** apply `guild_ark_notifications` + `ark_notification_state` with `python scripts/migrate_to_postgres.py --apply-schema` (or the matching SQL) before restarting on Postgres.

### Changed

- Docs, logs, and module names use Postgres / Postgres REST instead of vendor product names

## [1.2.8] - 2026-08-18

### Changed

- `/serverstatus` chart is a daily availability strip plus a week×hour heatmap on Discord dark, with green/red shades for partial downtime
- Deploy marker `v1.2.8`

## [1.2.7] - 2026-08-18

### Changed

- Official ASA CDN is the primary source for `/serverstatus` live fields (name, IP, players, ping, map, platform, version)
- Shared in-memory cache/poller for the official list, network status, and announcements (default 60s)
- Individual ONLINE/OFFLINE is a presence heuristic (list membership + freshness), not an authoritative Wildcard heartbeat
- BattleMetrics is fallback-only: uptime 7/30/90 graph, optional identity when a server is missing, optional discrepancy logs
- Deploy marker `v1.2.7`

## [1.2.6] - 2026-08-18

### Added

- Rates embed **Subscribe** (green) / **Unsubscribe** (red) buttons assign or remove the guild's rate-alert role
- Buttons persist on `/rates` and automatic rate-change posts
- Deploy marker `v1.2.6`

## [1.2.5] - 2026-08-18

### Added

- DM `RESTART_NOTIFY_USER_ID` when the bot is added to a Discord server (name, ID, owner, members, who added it when audit logs allow)
- Deploy marker `v1.2.5`

## [1.2.4] - 2026-08-17

### Added

- `/serverstatus` still shows occupancy + BattleMetrics uptime when the official list misses a known server (offline)
- Offline replies include **Notify me when it's up**; the bot checks every minute and pings subscribers in that channel when it returns
- Storage: `server_up_notify` (Postgres / Postgres REST / JSON fallback)
- Deploy marker `v1.2.4`

## [1.2.3] - 2026-08-17

### Changed

- `/serverstatus` uptime graph now fills the full BattleMetrics window (default 90 days); missing hourly buckets count as online
- 7d / 30d / 90d percents fall back to averages from that series when BM include data is missing
- Deploy marker `v1.2.3`

## [1.2.2] - 2026-08-16

### Changed

- `/serverstatus` history graph now uses **BattleMetrics uptime** (downtime → % online) instead of locally sampled player counts
- Occupancy bar kept; embed shows 7d / 30d / 90d uptime when BM responds
- Requires `BATTLEMETRICS_TOKEN` (personal access token from BattleMetrics developers area)
- Removed background player sampler integration
- Deploy marker `v1.2.2`

## [1.2.1] - 2026-08-16

### Added

- `/serverstatus` graphs: occupancy bar + 24h player-count history (PNG embed image)
- Background sampler for watched ASA servers (`server_watchlist` / `server_player_samples` on Postgres)
- `Pillow` for chart rendering

### Changed

- Deploy marker `v1.2.1`

## [1.2.0] - 2026-08-12

### Added

- **Bothunter** spam-trap channel (ported from [RiskyMH/honeypot](https://github.com/RiskyMH/honeypot), commands renamed)
  - `/bothunter` — configure trap channel, log channel, softban/ban/disabled, experiments
  - `/bothunter-messages` — custom warning / DM / log messages
  - Softban (ban+unban) deletes recent messages; skips owners/admins; optional DM + reinvite + timeout-first
  - Storage: JSON / Postgres `bothunter_config` + `bothunter_events` / REST same tables

### Changed

- Primary storage is **Postgres** (`DATABASE_URL`); all Sir-5rM8 tables (rates, karma, bothunter) live there
- Deploy marker `v1.2.0`

## [1.1.0] - 2026-08-10

### Added

- Shared **Discord Bots** Postgres REST storage (`bot_sir5rm8` role) with JSON fallback
- JSON → database and legacy database → Discord Bots migration scripts
- Deploy marker + slash sync listing for easier production verification
- Restart/redeploy DM to `RESTART_NOTIFY_USER_ID` (once per process)
- `asyncio.to_thread` regression tests for karma/admin storage paths
- `pytest-asyncio` for async unit tests

### Changed

- Cut over from the old Sir-5rM8 database project to the unified Discord Bots database
- Upgrade the Postgres REST Python client to `>=2.15` (supports `sb_secret_…` API keys)
- Reliability patterns: defer before DB, offload sync storage, fail-fast extension load, `SyncResult` slash sync
- Lighter schema probes (`.limit(0)`); docs renamed to Discord Bots
- BOT_BLUEPRINT clarifications for optional feature folders

### Removed

- Temporary `/migrate-json-to-db` and `/migrate-old-db-to-db` slash commands (CLI scripts retained)
- `.env.example` (configure `.env` / host vars directly)

## [1.0.0] - 2025-02

### Added

- Structured multi-server data storage under `data/`
- Per-guild configuration for rate notifications
- Versioned config schema for future migrations
- Rate monitoring: parse by key name (robust to config format changes)
- Rate monitoring: compare parsed values only (ignores formatting/comment changes)
- Rate monitoring: "changed" indicator in embed when rates change
- HTTP retries (3 attempts, 2s delay) for rate fetches
- Single message for rate notifications (embed + role ping combined)

### Removed

- Karma system (to be rebuilt later)
- XP & Giveaway system (to be rebuilt later)
- Message content intent (no longer required)

### Changed

- Rate notification data now stored in `data/config.json` with guild-keyed structure
- Rate change state stored in `data/rate_state/previous_values.json` (parsed dict, not raw text)
- Improved error handling for rate notifications (skips missing channels/roles gracefully)
- `/rates` command now uses key-based parsing and retries

### Restructure (2025-02)

- **utils/asa.py** — ASA API client (find_server, fetch_current_rates, HTTP retries)
- **utils/constants.py** — Shared RATE_DISPLAY, RATE_KEYS, HTTP settings
- **utils/config.py** — All URLs, paths (PROJECT_ROOT, DATA_DIR)
- **utils/functions.py** — Orchestration layer (thin wrapper over asa + storage)
- **utils/storage.py** — Uses config.DATA_DIR for robust paths
- **Admin** — Response before channel message; `/sync` slash command (owner); improved error handler
- **requirements.txt** — Added
