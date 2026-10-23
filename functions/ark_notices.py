"""Official in-game ASA notifications (notification.html) → Discord channels."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import db
from functions import json_db_cache as cache
from functions.asa_cache import current_announcement

RESTART_NOTICE_TITLE = "Official ARK Restart Notice"
REMOVAL_NOTICE_TITLE = "Official ARK Server Removal"
GENERIC_NOTICE_TITLE = "Official ARK Notification"

_EXECSAVE_RE = re.compile(r"^execsave[.!]*$", re.IGNORECASE)
_CRASH_DUMP_COMMAND_RE = re.compile(
    r"Exec(?:Enable|Disable)FullCrashDumps",
    re.IGNORECASE,
)
# Official restart countdowns are usually 15→1 minutes; Wildcard sometimes skips one.
_COUNTDOWN_RE = re.compile(
    r"\b(?:1[0-5]|[1-9])\s*(?:minutes?|mins?)\b",
    re.IGNORECASE,
)
_SERVER_REMOVAL_RE = re.compile(
    r"\b(?:"
    r"servers?\s+(?:will\s+be\s+|have\s+been\s+|are\s+being\s+)?remov(?:ed|al|ing)"
    r"|remov(?:ed|al|ing)\s+from\s+the\s+official"
    r"|decommission(?:ed|ing)?"
    r")\b",
    re.IGNORECASE,
)


def is_execsave_notice(text: str) -> bool:
    """True when the official page is only the in-game ``execsave`` line."""
    compact = " ".join((text or "").split()).strip()
    return bool(compact) and bool(_EXECSAVE_RE.fullmatch(compact))


def is_crash_dump_notice(text: str) -> bool:
    """True when a notice contains the crash-dump diagnostic command."""
    return bool(_CRASH_DUMP_COMMAND_RE.search(text or ""))


def is_restart_countdown_notice(text: str) -> bool:
    """True for restart countdown warnings from 1 through 15 minutes."""
    return bool(_COUNTDOWN_RE.search(text or ""))


def is_server_removal_notice(text: str) -> bool:
    """True when Wildcard announces official server removals."""
    return bool(_SERVER_REMOVAL_RE.search(text or ""))


def replaces_previous_ark_notice(text: str) -> bool:
    """Countdown and removal notices replace the prior posted message."""
    return is_restart_countdown_notice(text) or is_server_removal_notice(text)


def restart_notice_is_expired(
    created_at: datetime,
    *,
    now: datetime | None = None,
    ttl_hours: float | None = None,
) -> bool:
    """True when a restart notice Discord message should be auto-deleted."""
    import config

    ttl = config.ARK_RESTART_NOTICE_TTL_HOURS if ttl_hours is None else float(ttl_hours)
    if ttl <= 0:
        return False
    now = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at.astimezone(timezone.utc)) >= timedelta(hours=ttl)


def should_post_ark_notice(text: str) -> bool:
    """False for empty pages and internal-only exec lines Wildcard publishes."""
    compact = (text or "").strip()
    if not compact:
        return False
    return not is_execsave_notice(compact) and not is_crash_dump_notice(compact)


def consume_ark_notice_update() -> tuple[str | None, list[dict]]:
    """
    Compare the cached official notice to the last posted text.
    First run seeds state and does not post (avoids spam on restart).
    Empty pages (``..``) and ``execsave`` are stored but not posted.
    Returns (text, channels) when guilds should be notified.
    """
    announcement = current_announcement()
    if announcement is None or not announcement.fetch_ok:
        return None, []
    current = announcement.text or ""
    previous = cache.get("ark_notice_state", db.get_previous_ark_notice)
    if previous is None:
        db.save_previous_ark_notice(current)
        cache.put("ark_notice_state", current)
        return None, []
    if current == previous:
        return None, []
    # A changed notice is the only normal-time read-back from Neon.  Prefer
    # the authoritative value if another process changed it meanwhile.
    verified_previous = db.get_previous_ark_notice()
    if verified_previous is not None:
        previous = verified_previous
    db.save_previous_ark_notice(current)
    cache.put("ark_notice_state", current)
    if not should_post_ark_notice(current):
        return None, []
    return current, cache.get("ark_notifications", db.get_ark_notification_channels)


def list_ark_notifications() -> list[dict]:
    return list(cache.get("ark_notifications", db.get_ark_notification_channels) or [])


def get_ark_notification(guild_id: str) -> dict | None:
    for row in list_ark_notifications():
        if str(row.get("guild_id")) == str(guild_id):
            return {
                "channel_id": row.get("channel_id"),
                "last_message_id": row.get("last_message_id"),
            }
    return None


def set_ark_notice_last_message(guild_id: str, message_id: str | None) -> None:
    db.set_ark_notice_last_message(guild_id, message_id)
    def mutate(channels: list[dict]) -> None:
        for row in channels:
            if str(row.get("guild_id")) == str(guild_id):
                row["last_message_id"] = message_id
                break

    cache.update("ark_notifications", db.get_ark_notification_channels, mutate)


def set_ark_notification(guild_id: str, channel_id: str) -> None:
    db.set_ark_notification(guild_id, channel_id)
    def mutate(channels: list[dict]) -> None:
        existing = next(
            (row for row in channels if str(row.get("guild_id")) == str(guild_id)),
            None,
        )
        if existing is None:
            channels.append(
                {
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "last_message_id": None,
                }
            )
        else:
            existing["last_message_id"] = (
                existing.get("last_message_id")
                if existing.get("channel_id") == str(channel_id)
                else None
            )
            existing["channel_id"] = str(channel_id)

    cache.update("ark_notifications", db.get_ark_notification_channels, mutate)


def clear_ark_notification(guild_id: str) -> bool:
    cleared = db.clear_ark_notification(guild_id)
    if cleared:
        cache.update(
            "ark_notifications",
            db.get_ark_notification_channels,
            lambda channels: [
                row for row in channels if str(row.get("guild_id")) != str(guild_id)
            ],
        )
    return cleared


def verify_cached_ark_state() -> dict[str, bool]:
    result = {
        "ark_notice_state": cache.verify("ark_notice_state", db.get_previous_ark_notice),
        "ark_notifications": cache.verify(
            "ark_notifications", db.get_ark_notification_channels
        ),
    }
    return result
