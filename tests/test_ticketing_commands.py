"""Permission rules behind the /ticket commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from asu_discord.cogs.ticketing import TicketingCog
from tests.conftest import make_guild, make_role

STAFF_ROLE = "500"
CATEGORY_ROLE = "600"


def make_cog() -> TicketingCog:
    return TicketingCog(MagicMock(), guild_id=1234)


def make_ticket(category_id: int | None = 7, status: str = "open") -> dict:
    return {
        "id": 1,
        "guild_id": "1234",
        "channel_id": "777",
        "category_id": category_id,
        "opener_discord_id": "42",
        "status": status,
        "transcript_slug": "abc123",
    }


def member_with_roles(*role_ids: str) -> MagicMock:
    member = MagicMock()
    member.id = 99
    member.roles = [make_role(int(rid)) for rid in role_ids]
    return member


def patch_settings(staff_roles=(STAFF_ROLE,), category_roles=(CATEGORY_ROLE,)):
    return (
        patch(
            "asu_discord.cogs.ticketing._load_settings_dict",
            return_value={"staff_role_ids": list(staff_roles)},
        ),
        patch.object(
            TicketingCog, "_get_category", return_value={"extra_role_ids": list(category_roles)}
        ),
    )


@pytest.mark.parametrize(
    "roles, expected",
    [
        ((STAFF_ROLE,), True),        # global staff role
        ((CATEGORY_ROLE,), True),     # category-specific extra role
        (("999",), False),            # unrelated role
        ((), False),                  # no roles at all
    ],
)
def test_is_staff_accepts_global_and_category_roles(roles, expected):
    cog = make_cog()
    settings_patch, category_patch = patch_settings()
    with settings_patch, category_patch:
        assert cog._is_staff(make_guild(), member_with_roles(*roles), make_ticket()) is expected


def test_global_staff_applies_to_uncategorized_tickets():
    """The dashboard promises global staff roles reach every ticket, so a ticket whose
    category was deleted must not lock staff out."""
    cog = make_cog()
    settings_patch, category_patch = patch_settings()
    with settings_patch, category_patch:
        assert cog._is_staff(
            make_guild(), member_with_roles(STAFF_ROLE), make_ticket(category_id=None)
        ) is True


@pytest.mark.asyncio
async def test_delete_is_staff_only():
    cog = make_cog()
    interaction = MagicMock()
    interaction.channel = MagicMock(id=777, delete=AsyncMock())
    interaction.response.send_message = AsyncMock()
    interaction.user = member_with_roles("999")

    with (
        patch.object(TicketingCog, "_get_ticket_by_channel", return_value=make_ticket()),
        patch.object(TicketingCog, "_is_staff", return_value=False),
        patch.object(TicketingCog, "_finalize_transcript", new=AsyncMock()) as finalize,
    ):
        await cog.delete_ticket(interaction)

    interaction.channel.delete.assert_not_called()
    finalize.assert_not_called()
    assert "Only staff" in interaction.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_close_applies_overwrite_to_a_real_member():
    """set_permissions raises InvalidArgument on a bare discord.Object, which silently
    broke the Close button — the overwrite target must be a resolved Member."""
    cog = make_cog()
    opener = MagicMock(spec=discord.Member)
    opener.id = 42
    guild = make_guild()
    guild.get_member = lambda uid: opener if uid == 42 else None

    interaction = MagicMock()
    interaction.guild = guild
    interaction.channel = MagicMock(id=777, set_permissions=AsyncMock())
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = member_with_roles(STAFF_ROLE)

    with (
        patch.object(TicketingCog, "_get_ticket_by_channel", return_value=make_ticket()),
        patch.object(TicketingCog, "_is_staff", return_value=True),
        patch("asu_discord.cogs.ticketing.session_scope"),
    ):
        await cog.close_ticket(interaction)

    target = interaction.channel.set_permissions.call_args.args[0]
    assert not isinstance(target, discord.Object)
    assert isinstance(target, discord.Member)
    assert interaction.channel.set_permissions.call_args.kwargs["overwrite"].view_channel is False
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_close_still_works_when_opener_left_the_guild():
    """A departed opener has no overwrite to revoke, but the ticket must still close."""
    cog = make_cog()
    guild = make_guild()
    guild.get_member = lambda uid: None
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "gone"))

    interaction = MagicMock()
    interaction.guild = guild
    interaction.channel = MagicMock(id=777, set_permissions=AsyncMock())
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = member_with_roles(STAFF_ROLE)

    with (
        patch.object(TicketingCog, "_get_ticket_by_channel", return_value=make_ticket()),
        patch.object(TicketingCog, "_is_staff", return_value=True),
        patch("asu_discord.cogs.ticketing.session_scope"),
    ):
        await cog.close_ticket(interaction)

    interaction.channel.set_permissions.assert_not_called()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reopen_restores_opener_access():
    cog = make_cog()
    opener = MagicMock(spec=discord.Member)
    opener.id = 42
    guild = make_guild()
    guild.get_member = lambda uid: opener if uid == 42 else None

    interaction = MagicMock()
    interaction.guild = guild
    interaction.channel = MagicMock(id=777, set_permissions=AsyncMock())
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = member_with_roles(STAFF_ROLE)

    with (
        patch.object(
            TicketingCog, "_get_ticket_by_channel", return_value=make_ticket(status="closed")
        ),
        patch.object(TicketingCog, "_is_staff", return_value=True),
        patch("asu_discord.cogs.ticketing.session_scope"),
    ):
        await cog.reopen_ticket(interaction)

    target = interaction.channel.set_permissions.call_args.args[0]
    overwrite = interaction.channel.set_permissions.call_args.kwargs["overwrite"]
    assert isinstance(target, discord.Member) and target.id == 42  # the opener
    assert overwrite.view_channel is True


@pytest.mark.asyncio
async def test_reopen_rejects_already_open_ticket():
    cog = make_cog()
    interaction = MagicMock()
    interaction.channel = MagicMock(id=777, set_permissions=AsyncMock())
    interaction.response.send_message = AsyncMock()

    with patch.object(TicketingCog, "_get_ticket_by_channel", return_value=make_ticket()):
        await cog.reopen_ticket(interaction)

    interaction.channel.set_permissions.assert_not_called()
    assert "already open" in interaction.response.send_message.call_args.args[0]
