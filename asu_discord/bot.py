from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from utils.settings import DISCORD_CONFIG
from .cogs.message_logger import MessageLoggerCog
from .cogs.qna import QnACog
from .cogs.verification import VerificationCog
from .shared import register_bot

logger = logging.getLogger(__name__)


class ForkliftBot(commands.Bot):
    """Discord bot for Devil2Devil server management."""

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
            intents.guild_messages = True    # needed for on_message
            intents.message_content = True   # privileged — needed to read message text
        super().__init__(command_prefix=command_prefix, intents=intents)
        self._load_verification_cog()
        self._load_qna_cog()
        self._load_message_logger_cog()

    def _load_verification_cog(self) -> None:
        """Attach the verification cog immediately after initialization."""
        if DISCORD_CONFIG is None:
            logger.warning(
                "Discord bot started without DISCORD_CONFIG; skipping verification cog"
            )
            return

        unverified_role_id: Optional[int] = None
        if DISCORD_CONFIG.unverified_role_id:
            try:
                unverified_role_id = int(DISCORD_CONFIG.unverified_role_id)
            except ValueError:
                logger.warning(
                    "Invalid DISCORD_UNVERIFIED_ROLE_ID value: %s",
                    DISCORD_CONFIG.unverified_role_id,
                )

        try:
            self.add_cog(
                VerificationCog(
                    self,
                    guild_id=int(DISCORD_CONFIG.guild_id),
                    verified_role_id=int(DISCORD_CONFIG.verified_role_id),
                    unverified_role_id=unverified_role_id,
                )
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to load VerificationCog")
            raise

        logger.info("Loaded VerificationCog for guild %s", DISCORD_CONFIG.guild_id)

    def _load_qna_cog(self) -> None:
        """Attach the Q&A cog."""
        try:
            self.add_cog(QnACog(self))
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to load QnACog")
            raise

        logger.info("Loaded QnACog")

    def _load_message_logger_cog(self) -> None:
        """Attach the message logger cog."""
        if DISCORD_CONFIG is None:
            logger.warning("Skipping MessageLoggerCog: DISCORD_CONFIG not set")
            return
        try:
            self.add_cog(
                MessageLoggerCog(self, guild_id=int(DISCORD_CONFIG.guild_id))
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to load MessageLoggerCog")
            raise

        logger.info("Loaded MessageLoggerCog")

    async def setup_hook(self) -> None:
        """Run after the bot connects to Discord."""
        logger.info("ForkliftBot setup hook starting")

        try:
            await self.sync_commands()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to sync application commands with Discord")
            raise

        logger.info("Synced application commands")


def create_bot(
    *, command_prefix: str = "!", intents: Optional[discord.Intents] = None
) -> ForkliftBot:
    """Factory for the Forklift Discord bot."""
    bot = ForkliftBot(command_prefix=command_prefix, intents=intents)
    register_bot(bot)
    return bot
