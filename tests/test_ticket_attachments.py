"""Ticket image attachments: which ones get stored, and under what filename."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from asu_discord.cogs.ticketing import (
    _MAX_STORED_ATTACHMENT_BYTES,
    TicketingCog,
    _message_row_kwargs,
    _stored_attachment_name,
)


def make_attachment(
    attachment_id: int = 111,
    filename: str = "screenshot.png",
    content_type: str | None = "image/png",
    size: int = 1024,
) -> MagicMock:
    attachment = MagicMock()
    attachment.id = attachment_id
    attachment.filename = filename
    attachment.content_type = content_type
    attachment.size = size
    attachment.url = "https://cdn.discordapp.com/attachments/1/2/screenshot.png"
    return attachment


def test_image_stored_under_snowflake_name():
    assert _stored_attachment_name(make_attachment()) == "111.png"


def test_extension_comes_from_whitelist_not_user_filename():
    # A crafted filename must not escape the attachment directory or pick its own extension.
    traversal = make_attachment(filename="../../../etc/cron.d/payload.sh")
    assert _stored_attachment_name(traversal) is None

    disguised = make_attachment(filename="../../evil.png")
    assert _stored_attachment_name(disguised) == "111.png"


def test_non_images_and_oversized_files_are_skipped():
    assert _stored_attachment_name(make_attachment(content_type="application/pdf")) is None
    assert _stored_attachment_name(make_attachment(content_type=None)) is None
    assert _stored_attachment_name(make_attachment(filename="notes.txt")) is None
    assert (
        _stored_attachment_name(make_attachment(size=_MAX_STORED_ATTACHMENT_BYTES + 1)) is None
    )


def test_row_records_stored_name_only_for_downloaded_images():
    image = make_attachment(attachment_id=1, filename="a.png")
    document = make_attachment(attachment_id=2, filename="b.pdf", content_type="application/pdf")

    message = MagicMock()
    message.attachments = [image, document]
    message.embeds = []

    attachments = json.loads(_message_row_kwargs(message, {1: "1.png"})["attachments"])

    assert attachments[0]["stored"] == "1.png"
    assert attachments[1]["stored"] is None
    # The original CDN url is kept either way, so nothing is lost for old rows.
    assert all(a["url"].startswith("https://cdn.discordapp.com/") for a in attachments)


# ---------------------------------------------------------------------------
# Only channels tracked in the tickets table get captured
# ---------------------------------------------------------------------------

def make_message(guild_id: int = 1234, channel_name: str = "ticket-someone") -> MagicMock:
    message = MagicMock()
    message.id = 555
    message.guild = MagicMock(id=guild_id)
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 777
    message.channel.name = channel_name
    message.attachments = [make_attachment()]
    return message


@pytest.mark.asyncio
async def test_untracked_channel_downloads_nothing():
    """A channel named like a ticket but absent from the tickets table is ignored,
    so its images never land on disk."""
    cog = TicketingCog(MagicMock(), guild_id=1234)

    with (
        patch.object(TicketingCog, "_ticket_id_for_channel", return_value=None),
        patch("asu_discord.cogs.ticketing._download_images", new=AsyncMock()) as download,
        patch.object(TicketingCog, "_save_ticket_message") as save,
    ):
        await cog.on_message(make_message())

    download.assert_not_called()
    save.assert_not_called()


@pytest.mark.asyncio
async def test_tracked_channel_is_captured_even_when_renamed():
    cog = TicketingCog(MagicMock(), guild_id=1234)

    with (
        patch.object(TicketingCog, "_ticket_id_for_channel", return_value=42),
        patch("asu_discord.cogs.ticketing._download_images", new=AsyncMock(return_value={111: "111.png"})),
        patch.object(TicketingCog, "_save_ticket_message") as save,
    ):
        await cog.on_message(make_message(channel_name="renamed-by-staff"))

    assert save.call_args.args[0] == 42
    assert save.call_args.args[2] == {111: "111.png"}


@pytest.mark.asyncio
async def test_other_guild_is_ignored():
    cog = TicketingCog(MagicMock(), guild_id=1234)

    with patch.object(TicketingCog, "_ticket_id_for_channel") as lookup:
        await cog.on_message(make_message(guild_id=9999))

    lookup.assert_not_called()
