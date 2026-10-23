from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from functions import ark_notices as notice_cache
from functions.ark_notices import (
    GENERIC_NOTICE_TITLE,
    REMOVAL_NOTICE_TITLE,
    RESTART_NOTICE_TITLE,
    consume_ark_notice_update,
    is_restart_countdown_notice,
    is_server_removal_notice,
    list_ark_notifications,
    replaces_previous_ark_notice,
    restart_notice_is_expired,
    should_post_ark_notice,
)
from functions.asa_cache import current_announcement

logger = logging.getLogger(__name__)

_CHANNEL_TYPES = [
    discord.ChannelType.text,
    discord.ChannelType.news,
]


def build_ark_notice_embed(text: str) -> discord.Embed:
    if is_server_removal_notice(text):
        title = REMOVAL_NOTICE_TITLE
        colour = discord.Colour.red()
    elif is_restart_countdown_notice(text):
        title = RESTART_NOTICE_TITLE
        colour = discord.Colour.orange()
    else:
        title = GENERIC_NOTICE_TITLE
        colour = discord.Colour.orange()
    embed = discord.Embed(
        title=title,
        description=text[:4096],
        colour=colour,
    )
    embed.set_thumbnail(url=config.THUMBNAIL_URL)
    embed.set_footer(text="In-game official notice")
    return embed


async def _delete_previous_notice(channel, last_message_id: str | None) -> None:
    if not last_message_id:
        return
    try:
        old = await channel.fetch_message(int(last_message_id))
        await old.delete()
    except (ValueError, TypeError, discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def post_ark_notice(
    channel,
    text: str,
    *,
    guild_id: str,
    last_message_id: str | None,
) -> str | None:
    """Post a notice, replacing the previous countdown message. Returns the new message id."""
    if not should_post_ark_notice(text):
        return last_message_id
    if replaces_previous_ark_notice(text):
        await _delete_previous_notice(channel, last_message_id)
    sent = await channel.send(embed=build_ark_notice_embed(text))
    await asyncio.to_thread(notice_cache.set_ark_notice_last_message, guild_id, str(sent.id))
    return str(sent.id)


async def expire_stale_restart_notices(bot) -> int:
    """Delete tracked Official ARK Restart Notice posts older than the TTL. Returns delete count."""
    rows = await asyncio.to_thread(list_ark_notifications)
    deleted = 0
    for ent in rows:
        guild_id = str(ent.get("guild_id") or "")
        message_id = ent.get("last_message_id")
        channel_id = ent.get("channel_id")
        if not guild_id or not message_id or not channel_id:
            continue
        try:
            guild = bot.get_guild(int(guild_id))
            channel = guild.get_channel(int(channel_id)) if guild else None
            if channel is None or not hasattr(channel, "fetch_message"):
                continue
            msg = await channel.fetch_message(int(message_id))
        except (ValueError, TypeError, discord.NotFound):
            await asyncio.to_thread(notice_cache.set_ark_notice_last_message, guild_id, None)
            continue
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Restart notice expire skipped for guild %s: %s", guild_id, exc)
            continue

        title = msg.embeds[0].title if msg.embeds else None
        if title != RESTART_NOTICE_TITLE:
            continue
        if not restart_notice_is_expired(msg.created_at):
            continue
        try:
            await msg.delete()
        except discord.NotFound:
            pass
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Could not delete restart notice in guild %s: %s", guild_id, exc)
            continue
        await asyncio.to_thread(notice_cache.set_ark_notice_last_message, guild_id, None)
        deleted += 1
        logger.info("Deleted expired ARK restart notice in guild %s", guild_id)
    return deleted


async def _resolve_guild_channel(interaction: discord.Interaction, raw) -> discord.abc.Messageable | None:
    channel_id = getattr(raw, "id", None)
    if channel_id is None:
        return None
    guild = interaction.guild
    if guild is None:
        return None
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await guild.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    if not hasattr(channel, "send"):
        return None
    return channel


class ArkNotifySetupView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(ArkNotifyChannelSelect())

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, row=1)
    async def disable(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Administrator permission required.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        cleared = await asyncio.to_thread(notice_cache.clear_ark_notification, str(interaction.guild.id))
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except (discord.HTTPException, AttributeError):
            pass
        if cleared:
            await interaction.followup.send("ARK in-game notifications disabled for this server.", ephemeral=True)
        else:
            await interaction.followup.send("No ARK notification channel was configured.", ephemeral=True)


class ArkNotifyChannelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Select a channel for ARK in-game notifications",
            min_values=1,
            max_values=1,
            channel_types=_CHANNEL_TYPES,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Administrator permission required.", ephemeral=True)
            return
        channel = await _resolve_guild_channel(interaction, self.values[0])
        if channel is None:
            await interaction.response.send_message("I couldn't use that channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await asyncio.to_thread(notice_cache.set_ark_notification, str(interaction.guild.id), str(channel.id))
        view: discord.ui.View | None = self.view
        if view is not None:
            for item in view.children:
                item.disabled = True
            try:
                await interaction.message.edit(view=view)
            except (discord.HTTPException, AttributeError):
                pass
        mention = getattr(channel, "mention", f"<#{channel.id}>")
        notice = current_announcement()
        posted = False
        if (
            notice is not None
            and notice.fetch_ok
            and notice.text
            and should_post_ark_notice(notice.text)
        ):
            try:
                await post_ark_notice(
                    channel,
                    notice.text,
                    guild_id=str(interaction.guild.id),
                    last_message_id=None,
                )
                posted = True
            except discord.Forbidden:
                await interaction.followup.send(
                    f"{mention} is set, but I couldn't post there. Check my permissions.",
                    ephemeral=True,
                )
                return
        if posted:
            await interaction.followup.send(
                f"{mention} will get official in-game ARK notifications. Current notice posted.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"{mention} will get official in-game ARK notifications. "
                "Nothing is posted in-game right now — I'll send here when Wildcard publishes one.",
                ephemeral=True,
            )


class ArkNotifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        if os.environ.get("EXTENSION_VERIFY"):
            return
        if not self.poll_ark_notices.is_running():
            self.poll_ark_notices.start()
        if not self.expire_restart_notices.is_running():
            self.expire_restart_notices.start()

    def cog_unload(self) -> None:
        self.poll_ark_notices.cancel()
        self.expire_restart_notices.cancel()

    @app_commands.command(
        name="arknotifications",
        description="Choose a channel for official in-game ARK notifications",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def arknotifications(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        current = await asyncio.to_thread(notice_cache.get_ark_notification, str(interaction.guild.id))
        if current:
            channel = interaction.guild.get_channel(int(current["channel_id"]))
            where = channel.mention if channel else f"<#{current['channel_id']}>"
            body = f"Currently posting to {where}. Pick a new channel or disable."
        else:
            body = (
                "Pick a channel for official ARK in-game notifications "
                "(the same notices shown inside ASA)."
            )
        await interaction.followup.send(body, view=ArkNotifySetupView(), ephemeral=True)

    @tasks.loop(seconds=config.ASA_POLL_SECONDS)
    async def poll_ark_notices(self):
        try:
            text, channels = await asyncio.to_thread(consume_ark_notice_update)
            if not text or not channels:
                return
            for ent in channels:
                try:
                    guild = self.bot.get_guild(int(ent["guild_id"]))
                    channel = guild.get_channel(int(ent["channel_id"])) if guild else None
                    if channel is None or not hasattr(channel, "send"):
                        continue
                    await post_ark_notice(
                        channel,
                        text,
                        guild_id=str(ent["guild_id"]),
                        last_message_id=ent.get("last_message_id"),
                    )
                except (KeyError, TypeError, ValueError, discord.Forbidden, discord.HTTPException) as exc:
                    logger.warning(
                        "ARK notice skipped for guild %s: %s",
                        ent.get("guild_id", "?"),
                        exc,
                    )
        except Exception:
            logger.exception("ARK notice poll failed")

    @poll_ark_notices.before_loop
    async def before_poll_ark_notices(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=config.ARK_RESTART_NOTICE_EXPIRE_CHECK_MINUTES)
    async def expire_restart_notices(self):
        try:
            await expire_stale_restart_notices(self.bot)
        except Exception:
            logger.exception("ARK restart notice expiry failed")

    @expire_restart_notices.before_loop
    async def before_expire_restart_notices(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ArkNotifications(bot))
