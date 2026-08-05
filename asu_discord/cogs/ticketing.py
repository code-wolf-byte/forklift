from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from discord.commands import Option, slash_command

from utils.database import Ticket, TicketCategory, TicketMessage, TicketSettings, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

logger = logging.getLogger(__name__)

TICKET_SELECT_CUSTOM_ID = "ticket_open_select"
TICKET_CLOSE_CUSTOM_ID = "ticket_close"
TICKET_DELETE_CUSTOM_ID = "ticket_delete"

TEST_GUILD_IDS: list[int] = []
if DISCORD_CONFIG and DISCORD_CONFIG.test_guild_ids:
    TEST_GUILD_IDS = [int(gid) for gid in DISCORD_CONFIG.test_guild_ids]


def _ticket_command_kwargs(name: str, description: str) -> dict:
    kwargs: dict = {
        "name": name,
        "description": description,
        "dm_permission": False,
        "default_member_permissions": discord.Permissions(manage_channels=True),
    }
    if TEST_GUILD_IDS:
        kwargs["guild_ids"] = TEST_GUILD_IDS
    return kwargs


async def _category_autocomplete(ctx: discord.AutocompleteContext):
    """Offer the requesting guild's configured ticket categories as choices."""
    guild_id = ctx.interaction.guild_id
    if guild_id is None:
        return []
    settings = _load_settings_dict(str(guild_id))
    if not settings:
        return []
    query = (ctx.value or "").lower()
    return [
        discord.OptionChoice(name=c["label"], value=str(c["id"]))
        for c in settings["categories"]
        if query in c["label"].lower()
    ]

_MANAGE_PERMS = discord.Permissions(view_channel=True, send_messages=True, manage_messages=True)
_OPENER_PERMS = discord.Permissions(view_channel=True, send_messages=True, read_message_history=True)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ticket"


def _generate_transcript_slug() -> str:
    return secrets.token_urlsafe(12)


def _message_row_kwargs(message: discord.Message) -> dict:
    """Build TicketMessage column values from a live discord.Message."""
    return {
        "message_id": str(message.id),
        "author_id": str(message.author.id),
        "author_username": str(message.author),
        "author_display_name": message.author.display_name,
        "author_avatar_url": message.author.display_avatar.url,
        "content": message.content,
        "attachments": json.dumps(
            [{"filename": a.filename, "url": a.url, "content_type": a.content_type} for a in message.attachments]
        ),
        "embeds": len(message.embeds),
        "created_at": message.created_at.replace(tzinfo=None),
    }


def _load_settings_dict(guild_id: str) -> Optional[dict]:
    """Load ticket settings + categories for a guild as plain dicts (safe past session close)."""
    with session_scope() as db:
        settings = (
            db.query(TicketSettings).filter(TicketSettings.guild_id == guild_id).one_or_none()
        )
        if settings is None:
            return None
        categories = (
            db.query(TicketCategory)
            .filter(TicketCategory.settings_id == settings.id)
            .order_by(TicketCategory.position.asc())
            .all()
        )
        return {
            "id": settings.id,
            "guild_id": settings.guild_id,
            "panel_channel_id": settings.panel_channel_id,
            "panel_message_id": settings.panel_message_id,
            "transcript_channel_id": settings.transcript_channel_id,
            "embed_title": settings.embed_title or "Open a Ticket",
            "embed_description": settings.embed_description or "Select a category below to open a ticket.",
            "embed_color": settings.embed_color or "#8c1d40",
            "embed_image_url": settings.embed_image_url,
            "embed_thumbnail_url": settings.embed_thumbnail_url,
            "embed_footer": settings.embed_footer,
            "embed_footer_icon_url": settings.embed_footer_icon_url,
            "embed_url": settings.embed_url,
            "embed_author_name": settings.embed_author_name,
            "embed_author_url": settings.embed_author_url,
            "embed_author_icon_url": settings.embed_author_icon_url,
            "embed_timestamp": bool(settings.embed_timestamp),
            "embed_fields": json.loads(settings.embed_fields or "[]"),
            "select_placeholder": settings.select_placeholder or "Select a ticket category…",
            "staff_role_ids": json.loads(settings.staff_role_ids or "[]"),
            "categories": [
                {
                    "id": c.id,
                    "label": c.label,
                    "description": c.description,
                    "emoji": c.emoji,
                    "parent_category_id": c.parent_category_id,
                    "extra_role_ids": json.loads(c.extra_role_ids or "[]"),
                }
                for c in categories
            ],
        }


def _build_panel_embed(settings: dict) -> discord.Embed:
    color_hex = (settings.get("embed_color") or "#8c1d40").lstrip("#")
    try:
        color = discord.Color(int(color_hex, 16))
    except ValueError:
        color = discord.Color.from_rgb(140, 29, 64)

    embed = discord.Embed(
        title=settings.get("embed_title") or "Open a Ticket",
        description=settings.get("embed_description") or "Select a category below to open a ticket.",
        color=color,
        url=settings.get("embed_url") or None,
        timestamp=datetime.utcnow() if settings.get("embed_timestamp") else None,
    )
    if settings.get("embed_image_url"):
        embed.set_image(url=settings["embed_image_url"])
    if settings.get("embed_thumbnail_url"):
        embed.set_thumbnail(url=settings["embed_thumbnail_url"])
    if settings.get("embed_footer"):
        embed.set_footer(
            text=settings["embed_footer"],
            icon_url=settings.get("embed_footer_icon_url") or None,
        )
    if settings.get("embed_author_name"):
        embed.set_author(
            name=settings["embed_author_name"],
            url=settings.get("embed_author_url") or None,
            icon_url=settings.get("embed_author_icon_url") or None,
        )
    for field in settings.get("embed_fields") or []:
        name = (field.get("name") or "").strip()
        value = (field.get("value") or "").strip()
        if name and value:
            embed.add_field(name=name[:256], value=value[:1024], inline=bool(field.get("inline")))
    return embed


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, cog: "TicketingCog", categories: list[dict], placeholder: str) -> None:
        self.cog = cog
        if categories:
            options = [
                discord.SelectOption(
                    label=c["label"][:100],
                    description=(c.get("description") or None),
                    value=str(c["id"]),
                    emoji=c.get("emoji") or None,
                )
                for c in categories
            ]
        else:
            options = [discord.SelectOption(label="No categories configured", value="__none__")]

        super().__init__(
            custom_id=TICKET_SELECT_CUSTOM_ID,
            placeholder=placeholder[:150],
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        if value == "__none__":
            await interaction.response.send_message(
                "Ticketing isn't configured yet — please contact an admin.", ephemeral=True
            )
            return
        await self.cog.open_ticket_modal(interaction, category_id=int(value))


class TicketPanelView(discord.ui.View):
    def __init__(self, cog: "TicketingCog", categories: list[dict], placeholder: str) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(cog, categories, placeholder))


class TicketOpenModal(discord.ui.Modal):
    def __init__(self, cog: "TicketingCog", category_id: int) -> None:
        super().__init__(title="Open a Ticket")
        self.cog = cog
        self.category_id = category_id
        self.subject_input = discord.ui.InputText(
            label="Subject", placeholder="Brief summary of your issue", max_length=100
        )
        self.description_input = discord.ui.InputText(
            label="Description",
            style=discord.InputTextStyle.paragraph,
            placeholder="Describe your issue in detail",
            max_length=1000,
        )
        self.add_item(self.subject_input)
        self.add_item(self.description_input)

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.create_ticket(
            interaction,
            category_id=self.category_id,
            subject=self.subject_input.value or "",
            description=self.description_input.value or "",
        )


class TicketControlView(discord.ui.View):
    """Static view attached to every ticket channel's opening message."""

    def __init__(self, cog: "TicketingCog") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Close Ticket", style=discord.ButtonStyle.danger, custom_id=TICKET_CLOSE_CUSTOM_ID
    )
    async def close_button(self, _: discord.ui.Button, interaction: discord.Interaction) -> None:
        await self.cog.close_ticket(interaction)


class TicketDeleteView(discord.ui.View):
    """Static view shown after a ticket is closed, letting staff delete the channel."""

    def __init__(self, cog: "TicketingCog") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Delete Channel", style=discord.ButtonStyle.danger, custom_id=TICKET_DELETE_CUSTOM_ID
    )
    async def delete_button(self, _: discord.ui.Button, interaction: discord.Interaction) -> None:
        await self.cog.delete_ticket(interaction)


class TicketingCog(commands.Cog):
    """Self-serve ticketing: admin-configured panel opens private ticket channels."""

    def __init__(self, bot: commands.Bot, *, guild_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id

    # ── Startup / persistent views ────────────────────────────────────────────

    def build_persistent_views(self) -> list[discord.ui.View]:
        """Build the static views that must be re-registered on every bot start."""
        settings = _load_settings_dict(str(self.guild_id)) or {"categories": [], "select_placeholder": None}
        panel_view = TicketPanelView(
            self,
            settings["categories"],
            settings.get("select_placeholder") or "Select a ticket category…",
        )
        return [panel_view, TicketControlView(self), TicketDeleteView(self)]

    async def _resolve_guild(self) -> discord.Guild:
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            guild = await self.bot.fetch_guild(self.guild_id)
        return guild

    # ── Live transcript capture ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Persist every message sent in a ticket channel as it happens, so the transcript
        never needs to be re-fetched from Discord later."""
        if not message.guild or message.guild.id != self.guild_id:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if not message.channel.name.startswith("ticket-"):
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_ticket_message, str(message.channel.id), message)

    def _save_ticket_message(self, channel_id: str, message: discord.Message) -> None:
        try:
            with session_scope() as db:
                ticket = db.query(Ticket).filter(Ticket.channel_id == channel_id).one_or_none()
                if ticket is None:
                    return
                if db.query(TicketMessage.id).filter(TicketMessage.message_id == str(message.id)).first():
                    return
                db.add(TicketMessage(ticket_id=ticket.id, **_message_row_kwargs(message)))
        except Exception:
            logger.exception("Failed to save ticket message %s", message.id)

    # ── Permission helpers ──────────────────────────────────────────────────────

    def _staff_roles(self, guild: discord.Guild, settings: dict, category: dict) -> list[discord.Role]:
        role_ids = {*settings.get("staff_role_ids", []), *category.get("extra_role_ids", [])}
        roles = []
        for rid in role_ids:
            try:
                role = guild.get_role(int(rid))
            except (TypeError, ValueError):
                role = None
            if role is not None:
                roles.append(role)
        return roles

    async def _ensure_category_channel(
        self, guild: discord.Guild, category: dict
    ) -> discord.CategoryChannel:
        """Find (or create) the Discord category channel matching this ticket category's label."""
        existing_id = category.get("parent_category_id")
        if existing_id:
            channel = guild.get_channel(int(existing_id))
            if isinstance(channel, discord.CategoryChannel):
                return channel

        for channel in guild.categories:
            if channel.name.strip().lower() == category["label"].strip().lower():
                self._save_category_parent(category["id"], str(channel.id))
                return channel

        created = await guild.create_category(
            name=category["label"], reason="Ticketing: auto-created category"
        )
        self._save_category_parent(category["id"], str(created.id))
        return created

    def _save_category_parent(self, category_id: int, discord_category_id: str) -> None:
        with session_scope() as db:
            row = db.query(TicketCategory).filter(TicketCategory.id == category_id).one_or_none()
            if row is not None:
                row.parent_category_id = discord_category_id

    def _member_open_ticket(self, guild_id: str, discord_user_id: str) -> Optional[dict]:
        with session_scope() as db:
            ticket = (
                db.query(Ticket)
                .filter(
                    Ticket.guild_id == guild_id,
                    Ticket.opener_discord_id == discord_user_id,
                    Ticket.status == "open",
                )
                .one_or_none()
            )
            if ticket is None:
                return None
            return {"id": ticket.id, "channel_id": ticket.channel_id}

    def _get_ticket_by_channel(self, channel_id: str) -> Optional[dict]:
        with session_scope() as db:
            ticket = db.query(Ticket).filter(Ticket.channel_id == channel_id).one_or_none()
            if ticket is None:
                return None
            return {
                "id": ticket.id,
                "guild_id": ticket.guild_id,
                "channel_id": ticket.channel_id,
                "category_id": ticket.category_id,
                "opener_discord_id": ticket.opener_discord_id,
                "opener_username": ticket.opener_username,
                "subject": ticket.subject,
                "status": ticket.status,
                "transcript_slug": ticket.transcript_slug,
            }

    def _get_category(self, category_id: int) -> Optional[dict]:
        with session_scope() as db:
            c = db.query(TicketCategory).filter(TicketCategory.id == category_id).one_or_none()
            if c is None:
                return None
            return {
                "id": c.id,
                "label": c.label,
                "parent_category_id": c.parent_category_id,
                "extra_role_ids": json.loads(c.extra_role_ids or "[]"),
            }

    # ── Ticket lifecycle ────────────────────────────────────────────────────────

    async def open_ticket_modal(self, interaction: discord.Interaction, *, category_id: int) -> None:
        existing = self._member_open_ticket(str(interaction.guild_id), str(interaction.user.id))
        if existing is not None:
            channel = interaction.guild.get_channel(int(existing["channel_id"])) if interaction.guild else None
            mention = channel.mention if channel else "your existing ticket"
            await interaction.response.send_message(
                f"You already have an open ticket: {mention}", ephemeral=True
            )
            return

        category = self._get_category(category_id)
        if category is None:
            await interaction.response.send_message(
                "That ticket category no longer exists.", ephemeral=True
            )
            return

        await interaction.response.send_modal(TicketOpenModal(self, category_id))

    async def create_ticket(
        self,
        interaction: discord.Interaction,
        *,
        category_id: int,
        subject: str,
        description: str,
        opener: discord.Member | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This can only be used in the server.", ephemeral=True)
            return

        opener = opener or interaction.user
        on_behalf_of = opener.id != interaction.user.id

        # Re-check for a race between opening the modal and submitting it.
        existing = self._member_open_ticket(str(guild.id), str(opener.id))
        if existing is not None:
            message = (
                f"{opener.mention} already has an open ticket." if on_behalf_of else "You already have an open ticket."
            )
            await interaction.response.send_message(message, ephemeral=True)
            return

        settings = _load_settings_dict(str(guild.id))
        category = self._get_category(category_id)
        if settings is None or category is None:
            await interaction.response.send_message(
                "Ticketing isn't configured for this server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        parent_category = await self._ensure_category_channel(guild, category)
        staff_roles = self._staff_roles(guild, settings, category)

        overwrites: dict = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            opener: discord.PermissionOverwrite.from_pair(_OPENER_PERMS, discord.Permissions.none()),
        }
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite.from_pair(_MANAGE_PERMS, discord.Permissions.none())

        slug = _slugify(getattr(opener, "name", "member"))
        reason = (
            f"Ticket opened by {interaction.user} for {opener}" if on_behalf_of else f"Ticket opened by {interaction.user}"
        )
        channel = await guild.create_text_channel(
            name=f"ticket-{slug}",
            category=parent_category,
            overwrites=overwrites,
            reason=reason,
        )

        with session_scope() as db:
            ticket = Ticket(
                guild_id=str(guild.id),
                channel_id=str(channel.id),
                category_id=category_id,
                opener_discord_id=str(opener.id),
                opener_username=str(opener),
                subject=subject,
                description=description,
                status="open",
                transcript_slug=_generate_transcript_slug(),
            )
            db.add(ticket)

        embed = discord.Embed(
            title=subject or "New Ticket",
            description=description or "(no description provided)",
            color=discord.Color.from_rgb(140, 29, 64),
        )
        embed.add_field(name="Opened by", value=opener.mention, inline=True)
        embed.add_field(name="Category", value=category["label"], inline=True)

        role_mentions = " ".join(role.mention for role in staff_roles)
        content = f"{opener.mention} {role_mentions}".strip()

        await channel.send(content=content or None, embed=embed, view=TicketControlView(self))
        confirmation = (
            f"Ticket created for {opener.mention}: {channel.mention}"
            if on_behalf_of
            else f"Your ticket has been created: {channel.mention}"
        )
        await interaction.followup.send(confirmation, ephemeral=True)

    @slash_command(**_ticket_command_kwargs("new-ticket", "Open a ticket on behalf of a member."))
    async def new_ticket(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member = Option(discord.Member, "Member to open the ticket for"),
        category: str = Option(str, "Ticket category", autocomplete=_category_autocomplete),
        subject: str = Option(str, "Ticket subject", required=False, default=""),
        description: str = Option(str, "Ticket description", required=False, default=""),
    ) -> None:
        if ctx.guild is None or ctx.guild.id != self.guild_id:
            await ctx.respond("This command can only be used in the configured server.", ephemeral=True)
            return

        try:
            category_id = int(category)
        except (TypeError, ValueError):
            await ctx.respond("Invalid ticket category.", ephemeral=True)
            return

        await self.create_ticket(
            ctx.interaction,
            category_id=category_id,
            subject=subject,
            description=description,
            opener=user,
        )

    async def close_ticket(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        ticket = self._get_ticket_by_channel(str(channel.id))
        if ticket is None:
            await interaction.response.send_message("This channel isn't a tracked ticket.", ephemeral=True)
            return
        if ticket["status"] == "closed":
            await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
            return

        guild = interaction.guild
        member = interaction.user
        is_opener = str(member.id) == ticket["opener_discord_id"]
        is_staff = False
        if guild is not None and ticket["category_id"] is not None:
            settings = _load_settings_dict(str(guild.id)) or {"staff_role_ids": []}
            category = self._get_category(ticket["category_id"]) or {"extra_role_ids": []}
            staff_role_ids = {*settings.get("staff_role_ids", []), *category.get("extra_role_ids", [])}
            member_role_ids = {str(r.id) for r in getattr(member, "roles", [])}
            is_staff = bool(staff_role_ids & member_role_ids)

        if not (is_opener or is_staff):
            await interaction.response.send_message(
                "You don't have permission to close this ticket.", ephemeral=True
            )
            return

        await interaction.response.defer()

        opener_target = discord.Object(id=int(ticket["opener_discord_id"]))
        await channel.set_permissions(
            opener_target, overwrite=discord.PermissionOverwrite(view_channel=False)
        )

        with session_scope() as db:
            row = db.query(Ticket).filter(Ticket.id == ticket["id"]).one_or_none()
            if row is not None:
                row.status = "closed"
                row.closed_by = str(member.id)
                row.closed_at = datetime.utcnow()

        await interaction.followup.send(
            f"Ticket closed by {member.mention}.", view=TicketDeleteView(self)
        )

    async def delete_ticket(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        ticket = self._get_ticket_by_channel(str(channel.id))
        if ticket is None:
            await interaction.response.send_message("This channel isn't a tracked ticket.", ephemeral=True)
            return

        await interaction.response.send_message("Deleting ticket channel…", ephemeral=True)
        await self._finalize_transcript(channel, ticket)
        await channel.delete(reason=f"Ticket deleted by {interaction.user}")

    async def _finalize_transcript(self, channel: discord.TextChannel, ticket: dict) -> None:
        """Mark the ticket's (already live-captured) transcript as finalized and, if configured, post a link to it."""
        slug = ticket.get("transcript_slug") or _generate_transcript_slug()

        with session_scope() as db:
            row = db.query(Ticket).filter(Ticket.id == ticket["id"]).one_or_none()
            if row is not None:
                row.transcript_captured_at = datetime.utcnow()
                if not row.transcript_slug:
                    row.transcript_slug = slug

        settings = _load_settings_dict(ticket["guild_id"]) or {}
        transcript_channel_id = settings.get("transcript_channel_id")
        if not transcript_channel_id:
            return

        transcript_channel = channel.guild.get_channel(int(transcript_channel_id))
        if transcript_channel is None:
            return

        url = f"{CONFIG.PUBLIC_BASE_URL}/admin/tickets/transcript/{slug}"
        embed = discord.Embed(
            title=ticket.get("subject") or "Ticket transcript",
            description=(
                f"Opened by {ticket.get('opener_username') or ticket['opener_discord_id']}\n\n"
                f"[View full transcript]({url})"
            ),
            color=discord.Color.from_rgb(140, 29, 64),
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=f"#{channel.name}")
        try:
            await transcript_channel.send(embed=embed)
        except discord.HTTPException:
            logger.exception("Failed to post ticket transcript link for channel %s", channel.id)

    # ── Dashboard-triggered actions ─────────────────────────────────────────────

    async def publish_panel(self) -> dict:
        """Post or update the ticket panel message from current TicketSettings. Returns status info."""
        settings = _load_settings_dict(str(self.guild_id))
        if settings is None or not settings.get("panel_channel_id"):
            raise RuntimeError("Ticket settings are not configured (no panel channel set)")

        guild = await self._resolve_guild()
        channel = guild.get_channel(int(settings["panel_channel_id"]))
        if channel is None:
            raise RuntimeError("Configured panel channel could not be found")

        embed = _build_panel_embed(settings)
        view = TicketPanelView(self, settings["categories"], settings.get("select_placeholder") or "Select a ticket category…")

        message = None
        if settings.get("panel_message_id"):
            try:
                message = await channel.fetch_message(int(settings["panel_message_id"]))
            except discord.NotFound:
                message = None

        if message is not None:
            await message.edit(embed=embed, view=view)
        else:
            message = await channel.send(embed=embed, view=view)

        with session_scope() as db:
            row = (
                db.query(TicketSettings)
                .filter(TicketSettings.guild_id == str(self.guild_id))
                .one_or_none()
            )
            if row is not None:
                row.panel_message_id = str(message.id)

        return {"channel_id": str(channel.id), "message_id": str(message.id)}
