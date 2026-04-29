"""Shared fixtures for the forklift test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from asu_discord.models import SalesforceOpportunity, StudentProfile


# ---------------------------------------------------------------------------
# Discord object factories
# ---------------------------------------------------------------------------

def make_role(role_id: int, name: str = "role") -> MagicMock:
    role = MagicMock()
    role.id = role_id
    role.name = name
    return role


def make_member(member_id: int = 1, roles: list | None = None) -> MagicMock:
    member = MagicMock()
    member.id = member_id
    member.roles = roles or []
    member.remove_roles = AsyncMock()
    member.add_roles = AsyncMock()
    return member


def make_guild(guild_id: int = 1234, roles: dict[int, MagicMock] | None = None) -> MagicMock:
    role_map = roles or {}
    guild = MagicMock()
    guild.id = guild_id
    guild.get_role = lambda rid: role_map.get(rid)
    return guild


# ---------------------------------------------------------------------------
# StudentProfile factories
# ---------------------------------------------------------------------------

def make_opportunity(**kwargs) -> SalesforceOpportunity:
    defaults = {
        "stageName": "Enrolled",
        "termCode": "2267",
        "career": "Undergraduate",
        "type": "First Time Freshman",
    }
    defaults.update(kwargs)
    return SalesforceOpportunity.model_validate(defaults)


def make_student_profile(**kwargs) -> StudentProfile:
    defaults = {
        "asurite": "testuser",
        "opportunities": [],
    }
    defaults.update(kwargs)
    return StudentProfile.model_validate(defaults)


@pytest.fixture
def verified_role_id() -> int:
    return 9001


@pytest.fixture
def unverified_role_id() -> int:
    return 9002


@pytest.fixture
def guild_id() -> int:
    return 1234


@pytest.fixture
def mock_guild(guild_id, verified_role_id, unverified_role_id):
    verified = make_role(verified_role_id, "Verified")
    unverified = make_role(unverified_role_id, "Unverified")
    return make_guild(guild_id, {verified_role_id: verified, unverified_role_id: unverified})


@pytest.fixture
def mock_bot(guild_id, mock_guild):
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=mock_guild)
    bot.fetch_guild = AsyncMock(return_value=mock_guild)
    return bot


@pytest.fixture
def cog(mock_bot, guild_id, verified_role_id, unverified_role_id):
    from asu_discord.cogs.verification import VerificationCog
    return VerificationCog(
        mock_bot,
        guild_id=guild_id,
        verified_role_id=verified_role_id,
        unverified_role_id=unverified_role_id,
    )
