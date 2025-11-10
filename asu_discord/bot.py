from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from utils.settings import DISCORD_CONFIG
from .cogs.verification import VerificationCog

logger = logging.getLogger(__name__)


class ForkliftBot(commands.Bot):
    """Discord bot for Devils to Devils server management."""

    def __init__(
        self,
        *,
        command_prefix: str = "!",
        intents: Optional[discord.Intents] = None,
    ) -> None:
        if intents is None:
            intents = discord.Intents.default()
            intents.members = True
            intents.guilds = True
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def setup_hook(self) -> None:
        """Load bot cogs once the bot is ready."""
        if DISCORD_CONFIG is None:
            logger.warning("Discord bot started without DISCORD_CONFIG; skipping verification cog")
            return

        self.add_cog(
            VerificationCog(
                self,
                guild_id=int(DISCORD_CONFIG.guild_id),
                verified_role_id=int(DISCORD_CONFIG.verified_role_id),
            )
        )
        logger.info("Loaded VerificationCog for guild %s", DISCORD_CONFIG.guild_id)


def create_bot(*, command_prefix: str = "!", intents: Optional[discord.Intents] = None) -> ForkliftBot:
    """Factory for the Forklift Discord bot."""
    return ForkliftBot(command_prefix=command_prefix, intents=intents)
