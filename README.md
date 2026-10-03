```
  ███████╗██╗██████╗ 
  ██╔════╝██║██╔══██╗
  ███████╗██║██████╔╝
  ╚════██║██║██╔══██╗
  ███████║██║██║  ██║
  ╚══════╝╚═╝╚═╝  ╚═╝
     5rM8 · Discord Bot
```

# **Sir-5rM8**

**Version:** 1.8.0

### *Making the community better, one command at a time.*

*A feature-rich Discord bot for your ARK: Survival Ascended discord community.*

---

## Add to Your Server

**Invite Sir-5rM8 to your Discord server** — no setup required. Just add the bot and start with `/help`.

[**Add Sir-5rM8 to Discord**](https://discord.com/oauth2/authorize?client_id=1236457243222868010)

**[📖 Server Setup Guide](docs/SERVER_SETUP_GUIDE.md)** — For server owners: configure rate notifications, in-game ARK notices, and more.

---

## ✨ Features

Use **`/help`** in Discord for the same command list.

### ASA Official PVE Rate Fetch & Dynamic Rate Monitoring

| Command | Description |
|---------|-------------|
| `/rates` | Live server rates: EXP, Harvesting, Taming, Mating, Egg Hatch, Baby Mature, Imprint & Cuddle. **Subscribe** / **Unsubscribe** for the alert role |
| `/set_rate_channel [channel] [role]` | Set channel for automatic rate updates *(Admin only)*|
| `/rate_channel_status` | Show current rate notification setup *(Admin only)*|
| `/clear_rate_channel` | Remove rate notifications for this server *(Admin only)*|

### Server Status

| Command | Description |
|---------|-------------|
| `/serverstatus [server]` | Check ASA official server from Wildcard's list; occupancy bar + optional BattleMetrics uptime graph. If the server is down, tap **Notify me when it's up** or **Report Outage** |

### Official in-game notifications

| Command | Description |
|---------|-------------|
| `/arknotifications` | Pick a channel for the same notices Wildcard posts inside ASA *(Admin only)*. Includes a **Disable** button |

### Bothunter (spam trap)

Catch mass-spam bots by monitoring a dedicated trap channel. Anyone who posts there is softbanned (default) or banned. Commands renamed from the upstream [honeypot](https://github.com/RiskyMH/honeypot) bot.

| Command | Description |
|---------|-------------|
| `/bothunter` | Configure trap channel, log channel, action, and options *(Admin)* |
| `/bothunter-messages` | Customize warning / DM / log messages *(Admin)* |

**Setup tips:** place the trap near the top of your channel list, keep the bot’s role above member roles, and ensure it has **Ban Members**. Softban bans then unbans so Discord deletes recent messages.

### Twitch go-live alerts

| Command | Description |
|---------|-------------|
| `/streamers add` | Add comma- or space-separated Twitch logins to the go-live watchlist *(Admin)* |
| `/streamers list` | List the watchlist plus current ping role and channel *(Admin)* |
| `/streamers remove` | Remove saved Twitch logins from the watchlist *(Admin)* |
| `/streamers setup` | Choose the Discord role and channel for go-live alerts *(Admin)* |

Set `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET`, then configure the alert role and channel with `/streamers setup`. Watchlist logins persist in Postgres (or JSON fallback) and are mirrored to `STATE_BUCKET`; go-live ping dedupe lives in the bucket.

### Help & admin tools

| Command | Description |
|---------|-------------|
| `/help` | Setup guide and command reference |
| `/say [message]` | Repeats a message *(Admin)* |
| `/sync-commands` | Refresh slash commands *(Admin)* |
| `/killswitch on\|off` | Owner only: hard-block all slash commands except `/killswitch` (persisted when `DATABASE_URL` is set) |

### Coming soon features

- **XP Leaderboard & Giveaway**
- **Auto Partner Index**
- **Auction Monitoring**

---

## Self-hosting

**Requirements:** Python **3.10+**, a Discord bot token in `.env` (`TOKEN=...`).

```bash
pip install -r requirements.txt
python main.py
```

Optional storage: **Postgres** (`DATABASE_URL`) preferred, else Postgres REST — see [postgres/README.md](postgres/README.md).
Database-backed runtime state is copied into versioned JSON envelopes under
`data/cache/db/` and the configured dedicated Railway `STATE_BUCKET`. The
database remains authoritative. Persisted values may serve during a
configurable 10–30 second startup grace, then refresh in the background without
blocking bot readiness; reconciliation repeats hourly by default.

Cache timing is controlled by `JSON_CACHE_STARTUP_GRACE_SECONDS` (default `10`),
`JSON_CACHE_STARTUP_JITTER_SECONDS` (default `20`),
`JSON_CACHE_BUCKET_SNAPSHOT_SECONDS` (default `60`), and
`JSON_CACHE_RECONCILE_SECONDS` (default `3600`). Changed in-memory values are
snapshotted to the bucket every minute without querying Neon; authoritative Neon
reads occur during startup verification and hourly reconciliation. Use a separate
Sir-5rM8 state bucket rather than sharing another bot's credentials.

**Developer:** After code changes without a full restart, bot owner or admins can run `!reload` in Discord to reload cogs and re-sync slash commands.

---

## 📄 License

This project is licensed under the GNU Affero GPL v3 — see the [LICENSE](LICENSE) file for details.

---

**Built with** ❤ *for ARK Discord communities*. *Sir-5rM8 is not affiliated with Studio Wildcard.*

[Terms of Service](TERMS_OF_SERVICE.md) · [Privacy Policy](PRIVACY_POLICY.md)

<a href="https://www.buymeacoffee.com/odisseasmk" target="_blank" rel="noopener noreferrer" aria-label="Buy me a coffee"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy me a coffee" width="150" /></a>