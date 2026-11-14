-- Sir-5rM8 schema for Turso (libSQL / SQLite).
-- Apply: python scripts/migrate_neon_to_turso.py --apply-schema

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS guild_rate_notifications (
  guild_id   TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  role_id    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_state (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  previous_rates  TEXT
);

INSERT OR IGNORE INTO rate_state (id, previous_rates) VALUES (1, NULL);

CREATE TABLE IF NOT EXISTS bothunter_config (
  guild_id         TEXT PRIMARY KEY,
  channel_id       TEXT,
  log_channel_id   TEXT,
  action           TEXT NOT NULL DEFAULT 'softban',
  warning_msg_id   TEXT,
  experiments      TEXT NOT NULL DEFAULT '[]',
  warning_message  TEXT,
  dm_message       TEXT,
  log_message      TEXT,
  reinvite_code    TEXT
);

CREATE TABLE IF NOT EXISTS bothunter_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id   TEXT NOT NULL,
  user_id    TEXT NOT NULL,
  channel_id TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_bothunter_events_guild
  ON bothunter_events (guild_id);

CREATE INDEX IF NOT EXISTS idx_bothunter_events_guild_channel
  ON bothunter_events (guild_id, channel_id);

CREATE TABLE IF NOT EXISTS server_watchlist (
  server_key    TEXT PRIMARY KEY,
  session_name  TEXT,
  last_queried  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS server_player_samples (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  server_key   TEXT NOT NULL,
  num_players  INTEGER NOT NULL,
  max_players  INTEGER NOT NULL,
  sampled_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  FOREIGN KEY (server_key) REFERENCES server_watchlist (server_key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_server_player_samples_key_time
  ON server_player_samples (server_key, sampled_at DESC);

CREATE TABLE IF NOT EXISTS server_up_notify (
  server_key    TEXT NOT NULL,
  user_id       TEXT NOT NULL,
  channel_id    TEXT NOT NULL,
  guild_id      TEXT,
  query         TEXT,
  session_name  TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (server_key, user_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_server_up_notify_key
  ON server_up_notify (server_key);

CREATE TABLE IF NOT EXISTS guild_ark_notifications (
  guild_id         TEXT PRIMARY KEY,
  channel_id       TEXT NOT NULL,
  last_message_id  TEXT
);

CREATE TABLE IF NOT EXISTS ark_notification_state (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  previous_text   TEXT
);

INSERT OR IGNORE INTO ark_notification_state (id, previous_text) VALUES (1, NULL);

CREATE TABLE IF NOT EXISTS twitch_stream_pinged (
  twitch_login TEXT PRIMARY KEY,
  stream_id    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS twitch_stream_watchlist (
  twitch_login TEXT PRIMARY KEY,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS bot_runtime_state (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);