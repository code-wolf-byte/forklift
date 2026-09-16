"""Discord OAuth2 and guild role helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict
from urllib.parse import urlencode

import requests

from utils.settings import DISCORD_CONFIG, DiscordConfig
from .cogs.verification import VerificationCog
from .models import DiscordProfile, DiscordTokenData, StudentProfile
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


def _dispatch_to_cog(
    user_id: str,
    make_coroutine: Callable[[VerificationCog, int], Any],
    *,
    action: str,
) -> None:
    """Resolve the running bot/cog, parse user_id, dispatch a coroutine, and wait."""
    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError(f"Discord bot is not running; unable to {action}")

    try:
        discord_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DiscordAPIError("Invalid Discord user id") from exc

    cog = bot.get_cog("VerificationCog")
    if not isinstance(cog, VerificationCog):
        raise DiscordAPIError("Verification cog is not loaded in the Discord bot")

    future = asyncio.run_coroutine_threadsafe(make_coroutine(cog, discord_user_id), loop)
    try:
        future.result(timeout=DEFAULT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        future.cancel()
        raise DiscordAPIError(f"Timed out {action}") from exc
    except Exception as exc:
        raise DiscordAPIError(f"Failed to {action}: {exc}") from exc


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


def exchange_code_for_token(code: str) -> DiscordTokenData:
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

    return DiscordTokenData.model_validate(_safe_json(response))


def fetch_user_profile(access_token: str) -> DiscordProfile:
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

    return DiscordProfile.model_validate(_safe_json(response))


def _verification_enabled() -> bool:
    """Whether the admin verification switch is on.

    Deferred import: utils.app_settings reaches back into asu_discord.roles.
    """
    from utils.app_settings import get

    return bool(get("verification_enabled"))


def assign_verified_role(user_id: str, *, asurite: str | None = None) -> None:
    """Grant the verified role, unless verification is switched off.

    While off the CAS/OAuth flow is unchanged and the member is still recorded,
    but no roles move: the verified role is not granted and the unverified role
    is not removed. Returns rather than raising, because the OAuth callback
    turns a DiscordAPIError into a 502. The /verify and whitelist slash commands
    call the cog directly and are deliberately not gated.
    """
    if not _verification_enabled():
        logger.info(
            "Verification disabled — skipping verified role for Discord user %s (ASURITE: %s)",
            user_id,
            asurite,
        )
        return
    _config()
    _dispatch_to_cog(
        user_id,
        lambda cog, uid: cog.verify_member_by_id(uid, asurite=asurite),
        action="assign verified role",
    )


def remove_verified_role(user_id: str, *, reason: str | None = None) -> None:
    _config()
    _dispatch_to_cog(
        user_id,
        lambda cog, uid: cog.unverify_member_by_id(uid, reason=reason),
        action="remove verified role",
    )


def assign_roles_from_profile(user_id: str, student_profile: StudentProfile) -> None:
    """Assign Salesforce-derived roles, unless verification is switched off."""
    if not _verification_enabled():
        logger.info(
            "Verification disabled — skipping Salesforce roles for Discord user %s", user_id
        )
        return
    _config()
    _dispatch_to_cog(
        user_id,
        lambda cog, uid: cog.assign_roles_from_profile(uid, student_profile),
        action="assign Salesforce-based roles",
    )


def refresh_roles_from_profile(user_id: str, student_profile: StudentProfile) -> None:
    """Remove all ROLE_ID_MAP roles from a Discord member and re-assign from Salesforce."""
    _config()
    _dispatch_to_cog(
        user_id,
        lambda cog, uid: cog.refresh_roles_from_profile(uid, student_profile),
        action="refresh Salesforce-based roles",
    )


def remove_roles_from_profile(user_id: str, student_profile: StudentProfile) -> None:
    _config()
    _dispatch_to_cog(
        user_id,
        lambda cog, uid: cog.remove_roles_from_profile(uid, student_profile),
        action="remove Salesforce-based roles",
    )


_DISCORD_TEXT_CHANNEL_TYPES = frozenset({0, 5})   # GUILD_TEXT, GUILD_ANNOUNCEMENT
_DISCORD_FORUM_CHANNEL_TYPES = frozenset({15})    # GUILD_FORUM


def get_guild_channels(
    *, channel_types: frozenset[int] | None = None
) -> list[dict]:
    """Return guild channels as {id, name, type} dicts, text-only by default.

    Uses the Discord REST API directly so it works whether or not the bot
    process is running.
    """
    wanted = channel_types or _DISCORD_TEXT_CHANNEL_TYPES
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
            {"id": ch["id"], "name": ch["name"], "type": ch["type"]}
            for ch in channels
            if ch.get("type") in wanted
        ],
        key=lambda c: c["name"],
    )


def get_guild_roles() -> list[dict]:
    """Return assignable guild roles as {id, name, color, position} dicts.

    Skips @everyone and integration-managed roles, which an admin cannot assign.
    Ordered highest-first to match how roles read in the Discord UI.
    """
    cfg = _config()
    url = f"{cfg.api_base}/guilds/{cfg.guild_id}/roles"
    headers = {"Authorization": f"Bot {cfg.bot_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Failed to fetch guild roles from Discord API: %s", exc)
        return []

    if response.status_code >= 400:
        logger.error("Discord API returned %s fetching guild roles", response.status_code)
        return []

    payload = response.json()
    roles = payload if isinstance(payload, list) else []
    return sorted(
        [
            {
                "id": role["id"],
                "name": role["name"],
                "color": role.get("color", 0),
                "position": role.get("position", 0),
            }
            for role in roles
            if role["id"] != str(cfg.guild_id) and not role.get("managed")
        ],
        key=lambda r: -r["position"],
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
    _dispatch_to_cog(
        discord_user_id,
        lambda cog, uid: cog.add_role_to_member_by_id(uid, role_name),
        action=f"add role {role_name!r}",
    )


def remove_role_from_member(discord_user_id: str, role_name: str) -> None:
    """Immediately remove a named role from a guild member (called from a non-async thread)."""
    _dispatch_to_cog(
        discord_user_id,
        lambda cog, uid: cog.remove_role_from_member_by_id(uid, role_name),
        action=f"remove role {role_name!r}",
    )


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


def check_member_has_any_role(discord_user_id: str, role_ids: list[str]) -> bool:
    """Return True if the Discord user has any of the given role IDs in the guild."""
    if not role_ids:
        return False
    bot = get_running_bot()
    if bot is None:
        return False
    cfg = _config()
    guild = bot.get_guild(int(cfg.guild_id))
    if guild is None:
        return False
    member = guild.get_member(int(discord_user_id))
    if member is None:
        return False
    member_role_ids = {str(r.id) for r in member.roles}
    return bool(member_role_ids & set(role_ids))


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
    "check_member_has_any_role",
    "check_member_is_admin",
    "exchange_code_for_token",
    "fetch_user_profile",
    "get_guild_channels",
    "get_guild_roles",
    "get_member_info",
    "refresh_roles_from_profile",
    "remove_role_from_member",
    "remove_roles_from_profile",
    "remove_verified_role",
    "search_members",
    "send_channel_message",
]
