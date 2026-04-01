"""Discord OAuth2 and guild role helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict
from urllib.parse import urlencode

import requests

from utils.settings import DISCORD_CONFIG, DiscordConfig
from .cogs.verification import VerificationCog
from .shared import get_running_bot, get_running_loop

DEFAULT_TIMEOUT = 10
logger = logging.getLogger(__name__)


class DiscordAPIError(RuntimeError):
    """Raised when Discord API requests fail."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        payload: Dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


def _config() -> DiscordConfig:
    if DISCORD_CONFIG is None:
        raise DiscordAPIError(
            "Discord configuration is missing. Ensure Discord environment variables are set.",
            status=None,
        )
    return DISCORD_CONFIG


def build_authorize_url(state: str) -> str:
    cfg = _config()
    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scope,
        "state": state,
        "prompt": "consent",
    }
    return f"{cfg.authorize_base}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    cfg = _config()
    data = {
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        response = requests.post(
            cfg.token_url, data=data, headers=headers, timeout=DEFAULT_TIMEOUT
        )
    except requests.RequestException as exc:
        logger.error("Discord token exchange request failed: %s", exc)
        raise DiscordAPIError("Unable to reach Discord for token exchange") from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        logger.error("Discord token exchange failed: %s", payload)
        raise DiscordAPIError(
            "Discord token exchange failed",
            status=response.status_code,
            payload=payload,
        )

    return _safe_json(response)


def fetch_user_profile(access_token: str) -> Dict[str, Any]:
    cfg = _config()
    url = f"{cfg.api_base}/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Discord user profile request failed: %s", exc)
        raise DiscordAPIError("Unable to reach Discord to fetch user profile") from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        logger.error("Discord user profile fetch failed: %s", payload)
        raise DiscordAPIError(
            "Failed to fetch Discord user profile",
            status=response.status_code,
            payload=payload,
        )

    return _safe_json(response)


def assign_verified_role(user_id: str, *, asurite: str | None = None) -> None:
    _config()  # Ensure Discord configuration is present before attempting role assignment

    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError(
            "Discord bot is not running; unable to assign verified role"
        )

    try:
        discord_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id for role assignment") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.verify_member_by_id(discord_user_id, asurite=asurite),
        loop,
    )

    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError("Timed out assigning Discord verified role") from exc
    except Exception as exc:
        raise DiscordAPIError(f"Failed to assign Discord verified role: {exc}") from exc


def remove_verified_role(user_id: str, *, reason: str | None = None) -> None:
    _config()  # Ensure Discord configuration is present before attempting role removal

    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError(
            "Discord bot is not running; unable to remove verified role"
        )

    try:
        discord_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id for role removal") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.unverify_member_by_id(discord_user_id, reason=reason),
        loop,
    )

    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError("Timed out removing Discord verified role") from exc
    except Exception as exc:
        raise DiscordAPIError(f"Failed to remove Discord verified role: {exc}") from exc


def assign_roles_from_profile(user_id: str, student_profile: Dict[str, Any]) -> None:
    """
    Assign additional Discord roles to a user based on their Salesforce profile.
    """
    _config()  # Ensure Discord configuration is present before attempting role assignment

    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError(
            "Discord bot is not running; unable to assign Salesforce-based roles"
        )

    try:
        discord_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id for role assignment") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.assign_roles_from_profile(discord_user_id, student_profile),
        loop,
    )

    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError(
            "Timed out assigning Discord roles from Salesforce profile"
        ) from exc
    except Exception as exc:
        raise DiscordAPIError(
            f"Failed to assign Discord roles from Salesforce profile: {exc}"
        ) from exc


def refresh_roles_from_profile(user_id: str, student_profile: Dict[str, Any]) -> None:
    """
    Remove all ROLE_ID_MAP roles from a Discord member and re-assign based on their
    current Salesforce profile. Used by the automated role-refresh cron job.
    """
    _config()

    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError(
            "Discord bot is not running; unable to refresh Salesforce-based roles"
        )

    try:
        discord_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id for role refresh") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.refresh_roles_from_profile(discord_user_id, student_profile),
        loop,
    )

    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError(
            "Timed out refreshing Discord roles from Salesforce profile"
        ) from exc
    except Exception as exc:
        raise DiscordAPIError(
            f"Failed to refresh Discord roles from Salesforce profile: {exc}"
        ) from exc


def remove_roles_from_profile(user_id: str, student_profile: Dict[str, Any]) -> None:
    """
    Remove Discord roles from a user based on their Salesforce profile.
    """
    _config()  # Ensure Discord configuration is present before attempting role removal

    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError(
            "Discord bot is not running; unable to remove Salesforce-based roles"
        )

    try:
        discord_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id for role removal") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.remove_roles_from_profile(discord_user_id, student_profile),
        loop,
    )

    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError(
            "Timed out removing Discord roles from Salesforce profile"
        ) from exc
    except Exception as exc:
        raise DiscordAPIError(
            f"Failed to remove Discord roles from Salesforce profile: {exc}"
        ) from exc


_DISCORD_TEXT_CHANNEL_TYPES = {0, 5}  # GUILD_TEXT, GUILD_ANNOUNCEMENT


def get_guild_channels() -> list[dict]:
    """Return text channels in the guild as a list of {id, name} dicts.

    Uses the Discord REST API directly so it works whether or not the bot
    process is running.
    """
    cfg = _config()
    url = f"{cfg.api_base}/guilds/{cfg.guild_id}/channels"
    headers = {"Authorization": f"Bot {cfg.bot_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Failed to fetch guild channels from Discord API: %s", exc)
        return []

    if response.status_code >= 400:
        logger.error("Discord API returned %s fetching guild channels", response.status_code)
        return []

    channels = response.json() if isinstance(response.json(), list) else []
    return sorted(
        [
            {"id": ch["id"], "name": ch["name"]}
            for ch in channels
            if ch.get("type") in _DISCORD_TEXT_CHANNEL_TYPES
        ],
        key=lambda c: c["name"],
    )


def send_channel_message(channel_id: str, content: str) -> None:
    """Send a message to a Discord text channel (called from a non-async thread)."""
    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError("Discord bot is not running; unable to send channel message")

    async def _send() -> None:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            raise DiscordAPIError(f"Channel {channel_id} not found in bot cache")
        await channel.send(content)

    future = asyncio.run_coroutine_threadsafe(_send(), loop)
    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError("Timed out sending Discord channel message") from exc
    except DiscordAPIError:
        raise
    except Exception as exc:
        raise DiscordAPIError(f"Failed to send Discord channel message: {exc}") from exc


def add_role_to_member(discord_user_id: str, role_name: str) -> None:
    """Immediately add a named role to a guild member (called from a non-async thread)."""
    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError("Discord bot is not running; unable to add role")

    try:
        user_id = int(discord_user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.add_role_to_member_by_id(user_id, role_name), loop
    )
    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError("Timed out adding role") from exc
    except Exception as exc:
        raise DiscordAPIError(f"Failed to add role: {exc}") from exc


def remove_role_from_member(discord_user_id: str, role_name: str) -> None:
    """Immediately remove a named role from a guild member (called from a non-async thread)."""
    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError("Discord bot is not running; unable to remove role")

    try:
        user_id = int(discord_user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(
        cog.remove_role_from_member_by_id(user_id, role_name), loop
    )
    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError("Timed out removing role") from exc
    except Exception as exc:
        raise DiscordAPIError(f"Failed to remove role: {exc}") from exc


def search_members(query: str, *, limit: int = 25) -> list[dict]:
    """Search guild members by display name or username (bot cache, no API call).

    Returns a list of dicts with keys: discord_user_id, username, display_name, avatar.
    """
    bot = get_running_bot()
    if bot is None:
        return []
    cfg = _config()
    guild = bot.get_guild(int(cfg.guild_id))
    if guild is None:
        return []

    q = query.strip().lower()
    results = []
    for member in guild.members:
        if q in member.name.lower() or (member.display_name and q in member.display_name.lower()):
            results.append({
                "discord_user_id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "avatar": str(member.display_avatar.url) if member.display_avatar else None,
            })
            if len(results) >= limit:
                break
    return results


def get_member_info(discord_user_id: str) -> dict | None:
    """Return basic info for a guild member from the bot cache."""
    bot = get_running_bot()
    if bot is None:
        return None
    cfg = _config()
    guild = bot.get_guild(int(cfg.guild_id))
    if guild is None:
        return None
    try:
        member = guild.get_member(int(discord_user_id))
    except (TypeError, ValueError):
        return None
    if member is None:
        return None
    return {
        "discord_user_id": str(member.id),
        "username": member.name,
        "display_name": member.display_name,
        "avatar": str(member.display_avatar.url) if member.display_avatar else None,
    }


def check_member_is_admin(discord_user_id: str) -> bool:
    """Return True if the Discord user has Administrator permission in the guild."""
    bot = get_running_bot()
    if bot is None:
        return False
    cfg = _config()
    guild = bot.get_guild(int(cfg.guild_id))
    if guild is None:
        return False
    member = guild.get_member(int(discord_user_id))
    return bool(member and member.guild_permissions.administrator)


def _safe_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    return {"text": response.text}


__all__ = [
    "DiscordAPIError",
    "add_role_to_member",
    "assign_verified_role",
    "assign_roles_from_profile",
    "build_authorize_url",
    "check_member_is_admin",
    "exchange_code_for_token",
    "fetch_user_profile",
    "get_guild_channels",
    "get_member_info",
    "refresh_roles_from_profile",
    "remove_role_from_member",
    "remove_roles_from_profile",
    "remove_verified_role",
    "search_members",
    "send_channel_message",
]
