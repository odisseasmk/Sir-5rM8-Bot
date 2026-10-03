from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import time

import discord
from discord.ext import tasks, commands

import config
import db
from commands.core.command_sync import sync_application_commands
from commands.core.extensions import load_all_extensions
from functions.owner_notify import notify_restart

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
config.DATA_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(config.DATA_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Bumps when deploy verification matters; check logs after redeploy.
DEPLOY_MARKER = "v1.8.3"


def _last_commit_title(*, fallback: str | None = None) -> str:
    """Prefer Railway deploy commit message; fall back to local git, then DEPLOY_MARKER."""
    raw = (os.environ.get("RAILWAY_GIT_COMMIT_MESSAGE") or "").strip()
    if raw:
        return raw.splitlines()[0].strip()[:150]
    try:
        import subprocess
        from pathlib import Path

        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        if out:
            return out[:150]
    except Exception:
        pass
    return fallback or DEPLOY_MARKER


intents = discord.Intents.default()
intents.guilds = True
intents.members = True

# Keep members intent for moderation events, but do not retain a full guild member
# cache (~hundreds of MB across many ARK communities). Call sites use fetch_member.
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    chunk_guilds_at_startup=False,
    member_cache_flags=discord.MemberCacheFlags.none(),
)

extensions_loaded = False
global_sync_ok = False
restart_notice_sent = False  # One DM per process startup (not every Discord reconnect)
COMMIT_TITLE = _last_commit_title()


@tasks.loop(minutes=5)
async def update_presence():
    count = len(bot.guilds)
    activity = discord.Game(name=f"Watching over {count} server{'s' if count != 1 else ''}")
    await bot.change_presence(activity=activity)


@update_presence.before_loop
async def before_update_presence():
    await bot.wait_until_ready()


def _validate_env() -> None:
    if not config.TOKEN:
        logger.error("Missing required environment variable: TOKEN")
        sys.exit(1)

    logger.info("Deploy marker: %s · commit: %s", DEPLOY_MARKER, COMMIT_TITLE)

    from db import storage
    from functions.blob_state import probe_bucket_connection, state_bucket_configured

    bucket_raw = (config.STATE_BUCKET or "").strip()
    if state_bucket_configured():
        logger.info("Object cache: Railway bucket (%s)", config.STATE_BUCKET)
        ok, detail = probe_bucket_connection()
        if ok:
            logger.info("Object cache probe: %s", detail)
        else:
            logger.warning("Object cache probe failed: %s", detail)
    elif bucket_raw:
        if storage.looks_like_railway_template(bucket_raw):
            logger.warning(
                "STATE_BUCKET looks like a Railway template (%s); "
                "use Variable References on the Sir-5rM8 service, not a copied .env value",
                bucket_raw,
            )
        elif not storage.bucket_name_valid(bucket_raw):
            logger.warning(
                "STATE_BUCKET %r is not a valid bucket name; ASA cache will stay in-memory only",
                bucket_raw,
            )
        else:
            logger.warning(
                "STATE_BUCKET is set but S3 credentials/endpoint are missing; "
                "ASA cache will stay in-memory only"
            )

    if db.use_postgres():
        logger.info("Storage backend: Postgres")
        try:
            db.check_connection()
            logger.info("Postgres connection OK")
        except Exception as exc:
            logger.error(
                "Postgres connection failed: %s. "
                "Check DATABASE_URL (pooled or direct connection string).",
                exc,
            )
            sys.exit(1)

        for name, ok, err in db.check_schema():
            if ok:
                logger.info("Schema OK: %s", name)
            elif name == "bot_runtime_state":
                # Killswitch can run in-memory until DDL is applied.
                logger.warning(
                    "Optional schema missing for %s: %s (killswitch will not persist)",
                    name,
                    err,
                )
            else:
                logger.error("Schema check failed for %s: %s", name, err)
                sys.exit(1)
    elif db.use_postgrest():
        logger.info("Storage backend: Postgres REST (%s)", db.get_postgrest_url())
        try:
            db.check_connection()
            logger.info("Postgres REST connection OK")
        except Exception as exc:
            logger.error(
                "Postgres REST connection failed: %s. "
                "Check POSTGREST_URL and credentials, set DATABASE_URL for Postgres, "
                "or remove remote DB env vars to fall back to JSON files in %s.",
                exc,
                config.DATA_DIR,
            )
            sys.exit(1)

        for name, ok, err in db.check_schema():
            if ok:
                logger.info("Schema OK: %s", name)
            elif name == "bot_runtime_state":
                logger.warning(
                    "Optional schema missing for %s: %s (killswitch will not persist)",
                    name,
                    err,
                )
            else:
                logger.error("Schema check failed for %s: %s", name, err)
                sys.exit(1)
    else:
        logger.info("Storage backend: JSON files (%s)", config.DATA_DIR)


def _start_background_tasks() -> None:
    if not update_presence.is_running():
        update_presence.start()


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    logger.exception("Unhandled prefix command error", exc_info=error)


@bot.event
async def on_ready():
    global extensions_loaded, global_sync_ok, restart_notice_sent

    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    # Channel/role caches (not members) dominate multi-guild RSS — log footprint for RAM audits.
    guild_n = len(bot.guilds)
    channel_n = sum(len(g.channels) for g in bot.guilds)
    role_n = sum(len(g.roles) for g in bot.guilds)
    logger.info(
        "Guild footprint: %s guilds, %s channels, %s roles",
        guild_n,
        channel_n,
        role_n,
    )

    # DM the owner on every process start (retry on later on_ready if the first send fails).
    if not restart_notice_sent:
        restart_notice_sent = await notify_restart(
            bot,
            f"Sir-5rM8 is online after restart/redeploy "
            f"(`{bot.user}` / `{DEPLOY_MARKER}` · `{COMMIT_TITLE}`).",
        )

    if not extensions_loaded:
        try:
            await load_all_extensions(bot)
        except Exception:
            logger.exception("Extension load failed; shutting down")
            await bot.close()
            return
        extensions_loaded = True
        result = await sync_application_commands(bot)
        if result.ok:
            logger.info(
                "Slash commands ready (%s): %s",
                result.global_count,
                ", ".join(result.command_names),
            )
            global_sync_ok = True
        else:
            logger.error("Initial slash command sync failed")
        _start_background_tasks()
        return

    if not global_sync_ok:
        result = await sync_application_commands(bot)
        if result.ok:
            logger.info(
                "Slash commands ready (%s): %s",
                result.global_count,
                ", ".join(result.command_names),
            )
            global_sync_ok = True
        else:
            logger.error("Retry slash command sync failed")

    _start_background_tasks()


async def main():
    _validate_env()
    attempt = int(os.environ.get("LOGIN_RETRY_ATTEMPT", "0"))
    startup_delay = random.uniform(15, 45)
    if attempt > 0:
        startup_delay += 10 * attempt
    logger.info("Waiting %.0f seconds before login (staggered startup)...", startup_delay)
    await asyncio.sleep(startup_delay)
    await bot.start(config.TOKEN)


MAX_LOGIN_RETRIES = 5
LOGIN_RETRY_WAIT = 120

if __name__ == "__main__":
    attempt = int(os.environ.get("LOGIN_RETRY_ATTEMPT", "0"))
    if attempt >= MAX_LOGIN_RETRIES:
        logger.error("Max login retries (%s) reached. Exiting.", MAX_LOGIN_RETRIES)
        sys.exit(1)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down...")
        sys.exit(0)
    except discord.HTTPException as e:
        if e.status == 429 and attempt < MAX_LOGIN_RETRIES - 1:
            wait = min(600, LOGIN_RETRY_WAIT * (2 ** attempt))
            logger.warning(
                "Rate limited (429). Waiting %s seconds, then restarting for retry (%s/%s)...",
                wait, attempt + 1, MAX_LOGIN_RETRIES
            )
            asyncio.run(asyncio.sleep(wait))
            os.environ["LOGIN_RETRY_ATTEMPT"] = str(attempt + 1)
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
        else:
            raise
