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

    def __init__(self, message: str, *, status: int | None = None, payload: Dict[str, Any] | None = None):
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
        response = requests.post(cfg.token_url, data=data, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Discord token exchange request failed: %s", exc)
        raise DiscordAPIError("Unable to reach Discord for token exchange") from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        logger.error("Discord token exchange failed: %s", payload)
        raise DiscordAPIError("Discord token exchange failed", status=response.status_code, payload=payload)

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
        raise DiscordAPIError("Failed to fetch Discord user profile", status=response.status_code, payload=payload)

    return _safe_json(response)


def assign_verified_role(user_id: str, *, asurite: str | None = None) -> None:
    _config()  # Ensure Discord configuration is present before attempting role assignment

    bot = get_running_bot()
    loop = get_running_loop()
    if bot is None or loop is None or loop.is_closed():
        raise DiscordAPIError("Discord bot is not running; unable to assign verified role")

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
    "assign_verified_role",
    "build_authorize_url",
    "exchange_code_for_token",
    "fetch_user_profile",
]
