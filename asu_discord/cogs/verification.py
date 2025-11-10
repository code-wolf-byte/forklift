from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands
from discord.commands import slash_command

logger = logging.getLogger(__name__)


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

    @commands.command(name="verify")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def verify_member(self, ctx: commands.Context, member: discord.Member) -> None:
        """Assign the verification role to a member."""
        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.send("Unable to locate the configured verification role for this server.")
            return

        if role in member.roles:
            await ctx.send(f"{member.mention} already has the verification role.")
            return

        await member.add_roles(role, reason=f"Manual verification by {ctx.author}")
        await ctx.send(f"{member.mention} has been marked as verified. ✅")

    @commands.command(name="unverify")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def unverify_member(self, ctx: commands.Context, member: discord.Member) -> None:
        """Remove the verification role from a member."""
        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.send("Unable to locate the configured verification role for this server.")
            return

        if role not in member.roles:
            await ctx.send(f"{member.mention} is not currently verified.")
            return

        await member.remove_roles(role, reason=f"Manual unverification by {ctx.author}")
        await ctx.send(f"{member.mention} no longer has the verification role.")

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

    @slash_command(
        name="setup_verification",
        description="Post the Devils to Devils verification instructions.",
        dm_permission=False,
        default_member_permissions=discord.Permissions(manage_guild=True),
    )
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
