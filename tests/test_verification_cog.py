"""Async tests for VerificationCog helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from asu_discord.cogs.verification import VerificationCog
from asu_discord.roles import ROLE_ID_MAP
from tests.conftest import make_guild, make_member, make_role


# ---------------------------------------------------------------------------
# _remove_role
# ---------------------------------------------------------------------------

class TestRemoveRole:
    async def test_returns_false_when_role_is_none(self, cog):
        member = make_member()
        result = await cog._remove_role(member, None, label="verified", reason="test")
        assert result is False
        member.remove_roles.assert_not_called()

    async def test_returns_false_when_member_lacks_role(self, cog):
        role = make_role(999)
        member = make_member(roles=[])
        result = await cog._remove_role(member, role, label="verified", reason="test")
        assert result is False
        member.remove_roles.assert_not_called()

    async def test_returns_true_and_removes_role_when_present(self, cog):
        role = make_role(999)
        member = make_member(roles=[role])
        result = await cog._remove_role(member, role, label="verified", reason="test")
        assert result is True
        member.remove_roles.assert_called_once_with(role, reason="test")


# ---------------------------------------------------------------------------
# _remove_verified_role / _remove_unverified_role
# ---------------------------------------------------------------------------

class TestRemoveVerifiedRole:
    async def test_removes_when_member_has_role(self, cog, mock_guild, verified_role_id):
        verified_role = mock_guild.get_role(verified_role_id)
        member = make_member(roles=[verified_role])
        result = await cog._remove_verified_role(mock_guild, member, reason="test")
        assert result is True

    async def test_returns_false_when_wrong_guild(self, cog, verified_role_id):
        wrong_guild = make_guild(guild_id=9999, roles={verified_role_id: make_role(verified_role_id)})
        member = make_member(roles=[make_role(verified_role_id)])
        result = await cog._remove_verified_role(wrong_guild, member, reason="test")
        assert result is False

    async def test_returns_false_when_member_lacks_role(self, cog, mock_guild):
        member = make_member(roles=[])
        result = await cog._remove_verified_role(mock_guild, member, reason="test")
        assert result is False


class TestRemoveUnverifiedRole:
    async def test_removes_when_member_has_role(self, cog, mock_guild, unverified_role_id):
        unverified_role = mock_guild.get_role(unverified_role_id)
        member = make_member(roles=[unverified_role])
        result = await cog._remove_unverified_role(mock_guild, member, reason="test")
        assert result is True

    async def test_returns_false_when_wrong_guild(self, cog, unverified_role_id):
        wrong_guild = make_guild(guild_id=9999, roles={unverified_role_id: make_role(unverified_role_id)})
        member = make_member(roles=[make_role(unverified_role_id)])
        result = await cog._remove_unverified_role(wrong_guild, member, reason="test")
        assert result is False


# ---------------------------------------------------------------------------
# _apply_ban_discord_roles
# ---------------------------------------------------------------------------

class TestApplyBanDiscordRoles:
    async def test_removes_verified_role(self, cog, mock_guild, verified_role_id):
        verified_role = mock_guild.get_role(verified_role_id)
        member = make_member(roles=[verified_role])
        await cog._apply_ban_discord_roles(mock_guild, member, reason="ban test")
        member.remove_roles.assert_called()

    async def test_removes_managed_roles(self, cog, mock_guild):
        managed_role_id = next(iter(ROLE_ID_MAP.values()))
        managed_role = make_role(managed_role_id, "First Year")
        member = make_member(roles=[managed_role])
        await cog._apply_ban_discord_roles(mock_guild, member, reason="ban test")
        member.remove_roles.assert_called()

    async def test_assigns_unverified_role(self, cog, mock_guild, unverified_role_id):
        unverified_role = mock_guild.get_role(unverified_role_id)
        member = make_member(roles=[])
        await cog._apply_ban_discord_roles(mock_guild, member, reason="ban test")
        member.add_roles.assert_called_once_with(unverified_role, reason="ban test")

    async def test_does_not_add_unverified_if_already_has_it(self, cog, mock_guild, unverified_role_id):
        unverified_role = mock_guild.get_role(unverified_role_id)
        member = make_member(roles=[unverified_role])
        await cog._apply_ban_discord_roles(mock_guild, member, reason="ban test")
        member.add_roles.assert_not_called()

    async def test_handles_no_managed_roles(self, cog, mock_guild):
        member = make_member(roles=[])
        await cog._apply_ban_discord_roles(mock_guild, member, reason="ban test")
        # Should complete without error; remove_roles for managed roles not called
        # add_roles called for unverified role
        unverified_role = mock_guild.get_role(cog.unverified_role_id)
        member.add_roles.assert_called_once_with(unverified_role, reason="ban test")


# ---------------------------------------------------------------------------
# _get_verified_role / _get_unverified_role
# ---------------------------------------------------------------------------

class TestGetVerifiedRole:
    def test_returns_role_for_correct_guild(self, cog, mock_guild, verified_role_id):
        role = cog._get_verified_role(mock_guild)
        assert role is not None
        assert role.id == verified_role_id

    def test_returns_none_for_none_guild(self, cog):
        assert cog._get_verified_role(None) is None

    def test_returns_none_for_wrong_guild(self, cog, verified_role_id):
        wrong_guild = make_guild(guild_id=9999, roles={verified_role_id: make_role(verified_role_id)})
        assert cog._get_verified_role(wrong_guild) is None


class TestGetUnverifiedRole:
    def test_returns_role_for_correct_guild(self, cog, mock_guild, unverified_role_id):
        role = cog._get_unverified_role(mock_guild)
        assert role is not None
        assert role.id == unverified_role_id

    def test_returns_none_for_none_guild(self, cog):
        assert cog._get_unverified_role(None) is None

    def test_returns_none_for_wrong_guild(self, cog, unverified_role_id):
        wrong_guild = make_guild(guild_id=9999, roles={unverified_role_id: make_role(unverified_role_id)})
        assert cog._get_unverified_role(wrong_guild) is None
