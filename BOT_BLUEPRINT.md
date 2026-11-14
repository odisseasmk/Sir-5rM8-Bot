# BOT_BLUEPRINT.md

**Universal architecture and strategy for Discord bots** built with **Python 3.10+**, **discord.py** (slash/interactions only), **Turso (libSQL)** as the default primary store for relational domain tables, and optional **Neon / Lakebase Postgres** for hourly **Turso → Neon** backup when `NEON_BACKUP_ENABLED=1`.

Copy this file into every bot repo unchanged. Pair it with a bot-specific **`AGENTS.md`**. This file defines **how** bots are built — not **what** each bot does.

---

PLACEHOLDER_FULL_FILE