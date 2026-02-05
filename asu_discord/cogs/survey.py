from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from utils.settings import DISCORD_CONFIG
from utils.database import User, session_scope

logger = logging.getLogger(__name__)

# Arizona doesn't observe DST, so MST is always UTC-7
ARIZONA_TZ = ZoneInfo("America/Phoenix")

TEST_GUILD_IDS: list[int] = []
if DISCORD_CONFIG and DISCORD_CONFIG.test_guild_ids:
    TEST_GUILD_IDS = [int(gid) for gid in DISCORD_CONFIG.test_guild_ids]


def _get_users_verified_n_weeks_ago(weeks: int = 3) -> list[tuple[str, str]]:
    """
    Fetch users who verified exactly N weeks ago (within a 24-hour window).

    Returns a list of (discord_user_id, first_name) tuples.
    """
    now_utc = datetime.utcnow()
    target_date = now_utc - timedelta(weeks=weeks)

    # Window: from start of target day to end of target day (UTC)
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    users_to_ping: list[tuple[str, str]] = []

    with session_scope() as session:
        users = (
            session.query(User)
            .filter(
                User.verified == True,
                User.discord_user_id.isnot(None),
                User.verified_at >= start_of_day,
                User.verified_at < end_of_day,
                User.left_at.is_(None),  # Only ping users still in the server
                User.banned == False,
            )
            .all()
        )

        for user in users:
            discord_id = user.discord_user_id
            first_name = user.first_name or user.full_name or "Sun Devil"
            users_to_ping.append((discord_id, first_name))

    return users_to_ping


class SurveyCog(commands.Cog):
    """Cog for sending survey reminders to users who verified 3 weeks ago."""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        guild_id: int,
        survey_channel_id: int,
    ) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.survey_channel_id = survey_channel_id

    async def cog_load(self) -> None:
        """Start the survey reminder task when the cog loads."""
        self.survey_reminder_task.start()
        logger.info("SurveyCog loaded and survey reminder task started")

    async def cog_unload(self) -> None:
        """Stop the survey reminder task when the cog unloads."""
        self.survey_reminder_task.cancel()
        logger.info("SurveyCog unloaded and survey reminder task stopped")

    @tasks.loop(minutes=1)
    async def survey_reminder_task(self) -> None:
        """
        Check if it's 12:00 PM Arizona time and send survey reminders.

        Runs every minute to check if it's time to send reminders.
        Only triggers once per day at exactly 12:00 PM MST.
        """
        now_az = datetime.now(ARIZONA_TZ)

        # Only run at 12:00 PM Arizona time (hour=12, minute=0)
        if now_az.hour != 12 or now_az.minute != 0:
            return

        logger.info("Running survey reminder task at %s Arizona time", now_az.strftime("%Y-%m-%d %H:%M:%S"))

        await self._send_survey_reminders()

    @survey_reminder_task.before_loop
    async def before_survey_reminder_task(self) -> None:
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.info("Survey reminder task is ready")

    async def _send_survey_reminders(self) -> None:
        """Fetch eligible users and send survey pings to the survey channel."""
        users_to_ping = _get_users_verified_n_weeks_ago(weeks=3)

        if not users_to_ping:
            logger.info("No users to ping for survey reminders today")
            return

        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(self.guild_id)
            except discord.HTTPException as exc:
                logger.error("Failed to fetch guild %s: %s", self.guild_id, exc)
                return

        if guild is None:
            logger.error("Guild %s not found", self.guild_id)
            return

        channel = guild.get_channel(self.survey_channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(self.survey_channel_id)
            except discord.HTTPException as exc:
                logger.error("Failed to fetch survey channel %s: %s", self.survey_channel_id, exc)
                return

        if channel is None or not isinstance(channel, discord.TextChannel):
            logger.error("Survey channel %s not found or is not a text channel", self.survey_channel_id)
            return

        # Send individual pings for each user
        successful_pings = 0
        for discord_user_id, first_name in users_to_ping:
            try:
                member = guild.get_member(int(discord_user_id))
                if member is None:
                    try:
                        member = await guild.fetch_member(int(discord_user_id))
                    except discord.NotFound:
                        logger.warning("Member %s not found in guild", discord_user_id)
                        continue
                    except discord.HTTPException as exc:
                        logger.warning("Failed to fetch member %s: %s", discord_user_id, exc)
                        continue

                if member is None:
                    continue

                message = (
                    f"Hey {member.mention}! You've been part of Devil2Devil for 3 weeks now. "
                    f"We'd love to hear about your experience! Please take a moment to fill out our survey. "
                    f"Your feedback helps us improve the community for everyone. Thank you!"
                )

                await channel.send(message)
                successful_pings += 1
                logger.info("Sent survey reminder to user %s (%s)", discord_user_id, first_name)

            except discord.HTTPException as exc:
                logger.error("Failed to send survey reminder to user %s: %s", discord_user_id, exc)
            except Exception as exc:
                logger.exception("Unexpected error sending survey reminder to user %s: %s", discord_user_id, exc)

        logger.info("Survey reminders sent to %d/%d users", successful_pings, len(users_to_ping))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Log when the cog is ready."""
        guild = self.bot.get_guild(self.guild_id)
        guild_name = guild.name if guild else "Unknown"
        logger.info("SurveyCog ready in guild %s (%s)", self.guild_id, guild_name)
