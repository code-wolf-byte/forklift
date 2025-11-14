from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ext import commands
from discord.commands import Option, slash_command

from utils.settings import DISCORD_CONFIG

logger = logging.getLogger(__name__)

TEST_GUILD_IDS: list[int] = []
if DISCORD_CONFIG and DISCORD_CONFIG.test_guild_ids:
    TEST_GUILD_IDS = [int(gid) for gid in DISCORD_CONFIG.test_guild_ids]

SLASH_COMMAND_KWARGS = {
    "name": "setup_verification",
    "description": "Post the Devils to Devils verification instructions.",
    "dm_permission": False,
    "default_member_permissions": discord.Permissions(manage_guild=True),
}
if TEST_GUILD_IDS:
    SLASH_COMMAND_KWARGS["guild_ids"] = TEST_GUILD_IDS


def _moderation_command_kwargs(name: str, description: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": name,
        "description": description,
        "dm_permission": False,
        "default_member_permissions": discord.Permissions(manage_roles=True),
    }
    if TEST_GUILD_IDS:
        kwargs["guild_ids"] = TEST_GUILD_IDS
    return kwargs


class VerificationCog(commands.Cog):
    """Cog responsible for managing the Devils to Devils verification role."""

    VERIFICATION_URL = "https://verify.devil2devil.asu.edu"
    ASU_LOGO_URL = "https://verify.devil2devil.asu.edu/static/img/asu-logo-vertical.png"
    EMBED_COLOR = discord.Color.from_rgb(140, 29, 64)

    def __init__(self, bot: commands.Bot, *, guild_id: int, verified_role_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.verified_role_id = verified_role_id

    def _get_verified_role(self, guild: Optional[discord.Guild]) -> Optional[discord.Role]:
        if guild is None:
            return None
        if guild.id != self.guild_id:
            logger.debug("VerificationCog invoked for guild %s (expected %s)", guild.id, self.guild_id)
            return None
        return guild.get_role(self.verified_role_id)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.warning("VerificationCog could not locate guild %s yet", self.guild_id)
        else:
            logger.info("VerificationCog ready in guild %s (%s)", guild.id, guild.name)

    @slash_command(**_moderation_command_kwargs("verify", "Assign the verification role to a member."))
    async def verify_member(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to verify"),
    ) -> None:
        """Assign the verification role to a member."""
        if ctx.guild_id != self.guild_id or ctx.guild is None:
            await ctx.respond("This command is only available in the Devils to Devils server.", ephemeral=True)
            return

        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.respond("Unable to locate the configured verification role for this server.")
            return

        if role in member.roles:
            await ctx.respond(f"{member.mention} already has the verification role.")
            return

        await member.add_roles(role, reason=f"Manual verification by {ctx.author}")
        await ctx.respond(f"{member.mention} has been marked as verified. ✅")

    @slash_command(**_moderation_command_kwargs("unverify", "Remove the verification role from a member."))
    async def unverify_member(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to unverify"),
    ) -> None:
        """Remove the verification role from a member."""
        if ctx.guild_id != self.guild_id or ctx.guild is None:
            await ctx.respond("This command is only available in the Devils to Devils server.", ephemeral=True)
            return

        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.respond("Unable to locate the configured verification role for this server.")
            return

        if role not in member.roles:
            await ctx.respond(f"{member.mention} is not currently verified.")
            return

        await member.remove_roles(role, reason=f"Manual unverification by {ctx.author}")
        await ctx.respond(f"{member.mention} no longer has the verification role.")

    def _build_verification_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Verification",
            description=(
                "This Discord is for students admitted to Arizona State University. "
                "To get access to the full server please verify you've been accepted into Arizona State University."
            ),
            color=self.EMBED_COLOR,
        )
        embed.set_image(url=self.ASU_LOGO_URL)
        return embed

    def _build_verification_view(self) -> discord.ui.View:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Verify Here", url=self.VERIFICATION_URL))
        return view

    @slash_command(**SLASH_COMMAND_KWARGS)
    async def setup_verification(self, ctx: discord.ApplicationContext) -> None:
        """Slash command to seed the verification prompt embed in-channel."""
        if ctx.guild_id != self.guild_id:
            await ctx.respond("This command is only available in the Devils to Devils server.", ephemeral=True)
            return

        if ctx.channel is None:
            await ctx.respond("Unable to determine the target channel for this command.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

        embed = self._build_verification_embed()
        view = self._build_verification_view()
        await ctx.channel.send(embed=embed, view=view)

        await ctx.followup.send("Verification prompt posted with the Verify Here button.", ephemeral=True)
